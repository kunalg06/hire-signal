# Story 4.3: Human Override + Flag for Manual Review

Status: done

## Story

As a recruiter/employer,
I want to flag a candidate submission for manual review and override the AI hire recommendation,
so that human judgment can correct or supplement AI scoring without losing the original AI verdict.

## Acceptance Criteria

1. `POST /api/submissions/<id>/flag` accepts `{ "reason": "...", "flagged_by": "..." }` and stores flag data in the `submissions` table; `reason` is required (400 if missing), `flagged_by` is optional.
2. `POST /api/submissions/<id>/override` accepts `{ "override_recommendation": "...", "override_rationale": "..." }` and updates the `hire_evaluations` row; both fields required (400 if either missing or empty).
3. `override_recommendation` must be one of `strong_hire | hire | select | pass`; 400 on invalid value.
4. Both endpoints return 404 if the submission doesn't exist.
5. `POST /api/submissions/<id>/override` returns 409 if no `hire_evaluations` row exists for the submission (cannot override a not-yet-evaluated submission).
6. Original AI `composite_score` and `recommendation` are NEVER modified — `is_overridden`, `override_recommendation`, `override_rationale` are the only columns written.
7. `GET /api/submission/<id>` response includes `is_flagged`, `flag_reason`, `flag_by`, `flagged_at` fields (existing endpoint, additive change only).
8. `submissions` table gains four nullable columns: `is_flagged INTEGER DEFAULT 0`, `flag_reason TEXT`, `flag_by TEXT`, `flagged_at TIMESTAMP`.

## Tasks / Subtasks

- [x] Add flag columns to `submissions` table via migrations in `app/models/database.py` (AC: 8)
  - [x] Four separate `ALTER TABLE submissions ADD COLUMN ...` statements in try/except blocks
  - [x] Place after the existing `challenge_id` migration block (already in place from Story 4.2)
- [x] Add `flag_submission()` and `override_hire_evaluation()` DB methods to `database_service.py` (AC: 1, 2, 6)
  - [x] `flag_submission(submission_id, reason, flagged_by)` — UPDATE submissions SET is_flagged=1, flag_reason, flag_by, flagged_at
  - [x] `override_hire_evaluation(submission_id, override_recommendation, override_rationale)` — UPDATE hire_evaluations SET is_overridden=1, override_recommendation, override_rationale; does NOT touch composite_score or recommendation
- [x] Update `get_submission()` DB method SELECT to include flag columns (AC: 7)
  - [x] Add `s.is_flagged, s.flag_reason, s.flag_by, s.flagged_at` to the SELECT
  - [x] Update the route handler in `submissions.py` to include flag fields in the GET response
- [x] Add `POST /api/submissions/<id>/flag` endpoint to `submissions.py` (AC: 1, 4)
  - [x] Validate `reason` present; 400 if missing
  - [x] 404 if submission not found
  - [x] Call `db_service.flag_submission()`; return 200 with confirmation
- [x] Add `POST /api/submissions/<id>/override` endpoint to `submissions.py` (AC: 2, 3, 4, 5, 6)
  - [x] Validate both fields present and non-empty; 400 if not
  - [x] Validate `override_recommendation` enum; 400 on invalid
  - [x] 404 if submission not found
  - [x] 409 if no hire_evaluation row exists
  - [x] Call `db_service.override_hire_evaluation()`; return 200 with updated hire data
- [x] Smoke test: flag a submission, override it, verify GET response includes both (AC: 1-8)

## Dev Notes

### Files to Modify (all UPDATE — no new files)

| File | Change |
|------|--------|
| `app/models/database.py` | Four ALTER TABLE migrations for flag columns |
| `app/services/database_service.py` | Two new methods + update `get_submission()` SELECT |
| `app/routes/submissions.py` | Two new endpoints + update GET response to expose flag fields |

### Schema Migration — Four Columns via try/except

Add after the existing `challenge_id` migration block in `init_db()` (currently the last block):

```python
for _col_sql in [
    'ALTER TABLE submissions ADD COLUMN is_flagged INTEGER DEFAULT 0',
    'ALTER TABLE submissions ADD COLUMN flag_reason TEXT',
    'ALTER TABLE submissions ADD COLUMN flag_by TEXT',
    'ALTER TABLE submissions ADD COLUMN flagged_at TIMESTAMP',
]:
    try:
        with self.get_connection() as conn:
            conn.execute(_col_sql)
            conn.commit()
    except Exception:
        pass  # Column already exists
```

