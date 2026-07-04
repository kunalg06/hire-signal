"""Regression tests for POST /api/submissions/<id>/flag and .../override —
non-string JSON field values must 400 cleanly, not crash (party-mode
triage 2026-07-04 code review; see deferred-work.md).
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


# ── flag route ──────────────────────────────────────────────────────────────

def test_null_reason_returns_400_not_crash(client, db):
    submission_id = make_submission(db)
    resp = client.post(f"/api/submissions/{submission_id}/flag",
                       json={"reason": None})
    assert resp.status_code == 400
    assert "reason" in resp.get_json()["error"]


def test_non_string_reason_returns_400_not_crash(client, db):
    submission_id = make_submission(db)
    resp = client.post(f"/api/submissions/{submission_id}/flag",
                       json={"reason": 123})
    assert resp.status_code == 400
    assert "reason" in resp.get_json()["error"]


def test_non_string_flagged_by_falls_back_to_none(client, db):
    submission_id = make_submission(db)
    resp = client.post(f"/api/submissions/{submission_id}/flag",
                       json={"reason": "suspicious activity", "flagged_by": 42})
    assert resp.status_code == 200
    assert resp.get_json()["flag_by"] is None


# ── override route ───────────────────────────────────────────────────────────

def test_non_string_override_recommendation_returns_400_not_crash(client, db):
    submission_id = make_submission(db)
    resp = client.post(f"/api/submissions/{submission_id}/override",
                       json={"override_recommendation": 123,
                             "override_rationale": "looks fine"})
    assert resp.status_code == 400


def test_null_override_rationale_returns_400_not_crash(client, db):
    submission_id = make_submission(db)
    resp = client.post(f"/api/submissions/{submission_id}/override",
                       json={"override_recommendation": "hire",
                             "override_rationale": None})
    assert resp.status_code == 400
