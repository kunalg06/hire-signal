"""Story 9.2 — flag lifecycle audit trail tests.

No test file previously covered POST /api/submissions/<id>/flag at all.
Fixture pattern mirrors tests/test_submissions_flag_override_field_coercion.py:
real Flask test client + isolated tmp-path SQLite, db_service.db
monkeypatched directly since app.routes.submissions.db_service is an
import-time singleton.
"""
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
    # ORDER BY rowid, not flagged_at: SQLite's CURRENT_TIMESTAMP only has
    # 1-second resolution, so two flags in the same test can land in the
    # same second — rowid is monotonically increasing in insertion order
    # (this table has no WITHOUT ROWID clause), giving a deterministic sort.
    with db_service.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT reason, flagged_by FROM flag_events WHERE submission_id = ? ORDER BY rowid",
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
