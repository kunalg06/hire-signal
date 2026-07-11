# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🔴 READ FIRST — Session Continuity

**At the start of every session, read `AGENT.md` before doing anything else.**

`AGENT.md` is the living session-continuity file: current implementation state, epic/story status, known deferred issues, and architecture decisions made in prior sessions. This file (`CLAUDE.md`) is the stable how-to-work-here guide — it doesn't change every session. `AGENT.md` does.

Full epics and stories spec: `_bmad-output/planning-artifacts/epics-and-stories.md`
Deferred/known-issue log: `_bmad-output/implementation-artifacts/deferred-work.md`

---

## 🎯 Project Overview

**hire-signal** is an AI hire-readiness evaluation platform. Employers post coding challenges; candidates complete them in isolated Docker containers running browser-based VS Code with Gemini CLI access. Submissions are scored across **8 AI-collaboration dimensions** and produce a hire recommendation (`strong_hire` / `hire` / `select` / `pass`).

**This is a hiring tool, not an educational platform.** It evaluates AI-assisted coding competency, not raw coding ability in isolation.

### Core Flow
1. Employer generates a market-aligned coding challenge (Gemini-authored) or picks one from the catalog
2. Employer creates an assignment from that challenge and generates a candidate access link
3. Each link spins up an isolated Docker container running code-server with the Gemini CLI pre-installed
4. Candidate codes in the browser, optionally collaborating with Gemini, and submits
5. Gemini scores the submission across 8 dimensions; Python enforces the hire-recommendation thresholds
6. Results appear on the employer dashboard: ranked candidate list, radar chart, side-by-side comparison, flag/override workflow

---

## 🗂️ Architecture

### Backend — Flask application factory (`app/`)

```
app/
├── __init__.py          # create_app(config_name) — loads .env, registers all 7 blueprints
├── config.py             # Config / DevelopmentConfig / TestingConfig / ProductionConfig
├── models/
│   └── database.py       # Database class — sqlite3 connection + init_db() (CREATE TABLE IF NOT EXISTS + migrations)
├── routes/                # 7 Flask blueprints, one per concern (see API section below)
├── services/
│   ├── database_service.py    # All SQL — raw sqlite3, no ORM
│   ├── evaluation_service.py  # 8-dimension scoring, hire-threshold enforcement, challenge generation
│   ├── llm_service.py         # Thin Gemini wrapper — the ONLY LLM call surface
│   ├── docker_service.py      # Container lifecycle via subprocess `docker` CLI (not the docker SDK)
│   ├── management_service.py  # System status / container admin helpers
│   └── session_log_service.py # Parses Gemini CLI session logs from the student container
└── utils/helpers.py       # IDGenerator, ValidationHelper, RateLimiter
```

There is **no `main.py`**. The entry point is `run.py` at the repo root, which calls `create_app(env)` and runs the Flask dev server.

### Frontend (`templates/frontend.html`)

Single-file HTML/CSS/vanilla-JS employer dashboard (~85KB). No build step, no framework. Served directly by Flask's `/` route (`app/__init__.py`). Talks to the backend via relative `/api/...` fetch calls.

### Student environment (`docker/`)

