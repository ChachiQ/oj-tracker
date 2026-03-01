# Changelog

## v1.0.0 (2026-03-02) -- 第一个正式版 🎉

> 从 v0.6.0 到 v1.0.0 共积累 40+ commits，涵盖新平台、新功能、大量修复和文档完善。

### 新增
- **代码部落 (Coderlands) 爬虫**：Cookie 认证、hash-based 增量同步、UUID 三级解析、DB 持久化（`33290d3`）
- **Cookie 更新 UI**：Cookie 认证平台账号支持在线更新 Cookie，含格式校验和引导提示（`94bf4be`, `3525b8c`, `7cbbbfd`）
- **题目分析页**：独立题目分析页面，支持 URL 直接访问（`eb5875c`）
- **KaTeX 数学渲染**：AI 分析面板中的数学公式自动渲染，复杂度值用 `$` 包裹（`becfcb5`, `2059628`）
- **未AC题目筛选**：题目列表新增"仅未AC"checkbox，筛选有提交但未通过的题目（`b9948db`）
- **爬虫 SOP + 设计文档**：新增 `DESIGN.md` 架构文档和 Phase 0 API 探测强制流程（`6c0dd7d`, `c0f6c49`）
- **Bootstrap Modal 替代原生对话框**：`ojConfirm` / `ojAlert` / `ojToast` 统一组件（`2bb893a`）

### 修复
- **Coderlands UUID 系列修复**：`getProbelmUuid` API 解析包装响应格式（`0a12245`）、课节遍历 fallback（`231a127`）、UUID 创建时持久化 + URL 直链（`047f7d5`）
- **时间戳 UTC 转换**：Coderlands 和 BBCOJ 提交时间从 UTC+8 转为 UTC 存储（`2f5b920`）、YBT 已有数据修复（`05ab36f`）
- **AI 分析韧性**：JSON 解析多层容错（`7da8953`, `aea7057`）、推理模型 token 耗尽降级重试（`aefb07d`, `14f8e35`）、代码审查错误缓存和崩溃处理（`c3a6c7c`, `f042224`）
- **Markdown/LaTeX 渲染**：数学分隔符保护，防止被 Markdown 处理破坏（`fa3cd2d`）
- **YBT 爬虫**：添加中文判题结果映射，修复 UNKNOWN 状态（`da85f42`, `189a088`）
- **UI 修复**：smarttime 负天数（`ac57483`）、综合分析双击重复确认（`74487a3`）、AI 解析显示空结果（`7da8953`）、题目难度被爬虫覆盖（`b6228c6`）
- **Modal 竞态条件**：单例 Modal Promise 封装在连续调用时事件监听器错位（`92ed399`）

### 优化
- **Dashboard 布局**：等高卡片、一致间距、雷达图过滤低阶标签、弱项告警位置调整（`95c91f9`, `9bb9587`）
- **推理模型降级**：token 耗尽时临时降低 max_tokens 重试，而非直接失败（`aefb07d`）
- **AI 回填精简**：跳过自动代码审查（Phase 2），降低 token 消耗（`de11f4a`）
- **同步任务超时**：卡死任务超时从 6h 降为 2h，前端增加轮询超时（`4bce0f2`）

### 文档
- 爬虫子系统设计文档 `app/scrapers/DESIGN.md`：架构概览、5 平台深度解析、已知陷阱、接入指南
- 爬虫开发 SOP：Phase 0 API 探测强制流程 + 检查清单
- 经验教训文档 `tasks/lessons.md`：Modal 竞态、爬虫陷阱、UUID 解析策略

## v0.6.0 (2026-02-22) -- CTOJ平台 + 一键综合分析 + 全局同步进度 + 图片多模态AI

