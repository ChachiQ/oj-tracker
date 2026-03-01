# OJ Tracker - OJ做题追踪与分析系统

[English](README_EN.md) | 中文

帮助家长追踪孩子在多个OJ平台的做题情况，自动分析弱项，提供针对性训练建议和能力报表。

## 功能概览

- **多平台同步** - 支持洛谷、BBC OJ（HOJ系统）、一本通OJ、CTOJ酷思未来、代码部落，爬虫插件化架构可轻松扩展
- **同步/AI解耦** - 内容同步与AI分析独立运行，SyncJob任务追踪，支持暂停/恢复
- **Dashboard总览** - 统计卡片、雷达图、热力图（可选时间范围）、难度分布、刷题日历
- **知识点图谱** - ECharts力导向图，6阶段分层展示（语法基础→NOI），节点三色状态
- **弱项识别** - 基于年龄/年级的阶段期望值对比，自动检测薄弱知识点
- **AI分析** - 多模型支持（Claude/OpenAI/智谱），4阶段流水线：题目分类→提交评审→知识点评估→综合报告
- **周报/月报/季度报告** - 自动生成学习报告，AI分析日志链降低重复分析成本
- **KaTeX数学渲染** - 题目描述和AI分析结果中的数学公式自动渲染
- **练习推荐** - 基于弱项的智能题目推荐
- **可配置时区** - DISPLAY_TIMEZONE_OFFSET 支持全局时区偏移设置

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Flask 3.1 + SQLAlchemy 2.0 + SQLite |
| 前端 | Jinja2 + Bootstrap 5 + ECharts |
| 爬虫 | requests + BeautifulSoup4（插件化架构）|
| 定时任务 | APScheduler |
| AI分析 | Claude / OpenAI / 智谱（多模型可配置）|
| 数据分析 | pandas + numpy |
| 测试 | pytest（292个测试用例）|

## 目录结构

```
oj-tracker/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # 配置类 (Dev/Prod/Testing)
│   ├── extensions.py        # db, login_manager, migrate, csrf
│   ├── models/              # 11张数据库表 + 1关联表
│   ├── scrapers/            # OJ爬虫插件 (自动发现+注册)
│   ├── analysis/            # 分析引擎 + AI分析 + LLM抽象层
│   │   ├── engine.py        # AnalysisEngine 统计引擎
│   │   ├── weakness.py      # WeaknessDetector 弱项识别
│   │   ├── trend.py         # TrendAnalyzer 趋势分析
│   │   ├── recommender.py   # ProblemRecommender 推荐
│   │   ├── ai_analyzer.py   # AIAnalyzer 提交评审
│   │   ├── problem_classifier.py  # ProblemClassifier 题目分类
│   │   ├── knowledge_analyzer.py  # KnowledgeAnalyzer 知识点评估
│   │   ├── report_generator.py    # ReportGenerator 报告生成
│   │   ├── llm/             # 多模型LLM抽象层
│   │   └── prompts/         # AI Prompt模板
│   ├── services/            # SyncService, StatsService, AIBackfillService, TagMapper
│   ├── views/               # Flask蓝图路由 (9个蓝图)
│   ├── templates/           # Jinja2模板
│   ├── static/              # CSS/JS
│   └── tasks/               # APScheduler定时任务
├── migrations/              # Alembic数据库迁移
├── tests/                   # pytest测试套件 (292个用例)
├── backfill_tags.py         # 标签回填脚本
├── seed_data.py             # 知识点种子数据 (80+标签)
├── run.py                   # 启动入口
└── requirements.txt
```

## 快速开始

### 环境要求

- Python 3.9+
- pip

### 安装

```bash
git clone https://github.com/<your-username>/oj-tracker.git
cd oj-tracker
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 配置

创建 `.env` 文件（可选，覆盖默认配置）：

```bash
# Flask
SECRET_KEY=your-secret-key
FLASK_ENV=development

# AI 配置 (至少配一个)
AI_PROVIDER=zhipu          # zhipu / claude / openai
ZHIPU_API_KEY=your-key
ANTHROPIC_API_KEY=your-key
OPENAI_API_KEY=your-key

# AI 预算控制
AI_MONTHLY_BUDGET=5.0

# 爬虫频率 (请求间隔秒数)
SCRAPER_RATE_LIMIT=0.5

# 定时任务
SCHEDULER_ENABLED=false

# 显示时区偏移 (默认 UTC+8)
DISPLAY_TIMEZONE_OFFSET=8
```

也可以使用环境特定配置文件 `.env.development` 或 `.env.production`。

### 初始化数据库

```bash
# 创建数据库表
flask db upgrade

