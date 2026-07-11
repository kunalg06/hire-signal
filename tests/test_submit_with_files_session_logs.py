"""Integration test for POST /api/submit-with-files/<link_id>'s session-log
capture (2026-07-10 fix): confirms the corrected DockerService/SessionLogService
wiring actually persists real session_logs rows through the real route, not
just at the unit level (tests/test_session_log_capture.py covers the parsing
logic itself). Uses the same DB-isolation pattern as
tests/test_candidates_endpoint.py / tests/test_generate_challenge_endpoint.py
for this codebase's import-time db_service singleton trap.

The background evaluation/cleanup threads submit_with_files() spawns are
neutralized (EvaluationService.evaluate_code and DockerService.cleanup_container
mocked to no-ops) since this test only asserts on the SYNCHRONOUS part of the
route, which is where session_logs are actually written — before either
thread starts.
"""
import json

import pytest

import app.routes.submissions as submissions_module
from app.models.database import Database
from app.services.docker_service import DockerService
from app.services.evaluation_service import EvaluationService
from app.utils.helpers import IDGenerator


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = Database(str(tmp_path / "test.db"))
    test_db.init_db()
    monkeypatch.setattr(submissions_module.db_service, "db", test_db)
    monkeypatch.setattr(EvaluationService, "evaluate_code", lambda *a, **k: None)
    monkeypatch.setattr(DockerService, "cleanup_container", lambda *a, **k: None)
    monkeypatch.setattr(EvaluationService, "extract_container_files", lambda *a, **k: {})

    from app import create_app
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def db(client):
    return submissions_module.db_service


MAIN_SESSION = "\n".join([
    json.dumps({"sessionId": "s1", "projectHash": "h", "startTime": "t",
                "lastUpdated": "t", "kind": "main"}),
    json.dumps({"id": "u1", "timestamp": "2026-07-10T13:00:00.000Z", "type": "user",
                "content": [{"text": "What does is_even do?"}]}),
    json.dumps({"id": "g1", "timestamp": "2026-07-10T13:00:05.000Z", "type": "gemini",
                "content": "It checks divisibility by 2.",
                "tokens": {"input": 100, "output": 20, "total": 120}}),
])


def make_assignment_and_link(db_service):
    assignment_id = IDGenerator.generate_uuid()
    link_id = IDGenerator.generate_uuid()
    db_service.create_assignment(assignment_id, "Title", "Desc", "code", "criteria")
    db_service.create_session_link(link_id, assignment_id, container_id="fake-container",
                                    port=7100, expires_at="2099-01-01T00:00:00")
    return assignment_id, link_id


def test_submit_with_files_persists_real_session_logs(client, db, monkeypatch):
    _, link_id = make_assignment_and_link(db)
    monkeypatch.setattr(DockerService, "get_file_from_container",
                        lambda *a, **k: "print('solution')" if 'solution.py' in a[1] else None)
    monkeypatch.setattr(DockerService, "get_gemini_chat_files",
                        lambda *a, **k: {"chats/session-1.jsonl": MAIN_SESSION})

    res = client.post(f"/api/submit-with-files/{link_id}")
    assert res.status_code == 202
    body = res.get_json()
    assert body["session_logs_count"] == 1

    rows = db.get_session_logs(body["submission_id"])
    assert len(rows) == 1
    assert rows[0][2] == "What does is_even do?"        # prompt
    assert rows[0][3] == "It checks divisibility by 2."  # response_summary
    assert rows[0][5] == 120                             # token_count (party-mode review 2026-07-11)
    assert db.get_total_tokens_for_submission(body["submission_id"]) == 120


def test_submit_with_files_no_gemini_activity_stores_zero_logs(client, db, monkeypatch):
    """Sanity check: when get_gemini_chat_files() legitimately returns
    nothing (e.g. candidate never ran gemini), session_logs stays empty —
    this must not be confused with the old dead-code bug (which returned
    nothing to a check that was NEVER true even when it should have been)."""
    _, link_id = make_assignment_and_link(db)
    monkeypatch.setattr(DockerService, "get_file_from_container", lambda *a, **k: None)
    monkeypatch.setattr(DockerService, "get_gemini_chat_files", lambda *a, **k: {})

    res = client.post(f"/api/submit-with-files/{link_id}")
    assert res.status_code == 202
    assert res.get_json()["session_logs_count"] == 0


def test_submit_with_files_no_container_skips_gemini_capture_gracefully(client, db, monkeypatch):
    """No container (Docker unavailable) must not crash the route — must
    degrade to zero session logs, same as the existing solution.py/
    instructions.md graceful-degradation pattern."""
    assignment_id = IDGenerator.generate_uuid()
    link_id = IDGenerator.generate_uuid()
    db.create_assignment(assignment_id, "Title", "Desc", "code", "criteria")
    db.create_session_link(link_id, assignment_id, container_id=None,
                           port=None, expires_at="2099-01-01T00:00:00")

    res = client.post(f"/api/submit-with-files/{link_id}")
    assert res.status_code == 202
    assert res.get_json()["session_logs_count"] == 0
