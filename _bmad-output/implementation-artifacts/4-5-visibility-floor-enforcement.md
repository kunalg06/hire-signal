# Story 4.5: Visibility Floor Enforcement

Status: done

## Story

As an employer,
I want every candidate who submitted to a challenge to appear in the ranked list regardless of their score,
so that low-scoring candidates are visible for context and I always have the full picture.

## Acceptance Criteria

1. `GET /api/challenges/<id>/candidates` returns ALL submitted candidates — no score-based exclusion.
2. Candidates without a completed evaluation (no `hire_evaluations` row) always appear at the END of the sorted list regardless of `order` direction (asc or desc).
3. Each candidate in the response includes an `is_evaluated` boolean: `true` if `evaluated_at` is populated, `false` otherwise.
4. A candidate with composite_score=10/100 appears ranked last among evaluated candidates, not absent.
5. Returns `{"candidates": [], "total": 0, "dimension_averages": {}}` when no submissions exist — never 500.
6. Existing sort_by and order query param behaviour is unchanged for evaluated candidates.

## Tasks / Subtasks

- [x] Fix sort_key sentinel for un-evaluated candidates in `challenges.py` (AC: 2)
  - [x] Replace `or 0` fallback with `float('-inf')` (desc) or `float('inf')` (asc) so un-evaluated always sort last
- [x] Add `is_evaluated` field to each candidate in the response (AC: 3)
  - [x] `'is_evaluated': row[7] is not None` (row[7] is `evaluated_at` from the DB query)
- [x] Smoke test: low-score candidate ranked last, not absent (AC: 1, 4)
  - [x] Seed 2 evaluated candidates (scores 85 and 10), verify both appear, verify rank of score=10 is 2
  - [x] Seed 1 un-evaluated candidate alongside evaluated ones, verify it sorts last in both asc and desc

## Dev Notes

### File to Modify

Only `app/routes/challenges.py` — single function `get_challenge_candidates()`.

### Current Sort Key — The Bug

```python
# CURRENT (broken for asc order with un-evaluated candidates)
def sort_key(c):
    if sort_by == 'composite_score':
        return c.get('composite_score') or 0
    return c.get('dimensions', {}).get(sort_by, {}).get('score') or 0
```

When `order=asc` and a candidate has no composite_score (None → 0), they sort first
because 0 is less than any real score. They should always sort last.

### Fixed Sort Key

```python
import math  # add to top of file

def sort_key(c):
    if sort_by == 'composite_score':
        val = c.get('composite_score')
    else:
        val = c.get('dimensions', {}).get(sort_by, {}).get('score')
    if val is None:
        # Un-evaluated always last, regardless of direction
        return -math.inf if reverse else math.inf
    return float(val)
```

`math` is part of Python stdlib — no new dependency.

### `is_evaluated` Field

In the loop that builds candidates:
```python
candidates.append({
    ...
    'evaluated_at':  row[7],
    'is_evaluated':  row[7] is not None,   # ADD THIS
    'dimensions':    dimensions,
})
```

`row[7]` is `he.evaluated_at` from `get_candidates_for_challenge()` — NULL when no hire_evaluation row.

### What is Already Correct (DO NOT CHANGE)

- `get_candidates_for_challenge()` uses LEFT JOIN — all submissions appear. No change needed.
- 404 for unknown challenge_id — already correct.
- `dimension_averages` computed from evaluated candidates only — already correct.
- `rank` assigned after sort — already correct.
- `total` is len(candidates) before any filter — correct (shows all, not just evaluated).

### References

- `app/routes/challenges.py` `get_challenge_candidates()` — lines 196–253
- `app/services/database_service.py` `get_candidates_for_challenge()` — returns LEFT JOIN rows
- `row[7]` = `he.evaluated_at` (8th column in SELECT)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- sort_key `or 0` bug confirmed: in asc order, un-evaluated candidates (None→0) sorted FIRST — now fixed with math.inf sentinel
- `is_evaluated` derives from row[7] (he.evaluated_at) — NULL from LEFT JOIN when no hire_evaluation row
- Both desc and asc order tests pass: desc=[85, 10, None], asc=[10, 85, None]
- score=10 candidate confirmed present at rank 2 in desc, rank 1 in asc (visibility floor confirmed)

### Completion Notes List

- `import math` added to `challenges.py`
- sort_key sentinel: `float('-inf')` when reverse=True (desc), `float('inf')` when reverse=False (asc) — guarantees None values always sort last regardless of direction
- `is_evaluated: row[7] is not None` added to each candidate dict in `get_challenge_candidates()`
- No DB changes, no service changes — single route file modified

### File List

- app/routes/challenges.py