# 导入知识点种子数据 (80+标签，6阶段体系)
python seed_data.py
```

### 启动

```bash
python run.py
# 访问 http://localhost:5000
```

生产环境：

```bash
FLASK_ENV=production gunicorn run:app -b 0.0.0.0:5000
```

### 运行测试

```bash
pytest tests/ -v
```

## 数据库模型

```
User 1──N Student 1──N PlatformAccount 1──N Submission N──1 Problem N──M Tag
                                                │
                                           N AnalysisResult
          Problem 1──N AnalysisResult
          Student 1──N AnalysisLog
          Student 1──N Report
          User 1──N UserSetting
          User 1──N SyncJob
```

| 模型 | 说明 |
|------|------|
| User | 用户（家长），密码哈希存储 |
| Student | 学生，关联年级/生日/目标阶段，支持年龄感知分析 |
| PlatformAccount | OJ平台账号凭据与同步状态 |
| Problem | 题目信息，多对多关联Tag |
| Submission | 提交记录，关联题目和平台账号 |
| Tag | 知识点标签，带阶段(stage)和前置依赖 |
| AnalysisResult | AI分析结果，可关联Submission或Problem |
| AnalysisLog | AI分析日志链，降低重复分析成本 |
| Report | 周报/月报/季度报告 |
| UserSetting | 用户级配置 key-value 存储 |
| SyncJob | 同步/AI回填任务执行历史与进度 |

## 已支持的OJ平台

| 平台 | 标识 | 对接方式 |
|------|------|----------|
| 洛谷 | `luogu` | JSON API（x-lentille-request 头获取数据）|
| BBC OJ | `bbcoj` | HOJ系统 REST API |
| 一本通 | `ybt` | PHP系统 HTML/JS 解析 |
| CTOJ 酷思未来 | `ctoj` | Hydro系统 REST API |
| 代码部落 | `coderlands` | 自研系统 REST API（Cookie 认证）|

### 添加新平台

爬虫采用插件化架构，只需新增一个文件即可支持新OJ：

```python
# app/scrapers/new_oj.py
from app.scrapers.base import BaseScraper
from app.scrapers.common import register_scraper

@register_scraper('new_oj', '新平台名称')
class NewOJScraper(BaseScraper):
    PLATFORM = 'new_oj'
    BASE_URL = 'https://new-oj.com'

    def fetch_submissions(self, uid, cursor=None):
        ...
    def fetch_problem(self, problem_id):
        ...
```

文件放入 `app/scrapers/` 目录后自动发现注册，无需修改任何核心代码。

## 知识点6阶段体系

| 阶段 | 名称 | 示例知识点 |
|------|------|-----------|
| 1 | 语法基础 | 变量、循环、数组、字符串、函数 |
| 2 | 基础算法 | 排序、二分查找、模拟、贪心入门、BFS/DFS入门 |
| 3 | CSP-J（入门组）| 递归与分治、动态规划入门、图论基础、STL容器 |
| 4 | CSP-S（提高组）| 线段树、树链剖分、网络流、DP优化 |
| 5 | 省选 | 后缀数组、点分治、虚树、多项式 |
| 6 | NOI | FFT/NTT、持久化数据结构、博弈论 |

年级与阶段映射：小三~小四→阶段1-2，小五~小六→阶段1-3，初一~初二→阶段1-4，初三~高一→阶段1-5，高二~高三→阶段1-6。

## 配置环境

| 环境 | 用途 | 数据库 | 定时任务 |
|------|------|--------|---------|
| development | 本地开发 | `instance/dev.db` | 关闭 |
| production | 线上服务 | `instance/prod.db` | 开启 |
| testing | 自动化测试 | 内存SQLite | 关闭 |

切换方式：设置 `FLASK_ENV` 环境变量或传入 `create_app(config_name)`。

## API端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard/<student_id>` | GET | Dashboard统计数据 |
| `/api/knowledge/<student_id>` | GET | 知识点图谱数据 |
| `/api/weakness/<student_id>` | GET | 弱项分析数据 |
| `/api/trend/<student_id>` | GET | 趋势分析数据 |
| `/api/submissions/<student_id>` | GET | 提交记录（分页、筛选）|
| `/api/knowledge/<student_id>/analyze` | POST | 知识点AI评估（SSE流式）|
| `/api/knowledge/<student_id>/assessment` | GET | 获取知识点评估结果 |
| `/api/knowledge/<student_id>/assessment/<log_id>` | DELETE | 删除知识点评估 |
| `/api/problems` | GET | 题目列表（分页、筛选）|
| `/api/problem/<problem_id>/solution` | POST | AI生成题目解析 |
| `/api/problem/<problem_id>/full-solution` | POST | AI生成完整题解 |
| `/api/problem/<problem_id>/resync` | POST | 重新同步题目信息 |
| `/api/submission/<submission_id>/review` | POST | AI评审提交代码 |
| `/api/problem/<problem_id>/classify` | POST | AI分类题目 |
| `/api/problem/<problem_id>/comprehensive` | POST | 一键综合分析 |

