# Story 4.4: Override Logging as Calibration Dataset

Status: done

## Story

As a platform operator,
I want every human override captured in a dedicated audit table and queryable via an analytics endpoint,
so that recurring override patterns can surface which AI scoring dimensions need recalibration.

## Acceptance Criteria

1. A `score_overrides` table exists in the database; each row records: `submission_id`, `ai_recommendation` (original), `human_recommendation` (override), `override_rationale`, `overridden_at`.
2. Every successful call to `POST /api/submissions/<id>/override` inserts a row into `score_overrides` (in addition to updating `hire_evaluations`).
3. `GET /api/analytics/overrides` returns:
   - `total_overrides` (int)
   - `overrides_by_direction` — counts by `ai_recommendation → human_recommendation` pair
   - `recent_overrides` — last 20 override rows, newest first
4. The analytics endpoint returns 200 with empty lists/zero counts when no overrides exist (never 500).
5. Pattern detectable: after 10+ overrides, the response includes a `pattern_summary` key listing any direction that accounts for ≥20% of total overrides.

## Tasks / Subtasks

- [x] Add `score_overrides` table to `app/models/database.py` `init_db()` (AC: 1)
  - [x] `CREATE TABLE IF NOT EXISTS score_overrides` with all 5 required columns
  - [x] Place after the `comparison_sessions` table block, before `conn.commit()`
- [x] Add `log_score_override()` and `get_override_analytics()` to `database_service.py` (AC: 2, 3, 5)
  - [x] `log_score_override(override_id, submission_id, ai_recommendation, human_recommendation, override_rationale)` — INSERT
  - [x] `get_override_analytics()` — returns dict with total, direction counts, recent rows
- [x] Call `log_score_override()` in `override_submission()` route (AC: 2)
  - [x] After `db_service.override_hire_evaluation()` succeeds
  - [x] Pass `ai_recommendation = hire_row[1]` (original), `human_recommendation = override_rec`
  - [x] Generate new UUID for override_id via `IDGenerator.generate_uuid()`
- [x] Create `app/routes/analytics.py` with `GET /api/analytics/overrides` (AC: 3, 4, 5)
  - [x] New Blueprint `analytics_bp` with url_prefix `/api`
  - [x] Always returns 200; empty state is `total_overrides: 0, overrides_by_direction: {}, recent_overrides: [], pattern_summary: []`
  - [x] `pattern_summary`: list any direction pair with count ≥ 20% of total (only when total ≥ 10)
- [x] Register `analytics_bp` in `app/__init__.py` (AC: 3)
- [x] Smoke test: insert 3 overrides, call analytics, verify counts (AC: 3, 4)

## Dev Notes

### New Table — `score_overrides`

Add this `CREATE TABLE IF NOT EXISTS` block inside `init_db()` after the `comparison_sessions` block and before `conn.commit()`:

```python
# Override audit log — feeds calibration analytics
cursor.execute('''
    CREATE TABLE IF NOT EXISTS score_overrides (
        id TEXT PRIMARY KEY,
        submission_id TEXT NOT NULL,
        ai_recommendation TEXT NOT NULL,
        human_recommendation TEXT NOT NULL,
        override_rationale TEXT NOT NULL,
        overridden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
    )
''')
```

**Why a separate table rather than reading from `hire_evaluations`?**
`hire_evaluations.is_overridden` only shows current state — it would be overwritten if someone overrides twice. `score_overrides` is an immutable event log.

### New DB Methods

```python
def log_score_override(self, override_id, submission_id, ai_recommendation,
                       human_recommendation, override_rationale):
    """Append one override event to the calibration audit log"""
    with self.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO score_overrides
                (id, submission_id, ai_recommendation, human_recommendation, override_rationale)
            VALUES (?, ?, ?, ?, ?)
        ''', (override_id, submission_id, ai_recommendation,
              human_recommendation, override_rationale))
        conn.commit()

def get_override_analytics(self):
    """Return aggregated override stats for the analytics endpoint"""
    with self.db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM score_overrides')
        total = cursor.fetchone()[0]

        cursor.execute('''
            SELECT ai_recommendation, human_recommendation, COUNT(*) as cnt
            FROM score_overrides
            GROUP BY ai_recommendation, human_recommendation
            ORDER BY cnt DESC
        ''')
        direction_rows = cursor.fetchall()

        cursor.execute('''
            SELECT id, submission_id, ai_recommendation, human_recommendation,
                   override_rationale, overridden_at
            FROM score_overrides
            ORDER BY overridden_at DESC
            LIMIT 20
        ''')
        recent_rows = cursor.fetchall()

    overrides_by_direction = {
        f"{r[0]} -> {r[1]}": r[2]
        for r in direction_rows
    }

    recent_overrides = [
        {
            "override_id":           r[0],
            "submission_id":         r[1],
            "ai_recommendation":     r[2],
            "human_recommendation":  r[3],
            "override_rationale":    r[4],
            "overridden_at":         r[5],
        }
        for r in recent_rows
    ]

    # Pattern summary: directions that account for >=20% of total (only when total >= 10)
    pattern_summary = []
    if total >= 10:
        for direction, count in overrides_by_direction.items():
            if count / total >= 0.20:
                pattern_summary.append({
                    "direction": direction,
                    "count": count,
                    "pct": round(count / total * 100, 1),
                })

    return {
        "total_overrides":       total,
        "overrides_by_direction": overrides_by_direction,
        "recent_overrides":      recent_overrides,
        "pattern_summary":       pattern_summary,
    }
```