### 新增
- CTOJ（酷思未来）爬虫：Hydro 系统 REST API 对接，密码登录（`498e4c4`）
- 一键综合分析：合并 3 次串行 LLM 调用为 1 次，支持并发 AI 回填（`bc20c72`）
- 题目详情页交互式 AI 分类 + 一键分析按钮（`d2d7d25`, `1de4cd9`, `8d68093`）
- Web 日志查看器：RotatingFileHandler + /logs 页面（`3b56997`）
- 全局同步进度条：顶部 banner 实时显示同步状态、日志详情展开、新提交检测（`e1b2aa5`）
- 图片渲染 + AI 多模态支持：题目图片正确显示，AI 可分析图片内容（`db64dce`）
- 手动取消卡死的同步任务 + 过期任务自动检测（`4f7abf9`）

### 修复
- YBT 提交 UNKNOWN 状态：添加中文判题结果映射（`7e045fa`）
- SyncJob 进程被杀后卡在 "running" 状态（`226369a`）
- AI 难度解析：智能回退 + 未评级题目保持可重试（`09c322b`）
- 3 个 AI 回填 bug：重复记录、数据丢失、脆弱 JSON 解析（`abb465c`）
- 智谱 GLM-5 分类失败：reasoning_content 回退 + 提高 max_tokens（`bdc0f8b`）
- AI 分析超时导致 "Failed to fetch"：前端增加 300s 超时控制（`025e27b`）
- CTOJ 爬虫因客户端用户过滤丢弃所有提交（`8768f7b`）
- AI 费用统计 review 计数膨胀：对齐回填服务过滤条件（`fe6d66b`）
- AI 分析失败后残留高难度值（`657307f`）
- CTOJ 重新同步因缺少登录失败 + 错误提示不友好（`0aa4de2`）
- 综合分析 JSON 解析失败：多层容错解析器（`c4389bc`）
- 智谱 GLM-5 综合分析返回散文而非 JSON（`c5e2e5c`）
- GLM-5 推理耗尽导致 JSON 解析失败（`bf515ff`）
- 同步日志详情展开总显示"加载失败"（`91cfabe`）
- 提交记录 AI 解析多个 UI 问题（空解析显示箭头、loading 重叠、renderReview 过严格、重新生成按钮不消失）（`69a05ad`）
- 题目详情页相对路径图片不显示（`b2ec492`）
- 题目重新同步 500 错误（`0b3826c`）

### 优化
- 题目详情页精简：合并分析面板、只保留综合分析按钮、代码高亮（`78ec10b`, `8d68093`）
- 设置页同步 UX：异步全量同步、进度遮罩、操作确认（`f2ade80`）
- 导航栏精简 + 同步日志快捷入口（`0b3826c`）
- 分类器跳过逻辑加固 + 回填错误阈值提高（`d84bf11`）
- 默认端口改为 8088，避免 macOS AirPlay 冲突（`67336a7`）

## v0.5.1 (2026-02-18) -- 报告系统重构 + 同步解耦 + UX 全面优化

### 新增
- AI 分析与同步解耦：新增 `SyncJob` 模型和 `AIBackfillService`，AI 分析改为独立后台任务执行，同步页新增任务日志
- 同步按钮改为下拉菜单（仅同步内容 / 同步+AI / AI 回填），增加全局互斥锁防止并发
- 平台账号暂停/恢复切换：允许手动暂停同步，无需删除账号
- 季度报告生成（90 天周期，13 周统计）
- 报告删除和重新生成功能（含所有权验证）
- 报告智能周期选择器：日期输入改为周期下拉菜单，按报告类型自动生成可选周期
- 报告重复检测：生成前检查同周期报告是否已存在，避免重复消耗 AI token
- 报告生成 Loading UX：AJAX 旋转器 + 计时器，列表弹窗和详情页均支持
- 报告列表新增类型筛选按钮（周/月/季），已生成周期在下拉中标注
- KaTeX 数学公式渲染：题目详情页支持 LaTeX 公式显示
- 题库筛选改进：难度多选 checkbox、平台/标签自动提交、"全部难度"清除选项
- 新增 `/api/problem/<id>/resync` API，支持单题内容重新抓取
- `backfill_tags.py` 新增 `--review` 完整 4 阶段回填模式（分类→思路→解题→审查）
- ProblemClassifier 新增预算检查和费用追踪，分类成本纳入统计体系
- Student 模型新增 `target_stage` 字段，学生表单页可选择目标阶段
- 提交热力图新增时间范围切换（1月/3月/6月/全年）
- 可配置显示时区（环境变量 `DISPLAY_TIMEZONE_OFFSET`，默认 UTC+8）
- AI 分析结果展示所用模型名称和分析时间戳

