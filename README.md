# hire-signal

> AI-powered hire-readiness evaluation platform — assess candidates on real-world AI-assisted coding competency, not just algorithmic recall.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Flask](https://img.shields.io/badge/flask-3.0-green.svg)
![Status](https://img.shields.io/badge/status-phase%201%20complete-brightgreen.svg)
![AI Beta](https://img.shields.io/badge/AI%20scoring-experimental-orange.svg)

---

## What is hire-signal?

Coding interviews have changed. Candidates now use AI tools on the job — and the best ones know *how* to collaborate with AI effectively, not just write code from scratch. hire-signal evaluates that skill.

Employers post a challenge. Candidates solve it in an isolated browser-based VS Code environment with full Claude AI access. The platform records every Claude interaction, extracts the final workspace, and evaluates the candidate across **8 AI-collaboration dimensions** — producing a structured hire recommendation.

> **AI Beta Notice:** Scores are experimental signals. Human judgment holds final authority. Always review before making hiring decisions.

---

## How It Works

```
Employer creates challenge
        ↓
Generates unique link per candidate
        ↓
Candidate codes in isolated Docker container
(browser VS Code + Claude AI access)
        ↓
On submit: full workspace snapshot extracted
        ↓
8-dimension evaluation via Claude
        ↓
Hire recommendation: strong_hire / hire / select / pass
        ↓
Employer compares candidates side-by-side
```

---

## 8-Dimension Scoring Framework

Inspired by the ArcEval framework for AI-era engineering assessment:

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

Thresholds are Python-enforced — never delegated to Claude.

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
- **Guarded** — Claude restricted to guidance only. Candidate must reason independently.

---

## Features (Phase 1)

- **AI challenge generation** — describe a scenario, get a market-aligned coding challenge with starter code and evaluation rubric
- **Challenge catalog** — review, publish, and reuse challenges across assessments
- **Isolated candidate environments** — one Docker container per candidate with browser VS Code + Claude
- **Full workspace capture** — entire `/workspace` extracted before container cleanup
- **8-dimension evaluation** — single Claude call scores all dimensions with per-dimension rationales
- **Candidate comparison** — ranked table of all candidates for an assignment with dimension breakdowns and cohort averages
- **Employer dashboard** — 5-tab UI: Generate · Catalog · Link · Results · Compare
- **SVG radar chart** — visual 8-dimension profile per candidate
- **Human override policy** — AI scores inform, never decide

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Anthropic API key — [console.anthropic.com](https://console.anthropic.com)

### Setup

```bash
git clone https://github.com/kunalg06/hire-signal.git
cd hire-signal

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# Run the platform
python run.py
```

Open `http://localhost:8000` in your browser.

### Docker (full stack with candidate containers)

```bash
cd docker
docker-compose up --build
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
{ "title": "...", "description": "...", "evaluation_criteria": "...", "starter_code": "..." }

POST /api/generate-link/{assignment_id}
# Returns link_id — share with candidate
```

### 4. Candidate Submits

Candidate accesses their isolated VS Code environment, works with Claude, and clicks Submit. The platform captures the full workspace and starts evaluation.

### 5. View Results

```bash
GET /api/submission/{submission_id}
# Returns: composite_score, hire_recommendation, 8 dimension scores + rationales
```

### 6. Compare All Candidates

```bash
GET /api/assignments/{assignment_id}/candidates
# Returns: ranked list with per-dimension scores and cohort averages
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/generate-challenge` | Generate AI challenge (type, skill, mode) |
| `GET` | `/api/challenges` | List published challenges (filterable) |
| `GET` | `/api/challenges/{id}` | Get single challenge |
| `POST` | `/api/challenges/{id}/publish` | Publish to catalog |
| `DELETE` | `/api/challenges/{id}` | Remove from catalog |
| `GET` | `/api/challenges/meta/options` | Valid enum values |
| `POST` | `/api/assignments` | Create assignment |
| `GET` | `/api/assignments` | List all assignments |
| `GET` | `/api/assignments/{id}` | Get assignment |
| `GET` | `/api/assignments/{id}/candidates` | Ranked candidates with 8-dim scores |
| `POST` | `/api/generate-link/{assignment_id}` | Generate candidate link |
| `POST` | `/api/submit-with-files/{link_id}` | Submit workspace for evaluation |
| `GET` | `/api/submission/{id}` | Get results (score, dimensions, hire verdict) |
| `GET` | `/api/session-logs/{submission_id}` | Claude interaction log |
| `GET` | `/api/system/health` | System health check |
| `GET` | `/api/system/status` | Container and database status |

Full documentation: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

---

## Project Structure

```
hire-signal/
├── app/
│   ├── routes/
│   │   ├── assignments.py      # Assignment CRUD + candidate comparison
│   │   ├── challenges.py       # Challenge generation + catalog
│   │   ├── links.py            # Candidate link generation
│   │   ├── submissions.py      # Submission + 8-dim evaluation pipeline
│   │   ├── student.py          # Candidate workspace portal
│   │   └── management.py       # System health & container management
│   ├── services/
│   │   ├── evaluation_service.py   # Claude evaluation + challenge generation
│   │   ├── database_service.py     # All DB operations
│   │   ├── docker_service.py       # Container lifecycle
│   │   ├── session_log_service.py  # Claude interaction log parsing
│   │   └── management_service.py   # System monitoring
│   ├── models/
│   │   └── database.py         # SQLite schema (8 tables)
│   └── utils/
│       └── helpers.py          # ID generation, validation, rate limiting
├── templates/
│   └── frontend.html           # Employer dashboard (5-tab SPA)
├── docker/                     # Dockerfiles + compose
├── docs/                       # Architecture, API reference, requirements
├── scripts/                    # Setup scripts
├── tools/
│   └── client.py               # Python SDK for API access
├── _bmad-output/               # Planning artifacts (epics & stories)
├── AGENT.md                    # Session continuity for AI-assisted dev
├── run.py                      # Flask entry point
└── requirements.txt
```

---

## Database Schema

8 SQLite tables auto-created on startup:

| Table | Purpose |
|---|---|
| `assignments` | Challenge definitions |
| `session_links` | Candidate links → containers |
| `submissions` | Submitted workspaces |
| `submission_files` | Individual files per submission |
| `session_logs` | Claude interaction log per session |
| `challenges` | Challenge catalog (draft/published) |
| `dimension_scores` | Per-dimension scores per submission |
| `hire_evaluations` | Composite score + hire verdict |

---

## Environment Variables

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional
FLASK_ENV=development
PORT=8000
DB_PATH=assignments.db
CLAUDE_MODEL=claude-haiku-4-5-20251001
DOCKER_HOST=                          # auto-detected
SECRET_KEY=                           # auto-generated in dev
```

---

## Roadmap

### Phase 1 — Complete ✅
- 8-dimension scoring engine
- Market-aligned challenge generation and catalog
- Isolated Docker candidate environments
- Employer dashboard with radar chart and comparison view
- Hire recommendation (strong_hire / hire / select / pass)

### Phase 2 — Planned
- Human override UI with audit log
- Side-by-side candidate radar overlay (butterfly chart)
- Structured candidate workspace panels + verification nudge before submit
- Guarded mode Claude restrictions in-container
- Seed catalog with 10 curated challenges
- Unit test coverage

---

## Human Override Policy

AI scores are one signal in a hiring decision, not the decision itself. The platform is designed around this principle:

- Hiring managers can flag and override any score
- Every override is logged for calibration
- **Visibility floor**: score affects rank only — all candidates remain visible regardless of score
- AI Beta banner is always shown on the employer dashboard

---

## Tech Stack

- **Backend**: Python 3.11, Flask 3.0, SQLite
- **AI**: Anthropic Claude (haiku-4-5 default, configurable)
- **Candidate environment**: Docker, code-server (browser VS Code)
- **Frontend**: Vanilla HTML/CSS/JS — no framework dependency

---

## License

MIT

---

*Built with Claude Code · Phase 1 complete July 2026*
