# Story 7.4: Integration test — `GET /api/challenges/<id>/candidates`

Status: done

## Story

As a platform maintainer,
I want an integration test that drives the candidates endpoint through a real Flask test client and a real (but isolated) SQLite database,
so that the endpoint's ranking, filtering, and visibility-floor guarantees are verified end-to-end — not just at the unit level — without ever touching the actual development database.

## Acceptance Criteria

1. **Isolated DB, zero pollution risk** — every test runs against a throwaway SQLite file created fresh per test (or per test session via a fixture), never the real `data/assignments.db`. The real DB file's size/mtime is provably unaffected by running this suite.
2. **404 for missing challenge** — `GET /api/challenges/<nonexistent-id>/candidates` → 404, `{"error": "Challenge not found"}`.
3. **Empty list for a challenge with zero candidates** — a real, existing challenge with no linked assignments/submissions → 200, `{"candidates": [], "total": 0, "dimension_averages": {}}`.
4. **Sorted results (default)** — 3+ evaluated candidates with distinct `composite_score` values → default `GET .../candidates` (no query params) returns them ordered by `composite_score` descending, each with a `rank` field starting at 1.
5. **Sorted results (explicit sort_by + order)** — `?sort_by=<dimension_key>&order=asc` reorders candidates by that dimension's score ascending; `order=desc` reverses it.
6. **`dimension_averages` always present, correctly scoped** — averages are computed only over evaluated candidates and only over dimensions that have a non-null score; the field is `{}` (not missing, not null) when zero candidates are evaluated.
7. **Visibility floor** — a mix of evaluated and un-evaluated candidates: un-evaluated candidates (`is_evaluated: false`) always appear last in the `candidates` array, in both `order=asc` and `order=desc`.
8. **Query validation** — `?sort_by=not_a_real_field` → 400; `?order=sideways` → 400.
9. Full suite (`python -m pytest tests/ -v`) green from project root; the 38 pre-existing tests from Stories 7.1–7.3 unaffected.

## Tasks / Subtasks

- [x] Task 1: Isolated-DB test infrastructure in `tests/test_candidates_endpoint.py` (AC: 1)
  - [x] Fixture `client(monkeypatch, tmp_path)`: build a fresh `Database(tmp_path / "test.db")`, call `.init_db()`, monkeypatch `app.routes.challenges.db_service.db` to point at it (see Dev Notes — **this exact monkeypatch target is mandatory**, not `create_app(config_name)`), build the app via `create_app()`, `yield app.test_client()`
  - [x] Fixture `db(client)` or equivalent: expose the same repointed `db_service` (import `app.routes.challenges` and read its `db_service` attribute) so tests can seed rows through its existing `create_*` methods
  - [x] Sanity test: snapshot `os.path.getsize()` (or hash) of the real `data/assignments.db` before and after the full test module runs, assert unchanged (belt-and-suspenders proof the isolation actually works)
- [x] Task 2: Seeding helpers (AC: 2–8)
  - [x] `make_challenge(db_service, **overrides) -> challenge_id` — wraps `create_challenge(...)` with sane defaults (`challenge_type='bug_fix'`, `skill_area='api_integration'`, etc.)
  - [x] `make_evaluated_candidate(db_service, challenge_id, composite_score, dimension_scores=None, **overrides) -> submission_id` — wraps the full chain: `create_assignment(challenge_id=challenge_id)` → `create_session_link(...)` → `create_submission(...)` → `create_hire_evaluation(composite_score=..., recommendation=...)` → `create_dimension_score(...)` per dimension (default all 8 dims to `composite_score` if `dimension_scores` not given, for simplicity)
  - [x] `make_unevaluated_candidate(db_service, challenge_id, **overrides) -> submission_id` — same chain but skips `create_hire_evaluation` entirely (LEFT JOIN naturally produces NULLs → `is_evaluated: False`)
- [x] Task 3: 404 and empty-list tests (AC: 2, 3)
  - [x] `GET /api/challenges/does-not-exist/candidates` → 404 + exact error body
  - [x] Real challenge, zero candidates → 200, `candidates: []`, `total: 0`, `dimension_averages: {}`
