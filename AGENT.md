# AGENT.md — Session Continuity File
> Read this at the start of every session before doing anything else.
> Updated automatically as work progresses.

---

## What This Project Is

**AI Hire-Readiness Evaluation Platform** — employers post coding challenges, candidates complete them in isolated Docker containers with browser-based VS Code + Claude API access. The platform evaluates candidates across **8 AI-collaboration dimensions** and produces a hire recommendation (strong_hire / hire / select / pass) with a side-by-side candidate comparison view.

This is NOT an educational platform. It is a **hiring tool** for employers to evaluate AI-assisted coding competency.

---

## Key Product Decisions (from Party Mode session 2026-06-30)

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

- **Guarded vs Unguarded mode**: Unguarded = Claude can give full solutions (employer assesses HOW candidate uses AI). Guarded = Claude restricted to guidance only.

- **Challenge types**: `bug_fix | feature_extension | refactoring | optimization`
- **Skill areas**: `api_integration | rate_limiting | data_pipeline | llm_usage | server_monitoring | game_logic`

- **AI Beta transparency**: Always show banner to employers — "AI scoring is experimental. Human judgment holds final authority."

---

## Current Implementation State (~60% complete)

### ✅ Done
| Area | Files |
|---|---|
| Flask REST API backbone | `app/__init__.py`, `run.py` |
| SQLite schema (5 tables) | `app/services/database_service.py` → assignments, session_links, submissions, submission_files, session_logs |
| Docker container lifecycle | `app/services/docker_service.py` |
| Session log parsing | `app/services/session_log_service.py` |
| Basic evaluation (40/30/30 hardcoded) | `app/services/evaluation_service.py` |
| File extraction from container (3 files only) | `app/routes/submissions.py` + `docker_service.py` |
| Basic challenge generation | `app/routes/challenges.py` + `evaluation_service.py:generate_challenge()` |
| Teacher dashboard | `templates/frontend.html` |
| Student workspace (dynamic HTML + code-server iframe) | `app/routes/student.py` |
| System health / management endpoints | `app/routes/management.py` + `app/services/management_service.py` |
| Background evaluation thread | `app/routes/submissions.py` |

### ❌ Not Built Yet
- 8-dimension scoring engine (currently hardcoded 40/30/30)
- `challenges` catalog table + catalog endpoints
- `dimension_scores` table, `hire_evaluations` table, `comparison_sessions` table
- Challenge types / skill areas / ai_assistance_mode in schema and prompts
- Full workspace snapshot (currently only solution.py, instructions.md, claude_session.log)
- Candidate comparison endpoint
- Hire recommendation (strong_hire/hire/select/pass)
- Human override + flag for manual review
- Visibility floor enforcement
- AI Beta banner
- Employer dashboard with radar charts and comparison view
- Preview as Student
- Guarded mode Claude restrictions
- Verification nudge before submission
- Unit tests

### Known Bugs (Epic 1 — fix before adding features)
| Bug | File | Line | Status |
|---|---|---|---|
| `container_created_at` always None — queried wrong table | `app/routes/submissions.py` | 42-46 | ✅ Fixed 2026-06-30 |
| `container_id` not passed into evaluation pipeline | `app/routes/submissions.py` + `evaluation_service.py` | 13, 159 | ✅ Fixed 2026-06-30 |
| Score not clamped — could exceed 100 | `app/services/evaluation_service.py` | combined_score line | ✅ Fixed 2026-06-30 |

---

## Epics & Stories (full spec)

Full specification saved at:
`_bmad-output/planning-artifacts/epics-and-stories.md`

---

## Current Priority — Phase 1: Challenge Creation → Assessment Scoring

Build order: **Epic 1 (bugs) → Epic 3 (challenge catalog) → Epic 2 (8-dim scoring)**

### Epic 1 — Bug Fixes ✅ COMPLETE (2026-06-30)
- [x] Story 1.1 — Fix efficiency score bug — `submissions.py:evaluate_submission_files()` now queries `submissions` table for `link_id` instead of `submission_files`
- [x] Story 1.2 — Pass `container_id` into evaluation pipeline — added to `evaluate_submission_files()` signature and thread call; `EvaluationService.evaluate_code()` signature updated
- [x] Story 1.3 — Score bounds clamp — `min(100.0, max(0.0, ...))` added to combined score calculation in `evaluation_service.py`