所有API端点需要登录且只能访问自己孩子的数据。

## 页面路由

| 路由 | 说明 |
|------|------|
| `/auth/register` | 注册 |
| `/auth/login` | 登录 |
| `/auth/logout` | 登出 |
| `/dashboard/` | Dashboard总览 |
| `/student/` | 学生管理 |
| `/student/add` | 添加学生 |
| `/student/<id>/edit` | 编辑学生 |
| `/knowledge/` | 知识点图谱 |
| `/report/` | 报告列表 |
| `/report/<id>` | 报告详情 |
| `/report/generate` | 生成报告 |
| `/report/<id>/delete` | 删除报告 |
| `/report/<id>/regenerate` | 重新生成报告 |
| `/sync/log` | 同步日志 |
| `/problem/` | 题目库 |
| `/problem/<id>` | 题目详情 |
| `/settings/` | 设置（平台账号管理）|
| `/logs/` | Web 日志查看器 |

## 关键设计

### 爬虫插件化
- `BaseScraper` 抽象基类定义统一契约
- `@register_scraper` 装饰器自动注册
- `pkgutil` + `importlib` 实现自动发现
- `ScrapedSubmission`/`ScrapedProblem` 统一中间数据格式
- 增量同步机制（`sync_cursor`）

### AI分析多模型支持
- `BaseLLMProvider` 抽象基类
- 支持 Claude/OpenAI/智谱，通过配置一键切换
- Prompt模板与模型解耦
- 4阶段流水线：题目分类(ProblemClassifier)→提交评审(AIAnalyzer)→知识点评估(KnowledgeAnalyzer)→综合报告(ReportGenerator)
- `AI_MONTHLY_BUDGET` 预算控制，用户级 AI 配置

### 同步/AI解耦
- 内容同步(SyncService)与AI分析(AIBackfillService)完全解耦
- SyncJob 模型记录任务执行历史，支持进度轮询
- AI回填作为独立后台任务，不阻塞同步流程
- TagMapper 服务：OJ原生标签→知识点体系映射

### 报告系统
- 支持周报、月报、季度报告三种周期
- ReportGenerator 基于 AnalysisLog 链生成报告
- 报告支持生成、删除、重新生成操作
- KaTeX 渲染数学公式

### 分析日志链
- `AnalysisLog` 表作为AI记忆
- 周报→月报链式传递上下文
- 避免重复分析，降低token消耗

### 年龄感知分析
- Student模型包含birthday和grade
- 弱项识别自动过滤超龄知识点
- AI分析Prompt注入年龄上下文

## 版本规划

### v0.1.0 (2026-02-13) -- 项目初始化 ✅

全部基础功能完成：
- Flask应用骨架、9张数据库表、用户认证
- 3个OJ爬虫（洛谷/BBC OJ/一本通）
- 统计分析引擎、弱项识别、趋势分析
- AI分析引擎（多模型LLM支持）
- Dashboard、知识点图谱、报告等全部页面
- APScheduler定时任务
- 120个自动化测试用例

### v0.2.0 (2026-02-14) -- 设置页面完善 ✅

- BBC OJ / 一本通OJ 平台绑定支持（密码登录 + 会话冲突提示）
- REQUIRES_LOGIN 爬虫标记：区分需登录与公开 API 平台
- 同步错误追踪（last_sync_error）+ 定时同步自动跳过需登录平台
- AI 提供者可配置：支持 Claude/OpenAI/智谱 三家切换
- 用户级 API KEY 管理 + 月度预算 + 用量统计
- UserSetting 模型：用户配置 key-value 存储
- 211个自动化测试用例

### v0.3.0 / v0.3.1 (2026-02-14 ~ 2026-02-15) -- 爬虫稳定性 & 题库 UX ✅

- 爬虫稳定性：连续失败追踪、平台级共享限流、洛谷429重试、MAX_PAGES安全限制
- Dashboard/知识图谱完善：近期提交、推荐练习、字段修复
- 同步 AJAX 化 + 全屏 spinner 进度展示
- 题库 UX：智能时间展示、快速 tooltip、分页跳转
- 8个新知识点标签 + 中文描述 + upsert 种子

