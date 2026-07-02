# Story 4.1: Schema — Comparison Sessions

Status: done

## Story

As an employer/recruiter,
I want a `comparison_sessions` table that groups multiple candidate submissions under a named session,
so that I can track which candidates I'm comparing for the same challenge and reference that group later.

## Acceptance Criteria

1. `comparison_sessions` table exists in SQLite after app startup, created via `CREATE TABLE IF NOT EXISTS` — idempotent across restarts.
2. Table schema exactly matches the spec: `id`, `challenge_id`, `name`, `submission_ids_json`, `created_at` columns.
3. `challenge_id` references the `challenges` table (FK declared inline per existing project pattern).
4. `DatabaseService` exposes `create_comparison_session`, `get_comparison_session`, and `list_comparison_sessions` methods following existing service patterns.
5. No existing tables, routes, or DB behaviour are altered — additive change only.

## Tasks / Subtasks

- [x] Add `comparison_sessions` table to `init_db()` in `app/models/database.py` (AC: 1, 2, 3)
  - [x] Place the new `cursor.execute(...)` block after the `challenges` table block, before `conn.commit()`
  - [x] Match column order from spec: `id`, `challenge_id`, `name`, `submission_ids_json`, `created_at`
  - [x] Declare FK: `FOREIGN KEY(challenge_id) REFERENCES challenges(id)`
- [x] Add service methods to `app/services/database_service.py` (AC: 4)
  - [x] `create_comparison_session(session_id, challenge_id, name, submission_ids: list)` — `json.dumps(submission_ids)` before insert
  - [x] `get_comparison_session(session_id)` — returns raw row or None
  - [x] `list_comparison_sessions(challenge_id=None)` — optional filter; orders by `created_at DESC`
- [x] Manual smoke test: restart Flask, confirm no startup errors, confirm table appears in SQLite (AC: 1, 5)

## Dev Notes

### Files to Modify (both are UPDATE — do NOT create new files)

| File | Change |
|------|--------|
| `app/models/database.py` | Add table DDL inside `init_db()` — after challenges block, before `conn.commit()` |
| `app/services/database_service.py` | Add three CRUD methods following existing service patterns |

### Exact Table DDL (copy verbatim — no deviations)

```python
# Comparison sessions — group candidate submissions for side-by-side review
cursor.execute('''
    CREATE TABLE IF NOT EXISTS comparison_sessions (
        id TEXT PRIMARY KEY,
        challenge_id TEXT NOT NULL,
        name TEXT,
        submission_ids_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(challenge_id) REFERENCES challenges(id)
    )
''')
```

**Important:** SQLite does NOT enforce FK constraints by default. The existing codebase does not call `PRAGMA foreign_keys = ON` anywhere — do NOT add it. Declare the FK for documentation purposes only (consistent with all other tables).

### Service Method Signatures & Patterns

Follow the exact style of `create_challenge` / `get_challenge` / `list_challenges` already in `database_service.py`:

```python
def create_comparison_session(self, session_id, challenge_id, name, submission_ids):
    """Create a named comparison session grouping submissions for a challenge"""
    with self.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO comparison_sessions (id, challenge_id, name, submission_ids_json)
            VALUES (?, ?, ?, ?)
        ''', (session_id, challenge_id, name, json.dumps(submission_ids)))
        conn.commit()

def get_comparison_session(self, session_id):
    """Fetch a single comparison session by ID"""
    with self.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM comparison_sessions WHERE id = ?', (session_id,))
        return cursor.fetchone()

def list_comparison_sessions(self, challenge_id=None):
    """List comparison sessions, optionally filtered by challenge"""
    with self.db.get_connection() as conn:
        cursor = conn.cursor()
        if challenge_id:
            cursor.execute(
                'SELECT * FROM comparison_sessions WHERE challenge_id = ? ORDER BY created_at DESC',
                (challenge_id,)
            )
        else:
            cursor.execute('SELECT * FROM comparison_sessions ORDER BY created_at DESC')
        return cursor.fetchall()
```

**`json` is already imported at the top of `database_service.py` (line 2) — no new import needed.**

### ID Generation

When callers create sessions they use `IDGenerator.generate_uuid()` from `app/utils/helpers.py` (same as all other entities). This story does NOT add new routes — that is Story 4.2. The service methods are added here so Story 4.2 can call them without touching `database_service.py`.

### Existing Table Count After This Story

`init_db()` will then create 9 tables (was 8):
assignments, session_links, submissions, submission_files, session_logs, dimension_scores, hire_evaluations, challenges, **comparison_sessions**

### Known Gap — `score_overrides` Table

The Story 2.1 spec also included a `score_overrides` table, but it was never added to `database.py` (confirmed by reading the file). The `hire_evaluations` table covers per-submission override fields. `score_overrides` is used for aggregate analytics in Story 4.4 — add it there, not here, to keep this story narrowly scoped.

### Project Structure Notes

- All DB schema lives in `app/models/database.py` → `init_db()` only
- All DB queries live in `app/services/database_service.py` — no raw SQL in routes
- No migration tooling — `CREATE TABLE IF NOT EXISTS` is the migration strategy
- Do NOT modify `app/routes/` files in this story; routes come in Story 4.2

### References

- Epic spec: `_bmad-output/planning-artifacts/epics-and-stories.md` → Epic 4, Story 4.1
- Existing pattern: `app/models/database.py` lines 129–146 (`challenges` table — insert new table after this block)
- Existing pattern: `app/services/database_service.py` lines 262–328 (challenge service methods — mirror this style)
- ID generation: `app/utils/helpers.py` → `IDGenerator.generate_uuid()`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Smoke test confirmed 9 tables created, comparison_sessions columns and FK correct
- Service method tests: create, get, list-all, list-filtered, list-no-match, get-missing — all pass

### Completion Notes List

- Added `comparison_sessions` table DDL to `app/models/database.py` after challenges block (line ~144)
- Added three service methods to `app/services/database_service.py` under new `# Comparison session methods` section
- `submission_ids_json` serialised with `json.dumps` on write; callers use `json.loads` on read
- FK to `challenges` declared but not enforced at runtime (SQLite default; matches existing project pattern)
- No routes added — routes are Story 4.2's scope
- Noted: `score_overrides` table (from Story 2.1 spec) still missing; flagged for Story 4.4

### Review Findings

- [x] [Review][Patch] Migration silently swallows all exceptions, not just "column already exists" [app/models/database.py — ALTER TABLE blocks]

### File List

- app/models/database.py
- app/services/database_service.py
