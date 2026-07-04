# AGENT.md — Session Continuity File
> Read this at the start of every session before doing anything else.
> Updated automatically as work progresses.

---

## What This Project Is

**AI Hire-Readiness Evaluation Platform** — employers post coding challenges, candidates complete them in isolated Docker containers with browser-based VS Code + Gemini API access. The platform evaluates candidates across **8 AI-collaboration dimensions** and produces a hire recommendation (strong_hire / hire / select / pass) with a side-by-side candidate comparison view.

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
  - Thresholds enforced in Python — never trust Gemini's threshold determination alone

- **Human override policy**: AI scores inform, never decide. Employers can flag/override any score. Every override logged as calibration data. Visibility floor — score affects rank, never hides candidates.

- **Guarded vs Unguarded mode**: Unguarded = Gemini can give full solutions. Guarded = Gemini restricted to guidance only.

- **Challenge types**: `bug_fix | feature_extension | refactoring | optimization`
- **Skill areas**: `api_integration | rate_limiting | data_pipeline | llm_usage | server_monitoring | game_logic`

---

## Current Implementation State (100% of planned sprint complete)

### ✅ Done — Epics 1–7 + Phase 1 integration fixes (entire sprint complete as of 2026-07-03)

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

#### Epic 5 — Employer Dashboard UI Overhaul (done 2026-07-02)
- Story 5.3 (Side-by-Side Comparison View) — overlaid radar + butterfly chart + rationale panels in Tab 5; code review complete, 4 issues fixed

#### Epic 6 — Student Experience & Preview as Student (done 2026-07-03)
- Story 6.1 — structured challenge display: `instructions.md` injected with Scenario / Your Task / Evaluation Criteria three-panel format
- Story 6.2 — verification nudge before submission; wording trimmed to exact spec after code review
- Story 6.3 — real polling: `startPolling()` in `student.py` hits `GET /api/submission/<id>` every 3s until `evaluated_at` set, 60s timeout; composite_score falsy-fallback fixed (0-score edge case)
- Story 6.4 — `GET /student/preview/<challenge_id>` preview route (no Docker); review fixed hire_data/hire_evaluation key mismatch, unescaped rec label, NaN guard, missing-submissionId guard. AC3 reworded: challenge-template preview, not assignment-fidelity
- Story 6.5 — guarded mode: `inject_workspace_files()` writes `/workspace/CLAUDE.md` for guarded challenges; `links.py` resolves `ai_assistance_mode` via `challenge_id`. Smoke-tested end-to-end through real containers. Guarded mode is honor-system-only (accepted v1 scope). chmod-skip-on-CLAUDE.md-failure bug fixed

