"""Party-mode review 2026-07-11: a real candidate dry-run showed
"Architecture Decisions" scored 0 on a challenge that structurally never
offered a design decision — a validity bug, not a fair score. This adds:
  1. applicable_dimensions: which of the 8 dimensions THIS challenge can
     actually generate evidence for (defaults to all 8 for backward compat).
  2. decision_point: an optional genuine design fork the candidate must
     choose between and justify (defaults to applies=False).

Covers EvaluationService's normalization helpers directly (fast, no LLM
mocking needed) plus the /api/generate-challenge route's persistence of
both fields, reusing test_generate_challenge_endpoint.py's DB-isolation
fixtures.
"""
import json

import pytest

import app.routes.challenges as challenges_module
from app.models.database import Database
from app.services.evaluation_service import EvaluationService
from app.services.llm_service import LLMService

ENDPOINT = "/api/generate-challenge"
ALL_DIMS = list(EvaluationService.DIMENSION_WEIGHTS)

VALID_PAYLOAD = {
    "problem_statement": "Fix a leaking rate limiter under concurrent load",
    "difficulty": "medium",
    "challenge_type": "bug_fix",
    "skill_area": "api_integration",
    "ai_assistance_mode": "unguarded",
}


# ── _normalize_applicable_dimensions() ──────────────────────────────────────

def test_normalize_applicable_dimensions_passes_through_valid_subset():
    result = EvaluationService._normalize_applicable_dimensions(
        ["debugging_with_ai", "problem_decomposition"])
    # Order follows DIMENSION_WEIGHTS, not input order
    assert result == ["problem_decomposition", "debugging_with_ai"]


def test_normalize_applicable_dimensions_drops_unrecognized_keys():
    result = EvaluationService._normalize_applicable_dimensions(
        ["problem_decomposition", "made_up_dimension"])
    assert result == ["problem_decomposition"]


@pytest.mark.parametrize("bad_input", [None, "not-a-list", 42, [], ["nonsense"]])
def test_normalize_applicable_dimensions_falls_back_to_all_eight(bad_input):
    assert EvaluationService._normalize_applicable_dimensions(bad_input) == ALL_DIMS


# ── _normalize_decision_point() ─────────────────────────────────────────────

def test_normalize_decision_point_passes_through_complete_valid_object():
    raw = {"applies": True, "prompt": "A or B?", "option_a": "A", "option_b": "B"}
    assert EvaluationService._normalize_decision_point(raw) == raw


@pytest.mark.parametrize("bad_input", [
    None, "not-a-dict", {"applies": "yes"},
    {"applies": True, "prompt": "", "option_a": "A", "option_b": "B"},
    {"applies": True, "prompt": "A or B?", "option_a": "", "option_b": "B"},
])
def test_normalize_decision_point_falls_back_to_no_op(bad_input):
    result = EvaluationService._normalize_decision_point(bad_input)
    assert result == {"applies": False, "prompt": "", "option_a": "", "option_b": ""}


def test_normalize_decision_point_applies_false_is_passthrough_regardless_of_strings():
    """When applies=False, the string fields are irrelevant — must still
    normalize to the canonical no-op shape rather than leak stray text."""
    raw = {"applies": False, "prompt": "leftover text", "option_a": "x", "option_b": "y"}
    assert EvaluationService._normalize_decision_point(raw) == {
        "applies": False, "prompt": "", "option_a": "", "option_b": ""}


# ── generate_challenge() end-to-end normalization ───────────────────────────

