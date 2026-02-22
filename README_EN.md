# OJ Tracker - Online Judge Progress Tracking & Analysis

English | [中文](README.md)

A web application that helps parents track their children's competitive programming progress across multiple Online Judge (OJ) platforms, automatically analyze weaknesses, and provide targeted practice recommendations and skill reports.

## Features

- **Multi-Platform Sync** - Supports Luogu, BBC OJ (HOJ system), Ybt OJ, and CTOJ (Cool Think OJ), with a plugin-based scraper architecture for easy extension
- **Sync/AI Decoupling** - Content sync and AI analysis run independently, SyncJob task tracking, pause/resume support
- **Dashboard** - Stats cards, radar chart, heatmap (selectable time range), difficulty distribution, and submission calendar
- **Knowledge Graph** - ECharts force-directed graph with 6-stage layered display (Syntax Basics to NOI), tri-color node status
- **Weakness Detection** - Age/grade-aware comparison against stage expectations, automatic identification of weak topics
- **AI Analysis** - Multi-model support (Claude/OpenAI/Zhipu), 4-stage pipeline: problem classification -> submission review -> knowledge assessment -> comprehensive report
- **Weekly/Monthly/Quarterly Reports** - Auto-generated learning reports with chained AI analysis logs to reduce redundant token usage
- **KaTeX Math Rendering** - Automatic rendering of math formulas in problem descriptions and AI analysis results
- **Practice Recommendations** - Intelligent problem suggestions based on detected weaknesses
- **Configurable Timezone** - DISPLAY_TIMEZONE_OFFSET for global timezone offset setting

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.1 + SQLAlchemy 2.0 + SQLite |
| Frontend | Jinja2 + Bootstrap 5 + ECharts |
| Scrapers | requests + BeautifulSoup4 (plugin architecture) |
| Scheduler | APScheduler |
| AI Analysis | Claude / OpenAI / Zhipu (configurable multi-model) |
| Data Analysis | pandas + numpy |
| Testing | pytest (292 test cases) |

## Project Structure

```
oj-tracker/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # Config classes (Dev/Prod/Testing)
│   ├── extensions.py        # db, login_manager, migrate, csrf
│   ├── models/              # 11 database tables + 1 association table
│   ├── scrapers/            # OJ scraper plugins (auto-discovery + registration)
│   ├── analysis/            # Analysis engine + AI analysis + LLM abstraction
│   │   ├── engine.py        # AnalysisEngine - statistics
│   │   ├── weakness.py      # WeaknessDetector - weakness identification
│   │   ├── trend.py         # TrendAnalyzer - trend analysis
│   │   ├── recommender.py   # ProblemRecommender - recommendations
│   │   ├── ai_analyzer.py   # AIAnalyzer - submission review
│   │   ├── problem_classifier.py  # ProblemClassifier - problem classification
│   │   ├── knowledge_analyzer.py  # KnowledgeAnalyzer - knowledge assessment
│   │   ├── report_generator.py    # ReportGenerator - report generation
│   │   ├── llm/             # Multi-model LLM abstraction layer
│   │   └── prompts/         # AI prompt templates
│   ├── services/            # SyncService, StatsService, AIBackfillService, TagMapper
│   ├── views/               # Flask blueprint routes (9 blueprints)
│   ├── templates/           # Jinja2 templates
│   ├── static/              # CSS/JS
│   └── tasks/               # APScheduler scheduled tasks
├── migrations/              # Alembic database migrations
├── tests/                   # pytest test suite (292 cases)
├── backfill_tags.py         # Tag backfill script
├── seed_data.py             # Knowledge point seed data (80+ tags)
├── run.py                   # Entry point
└── requirements.txt
```

## Getting Started

### Prerequisites

- Python 3.9+
- pip

### Installation

```bash
git clone https://github.com/<your-username>/oj-tracker.git
cd oj-tracker
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Create a `.env` file (optional, overrides defaults):

```bash
# Flask
SECRET_KEY=your-secret-key
FLASK_ENV=development

# AI config (configure at least one)
AI_PROVIDER=zhipu          # zhipu / claude / openai
ZHIPU_API_KEY=your-key
ANTHROPIC_API_KEY=your-key
OPENAI_API_KEY=your-key