### 修复
- 移除同步时每题最多 3 条提交的限制，所有提交记录完整同步
- 报告详情页内容为空：`Report` 模型新增 `content`/`stats` 等计算属性
- 报告统计卡片 key 名称与 `stats_json` 实际字段对齐
- 报告生成器未从 UserSetting 读取 AI 提供者配置，改为优先用户设置回退环境变量
- 题目详情页 CSRF token 改为从 `<meta>` 标签读取，JS 块名修正为 `extra_scripts`
- AI 完整解题 `max_tokens` 从 4096 提升至 8192，避免输出截断
- AI 分析检测到空 JSON 或无效 JSON 结果时自动删除并重新分析
- 新增 `_clean_llm_json()` 辅助函数，自动剥离 LLM 返回的 Markdown 代码块包装
- Markdown 渲染增强：新增 `####` 标题、有序列表、`*` 无序列表解析，修复双重换行
- BBC OJ `map_difficulty` 修复：先检查文字标签再尝试整数转换，数值 clamp 至 0-7
- 应用启动时自动修正数据库中难度值 > 7 的脏数据
- AI 预算检查正确传入 `user_id`，实现按用户限额
- `difficulty=0` 的题目允许重新 AI 分类
- backfill 阶段 4 在 `problem_id_ref` 为 NULL 时不再崩溃
- 同步时 `_ensure_problem` 自动回填缺失的题目内容字段

### 优化
- 同步时跳过编译错误（CE）提交，减少无分析价值的数据
- 提交限制和 AI 审查上限改为按学生维度统计
- 能力雷达图按学生目标阶段过滤知识点，仅展示相关能力数据
- AI 报告 Prompt 强制要求输出 Markdown 格式，改进报告内容样式
- `problem_full_solution` prompt 新增长度约束，控制输出体量
- 题目详情页分析面板改为可折叠切换，重新分析前有确认弹窗
- 难度筛选新增"其他（未标记）"选项
- 平台列表从硬编码改为数据库动态读取

### 技术改进
- 新增 `SyncJob` 数据模型和 `PlatformAccount.last_submission_at` 字段（含迁移）
- 新增 `Student.target_stage` 字段（含迁移）
- `AIBackfillService` 统一 AI 分析 4 阶段流水线
- 新增 `sync` 蓝图（8 条路由）和同步日志页面

## v0.5.0 (2026-02-15) -- AI 题目分析 + 代码分析 + 知识评估增强

### 新增
- 题目思路分析：AI 分析解题思路、算法、复杂度、关键要点和常见错误（不含代码）
- AI 解题：AI 生成完整 C++ 解法，含代码、逐段解释、复杂度分析和替代方法
- 提交代码分析：AI 审查学生代码，评估代码质量、掌握程度，识别优缺点和改进建议
- 同步后自动分析：新同步的题目和提交自动触发 AI 分析（每次最多各 10 条，防 token 爆炸）
- 知识评估增强：报告 prompt 注入代码审查洞察，按标签聚合优缺点，提供更精准的掌握度评估
- 3 个新 API 端点：`POST /api/problem/<id>/solution`、`POST /api/problem/<id>/full-solution`、`POST /api/submission/<id>/review`
- 所有分析支持 `?force=1` 参数强制刷新（覆盖旧结果）
- 题目详情页新增思路分析、AI 解题两个 card，提交记录新增代码分析按钮
- 分析结果折叠显示，spinner 加载态，刷新按钮

