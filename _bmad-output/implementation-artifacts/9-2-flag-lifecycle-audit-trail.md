# Story 9.2: Flag Lifecycle Audit Trail

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a recruiter/employer who flags candidate submissions for manual review,
I want every flag event permanently recorded in an append-only audit log,
so that re-flagging a submission never silently loses the history of why it was flagged before, matching the same integrity guarantee overrides already have.

## Acceptance Criteria

1. New `flag_events` table exists, created idempotently via `CREATE TABLE IF NOT EXISTS` in `init_db()`, structurally mirroring `score_overrides` (append-only, never UPDATE/DELETE anywhere in the codebase).
2. `DatabaseService.flag_submission(submission_id, reason, flagged_by, event_id)` unconditionally inserts exactly one row into `flag_events` per successful flag (auto-generating `event_id` if the caller omits it) — no UPDATE, no DELETE, ever, on this table. (Revised 2026-07-06 finalization review: the standalone `log_flag_event()` method named in the original wording was folded directly into `flag_submission()` during the 2026-07-04 Post-Review Follow-Up, and the audit write was made unconditional — not merely caller-opt-in — during the finalization review, closing a gap where a caller omitting `event_id` produced zero audit rows.)
3. `POST /api/submissions/<id>/flag` logs one `flag_events` row on every successful flag, in addition to its existing behavior (unchanged).
4. Flagging the same submission twice (e.g. two different reasons) produces TWO rows in `flag_events` — proven by a test — not one overwritten row.
5. `submissions.flag_reason` / `flag_by` / `flagged_at` (the "current state" columns) still reflect only the LATEST flag after re-flagging — this existing last-value-wins behavior is UNCHANGED and must not be "fixed," since it mirrors the established `hire_evaluations` pattern (current-state columns + a separate append-only history table, `score_overrides`) already used for overrides.
6. No new query endpoint is added by this story — the fix is data preservation (stop losing flag history), not a new read surface. A future story can expose flag history via an endpoint if a real need emerges.

## Tasks / Subtasks

- [x] Add `flag_events` table to `init_db()` in `app/models/database.py` (AC: 1)
  - [x] Place it directly after the existing `score_overrides` table block, matching its exact column/constraint style
  - [x] `CREATE TABLE IF NOT EXISTS` — no ALTER TABLE migration needed, this is a brand-new table, not a new column on an existing table