### v0.4.0 / v0.4.1 (2026-02-15) -- 分析与可视化增强 ✅

- Dashboard增强：首次AC率卡片、提交状态分布图、周趋势图、平台分布统计
- 知识图谱交互：前置依赖链高亮、效率指标、跳转题库、全屏模式、旋转、标签重叠优化
- 能力评分优化：时间衰减、阶段自适应权重
- AI评估报告分页，阶段进度详情

### v0.5.0 (2026-02-15) -- AI题目分析 + 代码分析 + 知识评估增强 ✅

- AI题目思路分析与完整解题
- 提交代码AI审查（质量评估、优缺点、改进建议）
- 同步后自动触发AI分析
- 知识评估注入代码审查洞察
- `AnalysisResult` 支持关联 Problem（`problem_id_ref`）

### v0.5.1 (2026-02-18) -- 报告系统重构 + 同步解耦 + UX全面优化 ✅

- 同步/AI解耦：SyncJob模型、AIBackfillService独立后台任务
- 季度报告、报告删除/重新生成、智能周期选择器、重复检测
- KaTeX数学公式渲染
- 热力图时间范围切换、可配置显示时区
- 平台账号暂停/恢复、题库筛选改进
- 285个自动化测试用例

### v0.6.0 (2026-02-22) -- CTOJ平台 + 一键综合分析 + 全局同步进度 + 图片多模态AI ✅

- CTOJ（酷思未来）爬虫：Hydro系统 REST API 对接
- 一键综合分析：合并3次串行LLM调用为1次，支持并发AI回填
- Web日志查看器（/logs页面）+ 全局同步进度条
- 图片渲染 + AI多模态支持
- 大量AI分析稳定性修复（GLM-5兼容、JSON容错、超时控制）
- 292个自动化测试用例

### v1.0.0 (2026-03-02) -- 第一个正式版 ✅

- 代码部落（Coderlands）爬虫：Cookie 认证、hash-based 增量同步、UUID 三级解析
- Cookie 更新 UI、题目分析页、KaTeX 数学渲染、未AC题目筛选
- 爬虫子系统设计文档 + Phase 0 API 探测 SOP
- Bootstrap Modal 统一组件替代原生对话框
- 大量修复：UUID 解析、时间戳 UTC 转换、AI JSON 韧性、Markdown/LaTeX 保护
- 5 个 OJ 平台全面支持、292个自动化测试用例

### v1.1.0 -- 部署与扩展

计划内容：
- 云服务器部署方案（Gunicorn + Nginx）
- 学校/机构OJ适配器（根据实际页面结构实现）
- PDF报表导出

## 实施阶段 (Phases)

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 - 核心骨架 | Flask app factory, 数据库模型, 登录注册, 基础布局 | ✅ |
| Phase 2 - 爬虫系统 | BaseScraper抽象基类, 3个爬虫, SyncService, 账号管理, 种子数据 | ✅ |
| Phase 3 - 分析与可视化 | AnalysisEngine, Dashboard, WeaknessDetector, TrendAnalyzer, 知识点图谱 | ✅ |
| Phase 4 - AI分析与推荐 | AI 4阶段流水线, 同步/AI解耦, AIBackfillService, SyncJob, 292个测试 | ✅ |
| Phase 4.5 - 代码部落 + 文档 | Coderlands 爬虫, Cookie 认证 UI, 爬虫设计文档, v1.0.0 release | ✅ |
| Phase 5 - 部署与扩展 | 云部署, 学校OJ适配, PDF导出 | 计划中 |

## 开发指南

### 开发约定
- Python代码遵循 PEP 8
- 模型关系使用 `back_populates`（非 `backref`）
- 视图函数需要 `@login_required`
- 所有表单需要 CSRF 保护
- 日志使用 `logging` 模块
- 配置通过环境变量管理

### 运行测试

```bash
source venv/bin/activate
pytest tests/ -v --tb=short
```

测试套件包含 292 个测试用例，覆盖：
- 模型层：11个模型的CRUD、关系、约束
- 认证：注册、登录、登出、权限控制
- 视图层：所有路由的GET/POST响应
- API层：JSON端点响应与权限
- 爬虫：注册表、数据类、枚举
- 分析引擎：统计、弱项、趋势、AI分析
- 服务层：同步服务、统计服务、AI回填服务
- 标签映射：TagMapper 测试

## License

[GPL-3.0](LICENSE)
