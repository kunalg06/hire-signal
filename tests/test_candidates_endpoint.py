"""Story 7.4 — integration tests for GET /api/challenges/<id>/candidates.

Unlike Stories 7.1-7.3 (pure unit tests with mocked LLM/Docker), this drives
a real Flask test client against a real (but fully isolated) SQLite file.

CRITICAL #1: app.routes.challenges.db_service is a module-level singleton
constructed at import time from Config.DB_PATH, which defaults to the real
data/assignments.db. Because pytest imports all test files into one process,
that singleton already exists by the time this file runs (triggered by
Stories 7.1-7.3 importing app.services.evaluation_service -> app.config ->
app/__init__.py -> every blueprint). The fix is to directly monkeypatch the
blueprint's live db_service.db attribute per test — see the `client` fixture.

CRITICAL #2: create_app() ALSO builds its own internal Database(config.DB_PATH)
purely to call .init_db() during app setup — a SEPARATE instance from the
patched db_service, unrelated to what routes actually read/write, but it
still opens the real file and issues DDL against it if called with no config
(review finding, Story 7.4). Passing config_name='testing' points that
internal call at TestingConfig.DB_PATH ('data/test_assignments.db') instead
— a hardcoded literal, not env-var-dependent — so the real DB is never
touched by either code path.

Test ordering note: `test_real_db_file_untouched_by_this_suite` is placed
LAST in this file and relies on pytest's default file-order execution (no
randomization plugin is installed) to run after every other test's writes,
so it can prove the whole module — not just its own body — never touched
the real DB.
"""
import os

import pytest

import app.routes.challenges as challenges_module
from app.config import Config
from app.models.database import Database

REAL_DB_PATH = Config.DB_PATH

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
_real_db_baseline = {}


