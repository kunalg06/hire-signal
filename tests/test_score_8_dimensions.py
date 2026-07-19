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


def test_bare_fence_without_json_tag_parses(monkeypatch, assignment):
    """A ``` fence with no 'json' language tag must not silently zero-score."""
    fenced = "```\n" + make_response({d: 80 for d in ALL_DIMS}) + "\n```"
    mock_chat(monkeypatch, fenced)
    result = run(assignment)
    assert result["composite_score"] == 80.0
    assert set(result["dimensions"]) == EXPECTED_DIMS


def test_prose_wrapped_fence_parses(monkeypatch, assignment):
    """Prose before the fence must not defeat extraction."""
    wrapped = ("Here is the evaluation:\n```json\n"
               + make_response({d: 80 for d in ALL_DIMS}) + "\n```\nThanks!")
    mock_chat(monkeypatch, wrapped)
    result = run(assignment)
    assert result["composite_score"] == 80.0
    assert set(result["dimensions"]) == EXPECTED_DIMS


def test_truncated_fence_missing_closing_backticks_still_parses(monkeypatch, assignment):
    """max_tokens can truncate a response before its closing ``` — the
    fence must still be recoverable from the opening marker alone."""
    truncated = "```json\n" + make_response({d: 80 for d in ALL_DIMS})
    mock_chat(monkeypatch, truncated)
    result = run(assignment)
    assert result["composite_score"] == 80.0
    assert set(result["dimensions"]) == EXPECTED_DIMS


def test_unfenced_response_with_embedded_backticks_is_not_corrupted(monkeypatch, assignment):
    """A fully valid, UNFENCED response whose rationale text happens to
    contain a literal ``` must parse untouched — the fence-stripping
    fallback must never fire on already-valid JSON."""
    scores = {d: 80 for d in ALL_DIMS}
    payload = {
        "dimensions": {d: {"score": s, "rationale": "used ```print(x)``` to debug"}
                       for d, s in scores.items()},
        "recommendation_rationale": "employer-facing summary",
    }
    mock_chat(monkeypatch, json.dumps(payload))
    result = run(assignment)
    assert result["composite_score"] == 80.0
    assert set(result["dimensions"]) == EXPECTED_DIMS
    assert result["dimensions"]["problem_decomposition"]["rationale"] == \
        "used ```print(x)``` to debug"


def test_last_of_multiple_fenced_blocks_is_preferred(monkeypatch, assignment):
    """If a response contains more than one fenced JSON block (e.g. a draft
    followed by a final answer), the LAST block wins."""
    draft = make_response({d: 10 for d in ALL_DIMS})
    final = make_response({d: 80 for d in ALL_DIMS})
    wrapped = f"Draft:\n```json\n{draft}\n```\nFinal:\n```json\n{final}\n```"
    mock_chat(monkeypatch, wrapped)
    result = run(assignment)
    assert result["composite_score"] == 80.0


# ── Malformed response shapes: must degrade to the safe default, never crash ─

@pytest.mark.parametrize("payload", ["[]", "null", "42"])
def test_non_dict_top_level_returns_safe_default(monkeypatch, assignment, payload):
    mock_chat(monkeypatch, payload)
    assert_safe_default(run(assignment))


def test_non_dict_top_level_is_retried_before_falling_back(monkeypatch, assignment):
    """A bad-shape response gets the same retry budget as generate_challenge's
    validate= path — it shouldn't zero-score on the first bad draw alone."""
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            return "null"
        return make_response({d: 80 for d in ALL_DIMS})

    monkeypatch.setattr(LLMService, "chat", flaky)
    result = run(assignment)
    assert len(calls) == 3
    assert result["composite_score"] == 80.0


def test_non_dict_dimensions_returns_safe_default(monkeypatch, assignment):
    mock_chat(monkeypatch, json.dumps({"dimensions": "not-a-dict",
                                        "recommendation_rationale": "r"}))
    assert_safe_default(run(assignment))


def test_dimension_entry_missing_score_key_defaults_to_zero(monkeypatch, assignment):
    payload = {
        "dimensions": {d: {"rationale": "evidence"} for d in ALL_DIMS},
        "recommendation_rationale": "r",
    }
    mock_chat(monkeypatch, json.dumps(payload))
    result = run(assignment)
    assert result["composite_score"] == 0.0
    for d in EXPECTED_DIMS:
        assert result["dimensions"][d]["score"] == 0