- [x] Add `DatabaseService.log_flag_event(event_id, submission_id, reason, flagged_by)` in `app/services/database_service.py` (AC: 2)
  - [x] Place directly after `log_score_override()`, one INSERT statement, mirroring its exact pattern (no timestamp param — let the column's `DEFAULT CURRENT_TIMESTAMP` handle it, same as `score_overrides.overridden_at`)
- [x] Wire `db_service.log_flag_event(...)` into the `flag_submission()` route in `app/routes/submissions.py` (AC: 3)
  - [x] Call it AFTER the existing `db_service.flag_submission(...)` call succeeds — mirror exactly how `override_submission()` calls `log_score_override()` after `override_hire_evaluation()` succeeds
  - [x] Generate `event_id = IDGenerator.generate_uuid()` in the route, same as `override_log_id` is generated in `override_submission()`
- [x] Add test: flagging the same submission twice produces two distinct `flag_events` rows with the correct, respective reasons (AC: 4)
- [x] Add test: `submissions.flag_reason`/`flag_by`/`flagged_at` reflect only the latest flag after two flag calls — proves AC5's "unchanged" requirement explicitly, not just by omission
- [x] Add test: a single successful flag call produces exactly one `flag_events` row (baseline correctness, not just the re-flag case)
- [x] Run the full test suite and confirm no regressions

### Review Findings

- [x] [Review][Patch] Audit-log write is caller-opt-in, not method-enforced: `flag_submission(..., event_id=None)` only inserts into `flag_events` `if updated and event_id:` — any caller that omits `event_id` gets a fully successful flag with ZERO audit rows, silently. Confirmed as a REAL, currently-executing gap (not hypothetical): `tests/test_candidates_endpoint.py:286` calls `db.flag_submission(flagged_sub, "suspected plagiarism", flagged_by="employer-1")` with no `event_id` today. This is precisely the failure mode the story's own Post-Review hardening claims to have structurally eliminated — it only holds for the one route that remembers to pass the id (all 3 review layers — Blind Hunter, Edge Case Hunter, Acceptance Auditor — independently converged on this). Fixed: `flag_submission()` now generates `event_id` internally (`event_id or IDGenerator.generate_uuid()`) so the INSERT always fires whenever `updated` is true, regardless of what the caller passes. New test `test_flag_submission_audits_even_when_caller_omits_event_id` proves it. [app/services/database_service.py:118]
- [x] [Review][Patch] Same opt-in gap in `override_hire_evaluation(..., override_id=None)` — no current caller omits it, but nothing in the method prevented it. Additionally, `ai_recommendation=None` was incompatible with `score_overrides.ai_recommendation TEXT NOT NULL`: a caller passing `override_id` without `ai_recommendation` would have hit an uncaught `sqlite3.IntegrityError` instead of the route's intended graceful error. Fixed: `ai_recommendation` is now a required (no-default) parameter and `override_id` auto-generates internally the same way as the flag_submission fix above. [app/services/database_service.py:141]
- [x] [Review][Patch] No test exercised `override_hire_evaluation()`'s audit-log insert at the DB-row level — only route-level 200-status assertions existed for the override flow; nothing confirmed `score_overrides` actually receives a row post-9.2's refactor of this write path. Fixed: added `test_override_writes_a_score_overrides_row` to `tests/test_flag_events_audit_trail.py`. [tests/test_flag_events_audit_trail.py]
- [x] [Review][Patch] AC2's literal wording still named `DatabaseService.log_flag_event(event_id, submission_id, reason, flagged_by)` as a standalone method, but the Post-Review Follow-Up (2026-07-04, documented lower in this same file) folded its INSERT directly into `flag_submission()` instead. Fixed: AC2's text updated to describe the actual shipped interface. [this file, Acceptance Criteria section]
- [x] [Review][Defer] Uncaught `sqlite3.IntegrityError` if a caller ever reuses a duplicate `event_id`/`override_id` (both are `TEXT PRIMARY KEY`) — no rollback/retry handling, surfaces as an unhandled 500 rather than the route's graceful error response. Extremely low likelihood given UUID generation; matches the rest of the codebase's lack of DB-exception handling elsewhere in this file. [app/services/database_service.py:118] — deferred, pre-existing convention, extremely low practical likelihood
- [x] [Review][Defer] `hire_row[1]` is a brittle positional index for `ai_recommendation` in `override_submission()` — pre-existing pattern from Story 4.4, not introduced by this story. [app/routes/submissions.py:422] — deferred, pre-existing
- [x] [Review][Defer] No index on `flag_events.submission_id` — every audit-trail read does a full-table scan; benign at current scale and matches the existing convention (no other audit/history table in this schema is indexed either). [app/models/database.py:174] — deferred, benign-at-scale, convention-matching

## Dev Notes

### Why this exists

Originally flagged in the Epic 4 code review (2026-07-02): "Re-flagging overwrites prior flag metadata... Unlike overrides (which have `score_overrides` append-only log), flags have no audit trail." Re-triaged 2026-07-04 via `bmad-party-mode` (John/PM, Winston/Architect, Amelia/Dev): Winston's exact framing — "`is_flagged` is the `is_overridden` of the flagging world, and `flag_events` is the `score_overrides` of the flagging world. They coexist by design, not by accident." — pointing directly at `hire_evaluations` (current-state columns: `is_overridden`, `override_recommendation`, `override_rationale`) sitting next to the append-only `score_overrides` table as the exact precedent to copy. `is_flagged` visibility in the candidates payload was ALREADY shipped in Story 9.1's session (additive SELECT column, see `deferred-work.md`'s "Resolved 2026-07-04" section) — this story is ONLY the write-side audit trail, nothing else.

### Current code (read this before touching anything)

`app/models/database.py`, the `score_overrides` table — the EXACT pattern to mirror (lines 158–169):

```python
            # Override audit log — immutable event log for AI calibration analytics
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

            conn.commit()
```

Note `conn.commit()` immediately follows — `score_overrides` is the LAST table created inside the main `with self.get_connection() as conn:` block, before the function moves on to separate `try/except sqlite3.OperationalError` migration blocks for ALTER TABLE statements. `flag_events` is a NEW table (not a new column on an existing table), so it needs its own `CREATE TABLE IF NOT EXISTS` inside that same main block — NOT an ALTER TABLE migration block. Insert it directly before the `conn.commit()` line shown above.

`app/services/database_service.py`, `log_score_override()` — the EXACT pattern to mirror (lines 439–450):

```python
    def log_score_override(self, override_id, submission_id, ai_recommendation,
                           human_recommendation, override_rationale):
        """Append one override event to the immutable calibration audit log"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO score_overrides
                    (id, submission_id, ai_recommendation, human_recommendation, override_rationale)
                VALUES (?, ?, ?, ?, ?)
            ''', (override_id, submission_id, ai_recommendation,
                  human_recommendation, override_rationale))
            conn.commit()
```

`app/services/database_service.py`, `flag_submission()` — the CURRENT-STATE update, stays exactly as-is, do NOT modify (lines 114–124):

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
```

`app/routes/submissions.py`, `override_submission()` — the EXACT calling pattern to mirror for wiring the new audit log into the route (lines 383–423, the relevant excerpt):

```python
    if not db_service.override_hire_evaluation(submission_id, override_rec, override_rationale):
        return jsonify({'error': 'Failed to apply override'}), 500

    # Log to calibration audit table (Story 4.4)
    override_log_id = IDGenerator.generate_uuid()
    db_service.log_score_override(
        override_log_id,
        submission_id,
        hire_row[1],        # original AI recommendation
        override_rec,       # human override
        override_rationale,
    )
```

`app/routes/submissions.py`, `flag_submission()` route — CURRENT code to modify (lines 360–380):

```python
@submissions_bp.route('/submissions/<submission_id>/flag', methods=['POST'])
def flag_submission(submission_id):
    """Flag a submission for manual review"""
    data = request.get_json() or {}
    reason = _str_field(data, 'reason')
    if not reason:
        return jsonify({'error': 'reason is required'}), 400

    if not db_service.get_submission(submission_id):
        return jsonify({'error': 'Submission not found'}), 404

    flagged_by = _str_field(data, 'flagged_by') or None
    if not db_service.flag_submission(submission_id, reason, flagged_by):
        return jsonify({'error': 'Failed to flag submission'}), 500
    return jsonify({
        'submission_id': submission_id,
        'is_flagged':    True,
        'flag_reason':   reason,
        'flag_by':       flagged_by,
        'message':       'Submission flagged for manual review',
    }), 200
```

### New table — exact schema

Add to `app/models/database.py`'s `init_db()`, directly before the `conn.commit()` that follows `score_overrides`:

```python
            # Flag audit log — immutable event log for flag lifecycle history
            # (Story 9.2; mirrors score_overrides exactly — see deferred-work.md)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS flag_events (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    flagged_by TEXT,
                    flagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
                )
            ''')
```

Note `flagged_by` has no `NOT NULL` — matches the existing `submissions.flag_by` column, which is already nullable (an anonymous/unspecified flagger is valid, per the existing `flagged_by = _str_field(data, 'flagged_by') or None` route logic).

### New DB method — exact implementation

Add to `app/services/database_service.py`, directly after `log_score_override()`:

```python
    def log_flag_event(self, event_id, submission_id, reason, flagged_by=None):
        """Append one flag event to the immutable flag-lifecycle audit log
        (Story 9.2). Mirrors log_score_override() exactly — never
        UPDATE/DELETE this table."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO flag_events
                    (id, submission_id, reason, flagged_by)
                VALUES (?, ?, ?, ?)
            ''', (event_id, submission_id, reason, flagged_by))
            conn.commit()
