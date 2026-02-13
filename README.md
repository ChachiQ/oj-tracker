# OJ Tracker - OJ做题追踪与分析系统

帮助家长追踪孩子在多个OJ平台的做题情况，自动分析弱项，提供针对性训练建议和能力报表。

## 功能概览

- **多平台同步** - 支持洛谷、BBC OJ（HOJ系统）、一本通OJ，爬虫插件化架构可轻松扩展
- **Dashboard总览** - 统计卡片、雷达图、热力图、难度分布、刷题日历
- **知识点图谱** - ECharts力导向图，6阶段分层展示（语法基础→NOI），节点三色状态
- **弱项识别** - 基于年龄/年级的阶段期望值对比，自动检测薄弱知识点
- **AI分析** - 多模型支持（Claude/OpenAI/智谱），4级分析链：题目分类→单次提交→攻克过程→综合报告
- **周报/月报** - 自动生成学习报告，AI分析日志链降低重复分析成本
- **练习推荐** - 基于弱项的智能题目推荐

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Flask 3.1 + SQLAlchemy 2.0 + SQLite |
| 前端 | Jinja2 + Bootstrap 5 + ECharts |
| 爬虫 | requests + BeautifulSoup4（插件化架构）|
| 定时任务 | APScheduler |
| AI分析 | Claude / OpenAI / 智谱（多模型可配置）|
| 数据分析 | pandas + numpy |
| 测试 | pytest（120个测试用例）|

## 目录结构

```
oj-tracker/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # 配置类 (Dev/Prod/Testing)
│   ├── extensions.py        # db, login_manager, migrate, csrf
│   ├── models/              # 9张数据库表
│   ├── scrapers/            # OJ爬虫插件 (自动发现+注册)
│   ├── analysis/            # 分析引擎 + AI分析 + LLM抽象层
│   │   ├── engine.py        # AnalysisEngine 统计引擎
│   │   ├── weakness.py      # WeaknessDetector 弱项识别
│   │   ├── trend.py         # TrendAnalyzer 趋势分析
│   │   ├── recommender.py   # ProblemRecommender 推荐
│   │   ├── llm/             # 多模型LLM抽象层
│   │   └── prompts/         # AI Prompt模板
│   ├── services/            # SyncService, StatsService
│   ├── views/               # Flask蓝图路由
│   ├── templates/           # Jinja2模板
│   ├── static/              # CSS/JS
│   └── tasks/               # APScheduler定时任务
├── migrations/              # Alembic数据库迁移
├── tests/                   # pytest测试套件
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
          Student 1──N AnalysisLog
          Student 1──N Report
```

| 模型 | 说明 |
|------|------|
| User | 用户（家长），密码哈希存储 |
| Student | 学生，关联年级/生日，支持年龄感知分析 |
| PlatformAccount | OJ平台账号凭据与同步状态 |
| Problem | 题目信息，多对多关联Tag |
| Submission | 提交记录，关联题目和平台账号 |
| Tag | 知识点标签，带阶段(stage)和前置依赖 |
| AnalysisResult | AI分析结果 |
| AnalysisLog | AI分析日志链，降低重复分析成本 |
| Report | 周报/月报 |

## 已支持的OJ平台

| 平台 | 标识 | 对接方式 |
|------|------|----------|
| 洛谷 | `luogu` | JSON API（x-lentille-request 头获取数据）|
| BBC OJ | `bbcoj` | HOJ系统 REST API |
| 一本通 | `ybt` | PHP系统 HTML/JS 解析 |

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
| `/api/problems` | GET | 题目列表（分页、筛选）|

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
| `/problem/` | 题目库 |
| `/problem/<id>` | 题目详情 |
| `/settings/` | 设置（平台账号管理）|

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
- 4级分析链：题目分类→单次提交分析→攻克过程分析→综合报告
- `AI_MONTHLY_BUDGET` 预算控制

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

### v0.2.0 -- 爬虫完善与稳定性

计划内容：
- 洛谷爬虫优化：完善登录态管理、增量同步调优
- 爬虫错误重试机制与告警
- 平台账号状态监控
- 预置6阶段知识点种子数据完善

技术要点：
- `x-lentille-request: content-only` 头优化JSON获取
- 增量同步机制（sync_cursor）调优
- 频率控制（2秒间隔）精细化管理

### v0.3.0 -- 分析与可视化增强

计划内容：
- Dashboard增强：更丰富的统计维度
- 知识点图谱交互优化：点击节点查看关联题目
- 弱项识别算法升级：增加首次通过率和平均尝试次数维度
- 能力评分公式优化

技术要点：
- ECharts图表交互事件绑定
- WeaknessDetector算法迭代

### v0.4.0 -- AI分析与推荐

计划内容：
- AI代码分析引擎深度集成
- 分析日志机制完善（AnalysisLog日志链优化）
- 智能推荐算法升级（ProblemRecommender）
- APScheduler定时同步（每6小时）+ 定时AI分析（每周）

### v0.5.0 -- 部署与扩展

计划内容：
- 云服务器部署方案（Gunicorn + Nginx）
- 学校/机构OJ适配器（根据实际页面结构实现）
- PDF报表导出
- 移动端适配

## 实施阶段 (Phases)

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 - 核心骨架 | Flask app factory, 数据库模型, 登录注册, 基础布局 | ✅ |
| Phase 2 - 爬虫系统 | BaseScraper抽象基类, 3个爬虫, SyncService, 账号管理, 种子数据 | ✅ |
| Phase 3 - 分析与可视化 | AnalysisEngine, Dashboard, WeaknessDetector, TrendAnalyzer, 知识点图谱 | ✅ |
| Phase 4 - AI分析与推荐 | AI代码分析, 分析日志链, ProblemRecommender, 定时任务 | ✅ |
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

测试套件包含 120 个测试用例，覆盖：
- 模型层：9个模型的CRUD、关系、约束
- 认证：注册、登录、登出、权限控制
- 视图层：所有路由的GET/POST响应
- API层：JSON端点响应与权限
- 爬虫：注册表、数据类、枚举
- 分析引擎：统计、弱项、趋势
- 服务层：同步服务、统计服务

## License

[GPL-3.0](LICENSE)