### 技术改进
- `AnalysisResult` 模型新增 `problem_id_ref` FK，`submission_id` 改为 nullable
- `Problem` 模型新增 `analysis_results` relationship
- Alembic 迁移：`batch_alter_table` 兼容 SQLite
- 3 个新 Prompt 模板：`problem_solution`、`problem_full_solution`、`submission_review`
- `AIAnalyzer` 新增 `analyze_problem_solution()`、`analyze_problem_full_solution()`、`review_submission()` 方法
- `SyncService._analyze_new_content()` 同步后自动触发分析
- `KnowledgeAnalyzer._collect_submission_insights()` 收集代码审查洞察
- `knowledge_assessment` prompt 新增 `submission_insights` 参数和代码分析 section
- API 端点权限校验：problem 端点验证用户有该题提交，submission 端点验证所有权链

## v0.4.1 (2026-02-15) -- 知识图谱交互增强

### 新增
- 知识图谱全屏模式：ResizeObserver 自动适配容器尺寸，进出全屏自动居中
- 知识图谱旋转：±30° 旋转按钮，读取力导向布局坐标做矩阵旋转
- 标签重叠优化：ECharts 5 `labelLayout: { hideOverlap: true }` 自动隐藏重叠标签，缩放后自动显示
- AI 评估报告分页：每页 5 条，支持翻页导航
- 阶段进度详情：stages 新增 learning/weak 计数和 tags 详情列表

### 修复
- 全屏图谱消失：CSS 从 `flex:1 + height:auto` 改为 `calc(100vh - 70px)` 显式高度
- 标题下划线被 canvas 遮挡：标题行添加 `position: relative; z-index: 1`
- 评估报告删除后分页状态同步：从缓存列表移除并自动修正页码

### 优化
- 技能树图例改为三行垂直布局，移至阶段图例下方
- 全屏切换去除 setTimeout hack，改用 ResizeObserver
- 依赖链高亮/恢复保留旋转后的节点坐标

## v0.4.0 (2026-02-15) -- 分析与可视化增强

### 修复
- Dashboard 空数据崩溃：无平台账号时 `get_dashboard_data()` 返回完整空字典而非列表，防止前端 undefined 错误
- 统计卡片语义错误：「总提交题数」改用 `unique_attempted`（尝试过的不同题目数），不再与 AC 数重复

### 新增
- Dashboard 首次AC率卡片：第 5 个统计卡片，展示一次通过率
- Dashboard 提交状态分布图：ECharts 环形饼图，按状态着色（AC/WA/TLE/MLE/RE/CE），中心显示总提交数
- Dashboard 周趋势图：双轴折线图，左轴提交量+AC量（柱状），右轴通过率（折线），最近 12 周
- Dashboard 平台分布统计：按平台分组显示提交数、AC 数、通过率
- 知识图谱前置依赖高亮：点击节点递归高亮所有前置依赖链和后续依赖链，其余节点淡化；再次点击或点击空白恢复
- 知识图谱效率指标：节点详情面板新增首次AC率（带进度条）和平均尝试次数
- 知识图谱跳转题库：节点详情面板新增「查看所有相关题目」按钮，跳转题目列表页按标签筛选

### 优化
- 能力评分时间衰减：90 天内提交权重 1.0→0.5 线性衰减，90 天以前固定 0.5
- 能力评分阶段自适应权重：基础阶段侧重刷题量和通过率，高级阶段侧重难度和效率
- 标签评分新增 `recent_activity` 字段（近 30 天是否活跃）
- 统计卡片列布局适配 5 卡排列

## v0.3.1 (2026-02-15) -- 题库 UX 优化

### 新增
- 提交时间智能展示：Jinja2 `smarttime` 过滤器，微信风格相对时间（今天/昨天/前天/X天前/MM-DD/YYYY-MM-DD）
- 提交时间悬停 tooltip：Bootstrap Tooltip 替代原生 title，200ms 快速弹出完整时间
- 题库分页跳转：输入页码直接跳转，保留筛选参数

### 优化
- 题目列表排序改进：有提交记录的题目优先显示，按最近提交时间倒序

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
