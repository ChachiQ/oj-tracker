# Changelog

## v0.1.0 (2026-02-13) -- 项目初始化

### 新增
- Flask 应用骨架：app factory、配置管理、扩展初始化
- 9张数据库表：User, Student, PlatformAccount, Problem, Submission, Tag, AnalysisResult, AnalysisLog, Report
- 用户认证：注册、登录、退出（Flask-Login）
- 学生管理：添加、编辑、查看学生信息
- 平台账号管理：添加、删除、同步OJ平台账号
- 爬虫插件化架构：BaseScraper + 自动发现注册机制
- 洛谷爬虫：提交记录、题目信息、源代码获取
- BBC OJ爬虫：HOJ系统REST API对接
- 一本通OJ爬虫：PHP系统HTML/JS解析
- 数据同步服务：SyncService协调爬虫与数据库
- 统计分析引擎：基础统计、能力评分、标签评分
- AI分析引擎：单次提交分析、攻克过程分析
- 多模型LLM支持：Claude/OpenAI/智谱提供商
- AI题目分类器：自动识别题型和知识点
- 弱项识别引擎：基于阶段期望值的弱项检测
- 趋势分析：每周/每月趋势数据
- 练习推荐：基于弱项的智能推荐
- 报告生成器：周报/月报自动生成
- Dashboard总览页：统计卡片+雷达图+热力图+难度分布
- 知识点图谱页面：ECharts力导向图，6阶段分层展示
- 题目库浏览页：筛选、详情、代码查看
- 报告页面：列表、详情、生成
- 设置页面：平台账号管理、AI分析状态
- APScheduler定时任务：自动同步、AI分析、报告生成
- 6阶段知识点种子数据（80+知识点标签）

### 技术要点
- Flask app factory pattern
- SQLAlchemy + Alembic 数据库管理
- 爬虫自动发现机制（pkgutil + importlib）
- ECharts graph 力导向图实现知识点图谱
- Calendar heatmap 实现刷题日历
- 多模型LLM抽象层（插件化provider）
- 增量同步机制（sync_cursor）
- AI分析日志链（降低重复分析成本）
