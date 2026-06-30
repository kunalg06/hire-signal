# Epics & Stories — AI Hire-Readiness Evaluation Platform
**Generated:** 2026-06-30 | **Party Mode session with:** John (PM), Winston (Architect), Amelia (Dev), Sally (UX), Mary (BA)

---

## Context

This platform evaluates candidates' AI-assisted coding competency using the ArcEval 8-dimension framework. Employers receive hire recommendations (strong_hire / hire / select / pass), side-by-side candidate comparisons, and per-dimension rationale. Candidates work in isolated Docker containers with browser-based VS Code and Claude API access.

**Current state:** ~60% implemented. Core infrastructure (Flask, SQLite, Docker, session logs, basic evaluation) is working. The 8-dimension scoring engine, challenge catalog, candidate comparison, and employer UI are not yet built.

---

## Epic 1 — Bug Fixes & Foundation Hardening
*Prerequisite for everything else. Fix what's broken before building on it.*

### Story 1.1 — Fix efficiency score bug
- In `app/routes/submissions.py` around line 45, `container_created_at` is always `None` because the code queries `submission_files` for `link_id` (wrong table)
- Fix: get `link_id` directly from the `submissions` table, pass to `db_service.get_link_created_time(link_id)`
- **AC:** Efficiency score reflects real time elapsed, not always the default 15/30

### Story 1.2 — Pass container_id into evaluation pipeline
- Update `submissions.py` `submit_with_files()` to pass `container_id` down to `EvaluationService.evaluate_code()`
- Update `evaluate_code()` signature to accept `container_id` as optional param
- **AC:** Container ID available at evaluation time for full workspace file retrieval

### Story 1.3 — Score bounds enforcement
- Add `min(100, max(0, combined_score))` clamp in `evaluate_code()` final return
- **AC:** Score always 0–100, no overflow possible under any scoring path

### Story 1.4 — Replace print() with proper logging *(deferrable)*
- Replace all `print()` calls across services with Python `logging` module
- **AC:** All errors visible in Flask log output, not stdout

---

## Epic 2 — 8-Dimension AI Scoring Engine
*The core product differentiator. Replaces the hardcoded 40/30/30 scoring.*

