# OJ Tracker - Online Judge Progress Tracking & Analysis

English | [中文](README.md)

A web application that helps parents track their children's competitive programming progress across multiple Online Judge (OJ) platforms, automatically analyze weaknesses, and provide targeted practice recommendations and skill reports.

## Features

- **Multi-Platform Sync** - Supports Luogu, BBC OJ (HOJ system), and Ybt OJ, with a plugin-based scraper architecture for easy extension
- **Dashboard** - Stats cards, radar chart, heatmap, difficulty distribution, and submission calendar
- **Knowledge Graph** - ECharts force-directed graph with 6-stage layered display (Syntax Basics to NOI), tri-color node status
- **Weakness Detection** - Age/grade-aware comparison against stage expectations, automatic identification of weak topics
- **AI Analysis** - Multi-model support (Claude/OpenAI/Zhipu), 4-level analysis chain: problem classification -> single submission -> solution process -> comprehensive report
- **Weekly/Monthly Reports** - Auto-generated learning reports with chained AI analysis logs to reduce redundant token usage
- **Practice Recommendations** - Intelligent problem suggestions based on detected weaknesses

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.1 + SQLAlchemy 2.0 + SQLite |
| Frontend | Jinja2 + Bootstrap 5 + ECharts |
| Scrapers | requests + BeautifulSoup4 (plugin architecture) |
| Scheduler | APScheduler |
| AI Analysis | Claude / OpenAI / Zhipu (configurable multi-model) |
| Data Analysis | pandas + numpy |
| Testing | pytest (120 test cases) |

## Project Structure

```
oj-tracker/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # Config classes (Dev/Prod/Testing)
│   ├── extensions.py        # db, login_manager, migrate, csrf
│   ├── models/              # 9 database tables
│   ├── scrapers/            # OJ scraper plugins (auto-discovery + registration)
│   ├── analysis/            # Analysis engine + AI analysis + LLM abstraction
│   │   ├── engine.py        # AnalysisEngine - statistics
│   │   ├── weakness.py      # WeaknessDetector - weakness identification
│   │   ├── trend.py         # TrendAnalyzer - trend analysis
│   │   ├── recommender.py   # ProblemRecommender - recommendations
│   │   ├── llm/             # Multi-model LLM abstraction layer
│   │   └── prompts/         # AI prompt templates
│   ├── services/            # SyncService, StatsService
│   ├── views/               # Flask blueprint routes
│   ├── templates/           # Jinja2 templates
│   ├── static/              # CSS/JS
│   └── tasks/               # APScheduler scheduled tasks
├── migrations/              # Alembic database migrations
├── tests/                   # pytest test suite
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
          Student 1──N AnalysisLog
          Student 1──N Report
```

| Model | Description |
|-------|-------------|
| User | Parent user account with hashed passwords |
| Student | Child profile with grade/birthday for age-aware analysis |
| PlatformAccount | OJ platform credentials and sync state |
| Problem | Problem metadata with many-to-many Tag association |
| Submission | Submission records linked to Problem and PlatformAccount |
| Tag | Knowledge point tags with stage level and prerequisites |
| AnalysisResult | AI analysis results per submission |
| AnalysisLog | Chained AI analysis logs to reduce redundant analysis |
| Report | Weekly/monthly generated reports |

## Supported OJ Platforms

| Platform | Identifier | Integration Method |
|----------|-----------|-------------------|
| Luogu | `luogu` | JSON API (x-lentille-request header) |
| BBC OJ | `bbcoj` | HOJ system REST API |
| Ybt (Yi Ben Tong) | `ybt` | PHP system HTML/JS parsing |

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
| `/api/problems` | GET | Problem list (paginated, filterable) |

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
| `/problem/` | Problem library |
| `/problem/<id>` | Problem detail |
| `/settings/` | Settings (platform account management) |

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
- 4-level analysis chain: problem classification -> single submission -> solution process -> comprehensive report
- `AI_MONTHLY_BUDGET` for cost control

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

### v0.3.0 -- Scraper Refinement & Stability

Planned:
- Luogu scraper optimization: session management, incremental sync tuning
- Scraper error retry mechanism and alerts
- Knowledge point seed data refinement

### v0.4.0 -- Analysis & Visualization Enhancement

Planned:
- Enhanced dashboard with richer statistical dimensions
- Knowledge graph interaction: click nodes to view related problems
- Weakness detection algorithm upgrade: add first-AC rate and average attempts
- Skill scoring formula optimization

### v0.5.0 -- AI Analysis Deep Integration & Recommendations

Planned:
- Deep AI code analysis integration
- Analysis log chain optimization
- Intelligent recommendation algorithm upgrade (ProblemRecommender)

### v0.6.0 -- Deployment & Extensions

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
| Phase 4 - AI Analysis & Recommendations | AI code analysis, analysis log chain, ProblemRecommender, scheduled tasks | ✅ |
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

The test suite includes 120 test cases covering:
- Models: CRUD, relationships, and constraints for all 9 models
- Auth: registration, login, logout, access control
- Views: GET/POST responses for all routes
- API: JSON endpoint responses and permissions
- Scrapers: registry, dataclasses, enums
- Analysis: statistics, weakness detection, trends
- Services: sync service, stats service

## License

[GPL-3.0](LICENSE)
