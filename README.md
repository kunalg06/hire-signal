# hire-signal

> AI-powered hire-readiness evaluation platform — assess candidates on real-world AI-assisted coding competency, not just algorithmic recall.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Flask](https://img.shields.io/badge/flask-3.0-green.svg)
![Status](https://img.shields.io/badge/status-all%20epics%20complete-brightgreen.svg)
![Tests](https://img.shields.io/badge/tests-64%20passing-brightgreen.svg)
![AI Beta](https://img.shields.io/badge/AI%20scoring-experimental-orange.svg)

---

## What is hire-signal?

Coding interviews have changed. Candidates now use AI tools on the job — and the best ones know *how* to collaborate with AI effectively, not just write code from scratch. hire-signal evaluates that skill.

Employers post a challenge. Candidates solve it in an isolated browser-based VS Code environment with Claude Code CLI access. The platform records every Claude interaction, extracts the final workspace, and evaluates the candidate across **8 AI-collaboration dimensions** — producing a structured hire recommendation.

> **AI Beta Notice:** Scores are experimental signals. Human judgment holds final authority. Always review before making hiring decisions.

---

## How It Works

```
Employer creates challenge
        ↓
Generates unique link per candidate
        ↓
Candidate codes in isolated Docker container
(browser VS Code + Claude Code CLI access)
        ↓
On submit: full workspace snapshot extracted
        ↓
8-dimension evaluation via Claude
        ↓
Hire recommendation: strong_hire / hire / select / pass
        ↓
Employer compares candidates side-by-side, flags/overrides as needed
```

---

## 8-Dimension Scoring Framework

| # | Dimension | Weight | What It Measures |
|---|-----------|--------|-----------------|
| PD | Problem Decomposition | 15% | Did the candidate break the problem into logical sub-problems before diving in? |
| FP | First-Principles Thinking | 15% | Did they reason from fundamentals vs. copy-paste AI output blindly? |
| CP | Creative Problem Solving | 10% | Novel approaches, non-obvious solutions |
| IQ | Iteration Quality | 15% | How well did they refine and improve with each AI interaction? |
| DA | Debugging with AI | 15% | Did they diagnose root causes or just ask AI to fix errors? |
| AD | Architecture Decisions | 10% | Code structure, separation of concerns, maintainability choices |
| CC | Communication Clarity | 10% | Quality of prompts and how clearly they directed the AI |
| TE | Token Efficiency | 10% | Got good results without excessive back-and-forth |

### Hire Thresholds

| Recommendation | Score |
|---|---|
| ⭐ Strong Hire | ≥ 85 |
| ✅ Hire | ≥ 70 |
| 🟡 Select | ≥ 55 |
| ⛔ Pass | < 55 |

Thresholds are **Python-enforced** — the LLM's own claimed composite/recommendation is always discarded and recomputed from the raw per-dimension scores. See `_bmad-output/implementation-artifacts/deferred-work.md` for one known edge case where the composite display and recommendation can briefly disagree near a boundary.

---

## Challenge Types

| Type | Description |
|---|---|
| `feature_extension` | Partial working implementation — candidate adds a specified feature |
| `bug_fix` | Working code with intentional hidden bugs — candidate must find and fix |
| `refactoring` | Messy but correct code — candidate improves structure without changing behaviour |
| `optimization` | Correct but slow code — candidate improves performance against a benchmark |

### Skill Areas

`api_integration` · `rate_limiting` · `llm_usage` · `server_monitoring` · `data_pipeline` · `game_logic`

### AI Assistance Modes

- **Unguarded** — Claude can give full solutions. Employer assesses *how* the candidate uses AI.
- **Guarded** — Claude Code CLI is asked (via an injected `CLAUDE.md`) to restrict itself to conceptual guidance. **This is honor-system enforcement only** — a candidate with shell access can bypass it. Accepted as current scope; see `docs/PROJECT_REQUIREMENTS.md`.

---

## Features

- **AI challenge generation** — describe a scenario, get a market-aligned coding challenge with starter code and evaluation rubric
- **Challenge catalog** — review, publish, and reuse challenges across assessments; 10 curated challenges seeded across the type/skill matrix
- **Isolated candidate environments** — one Docker container per candidate with browser VS Code + Claude Code CLI (graceful degradation without Docker — links still generate)
- **Full workspace capture** — entire `/workspace` extracted before container cleanup, with a text-only filter and 50KB cap
- **8-dimension evaluation** — single Claude call scores all dimensions with per-dimension rationales; all 8 keys always present even on a partial LLM response
- **Employer dashboard** — 5-tab UI: Generate · Catalog · Link · Results · Compare
- **SVG radar chart** — visual 8-dimension profile per candidate
- **Side-by-side comparison** — overlaid radar + butterfly chart for two candidates
- **Human override & flag workflow** — flag any submission for review; override any hire recommendation with a required rationale; every override permanently logged to an append-only calibration table
- **Visibility floor** — un-evaluated candidates always sort last, never hidden
- **Employer preview** — see the candidate-facing view of a challenge without spinning up Docker
- **64-test suite** — 8-dimension scoring, workspace extraction, hire-threshold boundaries, candidate ranking, and challenge generation, all runnable with no LLM key or Docker daemon

---

## Quick Start

### Prerequisites

- Python 3.11+
- An [OpenRouter](https://openrouter.ai/keys) API key (LLM calls are routed through OpenRouter, not the Anthropic API directly)
- Docker (**optional** — the app runs and the employer dashboard is fully usable without it; only live candidate containers require it)

### Setup

```bash
git clone https://github.com/kunalg06/hire-signal.git
cd hire-signal

# Install dependencies
pip install -r requirements.txt

# Configure environment
echo "OPENROUTER_API_KEY=sk-or-your-key-here" > .env

# Run the platform
python run.py
```

Open `http://localhost:8000` in your browser.

### Running the test suite

```bash
python -m pytest tests/ -v
```

64 tests, no API key or Docker daemon required — every LLM/Docker call is mocked.

### Docker (for live candidate containers)

Build the candidate-container image and run the app normally — this is the actual dev path, **not** `docker-compose` (see `docs/ARCHITECTURE.md` for why `docker/docker-compose.yml` is a legacy/unused orchestration file in this codebase):

```bash
cd docker
docker build -f Dockerfile.codeserver -t coding-platform-student:latest .
cd ..
python run.py
```

---

## Employer Workflow

### 1. Generate a Challenge

```bash
POST /api/generate-challenge
{
  "problem_statement": "Build a rate limiter that throttles API requests per user",
  "challenge_type": "feature_extension",
  "skill_area": "rate_limiting",
  "difficulty": "medium",
  "ai_assistance_mode": "unguarded"
}
```

### 2. Publish to Catalog

```bash
POST /api/challenges/{challenge_id}/publish
```

### 3. Create an Assignment and Generate a Candidate Link

```bash
POST /api/assignments
{ "title": "...", "description": "...", "evaluation_criteria": "...", "starter_code": "...", "challenge_id": "..." }

POST /api/generate-link/{assignment_id}
# Returns link_id — share with candidate
```

### 4. Candidate Submits

Candidate accesses their isolated VS Code environment, works with Claude, and submits. The platform captures the full workspace and starts evaluation in the background — the candidate's browser polls for results every 3 seconds.

### 5. View Results

```bash
GET /api/submission/{submission_id}
# Returns: composite_score, hire_recommendation, 8 dimension scores + rationales
```

### 6. Compare, Flag, and Override

```bash
GET /api/challenges/{challenge_id}/candidates?sort_by=composite_score&order=desc
# Ranked list, sortable by composite or any dimension, un-evaluated candidates always last

POST /api/submissions/{submission_id}/flag
{ "reason": "Suspicious timing pattern" }

POST /api/submissions/{submission_id}/override
{ "override_recommendation": "hire", "override_rationale": "Strong communication, coachable" }
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/generate-challenge` | Generate AI challenge (type, skill, mode) |
| `GET` | `/api/challenges` | List published challenges (filterable) |
| `GET` | `/api/challenges/{id}` | Get single challenge |
| `POST` | `/api/challenges/{id}/publish` | Publish to catalog |
| `DELETE` | `/api/challenges/{id}` | Soft-remove from catalog |
| `GET` | `/api/challenges/{id}/candidates` | Ranked candidates, sortable, dimension averages, visibility floor |
| `GET` | `/api/challenges/meta/options` | Valid enum values |
| `POST` | `/api/assignments` | Create assignment |
| `GET` | `/api/assignments` | List all assignments |
| `GET` | `/api/assignments/{id}` | Get assignment |
| `POST` | `/api/generate-link/{assignment_id}` | Generate candidate link |
| `POST` | `/api/submit-with-files/{link_id}` | Submit workspace for evaluation |
| `GET` | `/api/submission/{id}` | Get results (score, dimensions, hire verdict) |
| `POST` | `/api/submissions/{id}/flag` | Flag a submission for manual review |
| `POST` | `/api/submissions/{id}/override` | Override the AI hire recommendation |
| `GET` | `/api/analytics/overrides` | Override calibration analytics |
| `GET` | `/student/preview/{challenge_id}` | Employer preview of the candidate view (no Docker) |
| `GET` | `/api/system/health` | System health check |

Full documentation with request/response examples: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

---

## Project Structure

```
hire-signal/
├── app/
│   ├── routes/
│   │   ├── assignments.py      # Assignment CRUD + simple per-assignment candidate list
│   │   ├── challenges.py       # Challenge generation + catalog + full candidate ranking
│   │   ├── links.py            # Candidate link generation + container spin-up
│   │   ├── submissions.py      # Submission + 8-dim evaluation pipeline + flag/override
│   │   ├── student.py          # Candidate workspace portal + employer preview
│   │   ├── analytics.py        # Override calibration analytics
│   │   └── management.py       # System health & container management
│   ├── services/
│   │   ├── evaluation_service.py   # Claude evaluation + challenge generation
│   │   ├── database_service.py     # All DB operations (raw SQL, no ORM)
│   │   ├── llm_service.py          # OpenRouter wrapper — the only LLM call surface
│   │   ├── docker_service.py       # Container lifecycle via subprocess `docker` CLI
│   │   ├── session_log_service.py  # Claude interaction log parsing
│   │   └── management_service.py   # System monitoring
│   ├── models/
│   │   └── database.py         # SQLite schema (10 tables)
│   └── utils/
│       └── helpers.py          # ID generation, validation, rate limiting
├── templates/
│   └── frontend.html           # Employer dashboard (5-tab SPA, single file)
├── tests/                      # 64 pytest tests, no LLM key or Docker daemon required
├── docker/                     # Dockerfiles (Dockerfile.codeserver is the one that matters)
├── docs/                       # Architecture, API reference, requirements, folder structure
├── scripts/
│   └── seed_challenges.py      # Seeds 10 curated challenges
├── tools/
│   └── client.py               # Python SDK for API access
├── _bmad-output/               # Planning + implementation artifacts (epics, stories, deferred work)
├── AGENT.md                    # Session continuity for AI-assisted dev — read this first
├── CLAUDE.md                   # Dev guide: architecture constraints, debugging, customization
├── run.py                      # Flask entry point
└── requirements.txt
```

---

## Database Schema

10 SQLite tables, auto-created on startup (`CREATE TABLE IF NOT EXISTS` + guarded `ALTER TABLE` migrations):

| Table | Purpose |
|---|---|
| `assignments` | Challenge definitions, optionally linked to a catalog challenge |
| `session_links` | Candidate links → containers |
| `submissions` | Submitted workspaces, with flag status |
| `submission_files` | Individual files per submission |
| `session_logs` | Claude interaction log per session |
| `dimension_scores` | Per-dimension score + rationale per submission |
| `hire_evaluations` | Composite score + hire verdict (+ human override) |
| `challenges` | Challenge catalog (draft/published) |
| `comparison_sessions` | Saved side-by-side comparison views |
| `score_overrides` | Append-only human-override audit log |

Full schema detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Environment Variables

```env
# Required
OPENROUTER_API_KEY=sk-or-...

# Optional (defaults shown)
OPENROUTER_MODEL=anthropic/claude-haiku-4-5
FLASK_ENV=development
PORT=8000
DB_PATH=data/assignments.db
DOCKER_HOST=                          # auto-detected
DOCKER_IMAGE=coding-platform-student:latest
SECRET_KEY=                           # auto-generated in dev
```

Note: candidate container ports (7100-7900) are a hardcoded constant in `app/config.py`, not an env var.

---

## Status

**All planned epics complete** as of July 2026 — challenge generation, 8-dimension scoring, candidate comparison and hiring workflow, employer dashboard, student experience, and test coverage. See `AGENT.md` for the current implementation snapshot and `_bmad-output/implementation-artifacts/deferred-work.md` for known, deliberately-deferred gaps (nothing blocking, all documented with file/line references).

---

## Human Override Policy

AI scores are one signal in a hiring decision, not the decision itself. The platform is designed around this principle:

- Hiring managers can flag and override any score
- Every override is logged for calibration in an append-only table — the original AI verdict is never modified
- **Visibility floor**: score affects rank only — all candidates remain visible regardless of score
- AI Beta banner is always shown on the employer dashboard

---

## Tech Stack

- **Backend**: Python 3.11, Flask 3.0, SQLite (no ORM)
- **AI**: Claude models via OpenRouter (Haiku 4.5 default, swappable via `OPENROUTER_MODEL`)
- **Candidate environment**: Docker, code-server (browser VS Code), Claude Code CLI
- **Frontend**: Vanilla HTML/CSS/JS — no framework, no build step
- **Testing**: pytest, 64 tests, fully mocked LLM/Docker

---

## License

MIT