def test_non_numeric_dimension_score_coerced_to_zero(monkeypatch, assignment):
    payload = {
        "dimensions": {d: {"score": "high", "rationale": "evidence"} for d in ALL_DIMS},
        "recommendation_rationale": "r",
    }
    mock_chat(monkeypatch, json.dumps(payload))
    result = run(assignment)
    assert result["composite_score"] == 0.0
    assert result["hire_recommendation"] == "pass"
    for d in EXPECTED_DIMS:
        assert result["dimensions"][d]["score"] == 0


# ── Party-mode review 2026-07-11: unscored != scored-0 ─────────────────────

def test_chat_exception_marks_evaluation_failed(monkeypatch, assignment):
    """A swallowed provider/parse failure must be distinguishable from a
    candidate who genuinely earned a 0 — see evaluate_submission_files()'s
    auto-flag in app/routes/submissions.py, which acts on this flag."""
    def boom(*args, **kwargs):
        raise RuntimeError("provider down")
    monkeypatch.setattr(LLMService, "chat", boom)
    result = run(assignment)
    assert result["evaluation_failed"] is True


def test_successful_scoring_does_not_mark_evaluation_failed(monkeypatch, assignment):
    mock_chat(monkeypatch, make_response({d: 80 for d in ALL_DIMS}))
    result = run(assignment)
    assert "evaluation_failed" not in result or result["evaluation_failed"] is False


# ── Party-mode review 2026-07-11: per-challenge dimension applicability ────
# Scoring a dimension the challenge never offered a real opportunity for as
# a deserved 0 (averaged in with everything else) made the composite
# unreliable across challenge types. An inapplicable dimension is now
# EXCLUDED from the composite's denominator instead.

def test_inapplicable_dimension_excluded_from_composite(monkeypatch):
    """architecture_decisions is marked inapplicable; even though the judge
    still returns a low score for it, it must not drag the composite down,
    and the renormalized weights of the remaining 7 dimensions must still
    sum correctly."""
    assignment = {
        "title": "T", "description": "D", "evaluation_criteria": "C",
        "applicable_dimensions": [d for d in ALL_DIMS if d != "architecture_decisions"],
    }
    scores = {d: 80 for d in ALL_DIMS}
    scores["architecture_decisions"] = 0  # judge still scores it, but it must not count
    mock_chat(monkeypatch, make_response(scores))
    result = run(assignment)

    # All dims scored 80 except the excluded one (irrelevant to the mean) —
    # composite must be exactly 80.0, not dragged down by the excluded 0.
    assert result["composite_score"] == 80.0
    assert result["dimensions"]["architecture_decisions"]["applicable"] is False
    for d in ALL_DIMS:
        if d != "architecture_decisions":
            assert result["dimensions"][d]["applicable"] is True


def test_applicable_dimensions_absent_defaults_to_all_eight(monkeypatch, assignment):
    """Backward compatibility: an assignment dict with no applicable_dimensions
    key (e.g. every pre-existing challenge) must score exactly as before."""
    mock_chat(monkeypatch, make_response(DISTINCT_SCORES))
    result = run(assignment)
    assert result["composite_score"] == 58.0
    for d in EXPECTED_DIMS:
        assert result["dimensions"][d]["applicable"] is True


def test_unrecognized_applicable_dimension_keys_are_sanitized(monkeypatch):
    """A garbage/unrecognized dimension key in applicable_dimensions must be
    dropped rather than crash the weight-sum computation."""
    assignment = {
        "title": "T", "description": "D", "evaluation_criteria": "C",
        "applicable_dimensions": ["problem_decomposition", "not_a_real_dimension"],
    }
    mock_chat(monkeypatch, make_response({d: 80 for d in ALL_DIMS}))
    result = run(assignment)
    assert result["composite_score"] == 80.0
    assert result["dimensions"]["problem_decomposition"]["applicable"] is True
    assert result["dimensions"]["first_principles_thinking"]["applicable"] is False