- `Dockerfile.codeserver` — code-server + Gemini CLI (`@google/gemini-cli` via npm), restricted to `gemini-2.5-flash` by container-level config
- `Dockerfile.backend` — Flask backend image (used only by `docker/docker-compose.yml`, which is a legacy/optional orchestration path — the actual dev workflow runs `python run.py` directly and manages student containers via `DockerService`'s subprocess CLI calls, not `docker-compose`)
- Container port range: **7100–7900** (see Architecture Constraints below)

### Database — SQLite, no ORM

11 tables via raw SQL in `app/models/database.py`. See **DB Schema** section below for the full table list. Migrations are `ALTER TABLE ... ADD COLUMN` wrapped in `try/except sqlite3.OperationalError`, run idempotently every time `init_db()` is called.

---

## 🔑 Key Product Decisions

- **8-Dimension scoring** (`EvaluationService.DIMENSION_WEIGHTS`, `app/services/evaluation_service.py`):
  1. Problem Decomposition (15%)
  2. First-Principles Thinking (15%)
  3. Creative Problem Solving (10%)
  4. Iteration Quality (15%)
  5. Debugging with AI (15%)
  6. Architecture Decisions (10%)
  7. Communication Clarity (10%)
  8. Token Efficiency (10%)

- **Hire recommendation thresholds** (`EvaluationService.HIRE_THRESHOLDS`): `strong_hire >= 85`, `hire >= 70`, `select >= 55`, `pass < 55` — **enforced in Python, never trusted from Claude's own response**. This is load-bearing: the LLM's scoring prompt asks it to also compute a composite/recommendation, but the route always recomputes both from the raw per-dimension scores.

- **Per-challenge dimension applicability** (revised 2026-07-11): not every challenge can generate real evidence for all 8 dimensions — e.g. "Architecture Decisions" on a pure-correctness bug fix with no design fork. `generate_challenge()` now emits `applicable_dimensions` (subset of the 8 dimension keys) and an optional `decision_point` (`{applies, prompt, option_a, option_b}` — a genuine design trade-off, no verdict), persisted as nullable `challenges.applicable_dimensions_json`/`decision_point_json` (NULL on any pre-existing challenge = "all 8 apply, no decision point"). `score_8_dimensions()` computes the composite as a weighted average over ONLY applicable dimensions, renormalized — an inapplicable dimension is excluded from the denominator, never scored 0 and averaged in. When `decision_point.applies`, the candidate is asked (via instructions.md) to implement one option and justify it in a `DECISION.md` file, which the existing `extract_container_files()` workspace-snapshot pull already captures for the scorer — no separate capture path.

- **Unscored ≠ scored 0** (2026-07-11): if `score_8_dimensions()`'s LLM call/parse fails even after retries, the safe-default result carries `evaluation_failed: True` (threaded through `evaluate_code()`). `evaluate_submission_files()` auto-flags that submission via the existing `flag_submission()`/`flag_events` path so a swallowed provider/parse failure can never look identical to a candidate who genuinely earned a 0 — never trust a `composite_score: 0.0` without checking this flag.

- **Human override policy**: AI scores inform, never decide. Employers can flag any submission or override its hire recommendation. Every override is logged as an append-only calibration event (`score_overrides` table) — never UPDATE/DELETE that table. The original AI `composite_score`/`recommendation` in `hire_evaluations` are read-only after creation.

- **Visibility floor**: score affects candidate rank, never hides a candidate. Un-evaluated candidates always sort last regardless of sort direction (`math.inf`/`-math.inf` sentinel in the ranking route).

- **Guarded vs unguarded mode**: `unguarded` lets Gemini give full solutions inside the student container; `guarded` read-only bind-mounts a `~/.gemini/GEMINI.md` (not workspace-local — Gemini CLI's global context file) asking Gemini CLI to act as a collaborator: no complete/full solutions in one shot, but short targeted code (a corrected line, a snippet, method syntax) is allowed for a specific question ONCE the candidate has stated their own hypothesis or symptom — governed AI availability, not a hard code block (revised 2026-07-10 based on how HackerRank/CodeSignal/Codility/CoderPad handle AI-assisted assessments; tightened again 2026-07-11 after a real candidate session showed Gemini complying with an unqualified "solve it for me" and volunteering the full remaining bug list unprompted — the wording now explicitly requires redirecting an unqualified solve/fix request with a diagnostic question, and forbids enumerating more than one issue per response). **Enforcement is honor-system for the wording itself** — the candidate has shell access and could set `HOME` elsewhere to dodge the mounted file entirely, and even with the file honored the model can still ignore its instructions under pressure (as observed 2026-07-11); the two mounted files (`GEMINI.md`, `settings.json`) themselves are kernel-enforced read-only. Accepted as v1 scope (see `deferred-work.md`).

- **Challenge types**: `bug_fix | feature_extension | refactoring | optimization`
- **Skill areas**: `api_integration | rate_limiting | data_pipeline | llm_usage | server_monitoring | game_logic`

---

## 🚀 Common Development Tasks

### Running the app

```bash
# Set GEMINI_API_KEY in .env first (copy from .env.example)
python run.py
# Backend + frontend both served from http://localhost:8000
```

There is no separate frontend dev server — `templates/frontend.html` is served directly by the Flask app.

### Running tests

```bash
python -m pytest tests/ -v
```

- 64 tests across 5 files (`tests/test_score_8_dimensions.py`, `test_extract_container_files.py`, `test_hire_recommendation_thresholds.py`, `test_candidates_endpoint.py`, `test_generate_challenge_endpoint.py`)
- Root `conftest.py` puts the project root on `sys.path` — no package install needed
- All LLM calls are mocked (`LLMService.chat` monkeypatched) — **no `GEMINI_API_KEY` required to run the suite**
- Integration tests (`test_candidates_endpoint.py`, `test_generate_challenge_endpoint.py`) use `create_app("testing")` plus a monkeypatched, `tmp_path`-backed SQLite file — see the ⚠️ warning below before writing any new integration test

### Testing the API directly

```bash
curl -X POST http://localhost:8000/api/generate-challenge \
  -H "Content-Type: application/json" \
  -d '{"problem_statement":"Fix a leaking rate limiter","difficulty":"medium"}'

curl -X POST http://localhost:8000/api/assignments \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","evaluation_criteria":"Test"}'

curl -X POST http://localhost:8000/api/generate-link/{assignment_id}
curl http://localhost:8000/api/challenges/{challenge_id}/candidates
```

### Seeding sample challenges

```bash
python scripts/seed_challenges.py
```

---

## ⚠️ Critical Trap — Blueprint `db_service` Is an Import-Time Singleton

**Every route file constructs `db_service = DatabaseService()` at module import time**, not per-request. `DatabaseService.__init__` resolves `Config.DB_PATH` **once**, at that moment — which means:

- `create_app(config_name)` does **not** give you database isolation. It builds its own separate `Database(config.DB_PATH)` purely to call `.init_db()` during app setup; the blueprints' `db_service` singletons never see it.
- Because Python caches module imports, if `app.config` (and therefore all 7 blueprints) is imported anywhere earlier in a process — including transitively, e.g. any file that does `from app.services.evaluation_service import ...` — the singletons are already constructed and already pointed at whatever `Config.DB_PATH` resolved to at that time (default: the real `data/assignments.db`).

**If you write a test or script that touches any route's `db_service`, you must directly monkeypatch that module's `db_service.db` attribute** onto a fresh `Database(temp_path)` instance — do not rely on `create_app(config_name)` alone. See `tests/test_candidates_endpoint.py`'s `client` fixture for the reference pattern (discovered and fixed during Story 7.4; reused in Story 7.5).

---

## 🛠️ Common Customization Points

### Change the LLM model
`GEMINI_MODEL` env var (default `gemini-2.5-flash`). Routed entirely through `LLMService.chat()` in `app/services/llm_service.py` — this is the **only** LLM call surface in the codebase; do not call the `google-genai` SDK directly anywhere else.

### Add packages to the student container
Edit `docker/Dockerfile.codeserver`.

### Add a new challenge type or skill area
Extend `VALID_CHALLENGE_TYPES`/`VALID_SKILL_AREAS` in `app/routes/challenges.py`, and the corresponding `type_instruction`/`skill_imports` dicts in `EvaluationService.generate_challenge()`.

### Customize the scoring rubric
`EvaluationService.score_8_dimensions()` builds the full scoring prompt inline in `app/services/evaluation_service.py` — dimension rubric text lives there, weights live in `DIMENSION_WEIGHTS` at the top of the class.

---

## 🔍 Debugging & Troubleshooting

**Port already in use** — the app runs on 8000 by default (`PORT` env var); student containers use 7100–7900.

**`GEMINI_API_KEY not set`** — `LLMService.get_client()` raises `ValueError` if the key is empty after stripping quotes/whitespace. Check `.env`.

**Docker unavailable** — the system degrades gracefully. Links still generate instantly with a helpful message; `DockerService.get_client()` returns `None` rather than raising when the `docker` CLI isn't reachable.

**A student container's iframe won't load** — no `sandbox` attribute is set on the student iframe intentionally; code-server relies on service workers that a sandboxed iframe would block.

**Windows-only: garbled/crashed print output** — the console is cp1252. Never put non-ASCII characters (arrows, em-dashes, etc.) directly in `print()`/`logging` calls; this has silently aborted execution before. ASCII only.

**Database looks stale mid-session** — remember the import-time-singleton trap above. If you changed `DB_PATH` and things don't reflect it, you're probably looking at a `db_service` that was constructed before your change took effect.

---

## 📊 DB Schema — 11 Tables

| Table | Purpose | Key columns |
|---|---|---|
| `assignments` | An employer-created assessment | `id, title, description, starter_code, evaluation_criteria, challenge_id, is_deleted` |
| `session_links` | Maps a shareable link to a running container | `link_id, assignment_id, container_id, port, expires_at` |
| `submissions` | A candidate's submitted code | `submission_id, link_id, assignment_id, score, feedback, is_flagged, flag_reason, flag_by, flagged_at` |
| `submission_files` | Individual files within a submission | `file_id, submission_id, filename, content, file_size` |
| `session_logs` | Parsed Gemini CLI interaction log | `log_id, submission_id, timestamp, interaction_type, prompt, response_summary` |
| `dimension_scores` | Per-dimension score + rationale | `score_id, submission_id, dimension, score, rationale` |
| `hire_evaluations` | Composite score + recommendation (+ override) | `eval_id, submission_id, composite_score, recommendation, is_overridden, override_recommendation, override_rationale, evaluated_at` |
| `challenges` | Challenge catalog (generated or curated) | `id, title, domain, description, evaluation_rubric, starter_code, challenge_type, skill_area, difficulty, ai_assistance_mode, is_published, created_at, applicable_dimensions_json, decision_point_json` |
| `comparison_sessions` | Saved side-by-side comparison views | `id, challenge_id, name, submission_ids_json, created_at` |
| `score_overrides` | Append-only human-override audit log | `id, submission_id, ai_recommendation, human_recommendation, override_rationale, overridden_at` |
| `flag_events` | Append-only flag-lifecycle audit log | `id, submission_id, reason, flagged_by, flagged_at` |

---

## 🌐 API Endpoints — Full List

All routes are registered as Flask blueprints (`app/routes/`) with `url_prefix='/api'` except `student` (root-level `/student/...`) and `management` (`url_prefix='/api/system'`).

**Assignments** (`app/routes/assignments.py`)
| Method | Path |
|---|---|
| GET/POST | `/api/assignments` |
| GET | `/api/assignments/<id>` |
| DELETE | `/api/assignments/<id>` (soft-delete; historical links/submissions still resolve by id) |
| GET | `/api/assignments/<id>/candidates` |

**Links** (`app/routes/links.py`)
| Method | Path |
|---|---|
| POST | `/api/generate-link/<assignment_id>` |

**Challenges** (`app/routes/challenges.py`)
| Method | Path |
|---|---|
| POST | `/api/generate-challenge` |
| GET | `/api/challenges` |
| GET | `/api/challenges/<id>` |
| POST | `/api/challenges/<id>/publish` |
| DELETE | `/api/challenges/<id>` (soft-delete) |
| GET | `/api/challenges/<id>/candidates` (sort_by/order, dimension_averages, visibility floor) |
| GET | `/api/challenges/meta/options` |

**Submissions** (`app/routes/submissions.py`)
| Method | Path |
|---|---|
| GET | `/api/submissions` |
| POST | `/api/submit-with-files/<link_id>` |
| GET | `/api/submission/<id_or_link>` |
| GET | `/api/session-logs/<submission_id>` |
| DELETE | `/api/submissions/<id>` (deletes owned rows; `score_overrides`/`flag_events` audit logs preserved) |
| POST | `/api/submissions/<id>/flag` |
| POST | `/api/submissions/<id>/override` |

**Analytics** (`app/routes/analytics.py`)
| Method | Path |
|---|---|
| GET | `/api/analytics/overrides` |

**Student** (`app/routes/student.py`)
| Method | Path |
|---|---|
| GET | `/student/<link_id>` |
| GET | `/student/preview/<challenge_id>` (employer preview, no Docker) |

**System / Management** (`app/routes/management.py`)
| Method | Path |
|---|---|
| GET | `/api/system/status`, `/api/system/health` |
| POST | `/api/system/cleanup-old`, `/api/system/cleanup-all` |
| GET | `/api/system/containers/<id>/info`, `/api/system/containers/<id>/logs` |
| POST | `/api/system/containers/<id>/restart`, `/api/system/containers/<id>/stop` |

Full request/response shapes and worked examples: `docs/API_REFERENCE.md`.

---

## 🔒 Architecture Constraints — Read Before Writing Any Code

- **SQLite only** — no Postgres, no Redis, no ORM. Raw SQL. `CREATE TABLE IF NOT EXISTS` is the migration strategy; `ALTER TABLE` guarded by `try/except sqlite3.OperationalError` (never a bare `except Exception`).
- **LLM via Gemini only** — `LLMService.chat()` is the single call surface. Model swap via `GEMINI_MODEL`. Do not import the `google-genai` SDK directly outside `llm_service.py`.
- **Docker via subprocess CLI** — the `docker` Python SDK is incompatible with `requests>=2.32` on Python 3.14 in this environment. All Docker operations go through `DockerService` in `docker_service.py`, which shells out to the `docker` CLI.
- **Container port range: 7100–7900** — ports below 7000 (especially 6000–6007) are Chrome-blocked and will silently fail to load in-browser.
- **Score thresholds are Python-enforced** — never trust Claude's own threshold/recommendation output; always recompute from the raw dimension scores.
- **Visibility floor** — never hide a candidate from the ranked list; un-evaluated candidates sort last, not omitted.
- **`score_overrides` is append-only** — never UPDATE or DELETE.
- **`flag_events` is append-only** — never UPDATE or DELETE; mirrors `score_overrides`. Written atomically alongside the `submissions` flag update inside `DatabaseService.flag_submission()` (same transaction, one commit) so a crash between the two writes can never lose audit history.
- **`hire_evaluations.composite_score`/`.recommendation` are read-only after creation** — an override only ever writes the `override_*` columns.
- **No `sandbox` attribute on the student iframe** — code-server needs service workers.
- **`db_service` is an import-time singleton per route module** — see the trap section above.
- **ASCII only in `print()`/logging strings** — Windows console is cp1252.
- **Tests: `LLMService.chat` is always mocked** — never let a test reach a real Gemini API call or a real Docker daemon.

---

## 📖 Related Documentation

- `AGENT.md` — current sprint/story state, deferred production gaps, session continuity (read this first, every session)
- `docs/ARCHITECTURE.md` — system diagrams and data-flow detail
- `docs/API_REFERENCE.md` — full endpoint documentation with request/response examples
- `docs/PROJECT_REQUIREMENTS.md` — product requirements and scoring rubric detail
- `docs/FOLDER_STRUCTURE.md` — annotated directory tree
- `_bmad-output/planning-artifacts/epics-and-stories.md` — full epic/story backlog spec
- `_bmad-output/implementation-artifacts/deferred-work.md` — every known-but-unfixed issue, with file/line references

---

**Last updated**: 2026-07-04 (migrated LLM provider from OpenRouter/Claude to Gemini — backend `LLMService` and the student container's coding assistant both now run on Gemini)