- [x] Task 4: Sorting tests (AC: 4, 5)
  - [x] 3 evaluated candidates with composite scores e.g. 90/70/50 → default GET ranks them 90,70,50 with `rank` 1,2,3
  - [x] `?order=asc` on the same data → 50,70,90
  - [x] `?sort_by=architecture_decisions&order=desc` with distinct per-dimension scores → ranked by that dimension, not composite
- [x] Task 5: dimension_averages tests (AC: 6)
  - [x] 2 evaluated candidates with known per-dim scores → assert each of the 8 averages equals the hand-computed mean, rounded to 1 decimal
  - [x] 1 evaluated + 1 unevaluated → averages computed only from the evaluated one
- [x] Task 6: Visibility floor test (AC: 7)
  - [x] 2 evaluated (scores 90, 50) + 1 unevaluated → `order=desc`: [90, 50, unevaluated]; `order=asc`: [50, 90, unevaluated] — unevaluated last in BOTH directions
- [x] Task 7: Validation tests (AC: 8)
  - [x] `?sort_by=not_a_real_field` → 400
  - [x] `?order=sideways` → 400
- [x] Task 8: Run and verify (AC: 9)
  - [x] `python -m pytest tests/ -v` green, 38 existing + new tests, real DB file unchanged

### Review Findings

- [x] [Review][Patch] `create_app()` called with no config still touches the real `data/assignments.db` via its own internal `Database(config.DB_PATH).init_db()` call — harmless today only because the real DB's schema is already fully migrated (idempotent no-op); on a fresh checkout the suite would create/migrate the real file [tests/test_candidates_endpoint.py:51-52]
- [x] [Review][Patch] Isolation-proof test is structurally unable to detect a leak — baseline captured AFTER seeding writes and `create_app()` already ran, only a single read-only GET is bracketed, silently no-ops if the real DB file is absent, and the path is CWD-relative instead of matching `Config.DB_PATH` [tests/test_candidates_endpoint.py:120-126]
- [x] [Review][Patch] `sort_by=<dimension>` test uses composite/dimension scores that are order-correlated — the test passes identically even if `sort_by` were silently ignored and the route fell back to composite sort [tests/test_candidates_endpoint.py:176-188]
- [x] [Review][Patch] `db` fixture doesn't structurally depend on `client` — a future test requesting only `db` gets the unpatched singleton (writes straight to the real DB); enforce via `def db(client):` [tests/test_candidates_endpoint.py:58-62]
- [x] [Review][Patch] `total` field only asserted in the empty-list case — add to multi-candidate tests
- [x] [Review][Patch] `rank` only asserted for default desc sort — add to the asc test and the visibility-floor test (unevaluated candidates get ranks too, at the tail)
- [x] [Review][Patch] Unevaluated-candidate response shape never asserted (`composite_score`, `dimensions`) — add to the visibility-floor test
- [x] [Review][Patch] No test for 400-vs-404 precedence (invalid `sort_by` + nonexistent challenge) — route checks challenge existence first; pin it
- [x] [Review][Patch] No cross-challenge leakage test — nothing proves a candidate from a sibling challenge is excluded by the `WHERE a.challenge_id = ?` filter
- [x] [Review][Patch] Dimension-sort path never tested with an unevaluated candidate present — only the composite-sort branch's None→±inf handling is exercised, not the dimension-sort branch's
- [x] [Review][Patch] `dimension_averages` test uses uniform per-dimension scores per candidate — a cross-dimension mix-up in the averaging code would pass undetected; use distinct per-dimension values like Story 7.1's `DISTINCT_SCORES` lesson

