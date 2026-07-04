"""Tests for POST /api/generate-link/<assignment_id> — ai_assistance_mode
whitelist (party-mode triage 2026-07-04; see deferred-work.md).

DockerService.create_container/inject_workspace_files are monkeypatched so
no real Docker daemon is required — only the mode-resolution logic in
app/routes/links.py is under test.
"""
import pytest

import app.routes.links as links_module
from app.config import Config
from app.models.database import Database
from app.services.docker_service import DockerService


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = Database(str(tmp_path / "test.db"))
    test_db.init_db()
    monkeypatch.setattr(links_module.db_service, "db", test_db)
    monkeypatch.setattr(DockerService, "create_container",
                        lambda *a, **k: ("fake-container-id", 7100))

    captured = {}
    def capture_inject(*args, **kwargs):
        captured["ai_assistance_mode"] = kwargs.get("ai_assistance_mode")
        return {"injected": True, "guarded_mode_enforced": True}
    monkeypatch.setattr(DockerService, "inject_workspace_files", capture_inject)

    from app import create_app
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, captured


@pytest.fixture
def db(client):
    return links_module.db_service


def make_assignment_with_challenge(db_service, ai_assistance_mode, challenge_id="challenge-1"):
    db_service.create_challenge(
        challenge_id, "Title", "backend", "Desc", "code",
        "bug_fix", "rate_limiting", "medium", ai_assistance_mode)
    assignment_id = "assignment-1"
    db_service.create_assignment(
        assignment_id, "T", "D", "code", "criteria", challenge_id=challenge_id)
    return assignment_id, challenge_id


def test_guarded_mode_passed_through(client, db):
    c, captured = client
    assignment_id, _ = make_assignment_with_challenge(db, "guarded")
    resp = c.post(f"/api/generate-link/{assignment_id}")
    assert resp.status_code == 201
    assert captured["ai_assistance_mode"] == "guarded"


def test_unguarded_mode_passed_through(client, db):
    c, captured = client
    assignment_id, _ = make_assignment_with_challenge(db, "unguarded")
    resp = c.post(f"/api/generate-link/{assignment_id}")
    assert resp.status_code == 201
    assert captured["ai_assistance_mode"] == "unguarded"


def test_drifted_mode_value_falls_back_to_default(client, db):
    c, captured = client
    assignment_id, challenge_id = make_assignment_with_challenge(db, "unguarded")
    # Simulate DB drift (manual edit / legacy data) bypassing enum validation
    # that normally happens at challenge-creation time.
    with db.db.get_connection() as conn:
        conn.execute("UPDATE challenges SET ai_assistance_mode = ? WHERE id = ?",
                     ("Guarded", challenge_id))
        conn.commit()

    resp = c.post(f"/api/generate-link/{assignment_id}")
    assert resp.status_code == 201
    assert captured["ai_assistance_mode"] == Config.DEFAULT_ASSISTANCE_MODE


def test_no_challenge_linked_defaults_to_unguarded(client, db):
    c, captured = client
    assignment_id = "assignment-no-challenge"
    db.create_assignment(assignment_id, "T", "D", "code", "criteria")
    resp = c.post(f"/api/generate-link/{assignment_id}")
    assert resp.status_code == 201
    assert captured["ai_assistance_mode"] == Config.DEFAULT_ASSISTANCE_MODE


# ── Guarded-mode injection outcome persisted on session_links (Story 9.3) ──

def test_successful_guarded_injection_persists_enforced_true(client, db):
    c, captured = client
    assignment_id, _ = make_assignment_with_challenge(db, "guarded")
    resp = c.post(f"/api/generate-link/{assignment_id}")
    assert resp.status_code == 201
    link_id = resp.get_json()["link_id"]

    ai_mode, enforced = db.get_session_link_assistance_info(link_id)
    assert ai_mode == "guarded"
    assert bool(enforced) is True


def test_failed_guarded_injection_persists_enforced_false(client, db, monkeypatch):
    c, captured = client
    def failing_inject(*args, **kwargs):
        return {"injected": True, "guarded_mode_enforced": False}
    monkeypatch.setattr(DockerService, "inject_workspace_files", failing_inject)

    assignment_id, _ = make_assignment_with_challenge(db, "guarded")
    resp = c.post(f"/api/generate-link/{assignment_id}")
    assert resp.status_code == 201
    link_id = resp.get_json()["link_id"]

    ai_mode, enforced = db.get_session_link_assistance_info(link_id)
    assert ai_mode == "guarded"
    assert bool(enforced) is False


def test_unguarded_mode_persists_enforced_true(client, db):
    c, captured = client
    assignment_id, _ = make_assignment_with_challenge(db, "unguarded")
    resp = c.post(f"/api/generate-link/{assignment_id}")
    assert resp.status_code == 201
    link_id = resp.get_json()["link_id"]

    ai_mode, enforced = db.get_session_link_assistance_info(link_id)
    assert ai_mode == "unguarded"
    assert bool(enforced) is True
