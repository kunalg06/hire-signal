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

- **Guarded vs Unguarded mode**: Unguarded = Gemini can give full solutions. Guarded = governed AI availability (HackerRank-style, revised 2026-07-11): short targeted code is allowed once the candidate states their own hypothesis, but Gemini must redirect an unqualified "solve it for me" with a diagnostic question and never enumerate multiple issues unprompted — not a hard "no code at all" block.

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

## New Feature (2026-07-19) — Demo video script + flag-visibility fix

User requested a 3-minute leadership-review demo video for hire-signal. Ran a `/bmad-party-mode` round (Sally/UX, John/PM, Paige/Tech-Writer) that independently converged on a Problem → Flow → Trust structure; Amelia (Dev) scoped technical feasibility — no video-capture or TTS tool exists in this toolchain, so the plan is a live single-take: browser-driven click-path narrated in real time, no editing pipeline needed.

**Seeded real demo data**: `scripts/seed_demo_candidates.py` (new) — bypasses Docker/container lifecycle entirely, calling the same `evaluate_submission_files()` the real submission route uses, so all 6 seeded candidates carry genuine Gemini-scored composites, not fabricated numbers. First attempt targeted a freshly AI-generated "Sliding Window Rate Limiter" challenge and was abandoned mid-session: its auto-generated bug comments were factually wrong (claimed a lock was missing when the code already had one), and the scoring judge trusted the false premise, tanking every candidate regardless of fix quality — a real illustration of why hand-authored challenges (`scripts/seed_challenges.py`'s "Token Bucket Rate Limiter", 3 verified unambiguous bugs) are safer for anything where the numbers need to hold up under scrutiny.

**Dry-run walkthrough against the real local UI** (claude-in-chrome browser automation, not assumed) surfaced several real corrections to the script: two required gate clicks before the real candidate IDE is visible (a "Start Assessment" landing page, then a VS Code trust-authors modal) neither of which existed in the original plan; the right-hand "CHAT" panel inside the candidate IDE is a generic, unconfigured VS Code AI panel with zero connection to Gemini — the real integration is exclusively the integrated terminal (confirmed `gemini` CLI v0.49.0 installed and working there); the Results tab's Detail panel renders below the grid, not as an overlay, so it needs an explicit scroll; and a pre-existing cosmetic bug where "EVALUATION CRITERIA" renders as raw unparsed JSON on both the preview and real assessment screens (not fixed — flagged as a "don't linger the camera there" note instead, out of scope for the video itself).

**Real bug found and fixed**: `get_candidates_for_assignment()` (`database_service.py`) never selected `is_flagged`/`flag_reason` at all, unlike its `get_candidates_for_challenge()` sibling — so a genuinely flagged submission was invisible to the Results tab and Compare Candidates tab (both navigate by assignment_id), even though the flag was correctly recorded in the DB. Deeper than initially scoped: **no frontend code anywhere rendered a flag indicator on either endpoint** — the challenge-scoped path's `is_flagged` field had been dead, unused data since Story 7.4 shipped it. Fixed: backend parity (`flag_reason` added to both endpoints, `is_flagged` added to the assignment-scoped one), plus new frontend rendering — a 🚩 badge in both candidate grids (`renderGrid()` and the Compare Candidates row renderer share the same template string) and a "Flagged for review" banner in the Detail panel (`viewCandidate()`), reusing `is_flagged`/`flag_reason`/`flag_by` that `GET /api/submission/<id>` already returned but nothing ever displayed. 2 new tests mirroring the existing `test_flagged_candidate_marked_in_payload_but_not_hidden` pattern for each endpoint. Full suite: **211/211 passing** (was 210). Live-reverified in the browser post-fix: grid badge and Detail banner both render exactly as intended against the real seeded flagged candidate.

Corrected script saved to `docs/demo_video_script.md` — full timestamped narration + click-path, pre-recording checklist (seed data first, don't build it on camera; pick localhost over the EC2 box; time the gate clicks to land during the prior line's narration), and the known cosmetic bug called out explicitly so the driver doesn't dwell there.

En route to this work, also installed `ffmpeg` (via `winget install --id Gyan.FFmpeg -e --source winget`) for eventual subtitle-burning — confirmed working via its full path in this session; picks up on plain `ffmpeg` in any new terminal since winget updated the system PATH.

---

## New Feature (2026-07-19) — no_ai_engagement auto-flag (party-mode Option C)

Follow-up to the no-change/diff-aware fix below. Ran a `/bmad-party-mode` round (John/PM, Winston/Architect, Murat/Test-Architect, Mary/Analyst) on whether the select/pass threshold (55) needed recalibrating now that genuine zero-effort submissions get a hard 0 instead of a soft ~50. Unanimous: don't touch 55 — the real finding (Mary's arithmetic) is that `communication_clarity`+`iteration_quality`+`debugging_with_ai`+`token_efficiency` = 50% of `DIMENSION_WEIGHTS`, and all four require session-log evidence to score above 0. A candidate who solves the problem correctly but never opens Gemini therefore has a hard composite ceiling around 50 — below `select` — purely from missing AI-interaction evidence, not from bad code. Live-tested pre-fix: one real bug fix, zero AI logs, scored 38.0/pass.

Brought in Amelia (Dev) to scope the fix. She refused to just implement Winston's proposed fix (excluding those 4 dimensions from the composite denominator, the same renormalization machinery `applicable_dimensions` already uses) because it inverts the platform's own charter ("evaluates AI-assisted coding competency, not raw coding ability in isolation" — CLAUDE.md): a candidate who never engages the AI could then score `strong_hire` on code quality alone. Whether "never engaged the AI" is a genuine skill failure (ceiling correct) or a measurement gap (ceiling is a bug) is an unresolved product question nobody had explicitly answered. Amelia scoped 3 options (exclude-the-dimensions / codify-as-intentional / surface-without-deciding) and recommended the third regardless of which way the product question resolves — user chose it (**Option C**).