### Epic 3 — Market-Aligned Challenge System ✅ COMPLETE (2026-06-30)
- [x] Story 3.1 — `challenges` table added to `app/models/database.py` `init_db()` — 12 columns, idempotent
- [x] Story 3.2 — `POST /api/generate-challenge` now accepts `challenge_type`, `skill_area`, `ai_assistance_mode` with enum validation (400 on invalid)
- [x] Story 3.3 — `EvaluationService.generate_challenge()` fully rewritten — market-aligned prompt, per-type scaffolding instructions, per-skill-area imports, mode-aware instructions, 3000 max tokens
- [x] Story 3.4 — Generated challenges auto-persisted to `challenges` table as unpublished; `challenge_id` returned in response
- [x] Story 3.5 — Catalog endpoints: `GET /api/challenges` (filterable), `GET /api/challenges/<id>`, `POST /api/challenges/<id>/publish`, `DELETE /api/challenges/<id>`, `GET /api/challenges/meta/options`
- [x] DB methods added to `database_service.py`: `create_challenge`, `get_challenge`, `list_challenges`, `publish_challenge`, `unpublish_challenge`

### Epic 2 — 8-Dimension Scoring Engine ✅ COMPLETE (2026-07-01)
- [x] Story 2.1 — `dimension_scores` + `hire_evaluations` tables added to `app/models/database.py`
- [x] Story 2.2 — `EvaluationService.extract_container_files()` — full `/workspace` snapshot via Docker tar archive, 50KB cap, graceful `{}` fallback; called in `submit_with_files()` before container cleanup
- [x] Story 2.3 — `EvaluationService.score_8_dimensions()` — single Claude call with full rubric; all 8 dimension keys guaranteed even on parse failure
- [x] Story 2.4 — Python-enforced thresholds in `score_8_dimensions()`: strong_hire≥85, hire≥70, select≥55, pass<55; Claude's threshold ignored
- [x] Story 2.5 — `evaluate_submission_files()` persists per-dimension rows to `dimension_scores` table and verdict to `hire_evaluations` table; DB methods in `database_service.py`
- [x] Story 2.6 — `GET /api/submission/<id>` now returns `dimensions` (dict of 8) and `hire_evaluation` (composite_score, recommendation, rationale, weights snapshot)

### ✅ Phase 1 Complete — All 3 Epics + Frontend Done (2026-07-01)

**End state:** Teacher generates a market-aligned challenge (bug_fix/feature_extension/refactoring/optimization × skill area) → saves to catalog → creates assignment → Student takes assessment in Docker container with Claude → On submission, full workspace extracted, 8-dimension score computed, hire recommendation (strong_hire/hire/select/pass) returned. All features visible in updated employer dashboard.

**Frontend (`templates/frontend.html`) covers:**
- Tab 1 — Generate Challenge: type/skill/mode dropdowns, Publish to Catalog button, Save as Assignment button
- Tab 2 — Challenge Catalog: filter grid, click-to-create-assignment flow
- Tab 3 — Student Link: assignment list, link generation
- Tab 4 — Results: hire badge (strong_hire/hire/select/pass color-coded), composite score, 8-spoke SVG radar chart, dimension breakdown table with bar scores + rationales
- Tab 5 — Compare Candidates: ranked table with per-dimension mini scores, cohort averages bars
- AI Beta transparency banner (dismissible)

---

## Phase 1 Integration Fixes — (2026-07-02)

End-to-end testing revealed and fixed 4 infrastructure bugs. No stories changed; these were gaps between spec and running system.

### Fix 1 — LLM provider: Anthropic → OpenRouter
- Added `app/services/llm_service.py` — thin 35-line wrapper around `openai` SDK pointed at OpenRouter (`https://openrouter.ai/api/v1`)
- `LLMService.chat(prompt, max_tokens)` is the single call site; model switchable via `OPENROUTER_MODEL` env var
- `httpx.Client(verify=False)` bypasses SSL cert issues on restricted networks
- Replaced all `anthropic` SDK calls in `evaluation_service.py` and `management_service.py`
- `app/config.py` updated: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL` (removed `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`)
- `requirements.txt`: added `openai>=1.0.0`, `flask-cors>=4.0.0`

### Fix 2 — CORS error on API calls
- `app/__init__.py`: added `flask-cors` → `CORS(app)` after app creation
- Frontend: changed all hardcoded `http://localhost:8000/api` URLs to relative `/api` path
- Root cause: browser blocked cross-origin fetch from `http://127.0.0.1:8000` to `http://localhost:8000`