# AI budget control
AI_MONTHLY_BUDGET=5.0

# Scraper rate limit (seconds between requests)
SCRAPER_RATE_LIMIT=0.5

# Scheduled tasks
SCHEDULER_ENABLED=false

# Display timezone offset (default UTC+8)
DISPLAY_TIMEZONE_OFFSET=8
```

Environment-specific config files `.env.development` and `.env.production` are also supported.

### Initialize Database

```bash
# Create database tables
flask db upgrade

# Import knowledge point seed data (80+ tags, 6-stage system)
python seed_data.py
```

### Run

```bash
python run.py
# Visit http://localhost:5000
```

Production:

```bash
FLASK_ENV=production gunicorn run:app -b 0.0.0.0:5000
```

### Run Tests

```bash
pytest tests/ -v
```

## Database Models

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

| Model | Description |
|-------|-------------|
| User | Parent user account with hashed passwords |
| Student | Child profile with grade/birthday/target stage for age-aware analysis |
| PlatformAccount | OJ platform credentials and sync state |
| Problem | Problem metadata with many-to-many Tag association |
| Submission | Submission records linked to Problem and PlatformAccount |
| Tag | Knowledge point tags with stage level and prerequisites |
| AnalysisResult | AI analysis results, linkable to Submission or Problem |
| AnalysisLog | Chained AI analysis logs to reduce redundant analysis |
| Report | Weekly/monthly/quarterly generated reports |
| UserSetting | Per-user configuration key-value store |
| SyncJob | Sync/AI backfill job execution history and progress |

## Supported OJ Platforms

| Platform | Identifier | Integration Method |
|----------|-----------|-------------------|
| Luogu | `luogu` | JSON API (x-lentille-request header) |
| BBC OJ | `bbcoj` | HOJ system REST API |
| Ybt (Yi Ben Tong) | `ybt` | PHP system HTML/JS parsing |
| CTOJ (Cool Think OJ) | `ctoj` | Hydro system REST API |

### Adding a New Platform

The scraper uses a plugin architecture - just add a single file to support a new OJ:

```python
# app/scrapers/new_oj.py
from app.scrapers.base import BaseScraper
from app.scrapers.common import register_scraper

@register_scraper('new_oj', 'New Platform Name')
class NewOJScraper(BaseScraper):
    PLATFORM = 'new_oj'
    BASE_URL = 'https://new-oj.com'

    def fetch_submissions(self, uid, cursor=None):
        ...
    def fetch_problem(self, problem_id):
        ...
```

Place the file in `app/scrapers/` and it will be auto-discovered and registered - no changes to core code required.

## 6-Stage Knowledge Point System

| Stage | Name | Example Topics |
|-------|------|---------------|
| 1 | Syntax Basics | Variables, loops, arrays, strings, functions |
| 2 | Basic Algorithms | Sorting, binary search, simulation, intro greedy, intro BFS/DFS |
| 3 | CSP-J (Junior) | Recursion & divide-and-conquer, intro DP, graph basics, STL containers |
| 4 | CSP-S (Senior) | Segment tree, heavy-light decomposition, network flow, DP optimization |
| 5 | Provincial Selection | Suffix array, centroid decomposition, virtual tree, polynomials |
| 6 | NOI | FFT/NTT, persistent data structures, game theory |

Grade-to-stage mapping: Grade 3-4 -> Stages 1-2, Grade 5-6 -> Stages 1-3, Grade 7-8 -> Stages 1-4, Grade 9-10 -> Stages 1-5, Grade 11-12 -> Stages 1-6.

## Environments

| Environment | Purpose | Database | Scheduler |
|-------------|---------|----------|-----------|
| development | Local development | `instance/dev.db` | Disabled |
| production | Production server | `instance/prod.db` | Enabled |
| testing | Automated tests | In-memory SQLite | Disabled |

Switch via `FLASK_ENV` environment variable or `create_app(config_name)`.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard/<student_id>` | GET | Dashboard statistics |
| `/api/knowledge/<student_id>` | GET | Knowledge graph data |
| `/api/weakness/<student_id>` | GET | Weakness analysis data |
| `/api/trend/<student_id>` | GET | Trend analysis data |
| `/api/submissions/<student_id>` | GET | Submissions (paginated, filterable) |
| `/api/knowledge/<student_id>/analyze` | POST | Knowledge AI assessment (SSE streaming) |
| `/api/knowledge/<student_id>/assessment` | GET | Get knowledge assessment results |
| `/api/knowledge/<student_id>/assessment/<log_id>` | DELETE | Delete knowledge assessment |
| `/api/problems` | GET | Problem list (paginated, filterable) |
| `/api/problem/<problem_id>/solution` | POST | AI-generated problem analysis |
| `/api/problem/<problem_id>/full-solution` | POST | AI-generated full solution |
| `/api/problem/<problem_id>/resync` | POST | Re-sync problem information |
| `/api/submission/<submission_id>/review` | POST | AI review of submission code |
| `/api/problem/<problem_id>/classify` | POST | AI problem classification |
| `/api/problem/<problem_id>/comprehensive` | POST | One-click comprehensive analysis |