### Story 2.1 — Schema: dimension scoring tables
Add to `app/services/database_service.py` `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS dimension_scores (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(submission_id),
    dimension TEXT NOT NULL,
    score INTEGER NOT NULL,
    rationale TEXT,
    scoring_method TEXT NOT NULL,
    scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hire_evaluations (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(submission_id),
    composite_score REAL NOT NULL,
    recommendation TEXT NOT NULL,
    dimension_weights_json TEXT NOT NULL,
    narrative TEXT,
    is_overridden INTEGER DEFAULT 0,
    override_recommendation TEXT,
    override_rationale TEXT,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS score_overrides (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL,
    ai_recommendation TEXT NOT NULL,
    human_recommendation TEXT NOT NULL,
    override_rationale TEXT NOT NULL,
    overridden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
- **AC:** Tables created idempotently on startup, no migration risk to existing data

### Story 2.2 — Full workspace snapshot at submission time
- In `EvaluationService`, add `extract_container_files(container_id)` using Docker `get_archive('/workspace')`
- Filter to text files only: `.py`, `.js`, `.ts`, `.md`, `.json`, `.sh`, `.yaml`, `.txt`
- Cap total at 50KB; truncate per-file with `[TRUNCATED]` marker
- Return `{}` gracefully if Docker unavailable — evaluation still proceeds
- **AC:** All candidate-authored files available for scoring; graceful fallback on Docker failure

### Story 2.3 — 8-dimension Claude scoring prompt
Replace `evaluate_code()` scoring logic with `score_8_dimensions(session_logs, file_snapshot, assignment)`.

**Dimension weights:**
```python
DIMENSION_WEIGHTS = {
    "problem_decomposition":     0.15,
    "first_principles_thinking": 0.15,
    "creative_problem_solving":  0.10,
    "iteration_quality":         0.15,
    "debugging_with_ai":         0.15,
    "architecture_decisions":    0.10,
    "communication_clarity":     0.10,
    "token_efficiency":          0.10,
}
```

**Claude prompt returns:**
```json
{
  "dimensions": {
    "problem_decomposition": {"score": 0-100, "rationale": "2 sentences citing log evidence"},
    "first_principles_thinking": {"score": 0-100, "rationale": "..."},
    "creative_problem_solving": {"score": 0-100, "rationale": "..."},
    "iteration_quality": {"score": 0-100, "rationale": "..."},
    "debugging_with_ai": {"score": 0-100, "rationale": "..."},
    "architecture_decisions": {"score": 0-100, "rationale": "..."},
    "communication_clarity": {"score": 0-100, "rationale": "..."},
    "token_efficiency": {"score": 0-100, "rationale": "..."}
  },
  "aggregate_score": 0.0,
  "hire_recommendation": "strong_hire|hire|select|pass",
  "recommendation_rationale": "3-4 sentences"
}
```

Defensive fallback: if JSON parse fails, return all dimensions at score=0 with `rationale="parse_error"`, `hire_recommendation="pass"`.

- **AC:** All 8 dimension keys always present; single Claude call; rubric embedded in prompt

### Story 2.4 — Hire recommendation logic (Python-enforced)
- Compute `composite_score` as Python-weighted average — do NOT trust Claude's value
- Enforce thresholds server-side: `strong_hire >= 85`, `hire >= 70`, `select >= 55`, `pass < 55`
- Write result to `hire_evaluations` table with dimension_weights snapshot for auditability
- **AC:** `hire_recommendation` always Python-determined; Claude's threshold recommendation logged but not used

### Story 2.5 — Persist dimension scores to DB
- After `score_8_dimensions()` returns, write one row per dimension to `dimension_scores` table
- Update `submissions` with aggregate score and hire recommendation
- **AC:** Per-dimension scores queryable; hire verdict stored with full audit trail

### Story 2.6 — Updated submission API response
- `GET /api/submission/<id>` adds: `hire_recommendation`, `composite_score`, `dimensions` (array of 8 with score + rationale), `recommendation_rationale`
- Existing fields (`score`, `feedback`) preserved for backward compatibility
- **AC:** No breaking changes; new fields additive

---

## Epic 3 — Market-Aligned Challenge System
*Generate real-world AI-era interview challenges, not generic algorithm puzzles.*

### Story 3.1 — Schema: challenges catalog table
Add to `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS challenges (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    domain TEXT NOT NULL,
    description TEXT NOT NULL,
    evaluation_rubric_json TEXT,
    starter_code TEXT,
    challenge_type TEXT NOT NULL,
    skill_area TEXT NOT NULL,
    difficulty TEXT NOT NULL DEFAULT 'medium',
    ai_assistance_mode TEXT NOT NULL DEFAULT 'unguarded',
    is_published INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Valid enums:**
- `challenge_type`: `bug_fix | feature_extension | refactoring | optimization`
- `skill_area`: `api_integration | rate_limiting | data_pipeline | llm_usage | server_monitoring | game_logic`
- `ai_assistance_mode`: `guarded | unguarded`

- **AC:** Table idempotent on startup; existing schema unaffected

### Story 3.2 — Extended challenge generation API
- Update `POST /api/generate-challenge` to accept: `challenge_type`, `skill_area`, `ai_assistance_mode`
- Validate enums server-side; return 400 with clear error message on invalid values
- Pass new params down to `EvaluationService.generate_challenge()`
- **AC:** 400 returned for invalid values; defaults applied when params omitted

### Story 3.3 — Richer challenge generation prompt *(the key unlock)*
Rewrite `generate_challenge()` prompt in `app/services/evaluation_service.py`:

- Market context: mirror Stripe/Anthropic/Vercel/Linear style interviews
- challenge_type instructions:
  - `bug_fix`: insert 2–4 real bugs, no comments marking them, minimum 40 lines
  - `feature_extension`: working partial implementation with explicit TODO points
  - `refactoring`: working but messy code, candidate improves structure
  - `optimization`: correct but slow, candidate improves performance
- skill_area: include realistic imports (httpx, anthropic, sqlite3, etc.) matching domain
- `guarded` mode instruction: self-contained starter code, rewards understanding
- `unguarded` mode instruction: deliberate gaps rewarding strategic AI tool use
- Return JSON: `{title, description, evaluation_criteria, starter_code}`
- **AC:** Generated starter_code ≥40 lines, type-hinted, includes `__main__` block; different challenge_types produce structurally different starter code

### Story 3.4 — Auto-persist generated challenge to catalog
- After Claude returns challenge JSON, write to `challenges` table with `is_published=0`
- Return `challenge_id` in API response alongside existing fields
- **AC:** Every generated challenge stored and retrievable; `challenge_id` in response

### Story 3.5 — Challenge catalog endpoints
- `GET /api/challenges` — list published challenges, filterable: `?challenge_type=`, `?skill_area=`, `?difficulty=`, `?ai_assistance_mode=`
- `GET /api/challenges/<id>` — fetch single challenge with full detail
- `POST /api/challenges/<id>/publish` — set `is_published=1`
- `DELETE /api/challenges/<id>` — soft delete (set `is_published=-1`)
- **AC:** Unpublished challenges not returned in list; single challenge endpoint returns regardless of publish status

### Story 3.6 — Seed 10 curated challenges *(deferrable)*
- Write `scripts/seed_challenges.py` inserting 10 hand-crafted challenges
- Cover all 4 challenge types × key skill areas
- Include: rate limiter bug fix, LLM prompt chaining feature extension, server log monitor refactoring, API integration optimization
- **AC:** Fresh install has usable library without generating anything

---

## Epic 4 — Candidate Comparison & Hiring Workflow
*The employer-facing hire/pass decision surface.*

### Story 4.1 — Schema: comparison sessions
```sql
CREATE TABLE IF NOT EXISTS comparison_sessions (
    id TEXT PRIMARY KEY,
    challenge_id TEXT NOT NULL REFERENCES challenges(id),
    name TEXT,
    submission_ids_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
- **AC:** Employers can group multiple candidates under one named comparison

### Story 4.2 — Candidate comparison endpoint
- `GET /api/challenges/<challenge_id>/candidates`
- Query params: `sort_by` (any dimension key or `composite_score`), `order` (desc/asc, default desc)
- Response: ranked candidates with all 8 dimension scores, hire recommendation, `dimension_averages` across cohort
- **AC:** Returns 200 with empty `candidates: []` when no submissions; `dimension_averages` always present

### Story 4.3 — Human override + Flag for Manual Review
- `POST /api/submissions/<id>/flag` — `{reason, flagged_by}` → stores in `submissions` table
- `POST /api/submissions/<id>/override` — `{override_recommendation, override_rationale}` → stored in `hire_evaluations`; original AI score preserved, never overwritten
- **AC:** Override requires rationale; AI score always readable alongside human override

### Story 4.4 — Override logging as calibration dataset
- Every override logged to `score_overrides` table (Story 2.1 schema)
- `GET /api/analytics/overrides` — admin endpoint returning override frequency per dimension
- **AC:** Pattern detectable after 10+ overrides

### Story 4.5 — Visibility floor enforcement
- `GET /api/challenges/<id>/candidates` NEVER excludes candidates based on score
- Score determines `rank` field only; all candidates with completed evaluations appear
- **AC:** Candidate with score 10/100 appears ranked last, not absent

---

## Epic 5 — Employer Dashboard UI Overhaul
*Turn single-score display into a hire-readiness command centre.*

### Story 5.1 — Challenge Results Board (candidate grid)
- New section in `templates/frontend.html` or new `templates/employer.html`
- Input challenge ID → fetch `GET /api/challenges/<id>/candidates`
- Candidate cards: name, timestamp, hire recommendation badge, aggregate score, mini radar chart (SVG), one-line AI summary
- Filter buttons: All / Strong Hire / Hire / Select / Pass
- Sort by: composite score or any dimension
- **AC:** All candidates visible; filter/sort client-side without re-fetch

### Story 5.2 — 8-dimension radar chart (SVG component)
- Reusable vanilla JS + SVG radar chart: 8 labeled spokes
- Abbreviated labels: PD, FP, CP, IQ, DA, AD, CC, TE; hover tooltips with full names
- Mini (80px) for candidate grid; full (300px) for detail and comparison
- **AC:** Renders without JS framework; accessible (title + desc SVG elements)

### Story 5.3 — Side-by-side candidate comparison view
- Select two candidates from grid → comparison view
- Overlaid ghost-polygon radar charts on same axes
- Butterfly chart: 8 rows, left = candidate A bar, right = candidate B bar
- Color-coded by quartile using `dimension_averages` from cohort
- Each row expandable: metric detail + prompt excerpt + rationale
- Warning modal on cross-challenge comparison attempt
- **AC:** Locked to same challenge_id; cross-challenge blocked with modal

### Story 5.4 — Hire recommendation surface
- Badge (Strong Hire / Hire / Select / Pass): green / blue / amber / gray
- AI-written narrative paragraph per candidate
- "Flag for Manual Review" button → calls Story 4.3
- "Override" action → dropdown + required rationale field; cannot save without rationale
- **AC:** Override requires rationale before save; AI score visible alongside override

### Story 5.5 — AI Beta transparency banner
- Persistent banner: *"AI scoring is experimental. Treat scores as one signal — human judgment holds final authority."*
- Dismissible per session (localStorage); returns on next page load
- **AC:** Visible on first employer dashboard load; absent from student view

---

## Epic 6 — Student Experience & Preview as Student

### Story 6.1 — Structured challenge display in student view
- Refactor student workspace template: three distinct panels: **Scenario**, **Your Task**, **Evaluation Criteria**
- Evaluation Criteria visible to candidate (industry standard — tests whether they can hit known targets)
- **AC:** Three labeled sections visible before code editor loads

### Story 6.2 — Verification nudge before submission
- Modal on submit click: *"Before you submit: Did you run the code? Did you test edge cases?"*
- Not a gate — candidate can dismiss and submit immediately
- **AC:** Modal appears every time; dismissing proceeds to submit

### Story 6.3 — Real polling instead of fixed 2s wait
- Replace `setTimeout(2000)` with polling loop: `GET /api/submission/<id>` every 3s until `evaluated_at` populated or 60s timeout
- Show: *"Analysis usually takes 20–40 seconds"*
- **AC:** Results appear as soon as evaluation completes; no fixed wait

### Story 6.4 — Preview as Student
- `GET /student/preview/<challenge_id>` — employer views student workspace without Docker
- Top banner: *"Preview Mode — No session data is recorded"*
- Submission button disabled (grayed, tooltip: "Disabled in preview")
- Uses challenge `starter_code` directly — no container needed
- **AC:** Preview loads in under 2s; shows exactly what candidate sees

### Story 6.5 — Guarded mode Claude restrictions
- When `ai_assistance_mode = guarded`, inject system prompt into student Claude environment
- System prompt: restricts full solution generation, allows conceptual guidance only
- **AC:** Guarded challenges restrict Claude responses; unguarded unrestricted

---

## Epic 7 — Test Coverage
*Each story in Epics 2–6 requires a corresponding test before merge.*

- **7.1** Unit test: `score_8_dimensions()` — mock Claude, assert all 8 keys, assert Python-weighted average used
- **7.2** Unit test: `extract_container_files()` — Docker unavailable → `{}`, text-only filter, 50KB cap
- **7.3** Unit test: hire recommendation thresholds — all 4 boundary conditions
- **7.4** Integration test: `GET /api/challenges/<id>/candidates` — empty list, sorted results, dimension_averages
- **7.5** Unit test: `generate_challenge()` with new params — invalid enum → 400, valid → persisted

---

## Build Order

```
Epic 1 (bugs)  →  Epic 3 (challenge system)  →  Epic 2 (scoring engine)
                            ↓                              ↓
                     Epic 4 (comparison)           Epic 6 (student UX)
                            ↓
                     Epic 5 (employer UI)
                            ↓
                     Epic 7 (tests — runs alongside all epics)
```

## Priority Execution Plan (Phase 1 — MVP Scoring Loop)

For the first delivery milestone — **challenge creation through assessment scoring** — execute only:

| Phase | Stories | Outcome |
|---|---|---|
| Foundation | E1: 1.1, 1.2, 1.3 | Bugs fixed, container_id flows correctly |
| Challenge creation | E3: 3.1, 3.2, 3.3, 3.4, 3.5 | Market-aligned challenges generated and catalogued |
| Scoring engine | E2: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6 | 8-dimension scoring + hire recommendation on every submission |

**Deferred to Phase 2:** Epic 4 (comparison), Epic 5 (employer UI), Epic 6 (student UX), Epic 7 (tests), Story 1.4 (logging), Story 3.6 (seed challenges)