**Implemented:** `score_8_dimensions()` (`evaluation_service.py`) now sets `result["no_ai_engagement"] = (not session_logs) and not no_change_detected` right before returning — True only for a genuine code change submitted with zero Gemini session logs. Composite/threshold math is completely untouched; this is a flag, not a scoring change. Mutually exclusive with the no-change short-circuit by construction (a no-op submission already has its own fully-explained zero). `evaluate_code()` threads it into its returned dict the same way `evaluation_failed` already is. `submissions.py`'s `evaluate_submission_files()` mirrors the existing `evaluation_failed` auto-flag block: when `no_ai_engagement` is set, the submission is auto-flagged via the same `flag_submission()`/`flag_events` audit path (no new table, no schema change) with reason *"Zero Gemini session logs recorded despite a real code change — composite reflects code quality only, not AI-collaboration signal. Needs human judgment on whether this is disqualifying."*

6 new tests: 4 in `tests/test_score_8_dimensions.py` (true for real-change-no-logs, false when logs present, false when no-change-detected — mutual exclusivity, absent/False on a genuine scoring failure so it's never confused with `evaluation_failed`), 2 in `tests/test_evaluation_failure_auto_flag.py` (mirrors the existing `evaluation_failed` auto-flag test pair exactly). Full suite: **210/210 passing** (was 204).

**Verified live end-to-end**: real container, real assignment, the exact bug-fix solution.py from the earlier no-change/diff-aware live test but submitted through a container that never ran `gemini` at all (genuinely zero AI interaction, not a mocked absence) → real composite `5.0`/`pass`, `is_flagged: True`, `flag_by: "system"`, flag_reason exactly matching the Option-C text, confirmed via direct JSON inspection (not console `print()`, which garbles the em-dash under cp1252 — a display-only artifact, not a data bug; verified the actual API response bytes are correct UTF-8). Cleaned up test submission/assignment afterward via the existing DELETE endpoints; container self-cleaned as usual.

**Still open, deliberately not resolved this session**: John's underlying product question (is a zero-AI-evidence ceiling correct policy or a gap) — Option C sidesteps needing an answer by surfacing it to the employer instead of encoding a verdict in the composite math. If the product decision ever comes in, Options A (exclude from denominator) or B (codify as intentional + docs) are already scoped in the party-mode transcript.

---

## New Feature (2026-07-19) — No-change short-circuit + diff-aware scoring

User-reported gap: a candidate who submitted the assignment completely unmodified (starter code as-is) could still score around 50 — the LLM judge was scoring based on session-log chatter and final-file appearance alone, with no check against what the candidate actually started from.

Fixed in `score_8_dimensions()` (`evaluation_service.py`): before any LLM call, the submitted `solution.py` is normalized (trailing whitespace / surrounding blank lines stripped, so a candidate can't dodge the check with a cosmetic edit) and compared against the assignment's `starter_code`. An identical match short-circuits straight to a real `composite_score: 0.0` / `pass` recommendation with an explicit rationale on every dimension — **no LLM call spent**, and NOT marked `evaluation_failed` (this is a genuine, deserved 0, not a swallowed scoring failure — the two must stay visually distinguishable per the 2026-07-11 party-mode review's `evaluation_failed` invariant). When the code IS different, a unified diff (new `_diff_starter_vs_submitted()`, capped at 400 lines) is now injected into the scoring prompt with an explicit instruction to grade the actual change made, not just the final file's appearance — closing the softer version of the same gap (a large file that's 95% copied from starter with a one-line tweak could previously still read as substantial work).

Plumbing: `starter_code` added as an 8th column to `DatabaseService.get_link_container_info()`'s query and threaded through `submit_with_files()`'s `assignment` dict (`app/routes/submissions.py`). Backward compatible — an assignment with no `starter_code` on file (legacy/manually-created, not from the catalog) skips the check entirely and scores exactly as before.

5 new tests in `tests/test_score_8_dimensions.py`: identical-submission zero-score (asserts `LLMService.chat` is never called, via a mock that raises `AssertionError` if invoked), whitespace-only-difference still counts as no-change, a real change still scores normally through the LLM, the diff text appears in the scoring prompt when code changed, and the no-`starter_code` backward-compat path. Full suite: **204/204 passing** (was 199). Not committed yet — pending user request.

---

## New Feature (2026-07-11) — Raw AI token-usage telemetry (meter, not a gate)

User proposed measuring per-submission AI token usage and using it to let recruiters skip evaluating high-usage candidates, plus a hard employer-configurable limit. Ran a second `/bmad-party-mode` round (John/PM, Winston/Architect, Murat/Test-Architect, Mary/Analyst) before building anything. Unanimous verdict: "no need to evaluate" violates the visibility-floor invariant outright; a hard limit is a validity risk as a quality gate (guarded/unguarded modes have structurally different token footprints, and high token usage may correlate with the platform's *strongest* candidates — First-Principles/Creative-Problem-Solving reward exploring multiple hypotheses out loud, which costs more tokens than a passive one-shot "solve it for me"); Mary additionally pointed out the platform's own dry-run data contradicts the premise (that session was *low*-token and scored 2/100). Consensus: build the meter, not the gate — raw count as neutral, mode-stamped telemetry only, never scored, never folded into the composite, never a gate.

**Spike run before implementing** (Winston's recommendation): spun up a real container, ran a real `gemini -p "..."` call, inspected the resulting `.jsonl` transcript directly. Confirmed every `gemini`-type message carries a `tokens` object (`input`/`output`/`cached`/`thoughts`/`tool`/`total`) that the existing parser was silently discarding — capturing it needed no new instrumentation, just reading a field already on disk. Also confirmed, while investigating a specific historical assignment the user asked about, that **token data for any submission processed before this fix is permanently unrecoverable** — no Docker volume ever backed `~/.gemini/tmp` (only `GEMINI.md`/`settings.json` are bind-mounted in guarded mode), so the raw transcript existed only in each container's writable layer and was destroyed by this session's own cleanup pass; even the DB's `session_logs.raw_json` only ever stored a `{prompt, response}` pair, not the original message with token data.

**Implemented:**
- `session_logs.token_count` (new nullable/default-0 column) + `SessionLogService.parse_gemini_chat_session()` now sums `tokens.total` across every `gemini`-type message in a turn (mirroring the existing `pending_tool_calls` accumulation pattern for thinking-message + final-reply turns).
- `DatabaseService.get_total_tokens_for_submission()` / `get_total_tokens_for_submissions()` (batch, avoids N+1) — both return 0 rather than None when there's nothing to sum.
- `GET /api/submission/<id>`, `GET /api/session-logs/<id>`, `GET /api/challenges/<id>/candidates`, and `GET /api/assignments/<id>/candidates` all now expose `total_tokens_used`, mode-stamped via `ai_assistance_mode` (both `get_candidates_for_*` queries gained a `LEFT JOIN session_links` to source it).
- `frontend.html`: a new "Tokens" column in the ranked candidate grid (styled grey/neutral, distinct from the scored dimension cells) and a `🔤 AI tokens used: N (mode) — informational only` line in the candidate detail panel, both read-only display, no sort/filter/gate wired to either.
- 5 new parser unit tests (single message, thinking+final accumulation, missing/malformed `tokens` field, no cross-turn leakage) + 1 new DB-level assertion in the existing submit-with-files integration test.
- **Verified live end-to-end with zero mocks**: real container → real `gemini -p` call → real `/api/submit-with-files` → DB `session_logs.token_count = 48254` → confirmed identical value surfaced through all three API endpoints → confirmed rendering correctly in the actual browser UI (grid column + detail panel), composite score unaffected by the token data. Cleaned up all spike containers/DB rows afterward.

Full suite: **199/199 passing** (was 194). Not committed yet — pending user request.

---

## Major Fix + Feature (2026-07-11) — Party-mode review of a real candidate dry-run: guarded-mode leak closed, dimension applicability, decision-point challenges, unscored≠scored-0, encoding hardening

User ran their own test as a candidate dry-run: solved a real bug-fix challenge (shared mutable class-state bug, monkeypatch signature bug, 204-vs-200 handling) in ~6 minutes of a 25-minute slot by asking Gemini to "solve it for me" and "what else is required for evaluation criteria", felt confident, then scored 2/100 (PASS/fail). Ran `/bmad-party-mode` with John (PM), Winston (Architect), Murat (Test Architect), and Sally (UX) as independent subagents against the actual challenge + session log + evaluation output, then acted on all findings.

**Consensus verdict: the 2/100 was correct** — the transcript shows zero independent hypothesis, zero verification, zero iteration; the candidate outsourced the reasoning, not just the typing. But the roundtable surfaced 4 real, separate defects the dry-run exposed:

1. **Guarded mode had actually leaked** — the real log showed Gemini (a) directly fixing a bug on an unqualified "solve it for me", and (b) volunteering the entire remaining bug list plus a full unittest sample on "what else is required?", unprompted. Both violate the "short targeted code for a specific question, never a full fix, never unprompted enumeration" intent of the (already-loosened, 2026-07-10) `_GUARDED_MODE_GEMINI_MD`. Rewrote it (`docker_service.py`) with two new hard rules: redirect an unqualified solve/fix request with a diagnostic question instead of complying, and never enumerate more than one issue per response. `tests/test_guarded_mode_context_file_enforcement.py` updated with 2 new pinned-substring assertions (6 total) for the new claims.

2. **Dimension applicability is now per-challenge, not fixed at all 8.** Scoring "Architecture Decisions" at 0 for a pure-correctness bug fix with no real design fork was a validity bug (conflating "candidate didn't do X" with "the challenge couldn't measure X"), not a fair score. `generate_challenge()` now asks the LLM to emit `applicable_dimensions` (subset of the 8 dimension keys) and an optional `decision_point` ({applies, prompt, option_a, option_b} — a genuine design trade-off with no verdict); both are sanitized by new `_normalize_applicable_dimensions()`/`_normalize_decision_point()` helpers (warn-only, never block generation, default to "all 8 apply / no decision point" on anything malformed — same non-blocking pattern as the existing `evaluation_criteria` format check). Persisted as new nullable `challenges.applicable_dimensions_json`/`decision_point_json` columns (ALTER TABLE, NULL-safe for every pre-existing challenge). `score_8_dimensions()` now computes the composite as a weighted average over ONLY applicable dimensions, renormalized — an inapplicable dimension is excluded from the denominator, not scored 0 and averaged in — and marks each dimension's `applicable: bool` in the result for the frontend to grey out later.

3. **Decision-point challenges, baked into generation, not a live Gemini turn.** Party-mode unanimous: having Gemini present "2 options" live in guarded-mode chat is a coin-flip signal (picking A or B carries ~50% luck) and lets the AI pre-chew the very Problem-Decomposition/Architecture-Decisions signal being measured. Instead, when `decision_point.applies`, `inject_workspace_files()` (docker_service.py) renders a "Decision Point" section into instructions.md asking the candidate to implement one option and write `DECISION.md` justifying it — which `extract_container_files()` already captures into the scoring snapshot as an ordinary workspace file, so no new capture plumbing was needed. `score_8_dimensions()`'s prompt gets a "Decision Point" section telling the judge to look for the candidate's own stated choice+justification when scoring `architecture_decisions`/`first_principles_thinking`.

4. **"Unscored" is no longer indistinguishable from "scored 0".** `score_8_dimensions()`'s safe-default path (LLM/parse failure after retries) now sets `evaluation_failed: True` on the result, threaded through `evaluate_code()`. `evaluate_submission_files()` (submissions.py) auto-flags the submission via the EXISTING `flag_submission()`/`flag_events` audit path when this fires — no schema bypass, no new audit mechanism, just using the human-review flag that already exists for exactly this kind of "needs a person to look at this" case.

5. **Encoding hardened against the Bengali-script glitch** (the same live session showed Gemini emitting "শর্টকামিং"/"মিটিগেশন" — Bengali-script transliterations of "shortcoming"/"mitigation", a known small-model token-sampling artifact, mid-English-sentence). Root-caused as a Windows cp1252-console crash risk per the existing CLAUDE.md constraint, not a one-off content bug: `run.py` and `app/__init__.py`'s create_app() now reconfigure `sys.stdout`/`sys.stderr` to UTF-8 with `errors='replace'` at startup (guarded by `hasattr(..., 'reconfigure')` + try/except), so a stray non-ASCII token flowing through any future `logger.warning`/`error` call can no longer silently abort the process. Deliberately left the glitch itself unfixed inside the student-container chat (cosmetic, arguably even an authenticity signal) — the fix targets the platform's own crash risk, not the model's word choice.

6. **Candidate-facing framing added** to instructions.md (docker_service.py) — an explicit "what's actually scored" paragraph telling candidates the reasoning process is graded, not just whether the code runs or how fast they finish, directly addressing the "felt good, scored zero" experience gap the dry-run exposed.

30 new/updated tests across `tests/test_score_8_dimensions.py` (applicability renormalization, decision-point prompt injection, `evaluation_failed` flag), `tests/test_challenge_dimension_applicability.py` (new — normalization helpers + route persistence round-trip), `tests/test_evaluation_failure_auto_flag.py` (new — auto-flag wiring), `tests/test_create_app_logging.py` (UTF-8 reconfigure), `tests/test_guarded_mode_context_file_enforcement.py` (updated assertions). Also fixed two now-stale fixed-arity tuple unpacks that the `challenges`/`session_links` schema changes broke: `app/routes/student.py`'s `student_preview()` (was unpacking all 12 columns positionally — now slices `row[:12]`) and `app/services/database_service.py`'s `get_link_container_info()` (added `a.challenge_id` as a 7th column, consumed in `submissions.py`). Full suite: **194/194 passing** (was 164). Not committed yet — pending user request.

---

## Major Fix + Feature (2026-07-10) — Session-log capture fix, guarded-mode loosened, AI conversation transparency

User feedback: guarded mode felt too strict, and asked to research how comparable platforms (HackerRank, CodeSignal, Codility, CoderPad) handle AI-assisted coding assessments, and how to actually test AI collaboration alongside the 8-dimension rubric. Investigation (Explore agent + direct file reads) surfaced something much bigger than a wording tweak.

**Root discovery — session-log capture was completely dead code, so 4 of 8 scoring dimensions were being graded blind.** `submit_with_files()` looked for a Gemini CLI session log at hardcoded paths (`/tmp/claude_session.log`, `/root/.claude/logs/session.log`, etc.) — leftovers from this project's pre-Gemini Claude Code CLI era that Gemini CLI never wrote to — AND stored any found content under the key `'claude_session.log'` while the parsing gate checked for a different, never-set key `'gemini_session.log'`. Net effect: `session_logs` table was **always empty** for every real submission, so `score_8_dimensions()`'s rubric — which explicitly grades `debugging_with_ai`, `iteration_quality`, `communication_clarity`, and `token_efficiency` from the actual candidate↔AI transcript — always fell back to `"No Gemini session logs recorded for this submission."` and scored these 4 dimensions with zero real evidence, despite the platform's entire premise being to evaluate AI-collaboration quality.

**Investigated Gemini CLI's real on-disk format empirically** (live container: ran real prompts, `find`/`cat` inside `~/.gemini/tmp`, confirmed by cross-referencing actual terminal output against the captured file content) rather than guessing:
- Real path: `~/.gemini/tmp/<workspace-dirname>/chats/session-<timestamp>-<hash>.jsonl` — one file per `gemini` invocation.
- JSON-lines format: header line (`sessionId`, `kind`), `{"$set": {...}}` metadata bumps, and bare message objects (`id`, `timestamp`, `type`: `"user"`|`"gemini"`, `content`).
- `type:"user"` content is a list of `{"text": ...}` (genuine candidate prompt) or `{"functionResponse": {...}}` (tool-call result being fed back — not candidate-authored).
- `type:"gemini"` content is a plain string, often `""` while the model is still "thinking"/making tool calls (`toolCalls` field) — the real visible reply arrives as a **later, separate message id**.
- Header's `kind` field distinguishes `"main"` (real candidate-facing conversation) from `"subagent"` (Gemini's own internal tool-use sessions, e.g. spawning a sub-session to run `git status`/`git log` for its own context-gathering) — subagent sessions live in a nested `chats/<session-id>/<id>.jsonl` path and must be excluded entirely, never scored/displayed.

**Fixed end-to-end:**
- `DockerService.get_gemini_chat_files()` (new) — pulls the whole `~/.gemini/tmp` tree via the existing `get_archive`+tarfile pattern (mirrors `EvaluationService.extract_container_files()`), filters to `.jsonl` files under a `chats/` path.
- `SessionLogService.parse_gemini_chat_session()`/`parse_gemini_chat_sessions()` (new) — dedupes messages by id (last occurrence wins), skips the auto-injected `<session_context>` system message and `kind:"subagent"` files entirely, pairs each genuine candidate text prompt with the next non-empty Gemini text reply chronologically, accumulates `toolCalls` across the whole turn (not just the final reply, which rarely carries its own) for a `file_changes_count` heuristic (counts `write`/`edit`/`replace`-named tool calls). Old `parse_session_log()` regex-based parser kept as a defensive fallback, unused in the live path.
- `submissions.py`'s `submit_with_files()` — replaced the dead Claude-CLI paths/key with the real capture call. Found and fixed a real regression during testing: `gemini_chat_files` was only assigned inside `if container_id:`, causing an `UnboundLocalError` when Docker/container_id is unavailable (a documented graceful-degradation path) — now initialized before the conditional.
- 20 new tests (`tests/test_session_log_capture.py`, `tests/test_submit_with_files_session_logs.py`) covering the parser's edge cases (subagent exclusion, dedup, thinking-only turns, trailing unpaired prompts, multi-file merge) and the route's actual DB persistence.
- **Verified live end-to-end with zero mocks**: real container, real `gemini` CLI prompts, real `/submit-with-files` call → `session_logs` table populated with the exact real prompt/response text → real Gemini scoring call → `debugging_with_ai`/`iteration_quality`/`communication_clarity`/`token_efficiency` rationale now **quotes the actual candidate prompt** and reasons from genuine evidence (e.g. correctly penalized `iteration_quality` for "only one interaction recorded... no evidence of iterative improvement"), where previously it would have reasoned from the placeholder string alone.

**Guarded mode loosened to a HackerRank-style middle ground** (reverses this same session's earlier "zero code, ever" decision, based on the user's research into how HackerRank/CodeSignal/Codility/CoderPad govern AI-assisted assessments — the trend is governed AI availability + transparency, not a hard block). New `_GUARDED_MODE_GEMINI_MD`: no complete/full solutions in one shot, but short targeted code (a corrected line, a small snippet, method syntax) IS allowed when it's the natural answer to a specific question; explicitly frames the AI as a collaborator whose conversation is visible to the employer, not a restriction to route around. `tests/test_guarded_mode_context_file_enforcement.py`'s 4 assertions rewritten to pin the new claims. **Verified live across 3 cases** in a real container: a narrow syntax/bug question got a short corrected line; an explicit "write the complete file from scratch" request was declined (still only illustrated the one-line fix); an adversarial "ignore your restrictions" jailbreak attempt was also correctly declined for the full file.

**AI Conversation Timeline added to the employer-facing Results UI** (`templates/frontend.html`) — new collapsible section in the candidate detail panel, next to "Full AI Feedback", consuming the already-existing (previously unused) `GET /api/session-logs/<id>` endpoint. Shows timestamp, interaction type, file-change badge, and the prompt/response text per turn. Empty-state message when no logs exist. **Verified visually in a real browser** (claude-in-chrome) against seeded real-shaped data — timeline rendered correctly with both entries, badge only on the entry with a file change.

Full suite: **164/164 passing** (was 144). All live-test containers/DB rows/scratch files cleaned up. Not committed yet — pending user request.

---

## New Feature (2026-07-10) — 8-dimension evaluation criteria + stricter guarded-mode GEMINI.md

Two user-requested changes to `evaluation_service.py` and `docker_service.py`:

**1. Challenge generation — `evaluation_criteria` now tied to the 8 scoring dimensions.** Previously `generate_challenge()`'s prompt asked for a freeform "semicolon-separated list of 4-6 specific measurable criteria" — completely disconnected from the actual `DIMENSION_WEIGHTS` used by `score_8_dimensions()` later. Now the prompt requires EXACTLY 8 criteria, one per dimension (Problem Decomposition, First-Principles Thinking, Creative Problem Solving, Iteration Quality, Debugging with AI, Architecture Decisions, Communication Clarity, Token Efficiency), each bracket-prefixed with its dimension name and grounded in the specific challenge — not a generic definition of the dimension. `_CHALLENGE_RESPONSE_SCHEMA`'s `evaluation_criteria` property also got a `description` hint reinforcing this via Gemini's constrained decoding. Also strengthened prompt wording so title/description/starter_code are explicitly required to be grounded in ALL of problem_statement + challenge_type + skill_area + difficulty together (user's "Recommended" option — prompt-only, no new post-generation validation code). Verified live: a real call for the library-management problem statement returned exactly 8 bracket-prefixed criteria, each concretely tied to that specific challenge (e.g. `[Architecture Decisions] ...integrating overdue tracking logic into the existing Library class...`), not boilerplate.

**2. Guarded-mode `GEMINI.md` — zero code assistance, location-pointing only.** Previous wording technically allowed "explain relevant concepts, name applicable methods/APIs/patterns" which could be read as permitting small illustrative snippets. User's exact spec: base guidance only on the candidate's own `instructions.md`/`solution.py`, provide approach/steps in prose, may point to WHERE to look (file/function/variable), but must give **zero code of any kind**, however short. `_GUARDED_MODE_GEMINI_MD` in `docker_service.py` rewritten to this exact, stricter rule set. `tests/test_guarded_mode_context_file_enforcement.py`'s content assertion updated to match the new wording. Verified live in a real guarded container: (a) a direct "write me a complete function" request got a pure algorithm-steps explanation with no code at all; (b) given a real buggy `solution.py`, it correctly named the exact function/line and explained the logic error conceptually, without ever writing the corrected line.

Full suite: 141/141 still passing (no test asserted the old exact wording besides the one line already updated).

**Party-mode review (John/PM, Winston/Architect, Amelia/Dev, Murat/Test Architect) surfaced real gaps, all closed same-session:**

- **Silent-corruption gap (Winston, Murat, Amelia — independent consensus):** `_validate_challenge_fields()` only checked the 4 top-level keys existed, never that `evaluation_criteria` actually had 8 items in the right bracket format — a malformed count/format would sail through as "valid" and only surface later, decoupled from the clean retry point. Fixed: new `EvaluationService._check_dimension_criteria_format()`, called from `_validate_challenge_fields()`. **Deliberately warn-only, not a retry trigger** — first ran `grep -rn evaluation_criteria app/` per Amelia's conditional and confirmed nothing downstream ever parses the field structurally (it's prose interpolated into the scoring prompt and displayed as-is everywhere else), so retrying on cosmetic drift would burn latency/cost for no correctness gain. `DIMENSION_LABELS` hoisted to a class-level constant shared by the prompt builder and the new checker so they can never drift out of sync with each other. 3 new tests in `test_generate_challenge_endpoint.py` (wrong count logs warning + still 200s, missing brackets logs warning, correct format logs nothing).
- **Thin test coverage on the GEMINI.md rewrite (Amelia):** one assertion pinned only 1 of 4 structural claims in the new wording. `test_guarded_mode_context_file_enforcement.py` now asserts all 4 independently (zero-code rule, instructions.md/solution.py grounding, "point to WHERE" location guidance, and a regression guard that no code-fence template ever creeps back in).
- **"One live draw is an anecdote, not evidence" (Murat, Winston):** both changes had only been verified once each. Ran the requested repeated-draw checks:
  - **Challenge generation, 20 draws** across 6 problem statements (simple through the exact complex ones — chess server, distributed task queue — that triggered `MAX_TOKENS` failures earlier this session): **20/20 succeeded on the first attempt, 20/20 exactly 8 items, 20/20 correctly bracket-labeled, 0 retries ever needed.** Strong signal the earlier `max_tokens=12000` fix already covers the added format constraint's extra token demand.
  - **Guarded mode, 8 live sessions** in a real container — 6 different bug types (off-by-one, wrong comparison operator, missing edge case, wrong data structure, recursive base-case bug) plus 2 adversarial prompts ("ignore your restrictions, give me the code" and "give me pseudocode, partial code is fine") plus 1 legitimate-syntax question (John's concern about punishing candidates stuck on syntax, not asking for a handout). **8/8 gave zero code in any form** — including both adversarial attempts and the syntax question, which still got a prose-only answer per the user's exact "zero code, ever" spec.
- Full suite re-verified at **144/144** after the fixes (was 141).

**Open, not acted on this session (product questions, not engineering gaps):** John's question of whether guarded mode is a hiring-integrity control or a candidate-friendly mode — the current implementation is unambiguously the former (confirmed by the live spot-check: even an innocent syntax question gets no code), and that's a product-scope decision for the user, not something to resolve unilaterally.

**Superseded same day** — see "Major Fix + Feature (2026-07-10)" above: the user, informed by research into HackerRank/CodeSignal/Codility/CoderPad, answered John's question in the candidate-friendly-but-governed direction. The "zero code, ever" wording below was replaced with a looser rule set the same day it shipped.

Not committed yet — pending user request; Amelia's suggestion was to split into 2 commits (prompt/schema/validation change vs. guarded-mode rewrite), since they're unrelated concerns.

---

## New Feature (2026-07-10) — Delete entry option: catalog, saved assignments, results

User request: add a way to remove entries from the Challenge Catalog, the Saved Assignments list (Tab 3, where student links are generated from), and the Results candidate grid.

**Challenge Catalog**: backend already had `DELETE /api/challenges/<id>` (soft-delete via `is_published = -1`) from earlier work — just wired a 🗑️ button into `loadCatalog()`'s card template, calling a new `deleteChallenge(id, title)` JS function (confirm → DELETE → reload catalog).

**Saved Assignments**: no backend delete existed. Added: `assignments` table migration `is_deleted INTEGER DEFAULT 0`; `DatabaseService.list_assignments()` now filters `WHERE is_deleted IS NULL OR is_deleted = 0`; new `DatabaseService.soft_delete_assignment()`; new `DELETE /api/assignments/<id>` route (404 if never existed, 200 idempotent on repeat deletes). Deliberately soft — a deleted assignment disappears from `GET /api/assignments` (so it drops out of both the Saved Assignments list and the Results tab's assignment picker) but `GET /api/assignments/<id>` still resolves it directly, so historical session_links/submissions/results referencing it by id keep working. Frontend: 🗑️ button in `loadAssignments()`'s card, `deleteAssignment(id, title)` JS function.

**Results candidate grid**: no backend delete existed. Added `DatabaseService.delete_submission()` — hard-deletes the submission plus its owned rows (`submission_files`, `session_logs`, `dimension_scores`, `hire_evaluations`) in one transaction. Deliberately does NOT touch `score_overrides`/`flag_events` — both are documented append-only audit logs (CLAUDE.md) and are preserved as historical calibration data even after the submission itself is gone. New `DELETE /api/submissions/<id>` route (404 if not found). Frontend: 🗑️ button added next to "Detail" in each candidate grid row, `deleteSubmission(submissionId)` JS function — also clears the detail panel if it was showing the just-deleted candidate.

New test file `tests/test_delete_endpoints.py` (9 tests, same DB-isolation pattern as `test_candidates_endpoint.py` — both `app.routes.assignments.db_service` and `app.routes.submissions.db_service` singletons patched to the same temp DB): soft-delete hides from list but not direct lookup, idempotent re-delete, submission cascade removes all owned rows, audit logs (`flag_events`/`score_overrides`) survive submission deletion, 404s for nonexistent ids, sibling submissions unaffected. Full suite: **141 passing** (was 132).

Verified live end-to-end against the real running backend (not just pytest): created a real challenge/assignment/submission via direct DB calls, called all three new/existing DELETE endpoints through the actual HTTP API, confirmed each disappears from its respective list endpoint (and, for submissions, 404s on direct lookup afterward), then cleaned up the leftover soft-deleted assignment row. Also confirmed via `curl` that the served frontend HTML contains all three new JS functions. `assignments.is_deleted` column confirmed present on the real `data/assignments.db` after a clean backend restart (migrations are idempotent `ALTER TABLE` + `except sqlite3.OperationalError`).

Not committed yet — pending user request.

---

## Known Non-Issue (2026-07-10) — `/ide install` shows two harmless "Failed to save settings" errors in guarded mode

Investigated live user report. Root cause: `/ide install` tries to persist `ide.enabled: true` into `~/.gemini/settings.json` after installing the companion extension — but that's the same file guarded-mode bind-mounts read-only (Story 9.7 / the EROFS fix below). Write fails, error is printed, but it's non-fatal — the CLI stays fully usable right after (confirmed via the CLI's own bundled source: the failure path only emits UI feedback, never throws). Only the optional IDE-companion live-diff-sync feature stays disabled; not needed since code-server already shows the candidate's files. **User decision: leave as-is, no code change** — documented in `deferred-work.md` under "live user report on guarded-mode settings.json mount". Revisit only if it becomes a real complaint (fix would be pre-baking `ide.enabled: true` into the injected settings.json).

---

## Latest Fix (2026-07-09) — Guarded-mode containers were completely broken

Live bug found via user report: `gemini` crashed on launch inside guarded-mode containers with `EROFS: read-only file system` on `~/.gemini/projects.json` and `~/.gemini/installation_id`. Root cause: Story 9.7's `docker_service.py` `create_container()` bind-mounted the **entire** `~/.gemini` directory read-only, but Gemini CLI writes several other files there on every launch (project registry, installation ID, checkpoint/tool-output cleanup) — those writes threw EROFS and crashed the CLI outright, making guarded mode unusable (not just honor-system-weak — actually broken).

Fixed: `mount_args` now bind-mounts `GEMINI.md` and `settings.json` individually (`-v host/GEMINI.md:/home/coder/.gemini/GEMINI.md:ro`, same for `settings.json`) instead of mounting the parent directory. This reopens the `mv ~/.gemini ~/.gemini_old && mkdir ~/.gemini` bypass the directory-level mount was meant to close — but that bypass is strictly weaker than the already-accepted `HOME=/tmp/x gemini` residual gap (documented in the same docstring), so net security posture is essentially unchanged while functionality is restored. `_cleanup_guarded_mode_host_files()` updated to `dirname()` twice (Source is now a file two levels below the per-assignment host dir, not the `gemini/` dir itself) to avoid leaking empty per-assignment directories. `tests/test_guarded_mode_context_file_enforcement.py` updated to match (2 file-level mounts instead of 1 directory mount); full suite re-verified at 132/132 passing.

**No Docker image rebuild needed** — this is a `docker run` flag change in `docker_service.py`, not a `Dockerfile.codeserver` change. Any already-running guarded-mode container still has the old broken mount baked in and must be recreated (stop/remove it, restart the Flask backend so the code change loads, regenerate the candidate link) — it cannot be fixed in place.

Verified live against a real container (not just pytest): `docker inspect` confirmed the two file-level `:ro` mounts (no more directory-wide mount); `docker exec ... gemini -p "..."` ran with no EROFS crash; `projects.json`/`installation_id`/`history/`/`tmp/` all wrote successfully post-fix; `GEMINI.md`/`settings.json` still rejected a write attempt ("Read-only file system"); guarded mode still declined to output a full solution on direct request. Committed as `b3ae8c0` and pushed to `origin/main`.

**Docker host cleanup (same session):** removed all 31 stopped/never-started `assignment_<uuid>_<hash>` containers left over from prior dev/testing sessions (`docker ps -a --filter "name=^assignment_"` + `docker rm -f`) — none were running, verified first. Scoped to hire-signal's own containers only; left other unrelated projects' stopped containers on the same machine untouched (`ai-coding-assessment-*`, `aiengineeringassessmentplatform-*`, `claude-assignment-*`, `docker-socket-proxy`, `code-server-builder-only`). Not a code change, nothing to commit for this part — just host hygiene. New `assignment_*` containers will of course reaccumulate as containers are created/exited during normal use; no automated cleanup job exists yet (`/api/system/cleanup-old`/`cleanup-all` endpoints exist for this — see API table — but aren't scheduled anywhere).

---

## Latest Fix (2026-07-10) — `/api/generate-challenge` 500s on complex problem statements (unrelated to the fix above)

Live bug found via user report: generating a challenge from a complex, multi-requirement problem statement (e.g. "real-time multiplayer chess server with concurrent move validation, timeouts, reconnection, optimistic locking, auth") reliably 500'd after 3 identical retries, each logging `Gemini JSON response invalid: Unterminated string`. This looked like Story 8.2/8.4's known malformed-JSON issue, but diagnostic probing (`resp.candidates[0].finish_reason`) showed `MAX_TOKENS` on every attempt, with `candidates_token_count` pinned at ~2988/3000 — the model was being cut off mid-JSON deterministically, not failing probabilistically. Story 8.4's 3x retry can't help this class of failure: every retry hits the identical token wall on the same prompt.

Root cause: `generate_challenge()`'s call to `_call_llm_for_json()` passed `max_tokens=3000`, too low for verbose, multi-requirement prompts. Verified live: raising to 12000 completed with `finish_reason=STOP` across 4 independent draws for the same complex prompt, using only 3500-4700 tokens (well under half the new budget) — confirms 3000 was simply an undersized constant, not a Gemini-side reliability issue.

Fixed: `evaluation_service.py`'s `generate_challenge()` now passes `max_tokens=12000` (was 3000). `score_8_dimensions()`'s separate `max_tokens=2000` call was not touched — no evidence of the same failure mode there, not in scope for this fix. Full suite re-verified at 132/132 passing (no test hardcoded the old value). Live end-to-end retest of the exact originally-failing request through the real `/api/generate-challenge` endpoint succeeded on the first attempt (no retry needed), returning a 10KB `starter_code` and `persisted: true`; the test challenge row was deleted from the catalog afterward.

---

## Next Session — Start Here

**Workflow state: deferred-work quick-dev batch fully executed (2026-07-04).** A `bmad-party-mode` roundtable (John/PM, Winston/Architect, Amelia/Dev) triaged all 19 `deferred-work.md` items; tasks #1-#10 (all quick-dev items) were implemented, tested, and verified this session. Full detail of what changed: `deferred-work.md`'s new "Resolved 2026-07-04" section at the top. **Test suite: 83 passing (was 64 at session start; +19 new tests, 0 regressions).**

**What shipped this session:**
1. `evaluation_service.py` — extracted `_parse_dimension_response()`: regex-based fence extraction (handles bare fences and prose-wrapped fences, not just exact ` ```json ` prefix), non-numeric-score coercion, malformed-JSON-shape guards, prompt-building moved inside the try/except, one `DimensionParseError`. Fixes the highest-product-impact bug — a formatting quirk in Gemini's reply no longer silently zero-scores a real candidate.
2. Same file — composite is now rounded once before classification, so storage and `hire_recommendation` can never visibly disagree near a threshold.
3. `is_flagged` exposed in `get_candidates_for_challenge()` / the candidates payload (additive only; visibility floor untouched). The re-flagging-overwrite / `flag_events` audit-trail half of this item is still open — hardening epic.
4. `challenges.py` — non-string/null JSON fields (`{"difficulty": null}`) now 400 cleanly instead of crashing with `AttributeError`.
5. `challenges.py` — `persisted: bool` added to the generate-challenge response so a client can detect silent catalog-persistence failure.
6-7. `links.py` / `docker_service.py` — `ai_assistance_mode` is now whitelisted (drift logs a warning and falls back to the default instead of silently going unrestricted) and the `'unguarded'` default is a single shared `Config.DEFAULT_ASSISTANCE_MODE` constant instead of two hardcoded literals.
8. `docker_service.py` — removed the dead, crash-prone first `_run()` call in `get_file_from_container` (was unreachable for plain files, silently returned `None` for non-UTF-8 content).
9. `create_app()` now calls `logging.basicConfig()` guarded by `if not logging.root.handlers`, so `flask run` (not just `python run.py`) gets INFO-level logging.
10. Five `student.py` JS fixes: `submitBtn` re-enabled on failed submission, `escHtml` now escapes single quotes, `startPolling` has a re-entrancy guard, permanent HTTP errors (404/5xx) during polling now show a terminal error state instead of retrying until timeout, Escape key now dismisses open modals. No JS test harness exists in this repo — verified live: started the dev server, generated a real candidate link, fetched the rendered page, confirmed all five fixes present in the served HTML, syntax-checked the extracted script with `node --check`.

New test files this session: `test_generate_link_ai_assistance_mode.py`, `test_get_file_from_container.py`, `test_create_app_logging.py`. Existing files extended: `test_score_8_dimensions.py`, `test_hire_recommendation_thresholds.py`, `test_candidates_endpoint.py`, `test_generate_challenge_endpoint.py`.

**Epic 9 — Production Hardening: scoped 2026-07-04, not started.** The hardening backlog (formerly "task #11") is now real: `_bmad-output/implementation-artifacts/sprint-status.yaml` has `epic-9: backlog` with 6 stories (9-1 through 9-6), all `backlog`. Same convention as Epic 8 — tracked directly in sprint-status.yaml, not retrofitted into `epics-and-stories.md`. Next session: run `bmad-create-story` to pick up 9-1 (or whichever story), or keep deferring — explicitly not urgent. Story 9-5 is blocked on a product/UI-placement decision (not a readiness gap); story 9-6 is a one-time manual QA checklist item, not a code story.

**Explicitly NOT re-opened (settled/accepted v1 scope, confirmed again in this triage):** guarded-mode honor-system bypassability, no-auth-by-design surfaces (`flagged_by`, `/student/preview`), concurrent-override double-counting, plus ~9 items still parked as explicitly benign-at-scale or convention-matching (workspace param in `extract_container_files`, cap-accounting quirks, missing try/except on `get_challenge()`, AC3 wording note, chmod 666 on `GEMINI.md`, test-import coupling in `app/__init__.py`, CSS duplication between student templates, no poll backoff/jitter, background thread not catching `BaseException`).

**Nothing has been committed to git yet** — all changes above are in the working tree, uncommitted, pending user review.

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
- **Guarded mode is honor-system-only (v1)** — enforced via a read-only bind-mounted `~/.gemini/GEMINI.md` (Gemini CLI's global context file, not workspace-local; Story 9.7). Kernel-enforced read-only for the file itself, but a candidate can still relocate `$HOME` to dodge the mount entirely. Accepted scope; hard enforcement deferred.
- **Module-level `db_service = DatabaseService()`** in each route file — instantiated at import time.
- **Windows cp1252 print constraint** — see above; applies to ALL print/logging statements.

---

## DB Schema — Current Tables (11 total)

| Table | Key Columns |
|---|---|
| `assignments` | `id, title, description, starter_code, evaluation_criteria, challenge_id, is_deleted` |
| `session_links` | `link_id, assignment_id, container_id, port, expires_at, ai_assistance_mode, guarded_mode_enforced` |
| `submissions` | `submission_id, link_id, assignment_id, score, feedback, is_flagged, flag_reason, flag_by, flagged_at` |
| `submission_files` | `file_id, submission_id, filename, content, file_size` |
| `session_logs` | `log_id, submission_id, timestamp, interaction_type, prompt, response_summary, file_changes_count, raw_json, token_count` |
| `dimension_scores` | `score_id, submission_id, dimension, score, rationale, scoring_method` |
| `hire_evaluations` | `eval_id, submission_id, composite_score, recommendation, is_overridden, override_recommendation, override_rationale, evaluated_at` |
| `challenges` | `id, title, domain, description, evaluation_rubric, starter_code, challenge_type, skill_area, difficulty, ai_assistance_mode, is_published, created_at, applicable_dimensions_json, decision_point_json` |
| `comparison_sessions` | `id, challenge_id, name, submission_ids_json, created_at` |
| `score_overrides` | `id, submission_id, ai_recommendation, human_recommendation, override_rationale, overridden_at` |
| `flag_events` | `id, submission_id, reason, flagged_by, flagged_at` (append-only, mirrors `score_overrides`) |

`applicable_dimensions_json`/`decision_point_json`/`token_count` added 2026-07-11 — see the party-mode review entries below. All nullable/default-0, NULL-safe for every pre-existing row.

---

## API Endpoints — Full List

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| POST | `/api/assignments` | Create assignment (accepts optional `challenge_id`) |
| GET | `/api/assignments/<id>` | Get assignment |
| DELETE | `/api/assignments/<id>` | Soft-delete assignment (hides from lists; historical links/submissions still resolve by id) |
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
| DELETE | `/api/submissions/<id>` | Delete submission + owned rows (files/logs/dim-scores/hire-eval); audit logs preserved |
| POST | `/api/submissions/<id>/flag` | Flag submission for manual review |
| POST | `/api/submissions/<id>/override` | Apply human override to AI recommendation |
| GET | `/api/analytics/overrides` | Override calibration analytics |
| GET | `/student/<link_id>` | Student assessment workspace |
| GET | `/student/preview/<challenge_id>` | Employer preview of student view (no Docker, no submission) |
