"""Story 7.5 — integration tests for POST /api/generate-challenge.

Validation and persistence both live in the Flask route (app/routes/
challenges.py), not in EvaluationService.generate_challenge() itself, which
has no validation of its own. This combines two prior patterns:
- Story 7.4's DB-isolation fixtures (client/db) — reused exactly, not
  re-derived. See tests/test_candidates_endpoint.py for the full discovery
  of why create_app() must be called as create_app("testing") and why
  db_service.db must be monkeypatched directly.
- Story 7.1's LLM-mocking pattern (shape-robust *args, **kwargs lambda).
"""
import json

import pytest

import app.routes.challenges as challenges_module
from app.models.database import Database
from app.services.llm_service import LLMService

ENDPOINT = "/api/generate-challenge"

VALID_PAYLOAD = {
    "problem_statement": "Fix a leaking rate limiter under concurrent load",
    "difficulty": "medium",
    "challenge_type": "bug_fix",
    "skill_area": "api_integration",
    "ai_assistance_mode": "unguarded",
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = Database(str(tmp_path / "test.db"))
    test_db.init_db()
    monkeypatch.setattr(challenges_module.db_service, "db", test_db)

    from app import create_app
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def db(client):
    return challenges_module.db_service


def make_llm_response():
    payload = {
        "title": "Fix the Rate Limiter",
        "description": "A sliding-window limiter leaks memory under load.",
        "evaluation_criteria": "Fixes leak; adds test; explains root cause",
        "starter_code": "def limiter(): pass",
    }
    return json.dumps(payload)


def mock_chat(monkeypatch, payload, raises=None):
    """Returns a list that will be filled with each call's args, so tests can
    assert whether the LLM was invoked at all (AC 9)."""
    calls = []

    def fake(*args, **kwargs):
        calls.append(args)
        if raises is not None:
            raise raises
        return payload

    monkeypatch.setattr(LLMService, "chat", fake)
    return calls


def spy_create_challenge(monkeypatch, db_service):
    """Records whether create_challenge was ever invoked, without actually
    calling through — used to prove persistence did NOT happen (AC 7)."""
    calls = []
    monkeypatch.setattr(db_service, "create_challenge",
                        lambda *a, **k: calls.append((a, k)))
    return calls


# ── AC 1: required fields ───────────────────────────────────────────────────

def test_missing_problem_statement_returns_400(client, monkeypatch):
    calls = mock_chat(monkeypatch, make_llm_response())
    payload = {**VALID_PAYLOAD, "problem_statement": ""}
    resp = client.post(ENDPOINT, json=payload)
    assert resp.status_code == 400
    assert "problem_statement" in resp.get_json()["error"]
    assert calls == []


def test_problem_statement_key_entirely_absent_returns_400(client, monkeypatch):
    # Distinct from the empty-string case above: proves the route's .get()
    # default converges absent-key and empty-string to the same 400 path.
    calls = mock_chat(monkeypatch, make_llm_response())
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "problem_statement"}
    resp = client.post(ENDPOINT, json=payload)
    assert resp.status_code == 400
    assert "problem_statement" in resp.get_json()["error"]
    assert calls == []


def test_missing_difficulty_returns_400(client, monkeypatch):
    calls = mock_chat(monkeypatch, make_llm_response())
    payload = {**VALID_PAYLOAD, "difficulty": ""}
    resp = client.post(ENDPOINT, json=payload)
    assert resp.status_code == 400
    assert "difficulty" in resp.get_json()["error"]
    assert calls == []


# ── AC 2-5: enum validation ──────────────────────────────────────────────────

def test_invalid_difficulty_returns_400(client, monkeypatch):
    calls = mock_chat(monkeypatch, make_llm_response())
    payload = {**VALID_PAYLOAD, "difficulty": "impossible"}
    resp = client.post(ENDPOINT, json=payload)
    assert resp.status_code == 400
    assert "difficulty" in resp.get_json()["error"]
    assert calls == []


def test_invalid_challenge_type_returns_400(client, monkeypatch):
    calls = mock_chat(monkeypatch, make_llm_response())
    payload = {**VALID_PAYLOAD, "challenge_type": "not_a_real_type"}
    resp = client.post(ENDPOINT, json=payload)
    assert resp.status_code == 400
    assert "challenge_type" in resp.get_json()["error"]
    assert calls == []


