"""Story 7.3 — boundary-precision tests for hire recommendation thresholds.

Story 7.1 exercised recommendations only as a side effect of testing other
guarantees, always at composite values well clear of an actual threshold.
This file pins the exact boundary values (85/70/55) so an off-by-one in the
inline `>=` comparisons inside score_8_dimensions() cannot slip through.

LLMService.chat is monkeypatched in every test; no network call is possible.
"""
import json

import pytest

from app.services.evaluation_service import EvaluationService
from app.services.llm_service import LLMService

ALL_DIMS = list(EvaluationService.DIMENSION_WEIGHTS)

# A non-uniform mix that weighted-sums to exactly 85.0, proving the real
# per-dimension weighting path (not just the uniform-score shortcut) lands
# correctly on a boundary. Verified: sum(score*weight) == 85.0 exactly.
NON_UNIFORM_AT_85 = {
    "problem_decomposition": 90,
    "first_principles_thinking": 90,
    "creative_problem_solving": 80,
    "iteration_quality": 90,
    "debugging_with_ai": 80,
    "architecture_decisions": 80,
    "communication_clarity": 80,
    "token_efficiency": 85,
}


@pytest.fixture(autouse=True)
def _no_llm_env(monkeypatch):
    """Hermeticity guard (matches test_score_8_dimensions.py): app/__init__.py
    force-loads .env at import time, so scrub LLM vars for every test here too."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)


@pytest.fixture
def assignment():
    return {"title": "T", "description": "D", "evaluation_criteria": "C"}


def make_dimension_response(scores):
    return json.dumps({
        "dimensions": {d: {"score": s, "rationale": "evidence"} for d, s in scores.items()},
        "recommendation_rationale": "boundary probe",
    })


def make_uniform_response(score):
    """All 8 dimensions scored identically -> composite == score exactly,
    since DIMENSION_WEIGHTS sums to 1.0 (no hand-computed weighting needed)."""
    return json.dumps({
        "dimensions": {d: {"score": score, "rationale": "evidence"} for d in ALL_DIMS},
        "recommendation_rationale": "boundary probe",
    })


def mock_chat(monkeypatch, payload):
    monkeypatch.setattr(LLMService, "chat", lambda *args, **kwargs: payload)


def score_at(monkeypatch, assignment, score):
    mock_chat(monkeypatch, make_uniform_response(score))
    return EvaluationService.score_8_dimensions(
        session_logs=[], file_snapshot={}, assignment=assignment)


# ── AC 1: strong_hire boundary (>= 85) ──────────────────────────────────────

def test_composite_exactly_85_is_strong_hire(monkeypatch, assignment):
    result = score_at(monkeypatch, assignment, 85)
    assert result["composite_score"] == 85.0
    assert result["hire_recommendation"] == "strong_hire"


def test_composite_84_is_hire_not_strong_hire(monkeypatch, assignment):
    result = score_at(monkeypatch, assignment, 84)
    assert result["composite_score"] == 84.0
    assert result["hire_recommendation"] == "hire"


# ── AC 2: hire boundary (>= 70) ──────────────────────────────────────────────

def test_composite_exactly_70_is_hire(monkeypatch, assignment):
    result = score_at(monkeypatch, assignment, 70)
    assert result["composite_score"] == 70.0
    assert result["hire_recommendation"] == "hire"


def test_composite_69_is_select_not_hire(monkeypatch, assignment):
    result = score_at(monkeypatch, assignment, 69)
    assert result["composite_score"] == 69.0
    assert result["hire_recommendation"] == "select"


# ── AC 3: select boundary (>= 55) ────────────────────────────────────────────

def test_composite_exactly_55_is_select(monkeypatch, assignment):
    result = score_at(monkeypatch, assignment, 55)
    assert result["composite_score"] == 55.0
    assert result["hire_recommendation"] == "select"


def test_composite_54_is_pass_not_select(monkeypatch, assignment):
    result = score_at(monkeypatch, assignment, 54)
    assert result["composite_score"] == 54.0
    assert result["hire_recommendation"] == "pass"


# ── AC 4: pass is reachable well below the select boundary ─────────────────

def test_composite_far_below_threshold_is_pass(monkeypatch, assignment):
    result = score_at(monkeypatch, assignment, 0)
    assert result["composite_score"] == 0.0
    assert result["hire_recommendation"] == "pass"


# ── Non-uniform composite exactly on a boundary (real weighting, not the
#    uniform-score shortcut) ─────────────────────────────────────────────────

def test_non_uniform_composite_landing_exactly_on_85_is_strong_hire(
        monkeypatch, assignment):
    mock_chat(monkeypatch, make_dimension_response(NON_UNIFORM_AT_85))
    result = EvaluationService.score_8_dimensions(
        session_logs=[], file_snapshot={}, assignment=assignment)
    assert result["composite_score"] == 85.0
    assert result["hire_recommendation"] == "strong_hire"


# ── Regression: composite is rounded ONCE, then classification and storage
#    both use that same rounded value — a composite of 84.996 rounds to 85.0
#    and must be classified "strong_hire", not "hire" (see deferred-work.md
#    for the pre-fix inconsistency this replaces). ───────────────────────────

def test_composite_rounding_up_to_85_classifies_strong_hire(
        monkeypatch, assignment):
    result = score_at(monkeypatch, assignment, 84.996)
    assert result["composite_score"] == 85.0
    assert result["hire_recommendation"] == "strong_hire"


# ── AC 5: thresholds asserted as literals, not the dict under test ─────────

def test_thresholds_are_the_literal_spec_values():
    # Anti-tautology guard: fail loudly if HIRE_THRESHOLDS itself drifts from
    # the spec numbers this whole file is built around.
    assert EvaluationService.HIRE_THRESHOLDS == {
        "strong_hire": 85, "hire": 70, "select": 55,
    }
