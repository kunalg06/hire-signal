"""Party-mode review 2026-07-11 (Murat/Test Architect): a swallowed judge
parse/API failure inside EvaluationService.score_8_dimensions() must not
look identical to a candidate who genuinely earned a 0 — both would
otherwise land on composite_score=0.0/"pass" with no way to tell them
apart. score_8_dimensions() now marks this case with evaluation_failed=True
(see tests/test_score_8_dimensions.py for that unit-level contract); this
file confirms app.routes.submissions.evaluate_submission_files() actually
acts on the flag by auto-flagging the submission for manual review, using
the SAME flag_submission()/flag_events audit-log path a human reviewer
would use — no new schema, no bypass of the append-only audit log.

Uses the same DB-isolation pattern as test_submit_with_files_session_logs.py
for this codebase's import-time db_service singleton trap.
"""
import pytest

import app.routes.submissions as submissions_module
from app.models.database import Database
from app.services.evaluation_service import EvaluationService
from app.utils.helpers import IDGenerator


@pytest.fixture
def db(monkeypatch, tmp_path):
    test_db = Database(str(tmp_path / "test.db"))
    test_db.init_db()
    monkeypatch.setattr(submissions_module.db_service, "db", test_db)
    return submissions_module.db_service


def make_submission(db_service):
    assignment_id = IDGenerator.generate_uuid()
    link_id = IDGenerator.generate_uuid()
    submission_id = IDGenerator.generate_uuid()
    db_service.create_assignment(assignment_id, "Title", "Desc", "code", "criteria")
    db_service.create_session_link(link_id, assignment_id, container_id="fake-container",
                                    port=7100, expires_at="2099-01-01T00:00:00")
    db_service.create_submission(submission_id, link_id, assignment_id, "[]")
    db_service.add_submission_file(IDGenerator.generate_file_id(), submission_id,
                                    "solution.py", "print('x')", 12)
    return assignment_id, submission_id


def test_evaluation_failed_result_auto_flags_submission(db, monkeypatch):
    """A score_8_dimensions() failure (evaluation_failed=True) must leave the
    submission flagged for manual review, not silently stored as a real 0."""
    _, submission_id = make_submission(db)

    def fake_evaluate_code(*a, **k):
        return {
            "hire_recommendation": "pass",
            "composite_score": 0.0,
            "recommendation_rationale": "Scoring error: provider down",
            "dimensions": {d: {"score": 0, "rationale": "Scoring error", "applicable": True}
                           for d in EvaluationService.DIMENSION_WEIGHTS},
            "evaluation_failed": True,
            "score": 0.0,
            "feedback": "Scoring error: provider down",
            "evaluation_details": {},
        }
    monkeypatch.setattr(EvaluationService, "evaluate_code", fake_evaluate_code)

    assignment = {"id": "a", "title": "T", "description": "D", "evaluation_criteria": "C"}
    submissions_module.evaluate_submission_files(submission_id, assignment)

    row = db.get_submission(submission_id)
    # is_flagged is column index 10 per get_submission's SELECT (verified via
    # the existing flag route tests) — assert truthy rather than pin the
    # exact index a second time.
    is_flagged = row[10] if len(row) > 10 else None
    assert is_flagged, "submission must be auto-flagged when evaluation_failed=True"


def test_successful_evaluation_does_not_auto_flag(db, monkeypatch):
    """Sanity check: a genuine (non-failed) evaluation must NOT be flagged —
    proves the auto-flag is conditional on evaluation_failed, not unconditional."""
    _, submission_id = make_submission(db)

    def fake_evaluate_code(*a, **k):
        return {
            "hire_recommendation": "hire",
            "composite_score": 80.0,
            "recommendation_rationale": "Solid work",
            "dimensions": {d: {"score": 80, "rationale": "evidence", "applicable": True}
                           for d in EvaluationService.DIMENSION_WEIGHTS},
            "evaluation_failed": False,
            "score": 80.0,
            "feedback": "Solid work",
            "evaluation_details": {},
        }
    monkeypatch.setattr(EvaluationService, "evaluate_code", fake_evaluate_code)

    assignment = {"id": "a", "title": "T", "description": "D", "evaluation_criteria": "C"}
    submissions_module.evaluate_submission_files(submission_id, assignment)

    row = db.get_submission(submission_id)
    is_flagged = row[10] if len(row) > 10 else None
    assert not is_flagged


# ── no_ai_engagement auto-flag (party-mode 2026-07-19, Amelia's Option C) ──
# A real code change submitted with zero Gemini session logs leaves 4 of 8
# dimensions unscoreable for lack of AI-interaction evidence — a genuine
# score, not a scoring failure, but one where the platform deliberately
# doesn't decide whether the resulting low composite is fair (see
# score_8_dimensions()'s no_ai_engagement comment in evaluation_service.py).
# Mirrors the evaluation_failed auto-flag above: same flag_submission()/
# flag_events audit path, no new schema.

def test_no_ai_engagement_result_auto_flags_submission(db, monkeypatch):
    _, submission_id = make_submission(db)

    def fake_evaluate_code(*a, **k):
        return {
            "hire_recommendation": "pass",
            "composite_score": 38.0,
            "recommendation_rationale": "Fixed the bug, but no AI session logs to judge",
            "dimensions": {d: {"score": 50, "rationale": "evidence", "applicable": True}
                           for d in EvaluationService.DIMENSION_WEIGHTS},
            "evaluation_failed": False,
            "no_ai_engagement": True,
            "score": 38.0,
            "feedback": "Fixed the bug, but no AI session logs to judge",
            "evaluation_details": {},
        }
    monkeypatch.setattr(EvaluationService, "evaluate_code", fake_evaluate_code)

    assignment = {"id": "a", "title": "T", "description": "D", "evaluation_criteria": "C"}
    submissions_module.evaluate_submission_files(submission_id, assignment)

    row = db.get_submission(submission_id)
    is_flagged = row[10] if len(row) > 10 else None
    flag_reason = row[11] if len(row) > 11 else None
    assert is_flagged, "submission must be auto-flagged when no_ai_engagement=True"
    assert "session logs" in flag_reason


def test_no_ai_engagement_false_does_not_auto_flag(db, monkeypatch):
    """Sanity check: a genuine change WITH session logs must not be flagged
    by this path — proves the auto-flag is conditional on no_ai_engagement,
    not unconditional on every successful evaluation."""
    _, submission_id = make_submission(db)

    def fake_evaluate_code(*a, **k):
        return {
            "hire_recommendation": "hire",
            "composite_score": 80.0,
            "recommendation_rationale": "Solid work, good AI collaboration",
            "dimensions": {d: {"score": 80, "rationale": "evidence", "applicable": True}
                           for d in EvaluationService.DIMENSION_WEIGHTS},
            "evaluation_failed": False,
            "no_ai_engagement": False,
            "score": 80.0,
            "feedback": "Solid work",
            "evaluation_details": {},
        }
    monkeypatch.setattr(EvaluationService, "evaluate_code", fake_evaluate_code)

    assignment = {"id": "a", "title": "T", "description": "D", "evaluation_criteria": "C"}
    submissions_module.evaluate_submission_files(submission_id, assignment)

    row = db.get_submission(submission_id)
    is_flagged = row[10] if len(row) > 10 else None
    assert not is_flagged
