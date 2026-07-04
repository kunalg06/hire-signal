# Folder Structure

Annotated directory tree for hire-signal.

```
coding_platforms/
│
├── run.py                      # Entry point — python run.py starts the Flask dev server
├── requirements.txt             # Python dependencies
├── CLAUDE.md                    # Dev guide for Claude Code sessions (architecture, constraints, debugging)
├── AGENT.md                     # Living session-continuity file — sprint state, deferred issues
├── README.md                    # Project overview and quick start
├── QUICKSTART.md                 # Step-by-step first-run guide
├── DOCKER_QUICK_START.md         # Fast Docker setup path
├── DOCKER_SETUP.md               # Full Docker setup + troubleshooting
├── conftest.py                   # Root pytest conftest — puts project root on sys.path
│
├── app/                          # Flask application package
│   ├── __init__.py                # create_app(config_name) — app factory, blueprint registration
│   ├── config.py                  # Config / DevelopmentConfig / TestingConfig / ProductionConfig
│   ├── models/
│   │   ├── __init__.py
│   │   └── database.py             # Database class — sqlite3 connections, init_db() schema + migrations
│   ├── routes/                     # One Flask blueprint per concern
│   │   ├── __init__.py
│   │   ├── assignments.py           # /api/assignments
│   │   ├── links.py                 # /api/generate-link/<id>
│   │   ├── challenges.py            # /api/generate-challenge, /api/challenges/*
│   │   ├── submissions.py           # /api/submit-with-files, /api/submission/*, flag/override
│   │   ├── student.py               # /student/<link_id>, /student/preview/<challenge_id>
│   │   ├── analytics.py             # /api/analytics/overrides
│   │   └── management.py            # /api/system/* — status, health, container admin
│   ├── services/                   # Business logic, no Flask imports
│   │   ├── __init__.py
│   │   ├── database_service.py      # All SQL — raw sqlite3, no ORM
│   │   ├── evaluation_service.py    # 8-dimension scoring, hire thresholds, challenge generation
│   │   ├── llm_service.py           # Gemini wrapper — the only LLM call surface in the codebase
│   │   ├── docker_service.py        # Container lifecycle via subprocess `docker` CLI
│   │   ├── management_service.py    # System status / container admin helpers
│   │   └── session_log_service.py   # Parses Gemini CLI session logs
│   ├── utils/
│   │   ├── __init__.py
│   │   └── helpers.py               # IDGenerator, ValidationHelper, RateLimiter, DateTimeHelper
│   └── templates/                   # Currently empty — the real frontend lives at the repo-root templates/
│
├── templates/
│   └── frontend.html              # The entire employer dashboard — single-file HTML/CSS/vanilla JS
│
├── tests/                          # pytest suite — 64 tests, 5 files, no LLM key or Docker daemon required
│   ├── test_score_8_dimensions.py           # 8-dim scoring unit tests (LLM mocked)
│   ├── test_extract_container_files.py       # Workspace-snapshot unit tests (Docker mocked)
│   ├── test_hire_recommendation_thresholds.py # Threshold-boundary precision tests
│   ├── test_candidates_endpoint.py            # Integration test — real Flask client + isolated SQLite
│   └── test_generate_challenge_endpoint.py    # Integration test — challenge generation + persistence
│
├── docker/                         # Container build/orchestration definitions
│   ├── Dockerfile.codeserver        # Candidate container image — code-server + Gemini CLI
│   ├── Dockerfile.backend           # Flask backend image (used only by docker-compose.yml, legacy/optional)
│   ├── Dockerfile                   # Alternate/earlier code-server image variant
│   ├── docker-compose.yml           # Legacy multi-service orchestration (Postgres/Redis included but
│   │                                 # unused by the current codebase — the live app runs `python run.py`
│   │                                 # directly and manages containers via docker_service.py's subprocess
│   │                                 # calls, not docker-compose)
│   └── start-services.py
│
├── scripts/
│   └── seed_challenges.py          # Seeds 10 curated challenges across the type/skill-area matrix
│
├── tools/
│   └── client.py                   # Small Python client for exercising the API programmatically
│
├── docs/                           # Reference documentation (this folder)
│   ├── ARCHITECTURE.md              # System diagram + the 4 core request/response flows
│   ├── API_REFERENCE.md             # Full endpoint reference with request/response examples
│   ├── PROJECT_REQUIREMENTS.md      # Product requirements, scoring rubric, scope boundaries
│   ├── FOLDER_STRUCTURE.md          # This file
│   └── problem_statements.txt       # Raw source material used when seeding challenges
│
├── data/                           # SQLite database files (gitignored — data/*.db, never committed)
│   └── assignments.db               # The live dev database
│
└── _bmad-output/                   # BMad Method planning + implementation artifacts
    ├── planning-artifacts/
    │   └── epics-and-stories.md     # Full epic/story backlog spec
    └── implementation-artifacts/
        ├── sprint-status.yaml       # Per-story status tracking (all epics currently `done`)
        ├── deferred-work.md         # Every known-but-unfixed issue, with file/line references
        └── <epic>-<story>-<slug>.md # One file per implemented story — full context + review history
```

## Notes on structure

- **No `main.py`.** The old FastAPI-based single-file design was fully replaced by the Flask `app/` package — if you see a reference to `main.py` anywhere, it's stale documentation, not current code.
- **Two `templates/` directories exist** (`app/templates/` and root `templates/`). Only the root one is used — `app/templates/` is empty and appears to be dead weight from an earlier refactor.
- **`docker/docker-compose.yml` is not the primary dev path.** It references Postgres/Redis services that nothing in the current codebase reads or writes to. The actual dev workflow is `python run.py` plus Docker containers spun up ad hoc by `docker_service.py`.
- **Route files construct their `db_service` at import time**, not per-request — this is a real trap for anyone writing new tests or scripts against these routes. See `CLAUDE.md`'s "Critical Trap" section before writing anything that touches a route's database access.