SQLite `ALTER TABLE ADD COLUMN` with `DEFAULT 0` sets existing rows to 0 automatically.
SQLite only supports adding one column per ALTER TABLE — hence the loop.

### `hire_evaluations` Table — Existing Override Columns

The `hire_evaluations` table already has these columns (added in Story 2.1):
- `is_overridden INTEGER DEFAULT 0`
- `override_recommendation TEXT`
- `override_rationale TEXT`

**No schema migration needed for overrides.** Just write to these existing columns.
The columns `composite_score` and `recommendation` must NEVER be changed by this story.

### New DB Methods

```python
def flag_submission(self, submission_id, reason, flagged_by=None):
    """Flag a submission for manual review"""
    with self.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE submissions
            SET is_flagged = 1, flag_reason = ?, flag_by = ?, flagged_at = ?
            WHERE submission_id = ?
        ''', (reason, flagged_by, datetime.now().isoformat(), submission_id))
        conn.commit()
        return cursor.rowcount > 0

def override_hire_evaluation(self, submission_id, override_recommendation, override_rationale):
    """Apply human override to hire evaluation — original AI scores are preserved"""
    with self.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE hire_evaluations
            SET is_overridden = 1,
                override_recommendation = ?,
                override_rationale = ?
            WHERE submission_id = ?
        ''', (override_recommendation, override_rationale, submission_id))
        conn.commit()
        return cursor.rowcount > 0
```

`datetime` is already imported at the top of `database_service.py` (line 2).

### Updated `get_submission()` SELECT

Current query (line ~102 in `database_service.py`):
```python
SELECT s.submission_id, s.link_id, s.assignment_id, s.code, s.submitted_at,
       s.evaluation_result, s.score, s.feedback, a.title, a.evaluation_criteria
FROM submissions s JOIN assignments a ON s.assignment_id = a.id
WHERE s.submission_id = ?
```

Add four flag columns (append to SELECT — indices 10-13):
```python
SELECT s.submission_id, s.link_id, s.assignment_id, s.code, s.submitted_at,
       s.evaluation_result, s.score, s.feedback, a.title, a.evaluation_criteria,
       s.is_flagged, s.flag_reason, s.flag_by, s.flagged_at
FROM submissions s JOIN assignments a ON s.assignment_id = a.id
WHERE s.submission_id = ?
```

### Route Handler Updates for GET /api/submission/<id>

In `submissions.py` `get_submission()`, the `return jsonify(...)` block already returns `row[0]`–`row[8]`. Add after `"assignment_title": row[8]`:

```python
"evaluation_criteria": row[9],
# Flag status (new — from Story 4.3)
"is_flagged":  bool(row[10]) if row[10] is not None else False,
"flag_reason": row[11],
"flag_by":     row[12],
"flagged_at":  row[13],
```

Note: the existing response already has `"instructions_md"`, `"claude_logs"`, `"dimensions"`, `"hire_evaluation"` added after the SQL row — keep all of those. Only add the flag fields to the SQL row section.

### New Route Endpoints — Add to `submissions.py`

Valid override recommendations (define as constant near top of file):
```python
VALID_RECOMMENDATIONS = {'strong_hire', 'hire', 'select', 'pass'}
```

**Flag endpoint:**
```python
@submissions_bp.route('/submissions/<submission_id>/flag', methods=['POST'])
def flag_submission(submission_id):
    data = request.get_json() or {}
    reason = (data.get('reason') or '').strip()
    if not reason:
        return jsonify({'error': 'reason is required'}), 400

    row = db_service.get_submission(submission_id)
    if not row:
        return jsonify({'error': 'Submission not found'}), 404

    flagged_by = (data.get('flagged_by') or '').strip() or None
    db_service.flag_submission(submission_id, reason, flagged_by)
    return jsonify({
        'submission_id': submission_id,
        'is_flagged': True,
        'flag_reason': reason,
        'flag_by': flagged_by,
        'message': 'Submission flagged for manual review',
    }), 200
```