#### Epic 7 — Test Coverage (done 2026-07-03)
- Story 7.1 — `tests/test_score_8_dimensions.py` (12 tests): all-8-keys guarantee, Python-weighted composite vs plain mean, Claude-supplied composite/recommendation overridden, failure safety, ```json fence stripping. Found: fence-stripping only handles the exact ```json prefix
- Story 7.2 — `tests/test_extract_container_files.py` (16 tests): Docker unavailable → `{}`, text-only filter, 50KB cap + truncation boundaries, symlinks/dotfiles excluded. Found: `workspace` param ignored by path normalization; cap counts raw bytes but stores decoded text
- Story 7.3 — `tests/test_hire_recommendation_thresholds.py` (10 tests): all 4 threshold boundaries (85/70/55) probed from both sides via a uniform-score trick, plus a non-uniform real-weighting boundary check. Found: `hire_recommendation` branches on pre-round composite while `composite_score` stores post-round — the two can visibly disagree near a boundary
- Story 7.4 — `tests/test_candidates_endpoint.py` (13 tests, first integration test): real Flask test client + isolated SQLite. **Found and fixed a real DB-pollution hazard**: `app.routes.challenges.db_service` is an import-time singleton pointed at the real `data/assignments.db`, completely independent of `create_app(config_name)` — both the blueprint singleton and `create_app()`'s own internal schema-init call had to be neutralized (monkeypatch + `create_app("testing")`). Zero production gaps found
- Story 7.5 — `tests/test_generate_challenge_endpoint.py` (13 tests): combines 7.1's LLM-mock + 7.4's DB-isolation patterns for `POST /api/generate-challenge`. Found: non-string field values (e.g. `{"difficulty": null}`) crash with unhandled `AttributeError` instead of a clean 400 (confirmed empirically — the exception genuinely propagates under Flask's `TESTING=True`)
- **Total: 64 tests, root `conftest.py` bootstraps `sys.path`. All code-reviewed via 3-layer adversarial process (Blind Hunter + Edge Case Hunter + Acceptance Auditor) with patches applied and findings triaged into deferred-work.md.**

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

#### Phase 2 — LLM Provider Migration: OpenRouter/Claude → Gemini (done 2026-07-04)
- Backend: `app/services/llm_service.py` rewritten from an OpenAI-SDK-over-OpenRouter client to the `google-genai` SDK (`genai.Client` + `models.generate_content`). `LLMService.chat()`'s core signature (`prompt`, `max_tokens`) unchanged; gained an optional `response_schema` param in Story 8.2 below.
- Config: `app/config.py` — `OPENROUTER_API_KEY`/`OPENROUTER_MODEL`/`OPENROUTER_BASE_URL` replaced with `GEMINI_API_KEY`/`GEMINI_MODEL` (default `gemini-2.5-flash`).
- `.env` — `GEMINI_API_KEY` + `GEMINI_MODEL` set; unused `ANTHROPIC_API_KEY`/`OPENROUTER_*` entries removed.
- `requirements.txt` — `anthropic`/`openai` removed, `google-genai` added.
- Student container (`docker/Dockerfile.codeserver`): `@anthropic-ai/claude-code` → `@google/gemini-cli`; model pinned to `gemini-2.5-flash` via `~/.gemini/settings.json` + `GEMINI_MODEL` env var (same honor-system restriction pattern as before, not hard-enforced).
- `docker_service.py`'s `create_container()` now passes `GEMINI_API_KEY`/`GEMINI_MODEL` into the container at launch (`-e` flags) — previously no API key was wired into the container at all for Claude Code CLI, a pre-existing gap this migration also fixed.
- Guarded-mode context file renamed `CLAUDE.md` → `GEMINI.md` (Gemini CLI's auto-loaded context-file convention) in `inject_workspace_files()`.
- `session_log_service.py` / `submissions.py` — `interaction_type` default label `claude_cli` → `gemini_cli`; transcript keyword-matching updated.
- Docs updated: `CLAUDE.md` and this file — all "OpenRouter"/"Claude Code CLI"/"anthropic SDK" architecture-constraint language repointed to Gemini.
- Verified: real `GEMINI_API_KEY` confirmed valid against `generativelanguage.googleapis.com`; `@google/gemini-cli` confirmed to exist on npm; full pytest suite re-run (still passes — LLM calls are mocked at the `LLMService.chat` level so the provider swap is transparent to tests).

#### Epic 8, Story 8.1 — Pre-Authenticate Gemini CLI in Student Container (done 2026-07-04)
- Found: Phase 2's own verification used headless mode (`gemini -p "..."`), which works fine with just `GEMINI_API_KEY`. But **interactive** mode — what a candidate actually gets typing `gemini` in the code-server terminal — shows a "choose your authentication method" picker on first launch even with `GEMINI_API_KEY` set, unless an auth method is already recorded in `~/.gemini/settings.json`.
- Fixed: added `"security": {"auth": {"selectedType": "gemini-api-key"}}` to the baked-in `~/.gemini/settings.json` in `docker/Dockerfile.codeserver`, sourced directly from the installed CLI's own bundled `reference/configuration.md` (version-matched, not the public website). Rebuilt the image and verified: settings.json parses with no error, headless mode still returns correct output.
- Also independently re-verified guarded/unguarded AI-assistance mode still works correctly on Gemini CLI post-migration: with `/workspace/GEMINI.md` present, Gemini CLI explicitly declines to output complete solution code ("Under the guarded assessment rules of this session, I cannot provide a complete, working code block...") and gives conceptual guidance instead; with no `GEMINI.md`, it gives a complete working solution. No code change needed for this part — verification only.
- Full details: `_bmad-output/implementation-artifacts/8-1-pre-authenticate-gemini-cli-in-student-container.md`.
- Residual gap: the interactive-picker-before-fix / no-picker-after-fix behavior could not be captured via automated tooling in this session (ink-based TUI doesn't render reliably through `docker exec -t` without a genuine attached terminal). Recommend one manual pass through the real candidate flow (open the code-server terminal in a browser, type `gemini`) to close this out completely.

#### Epic 8, Story 8.2 — Fix Gemini JSON Response Reliability (done 2026-07-04)
- Found: a live user hit `Failed to parse Gemini response as JSON: Unterminated string starting at: line 5 column 19 (char 1234)` on the real "Generate with AI" flow. Root-caused to **two distinct bugs**, not one:
  1. Thinking tokens (gemini-2.5-flash+ is a "thinking" model) draw from the same `max_output_tokens` budget as the visible reply — a long-enough internal reasoning pass silently truncates the JSON before the closing brace. Fixed via `thinking_config=types.ThinkingConfig(thinking_budget=0)`.
  2. Even with thinking disabled and `response_mime_type='application/json'` set, the model could still emit a raw unescaped literal newline inside the `starter_code` string value (a full multi-line Python file embedded as JSON) — illegal per the JSON spec, breaks `json.loads()`. Reproduced this failure twice independently on the same `easy/bug_fix/game_logic` parameter combination, confirming `response_mime_type` alone isn't sufficient.
- Fixed: added an optional `response_schema` param to `LLMService.chat()` — Gemini's true structured-output/constrained-decoding schema, not just the mimetype hint. `EvaluationService` now has `_CHALLENGE_RESPONSE_SCHEMA` and `_SCORING_RESPONSE_SCHEMA` class-level dicts, passed into `generate_challenge()` and `score_8_dimensions()` respectively.
- Verified: 22 live calls (14 direct SDK repro + 8 through the real `generate_challenge()` code path, including 3 repeats of the specific combination that failed before) — 0 failures post-fix. Full pytest suite unchanged at 64/64 (mocks use flexible `lambda *args, **kwargs` signatures, unaffected by the new optional param).
- Full details: `_bmad-output/implementation-artifacts/8-2-fix-gemini-json-response-reliability.md`.

#### Epic 8, Story 8.3 — Fix `/ide install` "VS Code CLI not found" (done 2026-07-04)
- Found: while confirming Story 8.1's auth fix live, a user ran `/ide install` inside the real interactive `gemini` session in a code-server terminal and got `VS Code CLI not found. Please ensure 'code' is in your system's PATH.`
- Root-caused via the installed CLI's own bundled source (`VsCodeInstaller` class): `/ide install` hardcodes a search for a binary literally named `code` — code-server only ships `code-server`, never `code`. Confirmed `code-server --help` supports the identical `--install-extension <id> --force` flags the installer invokes.
- Fixed: `RUN ln -sf /usr/bin/code-server /usr/local/bin/code` added to `docker/Dockerfile.codeserver`.
- Verified: rebuilt the image; `code --install-extension google.gemini-cli-vscode-ide-companion --force` succeeded (not just that the binary resolves) as both `root` and the real runtime user `coder`; no regression to headless `gemini -p ...` or the pytest suite.
- Full details: `_bmad-output/implementation-artifacts/8-3-fix-ide-install-code-cli-not-found.md`.

#### Epic 8, Story 8.4 — Retry on Gemini JSON Parse Failure (done 2026-07-04)
- Found: a user hit the **exact same error** Story 8.2 fixed — `Failed to parse Gemini response as JSON: Unterminated string starting at: line 5 column 19 (char 1234)` — a second time, after that fix was already live.
- Ruled out two false leads before touching code: (1) stale server process — `curl`'d the actual live running server directly and it succeeded, proving Story 8.2's fix genuinely was deployed and loaded; (2) reverted fix — `grep` confirmed `response_schema`/`thinking_config`/`response_mime_type` all still present on disk, and a fresh Python process succeeded 8/8 across varied parameters.
- Conclusion: `response_schema` reduces the malformed-JSON rate a great deal (Story 8.2's 22/22, this story's own 8/8 and 5/5) but doesn't reduce it to zero — it's probabilistic, not a guarantee, for long code-heavy string fields.
- Fixed: added `EvaluationService._call_llm_for_json()`, a shared helper used by both `generate_challenge()` and `score_8_dimensions()`, retrying up to 3 times **only** on `json.JSONDecodeError`/validation `ValueError` — never on a genuine `LLMService.chat()` exception (network/API error), which still propagates on the first attempt. This distinction matters: an existing test asserts `LLMService.chat` is called exactly once when the provider is down, and blindly retrying that case would both break the test and add pointless latency to an unretryable failure.
- Verified: a mocked "fails twice then succeeds" scenario recovers correctly on attempt 3; full pytest suite unchanged at 64/64 including the exact-call-count assertion; additional live stress runs (8/8, 5/5) against the real API post-fix.
- Full details: `_bmad-output/implementation-artifacts/8-4-retry-on-gemini-json-parse-failure.md`.

---

### ❌ Not Built Yet (backlog)

**None.** Every story in `sprint-status.yaml` (Epics 1-7) is `done`. The sprint is complete.

Known gaps are tracked in `_bmad-output/implementation-artifacts/deferred-work.md`, not as backlog stories — see "Notable open production gaps" below.

---

## Next Session — Start Here

**Workflow state: the entire sprint is `done`.** All 7 epics, all stories in `sprint-status.yaml`, are `done` as of 2026-07-03. There is no `ready-for-dev` or `in-progress` story anywhere.

**Next action:** There is no next story to auto-discover. Options for a future session:
1. Run `/bmad-correct-course` or talk to the PM agent to scope a Phase 2 / new epic if there's new product direction.
2. Pick up one of the deferred production gaps below as a new story (each is a real, confirmed issue, not speculative).
3. Run retrospectives (`epic-1-retrospective` through `epic-7-retrospective` are all `optional`, none done yet) if a look-back is wanted.
4. Nothing is blocking — the codebase is in a clean, fully-tested, fully-committed state.

**Notable open production gaps** (all logged in detail in `deferred-work.md`, none fixed — each was found during Epic 7's test-writing and deliberately left as "test documents current behavior, doesn't fix it" per each story's scope):
- `score_8_dimensions()` fence-stripping only handles the exact ` ```json ` prefix — a bare ` ``` ` fence or prose-wrapped JSON from the LLM silently zero-scores a real candidate (7.1) — **highest product impact of the group**
- `extract_container_files()` ignores its own `workspace` parameter when stripping path prefixes; its 50KB cap counts raw bytes but stores decoded text (7.2)
- `hire_recommendation` branches on the pre-round composite while `composite_score` stores the post-round value — the two can visibly disagree near a threshold, e.g. a stored `85.0` labeled `"hire"` (7.3)
- `POST /api/generate-challenge` returns 200 even when catalog persistence silently fails, with no `persisted` field for the client to detect it (7.5)
- `POST /api/generate-challenge` (and likely sibling routes) crash with an unhandled `AttributeError` on non-string JSON field values (e.g. `{"difficulty": null}`) instead of a clean 400 (7.5)
- Guarded mode (`ai_assistance_mode='guarded'`) is honor-system-only — a candidate with shell access can delete/edit the injected `GEMINI.md` (6.5), accepted as v1 scope

**Housekeeping note:** Story 7.4 introduced a harmless side-effect file `data/test_assignments.db` (created by `create_app("testing")`'s own schema init) — not a bug, expected from `TestingConfig`, safe to delete or ignore.

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
| LLM wrapper (Gemini) | `app/services/llm_service.py` |
| Submission routes | `app/routes/submissions.py` |
| Challenge routes | `app/routes/challenges.py` |
| Analytics routes | `app/routes/analytics.py` |
| Teacher dashboard | `templates/frontend.html` |
| Student workspace | `app/routes/student.py` |

---

## Architecture Constraints — Read Before Writing Any Code

- **SQLite only** — no Postgres, no Redis. Raw SQL, no ORM. `CREATE TABLE IF NOT EXISTS` is the migration strategy; `ALTER TABLE` via `try/except sqlite3.OperationalError` (not bare `except Exception`).
- **LLM via Gemini** — `LLMService` in `app/services/llm_service.py`; model via `GEMINI_MODEL` env var. Do NOT use the `google-genai` SDK directly outside `llm_service.py`.
- **Docker via subprocess CLI** — `docker` Python SDK incompatible with requests≥2.32 on Python 3.14. All Docker ops go through `DockerService` in `docker_service.py`.
- **Container port range: 7100–7900** — ports below 7000 (esp. 6000–6007) are Chrome-blocked.
- **No non-ASCII in `print()` on Windows** — cp1252 console; Unicode arrows silently abort execution. ASCII only in print/log strings.
- **Score thresholds: Python-enforced** — `strong_hire>=85, hire>=70, select>=55, pass<55`. Never rely on Claude's threshold logic.
- **Visibility floor** — score affects rank only, never hides candidates. Un-evaluated candidates sort last (math.inf sentinel).
- **`score_overrides` is append-only** — every override inserts a new row. Never UPDATE or DELETE from it.
- **`hire_evaluations.composite_score` and `.recommendation` are read-only after creation** — override only writes `is_overridden`, `override_recommendation`, `override_rationale`.
- **`dim_averages` uses `is_evaluated` filter, not dict truthiness** — and skips None scores (no zero-default).
- **No sandbox on student iframe** — code-server uses service workers; sandbox blocks them.
- **Guarded mode is honor-system-only (v1)** — enforced via `/workspace/GEMINI.md` injection; students can delete/edit it. Accepted scope; hard enforcement deferred.
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
| GET | `/student/preview/<challenge_id>` | Employer preview of student view (no Docker, no submission) |
