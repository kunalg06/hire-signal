"""Story 9.5 — student preview routes.

Covers both the existing challenge-keyed preview (GET /student/preview/<challenge_id>,
previously untested) and the new assignment-keyed preview (GET /student/preview/assignment/<id>).

The challenge-keyed tests exist primarily to PIN current behavior before the
_render_student_preview_html() extraction refactor, proving the refactor is
byte-for-byte behavior preserving, not just "looks the same."

Fixture pattern mirrors tests/test_candidates_endpoint.py: real Flask test
client + isolated tmp-path SQLite, db_service.db monkeypatched directly since
app.routes.student.db_service is an import-time singleton.
"""
import pytest

import app.routes.student as student_module
from app.models.database import Database
from app.utils.helpers import IDGenerator


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = Database(str(tmp_path / "test.db"))
    test_db.init_db()
    monkeypatch.setattr(student_module.db_service, "db", test_db)

    from app import create_app
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def db(client):
    return student_module.db_service


def make_challenge(db_service, **overrides):
    challenge_id = IDGenerator.generate_uuid()
    fields = {
        "title": "Fix the Leaky Rate Limiter",
        "domain": "backend",
        "description": "A rate limiter is leaking memory under load.",
        "starter_code": "def rate_limit():\n    pass\n",
        "challenge_type": "bug_fix",
        "skill_area": "rate_limiting",
        "difficulty": "medium",
        "ai_assistance_mode": "unguarded",
        "evaluation_rubric_json": '{"criteria": "Fixes the leak without breaking throughput."}',
    }
    fields.update(overrides)
    db_service.create_challenge(challenge_id, fields["title"], fields["domain"],
        fields["description"], fields["starter_code"], fields["challenge_type"],
        fields["skill_area"], fields["difficulty"], fields["ai_assistance_mode"],
        fields["evaluation_rubric_json"])
    return challenge_id


def make_assignment(db_service, **overrides):
    assignment_id = IDGenerator.generate_uuid()
    fields = {
        "title": "Fix the Leaky Rate Limiter",
        "description": "A rate limiter is leaking memory under load.",
        "starter_code": "def rate_limit():\n    pass\n",
        "evaluation_criteria": "Fixes the leak without breaking throughput.",
        "challenge_id": None,
    }
    fields.update(overrides)
    db_service.create_assignment(assignment_id, fields["title"], fields["description"],
        fields["starter_code"], fields["evaluation_criteria"], fields["challenge_id"])
    return assignment_id


# ── Challenge-keyed preview (existing route — pinning tests) ───────────────

def test_challenge_preview_returns_200_with_expected_content(client, db):
    challenge_id = make_challenge(db)
    resp = client.get(f"/student/preview/{challenge_id}")
    assert resp.status_code == 200
    assert resp.content_type == "text/html; charset=utf-8"
    body = resp.get_data(as_text=True)
    assert "Fix the Leaky Rate Limiter" in body
    assert "A rate limiter is leaking memory under load." in body
    assert "Fixes the leak without breaking throughput." in body
    assert "def rate_limit():" in body
    assert "Preview Mode" in body
    assert "No session data is recorded" in body
    assert "Start Preview" in body


def test_challenge_preview_missing_id_returns_404(client, db):
    resp = client.get("/student/preview/does-not-exist")
    assert resp.status_code == 404
    assert resp.get_json() == {"detail": "Challenge not found"}


def test_challenge_preview_falls_back_to_default_criteria_text(client, db):
    challenge_id = make_challenge(db, evaluation_rubric_json=None)
    resp = client.get(f"/student/preview/{challenge_id}")
    assert resp.status_code == 200
    assert "Evaluation criteria set by employer." in resp.get_data(as_text=True)


# ── Assignment-keyed preview (new route) ────────────────────────────────────

def test_assignment_preview_returns_200_with_expected_content(client, db):
    assignment_id = make_assignment(db)
    resp = client.get(f"/student/preview/assignment/{assignment_id}")
    assert resp.status_code == 200
    assert resp.content_type == "text/html; charset=utf-8"
    body = resp.get_data(as_text=True)
    assert "Fix the Leaky Rate Limiter" in body
    assert "A rate limiter is leaking memory under load." in body
    assert "Fixes the leak without breaking throughput." in body
    assert "def rate_limit():" in body
    assert "Preview Mode" in body


def test_assignment_preview_missing_id_returns_404(client, db):
    resp = client.get("/student/preview/assignment/does-not-exist")
    assert resp.status_code == 404
    assert resp.get_json() == {"detail": "Assignment not found"}


def test_assignment_preview_falls_back_to_default_criteria_text(client, db):
    assignment_id = make_assignment(db, evaluation_criteria=None)
    resp = client.get(f"/student/preview/assignment/{assignment_id}")
    assert resp.status_code == 200
    assert "Evaluation criteria set by employer." in resp.get_data(as_text=True)


def test_assignment_preview_reflects_post_generation_edits(client, db):
    """The whole point of this story: an assignment edited after being
    generated from a challenge must show the EDITED text, not the
    challenge template's original text — proving the drift bug is fixed."""
    challenge_id = make_challenge(db, description="Original challenge description.")
    assignment_id = make_assignment(
        db, description="Original challenge description.", challenge_id=challenge_id)

    # Simulate an employer editing the assignment post-generation.
    with db.db.get_connection() as conn:
        conn.execute(
            "UPDATE assignments SET description = ? WHERE id = ?",
            ("Employer-edited description — now different from the challenge.", assignment_id))
        conn.commit()

    resp = client.get(f"/student/preview/assignment/{assignment_id}")
    body = resp.get_data(as_text=True)
    assert "Employer-edited description" in body
    assert "Original challenge description." not in body

    # The challenge-keyed preview still shows the ORIGINAL text — proving
    # the two previews are independent and the drift is real without this story.
    challenge_resp = client.get(f"/student/preview/{challenge_id}")
    assert "Original challenge description." in challenge_resp.get_data(as_text=True)
