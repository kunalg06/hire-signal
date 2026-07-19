"""Tests for GET /api/assignments/<assignment_id>/candidates.

No test file existed for this endpoint before this change. Extends Story
9.1's N+1 fix (originally scoped to the challenges.py sibling endpoint only)
to this endpoint too, reusing the same DatabaseService.
get_dimension_scores_for_submissions() batched method — see deferred-work.md
and the code-review that flagged this as a trivial, risk-free reuse.

Fixture pattern mirrors tests/test_candidates_endpoint.py: real Flask test
client + isolated tmp-path SQLite, db_service.db monkeypatched directly
since app.routes.assignments.db_service is an import-time singleton.
"""
import pytest

import app.routes.assignments as assignments_module
from app.models.database import Database
from app.utils.helpers import IDGenerator

ALL_DIMS = [
    "problem_decomposition",
    "first_principles_thinking",
    "creative_problem_solving",
    "iteration_quality",
    "debugging_with_ai",
    "architecture_decisions",
    "communication_clarity",
    "token_efficiency",
]

_counter = {"n": 0}


def _uid(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = Database(str(tmp_path / "test.db"))
    test_db.init_db()
    monkeypatch.setattr(assignments_module.db_service, "db", test_db)

    from app import create_app
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def db(client):
    return assignments_module.db_service


def make_assignment(db_service):
    assignment_id = _uid("assignment")
    db_service.create_assignment(
        assignment_id, "Assignment", "Desc", "code", "criteria")
    return assignment_id


def make_evaluated_candidate(db_service, assignment_id, composite_score,
                             dimension_scores=None, recommendation="hire"):
    link_id = _uid("link")
    submission_id = _uid("submission")
    eval_id = _uid("eval")

    db_service.create_session_link(
        link_id, assignment_id, "container-x", 7100, "2099-01-01T00:00:00")
    db_service.create_submission(submission_id, link_id, assignment_id, "{}")
    db_service.create_hire_evaluation(
        eval_id, submission_id, composite_score, recommendation,
        "{}", "narrative")

    dims = dimension_scores or {d: composite_score for d in ALL_DIMS}
    for dim, score in dims.items():
        db_service.create_dimension_score(
            _uid("dim"), submission_id, dim, score, "evidence")

    return submission_id


def make_unevaluated_candidate(db_service, assignment_id):
    link_id = _uid("link")
    submission_id = _uid("submission")
    db_service.create_session_link(
        link_id, assignment_id, "container-x", 7100, "2099-01-01T00:00:00")
    db_service.create_submission(submission_id, link_id, assignment_id, "{}")
    return submission_id


def test_missing_assignment_returns_404(client):
    resp = client.get("/api/assignments/does-not-exist/candidates")
    assert resp.status_code == 404


def test_assignment_with_no_candidates_returns_empty_list(client, db):
    assignment_id = make_assignment(db)
    resp = client.get(f"/api/assignments/{assignment_id}/candidates")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["candidates"] == []
    assert body["total"] == 0
    assert body["dimension_averages"] == {}


def test_candidates_ranked_by_composite_score_descending(client, db):
    assignment_id = make_assignment(db)
    make_evaluated_candidate(db, assignment_id, 50)
    make_evaluated_candidate(db, assignment_id, 90)
    make_evaluated_candidate(db, assignment_id, 70)

    resp = client.get(f"/api/assignments/{assignment_id}/candidates")
    body = resp.get_json()
    scores = [c["composite_score"] for c in body["candidates"]]
    ranks = [c["rank"] for c in body["candidates"]]
    assert scores == [90, 70, 50]
    assert ranks == [1, 2, 3]


def test_dimension_scores_fetched_in_one_batched_call(client, db, monkeypatch):
    assignment_id = make_assignment(db)
    make_evaluated_candidate(db, assignment_id, 90)
    make_evaluated_candidate(db, assignment_id, 70)
    make_evaluated_candidate(db, assignment_id, 50)

    calls = []
    original = db.get_dimension_scores_for_submissions
    def spy(submission_ids):
        calls.append(submission_ids)
        return original(submission_ids)
    monkeypatch.setattr(db, "get_dimension_scores_for_submissions", spy)

    resp = client.get(f"/api/assignments/{assignment_id}/candidates")
    assert resp.status_code == 200
    assert len(calls) == 1
    assert len(calls[0]) == 3


def test_batched_dimension_scores_attributed_to_correct_candidate(client, db):
    assignment_id = make_assignment(db)
    sub_a = make_evaluated_candidate(db, assignment_id, 80,
        dimension_scores={d: 10 for d in ALL_DIMS})
    sub_b = make_evaluated_candidate(db, assignment_id, 80,
        dimension_scores={d: 90 for d in ALL_DIMS})
    sub_c = make_evaluated_candidate(db, assignment_id, 80,
        dimension_scores={d: 50 for d in ALL_DIMS})

    resp = client.get(f"/api/assignments/{assignment_id}/candidates")
    by_id = {c["submission_id"]: c for c in resp.get_json()["candidates"]}
    assert by_id[sub_a]["dimensions"]["problem_decomposition"]["score"] == 10
    assert by_id[sub_b]["dimensions"]["problem_decomposition"]["score"] == 90
    assert by_id[sub_c]["dimensions"]["problem_decomposition"]["score"] == 50


def test_dimension_averages_computed_only_over_evaluated(client, db):
    assignment_id = make_assignment(db)
    candidate_a = {d: 10 + 10 * i for i, d in enumerate(ALL_DIMS)}
    candidate_b = {d: 15 + 10 * i for i, d in enumerate(ALL_DIMS)}
    make_evaluated_candidate(db, assignment_id, 70, dimension_scores=candidate_a)
    make_evaluated_candidate(db, assignment_id, 70, dimension_scores=candidate_b)
    make_unevaluated_candidate(db, assignment_id)

    resp = client.get(f"/api/assignments/{assignment_id}/candidates")
    averages = resp.get_json()["dimension_averages"]
    assert set(averages) == set(ALL_DIMS)
    for d in ALL_DIMS:
        expected = round((candidate_a[d] + candidate_b[d]) / 2, 1)
        assert averages[d] == expected


# ── is_flagged/flag_reason visibility (demo-video dry-run, 2026-07-19) ──────
# get_candidates_for_assignment() previously selected neither column, so a
# genuinely flagged submission was invisible to any caller (including the
# frontend's Results tab and Compare Candidates tab) that looked candidates
# up by assignment_id rather than challenge_id — the two endpoints had
# silently drifted apart. Mirrors
# test_candidates_endpoint.py's test_flagged_candidate_marked_in_payload_but_not_hidden
# for the challenge-scoped sibling.

def test_flagged_candidate_marked_in_payload_but_not_hidden(client, db):
    assignment_id = make_assignment(db)
    flagged_sub = make_evaluated_candidate(db, assignment_id, 90)
    clean_sub = make_evaluated_candidate(db, assignment_id, 80)
    db.flag_submission(flagged_sub, "suspected plagiarism", flagged_by="employer-1")

    resp = client.get(f"/api/assignments/{assignment_id}/candidates")
    body = resp.get_json()
    by_id = {c["submission_id"]: c for c in body["candidates"]}

    assert by_id[flagged_sub]["is_flagged"] is True
    assert by_id[flagged_sub]["flag_reason"] == "suspected plagiarism"
    assert by_id[clean_sub]["is_flagged"] is False
    assert by_id[clean_sub]["flag_reason"] is None
    # Visibility floor: flagging never removes or reorders past composite rank
    assert [c["submission_id"] for c in body["candidates"]] == [flagged_sub, clean_sub]