def test_generate_challenge_defaults_to_all_eight_when_llm_omits_field(monkeypatch):
    """Backward compat: an LLM response with no applicable_dimensions/
    decision_point keys (e.g. an older prompt/model) must not crash and
    must default to 'all 8 apply, no decision point'."""
    payload = {
        "title": "Fix the Rate Limiter",
        "description": "A sliding-window limiter leaks memory under load.",
        "evaluation_criteria": "Fixes leak; adds test; explains root cause",
        "starter_code": "def limiter(): pass",
    }
    monkeypatch.setattr(LLMService, "chat", lambda *a, **k: json.dumps(payload))
    result = EvaluationService.generate_challenge(
        problem_statement="Fix a leaking rate limiter", difficulty="medium")
    assert result["applicable_dimensions"] == ALL_DIMS
    assert result["decision_point"] == {"applies": False, "prompt": "", "option_a": "", "option_b": ""}


def test_generate_challenge_auto_includes_architecture_decisions_when_decision_point_applies(monkeypatch):
    """If the LLM sets decision_point.applies=True but forgets to include
    architecture_decisions in applicable_dimensions, the platform must fix
    that inconsistency rather than silently score a decision-point
    challenge as if architecture_decisions were inapplicable."""
    payload = {
        "title": "Rate Limiter Design Choice",
        "description": "Choose a rate-limiting strategy.",
        "evaluation_criteria": "criteria",
        "starter_code": "code",
        "applicable_dimensions": ["problem_decomposition", "debugging_with_ai"],
        "decision_point": {
            "applies": True,
            "prompt": "Sliding window or token bucket?",
            "option_a": "Sliding window: precise, more memory",
            "option_b": "Token bucket: less memory, allows bursts",
        },
    }
    monkeypatch.setattr(LLMService, "chat", lambda *a, **k: json.dumps(payload))
    result = EvaluationService.generate_challenge(
        problem_statement="Rate limiter", difficulty="medium")
    assert "architecture_decisions" in result["applicable_dimensions"]
    assert result["decision_point"]["applies"] is True


# ── /api/generate-challenge persists both fields ────────────────────────────

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


def test_route_persists_and_returns_applicable_dimensions_and_decision_point(client, db, monkeypatch):
    payload = {
        "title": "Rate Limiter Design Choice",
        "description": "Choose a rate-limiting strategy.",
        "evaluation_criteria": "criteria",
        "starter_code": "code",
        "applicable_dimensions": ["problem_decomposition", "architecture_decisions"],
        "decision_point": {
            "applies": True,
            "prompt": "Sliding window or token bucket?",
            "option_a": "Sliding window",
            "option_b": "Token bucket",
        },
    }
    monkeypatch.setattr(LLMService, "chat", lambda *a, **k: json.dumps(payload))

    resp = client.post(ENDPOINT, json=VALID_PAYLOAD)
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body["applicable_dimensions"]) == {"problem_decomposition", "architecture_decisions"}
    assert body["decision_point"]["applies"] is True

    # Round-trip through the DB, not just the response of the generation call
    challenge_id = body["challenge_id"]
    get_resp = client.get(f"/api/challenges/{challenge_id}")
    get_body = get_resp.get_json()
    assert set(get_body["applicable_dimensions"]) == {"problem_decomposition", "architecture_decisions"}
    assert get_body["decision_point"]["applies"] is True
    assert get_body["decision_point"]["prompt"] == "Sliding window or token bucket?"


def test_route_defaults_persisted_fields_when_llm_omits_them(client, db, monkeypatch):
    payload = {
        "title": "Fix the Rate Limiter",
        "description": "A sliding-window limiter leaks memory under load.",
        "evaluation_criteria": "criteria",
        "starter_code": "code",
    }
    monkeypatch.setattr(LLMService, "chat", lambda *a, **k: json.dumps(payload))

    resp = client.post(ENDPOINT, json=VALID_PAYLOAD)
    assert resp.status_code == 200
    challenge_id = resp.get_json()["challenge_id"]

    get_resp = client.get(f"/api/challenges/{challenge_id}")
    get_body = get_resp.get_json()
    assert set(get_body["applicable_dimensions"]) == set(ALL_DIMS)
    assert get_body["decision_point"] == {"applies": False, "prompt": "", "option_a": "", "option_b": ""}
