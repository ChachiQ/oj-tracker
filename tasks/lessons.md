# Lessons Learned

## 1. Bootstrap 单例 Modal + Promise 竞态条件

**日期**: 2026-02-28
**相关提交**: `92ed399` (Fix ojConfirm race condition when chaining consecutive modals)

### 问题模式

单例 modal 封装为返回 Promise 的函数时，如果在 click handler 中同步 resolve Promise 再异步 hide modal，连续调用会导致第一个 modal 的 `hidden.bs.modal` 事件"偷走"第二个调用的 resolve 回调。

**根因**: Bootstrap `modal.hide()` 是异步的（有动画），但 `resolve()` 是同步的。连续调用时序：

1. 用户点击确认 → click handler 同步 resolve Promise A → 调用 `modal.hide()`
2. 调用方收到 resolve，立即发起下一个 `ojConfirm()` → 绑定新的 `hidden.bs.modal` listener
3. 第一个 modal 的 hide 动画完成 → 触发 `hidden.bs.modal` → 执行的是**第二个调用**的 listener
4. 第二个 modal 还没展示就被"关闭"了

### 规则

单例 UI 组件（modal/dialog/toast）封装为 Promise 时：

- **resolve 时机必须统一到组件完全关闭的事件中**（如 `hidden.bs.modal`）
- 用标志位（如 `confirmed = true/false`）区分确认/取消
- **绝不在 click handler 中同步 resolve 后异步 hide**

### 正确实现模式

```javascript
function ojConfirm(message) {
    return new Promise(resolve => {
        let confirmed = false;

        confirmBtn.onclick = () => { confirmed = true; modal.hide(); };
        cancelBtn.onclick = () => { confirmed = false; modal.hide(); };

        modalEl.addEventListener('hidden.bs.modal', function handler() {
            modalEl.removeEventListener('hidden.bs.modal', handler);
            resolve(confirmed);  // resolve 在动画完全结束后
        });

        modal.show();
    });
}
```

### 通用原则

**异步 UI 动画 + 共享状态 + Promise = 竞态高发区。** 状态变更必须与动画生命周期严格同步。

---

## 2. OJ 爬虫开发经验

**日期**: 2026-02-28
**参考文档**: `app/scrapers/DESIGN.md`

### 2.1 YBT 编码是 UTF-8，不是 GBK

YBT（一本通）是古老的 PHP 系统，但页面编码是 UTF-8。使用 `resp.content.decode('utf-8', errors='replace')`，不要假设 GBK。

**规则**: 不要根据系统年代猜测编码，以实际响应为准。

### 2.2 YBT pshow() 是单参数格式

YBT 题目页面的 `pshow()` 函数只有一个双引号字符串参数：
```javascript
pshow("content with \\n and \\" escapes")
```
不是 `pshow("title", "content")` 双参数格式。正则必须精确匹配单参数。

反转义顺序敏感：先处理 `\\n`/`\\"`/`\\'`，最后处理 `\\\\`。

### 2.3 CTOJ 客户端过滤陷阱

Hydro 的 `/d/{domain}/record?uidOrName={uid}` 已在服务端按用户过滤。不要在客户端再做 uid 匹配过滤——Hydro 返回的 `uid` 是数字 ID 而非用户名，客户端比对会导致所有记录被错误丢弃。

**规则**: 先确认 API 是否已做过滤，再决定是否需要客户端过滤。重复过滤不是安全，是 bug。

### 2.4 Coderlands hash cursor 耦合

Coderlands 使用 hash-based 增量同步，通过 `self._new_cursor` 属性传递自定义 cursor。SyncService 通过 `getattr(scraper, '_new_cursor', None)` 读取。

这是一个隐式耦合点——如果新爬虫也定义了 `_new_cursor` 属性，会被 SyncService 意外消费。

**规则**: 自定义 cursor 机制应在 BaseScraper 中显式声明接口，而非依赖隐式属性。

### 2.5 HOJ JWT Token 位置

BBC OJ (HOJ) 的 JWT Token 在响应头 `Authorization` 中返回，**不带 `Bearer` 前缀**。设置时直接 `session.headers['Authorization'] = token`，加了 `Bearer ` 前缀会导致 401。

**规则**: 不要假设所有 JWT 实现都遵循 `Bearer {token}` 规范。以实际 API 行为为准。

### 2.6 Coderlands getClassWorkOne 只接受 UUID

**日期**: 2026-03-01

`getClassWorkOne?uuid={param}` 的 `uuid` 参数**只接受 32 位十六进制 UUID**，传入题号会返回 HTTP 500（无错误消息）。这导致初版 UUID 解析 Stage 2 对 53 个题号发起 159 次无效 API 调用（53 × 3 重试），全部 500 错误。