### Fix 3 — Docker SDK incompatible with Python 3.14
- `docker==7.0.0` throws `URLSchemeUnknown: http+docker` with `requests>=2.32` on Python 3.14
- Rewrote `app/services/docker_service.py` entirely using `subprocess` calls to the `docker` CLI
- No SDK version dependencies; works identically across OS/Python versions
- `docker/Dockerfile` fixed: added `USER root` before `apt-get`, `USER coder` before `CMD`

### Fix 4 — Student workspace not populated
- **Problem:** Containers started empty — no `instructions.md`, no `solution.py`
- **Fix:** Added `DockerService.inject_workspace_files()` called in `links.py` immediately after container creation
- Waits 2s for container filesystem to settle, then `docker cp` both files in
- `instructions.md` — Story 6.1 three-panel format: Scenario / Your Task / Evaluation Criteria
- `solution.py` — AI-generated starter code from the assignment (stub fallback if empty)
- **Bug in fix:** `→` (U+2192) in print statement after `instructions.md` copy raised `UnicodeEncodeError` on Windows cp1252 console, silently aborting before `solution.py` was copied. Fixed by replacing with ASCII.

### Fix 5 — Student page iframe not loading
- **Root cause 1:** Port 6000 is Chrome's hard-blocked list (X11). Changed `DOCKER_PORT_RANGE_START` from 6000 to 7100 in `app/config.py`
- **Root cause 2:** `sandbox` attribute on iframe blocked service workers that code-server relies on. Removed sandbox entirely.
- **Root cause 3:** iframe loaded immediately at page render before code-server was warm. Now deferred: `startAssessment()` shows a spinner, polls `fetch(vscode_url, {mode:'no-cors'})` every 1.5s until code-server responds (45s timeout), then sets `iframe.src` and transitions to assessment screen.
- Added warmup screen (`#warmup` div) between landing and assessment screens in `app/routes/student.py`

### Deferred to Phase 2
- Epic 4 — Human override UI + flag for review
- Epic 5 — Advanced employer UI (butterfly chart, side-by-side radar overlay)
- Epic 6 — Student UX (structured panels, verification nudge, real polling, Preview as Student, guarded mode enforcement)
- Epic 7 — Unit tests
- Story 1.4 — Replace print() with logging module
- Story 3.6 — Seed 10 curated challenges

---

## Key File Locations

| Purpose | Path |
|---|---|
| Epics & Stories | `_bmad-output/planning-artifacts/epics-and-stories.md` |
| This file | `AGENT.md` |
| Main config | `app/config.py` |
| DB schema / init | `app/services/database_service.py` |
| Evaluation + challenge gen | `app/services/evaluation_service.py` |
| Session log parsing + scoring | `app/services/session_log_service.py` |
| Submission routes (bug fixes applied) | `app/routes/submissions.py` |
| Challenge routes | `app/routes/challenges.py` |
| Teacher dashboard | `templates/frontend.html` |
| Student workspace | `app/routes/student.py` (dynamic HTML) |

---

## Architecture Constraints to Remember

- **SQLite only** — no Postgres, no Redis despite requirements.txt listing them
- **LLM via OpenRouter** — `LLMService` in `app/services/llm_service.py`; model set via `OPENROUTER_MODEL` env var (default `anthropic/claude-haiku-4-5`). Do NOT use `anthropic` SDK directly.
- **Docker via subprocess CLI** — `docker` Python SDK incompatible with requests≥2.32 on Python 3.14. All Docker ops go through `DockerService` in `docker_service.py` using `subprocess`.
- **Container port range: 7100–7900** — ports below 7000 (esp. 6000–6007) are Chrome-blocked. Never go below 7100.
- **Workspace injection is blocking** — `inject_workspace_files()` sleeps 2s then runs `docker cp`. Link generation takes ~3–4s total. This is intentional.
- **No `→` or non-ASCII in print() on Windows** — Windows console defaults to cp1252; Unicode arrows in print raise `UnicodeEncodeError` silently caught by outer except, aborting subsequent steps. Use ASCII only in print/log strings.
- **Score thresholds must be Python-enforced** — never rely on Claude's own threshold logic
- **Visibility floor** — score affects rank only, never hides candidates from comparison view
- **Docker file extraction** — must return `{}` gracefully when Docker unavailable, never block evaluation
- **iframe must not use sandbox** — code-server uses service workers; sandbox blocks them. Use `allow=` permissions attribute only.

---

## How to Update This File

After completing each story, update:
1. The bug table (mark ✅ Fixed)
2. The checkbox list under Current Priority
3. Add any new architecture decisions or constraints discovered during implementation
