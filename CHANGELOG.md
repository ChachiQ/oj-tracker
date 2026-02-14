# Changelog

## v0.2.0 (2026-02-14) -- 设置页面完善

### 新增
- BBC OJ / 一本通OJ 平台绑定支持（密码登录 + 会话冲突提示）
- REQUIRES_LOGIN 爬虫标记：区分需登录与公开 API 平台
- 同步错误追踪：last_sync_error 字段 + 状态 badge
- 定时同步自动跳过需登录平台，避免踢掉用户活跃会话
- AI 提供者可配置：支持 Claude/OpenAI/智谱 三家切换
- 用户级 API KEY 管理：UI 配置，优先于环境变量
- 月度预算设置和 API 用量统计（按模型分组）
- UserSetting 模型：用户配置 key-value 存储
- 34 新增测试用例（AI 测试全部 mock，零 token 消耗）

### 修复
- 设置页面 accounts 变量未传到模板
- 设置页面 analyzed_count 变量未传到模板
- 平台下拉列表从硬编码改为动态渲染

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
