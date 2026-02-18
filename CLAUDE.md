# OJ Tracker - AI 开发指南

## 项目简介
OJ做题追踪与分析系统，帮助家长追踪孩子在多个OJ平台的做题情况，分析弱项，提供针对性训练建议和能力报表。

## 目标用户
- 家长：查看孩子学习报告、能力评估
- 学生：查看知识点图谱、刷题进度

## 技术栈
- **后端**: Flask + SQLAlchemy + SQLite
- **前端**: Jinja2 + Bootstrap 5 + ECharts
- **爬虫**: requests + BeautifulSoup4 (插件化架构)
- **定时任务**: APScheduler
- **AI分析**: 多模型可配置 (Claude/OpenAI/智谱)
- **数据分析**: pandas + numpy

## 目录结构
```
oj-tracker/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # 配置类 (Dev/Prod/Testing)
│   ├── extensions.py        # db, login_manager, migrate, csrf
│   ├── models/              # SQLAlchemy 数据模型 (11张表 + 1关联表)
│   ├── scrapers/            # OJ爬虫插件 (自动发现+注册)
│   ├── analysis/            # 分析引擎 + AI分析 + LLM抽象层
│   ├── services/            # 业务服务 (同步, 统计, AI回填, 标签映射)
│   ├── views/               # Flask蓝图路由
│   ├── templates/           # Jinja2模板
│   ├── static/              # CSS/JS
│   └── tasks/               # APScheduler定时任务
├── migrations/              # Alembic数据库迁移
├── tests/                   # pytest测试套件 (285个用例)
├── backfill_tags.py         # 标签回填脚本
├── seed_data.py             # 知识点种子数据
├── run.py                   # 启动入口
└── requirements.txt
```

## 数据库模型关系
```
User 1-N Student 1-N PlatformAccount 1-N Submission N-1 Problem N-M Tag
Submission 1-N AnalysisResult
Problem 1-N AnalysisResult
Student 1-N AnalysisLog
Student 1-N Report
User 1-N UserSetting
User 1-N SyncJob
```

## 关键设计决策

### 1. 爬虫插件化
- `BaseScraper` 抽象基类定义契约
- `@register_scraper` 装饰器自动注册
- 新增OJ只需添加一个文件，零修改核心代码
- `ScrapedSubmission`/`ScrapedProblem` 统一中间数据格式

### 2. AI分析多模型支持
- `BaseLLMProvider` 抽象基类
- 支持 Claude/OpenAI/智谱，通过配置切换
- Prompt模板与模型解耦
- 4阶段流水线: 题目分类(ProblemClassifier)→提交评审(AIAnalyzer)→知识点评估(KnowledgeAnalyzer)→综合报告(ReportGenerator)
- 用户级 AI 配置：每用户可独立选择 AI 提供者、API KEY 和预算

### 3. 分析日志链
- AnalysisLog 表作为AI记忆
- 周报→月报链式传递上下文
- 避免重复分析，降低token成本

### 4. 知识点6阶段体系
- 语法基础→基础算法→CSP-J→CSP-S→省选→NOI
- 标签带stage字段，支持年龄感知过滤
- 前置依赖关系记录在prerequisite_tags

### 5. 年龄感知
- Student模型包含birthday和grade
- 弱项识别过滤超龄知识点
- AI分析Prompt注入年龄上下文

### 6. 用户级 AI 配置
- UserSetting key-value 模型存储用户偏好
- AI API KEY 优先从 UserSetting 读取，回退到环境变量
- 每用户可独立选择 AI 提供者和预算

### 7. 同步/AI 解耦
- 内容同步(SyncService)与AI分析(AIBackfillService)完全解耦
- SyncJob 模型记录任务执行历史，支持进度轮询
- AI回填作为独立后台任务，不阻塞同步流程
- TagMapper 服务：OJ原生标签→知识点体系映射

### 8. 报告系统
- 支持周报、月报、季度报告三种周期
- ReportGenerator 基于 AnalysisLog 链生成报告
- 报告支持生成、删除、重新生成操作
- KaTeX 渲染数学公式

## 开发约定
- Python 代码遵循 PEP 8
- 模型关系使用 back_populates (非 backref)
- 视图函数需要 @login_required
- 所有表单需要 CSRF 保护
- 日志使用 logging 模块
- 配置通过环境变量管理

## 已支持的OJ平台
- 洛谷 (luogu) - JSON API（无需登录）
- BBC OJ (bbcoj) - HOJ系统 REST API（需密码登录，会影响活跃会话）
- 一本通 (ybt) - PHP系统 HTML解析（需密码登录，会影响活跃会话）

## 当前进度
见 CHANGELOG.md