def test_invalid_skill_area_returns_400(client, monkeypatch):
    calls = mock_chat(monkeypatch, make_llm_response())
    payload = {**VALID_PAYLOAD, "skill_area": "not_a_real_area"}
    resp = client.post(ENDPOINT, json=payload)
    assert resp.status_code == 400
    assert "skill_area" in resp.get_json()["error"]
    assert calls == []


def test_invalid_ai_assistance_mode_returns_400(client, monkeypatch):
    calls = mock_chat(monkeypatch, make_llm_response())
    payload = {**VALID_PAYLOAD, "ai_assistance_mode": "sideways"}
    resp = client.post(ENDPOINT, json=payload)
    assert resp.status_code == 400
    assert "ai_assistance_mode" in resp.get_json()["error"]
    assert calls == []


# ── Documents a known, deferred production gap (see deferred-work.md):
#    non-string values crash .strip() with an unhandled AttributeError, not
#    a clean 400 — confirmed to actually propagate as a raised exception
#    through Flask's test client (TESTING=True re-raises unhandled errors
#    instead of converting them to a 500 response) rather than being caught
#    anywhere in the route, which only wraps the LLM call in a try/except.

def test_null_difficulty_currently_crashes_unhandled(client, monkeypatch):
    mock_chat(monkeypatch, make_llm_response())
    payload = {**VALID_PAYLOAD, "difficulty": None}
    with pytest.raises(AttributeError):
        client.post(ENDPOINT, json=payload)


# ── AC 6: success + persistence ─────────────────────────────────────────────

def test_valid_request_returns_200_and_persists_as_unpublished_draft(
        client, db, monkeypatch):
    calls = mock_chat(monkeypatch, make_llm_response())
    resp = client.post(ENDPOINT, json=VALID_PAYLOAD)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["challenge_id"] is not None
    assert body["is_published"] is False
    assert body["title"] == "Fix the Rate Limiter"

    # Prompt actually carries the request's own field values — an endpoint
    # that ignored its inputs and sent a hardcoded prompt would still 200.
    prompt = calls[0][0]
    assert VALID_PAYLOAD["problem_statement"] in prompt
    assert VALID_PAYLOAD["difficulty"] in prompt
    assert VALID_PAYLOAD["challenge_type"] in prompt
    assert VALID_PAYLOAD["skill_area"] in prompt

    # challenges table column order: id, title, domain, description,
    # evaluation_rubric_json, starter_code, challenge_type, skill_area,
    # difficulty, ai_assistance_mode, is_published, created_at (index 10).
    row = db.get_challenge(body["challenge_id"])
    assert row is not None
    assert row[10] == 0  # is_published


# ── AC 7: LLM failure -> 500, nothing persisted ─────────────────────────────

def test_llm_failure_returns_500_and_persists_nothing(client, db, monkeypatch):
    chat_calls = mock_chat(monkeypatch, None, raises=RuntimeError("LLM provider down"))
    persist_calls = spy_create_challenge(monkeypatch, db)

    resp = client.post(ENDPOINT, json=VALID_PAYLOAD)
    assert resp.status_code == 500

    assert len(chat_calls) == 1  # the LLM genuinely was reached and failed
    assert persist_calls == []  # ... and generation failure never reaches persist


def test_malformed_llm_json_returns_500(client, monkeypatch):
    mock_chat(monkeypatch, "not valid json at all")
    resp = client.post(ENDPOINT, json=VALID_PAYLOAD)
    assert resp.status_code == 500
    assert "Failed to parse" in resp.get_json()["error"]


def test_llm_response_missing_required_field_returns_500(client, monkeypatch):
    payload = make_llm_response()
    incomplete = json.loads(payload)
    del incomplete["starter_code"]
    mock_chat(monkeypatch, json.dumps(incomplete))
    resp = client.post(ENDPOINT, json=VALID_PAYLOAD)
    assert resp.status_code == 500
    assert "Missing fields" in resp.get_json()["error"]


# ── AC 8: persist failure degrades gracefully ───────────────────────────────

def test_persist_failure_still_returns_200_with_null_challenge_id(
        client, db, monkeypatch):
    mock_chat(monkeypatch, make_llm_response())

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")
    monkeypatch.setattr(db, "create_challenge", boom)

    resp = client.post(ENDPOINT, json=VALID_PAYLOAD)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["challenge_id"] is None
    assert body["title"] == "Fix the Rate Limiter"
