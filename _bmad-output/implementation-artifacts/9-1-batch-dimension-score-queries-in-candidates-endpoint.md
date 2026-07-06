# Story 9.1: Batch Dimension-Score Queries in Candidates Endpoint

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a recruiter/employer viewing a candidate cohort for a challenge,
I want `GET /api/challenges/<challenge_id>/candidates` to fetch all candidates' dimension scores in a single query instead of one query per candidate,
so that the results page stays fast as cohort size grows, with zero change to ranking, visibility, or response shape.

## Acceptance Criteria

1. `GET /api/challenges/<challenge_id>/candidates` issues exactly ONE additional query for dimension scores per request, regardless of how many candidates are in the cohort (0, 1, or 50) — not one query per candidate.
2. Every existing test in `tests/test_candidates_endpoint.py` passes with ZERO assertion changes — this is the regression proof, not optional. In particular:
   - `test_unevaluated_candidates_sort_last_in_both_directions` (the visibility floor) must still pass unmodified.
   - `test_dimension_averages_computed_only_over_evaluated` must still pass unmodified.
   - `test_flagged_candidate_marked_in_payload_but_not_hidden` must still pass unmodified.
3. Each candidate's `dimensions` dict contains ONLY that candidate's own dimension scores — no cross-candidate mixing — proven by a new test with ≥3 candidates carrying distinct per-dimension scores.
4. A challenge with zero candidates still returns `{candidates: [], dimension_averages: {}, total: 0}` with no crash (no `WHERE submission_id IN ()` on an empty list — sqlite3 can't parameterize an empty IN clause).
5. JSON response shape is byte-for-byte identical to today's — this is purely an internal query-count optimization, not a feature change. No new/removed/renamed fields.

## Tasks / Subtasks

- [x] Add `DatabaseService.get_dimension_scores_for_submissions(submission_ids)` (AC: 1, 4)
  - [x] Guard: if `submission_ids` is empty, return `{}` immediately without querying (sqlite3 cannot bind an empty `IN (...)` list)
  - [x] One query: `SELECT submission_id, dimension, score, rationale, scoring_method, scored_at FROM dimension_scores WHERE submission_id IN (...) ORDER BY submission_id, dimension ASC`
  - [x] Group rows by `submission_id` into a `{submission_id: [(dimension, score, rationale, scoring_method, scored_at), ...]}` dict before returning
- [x] Update `get_challenge_candidates()` in `app/routes/challenges.py` to use the batched method (AC: 1, 3, 5)
  - [x] Collect all `submission_id`s from `rows` (the result of `get_candidates_for_challenge()`) BEFORE the per-candidate loop
  - [x] Call `get_dimension_scores_for_submissions(submission_ids)` exactly once
  - [x] Inside the loop, replace `db_service.get_dimension_scores(submission_id)` with `dims_by_submission.get(submission_id, [])`
  - [x] Leave the `dimensions = {r[0]: {'score': r[1], 'rationale': r[2]} for r in dim_rows}` line and everything after it (sort, rank, `dimension_averages`, `is_flagged`) completely untouched — this story changes ONLY how `dim_rows` is obtained, nothing downstream
- [x] Add a test proving exactly one call to `get_dimension_scores_for_submissions` per request regardless of candidate count (AC: 1) — spy on the method, assert `len(calls) == 1`
- [x] Add a test with ≥3 evaluated candidates carrying distinct per-dimension scores, asserting each candidate's `dimensions` dict matches only its own scores (AC: 3)
- [x] Run the full existing `tests/test_candidates_endpoint.py` file unmodified and confirm 100% green (AC: 2)

### Review Findings

- [x] [Review][Defer] Unbounded `IN (...)` placeholder count in `get_dimension_scores_for_submissions` — no chunking/batching of the parameter list, so a single challenge/assignment whose candidate count exceeds SQLite's host-parameter ceiling (verified empirically at 32766 in this environment's bundled SQLite 3.50.4) would raise an uncaught `sqlite3.OperationalError` and 500 the entire `/candidates` endpoint, a failure mode the old N+1 code could never hit (confirmed by both Blind Hunter and Edge Case Hunter review layers). Not exercised by any test (both test files cap out at 3 candidates). Far outside this story's tested/intended scale (AC1 only specifies correctness at 0/1/50 candidates) — not blocking finalization. [app/services/database_service.py:280] — deferred, pre-existing risk class introduced at a scale far beyond current design intent
- [x] [Review][Defer] `is_flagged` is present on the `challenges.py` candidates payload but the `assignments.py` sibling endpoint (batched in this same story) was not given the equivalent field, despite the new `test_assignments_candidates_endpoint.py` docstring describing the two endpoints as being kept in lockstep (Blind Hunter finding). The `is_flagged` field itself predates Story 9.1 (added by a separate party-mode triage item scoped only to `challenges.py`) — this is a pre-existing parity gap between the two endpoints, not something this story's batching change introduced or was scoped to fix. [app/routes/assignments.py:94] — deferred, pre-existing scope gap unrelated to this story's batching change
- [x] [Review][Defer] If `get_candidates_for_challenge`/`get_candidates_for_assignment` ever returned more than one row for the same `submission_id` (e.g. a re-evaluated submission with a stale prior `hire_evaluations` row, since `hire_evaluations.submission_id` has no `UNIQUE` constraint), `submission_ids = [row[0] for row in rows]` would pass the duplicate straight into the `IN (...)` list unfiltered, needlessly consuming parameter budget (Edge Case Hunter finding). Result would still be correct (dict keys collapse) — this is a contributing factor to the placeholder-ceiling finding above, not a correctness bug on its own, and depends on a scenario not currently reachable via the app's actual code paths. [app/services/database_service.py:280] — deferred, contingent on an unenforced schema invariant not observed in practice

