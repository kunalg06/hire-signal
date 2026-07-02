# AGENT.md — Session Continuity File
> Read this at the start of every session before doing anything else.
> Updated automatically as work progresses.

---

## What This Project Is

**AI Hire-Readiness Evaluation Platform** — employers post coding challenges, candidates complete them in isolated Docker containers with browser-based VS Code + Claude API access. The platform evaluates candidates across **8 AI-collaboration dimensions** and produces a hire recommendation (strong_hire / hire / select / pass) with a side-by-side candidate comparison view.

This is NOT an educational platform. It is a **hiring tool** for employers to evaluate AI-assisted coding competency.

---

## Key Product Decisions

- **8-Dimension scoring engine** (ArcEval/Vizuara framework):
  1. Problem Decomposition (15%)
  2. First-Principles Thinking (15%)
  3. Creative Problem Solving (10%)
  4. Iteration Quality (15%)
  5. Debugging with AI (15%)
  6. Architecture Decisions (10%)
  7. Communication Clarity (10%)
  8. Token Efficiency (10%)

- **Hire recommendations**: `strong_hire >= 85`, `hire >= 70`, `select >= 55`, `pass < 55`
  - Thresholds enforced in Python — never trust Claude's threshold determination alone

- **Human override policy**: AI scores inform, never decide. Employers can flag/override any score. Every override logged as calibration data. Visibility floor — score affects rank, never hides candidates.

- **Guarded vs Unguarded mode**: Unguarded = Claude can give full solutions. Guarded = Claude restricted to guidance only.

- **Challenge types**: `bug_fix | feature_extension | refactoring | optimization`
- **Skill areas**: `api_integration | rate_limiting | data_pipeline | llm_usage | server_monitoring | game_logic`

---

## Current Implementation State (~80% complete)

### ✅ Done — Epics 1, 2, 3, 4 + Phase 1 integration fixes

#### Epic 1 — Bug Fixes (done 2026-06-30)
- Story 1.1 — efficiency score bug fixed (`submissions.py`)
- Story 1.2 — `container_id` passed into evaluation pipeline
- Story 1.3 — score bounds clamp: `min(100.0, max(0.0, ...))`

#### Phase 1 Integration Fixes (done 2026-07-02)
- LLM: Anthropic SDK → OpenRouter via `app/services/llm_service.py`
- CORS: `flask-cors` + relative `/api` URLs
- Docker SDK → subprocess CLI (`docker_service.py` rewritten)
- Workspace injection: `inject_workspace_files()` in `links.py`
- iframe: port range 7100–7900, removed sandbox, added warmup polling

#### Epic 3 — Market-Aligned Challenge System (done 2026-07-01)
- `challenges` table (12 cols), catalog CRUD endpoints
- `POST /api/generate-challenge` with type/skill/mode enums + validation
- Market-aligned generation prompt in `evaluation_service.py`
- Auto-persist generated challenges as unpublished