Dismissed as noise (4): "no assertion the monkeypatch took effect" (redundant — every 200-path test would 404 instead if the patch silently failed, since seeded IDs don't exist in the real DB; execution evidence already proves the patch works), "exact-match 404 body assertion is brittle" (matches established project convention — all prior stories pin literal error bodies), "REAL_DB_PATH is CWD-relative" (folded into the isolation-test rewrite patch — now imports `Config.DB_PATH` directly instead of hardcoding), "duplicate fixture data (container-x/7100) invites hidden constraint failures" (speculative — no uniqueness constraint exists in the schema).

## Dev Notes

### THE central design constraint — read this before writing any fixture

**`create_app(config_name)` does NOT give you database isolation for this endpoint.** This is the single most important thing to get right in this story, and it is not obvious from reading `app/routes/challenges.py` in isolation. Verified by reading the actual code:

1. `app/routes/challenges.py:11` has `db_service = DatabaseService()` at **module level** — constructed once, the moment the module is first imported.
2. `DatabaseService.__init__(self, db_path=None)` → `self.db = Database(db_path)` (`app/services/database_service.py:10-11`).
3. `Database.__init__(self, db_path=None)` → `self.db_path = db_path or Config.DB_PATH` (`app/models/database.py:8-9`).
4. `Config.DB_PATH = os.getenv('DB_PATH', os.path.join('data', 'assignments.db'))` — a **class attribute evaluated once**, when `app/config.py` is first imported.
5. **Import-order trap**: `app.services.evaluation_service` (imported by Stories 7.1–7.3's test files) does `from app.config import Config`, which — because `app.config` is a submodule of the `app` package — triggers Python to first execute `app/__init__.py`. That file imports **every blueprint module**, including `app.routes.challenges`, which constructs `db_service` **right then**, using whatever `Config.DB_PATH` resolves to **at that moment** (no `DB_PATH` env var is set in this project's `.env` — confirmed by inspection — so it resolves to `data/assignments.db`, **the real development database**, confirmed present on disk at 249KB as of story-authoring time).
6. Because pytest collects and imports all test files into **one process**, by the time this story's test file runs, `app.routes.challenges.db_service` **already exists** and is **already pointed at the real DB file** — regardless of what config name you later pass to `create_app()`. Calling `create_app('testing')` creates a *second, throwaway* `Database` instance solely to call `.init_db()` on `TestingConfig.DB_PATH` (`data/test_assignments.db`) — the blueprint's `db_service` never sees or uses it.

**The only robust fix**: directly monkeypatch the blueprint's live singleton inside the test fixture itself, so it is order-independent regardless of what other test files import first:

```python
import app.routes.challenges as challenges_module
from app.models.database import Database

@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = Database(str(tmp_path / "test.db"))
    test_db.init_db()
    monkeypatch.setattr(challenges_module.db_service, "db", test_db)

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
```

After this, `challenges_module.db_service` (the exact object the route function closes over) reads/writes only the temp file. Seed data through `challenges_module.db_service`'s own `create_*` methods (same object, now safely repointed) — do not construct a second `DatabaseService` pointed at the same temp path; reuse the patched one so there is exactly one source of truth per test.

### Route anatomy — `GET /api/challenges/<challenge_id>/candidates`

`app/routes/challenges.py:199-269`:
1. `db_service.get_challenge(challenge_id)` falsy → 404 `{'error': 'Challenge not found'}` (line 202-203)
2. `sort_by` defaults to `'composite_score'`, must be in `VALID_SORT_FIELDS` (composite_score + all 8 dimension keys, line 24) or 400 (line 208-209)
3. `order` defaults to `'desc'`, must be `asc`/`desc` or 400 (line 210-211)
4. `db_service.get_candidates_for_challenge(challenge_id)` — SQL: `submissions JOIN assignments ON a.challenge_id = ? LEFT JOIN hire_evaluations` (`database_service.py:289-309`) — **only submissions whose assignment's `challenge_id` matches are returned**; a submission on an assignment with no `challenge_id` (or a different one) never appears
5. Per candidate: `is_evaluated = row[7] is not None` (`he.evaluated_at`) — an unevaluated candidate is one with **no `hire_evaluations` row at all** (LEFT JOIN → NULL), not one with a zero score
6. Python-side sort (`sort_key`, lines 235-242): unevaluated candidates get `-math.inf` (asc) or `math.inf` (desc) as their sort value — **always sorts last regardless of direction**; this is the "visibility floor"
7. `rank` assigned 1-indexed **after** sorting (line 246-247)
8. `dimension_averages` (lines 252-262): filtered by `c['is_evaluated']` (boolean, not dict truthiness — a Story 4.x review patch), then per-dimension only over candidates that actually have that dimension's score present and non-None; `round(mean, 1)`; **stays `{}` if `evaluated` list is empty** (the `if evaluated:` guard, line 254)

### Required seed chain for one evaluated candidate

Foreign keys are declared but SQLite does not enforce them by default in this codebase (no `PRAGMA foreign_keys = ON` in `Database.get_connection()`), but seed the full realistic chain anyway — it is what production actually writes and keeps the test meaningful:

`create_challenge(...)` → `create_assignment(assignment_id, ..., challenge_id=challenge_id)` → `create_session_link(link_id, assignment_id, container_id, port, expires_at)` → `create_submission(submission_id, link_id, assignment_id, files_json)` → `create_hire_evaluation(eval_id, submission_id, composite_score, recommendation, dimension_weights_json, narrative)` → `create_dimension_score(score_id, submission_id, dimension, score, rationale)` × 8 (or however many you need for a given test)

All ID params are opaque strings — use `IDGenerator` (`app.utils.helpers`, already imported by `challenges.py`) or simple literals like `f"sub-{n}"`; uniqueness across the test file's tables (`submission_id` is a `TEXT PRIMARY KEY`) is all that matters, not any particular format.

For an **unevaluated** candidate: run the same chain but stop after `create_submission` — never call `create_hire_evaluation`. The LEFT JOIN then naturally produces `he.evaluated_at IS NULL` → `is_evaluated: False`.

### Story 7.1–7.3 learnings that still apply

- Shape-robust mocks were needed there because those stories mocked the LLM; this story does not mock anything — it drives real Flask routing and real SQLite through a real (isolated) file. No `LLMService`/`DockerService` mocking needed or relevant here.
- Pin expectations as literals, not derived from the code under test (e.g. `VALID_SORT_FIELDS` — don't import and iterate it to build your test's dimension list; write out the 8 dimension name strings, matching the pattern from `test_score_8_dimensions.py`'s `EXPECTED_DIMS`).
- ASCII only in any print/log output.
- Test infra already exists: root `conftest.py` handles `sys.path`.

### Scope boundaries — do not creep

- **No production code changes.** If the DB-isolation trap above turns out to affect other future integration tests, that's worth a note in Dev Notes for whoever writes Story 7.5+, not a fix here (though: if you want to leave a trail, a future refactor could make blueprint `db_service` instances lazy/injectable rather than import-time singletons — note it in `deferred-work.md` if it becomes a recurring pain, don't refactor it now).
- Do not test `POST /api/generate-challenge` or challenge creation validation — that's Story 7.5.
- Do not re-test `score_8_dimensions`, `extract_container_files`, or threshold logic — Stories 7.1–7.3, already done.
- Do not add a shared `conftest.py` fixture for this DB-isolation pattern unless you're confident a later story will reuse it — a future story can extract one once the pattern repeats (YAGNI); this story's fixtures can live entirely in its own test file, consistent with 7.1–7.3's per-file convention.

### Project Structure Notes

- New file: `tests/test_candidates_endpoint.py` only
- This is the first test file in the suite to use Flask's `test_client()` and a real (temp-file) SQLite DB rather than pure mocking — expect more setup code per test than Stories 7.1–7.3, that's inherent to integration testing, not a sign something's wrong

### References

- [Source: _bmad-output/planning-artifacts/epics-and-stories.md#Epic 7 — story 7.4 line 329]
- [Source: app/routes/challenges.py lines 1-24, 199-269 — endpoint + validation sets]
- [Source: app/services/database_service.py lines 7-11, 59-67, 227-238, 239-251, 289-309, 313-334 — DatabaseService, create_* methods, get_candidates_for_challenge]
- [Source: app/models/database.py lines 5-18, 51-66, 99-144, 173-193 — Database class, table schemas, challenge_id migration]
- [Source: app/__init__.py lines 1-53 — create_app(), .env force-load, blueprint registration order]
- [Source: app/config.py lines 1-68 — Config.DB_PATH resolution, TestingConfig]
- [Source: AGENT.md#Architecture Constraints — "Module-level db_service = DatabaseService() in each route file — instantiated at import time"]

## Dev Agent Record

### Agent Model Used

claude-fable-5

### Debug Log References

- `python -m pytest tests/test_candidates_endpoint.py -v` — 11 passed in 2.95s, first run green
- `python -m pytest tests/ -v` — 49 passed in 2.91s (11 new + 38 from Stories 7.1-7.3), zero regressions
- Real DB isolation proof: `data/assignments.db` mtime/size (`1783022402` / `249856` bytes) identical before and after the full suite run, captured via a raw filesystem stat outside pytest

### Completion Notes List

- 11 tests in `tests/test_candidates_endpoint.py` covering all 9 ACs: isolation proof (real DB untouched), 404 for missing challenge, empty-list for zero candidates, default sort (composite_score desc) with rank assignment, order=asc reversal, sort_by a specific dimension key, dimension_averages computed only over evaluated candidates (with exact-mean assertion), dimension_averages empty when none evaluated, visibility floor in both sort directions, and 400s for invalid sort_by/order
- The critical finding from story creation — that `app.routes.challenges.db_service` is an import-time singleton pointed at the real `data/assignments.db` regardless of `create_app(config_name)` — was confirmed exactly as documented in Dev Notes: `create_app()` was called with no config override at all in the final fixture, since bypassing its DB init was already the plan; the monkeypatch on `challenges_module.db_service.db` is what actually provides isolation
- Seeding helpers (`make_challenge`, `make_evaluated_candidate`, `make_unevaluated_candidate`) wrap the full realistic write chain (challenge → assignment → session_link → submission → hire_evaluation → dimension_scores) through the same patched `db_service`, so no second `DatabaseService` instance was needed
- No production code touched
- Code review 2026-07-03 (Blind Hunter + Edge Case Hunter + Acceptance Auditor): Acceptance Auditor verdict "Acceptable" — all 9 ACs met, mandatory monkeypatch pattern verified exact, all seeding helper signatures verified against real `DatabaseService` methods. All three layers independently converged on the same root-cause finding: `create_app()` called with no config argument still touched the real `data/assignments.db` via its own internal `Database(config.DB_PATH).init_db()` call — harmless only because that DB's schema was already fully migrated (idempotent no-op), not because of any actual isolation. Fixed by passing `create_app("testing")` (`TestingConfig.DB_PATH` is a hardcoded literal, not env-var-dependent, so this reliably points the internal call at `data/test_assignments.db` instead). The isolation-proof test was also rewritten: baseline is now captured by a module-scoped autouse fixture BEFORE any test in the file runs (not after seeding, as before), verified against the LAST-executing test (relies on pytest's default file-order execution — no randomization plugin installed), checks both size and mtime, uses `Config.DB_PATH` directly instead of a hardcoded path, and explicitly `pytest.skip`s (visible) rather than silently no-oping if the real DB is absent. Also fixed a logic bug in the `sort_by=<dimension>` test: the original fixture data was order-correlated with composite score, so the test couldn't actually distinguish real dimension-sorting from a silently-ignored `sort_by` falling back to composite order — rebuilt with anti-correlated data. 11 patches total applied (10 above the two headline fixes: `db` fixture now structurally depends on `client`; `total`/`rank` assertions added to more tests; unevaluated-candidate response shape asserted; a 400-vs-404 precedence test and a cross-challenge leakage test added; the dimension-sort test now includes an unevaluated candidate; `dimension_averages` test rebuilt with distinct non-mirrored per-dimension values so a key mix-up would be caught). Zero production gaps found — first story in Epic 7 review with no new deferred-work.md entry. 4 findings dismissed as noise. Suite now 13 tests in this file (51 total with 7.1-7.3), all green in 3.19s; real DB file's mtime/size independently confirmed byte-identical before and after via a raw filesystem stat outside pytest.

### File List

- `tests/test_candidates_endpoint.py` (new)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — status tracking)
- `_bmad-output/implementation-artifacts/7-4-integration-test-get-api-challenges-id-candidates.md` (this file)
