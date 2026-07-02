# Story 4.2: Candidate Comparison Endpoint

Status: done

## Story

As a recruiter/employer,
I want a `GET /api/challenges/<challenge_id>/candidates` endpoint that returns all candidates who completed a given challenge,
so that I can see a ranked, filterable list with per-dimension scores and cohort averages to inform hiring decisions.

## Acceptance Criteria

1. `GET /api/challenges/<challenge_id>/candidates` returns HTTP 200 with `{ candidates: [], dimension_averages: {}, total: 0 }` when no submissions exist — never 404 or 500 on empty cohort.
2. Each candidate object contains: `rank`, `submission_id`, `link_id`, `submitted_at`, `score`, `composite_score`, `hire_recommendation`, `recommendation_rationale`, `evaluated_at`, `dimensions` (dict of 8 keys).
3. `dimension_averages` key is always present (empty dict `{}` when no evaluated candidates, populated dict when ≥1 evaluated).
4. `sort_by` query param accepts `composite_score` (default) or any of the 8 dimension keys; invalid value returns 400.
5. `order` query param accepts `desc` (default) or `asc`; invalid value returns 400.
6. Returns 404 with `{ "error": "Challenge not found" }` if `challenge_id` doesn't exist in the `challenges` table.
7. `assignments` table gains a nullable `challenge_id TEXT` column so assignments can be linked to catalog challenges.
8. `POST /api/assignments` accepts optional `challenge_id` field and stores it (ignored if omitted — backward compatible).

## Tasks / Subtasks

- [x] Add `challenge_id` column to `assignments` table via migration in `init_db()` (AC: 7)
  - [x] Use `try/except` ALTER TABLE pattern (SQLite has no `ALTER TABLE ... IF NOT EXISTS`)
  - [x] Place the migration block at the END of `init_db()`, after `conn.commit()`, in its own connection block
- [x] Update `DatabaseService.create_assignment()` to accept and store `challenge_id` (AC: 8)
  - [x] Add `challenge_id=None` as optional kwarg to signature
  - [x] Include `challenge_id` in the INSERT statement
- [x] Add `DatabaseService.get_candidates_for_challenge(challenge_id)` (AC: 1, 2, 3)
  - [x] Single SQL query JOINing submissions → assignments → hire_evaluations WHERE `a.challenge_id = ?`
  - [x] Order by `COALESCE(he.composite_score, s.score, 0) DESC` (Python-side re-sort handles sort_by param)
- [x] Update `POST /api/assignments` route handler to pass `challenge_id` (AC: 8)
  - [x] Extract optional `challenge_id` from request body
  - [x] Pass to `db_service.create_assignment()`
  - [x] Include in response JSON
- [x] Add `GET /api/challenges/<challenge_id>/candidates` endpoint to `challenges.py` (AC: 1–6)
  - [x] Validate `sort_by` param; return 400 on invalid
  - [x] Validate `order` param; return 400 on invalid
  - [x] 404 if challenge doesn't exist
  - [x] Fetch candidates via `get_candidates_for_challenge()`; fetch dimension scores per candidate (same N+1 pattern as existing)
  - [x] Python-sort by `sort_by` field after assembling candidates
  - [x] Compute `dimension_averages` across evaluated candidates only
  - [x] Always return `dimension_averages` key (empty dict if no evaluated candidates)
- [x] Smoke test: confirm existing `GET /api/assignments/<assignment_id>/candidates` still works (no regression) (AC: all)

## Dev Notes

### Architectural Context — Why This Story Requires a Schema Change

The existing system links submissions to **assignments**, not challenges directly:

```
challenges → (no FK) → assignments → session_links → submissions
```

`assignments` table currently has NO `challenge_id` column (confirmed in `app/models/database.py`).
Without it, `GET /api/challenges/<challenge_id>/candidates` cannot find any submissions.

**Solution:** Add nullable `challenge_id TEXT` column to `assignments` via `ALTER TABLE`.
Existing assignments remain unaffected (column defaults to NULL). New assignments created via
"Save as Assignment" from the catalog will pass `challenge_id`.

### Files to Modify (all UPDATE — no new files)

| File | Change |
|------|--------|
| `app/models/database.py` | Add ALTER TABLE migration for `challenge_id` column |
| `app/services/database_service.py` | Update `create_assignment()`, add `get_candidates_for_challenge()` |
| `app/routes/assignments.py` | Update POST handler to forward `challenge_id` |
| `app/routes/challenges.py` | Add new `GET /api/challenges/<challenge_id>/candidates` endpoint |