## Dev Notes

### Why this exists

Flagged in Story 4.2's original code review (2026-07-02) as an accepted-for-now N+1 pattern with "no pagination AC." Re-triaged 2026-07-04 via a `bmad-party-mode` session (John/PM, Winston/Architect, Amelia/Dev) that reviewed every item in `deferred-work.md` — this was judged real (a genuine perf cliff at 100+ candidates) but not urgent, and specifically **not** safe as a bare drive-by patch: Winston's condition for greenlighting it was that the rewrite ship with a test proving the **visibility floor** (`math.inf`/`-math.inf` sentinel — un-evaluated candidates always sort last) survives, since a naive `LEFT JOIN`-based rewrite could easily change how missing-score rows come back and silently break that guarantee. This story's design avoids that risk entirely by NOT touching the ranking/sort query at all — see "Why this design has near-zero regression risk" below.

### Current code (read this before touching anything — this is the CURRENT working-tree state, already includes this session's uncommitted `is_flagged` column addition)

`app/routes/challenges.py`, `get_challenge_candidates()` (lines 212–276 as of this story's creation):

```python
@challenges_bp.route('/challenges/<challenge_id>/candidates', methods=['GET'])
def get_challenge_candidates(challenge_id):
    """Return all candidates for a challenge, ranked and filterable by sort_by/order"""
    if not db_service.get_challenge(challenge_id):
        return jsonify({'error': 'Challenge not found'}), 404

    sort_by = request.args.get('sort_by', 'composite_score')
    order   = request.args.get('order', 'desc')

    if sort_by not in VALID_SORT_FIELDS:
        return jsonify({'error': f'sort_by must be one of: {sorted(VALID_SORT_FIELDS)}'}), 400
    if order not in ('asc', 'desc'):
        return jsonify({'error': 'order must be asc or desc'}), 400

    rows = db_service.get_candidates_for_challenge(challenge_id)
    candidates = []
    for row in rows:
        submission_id = row[0]
        dim_rows = db_service.get_dimension_scores(submission_id)   # <-- N+1: one query per row
        dimensions = {r[0]: {'score': r[1], 'rationale': r[2]} for r in dim_rows}
        candidates.append({
            'submission_id':            row[0],
            'link_id':                  row[1],
            'submitted_at':             row[2],
            'score':                    row[3],
            'composite_score':          row[4],
            'hire_recommendation':      row[5],
            'recommendation_rationale': row[6],
            'evaluated_at':             row[7],
            'is_evaluated':             row[7] is not None,
            'is_flagged':               bool(row[8]),
            'dimensions':               dimensions,
        })

    # Sort by requested field (Python-side — dimension scores are in a separate table)
    # Un-evaluated candidates (None values) always sort to the end regardless of direction.
    reverse = (order == 'desc')
    def sort_key(c):
        if sort_by == 'composite_score':
            val = c.get('composite_score')
        else:
            val = c.get('dimensions', {}).get(sort_by, {}).get('score')
        if val is None:
            return -math.inf if reverse else math.inf
        return float(val)
    candidates.sort(key=sort_key, reverse=reverse)

    # Assign rank after sort
    for i, c in enumerate(candidates, 1):
        c['rank'] = i

    # Dimension averages across evaluated candidates only.
    evaluated = [c for c in candidates if c['is_evaluated']]
    dim_averages = {}
    if evaluated:
        for dim in DIM_KEYS:
            scores = [
                c['dimensions'][dim]['score']
                for c in evaluated
                if dim in c['dimensions'] and c['dimensions'][dim].get('score') is not None
            ]
            if scores:
                dim_averages[dim] = round(sum(scores) / len(scores), 1)

    return jsonify({
        'challenge_id':       challenge_id,
        'candidates':         candidates,
        'total':              len(candidates),
        'dimension_averages': dim_averages,
    }), 200
```

`app/services/database_service.py`, `get_dimension_scores()` (lines 227–237, the per-submission method — DO NOT delete, still used elsewhere, see below):

```python
def get_dimension_scores(self, submission_id):
    """Return all dimension scores for a submission as a list of rows"""
    with self.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT dimension, score, rationale, scoring_method, scored_at
            FROM dimension_scores
            WHERE submission_id = ?
            ORDER BY dimension ASC
        ''', (submission_id,))
        return cursor.fetchall()
```

### Why this design has near-zero regression risk

The visibility-floor sort (`sort_key()`, the `-math.inf`/`math.inf` sentinel) operates on `c['composite_score']` (from `row[4]`, untouched by this story) and `c['dimensions'][sort_by]['score']` (built from `dim_rows`, whose SOURCE changes but whose per-candidate CONTENT does not). This story changes only how `dim_rows` is fetched — from N queries to 1 — and changes nothing about `get_candidates_for_challenge()`'s own query, the sort logic, the rank assignment, or `dimension_averages`. If the batched grouping correctly reproduces "the same rows `get_dimension_scores(submission_id)` would have returned, just fetched together," everything downstream is provably unaffected. Do not "improve" the sort/JOIN logic as part of this story — that is explicitly out of scope and is exactly the kind of change Winston's review flagged as risky.

### New method — exact implementation

Add directly below the existing `get_dimension_scores()` method in `app/services/database_service.py`:

```python
def get_dimension_scores_for_submissions(self, submission_ids):
    """Batch-fetch dimension scores for multiple submissions in one query,
    grouped by submission_id — avoids the N+1 pattern in candidate ranking
    (see deferred-work.md / Story 9.1). Each value has the same row shape
    get_dimension_scores() returns (dimension, score, rationale,
    scoring_method, scored_at), just grouped instead of pre-filtered.
    """
    if not submission_ids:
        return {}
    with self.db.get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(submission_ids))
        cursor.execute(f'''
            SELECT submission_id, dimension, score, rationale, scoring_method, scored_at
            FROM dimension_scores
            WHERE submission_id IN ({placeholders})
            ORDER BY submission_id, dimension ASC
        ''', submission_ids)
        rows = cursor.fetchall()
    grouped = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row[1:])
    return grouped
```

Note the `f'...IN ({placeholders})...'` — `placeholders` is built from `'?' * len(submission_ids)`, never from user input, so this is not a SQL-injection risk (matches the existing parameterized-query convention everywhere else in this file).

### Updated route logic — exact diff shape

In `get_challenge_candidates()`, replace:

```python
    rows = db_service.get_candidates_for_challenge(challenge_id)
    candidates = []
    for row in rows:
        submission_id = row[0]
        dim_rows = db_service.get_dimension_scores(submission_id)
        dimensions = {r[0]: {'score': r[1], 'rationale': r[2]} for r in dim_rows}
```

with:

```python
    rows = db_service.get_candidates_for_challenge(challenge_id)
    submission_ids = [row[0] for row in rows]
    dims_by_submission = db_service.get_dimension_scores_for_submissions(submission_ids)
    candidates = []
    for row in rows:
        submission_id = row[0]
        dim_rows = dims_by_submission.get(submission_id, [])
        dimensions = {r[0]: {'score': r[1], 'rationale': r[2]} for r in dim_rows}
```

Everything from `candidates.append({...})` onward is UNCHANGED — do not touch it.

### Known sibling occurrence — explicitly OUT OF SCOPE for this story

`app/routes/assignments.py:90` has the exact same N+1 pattern (`GET /api/assignments/<assignment_id>/candidates` calls `db_service.get_dimension_scores(submission_id)` per row). This was NOT part of the deferred-work.md finding that created Epic 9 (which named only `app/routes/challenges.py:215`), and the party-mode triage did not evaluate it. Do not fix it as part of this story — flag it as a new deferred-work.md entry instead if you notice it during implementation, so a future story can decide whether to batch it too (it may warrant the identical fix, or may be low-traffic enough not to matter — that's a separate triage decision).

### Testing

Existing coverage lives in `tests/test_candidates_endpoint.py` (uses the `client`/`db` fixture pattern — real Flask test client + isolated tmp-path SQLite, `db_service.db` monkeypatched directly since `challenges_module.db_service` is an import-time singleton). Add new tests to this same file, following its existing `make_challenge()` / `make_evaluated_candidate()` / `make_unevaluated_candidate()` helpers — do not re-derive fixtures.

**New test 1 — exactly one batched call regardless of cohort size:**
```python
def test_dimension_scores_fetched_in_one_batched_call(client, db, monkeypatch):
    challenge_id = make_challenge(db)
    make_evaluated_candidate(db, challenge_id, 90)
    make_evaluated_candidate(db, challenge_id, 70)
    make_evaluated_candidate(db, challenge_id, 50)

    calls = []
    original = db.get_dimension_scores_for_submissions
    def spy(submission_ids):
        calls.append(submission_ids)
        return original(submission_ids)
    monkeypatch.setattr(db, "get_dimension_scores_for_submissions", spy)

    resp = client.get(f"/api/challenges/{challenge_id}/candidates")
    assert resp.status_code == 200
    assert len(calls) == 1
    assert len(calls[0]) == 3
```

**New test 2 — no cross-candidate contamination:**
```python
def test_batched_dimension_scores_attributed_to_correct_candidate(client, db):
    challenge_id = make_challenge(db)
    sub_a = make_evaluated_candidate(db, challenge_id, 80,
        dimension_scores={d: 10 for d in ALL_DIMS})
    sub_b = make_evaluated_candidate(db, challenge_id, 80,
        dimension_scores={d: 90 for d in ALL_DIMS})
    sub_c = make_evaluated_candidate(db, challenge_id, 80,
        dimension_scores={d: 50 for d in ALL_DIMS})

    resp = client.get(f"/api/challenges/{challenge_id}/candidates")
    by_id = {c["submission_id"]: c for c in resp.get_json()["candidates"]}
    assert by_id[sub_a]["dimensions"]["problem_decomposition"]["score"] == 10
    assert by_id[sub_b]["dimensions"]["problem_decomposition"]["score"] == 90
    assert by_id[sub_c]["dimensions"]["problem_decomposition"]["score"] == 50
```

Then run the ENTIRE file (`python -m pytest tests/test_candidates_endpoint.py -v`) and confirm all pre-existing tests pass with no modification — that full-file green run IS acceptance criterion 2, not a nice-to-have.

### Project Structure Notes

- New method goes in `app/services/database_service.py`, directly after `get_dimension_scores()` — keeps the single-fetch and batch-fetch variants adjacent for discoverability.
- No new files. No new routes. No schema changes.
- `app/routes/assignments.py`'s sibling endpoint is untouched (see "Known sibling occurrence" above).

### References

- Original finding: Story 4.2 code review, 2026-07-02 (`_bmad-output/implementation-artifacts/4-2-candidate-comparison-endpoint.md`, "Review Findings" section, `[Review][Defer]` N+1 entry)
- Party-mode re-triage: `_bmad-output/implementation-artifacts/deferred-work.md`, "Deferred from: code review of Epic 4 stories 4.1–4.5" section, and the "Resolved 2026-07-04" section's note that this item moved to Epic 9
- Epic scope: `_bmad-output/implementation-artifacts/sprint-status.yaml` → `epic-9` → `9-1-batch-dimension-score-queries-in-candidates-endpoint`
- Current route: `app/routes/challenges.py` lines 212–276
- Current DB method to extend: `app/services/database_service.py` lines 227–237 (`get_dimension_scores`) and lines 289–310 (`get_candidates_for_challenge`, which already includes the `is_flagged` column added this session — do not re-touch that query)
- Existing tests to preserve unmodified: `tests/test_candidates_endpoint.py` (all 15 tests as of this story's creation, including `test_flagged_candidate_marked_in_payload_but_not_hidden` added this session)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Red-first: added the two new tests before touching source; `test_dimension_scores_fetched_in_one_batched_call` failed with
  `AttributeError: 'DatabaseService' object has no attribute 'get_dimension_scores_for_submissions'` as expected (the method
  didn't exist yet). `test_batched_dimension_scores_attributed_to_correct_candidate` and `test_zero_candidates_returns_empty_without_crash`
  already passed against the old N+1 code (expected — they test observable behavior, not query count; they became stronger
  regression guards once the batched method landed).
- Implemented `get_dimension_scores_for_submissions()` exactly as specified in Dev Notes, then rewired
  `get_challenge_candidates()`'s three lines per the exact diff shown — no other line in that function touched.
- `tests/test_candidates_endpoint.py` full file: 17/17 passed (14 pre-existing unmodified + 3 new).
- Full suite: 95/95 passed (92 before this story + 3 new), zero regressions.
- Confirmed the sibling N+1 in `app/routes/assignments.py:90` (`GET /api/assignments/<assignment_id>/candidates`) noted in Dev
  Notes as out-of-scope — left untouched, logged as a new `deferred-work.md` entry per the story's own instruction.

### Completion Notes List

- Added `DatabaseService.get_dimension_scores_for_submissions(submission_ids)` in `app/services/database_service.py`, directly
  below `get_dimension_scores()`: one `WHERE submission_id IN (...)` query, results grouped into
  `{submission_id: [(dimension, score, rationale, scoring_method, scored_at), ...]}`; empty-input guard returns `{}` without
  querying (sqlite3 can't bind an empty `IN` list).
- `get_challenge_candidates()` in `app/routes/challenges.py` now collects all `submission_id`s up front and calls the batched
  method once instead of once per candidate. Sort, rank, `dimension_averages`, and `is_flagged` logic — all untouched, as
  specified, since they only depend on the per-candidate `dimensions` dict shape, which is unchanged.
- `get_dimension_scores()` (single-submission) left in place — still used by `app/routes/assignments.py` and
  `app/routes/submissions.py`.
- All 5 acceptance criteria verified: AC1 (one batched call — new spy test), AC2 (all 14 pre-existing
  `test_candidates_endpoint.py` tests pass unmodified, including the visibility-floor and `is_flagged` tests named in the AC),
  AC3 (new cross-candidate-attribution test), AC4 (new zero-candidates test, plus the pre-existing
  `test_challenge_with_no_candidates_returns_empty_list` also now exercises the empty-list guard), AC5 (response shape
  unchanged — same field set, same test assertions on shape pass unmodified).

### Post-Review Follow-Up (2026-07-04)

Code review of this story re-raised the `assignments.py:90` sibling N+1 (originally logged as deliberately out of scope, above) since the exact fix was already written and tested. User elected to apply it same-day rather than wait for a future story: `get_candidates()` in `app/routes/assignments.py` now uses `get_dimension_scores_for_submissions()` with the identical pattern. New test file `tests/test_assignments_candidates_endpoint.py` (6 tests — this endpoint had zero test coverage before). Full suite: 101/101 passing. `deferred-work.md` updated to mark the sibling finding resolved.

### File List

- app/services/database_service.py
- app/routes/challenges.py
- app/routes/assignments.py (post-review follow-up)
- tests/test_candidates_endpoint.py
- tests/test_assignments_candidates_endpoint.py (post-review follow-up, new file)
- _bmad-output/implementation-artifacts/deferred-work.md