def test_empty_applicable_dimensions_falls_back_to_all_eight(monkeypatch):
    """An empty list (e.g. every key filtered out as bogus) must fall back
    to 'all 8 apply' rather than compute a divide-by-zero or empty composite."""
    assignment = {
        "title": "T", "description": "D", "evaluation_criteria": "C",
        "applicable_dimensions": [],
    }
    mock_chat(monkeypatch, make_response({d: 80 for d in ALL_DIMS}))
    result = run(assignment)
    assert result["composite_score"] == 80.0
    for d in EXPECTED_DIMS:
        assert result["dimensions"][d]["applicable"] is True


def test_decision_point_context_reaches_the_scoring_prompt(monkeypatch):
    captured = {}

    def capture(*args, **kwargs):
        captured["prompt"] = args[0]
        return make_response({d: 80 for d in ALL_DIMS})
    monkeypatch.setattr(LLMService, "chat", capture)

    assignment = {
        "title": "T", "description": "D", "evaluation_criteria": "C",
        "decision_point": {
            "applies": True,
            "prompt": "Sliding window or token bucket?",
            "option_a": "Sliding window: precise, more memory",
            "option_b": "Token bucket: less memory, allows bursts",
        },
    }
    run(assignment)
    prompt = captured["prompt"]
    assert "Sliding window or token bucket?" in prompt
    assert "Sliding window: precise, more memory" in prompt
    assert "Token bucket: less memory, allows bursts" in prompt


def test_decision_point_not_applicable_omitted_from_prompt(monkeypatch, assignment):
    captured = {}

    def capture(*args, **kwargs):
        captured["prompt"] = args[0]
        return make_response({d: 80 for d in ALL_DIMS})
    monkeypatch.setattr(LLMService, "chat", capture)
    run(assignment)  # default `assignment` fixture has no decision_point key
    assert "Decision Point" not in captured["prompt"]


# ── No-change short-circuit: unmodified starter code must score 0 ──────────
# User-reported gap: a candidate submitting the assignment byte-for-byte
# as-is could still score ~50 (session-log chatter alone was enough to earn
# credit on communication/iteration dimensions with no actual code change).
# score_8_dimensions() now cross-checks solution.py against the assignment's
# starter_code before ever calling the LLM.

STARTER = "def solve(x):\n    return x\n"


def _explode_chat(*args, **kwargs):
    raise AssertionError("LLMService.chat must not be called for an unchanged submission")


def test_identical_submission_scores_zero_without_llm_call(monkeypatch):
    monkeypatch.setattr(LLMService, "chat", _explode_chat)
    assignment = {"title": "T", "description": "D", "evaluation_criteria": "C",
                  "starter_code": STARTER}
    result = EvaluationService.score_8_dimensions(
        session_logs=[{"prompt": "solve it for me", "response_summary": "here", "file_changes_count": 0}],
        file_snapshot={"solution.py": STARTER},
        assignment=assignment,
    )
    assert result["composite_score"] == 0.0
    assert result["hire_recommendation"] == "pass"
    assert result.get("evaluation_failed", False) is False  # a real 0, not a scoring failure
    for d in EXPECTED_DIMS:
        assert result["dimensions"][d]["score"] == 0


def test_whitespace_only_difference_still_counts_as_no_change(monkeypatch):
    monkeypatch.setattr(LLMService, "chat", _explode_chat)
    assignment = {"title": "T", "description": "D", "evaluation_criteria": "C",
                  "starter_code": STARTER}
    padded = "\n" + STARTER.replace("    return x", "    return x   ") + "\n"
    result = EvaluationService.score_8_dimensions(
        session_logs=[], file_snapshot={"solution.py": padded}, assignment=assignment)
    assert result["composite_score"] == 0.0


def test_changed_submission_still_scores_normally_via_llm(monkeypatch):
    mock_chat(monkeypatch, make_response({d: 80 for d in ALL_DIMS}))
    assignment = {"title": "T", "description": "D", "evaluation_criteria": "C",
                  "starter_code": STARTER}
    changed = "def solve(x):\n    return x * 2\n"
    result = EvaluationService.score_8_dimensions(
        session_logs=[], file_snapshot={"solution.py": changed}, assignment=assignment)
    assert result["composite_score"] == 80.0