#### Epic 2 — 8-Dimension Scoring Engine (done 2026-07-01)
- `dimension_scores` + `hire_evaluations` tables
- `extract_container_files()` — full workspace snapshot (50KB cap, `{}` fallback)
- `score_8_dimensions()` — single Claude call, all 8 keys guaranteed
- Python-enforced thresholds (never trust Claude's)
- Per-dimension rows persisted; `GET /api/submission/<id>` returns full 8-dim response

#### Epic 4 — Candidate Comparison & Hiring Workflow (done 2026-07-02)

**Story 4.1 — Schema: comparison_sessions**
- `comparison_sessions` table in `database.py` `init_db()`
- DB methods: `create_comparison_session`, `get_comparison_session`, `list_comparison_sessions`

**Story 4.2 — Candidate comparison endpoint**
- `GET /api/challenges/<challenge_id>/candidates` — returns ALL candidates ranked by `composite_score` (default) or any of 8 dimension keys
- `sort_by` / `order` query params; 400 on invalid; 404 if challenge not found
- Each candidate has: `rank`, `is_evaluated`, `dimensions` dict, `composite_score`, `hire_recommendation`
- `dimension_averages` always returned (empty `{}` when no evaluated candidates)
- `assignments.challenge_id` column added via migration; `POST /api/assignments` accepts optional `challenge_id`

**Story 4.3 — Human override + flag**
- `POST /api/submissions/<id>/flag` — stores `is_flagged`, `flag_reason`, `flag_by`, `flagged_at`; `reason` required (400 if missing)
- `POST /api/submissions/<id>/override` — writes `is_overridden`, `override_recommendation`, `override_rationale` to `hire_evaluations`; original AI `composite_score` and `recommendation` NEVER touched
- Both return 404 (not found) / 409 (no evaluation exists to override)
- `GET /api/submission/<id>` now includes flag fields (indices 10–13)

**Story 4.4 — Override logging as calibration dataset**
- `score_overrides` table — append-only event log; every successful override inserts a row
- `GET /api/analytics/overrides` — returns `total_overrides`, `overrides_by_direction`, `recent_overrides` (last 20), `pattern_summary` (directions ≥20% share when total ≥10)
- `app/routes/analytics.py` — new blueprint registered in `app/__init__.py`

**Story 4.5 — Visibility floor enforcement**
- Un-evaluated candidates always sort LAST regardless of `order` direction (math.inf/-math.inf sentinel)
- `is_evaluated` boolean on each candidate (`row[7] is not None` from `he.evaluated_at`)

**Code review patches applied (2026-07-02):**
- `database.py` — migration `except Exception` → `except sqlite3.OperationalError` (both ALTER TABLE blocks)
- `submissions.py` — link_id fallback query now selects all 14 columns (was 9; flag fields were invisible)
- `challenges.py` — `dim_averages` now filters by `c['is_evaluated']` (not dict truthiness) and skips None scores
- `submissions.py` — flag/override routes check `rowcount > 0`; return 500 on silent DB failure

**Frontend sync fixes (applied alongside Story 4.4):**
- `saveAsAssignment()` — sends `challenge_id: currentChallengeId || null`
- `useCatalogChallenge()` — sends `challenge_id: id`
- Removed duplicate `viewInResults()` definition
- Flag and Override buttons added to Results detail panel (wired to `/flag` and `/override` endpoints)

---

### ❌ Not Built Yet (backlog)

| Story | Description |
|---|---|
| 1.4 | Replace `print()` with `logging` module |
| 3.6 | Seed 10 curated challenges (`scripts/seed_challenges.py`) |
| 5.3 | Butterfly chart / side-by-side radar overlay (Tab 5) |
| 6.2 | Verification nudge before submission ("Did you run it?") |
| 6.3 | Real polling: `GET /api/submission/<id>` every 3s until `evaluated_at` set |
| 6.4 | Preview as Student: `GET /student/preview/<challenge_id>` (no Docker) |
| 6.5 | Guarded mode: Claude system prompt injection in student container |
| 7.1–7.5 | Unit + integration tests (Epic 7) |

---

## Next Session — Start Here

**Workflow state:** All Epic 4 stories (4.1–4.5) are `done`. No `ready-for-dev` stories exist.

**Next action:** Run `/bmad-create-story` to create the next story file.
- First backlog story in sprint order: **Story 1.4** (`1-4-replace-print-with-proper-logging`)
- The skill will auto-discover this from `sprint-status.yaml`

**Then:** Run `/bmad-dev-story` to implement it.

---

## Key File Locations

| Purpose | Path |
|---|---|
| Epics & Stories (full spec) | `_bmad-output/planning-artifacts/epics-and-stories.md` |
| Sprint status | `_bmad-output/implementation-artifacts/sprint-status.yaml` |
| Deferred work log | `_bmad-output/implementation-artifacts/deferred-work.md` |
| This file | `AGENT.md` |
| Main config | `app/config.py` |
| DB schema / init | `app/models/database.py` |
| All DB queries | `app/services/database_service.py` |
| Evaluation + challenge gen | `app/services/evaluation_service.py` |
| LLM wrapper (OpenRouter) | `app/services/llm_service.py` |
| Submission routes | `app/routes/submissions.py` |
| Challenge routes | `app/routes/challenges.py` |
| Analytics routes | `app/routes/analytics.py` |
| Teacher dashboard | `templates/frontend.html` |
| Student workspace | `app/routes/student.py` |

---

## Architecture Constraints — Read Before Writing Any Code

- **SQLite only** — no Postgres, no Redis. Raw SQL, no ORM. `CREATE TABLE IF NOT EXISTS` is the migration strategy; `ALTER TABLE` via `try/except sqlite3.OperationalError` (not bare `except Exception`).
- **LLM via OpenRouter** — `LLMService` in `app/services/llm_service.py`; model via `OPENROUTER_MODEL` env var. Do NOT use `anthropic` SDK directly.
- **Docker via subprocess CLI** — `docker` Python SDK incompatible with requests≥2.32 on Python 3.14. All Docker ops go through `DockerService` in `docker_service.py`.
- **Container port range: 7100–7900** — ports below 7000 (esp. 6000–6007) are Chrome-blocked.
- **No non-ASCII in `print()` on Windows** — cp1252 console; Unicode arrows silently abort execution. ASCII only in print/log strings.
- **Score thresholds: Python-enforced** — `strong_hire>=85, hire>=70, select>=55, pass<55`. Never rely on Claude's threshold logic.
- **Visibility floor** — score affects rank only, never hides candidates. Un-evaluated candidates sort last (math.inf sentinel).
- **`score_overrides` is append-only** — every override inserts a new row. Never UPDATE or DELETE from it.
- **`hire_evaluations.composite_score` and `.recommendation` are read-only after creation** — override only writes `is_overridden`, `override_recommendation`, `override_rationale`.
- **`dim_averages` uses `is_evaluated` filter, not dict truthiness** — and skips None scores (no zero-default).
- **No sandbox on student iframe** — code-server uses service workers; sandbox blocks them.
- **Module-level `db_service = DatabaseService()`** in each route file — instantiated at import time.
- **Windows cp1252 print constraint** — see above; applies to ALL print/logging statements.

---

## DB Schema — Current Tables (10 total after Epic 4)

| Table | Key Columns |
|---|---|
| `assignments` | `id, title, description, starter_code, evaluation_criteria, challenge_id` |
| `session_links` | `link_id, assignment_id, container_id, port, expires_at` |
| `submissions` | `submission_id, link_id, assignment_id, score, feedback, is_flagged, flag_reason, flag_by, flagged_at` |
| `submission_files` | `file_id, submission_id, filename, content, file_size` |
| `session_logs` | `log_id, submission_id, timestamp, interaction_type, prompt, response_summary` |
| `dimension_scores` | `score_id, submission_id, dimension, score, rationale` |
| `hire_evaluations` | `eval_id, submission_id, composite_score, recommendation, is_overridden, override_recommendation, override_rationale, evaluated_at` |
| `challenges` | `id, title, domain, description, evaluation_rubric, starter_code, challenge_type, skill_area, difficulty, ai_assistance_mode, is_published, created_at` |
| `comparison_sessions` | `id, challenge_id, name, submission_ids_json, created_at` |
| `score_overrides` | `id, submission_id, ai_recommendation, human_recommendation, override_rationale, overridden_at` |

---

## API Endpoints — Full List

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| POST | `/api/assignments` | Create assignment (accepts optional `challenge_id`) |
| GET | `/api/assignments/<id>` | Get assignment |
| POST | `/api/generate-link/<assignment_id>` | Generate student link + spin up container |
| POST | `/api/generate-challenge` | Generate + persist challenge to catalog |
| GET | `/api/challenges` | List challenges (filterable) |
| GET | `/api/challenges/<id>` | Get challenge |
| POST | `/api/challenges/<id>/publish` | Publish challenge |
| DELETE | `/api/challenges/<id>` | Soft-delete challenge |
| GET | `/api/challenges/meta/options` | Valid enum values |
| GET | `/api/challenges/<id>/candidates` | Ranked candidates for challenge (sort_by/order) |
| POST | `/api/submit-with-files/<link_id>` | Submit workspace files for evaluation |
| GET | `/api/submission/<id_or_link>` | Get submission + evaluation results |
| GET | `/api/submissions` | List all submissions |
| POST | `/api/submissions/<id>/flag` | Flag submission for manual review |
| POST | `/api/submissions/<id>/override` | Apply human override to AI recommendation |
| GET | `/api/analytics/overrides` | Override calibration analytics |
| GET | `/student/<link_id>` | Student assessment workspace |