```

### Updated route — exact diff shape

In `app/routes/submissions.py`'s `flag_submission()`, replace:

```python
    flagged_by = _str_field(data, 'flagged_by') or None
    if not db_service.flag_submission(submission_id, reason, flagged_by):
        return jsonify({'error': 'Failed to flag submission'}), 500
    return jsonify({
```

with:

```python
    flagged_by = _str_field(data, 'flagged_by') or None
    if not db_service.flag_submission(submission_id, reason, flagged_by):
        return jsonify({'error': 'Failed to flag submission'}), 500

    # Log to flag-lifecycle audit table (Story 9.2) — mirrors how
    # override_submission() logs to score_overrides after a successful override.
    event_id = IDGenerator.generate_uuid()
    db_service.log_flag_event(event_id, submission_id, reason, flagged_by)

    return jsonify({
```

`IDGenerator` is already imported in this file (used elsewhere for `override_log_id`, `submission_id`, etc.) — no new import needed.

### What NOT to do

- Do NOT add a `WHERE is_flagged = 0` guard to block re-flagging. That was the alternative option named in Epic 9's original scoping (`sprint-status.yaml`), but it's the WRONG choice given the override precedent: overrides don't block re-overriding, they log every one and let the current-state columns show the latest. Flags should behave identically for consistency.
- Do NOT change `flag_submission()`'s existing `UPDATE submissions SET is_flagged = 1, ...` behavior. The "overwrite" is not a bug once `flag_events` exists — it's the same intentional design as `hire_evaluations.override_recommendation` being overwritable while `score_overrides` keeps full history.
- Do NOT add a new `GET` endpoint for flag history in this story (see AC 6). Keep this story's diff to schema + one DB method + one route wiring change, matching how tightly-scoped Story 9.1 was.

### Testing

No existing test file covers `POST /api/submissions/<id>/flag` at all — `tests/test_submissions_flag_override_field_coercion.py` (added this session) only tests the non-string-field-coercion edge case, not the flag lifecycle itself. Create a new file `tests/test_flag_events_audit_trail.py`, following the exact `client`/`db` fixture pattern from `tests/test_submissions_flag_override_field_coercion.py` (real Flask test client + isolated tmp-path SQLite, `submissions_module.db_service.db` monkeypatched directly).

```python
import pytest

import app.routes.submissions as submissions_module
from app.models.database import Database
from app.utils.helpers import IDGenerator


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = Database(str(tmp_path / "test.db"))
    test_db.init_db()
    monkeypatch.setattr(submissions_module.db_service, "db", test_db)

    from app import create_app
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def db(client):
    return submissions_module.db_service


def make_submission(db_service):
    assignment_id = IDGenerator.generate_uuid()
    link_id = IDGenerator.generate_uuid()
    submission_id = IDGenerator.generate_uuid()
    db_service.create_assignment(assignment_id, "T", "D", "code", "criteria")
    db_service.create_session_link(link_id, assignment_id, "container-x", 7100,
                                   "2099-01-01T00:00:00")
    db_service.create_submission(submission_id, link_id, assignment_id, "{}")
    return submission_id


def _flag_event_rows(db_service, submission_id):
    with db_service.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT reason, flagged_by FROM flag_events WHERE submission_id = ? ORDER BY flagged_at",
            (submission_id,))
        return cursor.fetchall()


def test_single_flag_produces_one_event_row(client, db):
    submission_id = make_submission(db)
    resp = client.post(f"/api/submissions/{submission_id}/flag",
                       json={"reason": "suspected plagiarism", "flagged_by": "employer-1"})
    assert resp.status_code == 200
    rows = _flag_event_rows(db, submission_id)
    assert len(rows) == 1
    assert rows[0] == ("suspected plagiarism", "employer-1")


def test_reflagging_appends_a_second_event_row_not_overwrite(client, db):
    submission_id = make_submission(db)
    client.post(f"/api/submissions/{submission_id}/flag",
               json={"reason": "first reason", "flagged_by": "employer-1"})
    client.post(f"/api/submissions/{submission_id}/flag",
               json={"reason": "second reason", "flagged_by": "employer-2"})

    rows = _flag_event_rows(db, submission_id)
    assert len(rows) == 2
    assert rows[0] == ("first reason", "employer-1")
    assert rows[1] == ("second reason", "employer-2")


def test_reflagging_still_updates_current_state_to_latest(client, db):
    """AC5: the submissions table's current-state columns are UNCHANGED
    behavior — they show only the latest flag, same as before this story."""
    submission_id = make_submission(db)
    client.post(f"/api/submissions/{submission_id}/flag",
               json={"reason": "first reason", "flagged_by": "employer-1"})
    resp = client.post(f"/api/submissions/{submission_id}/flag",
                       json={"reason": "second reason", "flagged_by": "employer-2"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["flag_reason"] == "second reason"
    assert body["flag_by"] == "employer-2"

    # Confirm the same via GET /api/submission/<id> — the actual persisted state
    get_resp = client.get(f"/api/submission/{submission_id}")
    get_body = get_resp.get_json()
    assert get_body["flag_reason"] == "second reason"
    assert get_body["flag_by"] == "employer-2"
    # Only 2 flag_events rows exist despite the current-state column showing one value
    assert len(_flag_event_rows(db, submission_id)) == 2
```

Then run the full suite (`python -m pytest tests/ -q`) and confirm no regressions.

### Project Structure Notes

- New table goes in `app/models/database.py`'s main `init_db()` block (NOT a migration — `flag_events` is a brand-new table, so `CREATE TABLE IF NOT EXISTS` alone is sufficient and idempotent; no `ALTER TABLE` needed).
- New DB method goes in `app/services/database_service.py`, directly after `log_score_override()` — keeps the two audit-log methods adjacent.
- No new files except the new test file. No new routes. No changes to `app/routes/challenges.py` or Story 9.1's work.

### References

- Original finding: Epic 4 code review, 2026-07-02 (`_bmad-output/implementation-artifacts/deferred-work.md`, "Deferred from: code review of Epic 4 stories 4.1–4.5" section, "Re-flagging overwrites prior flag metadata" entry)
- Party-mode re-triage: `_bmad-output/implementation-artifacts/deferred-work.md`, "Resolved 2026-07-04 (bmad-party-mode triage...)" section — notes the `is_flagged` visibility half was already shipped, this story is the remaining audit-trail half
- Epic scope: `_bmad-output/implementation-artifacts/sprint-status.yaml` → `epic-9` → `9-2-flag-lifecycle-audit-trail`
- Pattern to mirror exactly: `score_overrides` table (`app/models/database.py` lines 158–169) + `log_score_override()` (`app/services/database_service.py` lines 439–450) + its call site in `override_submission()` (`app/routes/submissions.py` lines 405–413)
- Current route to modify: `app/routes/submissions.py` lines 360–380 (`flag_submission()`)
- Sibling story for testing-pattern reference: `9-1-batch-dimension-score-queries-in-candidates-endpoint.md` (same `client`/`db` fixture style, same red-first discipline)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Red-first: wrote `tests/test_flag_events_audit_trail.py` before touching source. All 3 tests failed with
  `sqlite3.OperationalError: no such table: flag_events` as expected (the table didn't exist yet).
- Implemented exactly per Dev Notes: `flag_events` table added to `init_db()` directly after `score_overrides`,
  `log_flag_event()` added directly after `log_score_override()`, and the route wired identically to how
  `override_submission()` calls `log_score_override()`.
- All 3 new tests passed on first run post-implementation — no iteration needed since the pattern was copied
  exactly from the proven `score_overrides`/`log_score_override` precedent.
- Full suite: 104/104 passed (101 before this story + 3 new), zero regressions.

### Completion Notes List

- Added `flag_events` table (`app/models/database.py`) — append-only, `CREATE TABLE IF NOT EXISTS`, structurally
  identical to `score_overrides` (`id, submission_id, reason, flagged_by, flagged_at DEFAULT CURRENT_TIMESTAMP`).
- Added `DatabaseService.log_flag_event(event_id, submission_id, reason, flagged_by=None)` — single INSERT, no
  UPDATE/DELETE anywhere touches this table.
- `flag_submission()` route in `app/routes/submissions.py` now calls `log_flag_event()` after a successful
  `db_service.flag_submission(...)` call, generating `event_id` via `IDGenerator.generate_uuid()` — identical
  pattern to the override route's `log_score_override()` call.
- Deliberately did NOT add a `WHERE is_flagged = 0` guard (would block re-flagging, inconsistent with how
  overrides behave) and did NOT add a new GET endpoint for flag history (out of scope per AC6 — data
  preservation only, not a new read surface).
- `flag_submission()`'s existing "last-value-wins" behavior on `submissions.flag_reason`/`flag_by`/`flagged_at`
  is completely unchanged — verified by a dedicated test, not just left alone by omission.
- All 6 acceptance criteria verified: AC1 (table exists, mirrors score_overrides), AC2 (single-INSERT method,
  no UPDATE/DELETE), AC3 (route logs on every successful flag), AC4 (two flags -> two rows, new test), AC5
  (current-state still shows latest, new test), AC6 (no new endpoint added).

### Post-Review Follow-Up (2026-07-04)

Code review of this story found 3 issues, all fixed same-day:
1. **Non-atomic write pair**: `flag_submission()` and `override_hire_evaluation()` originally did their state-mutating UPDATE and their audit-log INSERT as two separate connections/commits (mirroring `override_submission()`'s pre-existing pattern, per the story's own Dev Notes instruction) — a crash or transient DB error between the two could leave a flag/override applied with zero audit-trail row, the exact failure mode this story exists to prevent. Fixed by folding both writes into a single transaction: `flag_submission()` now accepts an optional `event_id` and `override_hire_evaluation()` now accepts optional `ai_recommendation`/`override_id`, each doing its UPDATE + INSERT on the same cursor before one `conn.commit()`. The standalone `log_score_override()`/`log_flag_event()` methods were removed (their logic folded in, not left as dead code) and both routes in `app/routes/submissions.py` updated accordingly. Fixed for BOTH the flag and override paths for consistency, not just the one this story added.
2. **Test ordering fragility**: `test_reflagging_appends_a_second_event_row_not_overwrite` relied on `ORDER BY flagged_at`, but SQLite's `CURRENT_TIMESTAMP` has only 1-second resolution — two flags in the same test can land in the same second. Fixed by ordering on `rowid` instead (monotonically increasing in insertion order for this non-`WITHOUT ROWID` table), a deterministic tie-breaker.
3. **CLAUDE.md schema docs were stale**: the "DB Schema" table count/list and the Architecture Constraints' append-only rules named `score_overrides` but not the new `flag_events` table, even though its own docstring asserts the identical invariant. Updated `CLAUDE.md`: table count 10→11, added the `flag_events` row, added its append-only constraint line.

### Finalization Code Review (2026-07-06)

3-layer review (Blind Hunter, Edge Case Hunter, Acceptance Auditor) found the "unconditional" audit-trail guarantee from the 2026-07-04 follow-up above was actually still caller-opt-in: `flag_submission(..., event_id=None)` and `override_hire_evaluation(..., ai_recommendation=None, override_id=None)` only wrote the audit row `if updated and event_id`/`override_id`, so any caller that forgot to pass the id got a fully successful flag/override with ZERO audit rows — and `tests/test_candidates_endpoint.py:286` was already doing exactly that. All 3 review layers independently converged on this same finding. Fixed:
1. `flag_submission()` now generates `event_id` internally (`event_id or IDGenerator.generate_uuid()`) and always inserts into `flag_events` when the update succeeds — no more silent skip.
2. `override_hire_evaluation()` — same fix for `override_id`, plus `ai_recommendation` changed from an optional `None` default to a required parameter (it's `NOT NULL` in `score_overrides` and has no safe default; leaving it optional risked an uncaught `sqlite3.IntegrityError` on any future caller that omitted it).
3. Added `test_flag_submission_audits_even_when_caller_omits_event_id` and `test_override_writes_a_score_overrides_row` to `tests/test_flag_events_audit_trail.py` — the override-audit path had zero DB-row-level test coverage before this pass.
4. Updated AC2's wording (it still named the removed standalone `log_flag_event()` method).

3 additional findings deferred (uncaught `IntegrityError` on duplicate id reuse, a pre-existing `hire_row[1]` positional-index brittleness from Story 4.4, no index on `flag_events.submission_id`) — logged to `deferred-work.md`. Full suite: 118/118 passing (116 before this pass + 2 new).

Full suite: 104/104 passing after all three fixes.

### File List

- app/models/database.py
- app/services/database_service.py
- app/routes/submissions.py
- tests/test_flag_events_audit_trail.py (new file)
- CLAUDE.md (post-review follow-up)
