# OJ 爬虫设计文档

> 最后更新：2026-02-28
>
> 本文档记录 OJ 爬虫子系统的架构设计、各平台实现细节和已知陷阱。
> 修改爬虫代码时 **必须** 同步更新本文档（见第七部分维护清单）。

---

## 目录

1. [架构概览](#1-架构概览)
2. [基础设施](#2-基础设施)
3. [各平台深度解析](#3-各平台深度解析)
4. [跨平台通用模式](#4-跨平台通用模式)
5. [新平台接入指南](#5-新平台接入指南)
6. [已知问题与改进方向](#6-已知问题与改进方向)
7. [维护清单](#7-维护清单)

---

## 1. 架构概览

### 插件体系

```
BaseScraper (ABC)                   @register_scraper 装饰器
     │                                     │
     ├── LuoguScraper      ←──── luogu.py  │  自动发现
     ├── BBCOJScraper       ←──── bbcoj.py  │  _auto_discover()
     ├── YBTScraper         ←──── ybt.py    │  遍历 __init__.py
     ├── CTOJScraper        ←──── ctoj.py   │  所在目录的模块
     └── CoderlandsScraper  ←──── coderlands.py
```

每个爬虫是一个独立 Python 模块。`__init__.py` 启动时通过 `_auto_discover()` 自动
导入所有模块（排除 `base`, `common`, `rate_limiter`），触发 `@register_scraper`
装饰器将类注册到 `_registry` 字典。

### 数据流

```
用户触发同步
    │
    ▼
SyncService.sync_account(account_id)
    │
    ├── get_scraper_instance(platform, auth_cookie=..., auth_password=...)
    │
    ├── scraper.fetch_submissions(platform_uid, since, cursor)
    │       │
    │       └── yield ScrapedSubmission(...)  ← 统一中间格式
    │
    ├── 去重：Submission.query.filter_by(platform_record_id=...)
    │
    ├── _ensure_problem(platform, problem_id, scraper)
    │       │
    │       ├── Problem 已存在 → 回填缺失字段
    │       └── Problem 不存在 → scraper.fetch_problem() → 建 Problem → TagMapper
    │
    ├── 创建 Submission 记录
    │
    ├── 可选: scraper.fetch_submission_code(record_id)
    │
    └── 更新 sync_cursor / last_sync_at → commit
```

### ScrapedSubmission 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `platform_record_id` | `str` | 平台唯一提交ID（部分平台含命名空间，如 `domain/rid`） |
| `problem_id` | `str` | 平台题目ID（部分含命名空间，如 `domain/pid`，Coderlands 用 `P{no}`） |
| `status` | `str` | 统一状态枚举值：AC/WA/TLE/MLE/RE/CE/UNKNOWN/PENDING/JUDGING |
| `score` | `int \| None` | 得分，10分制（YBT）或100分制（其他） |
| `language` | `str \| None` | 编程语言名称 |
| `time_ms` | `int \| None` | 运行时间（毫秒） |
| `memory_kb` | `int \| None` | 内存使用（KB） |
| `submitted_at` | `datetime` | 提交时间（UTC） |
| `source_code` | `str \| None` | 源代码（通常在 fetch_submission_code 中单独获取） |

### ScrapedProblem 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `problem_id` | `str` | 平台题目ID |
| `title` | `str` | 题目标题 |
| `difficulty_raw` | `str \| None` | 平台原始难度标签 |
| `tags` | `list[str]` | 平台原始标签列表 |
| `source` | `str \| None` | 题目来源 |
| `url` | `str` | 题目页面 URL |
| `description` | `str \| None` | 题目描述 |
| `input_desc` | `str \| None` | 输入格式说明 |
| `output_desc` | `str \| None` | 输出格式说明 |
| `examples` | `str \| None` | 样例输入输出 |
| `hint` | `str \| None` | 提示/说明 |

### BaseScraper 类属性

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `PLATFORM_NAME` | `str` | `""` | 平台标识符，用于注册和数据库查询 |
| `PLATFORM_DISPLAY` | `str` | `""` | 平台中文显示名 |
| `BASE_URL` | `str` | `""` | 平台 API 基础 URL |
| `REQUIRES_LOGIN` | `bool` | `False` | 是否需要认证 |
| `SUPPORT_CODE_FETCH` | `bool` | `False` | 是否支持获取源代码 |
| `AUTH_METHOD` | `str` | `'password'` | 认证方式：`'password'` 或 `'cookie'` |

### BaseScraper 抽象方法

| 方法 | 签名 | 说明 |
|------|------|------|
| `validate_account` | `(platform_uid: str) → bool` | 验证账号有效性 |
| `fetch_submissions` | `(platform_uid, since, cursor) → Generator[ScrapedSubmission]` | 增量拉取提交记录 |
| `fetch_problem` | `(problem_id: str) → ScrapedProblem \| None` | 获取题目详情 |
| `map_status` | `(raw_status) → str` | 平台状态码 → 统一状态枚举 |
| `map_difficulty` | `(raw_difficulty) → int` | 平台难度 → 0-7 数值 |

### BaseScraper 可选覆盖方法

| 方法 | 默认行为 | 说明 |
|------|----------|------|
| `fetch_submission_code(record_id)` | `return None` | 获取提交源代码 |
| `get_problem_url(problem_id)` | `BASE_URL/problem/{id}` | 生成题目页面 URL |
| `get_auth_instructions()` | 通用 Cookie 提示 | 认证引导文案 |

---

## 2. 基础设施

### 2.1 自动发现机制

**文件**: `__init__.py`

```python
_auto_discover()  # 在模块导入时自动执行
```

- 遍历 `scrapers/` 目录下所有 Python 模块（排除 `base`, `common`, `rate_limiter`, `__init__`）
- `importlib.import_module()` 触发模块级 `@register_scraper` 装饰器
- 失败的模块会被日志记录但不阻断其他模块加载

**`get_scraper_instance(platform, **kwargs)`** 通过 `inspect.signature` 过滤参数：
- 只传递目标类 `__init__` 实际接受的 kwargs
- 避免不同爬虫 `__init__` 签名不一致导致的 TypeError
- 例：`platform_uid` 参数只有 CTOJ 和 Coderlands 接受

### 2.2 速率限制

**文件**: `rate_limiter.py`

- `RateLimiter` 类：线程安全（`threading.Lock`），保证请求间最小间隔
- **平台级共享**：`get_platform_limiter(platform, min_interval)` 维护全局 `_platform_limiters` 字典
- 同一平台的多个账号共享同一个限速器，避免并发同步时触发限流
- 默认间隔：`2.0` 秒

### 2.3 请求重试

**文件**: `base.py` → `_request_with_retry()`

- 最多 `max_retries=3` 次重试
- 指数退避：`time.sleep(2 ** attempt)` → 1s, 2s, 4s
- 每次请求前调用 `self.rate_limiter.wait()`
- 超时固定 30 秒
- `_rate_limited_get()` 是 GET 快捷方法

### 2.4 URL 解析器

**文件**: `url_parser.py`

5 个正则模式匹配题目 URL → `(platform_name, problem_id)` 元组：

| 平台 | URL 模式 | problem_id 格式 |
|------|----------|-----------------|
| luogu | `luogu.com.cn/problem/{id}` | `P1001` |
| bbcoj | `bbcoj.cn/problem/{id}` 或 `bbcoj.cn/training/{n}/problem/{id}` | `BA405` |
| ybt | `ybt.ssoier.cn:8088/problem_show.php?pid={id}` | `1234` |
| ctoj | `ctoj.ac/d/{domain}/p/{pid}` | **`domain/pid`**（双捕获组拼接） |
| coderlands | `coderlands.com/web/#/newAnswer#{UUID}` | 32位十六进制 UUID |

**注意**：CTOJ 使用双捕获组 `([^/]+)/([^/?\s]+)` 拼接为 `domain/pid` 格式。

### 2.5 增量同步

两种 cursor 策略：

| 策略 | 使用平台 | cursor 内容 | 对比方式 |
|------|----------|-------------|----------|
| record_id cursor | Luogu, BBCOJ, YBT, CTOJ | 最新提交的 `platform_record_id` | 遍历到 cursor 相同的记录即停止 |
| hash cursor | Coderlands | exercise 数据的 MD5 前16位 | 比较 hash 决定是否需要同步 |

**cursor 耦合点**（`sync_service.py:114`）：
```python
scraper_cursor = getattr(scraper, '_new_cursor', None)
if isinstance(scraper_cursor, str):
    account.sync_cursor = scraper_cursor
elif first_record_id:
    account.sync_cursor = first_record_id
```

Coderlands 爬虫通过设置 `self._new_cursor` 属性传递自定义 cursor，SyncService
通过 `getattr` 读取。其他爬虫使用默认的 `first_record_id`（最新提交ID）作为 cursor。

---

## 3. 各平台深度解析

### 3.1 洛谷 (luogu)

**文件**: `luogu.py`

#### 基本信息

| 项目 | 值 |
|------|-----|
| PLATFORM_NAME | `luogu` |
| BASE_URL | `https://www.luogu.com.cn` |
| REQUIRES_LOGIN | `False` |
| AUTH_METHOD | `password`（默认，实际不需要登录） |
| SUPPORT_CODE_FETCH | `True` |
| 系统类型 | 自研平台，JSON API |

#### API 接口

| 接口 | 方法 | URL | 说明 |
|------|------|-----|------|
| 用户验证 | GET | `/user/{uid}` | 检查 `currentData.user.uid` 存在 |
| 提交列表 | GET | `/record/list?user={uid}&page={n}` | 分页，JSON 响应 |
| 题目详情 | GET | `/problem/{pid}` | JSON 响应，含标签 ID 列表 |
| 提交代码 | GET | `/record/{record_id}` | `currentData.record.sourceCode` |

#### 认证流程

无需登录。但需要特殊请求头：
```
x-lentille-request: content-only    ← 关键：告诉服务端只返回 JSON 数据
Referer: https://www.luogu.com.cn/
```

#### 数据解析要点

- **分页**：`page` 参数，每页 `perPage`（默认20）条。`MAX_PAGES=100` 硬上限
- **状态码**：数字枚举（0=Pending, 12=AC, 6=WA 等），见 `_STATUS_MAP`
- **难度**：数字 0-7 → 中文标签（`_DIFFICULTY_LABELS`），如 `3='普及/提高-'`
- **标签**：`problem.tags` 返回的是 **标签 ID 列表**（整数），需要用 `currentData.tags` 数组交叉引用获取标签名称
- **语言**：数字 ID → 名称（`_LANG_MAP`），如 `12='C++17'`
- **时间戳**：Unix epoch 秒

#### 已知陷阱

1. **429 限流**：洛谷会返回 429 状态码，特殊处理为 `time.sleep(30)` 后重试同一页（不是指数退避）
2. **Content-Type 检查**：偶尔返回非 JSON 响应（HTML 错误页），需检查 `Content-Type` 含 `application/json` 或 `text/json`
3. **标签 ID vs 名称**：`problem.tags` 是 ID 数组而非名称，必须从 `currentData.tags` 解析 `{id → name}` 映射表

---

### 3.2 BBC OJ (bbcoj)

**文件**: `bbcoj.py`

#### 基本信息

| 项目 | 值 |
|------|-----|
| PLATFORM_NAME | `bbcoj` |
| BASE_URL | `http://bbcoj.cn` |
| REQUIRES_LOGIN | `True` |
| AUTH_METHOD | `password` |
| SUPPORT_CODE_FETCH | `True` |
| 系统类型 | HOJ (Hcode Online Judge) REST API |

#### API 接口

| 接口 | 方法 | URL | 说明 |
|------|------|-----|------|
| 登录 | POST | `/api/login` | JSON body `{username, password}` |
| 提交列表 | GET | `/api/get-submission-list?limit={n}&currentPage={p}&onlyMine=true` | 需认证 |
| 题目详情 | GET | `/api/get-problem-detail?problemId={pid}` | |
| 题目标签 | GET | `/api/get-problem-tags-and-classification?oj=ME` | |
| 提交代码 | GET | `/api/get-submission-detail?submitId={id}&cid=0` | |

#### 认证流程

1. POST `/api/login` 发送 `{username, password}`
2. 响应 `status=200` 表示成功
3. JWT Token 从 **响应头** `Authorization` 获取（注意：**无 `Bearer` 前缀**）
4. 回退：若响应头无 token，尝试从响应体 `data.token` 获取
5. 设置 `session.headers['Authorization'] = token`（直接设值，不加前缀）
6. JSESSIONID 通过 Set-Cookie 自动设置

#### 数据解析要点

- **样例格式**：XML 标签包裹 `<input>...</input><output>...</output>`，用正则提取
- **标签解析**：当前实现 `_fetch_problem_tags()` 始终返回 `[]`（tag cache 无法从分类数据反向关联到具体题目）
- **时间戳双格式**：`submitTime` 可能是 ISO-8601 字符串或 epoch 毫秒数值，需两种解析
- **题目ID**：优先用 `displayPid`（用户可见ID如 `BA405`），回退到 `pid`

#### 已知陷阱

1. **标签始终为空**：`_fetch_problem_tags()` 获取了分类数据但无法关联到具体题目，始终返回 `[]`。需要分析 HOJ API 数据结构才能修复
2. **JWT Token 位置**：HOJ 返回 JWT 在响应头 `Authorization`，不带 `Bearer` 前缀。如果加了前缀会导致 401
3. **时间戳双格式**：必须同时处理字符串和数值两种时间戳格式
4. **`displayPid` vs `pid`**：用户可见ID是 `displayPid`，内部ID是 `pid`。系统统一使用 `displayPid`

---

### 3.3 一本通 (ybt)

**文件**: `ybt.py`

> **最脆弱的爬虫**：依赖 HTML 解析和 JavaScript 变量提取，格式变更极易导致解析失败。

#### 基本信息

| 项目 | 值 |
|------|-----|
| PLATFORM_NAME | `ybt` |
| BASE_URL | `http://ybt.ssoier.cn:8088` |
| REQUIRES_LOGIN | `True` |
| AUTH_METHOD | `password` |
| SUPPORT_CODE_FETCH | `True` |
| 系统类型 | PHP 系统，HTML 页面解析 |

#### API 接口（实际都是 HTML 页面）

| 接口 | 方法 | URL | 说明 |
|------|------|-----|------|
| 登录 | POST | `/login.php` | form-encoded，follow redirect |
| 提交列表 | GET | `/status.php?showname={uid}&start={offset}` | HTML 页面，解析 JS `var ee="..."` |
| 题目详情 | GET | `/problem_show.php?pid={pid}` | HTML 页面，解析 `pshow()` 调用 |
| 提交代码 | GET | `/show_source.php?runid={rid}` | HTML `<pre>` 标签 |

#### 认证流程

1. POST `/login.php` 发送 form-encoded `{username, password}`，`allow_redirects=True`
2. 检查 PHPSESSID Cookie 是否设置
3. 检查响应中是否包含 `密码错误` 或 `用户不存在`
4. 若不确定，验证 `/member.php` 是否重定向到登录页

#### 数据解析要点

**提交列表 — `var ee` 变量**

页面内嵌 JavaScript 变量：`var ee="record1#record2#..."`

每条记录用 `#` 分隔，字段用反引号 `` ` `` 分隔：

```
Username:DisplayName`FLAG_RUNID`ProblemID`Result`LangCode`CodeLen`SubmitTime
```

- `FLAG_RUNID`：第一个字符是可见性标志（`1`=可查看源码），剩余部分是实际 `runid`
- `Result` 格式：
  - `"Accepted"` → AC, score=10
  - `"Accepted|score:4/10"` → AC, score=4
  - `"Wrong Answer|score:3/10"` → WA, score=3
  - `"C"` → CE
- `LangCode`：数字（`0`=C, `2`=C++, `7`=C++ 等）

**题目页面 — `pshow()` 调用**

题目内容通过 JavaScript 函数 `pshow("...")` 渲染，使用 **单参数双引号格式**：

```javascript
pshow("content with \\n line breaks and \\" escaped quotes")
```

提取流程：
1. 找到 `【题目描述】` 等中文节标题
2. 从标题位置向后搜索最近的 `pshow("...")` 调用
3. 反转义：`\\n` → `\n`，`\\"` → `"`，`\\'` → `'`，`\\\\` → `\`
4. **反转义顺序敏感**：必须先处理 `\\n`/`\\"` 再处理 `\\\\`
5. 最后 `html.unescape()` 处理 HTML 实体
6. 修复相对图片 URL 为绝对路径

**样例**：不使用 `pshow()`，而是 `【输入样例】<pre>...</pre>` 格式。

**时间戳**：YBT 返回 UTC+8 时间，需手动 `- timedelta(hours=8)` 转换为 UTC。

#### 已知陷阱

1. **编码是 UTF-8，不是 GBK**：虽然是古老的 PHP 系统，但使用 `resp.content.decode('utf-8', errors='replace')`。不要假设 GBK
2. **`pshow()` 是单参数格式**：只有一个双引号参数 `pshow("...")`，不是 `pshow("title", "content")` 双参数格式。正则必须匹配 `pshow\s*\(\s*"((?:[^"\\]|\\.)*)"\s*\)`
3. **中英文双状态映射**：`_RESULT_STATUS_MAP` 需同时包含英文（`Accepted`, `Wrong Answer`）和中文（`完全正确`, `答案正确`）状态文本
4. **无难度和标签**：YBT 不提供难度等级和标签分类，`difficulty_raw=None`，`tags=[]`
5. **分页偏移**：使用 `start` 参数（记录偏移），不是页码。每页 20 条

---

### 3.4 CTOJ 酷思未来 (ctoj)

**文件**: `ctoj.py`

#### 基本信息

| 项目 | 值 |
|------|-----|
| PLATFORM_NAME | `ctoj` |
| BASE_URL | `https://ctoj.ac` |
| REQUIRES_LOGIN | `True` |
| AUTH_METHOD | `password` |
| SUPPORT_CODE_FETCH | `True` |
| 系统类型 | Hydro Online Judge REST API |

#### API 接口

| 接口 | 方法 | URL | 说明 |
|------|------|-----|------|
| 登录 | POST | `/login` | JSON `{uname, password}`，成功返回 `{url: ...}` |
| 域列表 | GET | `/home/domain` | 返回 `ddocs` 数组 |
| 提交列表 | GET | `/d/{domain}/record?uidOrName={uid}&page={p}` | JSON，`Accept: application/json` |
| 题目详情 | GET | `/d/{domain}/p/{pid}` | JSON，`pdoc` 对象 |
| 提交代码 | GET | `/d/{domain}/record/{rid}` | `rdoc.code` |

#### 认证流程

1. POST `/login` 发送 JSON `{uname, password}`（注意字段是 `uname` 不是 `username`）
2. 成功：响应含 `url` 字段（重定向目标）
3. 失败：响应含 `error` 字段
4. Session cookie 自动设置
5. 所有请求需要 `Accept: application/json` 头

#### 数据解析要点

**多域架构**

CTOJ 使用 Hydro 的 domain 概念，用户可能属于多个域（如不同班级/竞赛组）：
- 登录后通过 `/home/domain` 获取 `ddocs` → 提取 `_id` 列表
- 遍历所有域拉取提交记录
- **ID 命名空间**：`problem_id = "{domain}/{pid}"`，`record_id = "{domain}/{rid}"`
- 域列表在会话内缓存（`_domains_cache`）

**题目内容解析**

`pdoc.content` 是 Markdown 格式，按 `##` 标题切分：
```markdown
## 题目描述
...
## 输入格式
...
## 输出格式
...
## 样例
...
## 提示/说明
...
```

`_parse_hydro_content()` 按 `##` 标题拆分到 `sections` 字典，通过关键词匹配映射到字段。

**难度映射**

Hydro 使用 0-10 分制，线性映射到项目 0-7 分制：`round(raw * 7 / 10)`

**内存单位**

Hydro 返回内存以 **bytes** 为单位，需 `// 1024` 转换为 KB。

#### 已知陷阱

1. **服务端已过滤用户**：`/d/{domain}/record?uidOrName={uid}` 已经在服务端按用户过滤，无需客户端再过滤。早期版本曾在客户端做 `uid` 匹配造成数据丢失（因为 Hydro 返回的 `uid` 是数字 ID 而非用户名）
2. **内存单位 bytes→KB**：Hydro 返回 `memory` 字段单位是 bytes，不是 KB。必须 `// 1024`
3. **域列表缓存**：`_domains_cache` 在 scraper 实例生命周期内不会过期。如果用户在同步期间被加入新域，本次同步不会发现
4. **登录字段是 `uname`**：不是通常的 `username`，是 Hydro 特有的

---

### 3.5 代码部落 (coderlands)

**文件**: `coderlands.py`

> **最复杂的爬虫**：Cookie 认证、hash-based 增量同步、UUID 三级解析、DB 内查询。

#### 基本信息

| 项目 | 值 |
|------|-----|
| PLATFORM_NAME | `coderlands` |
| BASE_URL | `https://course.coderlands.com` |
| REQUIRES_LOGIN | `True` |
| AUTH_METHOD | `cookie`（唯一使用 Cookie 认证的爬虫） |
| SUPPORT_CODE_FETCH | `True` |
| 系统类型 | 自研教育平台 REST API |

#### API 接口

| 接口 | 方法 | URL | 说明 |
|------|------|-----|------|
| 会话验证 | GET | `/server/student/person/center/baseInfo` | 返回 `loginName` |
| 练习数据 | POST | `/server/student/person/center/exercise` | JSON `{}`，返回 AC/未AC 题目列表 |
| 题目详情 | GET | `/server/student/stady/getClassWorkOne?uuid={}&lessonUuid=personalCenter` | **注意 "stady" 拼写** |
| 提交列表 | GET | `/server/student/stady/listSubNew?problemUuid={uuid}` | 按题目拉取 |
| 提交详情 | GET | `/server/student/stady/mDetail?uuid={submission_uuid}` | 含源代码 |
| 课节列表 | GET | `/server/student/stady/myls` | 返回 `lessonInfo[]` + `classInfo` |
| 课节内容 | GET | `/server/student/stady/getlesconNew?uuid={lessonUuid}&classUuid={classUuid}` | 返回课节内题目列表（含 UUID） |

#### 认证流程

1. 用户在浏览器登录，获取 `JSESSIONID` Cookie 值
2. 配置 `auth_cookie = "JSESSIONID=xxx"`
3. `BaseScraper._create_session()` 将 cookie 设置到 `session.headers['Cookie']`
4. API 返回 `code != 1` 且 msg 含"登录/未登录"时抛 `CoderlandsSessionExpired`

**不影响用户活跃会话**（与密码登录的平台不同）。

#### 增量同步策略（Hash-based）

不同于其他平台的 record_id cursor，Coderlands 使用 **hash-based 变更检测**：

```
1. POST exercise API → 获取 acStr（已AC题号列表）+ unAcStr（未AC题号列表）
2. 计算 exercise_hash = MD5(sorted_ac_ids + "|" + sorted_unac_ids)[:16]
3. 与上次 cursor 比较：
   - hash 未变 → 仅同步 DB 中不存在的新题目
   - hash 改变 → 同步所有未AC/新AC的题目
4. 过滤掉本地已 AC 的题目（跳过，节省 API 调用）
5. 同步完成后 self._new_cursor = exercise_hash
```

#### UUID 解析（课节遍历策略）

Coderlands 内部使用 32 位十六进制 UUID 标识题目，但 exercise API 只返回题号（数字）。
需要将题号映射到 UUID 才能调用 `listSubNew` 获取提交记录。

**重要**：`getClassWorkOne` API **只接受 32 位十六进制 UUID**，传入题号（数字）会返回 HTTP 500。

解析策略（`_resolve_uuids()`）：

```
1. 缓存命中 → 直接使用 _uuid_cache[problem_no]
2. 课节遍历 → _build_uuid_map_from_lessons()
   - GET /server/student/stady/myls → 获取 lessonInfo[] 和 classInfo.uuid
   - 对每个课节 GET /server/student/stady/getlesconNew?uuid={lessonUuid}&classUuid={classUuid}
   - 每个课节返回 dataList[]，每项含 uuid 和 name（格式 "P{no} 题目名"）
   - 从 name 字段正则提取题号，建立 problemNo → UUID 映射
```

**限制**：`myls` 只返回**当前班级**的课节。exercise API 返回的题目可能来自**过去班级**，
这些题目的 UUID 无法通过当前 API 解析。未能解析的题目会被跳过并记录警告日志。

**性能**：31 课节 × 1 API 调用 = ~60 秒（受 2 秒速率限制）。映射结果缓存在 `_uuid_cache`
中，同一 scraper 实例生命周期内不重复遍历。

#### DB 内查询（打破纯库模式）

Coderlands 爬虫 **直接导入并查询 app.models**：
```python
from app.models import Submission, PlatformAccount, Problem
```

用途：
- `_get_locally_ac_problem_ids()`: 查询本地已 AC 的题目，跳过不需要同步的
- `_get_db_known_problem_ids()`: 查询 DB 已知题目，识别新增题目

这打破了其他爬虫"纯库、不依赖 app 层"的模式，但对于 Coderlands 的增量同步策略是必要的。

#### 已知陷阱

1. **JSESSIONID 过期无自动刷新**：Cookie 过期后只能抛异常，用户需手动更新。没有自动重新登录机制
2. **getClassWorkOne 只接受 UUID**：传入题号（数字）会返回 HTTP 500。**绝不能**用题号直接调 `getClassWorkOne`。UUID 必须通过课节遍历 (`getlesconNew`) 获取
3. **myls 响应结构**：课节列表在 `result.lessonInfo[]`（不是 `dataList/data/list`）。每项含 `uuid`、`lessonName`、`status`
4. **getlesconNew 题号在 name 字段**：返回的 `dataList[].name` 格式为 `"P{no} 题目名"`，没有独立的 `problemNo` 字段。需用正则 `^P(\d+)\s` 提取
5. **过去班级题目不可见**：`myls` 只返回当前班级的课节。exercise API 返回的题目可能来自过去班级，这些题目的 UUID 无法解析（会被跳过）
6. **课节遍历耗时**：`_build_uuid_map_from_lessons()` 为每个课节发起一次 API 请求，~30 课节需要 ~60 秒（受 2 秒速率限制）。结果会缓存
7. **API 路径拼写错误**：URL 中是 `stady` 而不是 `study`——这是平台方的拼写错误，不要"修正"
8. **problem_id 格式**：使用 `P{number}` 格式（如 `P1234`），exercise API 返回 P 前缀+空格分隔，解析时用 `re.split(r'[,\s]+', ...)` + `_PNO_RE`
9. **record_id 格式**：`P{no}/{submission_uuid}`，用 `/` 分隔题目 ID 和提交 UUID
10. **DB 耦合**：直接导入 `app.models`，在无 Flask app context 环境下会失败

---

## 4. 跨平台通用模式

### 4.1 时间戳处理

| 平台 | 格式 | 时区 | 转换方式 |
|------|------|------|----------|
| Luogu | Unix epoch 秒 | UTC | `datetime.utcfromtimestamp()` |
| BBCOJ | ISO-8601 字符串 或 epoch 毫秒 | UTC | 字符串解析 或 `/ 1000.0` |
| YBT | `YYYY-MM-DD HH:MM:SS` | **UTC+8** | `strptime() - timedelta(hours=8)` |
| CTOJ | ISO-8601 字符串 或 epoch 毫秒 | UTC | 同 BBCOJ |
| Coderlands | `YYYY-MM-DD HH:MM:SS` | 未明确（假设 UTC） | `strptime()` 多格式尝试 |

**注意**：YBT 是唯一需要手动时区转换的平台。

### 4.2 错误恢复机制

**文件**: `sync_service.py:137-150`

```python
account.consecutive_sync_failures = (account.consecutive_sync_failures or 0) + 1
if account.consecutive_sync_failures >= 10:
    account.is_active = False  # 自动停用
```

- 每次同步失败：`consecutive_sync_failures += 1`，记录 `last_sync_error`
- 连续失败 **10 次**：自动停用账号（`is_active = False`）
- 同步成功：重置 `consecutive_sync_failures = 0`，清除 `last_sync_error`

### 4.3 标签映射策略

**文件**: `tag_mapper.py` → `TagMapper.map_tags()`

三级匹配策略（按优先级）：

1. **静态字典**：`{platform}_TAG_MAP` 中的 `平台标签 → [内部标签名]` 映射
2. **Tag.name 精确匹配**：直接用平台标签文本查 Tag 表
3. **Tag.display_name 精确匹配**：用平台标签文本匹配显示名

未匹配的标签通过 `logger.warning()` 记录，方便后续补充字典。

各平台静态字典覆盖率：

| 平台 | 映射条目数 | 说明 |
|------|-----------|------|
| Luogu | ~90 | 最完整，覆盖 Stage 1-6 |
| BBCOJ | ~50 | 与 Luogu 重合度高 |
| Coderlands | ~30 | 基础标签 |
| YBT | 0 | YBT 不返回标签 |
| CTOJ | 0 | 待补充 |

### 4.4 认证方式对比

| 平台 | 需要认证 | 认证方式 | 会影响活跃会话 | 会话保持 |
|------|---------|---------|-------------|---------|
| Luogu | 否 | — | — | — |
| BBCOJ | 是 | 用户名+密码 → JWT | **是**（登录会踢掉其他会话） | JWT Token + Session Cookie |
| YBT | 是 | 用户名+密码 → PHPSESSID | **是** | PHPSESSID Cookie |
| CTOJ | 是 | 用户名+密码 → Session | **是** | Hydro Session Cookie |
| Coderlands | 是 | JSESSIONID Cookie | **否** | 复用浏览器 Session |

---

## 5. 新平台接入指南

### 10 步清单

1. **新建文件**：`app/scrapers/{platform_name}.py`

2. **注册装饰器**：
   ```python
   from . import register_scraper

   @register_scraper
   class NewScraper(BaseScraper):
       ...
   ```

3. **设置类属性**：
   ```python
   PLATFORM_NAME = "new_platform"
   PLATFORM_DISPLAY = "平台中文名"
   BASE_URL = "https://..."
   REQUIRES_LOGIN = True/False
   SUPPORT_CODE_FETCH = True/False
   AUTH_METHOD = 'password'  # or 'cookie'
   ```

4. **实现抽象方法**（5 个必须）：
   - `validate_account(platform_uid) → bool`
   - `fetch_submissions(platform_uid, since, cursor) → Generator[ScrapedSubmission]`
   - `fetch_problem(problem_id) → ScrapedProblem | None`
   - `map_status(raw_status) → str`
   - `map_difficulty(raw_difficulty) → int`

5. **可选覆盖**：
   - `fetch_submission_code(record_id) → str | None`
   - `get_problem_url(problem_id) → str`
   - `get_auth_instructions() → str`
   - 如需密码登录：实现 `login()` + `_ensure_logged_in()`

6. **添加 URL 解析正则**：`url_parser.py` → `_PATTERNS` 列表

7. **添加标签映射**：`tag_mapper.py` → 新建 `{PLATFORM}_TAG_MAP` 字典并注册到 `_PLATFORM_MAPS`

8. **更新文档**：
   - 本文件 `DESIGN.md` 新增平台章节
   - `CLAUDE.md` → "已支持的OJ平台" 章节
   - `tasks/lessons.md` → 记录踩坑经验

9. **编写测试**：`tests/test_{platform_name}_scraper.py`

10. **验证同步**：手动触发同步，确认提交和题目正确入库

### 最小实现模板

```python
from __future__ import annotations

import logging
from datetime import datetime
from typing import Generator

from .base import BaseScraper
from .common import ScrapedSubmission, ScrapedProblem, SubmissionStatus
from . import register_scraper

logger = logging.getLogger(__name__)


@register_scraper
class NewPlatformScraper(BaseScraper):
    PLATFORM_NAME = "new_platform"
    PLATFORM_DISPLAY = "新平台"
    BASE_URL = "https://example.com"
    REQUIRES_LOGIN = False
    SUPPORT_CODE_FETCH = False

    def validate_account(self, platform_uid: str) -> bool:
        # TODO: 验证账号存在性
        return True

    def fetch_submissions(
        self, platform_uid: str, since: datetime = None, cursor: str = None
    ) -> Generator[ScrapedSubmission, None, None]:
        # TODO: 分页获取提交记录
        # 注意：遇到 cursor 相同的记录或 since 之前的记录时停止
        yield from []

    def fetch_problem(self, problem_id: str) -> ScrapedProblem | None:
        # TODO: 获取题目详情
        return None

    def map_status(self, raw_status) -> str:
        # TODO: 平台状态码 → SubmissionStatus 枚举值
        return SubmissionStatus.UNKNOWN.value

    def map_difficulty(self, raw_difficulty) -> int:
        # TODO: 平台难度 → 0-7 数值
        return 0
```

---

## 6. 已知问题与改进方向

### 功能缺陷

| 问题 | 影响平台 | 严重程度 | 说明 |
|------|---------|---------|------|
| 标签解析始终返回空 | BBCOJ | 中 | `_fetch_problem_tags()` 无法从分类数据关联到具体题目 |
| HTML 解析脆弱 | YBT | 高 | 依赖 `var ee` 变量和 `pshow()` 格式，页面改版即失效 |
| DB 耦合 | Coderlands | 低 | 直接导入 `app.models`，限制了独立测试 |

### 架构改进

| 方向 | 说明 |
|------|------|
| 时间戳统一化 | 各平台时间戳处理逻辑分散，可抽取到 `common.py` 工具函数 |
| 语言映射统一化 | 各平台各自维护 `_LANG_MAP`，可合并为共享映射 + 平台特定补充 |
| Cookie 自动刷新 | Coderlands JSESSIONID 过期后需手动更新，可考虑用 Selenium/Playwright 自动刷新 |
| 标签映射补全 | CTOJ 标签映射为空，需收集实际标签数据后补充 |

---

## 7. 维护清单

修改爬虫代码时，请检查以下文档是否需要同步更新：

- [ ] `app/scrapers/DESIGN.md`（本文件）— API 路径、字段名、映射表是否与代码一致
- [ ] `CLAUDE.md` — "已支持的OJ平台" 列表是否需要更新
- [ ] `app/scrapers/url_parser.py` — 新平台是否需要添加 URL 解析正则
- [ ] `app/services/tag_mapper.py` — 新标签是否需要添加映射
- [ ] `tasks/lessons.md` — 修复 bug 后是否需要追加陷阱条目
- [ ] `tests/` — 对应的测试用例是否需要更新