### Schema Migration — Exact Pattern

SQLite does NOT support `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Use try/except:

```python
# In init_db(), AFTER the existing conn.commit(), in a SEPARATE connection block:
try:
    with self.get_connection() as conn:
        conn.execute('ALTER TABLE assignments ADD COLUMN challenge_id TEXT')
        conn.commit()
except Exception:
    pass  # Column already exists — this is the expected path on subsequent startups
```

**Do NOT put this inside the main `init_db()` `with` block** — it must be a separate connection after the initial `conn.commit()` to avoid transaction conflicts.

### Updated `create_assignment()` Signature

Current signature (line 13 of `database_service.py`):
```python
def create_assignment(self, assignment_id, title, description, starter_code, evaluation_criteria):
```

New signature:
```python
def create_assignment(self, assignment_id, title, description, starter_code, evaluation_criteria, challenge_id=None):
```

Updated INSERT:
```python
cursor.execute('''
    INSERT INTO assignments (id, title, description, starter_code, evaluation_criteria, challenge_id)
    VALUES (?, ?, ?, ?, ?, ?)
''', (assignment_id, title, description, starter_code, evaluation_criteria, challenge_id))
```

### New DB Method — `get_candidates_for_challenge()`

```python
def get_candidates_for_challenge(self, challenge_id):
    """Return all submissions for a challenge (across all its assignments), ranked by composite score"""
    with self.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                s.submission_id,
                s.link_id,
                s.submitted_at,
                s.score,
                he.composite_score,
                he.recommendation,
                he.narrative,
                he.evaluated_at
            FROM submissions s
            JOIN assignments a ON s.assignment_id = a.id
            LEFT JOIN hire_evaluations he ON s.submission_id = he.submission_id
            WHERE a.challenge_id = ?
            ORDER BY COALESCE(he.composite_score, s.score, 0) DESC
        ''', (challenge_id,))
        return cursor.fetchall()
```

### New Route — `GET /api/challenges/<challenge_id>/candidates`

Add to `challenges.py` — follow the exact style of `get_candidates()` in `assignments.py:76–115`.

Valid sort_by values (defined as a constant):
```python
VALID_SORT_FIELDS = {'composite_score'} | set(DIM_KEYS)
```

Where `DIM_KEYS` is already defined in `assignments.py` — **copy the same list into `challenges.py`** (do NOT import from assignments; blueprints should be self-contained):

```python
DIM_KEYS = [
    'problem_decomposition', 'first_principles_thinking', 'creative_problem_solving',
    'iteration_quality', 'debugging_with_ai', 'architecture_decisions',
    'communication_clarity', 'token_efficiency',
]
```

Full endpoint logic:
```python
@challenges_bp.route('/challenges/<challenge_id>/candidates', methods=['GET'])
def get_challenge_candidates(challenge_id):
    # 1. Validate challenge exists
    if not db_service.get_challenge(challenge_id):
        return jsonify({'error': 'Challenge not found'}), 404

    # 2. Validate query params
    sort_by = request.args.get('sort_by', 'composite_score')
    order   = request.args.get('order', 'desc')
    VALID_SORT = {'composite_score'} | set(DIM_KEYS)
    if sort_by not in VALID_SORT:
        return jsonify({'error': f'sort_by must be one of: {sorted(VALID_SORT)}'}), 400
    if order not in ('asc', 'desc'):
        return jsonify({'error': 'order must be asc or desc'}), 400

    # 3. Fetch candidates
    rows = db_service.get_candidates_for_challenge(challenge_id)
    candidates = []
    for row in rows:
        submission_id = row[0]
        dim_rows = db_service.get_dimension_scores(submission_id)
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
            'dimensions':               dimensions,
        })

    # 4. Python-sort by sort_by (composite_score is top-level; dimensions are nested)
    reverse = (order == 'desc')
    def sort_key(c):
        if sort_by == 'composite_score':
            return c.get('composite_score') or 0
        return c.get('dimensions', {}).get(sort_by, {}).get('score') or 0
    candidates.sort(key=sort_key, reverse=reverse)

    # 5. Assign rank after sort
    for i, c in enumerate(candidates, 1):
        c['rank'] = i

    # 6. Dimension averages (evaluated = has at least one dimension score)
    evaluated = [c for c in candidates if c['dimensions']]
    dim_averages = {}
    if evaluated:
        for dim in DIM_KEYS:
            scores = [c['dimensions'].get(dim, {}).get('score', 0) for c in evaluated]
            dim_averages[dim] = round(sum(scores) / len(scores), 1)

    return jsonify({
        'challenge_id':       challenge_id,
        'candidates':         candidates,
        'total':              len(candidates),
        'dimension_averages': dim_averages,
    }), 200
```

### Existing Endpoint to Preserve (DO NOT BREAK)

`GET /api/assignments/<assignment_id>/candidates` in `assignments.py:76–115` must continue to work unchanged. This story adds a parallel challenge-scoped endpoint — it does NOT replace or modify the assignment-scoped one.

The frontend Tab 4 Results board uses the assignments endpoint — do not change its response shape.

### `POST /api/assignments` Update

Current handler (line 32–57 of `assignments.py`) calls:
```python
db_service.create_assignment(assignment_id, data.get('title'), ...)
```

Update to:
```python
challenge_id = data.get('challenge_id') or None  # None if omitted or empty string
db_service.create_assignment(
    assignment_id,
    data.get('title'),
    data.get('description', ''),
    data.get('starter_code', ''),
    data.get('evaluation_criteria'),
    challenge_id=challenge_id,
)
```

Add `"challenge_id": challenge_id` to the 201 response JSON.

### Project Structure Notes

- New endpoint lives in `challenges.py` (not a new file) — follows the pattern that challenge-catalog routes all live together
- `DIM_KEYS` constant duplicated in `challenges.py` — intentional, blueprints are self-contained
- No new imports needed in `challenges.py` beyond what's already there

### References

- Epic spec: `_bmad-output/planning-artifacts/epics-and-stories.md` → Epic 4, Story 4.2
- Existing candidates pattern: `app/routes/assignments.py` lines 76–115
- Existing challenge routes: `app/routes/challenges.py` (full file — add new endpoint after `delete_challenge`)
- DB method to mirror: `app/services/database_service.py` → `get_candidates_for_assignment()` (lines 240–259)
- Story 4.1 completion: `app/models/database.py` — `comparison_sessions` table added (9 tables total after 4.1)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Schema migration: `ALTER TABLE assignments ADD COLUMN challenge_id TEXT` — idempotent via try/except
- Service method: `get_candidates_for_challenge` — JOIN through assignments, verified 2-row result with correct ordering
- Endpoint: 404/400/200-empty all verified via Flask test client with patched db_service
- Sort by dimension (ASC/DESC) and rank assignment verified via Python sort logic
- Regression: `get_candidates_for_assignment` unchanged, still returns 1 row for its own assignment

### Completion Notes List

- Added `challenge_id TEXT` (nullable) to `assignments` via ALTER TABLE migration — backward compatible, existing rows keep NULL
- `create_assignment()` gains `challenge_id=None` kwarg — all existing callers unaffected
- `get_candidates_for_challenge()` JOINs through assignments to submissions/hire_evaluations in one query
- New `GET /api/challenges/<challenge_id>/candidates` in `challenges.py` — supports `sort_by` (9 valid values) and `order` (asc/desc), Python-side sort after N+1 dimension fetch
- `DIM_KEYS` and `VALID_SORT_FIELDS` constants added at module level in `challenges.py` — self-contained, not imported from assignments
- `dimension_averages` always returned (empty dict when no evaluated candidates — AC3 confirmed)
- Existing `GET /api/assignments/<assignment_id>/candidates` untouched — no regression

### Review Findings

- [x] [Review][Patch] dim_averages inflated/deflated: (a) filter uses dict truthiness not is_evaluated; (b) missing dimension scores counted as 0 instead of skipped [app/routes/challenges.py:248-253]
- [x] [Review][Defer] N+1 DB queries per candidate (one get_dimension_scores() per row, unbounded) [app/routes/challenges.py:215] — deferred, pre-existing design from Story 4.2; no pagination AC
- [x] [Review][Defer] Flagged candidates returned unfiltered in candidates endpoint; no is_flagged field in payload — deferred, pre-existing feature gap, not in any current AC

### File List

- app/models/database.py
- app/services/database_service.py
- app/routes/assignments.py
- app/routes/challenges.py