**正确做法**：通过课节遍历 (`getlesconNew`) 获取 UUID。`myls` 返回 `result.lessonInfo[]`（不是 `dataList`），每个课节通过 `getlesconNew?uuid={lessonUuid}&classUuid={classUuid}` 获取题目列表，题目 UUID 在 `dataList[].uuid`，题号在 `dataList[].name` 字段（格式 `"P{no} 题目名"`，无独立 `problemNo` 字段）。

**限制**：`myls` 只返回当前班级课节，过去班级的题目 UUID 不可见。

**规则**:
- 不要猜测 API 参数的接受类型，先用诊断脚本验证
- 对未知 API 响应结构，先打印完整响应再写解析代码
- N × retry 的 API 调用模式在参数错误时会放大问题（需有快速失败机制）

### 2.7 通用规则

- **新爬虫上线前**：必须在 `app/scrapers/DESIGN.md` 中记录平台章节
- **修复爬虫 bug 后**：必须在 DESIGN.md 对应平台的"已知陷阱"节追加条目
- **修改 API 路径/字段**：同步更新 DESIGN.md 中的 API 接口表

---

## 3. 爬虫开发 SOP（标准操作流程）

**日期**: 2026-03-01
**背景**: 复盘 5 个 OJ 爬虫的开发历史，除 Luogu（公开文档化 API）外，每个平台都经历了多轮修复。根因是在不确定性最高的阶段（API 行为）投入了最多的工程量（完整实现），导致假设错误后大量返工。

### 核心原则

> **不确定性最高的部分（外部 API 行为）应该最先验证，而不是最先假设。**
>
> 经验的价值不在于记录本身，而在于转化为开发流程中的强制检查点。

### 各平台 Bug 历史

| 平台 | 提交数 | 典型 Bug | 根因 |
|------|--------|----------|------|
| Luogu | 1 | 无 | 公开文档化 API，无需猜测 |
| BBCOJ | 2 | JWT 无 Bearer 前缀 → 401 | 假设标准实现 |
| YBT | 4 | 编码假设 GBK（实际 UTF-8）、pshow 参数格式错误 | 假设 + 无预验证 |
| CTOJ | 3 | 客户端重复过滤导致 0 结果 | 不理解服务端已过滤 |
| Coderlands | 5 | UUID 只接受 hex、myls 响应结构错误 | 无文档 API 全靠猜 |

### 反模式（当前流程）

```
阅读有限信息 → 假设 API 行为 → 写完整爬虫 → 运行 → 发现假设错误 → 修复
```

### 正确流程（4 阶段）

#### Phase 0: API 探测（在写任何爬虫代码之前）

1. 创建 `scripts/probe_{platform}.py` 诊断脚本
2. 对每个将要使用的 API endpoint：
   - 调用并打印完整响应 JSON（所有字段）
   - 记录实际的 key 名、数据类型、嵌套层级
   - 记录认证方式的具体格式（Bearer/无前缀/Cookie 格式）
   - 记录编码（`resp.encoding`, `resp.apparent_encoding`）
3. 产出：一份 API 行为事实清单，作为 Phase 1 的输入

#### Phase 1: 最小可行爬虫

- 只实现 `fetch_submissions()` 核心路径
- 硬编码测试参数，不做泛化
- 立即运行验证能拿到数据

#### Phase 2: 端到端集成测试

- 通过 `SyncService` 跑完整同步
- 验证 DB 中有正确的 submissions 和 problems
- 验证增量同步（第二次运行不重复导入）

#### Phase 3: 完善与文档

- 补充错误处理、日志、edge cases
- 更新 `DESIGN.md`、`CLAUDE.md`、`tasks/lessons.md`

### 爬虫开发检查清单（plan 阶段必须逐项确认）

#### API 行为验证
- [ ] 每个 endpoint 的响应结构是否已通过诊断脚本确认？
- [ ] 认证 token 的格式是否已确认（Bearer/无前缀/其他）？
- [ ] 响应编码是否已确认（不要猜）？
- [ ] API 是否已做服务端过滤（避免客户端重复过滤）？
- [ ] API 参数的接受类型是否已确认（UUID vs 数字 vs 字符串）？

#### 数据解析验证
- [ ] 实际响应的 JSON key 名是否已确认（不要假设 dataList/data/list）？
- [ ] 字段格式是否已确认（如题号是独立字段还是嵌入在 name 中）？
- [ ] 分隔符/转义是否已确认？

#### 端到端验证
- [ ] 单独运行 scraper 能返回 submissions？
- [ ] 通过 SyncService 集成能写入 DB？
- [ ] 增量同步能正确工作（第二次不重复）？
