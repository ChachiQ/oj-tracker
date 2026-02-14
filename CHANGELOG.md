# Changelog

## v0.3.0 (2026-02-14) -- Dashboard & 知识图谱完善 + 爬虫稳定性

### 新增
- 同步 AJAX 化：设置页同步操作改为 AJAX 请求，添加全屏 overlay + spinner 进度展示
- Dashboard 近期提交：`get_dashboard_data()` 新增 `stats`/`recent_submissions`/`weaknesses` 字段
- 知识图谱推荐练习：每个知识点节点附带最多5道推荐练习题
- 连续失败追踪：`PlatformAccount` 新增 `consecutive_sync_failures` 字段，>=10 次自动停用
- 平台级共享限流：`get_platform_limiter()` 注册表，同平台多账号共享限流器
- 洛谷 429 限流处理：遇到 HTTP 429 自动等待 30 秒后重试
- 洛谷 Content-Type 校验：非 JSON 响应提前中断，防止解析垃圾数据
- 洛谷 MAX_PAGES 安全限制：最多抓取 100 页，防止无限循环
- 8 个新知识点标签：位运算、哈希表、滑动窗口、双端队列、LIS、折半搜索、2-SAT、斜率优化DP
- 所有知识点标签添加中文描述字段
- `seed_tags()` 改为 upsert 模式，可重复运行不会产生重复数据

### 修复
- Dashboard 数据结构：前端 `updateStatCards()` 期望的 `data.stats` 字段现在正确返回
- Dashboard 提交列表回退请求：`data.submissions` → `data.items`（匹配 API 实际返回）
- 知识图谱阶段进度条：`data.stage_stats` → `data.stages`（匹配后端实际返回字段名）
- `sync_cursor` 修复：同步后存储最新 record_id 而非时间戳，增量同步真正生效
- `union_find` 阶段修正：从 stage 4 → stage 3（并查集属于 CSP-J 级别）
- YBT 登录验证加固：替换乐观 fallback 为 member.php 页面验证

### 技术改进
- 设置页同步/删除按钮在同步期间禁用，防止误操作
- 设置页状态列显示连续失败次数和自动停用提示
- Alembic 迁移：`consecutive_sync_failures` 列

## v0.2.1 (2026-02-14) -- YBT 爬虫修复 & 题目详情优化

### 修复
- YBT 爬虫编码：GBK → UTF-8（页面实际为 UTF-8 + BOM，之前解码导致标题乱码）
- YBT 题目内容解析：重写 `_extract_section()`，匹配实际 `pshow("content")` 单参数格式（旧正则 `pshow('name','content')` 完全不匹配）
- YBT 样例提取：从 `<pre>` 标签提取输入/输出样例（样例区域不使用 pshow）
- YBT 图片抓取：新增 `_fix_image_urls()`，将 `pic/1365.gif` 等相对路径转为绝对 URL
- 题目详情模板字段映射：`platform_pid` → `problem_id`、`source_url` → `url`、`input_format` → `input_desc`、`output_format` → `output_desc`、`sub.code` → `sub.source_code`、`sub.student` → `sub.platform_account.student`、`ai_type` → `ai_problem_type`
- 提交记录排序改为按时间倒序（最新在前）

### 优化
- 题目列表/详情页：移除题号列，平台 badge 内嵌外链图标，点击直接跳转 OJ 原题
- 平台 badge 悬停变色效果，提升可点击感知
- 全站 footer 显示版本号（`__version__` + context_processor）

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
