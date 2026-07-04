"""Story 9.3 — GET /api/submission/<id_or_link> must surface
ai_assistance_mode and guarded_mode_enforced so an employer can tell whether
a "guarded" assessment actually had its GEMINI.md restriction applied.

Fixture pattern mirrors tests/test_flag_events_audit_trail.py: real Flask
test client + isolated tmp-path SQLite, db_service.db monkeypatched directly.
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


def make_submission(db_service, ai_assistance_mode=None, guarded_mode_enforced=None):
    assignment_id = IDGenerator.generate_uuid()
    link_id = IDGenerator.generate_uuid()
    submission_id = IDGenerator.generate_uuid()
    db_service.create_assignment(assignment_id, "T", "D", "code", "criteria")
    db_service.create_session_link(
        link_id, assignment_id, "container-x", 7100, "2099-01-01T00:00:00",
        ai_assistance_mode=ai_assistance_mode,
        guarded_mode_enforced=guarded_mode_enforced)
    db_service.create_submission(submission_id, link_id, assignment_id, "{}")
    return submission_id


def test_guarded_mode_enforced_true_visible_on_submission(client, db):
    submission_id = make_submission(db, ai_assistance_mode="guarded",
                                    guarded_mode_enforced=True)
    resp = client.get(f"/api/submission/{submission_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ai_assistance_mode"] == "guarded"
    assert body["guarded_mode_enforced"] is True


def test_guarded_mode_enforcement_failure_visible_on_submission(client, db):
    submission_id = make_submission(db, ai_assistance_mode="guarded",
                                    guarded_mode_enforced=False)
    resp = client.get(f"/api/submission/{submission_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ai_assistance_mode"] == "guarded"
    assert body["guarded_mode_enforced"] is False


def test_unguarded_mode_visible_on_submission(client, db):
    submission_id = make_submission(db, ai_assistance_mode="unguarded",
                                    guarded_mode_enforced=True)
    resp = client.get(f"/api/submission/{submission_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ai_assistance_mode"] == "unguarded"
    assert body["guarded_mode_enforced"] is True


def test_missing_session_link_columns_return_none(client, db):
    """A link created without these fields (or a pre-migration legacy row)
    must not crash the response — both fields simply come back None."""
    submission_id = make_submission(db)  # no ai_assistance_mode/guarded_mode_enforced passed
    resp = client.get(f"/api/submission/{submission_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ai_assistance_mode"] is None
    assert body["guarded_mode_enforced"] is None
