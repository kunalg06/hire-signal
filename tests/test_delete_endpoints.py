"""DELETE /api/assignments/<id> and DELETE /api/submissions/<id> — real Flask
test client + isolated SQLite, following the pattern established in
test_candidates_endpoint.py (Story 7.4) and test_generate_challenge_endpoint.py
(Story 7.5) for this codebase's import-time db_service singleton trap.

Both app.routes.assignments.db_service and app.routes.submissions.db_service
are separate module-level singletons that must each be repointed at the same
isolated temp DB, since a request can touch either blueprint.
"""
import os

import pytest

import app.routes.assignments as assignments_module
import app.routes.submissions as submissions_module
from app.config import Config
from app.models.database import Database

REAL_DB_PATH = Config.DB_PATH
_counter = {"n": 0}
_real_db_baseline = {}


def _uid(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


@pytest.fixture(scope="module", autouse=True)
def _capture_real_db_baseline():
    if os.path.exists(REAL_DB_PATH):
        _real_db_baseline["size"] = os.path.getsize(REAL_DB_PATH)
        _real_db_baseline["mtime"] = os.path.getmtime(REAL_DB_PATH)
    yield


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = Database(str(tmp_path / "test.db"))
    test_db.init_db()
    monkeypatch.setattr(assignments_module.db_service, "db", test_db)
    monkeypatch.setattr(submissions_module.db_service, "db", test_db)

    from app import create_app
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def db(client):
    return assignments_module.db_service


def make_assignment(db_service, **overrides):
    assignment_id = overrides.pop("assignment_id", _uid("assignment"))
    defaults = dict(title="Test Assignment", description="desc",
                     starter_code="", evaluation_criteria="criteria")
    defaults.update(overrides)
    db_service.create_assignment(assignment_id, **defaults)
    return assignment_id


def make_submission_with_full_pipeline(db_service, assignment_id):
    """Creates a submission plus one row in every table it owns, so
    delete_submission's cascade can be verified against all of them."""
    link_id = _uid("link")
    submission_id = _uid("submission")

    db_service.create_session_link(link_id, assignment_id, container_id=None,
                                    port=None, expires_at="2099-01-01T00:00:00")
    db_service.create_submission(submission_id, link_id, assignment_id, files_json="[]")
    db_service.add_submission_file(_uid("file"), submission_id, "solution.py", "print(1)", 8)
    db_service.add_session_log(_uid("log"), submission_id, "2026-01-01T00:00:00",
                                "gemini_cli", "prompt", "summary", 0, "{}")
    db_service.create_dimension_score(_uid("dim"), submission_id,
                                       "problem_decomposition", 80, "good")
    db_service.create_hire_evaluation(_uid("eval"), submission_id,
                                       composite_score=80.0, recommendation="hire",
                                       dimension_weights_json="{}", narrative="n/a")
    return submission_id


# ── DELETE /api/assignments/<id> ─────────────────────────────────────────────

def test_delete_assignment_soft_deletes_and_hides_from_list(client, db):
    assignment_id = make_assignment(db)

    res = client.delete(f'/api/assignments/{assignment_id}')
    assert res.status_code == 200
    assert res.get_json()['deleted'] is True

    listed_ids = [a['id'] for a in client.get('/api/assignments').get_json()]
    assert assignment_id not in listed_ids


def test_delete_assignment_does_not_break_direct_lookup_of_historical_data(client, db):
    """A soft-deleted assignment must still resolve by direct id — existing
    session links / submissions / results referencing it must keep working."""
    assignment_id = make_assignment(db)
    client.delete(f'/api/assignments/{assignment_id}')

    res = client.get(f'/api/assignments/{assignment_id}')
    assert res.status_code == 200
    assert res.get_json()['id'] == assignment_id


def test_delete_assignment_404_for_nonexistent(client):
    res = client.delete('/api/assignments/does-not-exist')
    assert res.status_code == 404


def test_delete_assignment_twice_is_idempotent_200(client, db):
    assignment_id = make_assignment(db)
    assert client.delete(f'/api/assignments/{assignment_id}').status_code == 200
    # Second delete: get_assignment() still finds the (soft-deleted) row —
    # not-found only means "never existed", not "already deleted" — so this
    # is idempotent-success, not a 404.
    res = client.delete(f'/api/assignments/{assignment_id}')
    assert res.status_code == 200


# ── DELETE /api/submissions/<id> ─────────────────────────────────────────────

def test_delete_submission_removes_it_and_all_owned_rows(client, db):
    assignment_id = make_assignment(db)
    submission_id = make_submission_with_full_pipeline(db, assignment_id)

    res = client.delete(f'/api/submissions/{submission_id}')
    assert res.status_code == 200
    assert res.get_json()['deleted'] is True

    assert client.get(f'/api/submission/{submission_id}').status_code == 404
    assert db.get_submission_files(submission_id) == []
    assert db.get_session_logs(submission_id) == []
    assert db.get_dimension_scores(submission_id) == []
    assert db.get_hire_evaluation(submission_id) is None


def test_delete_submission_preserves_append_only_audit_logs(client, db):
    """score_overrides/flag_events must survive submission deletion —
    CLAUDE.md: 'score_overrides is append-only' / 'flag_events is
    append-only' — never UPDATE or DELETE from either, even here."""
    assignment_id = make_assignment(db)
    submission_id = make_submission_with_full_pipeline(db, assignment_id)

    db.flag_submission(submission_id, "reason", flagged_by="reviewer", event_id=_uid("flagevent"))
    db.override_hire_evaluation(submission_id, "strong_hire", "rationale",
                                 ai_recommendation="hire", override_id=_uid("override"))

    client.delete(f'/api/submissions/{submission_id}')

    with db.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM flag_events WHERE submission_id = ?', (submission_id,))
        assert cursor.fetchone()[0] == 1
        cursor.execute('SELECT COUNT(*) FROM score_overrides WHERE submission_id = ?', (submission_id,))
        assert cursor.fetchone()[0] == 1


def test_delete_submission_404_for_nonexistent(client):
    res = client.delete('/api/submissions/does-not-exist')
    assert res.status_code == 404


def test_delete_submission_does_not_affect_sibling_submissions(client, db):
    assignment_id = make_assignment(db)
    keep_id = make_submission_with_full_pipeline(db, assignment_id)
    delete_id = make_submission_with_full_pipeline(db, assignment_id)

    client.delete(f'/api/submissions/{delete_id}')

    assert client.get(f'/api/submission/{keep_id}').status_code == 200
    assert client.get(f'/api/submission/{delete_id}').status_code == 404


def test_real_db_file_untouched_by_this_suite():
    """Placed last (default pytest file-order execution, no randomization
    plugin installed) so it verifies the whole module, not just its own
    body, never touched the real DB — mirrors test_candidates_endpoint.py."""
    if "size" not in _real_db_baseline:
        pytest.skip("Real DB file did not exist before this suite ran")
    assert os.path.getsize(REAL_DB_PATH) == _real_db_baseline["size"]
    assert os.path.getmtime(REAL_DB_PATH) == _real_db_baseline["mtime"]
