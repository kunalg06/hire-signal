"""Story 7.1 — unit tests for EvaluationService.score_8_dimensions().

LLMService.chat is monkeypatched in every test; no network or API key needed.
"""
import json

import pytest

from app.services.evaluation_service import EvaluationService
from app.services.llm_service import LLMService

# The 8 spec dimensions, pinned as literals so a dimension accidentally
# dropped from DIMENSION_WEIGHTS fails the suite instead of shrinking it.
EXPECTED_DIMS = {
    "problem_decomposition",
    "first_principles_thinking",
    "creative_problem_solving",
    "iteration_quality",
    "debugging_with_ai",
    "architecture_decisions",
    "communication_clarity",
    "token_efficiency",
}

ALL_DIMS = list(EvaluationService.DIMENSION_WEIGHTS)

# Weighted composite = 58.0; plain unweighted mean = 55.0 — distinguishes
# the Python-enforced weighted average from a naive mean.
DISTINCT_SCORES = {
    "problem_decomposition": 90,
    "first_principles_thinking": 80,
    "creative_problem_solving": 70,
    "iteration_quality": 60,
    "debugging_with_ai": 50,
    "architecture_decisions": 40,
    "communication_clarity": 30,
    "token_efficiency": 20,
}


@pytest.fixture(autouse=True)
def _no_llm_env(monkeypatch):
    """Hermeticity guard: app/__init__.py force-loads .env (override=True) at
    import time, so scrub the LLM vars for every test — an accidentally
    unmocked call can then never construct a real OpenRouter client."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)


@pytest.fixture
def assignment():
    return {"title": "T", "description": "D", "evaluation_criteria": "C"}


def make_response(scores, **top_level):
    """Build a Claude-shaped JSON response string for the given dim scores."""
    payload = {
        "dimensions": {d: {"score": s, "rationale": "evidence"} for d, s in scores.items()},
        "recommendation_rationale": "employer-facing summary",
    }
    payload.update(top_level)
    return json.dumps(payload)


def mock_chat(monkeypatch, payload):
    """Patch the single LLM seam to return a canned response string."""
    monkeypatch.setattr(LLMService, "chat", lambda *args, **kwargs: payload)


def run(assignment):
    return EvaluationService.score_8_dimensions(
        session_logs=[], file_snapshot={}, assignment=assignment)


def assert_safe_default(result):
    assert result["composite_score"] == 0.0
    assert result["hire_recommendation"] == "pass"
    assert set(result["dimensions"]) == EXPECTED_DIMS
    for d in EXPECTED_DIMS:
        assert result["dimensions"][d]["score"] == 0


# ── Weights contract ────────────────────────────────────────────────────────

def test_weights_define_exactly_the_eight_spec_dimensions():
    assert set(EvaluationService.DIMENSION_WEIGHTS) == EXPECTED_DIMS
    assert round(sum(EvaluationService.DIMENSION_WEIGHTS.values()), 10) == 1.0


# ── AC 2, 3: happy path — all 8 keys, weighted average ─────────────────────

def test_all_eight_keys_present_on_valid_response(monkeypatch, assignment):
    mock_chat(monkeypatch, make_response({d: 80 for d in ALL_DIMS}))
    result = run(assignment)
    assert set(result["dimensions"]) == EXPECTED_DIMS
    assert result["composite_score"] == 80.0
    assert result["hire_recommendation"] == "hire"
    # Model-supplied rationales survive into the result untouched
    assert result["recommendation_rationale"] == "employer-facing summary"
    for d in EXPECTED_DIMS:
        assert result["dimensions"][d]["rationale"] == "evidence"


def test_composite_is_weighted_average_not_plain_mean(monkeypatch, assignment):
    mock_chat(monkeypatch, make_response(DISTINCT_SCORES))
    result = run(assignment)
    assert result["composite_score"] == 58.0  # plain mean would be 55.0
    assert result["hire_recommendation"] == "select"


# ── AC 2: missing dimensions backfilled ─────────────────────────────────────

def test_missing_dimensions_backfilled_with_zero(monkeypatch, assignment):
    partial = {d: s for d, s in DISTINCT_SCORES.items()
               if d not in ("architecture_decisions",
                            "communication_clarity",
                            "token_efficiency")}
    mock_chat(monkeypatch, make_response(partial))
    result = run(assignment)

    assert set(result["dimensions"]) == EXPECTED_DIMS
    for missing in ("architecture_decisions", "communication_clarity",
                    "token_efficiency"):
        assert result["dimensions"][missing]["score"] == 0
        assert result["dimensions"][missing]["rationale"] == \
            "dimension missing from response"
    # 58.0 minus contributions 4.0 + 3.0 + 2.0 of the zeroed dims
    assert result["composite_score"] == 49.0
    assert result["hire_recommendation"] == "pass"


def test_dimensions_key_absent_backfills_all_eight(monkeypatch, assignment):
    mock_chat(monkeypatch, json.dumps({"recommendation_rationale": "no dims"}))
    result = run(assignment)
    assert set(result["dimensions"]) == EXPECTED_DIMS
    for d in EXPECTED_DIMS:
        assert result["dimensions"][d]["score"] == 0
        assert result["dimensions"][d]["rationale"] == \
            "dimension missing from response"
    assert result["composite_score"] == 0.0
    assert result["hire_recommendation"] == "pass"


# ── AC 4: Claude's own composite/recommendation are overridden ─────────────

def test_claude_supplied_composite_and_recommendation_ignored(monkeypatch,
                                                              assignment):
    mock_chat(monkeypatch, make_response(
        DISTINCT_SCORES, composite_score=99, hire_recommendation="strong_hire"))
    result = run(assignment)
    assert result["composite_score"] == 58.0
    assert result["hire_recommendation"] == "select"


# ── Composite clamp bounds (also exercises the strong_hire branch) ─────────

def test_scores_above_100_clamped_to_100(monkeypatch, assignment):
    mock_chat(monkeypatch, make_response({d: 150 for d in ALL_DIMS}))
    result = run(assignment)
    assert result["composite_score"] == 100.0
    assert result["hire_recommendation"] == "strong_hire"


def test_negative_scores_clamped_to_zero(monkeypatch, assignment):
    mock_chat(monkeypatch, make_response({d: -20 for d in ALL_DIMS}))
    result = run(assignment)
    assert result["composite_score"] == 0.0
    assert result["hire_recommendation"] == "pass"


# ── Prompt assembly: inputs actually reach the LLM ──────────────────────────

def test_prompt_includes_assignment_logs_and_files(monkeypatch):
    captured = {}

    def capture(*args, **kwargs):
        captured["prompt"] = args[0]
        return make_response({d: 80 for d in ALL_DIMS})

    monkeypatch.setattr(LLMService, "chat", capture)
    distinctive = {
        "title": "Rate Limiter Challenge",
        "description": "Build a sliding-window limiter",
        "evaluation_criteria": "Correctness before cleverness",
    }
    logs = [{"prompt": "how do I paginate the API results?",
             "response_summary": "use cursor-based pagination",
             "file_changes_count": 2}]
    snapshot = {"solution.py": "def paginate(): pass"}

    result = EvaluationService.score_8_dimensions(
        session_logs=logs, file_snapshot=snapshot, assignment=distinctive)

    prompt = captured["prompt"]
    for fragment in ("Rate Limiter Challenge",
                     "Build a sliding-window limiter",
                     "Correctness before cleverness",
                     "how do I paginate the API results?",
                     "use cursor-based pagination",
                     "solution.py",
                     "def paginate(): pass"):
        assert fragment in prompt
    assert result["composite_score"] == 80.0


# ── AC 5: failure safety ────────────────────────────────────────────────────

def test_chat_exception_returns_safe_default(monkeypatch, assignment):
    def boom(*args, **kwargs):
        raise RuntimeError("provider down")
    monkeypatch.setattr(LLMService, "chat", boom)

    result = run(assignment)
    assert_safe_default(result)
    for d in EXPECTED_DIMS:
        assert result["dimensions"][d]["rationale"].startswith("Scoring error:")


def test_non_json_response_returns_safe_default(monkeypatch, assignment):
    mock_chat(monkeypatch, "I am not JSON")
    assert_safe_default(run(assignment))


# ── AC 6: markdown fence stripping ──────────────────────────────────────────

def test_json_fenced_response_parses(monkeypatch, assignment):
    fenced = "```json\n" + make_response({d: 80 for d in ALL_DIMS}) + "\n```"
    mock_chat(monkeypatch, fenced)
    result = run(assignment)
    assert result["composite_score"] == 80.0
    assert set(result["dimensions"]) == EXPECTED_DIMS