**Override endpoint:**
```python
@submissions_bp.route('/submissions/<submission_id>/override', methods=['POST'])
def override_submission(submission_id):
    data = request.get_json() or {}
    override_rec      = (data.get('override_recommendation') or '').strip()
    override_rationale = (data.get('override_rationale') or '').strip()

    if not override_rec or not override_rationale:
        return jsonify({'error': 'override_recommendation and override_rationale are both required'}), 400
    if override_rec not in VALID_RECOMMENDATIONS:
        return jsonify({'error': f'override_recommendation must be one of: {sorted(VALID_RECOMMENDATIONS)}'}), 400

    row = db_service.get_submission(submission_id)
    if not row:
        return jsonify({'error': 'Submission not found'}), 404

    hire_row = db_service.get_hire_evaluation(submission_id)
    if not hire_row:
        return jsonify({'error': 'No evaluation found for this submission — cannot override'}), 409

    db_service.override_hire_evaluation(submission_id, override_rec, override_rationale)
    return jsonify({
        'submission_id':           submission_id,
        'is_overridden':           True,
        'override_recommendation': override_rec,
        'override_rationale':      override_rationale,
        'original_composite_score':   hire_row[0],
        'original_recommendation':    hire_row[1],
        'message': 'Human override applied. Original AI score preserved.',
    }), 200
```

### Existing Code to Preserve (DO NOT BREAK)

- `GET /api/submission/<id>` response shape — additive only (add flag fields, touch nothing else)
- `hire_evaluations.composite_score` and `hire_evaluations.recommendation` — read-only in this story
- All other submission routes unchanged

### Route File Placement

Both new endpoints go into `app/routes/submissions.py`.
Add `VALID_RECOMMENDATIONS` constant near the top (after the Blueprint declaration, before route functions).
Add the two new endpoints after `get_submission_logs()` (currently the last function in the file).

### References

- Epic spec: `_bmad-output/planning-artifacts/epics-and-stories.md` → Epic 4, Story 4.3
- `hire_evaluations` schema: `app/models/database.py` lines 112–126 (override columns already exist)
- `get_submission()` query: `app/services/database_service.py` lines 100–111
- `get_hire_evaluation()`: `app/services/database_service.py` lines 225–238
- Existing flag column migrations will follow same pattern as `challenge_id` migration (Story 4.2) in `app/models/database.py`
- Story 4.4 note: `score_overrides` table (for analytics) is Story 4.4's job — do NOT add it here

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Schema: 4 flag columns added to submissions via ALTER TABLE loop — is_flagged DEFAULT 0 sets existing rows to 0 automatically
- flag_submission: rowcount check confirms only matching row updated; nonexistent ID returns False
- override_hire_evaluation: composite_score=75.0 and recommendation='hire' unchanged after override confirmed
- Flask endpoints: all 9 test cases passed — 400/404/409/200 all correct

### Completion Notes List

- Added `is_flagged`, `flag_reason`, `flag_by`, `flagged_at` to `submissions` via idempotent ALTER TABLE loop in `database.py`
- `hire_evaluations` override columns (`is_overridden`, `override_recommendation`, `override_rationale`) already existed from Story 2.1 — no schema work needed
- `get_submission()` SELECT updated to include 4 flag columns (indices 10–13); GET response extended with flag fields
- `VALID_RECOMMENDATIONS` constant at top of `submissions.py`; two new POST endpoints at bottom
- Original AI `composite_score` and `recommendation` confirmed unchanged after override (AC6)
- 409 returned when override attempted on unevaluated submission (AC5)

### Review Findings

- [x] [Review][Patch] Flag fields silently hidden when submission fetched by link_id — fallback query returns 9 cols, len(row) > 10 always False [app/routes/submissions.py:252-260]
- [x] [Review][Patch] flag_submission() / override_hire_evaluation() return values discarded — routes return 200 even when DB UPDATE affects 0 rows [app/routes/submissions.py:361,390]
- [x] [Review][Defer] Re-flagging overwrites prior flag metadata (flag_by, reason, flagged_at) with no audit log — deferred, mutable flag state by design; flag audit log would be a new story
- [x] [Review][Defer] flagged_by is caller-supplied with no auth — deferred, CLAUDE.md: no auth by design for dev system
- [x] [Review][Defer] Concurrent overrides both succeed, double-counting in score_overrides analytics — deferred, single-tenant dev system; no concurrency AC

### File List

- app/models/database.py
- app/services/database_service.py
- app/routes/submissions.py