All API endpoints require authentication and only allow access to the current user's children's data.

## Page Routes

| Route | Description |
|-------|-------------|
| `/auth/register` | User registration |
| `/auth/login` | Login |
| `/auth/logout` | Logout |
| `/dashboard/` | Dashboard overview |
| `/student/` | Student management |
| `/student/add` | Add student |
| `/student/<id>/edit` | Edit student |
| `/knowledge/` | Knowledge graph |
| `/report/` | Report list |
| `/report/<id>` | Report detail |
| `/report/generate` | Generate report |
| `/report/<id>/delete` | Delete report |
| `/report/<id>/regenerate` | Regenerate report |
| `/sync/log` | Sync log |
| `/problem/` | Problem library |
| `/problem/<id>` | Problem detail |
| `/settings/` | Settings (platform account management) |
| `/logs/` | Web log viewer |

## Architecture Highlights

### Plugin-Based Scrapers
- `BaseScraper` abstract base class defines the contract
- `@register_scraper` decorator for automatic registration
- `pkgutil` + `importlib` for auto-discovery
- `ScrapedSubmission`/`ScrapedProblem` unified intermediate data format
- Incremental sync via `sync_cursor`

### Multi-Model AI Analysis
- `BaseLLMProvider` abstract base class
- Supports Claude/OpenAI/Zhipu, switchable via configuration
- Prompt templates decoupled from model providers
- 4-stage pipeline: problem classification (ProblemClassifier) -> submission review (AIAnalyzer) -> knowledge assessment (KnowledgeAnalyzer) -> comprehensive report (ReportGenerator)
- `AI_MONTHLY_BUDGET` for cost control, per-user AI configuration

### Sync/AI Decoupling
- Content sync (SyncService) and AI analysis (AIBackfillService) fully decoupled
- SyncJob model tracks job execution history with progress polling
- AI backfill runs as independent background task, non-blocking to sync flow
- TagMapper service: OJ native tags -> knowledge point system mapping

### Report System
- Supports weekly, monthly, and quarterly report periods
- ReportGenerator builds reports from AnalysisLog chain
- Reports support generate, delete, and regenerate operations
- KaTeX rendering for math formulas

### Analysis Log Chain
- `AnalysisLog` table serves as AI memory
- Weekly -> monthly reports chain context forward
- Avoids redundant analysis, reducing token consumption

### Age-Aware Analysis
- Student model includes birthday and grade
- Weakness detection filters out age-inappropriate topics
- AI analysis prompts inject age context

## Roadmap

### v0.1.0 (2026-02-13) -- Project Initialization ✅

All foundational features complete:
- Flask app skeleton, 9 database tables, user authentication
- 3 OJ scrapers (Luogu / BBC OJ / Ybt)
- Statistical analysis engine, weakness detection, trend analysis
- AI analysis engine (multi-model LLM support)
- Dashboard, knowledge graph, reports, and all pages
- APScheduler scheduled tasks
- 120 automated test cases

### v0.2.0 (2026-02-14) -- Settings Page Enhancements ✅

- BBC OJ / Ybt OJ platform binding (password login + session conflict warnings)
- REQUIRES_LOGIN scraper attribute: distinguish login-required vs public API platforms
- Sync error tracking (last_sync_error) + scheduler auto-skips login-required platforms
- Configurable AI provider: switch between Claude/OpenAI/Zhipu
- Per-user API KEY management + monthly budget + usage statistics
- UserSetting model: user config key-value store
- 211 automated test cases