def _uid(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


@pytest.fixture(scope="module", autouse=True)
def _capture_real_db_baseline():
    """Runs once, before the first test in this module — captures the real
    DB's state before any fixture or test in this file has run anything."""
    if os.path.exists(REAL_DB_PATH):
        _real_db_baseline["size"] = os.path.getsize(REAL_DB_PATH)
        _real_db_baseline["mtime"] = os.path.getmtime(REAL_DB_PATH)
    yield


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
    """The blueprint's own db_service, now safely repointed at the temp DB
    by `client` — depending on `client` here (not just documenting it)
    guarantees the patch is applied before any test body runs."""
    return challenges_module.db_service


def make_challenge(db_service, **overrides):
    challenge_id = overrides.pop("challenge_id", _uid("challenge"))
    defaults = dict(
        title="Rate Limiter Bug", domain="backend",
        description="Fix the sliding window limiter",
        starter_code="def limiter(): pass",
        challenge_type="bug_fix", skill_area="rate_limiting",
        difficulty="medium", ai_assistance_mode="unguarded",
    )
    defaults.update(overrides)
    db_service.create_challenge(challenge_id, **defaults)
    return challenge_id


def make_evaluated_candidate(db_service, challenge_id, composite_score,
                             dimension_scores=None, recommendation="hire"):
    assignment_id = _uid("assignment")
    link_id = _uid("link")
    submission_id = _uid("submission")
    eval_id = _uid("eval")

    db_service.create_assignment(
        assignment_id, "Assignment", "Desc", "code", "criteria",
        challenge_id=challenge_id)
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


def make_unevaluated_candidate(db_service, challenge_id):
    assignment_id = _uid("assignment")
    link_id = _uid("link")
    submission_id = _uid("submission")

    db_service.create_assignment(
        assignment_id, "Assignment", "Desc", "code", "criteria",
        challenge_id=challenge_id)
    db_service.create_session_link(
        link_id, assignment_id, "container-x", 7100, "2099-01-01T00:00:00")
    db_service.create_submission(submission_id, link_id, assignment_id, "{}")
    return submission_id


# ── AC 2: 404 for missing challenge ─────────────────────────────────────────

def test_missing_challenge_returns_404(client):
    resp = client.get("/api/challenges/does-not-exist/candidates")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Challenge not found"}


# ── AC 3: empty list for a challenge with zero candidates ──────────────────

def test_challenge_with_no_candidates_returns_empty_list(client, db):
    challenge_id = make_challenge(db)
    resp = client.get(f"/api/challenges/{challenge_id}/candidates")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["candidates"] == []
    assert body["total"] == 0
    assert body["dimension_averages"] == {}


# ── AC 4, 5: sorting ─────────────────────────────────────────────────────────

def test_default_sort_is_composite_score_descending(client, db):
    challenge_id = make_challenge(db)
    make_evaluated_candidate(db, challenge_id, 50)
    make_evaluated_candidate(db, challenge_id, 90)
    make_evaluated_candidate(db, challenge_id, 70)

    resp = client.get(f"/api/challenges/{challenge_id}/candidates")
    body = resp.get_json()
    scores = [c["composite_score"] for c in body["candidates"]]
    ranks = [c["rank"] for c in body["candidates"]]
    assert scores == [90, 70, 50]
    assert ranks == [1, 2, 3]
    assert body["total"] == 3


def test_order_asc_reverses_default_sort(client, db):
    challenge_id = make_challenge(db)
    make_evaluated_candidate(db, challenge_id, 50)
    make_evaluated_candidate(db, challenge_id, 90)
    make_evaluated_candidate(db, challenge_id, 70)

    resp = client.get(f"/api/challenges/{challenge_id}/candidates?order=asc")
    body = resp.get_json()
    scores = [c["composite_score"] for c in body["candidates"]]
    ranks = [c["rank"] for c in body["candidates"]]
    assert scores == [50, 70, 90]
    assert ranks == [1, 2, 3]


def test_sort_by_dimension_key_ranks_by_that_dimension_not_composite(client, db):
    # Anti-correlated with composite on purpose: if sort_by were silently
    # ignored and the route fell back to composite order, this would fail.
    challenge_id = make_challenge(db)
    sub_high_composite_low_dim = make_evaluated_candidate(
        db, challenge_id, 90,
        dimension_scores={**{d: 90 for d in ALL_DIMS}, "architecture_decisions": 20})
    sub_low_composite_high_dim = make_evaluated_candidate(
        db, challenge_id, 50,
        dimension_scores={**{d: 50 for d in ALL_DIMS}, "architecture_decisions": 95})
    make_unevaluated_candidate(db, challenge_id)

    resp = client.get(
        f"/api/challenges/{challenge_id}/candidates"
        "?sort_by=architecture_decisions&order=desc")
    candidates = resp.get_json()["candidates"]
    evaluated = [c for c in candidates if c["is_evaluated"]]
    dims = [c["dimensions"]["architecture_decisions"]["score"] for c in evaluated]
    ids = [c["submission_id"] for c in evaluated]
    assert dims == [95, 20]
    # Order is by the dimension (95 first), the OPPOSITE of composite order
    assert ids == [sub_low_composite_high_dim, sub_high_composite_low_dim]
    # Visibility floor holds on the dimension-sort branch too
    assert candidates[-1]["is_evaluated"] is False


# ── AC 6: dimension_averages ────────────────────────────────────────────────

def test_dimension_averages_computed_only_over_evaluated(client, db):
    challenge_id = make_challenge(db)
    # Distinct, non-mirrored per-dimension values so a key mix-up in the
    # averaging code would produce a wrong value for a SPECIFIC dimension,
    # not an equally-wrong value for all of them.
    candidate_a = {d: 10 + 10 * i for i, d in enumerate(ALL_DIMS)}
    candidate_b = {d: 15 + 10 * i for i, d in enumerate(ALL_DIMS)}
    make_evaluated_candidate(db, challenge_id, 70, dimension_scores=candidate_a)
    make_evaluated_candidate(db, challenge_id, 70, dimension_scores=candidate_b)
    make_unevaluated_candidate(db, challenge_id)

    resp = client.get(f"/api/challenges/{challenge_id}/candidates")
    averages = resp.get_json()["dimension_averages"]
    assert set(averages) == set(ALL_DIMS)
    for d in ALL_DIMS:
        expected = round((candidate_a[d] + candidate_b[d]) / 2, 1)
        assert averages[d] == expected


def test_dimension_averages_empty_when_none_evaluated(client, db):
    challenge_id = make_challenge(db)
    make_unevaluated_candidate(db, challenge_id)
    make_unevaluated_candidate(db, challenge_id)

    resp = client.get(f"/api/challenges/{challenge_id}/candidates")
    assert resp.get_json()["dimension_averages"] == {}


# ── AC 7: visibility floor ──────────────────────────────────────────────────

def test_unevaluated_candidates_sort_last_in_both_directions(client, db):
    challenge_id = make_challenge(db)
    make_evaluated_candidate(db, challenge_id, 90)
    make_evaluated_candidate(db, challenge_id, 50)
    make_unevaluated_candidate(db, challenge_id)

    desc = client.get(f"/api/challenges/{challenge_id}/candidates?order=desc")
    desc_body = desc.get_json()
    desc_flags = [c["is_evaluated"] for c in desc_body["candidates"]]
    assert desc_flags == [True, True, False]
    assert [c["rank"] for c in desc_body["candidates"]] == [1, 2, 3]

    asc = client.get(f"/api/challenges/{challenge_id}/candidates?order=asc")
    asc_body = asc.get_json()
    asc_flags = [c["is_evaluated"] for c in asc_body["candidates"]]
    assert asc_flags == [True, True, False]
    assert [c["rank"] for c in asc_body["candidates"]] == [1, 2, 3]
    # asc among the evaluated pair is still ascending; only the tail is fixed
    asc_scores = [c["composite_score"] for c in asc_body["candidates"]
                  if c["is_evaluated"]]
    assert asc_scores == [50, 90]

    # Unevaluated candidate's own response shape
    unevaluated = desc_body["candidates"][-1]
    assert unevaluated["composite_score"] is None
    assert unevaluated["dimensions"] == {}


# ── Cross-challenge isolation of results (not the DB-file isolation above) ─

def test_candidates_from_other_challenges_are_excluded(client, db):
    challenge_a = make_challenge(db, title="Challenge A")
    challenge_b = make_challenge(db, title="Challenge B")
    sub_a = make_evaluated_candidate(db, challenge_a, 80)
    sub_b = make_evaluated_candidate(db, challenge_b, 95)

    resp = client.get(f"/api/challenges/{challenge_a}/candidates")
    body = resp.get_json()
    submission_ids = [c["submission_id"] for c in body["candidates"]]
    assert submission_ids == [sub_a]
    assert sub_b not in submission_ids
    assert body["total"] == 1


# ── AC 8: query validation ──────────────────────────────────────────────────

def test_invalid_sort_by_returns_400(client, db):
    challenge_id = make_challenge(db)
    resp = client.get(f"/api/challenges/{challenge_id}/candidates?sort_by=nope")
    assert resp.status_code == 400


def test_invalid_order_returns_400(client, db):
    challenge_id = make_challenge(db)
    resp = client.get(f"/api/challenges/{challenge_id}/candidates?order=sideways")
    assert resp.status_code == 400


def test_missing_challenge_wins_over_invalid_query_params(client):
    # Challenge-existence check runs before sort_by/order validation
    # (app/routes/challenges.py:202 precedes :208) — 404, not 400.
    resp = client.get(
        "/api/challenges/does-not-exist/candidates?sort_by=nope&order=sideways")
    assert resp.status_code == 404


# ── AC 1: isolation proof (see module docstring re: ordering) ──────────────

def test_real_db_file_untouched_by_this_suite():
    if "size" not in _real_db_baseline:
        pytest.skip(
            f"real DB not present at {REAL_DB_PATH} when this module "
            "started — cannot prove isolation, but nothing in this file "
            "can have touched a file that didn't exist")
    assert os.path.getsize(REAL_DB_PATH) == _real_db_baseline["size"]
    assert os.path.getmtime(REAL_DB_PATH) == _real_db_baseline["mtime"]