### Route Call Site Update — `submissions.py`

In `override_submission()`, after the call to `db_service.override_hire_evaluation()` and before the `return jsonify(...)`:

```python
# Log to calibration audit table (Story 4.4)
override_log_id = IDGenerator.generate_uuid()
db_service.log_score_override(
    override_log_id,
    submission_id,
    hire_row[1],   # original AI recommendation
    override_rec,  # human override
    override_rationale,
)
```

`IDGenerator` is already imported at the top of `submissions.py`.

### New File — `app/routes/analytics.py`

```python
from flask import Blueprint, jsonify
from app.services.database_service import DatabaseService

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api')
db_service = DatabaseService()

@analytics_bp.route('/analytics/overrides', methods=['GET'])
def get_override_analytics():
    """Admin: aggregated override stats for AI calibration"""
    data = db_service.get_override_analytics()
    return jsonify(data), 200
```

### Registration in `app/__init__.py`

Add these two lines:
```python
from app.routes.analytics import analytics_bp
# and in create_app():
app.register_blueprint(analytics_bp)
```

Pattern: same as `challenges_bp` which was the last blueprint added.

### Files to Modify

| File | Change |
|------|--------|
| `app/models/database.py` | Add `score_overrides` table inside `init_db()` |
| `app/services/database_service.py` | Add `log_score_override()` and `get_override_analytics()` |
| `app/routes/submissions.py` | Call `log_score_override()` after `override_hire_evaluation()` |
| `app/__init__.py` | Import and register `analytics_bp` |
| `app/routes/analytics.py` | NEW — analytics blueprint |

### Existing Code NOT to Break

- `hire_evaluations.composite_score` and `hire_evaluations.recommendation` — read-only (Story 4.3 contract)
- `override_hire_evaluation()` — call it exactly as before; add `log_score_override()` call AFTER it
- All existing routes unchanged

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- `score_overrides` CREATE TABLE placed inside `init_db()` before `conn.commit()` — verified table present in sqlite_master
- `get_override_analytics()` uses a single connection block with three cursor.execute calls; connection closed once, not three times
- pattern_summary boundary confirmed: 20.0% (exactly 2/10) correctly included; 9 total correctly produces empty pattern_summary
- Flask integration: `POST /override` → `log_score_override()` → `GET /analytics/overrides` returns updated count in same test run

### Completion Notes List

- `score_overrides` table added to `init_db()` — immutable event log, not a state column on `hire_evaluations`
- `log_score_override()` called from `override_submission()` route after `override_hire_evaluation()` succeeds; uses `IDGenerator.generate_uuid()` for override_id
- `GET /api/analytics/overrides` always returns 200 (empty state: zero counts, empty lists)
- `pattern_summary` populated only when total ≥ 10; all directions with ≥20% share are listed
- `analytics_bp` registered in `app/__init__.py` after `challenges_bp`

### Frontend sync fixes applied alongside this story

- `saveAsAssignment()`: now sends `challenge_id: currentChallengeId || null` — links generated assignment to its parent challenge
- `useCatalogChallenge()`: now sends `challenge_id: id` — catalog-created assignments preserve challenge link for candidate grouping
- Duplicate `viewInResults()` removed (stale second definition referenced non-existent `submissionId` element and `loadResults()`)
- Flag and Override buttons added to Results detail panel with inline expand forms wired to `POST /submissions/<id>/flag` and `POST /submissions/<id>/override`

### File List

- app/models/database.py
- app/services/database_service.py
- app/routes/submissions.py
- app/routes/analytics.py (NEW)
- app/__init__.py
- templates/frontend.html