def test_diff_included_in_prompt_when_code_changed(monkeypatch):
    captured = {}

    def capture(*args, **kwargs):
        captured["prompt"] = args[0]
        return make_response({d: 80 for d in ALL_DIMS})
    monkeypatch.setattr(LLMService, "chat", capture)

    assignment = {"title": "T", "description": "D", "evaluation_criteria": "C",
                  "starter_code": STARTER}
    changed = "def solve(x):\n    return x * 2\n"
    EvaluationService.score_8_dimensions(
        session_logs=[], file_snapshot={"solution.py": changed}, assignment=assignment)
    prompt = captured["prompt"]
    assert "Starter Code vs Submitted Solution" in prompt
    assert "return x * 2" in prompt


def test_no_starter_code_on_file_skips_no_change_check(monkeypatch, assignment):
    """Backward compatibility: assignments with no starter_code (e.g. legacy
    or manually-created, not from the catalog) must score exactly as
    before — no false-positive zero from an empty-vs-empty comparison."""
    mock_chat(monkeypatch, make_response({d: 80 for d in ALL_DIMS}))
    result = EvaluationService.score_8_dimensions(
        session_logs=[], file_snapshot={}, assignment=assignment)
    assert result["composite_score"] == 80.0


# ── no_ai_engagement flag (party-mode 2026-07-19, Amelia's Option C) ───────
# A real code change submitted with zero Gemini session logs leaves 4 of 8
# dimensions unscoreable for lack of AI-interaction evidence (they require
# session-log text to judge), capping the composite around 50 regardless of
# code quality. Composite/threshold math is deliberately left untouched —
# whether that ceiling is a fair penalty or a measurement gap is an
# unresolved product question, not something this code silently decides.
# The flag only surfaces the ambiguity for a human via submissions.py's
# auto-flag (tests/test_evaluation_failure_auto_flag.py).

def test_no_ai_engagement_true_for_real_change_with_no_session_logs(monkeypatch):
    mock_chat(monkeypatch, make_response({d: 80 for d in ALL_DIMS}))
    assignment = {"title": "T", "description": "D", "evaluation_criteria": "C",
                  "starter_code": STARTER}
    changed = "def solve(x):\n    return x * 2\n"
    result = EvaluationService.score_8_dimensions(
        session_logs=[], file_snapshot={"solution.py": changed}, assignment=assignment)
    assert result["no_ai_engagement"] is True


def test_no_ai_engagement_false_when_session_logs_present(monkeypatch):
    mock_chat(monkeypatch, make_response({d: 80 for d in ALL_DIMS}))
    assignment = {"title": "T", "description": "D", "evaluation_criteria": "C",
                  "starter_code": STARTER}
    changed = "def solve(x):\n    return x * 2\n"
    result = EvaluationService.score_8_dimensions(
        session_logs=[{"prompt": "how does this window logic work?",
                       "response_summary": "explained sliding window", "file_changes_count": 1}],
        file_snapshot={"solution.py": changed}, assignment=assignment)
    assert result["no_ai_engagement"] is False


def test_no_ai_engagement_false_when_no_change_detected(monkeypatch):
    """Mutual exclusivity (AC3): a no-op submission already gets a fully
    explained zero from the no-change short-circuit — it must not ALSO be
    flagged as no_ai_engagement, which would be a second, redundant, and
    less specific reason for the same root cause."""
    monkeypatch.setattr(LLMService, "chat", _explode_chat)
    assignment = {"title": "T", "description": "D", "evaluation_criteria": "C",
                  "starter_code": STARTER}
    result = EvaluationService.score_8_dimensions(
        session_logs=[], file_snapshot={"solution.py": STARTER}, assignment=assignment)
    assert result["no_ai_engagement"] is False


def test_no_ai_engagement_absent_on_scoring_failure(monkeypatch):
    """A swallowed LLM/parse failure is a DIFFERENT condition (evaluation_failed)
    from a genuine no-AI-evidence score — the safe-default path must not also
    report no_ai_engagement=True, which would misrepresent a scoring failure
    as a real, judged outcome."""
    monkeypatch.setattr(LLMService, "chat", lambda *a, **k: "not json")
    assignment = {"title": "T", "description": "D", "evaluation_criteria": "C",
                  "starter_code": STARTER}
    changed = "def solve(x):\n    return x * 2\n"
    result = EvaluationService.score_8_dimensions(
        session_logs=[], file_snapshot={"solution.py": changed}, assignment=assignment)
    assert result["evaluation_failed"] is True
    assert result.get("no_ai_engagement", False) is False