### v0.3.0 / v0.3.1 (2026-02-14 ~ 2026-02-15) -- Scraper Stability & Problem List UX ✅

- Scraper stability: consecutive failure tracking, platform-level shared rate limiting, Luogu 429 retry, MAX_PAGES safety limit
- Dashboard/knowledge graph improvements: recent submissions, recommended exercises, field fixes
- Sync AJAX + full-screen spinner progress display
- Problem list UX: smart time display, fast tooltip, page jump
- 8 new knowledge point tags + Chinese descriptions + upsert seed

### v0.4.0 / v0.4.1 (2026-02-15) -- Analysis & Visualization Enhancement ✅

- Dashboard enhancements: first-AC rate card, submission status distribution, weekly trend chart, platform distribution stats
- Knowledge graph interaction: prerequisite chain highlighting, efficiency metrics, problem library jump, fullscreen mode, rotation, overlap optimization
- Skill scoring optimization: time decay, stage-adaptive weighting
- AI assessment report pagination, stage progress details

### v0.5.0 (2026-02-15) -- AI Problem Analysis + Code Analysis + Knowledge Assessment Enhancement ✅

- AI problem solution analysis and full solution generation
- Submission code AI review (quality assessment, strengths/weaknesses, improvement suggestions)
- Auto-trigger AI analysis after sync
- Knowledge assessment injected with code review insights
- `AnalysisResult` supports linking to Problem (`problem_id_ref`)

### v0.5.1 (2026-02-18) -- Report System Refactor + Sync Decoupling + Comprehensive UX Optimization ✅

- Sync/AI decoupling: SyncJob model, AIBackfillService as independent background task
- Quarterly reports, report delete/regenerate, smart period selector, duplicate detection
- KaTeX math formula rendering
- Heatmap time range switching, configurable display timezone
- Platform account pause/resume, problem list filter improvements
- 285 automated test cases

### v0.6.0 (2026-02-22) -- CTOJ Platform + One-Click Comprehensive Analysis + Global Sync Progress + Image Multimodal AI ✅

- CTOJ (Cool Think OJ) scraper: Hydro system REST API integration
- One-click comprehensive analysis: merge 3 serial LLM calls into 1, concurrent AI backfill
- Web log viewer (/logs page) + global sync progress bar
- Image rendering + AI multimodal support
- Numerous AI analysis stability fixes (GLM-5 compatibility, JSON fault tolerance, timeout control)
- 292 automated test cases

### v0.7.0 -- Deployment & Extensions

Planned:
- Cloud deployment (Gunicorn + Nginx)
- School/institution OJ adapters
- PDF report export

## Implementation Phases

| Phase | Content | Status |
|-------|---------|--------|
| Phase 1 - Core Skeleton | Flask app factory, database models, auth, base layout | ✅ |
| Phase 2 - Scraper System | BaseScraper, 3 scrapers, SyncService, account management, seed data | ✅ |
| Phase 3 - Analysis & Visualization | AnalysisEngine, Dashboard, WeaknessDetector, TrendAnalyzer, knowledge graph | ✅ |
| Phase 4 - AI Analysis & Recommendations | AI 4-stage pipeline, sync/AI decoupling, AIBackfillService, SyncJob, 292 tests | ✅ |
| Phase 5 - Deployment & Extensions | Cloud deployment, school OJ adapters, PDF export | Planned |

## Development Guide

### Conventions
- Python code follows PEP 8
- Model relationships use `back_populates` (not `backref`)
- View functions require `@login_required`
- All forms require CSRF protection
- Logging via the `logging` module
- Configuration managed through environment variables

### Running Tests

```bash
source venv/bin/activate
pytest tests/ -v --tb=short
```

The test suite includes 292 test cases covering:
- Models: CRUD, relationships, and constraints for all 11 models
- Auth: registration, login, logout, access control
- Views: GET/POST responses for all routes
- API: JSON endpoint responses and permissions
- Scrapers: registry, dataclasses, enums
- Analysis: statistics, weakness detection, trends, AI analysis
- Services: sync service, stats service, AI backfill service
- Tag mapping: TagMapper tests

## License

[GPL-3.0](LICENSE)
