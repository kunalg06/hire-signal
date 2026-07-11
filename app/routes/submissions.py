import logging
import threading
import json
from flask import Blueprint, request, jsonify
from app.services.database_service import DatabaseService
from app.services.docker_service import DockerService
from app.services.session_log_service import SessionLogService
from app.services.evaluation_service import EvaluationService
from app.utils.helpers import IDGenerator

submissions_bp = Blueprint('submissions', __name__, url_prefix='/api')
db_service = DatabaseService()
logger = logging.getLogger(__name__)

VALID_RECOMMENDATIONS = {'strong_hire', 'hire', 'select', 'pass'}

def _str_field(data, key, default=''):
    # Coerce non-string values (e.g. an explicit `null` or a number) to the
    # default instead of crashing .strip() with an AttributeError.
    value = data.get(key)
    return (value if isinstance(value, str) else default).strip()

def evaluate_submission_files(submission_id, assignment, session_logs=None,
                              container_created_at=None, container_id=None,
                              file_snapshot=None):
    """Evaluate submitted files using the 8-dimension scoring engine"""
    try:
        # Get solution.py from stored submission files
        files = db_service.get_submission_files(submission_id)
        code = next((c for fn, c in files if fn == 'solution.py'), "# No solution.py found")

        # Reload session logs from DB if not supplied
        if session_logs is None:
            log_rows = db_service.get_session_logs(submission_id)
            session_logs = [
                {
                    'timestamp':          row[0],
                    'interaction_type':   row[1],
                    'prompt':             row[2],
                    'response_summary':   row[3],
                    'file_changes_count': row[4],
                }
                for row in log_rows
            ] if log_rows else []

        # Fix: get container_created_at from submissions → session_links
        if container_created_at is None:
            submission_row = db_service.get_submission(submission_id)
            if submission_row:
                container_created_at = db_service.get_link_created_time(submission_row[1])

        # Run 8-dimension evaluation
        evaluation = EvaluationService.evaluate_code(
            code=code,
            assignment=assignment,
            session_logs=session_logs,
            container_created_at=container_created_at,
            container_id=container_id,
            file_snapshot=file_snapshot,
        )

        # Persist base result to submissions table
        db_service.update_submission_evaluation(
            submission_id,
            evaluation["score"],
            evaluation["feedback"],
            evaluation["evaluation_details"],
        )

        # Persist per-dimension scores
        dims = evaluation.get("dimensions", {})
        for dimension, dim_data in dims.items():
            score_id = IDGenerator.generate_uuid()
            db_service.create_dimension_score(
                score_id=score_id,
                submission_id=submission_id,
                dimension=dimension,
                score=int(dim_data.get("score", 0)),
                rationale=dim_data.get("rationale", ""),
            )

        # Persist hire evaluation verdict
        eval_id = IDGenerator.generate_uuid()
        db_service.create_hire_evaluation(
            eval_id=eval_id,
            submission_id=submission_id,
            composite_score=evaluation["composite_score"],
            recommendation=evaluation["hire_recommendation"],
            dimension_weights_json=json.dumps(EvaluationService.DIMENSION_WEIGHTS),
            narrative=evaluation.get("recommendation_rationale", ""),
        )

        logger.info(
            "Evaluation complete for %s: score=%.1f (%s)",
            submission_id,
            evaluation['composite_score'],
            evaluation['hire_recommendation'],
        )

        # Party-mode review 2026-07-11 (Murat/Test Architect): a swallowed
        # judge parse/API failure must never look identical to a candidate
        # who genuinely earned 0. score_8_dimensions() marks this case with
        # evaluation_failed=True; auto-flag it here using the EXISTING
        # flag/audit infrastructure so it surfaces for manual review instead
        # of silently standing in as a real hire decision.
        if evaluation.get("evaluation_failed"):
            event_id = IDGenerator.generate_uuid()
            db_service.flag_submission(
                submission_id,
                "AI evaluation failed (parse/API error) — composite score is a "
                "placeholder, not a real judgment. Needs manual review.",
                flagged_by="system",
                event_id=event_id,
            )
            logger.warning(
                "Submission %s auto-flagged: evaluation_failed", submission_id)

    except Exception as e:
        logger.error("Failed to evaluate submission %s: %s", submission_id, e)

@submissions_bp.route('/submissions', methods=['GET'])
def list_submissions():
    """List all submissions for the recruiter dashboard. Optional filters:
    ?recommendation=strong_hire|hire|select|pass  &assignment_id=<uuid>"""
    rec_filter    = request.args.get('recommendation', '').strip() or None
    assign_filter = request.args.get('assignment_id', '').strip() or None

    rows = db_service.list_submissions(rec_filter, assign_filter)
    results = []
    for row in rows:
        results.append({
            "submission_id":    row[0],
            "assignment_id":    row[1],
            "assignment_title": row[2],
            "submitted_at":     row[3],
            "score":            row[4],
            "evaluated_at":     row[5],
            "composite_score":  row[6],
            "recommendation":   row[7],
        })
    return jsonify({"submissions": results, "total": len(results)}), 200


@submissions_bp.route('/submit-with-files/<link_id>', methods=['POST'])
def submit_with_files(link_id):
    """Submit files from student workspace"""
    # Get session and assignment info
    row = db_service.get_link_container_info(link_id)

    if not row:
        return jsonify({"detail": "Session not found"}), 404

    container_id, assignment_id, title, description, criteria, container_created_at, challenge_id = row

    # applicable_dimensions/decision_point (party-mode review 2026-07-11):
    # None-safe — assignments not linked to a catalog challenge, or
    # challenges created before this feature, simply get the pre-existing
    # "all 8 dimensions apply, no decision point" behavior.
    applicable_dimensions, decision_point = (None, None)
    if challenge_id:
        applicable_dimensions, decision_point = db_service.get_challenge_dimension_config(challenge_id)

    # Create assignment dict for evaluation
    assignment = {
        "id": assignment_id,
        "title": title,
        "description": description,
        "evaluation_criteria": criteria,
        "applicable_dimensions": applicable_dimensions,
        "decision_point": decision_point,
    }

    # Collect files from container
    files_dict = {}
    gemini_chat_files = {}

    if container_id:
        logger.info("Reading files from container %s...", container_id[:12])

        # Get solution.py
        solution_content = DockerService.get_file_from_container(container_id, '/workspace/solution.py')
        if solution_content and solution_content.strip() != "":
            files_dict['solution.py'] = solution_content
            logger.debug("  [ok] solution.py (%s bytes)", len(solution_content))

        # Get instructions.md
        instructions_content = DockerService.get_file_from_container(container_id, '/workspace/instructions.md')
        if instructions_content:
            files_dict['instructions.md'] = instructions_content
            logger.debug("  [ok] instructions.md (%s bytes)", len(instructions_content))

        # Pull Gemini CLI's real session transcripts (~/.gemini/tmp/*/chats/*.jsonl).
        # Previously this looked for /tmp/claude_session.log and similar
        # Claude-Code-CLI paths left over from before this project migrated
        # to Gemini — Gemini CLI never wrote to any of those paths, so
        # session_logs was always empty for every real submission. Fixed:
        # see AGENT.md's session-log-capture-fix entry for how the real
        # path/format was found.
        gemini_chat_files = DockerService.get_gemini_chat_files(container_id)
        logger.debug("  [ok] %s Gemini session transcript file(s)", len(gemini_chat_files))

    # If no solution.py found, create default
    if 'solution.py' not in files_dict:
        files_dict['solution.py'] = "# solution.py not found"
        logger.warning("solution.py not found in workspace")

    # Create submission record
    submission_id = IDGenerator.generate_uuid()
    files_json = json.dumps(list(files_dict.keys()))

    db_service.create_submission(submission_id, link_id, assignment_id, files_json)

    # Store individual files
    for filename, content in files_dict.items():
        file_id = IDGenerator.generate_file_id()
        file_size = len(content.encode('utf-8')) if isinstance(content, str) else len(content)
        db_service.add_submission_file(file_id, submission_id, filename, content, file_size)

    # Parse and store Gemini session logs if available
    session_logs = []

    if gemini_chat_files:
        try:
            session_logs = SessionLogService.parse_gemini_chat_sessions(gemini_chat_files)

            # Store parsed logs in session_logs table
            for log_entry in session_logs:
                log_id = IDGenerator.generate_log_id()
                db_service.add_session_log(
                    log_id,
                    submission_id,
                    log_entry.get('timestamp'),
                    log_entry.get('interaction_type', 'gemini_cli'),
                    log_entry.get('prompt', ''),
                    log_entry.get('response_summary', ''),
                    log_entry.get('file_changes_count', 0),
                    log_entry.get('raw_json', ''),
                    log_entry.get('token_count', 0)
                )

            logger.debug("  [ok] Stored %s session log entries", len(session_logs))
        except Exception as e:
            logger.warning("Failed to parse/store session logs: %s", e)

    # Extract full workspace snapshot NOW (before container cleanup)
    file_snapshot = {}
    if container_id:
        file_snapshot = EvaluationService.extract_container_files(container_id)
        logger.debug("  [ok] workspace snapshot: %s files", len(file_snapshot))

    # Schedule evaluation in background
    thread = threading.Thread(
        target=evaluate_submission_files,
        args=(submission_id, assignment, session_logs,
              container_created_at, container_id, file_snapshot)
    )
    thread.daemon = True
    thread.start()

    # Schedule container cleanup (after snapshot is already taken)
    cleanup_thread = threading.Thread(
        target=DockerService.cleanup_container,
        args=(container_id,)
    )
    cleanup_thread.daemon = True
    cleanup_thread.start()

    return jsonify({
        "submission_id": submission_id,
        "status": "submitted",
        "message": "Files submitted successfully. Evaluation in progress...",
        "session_logs_count": len(session_logs)
    }), 202

@submissions_bp.route('/submission/<submission_id_or_link>', methods=['GET'])
def get_submission(submission_id_or_link):
    """Retrieve submission and evaluation results by submission_id or link_id"""
    # Try to get by submission_id first
    row = db_service.get_submission(submission_id_or_link)

    # If not found and looks like a link_id, try to find submission by link_id
    if not row:
        # Get submissions with matching link_id
        with db_service.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.submission_id, s.link_id, s.assignment_id, s.code, s.submitted_at,
                       s.evaluation_result, s.score, s.feedback, a.title, a.evaluation_criteria,
                       s.is_flagged, s.flag_reason, s.flag_by, s.flagged_at
                FROM submissions s
                JOIN assignments a ON s.assignment_id = a.id
                WHERE s.link_id = ?
                ORDER BY s.submitted_at DESC
                LIMIT 1
            ''', (submission_id_or_link,))
            row = cursor.fetchone()

            if not row:
                return jsonify({"detail": "Submission not found"}), 404

            submission_id = row[0]
    else:
        submission_id = submission_id_or_link

    files = db_service.get_submission_files(submission_id)

    instructions_md = ""
    gemini_logs = ""
    for filename, content in files:
        if filename == 'instructions.md':
            instructions_md = content
        elif filename == 'gemini_session.log':
            gemini_logs = content

    # Fetch 8-dimension scores
    dim_rows = db_service.get_dimension_scores(submission_id)
    dimensions = {
        r[0]: {"score": r[1], "rationale": r[2], "scoring_method": r[3]}
        for r in dim_rows
    } if dim_rows else {}

    # Fetch hire evaluation
    hire_row = db_service.get_hire_evaluation(submission_id)
    if hire_row:
        hire_data = {
            "composite_score":          hire_row[0],
            "hire_recommendation":      hire_row[1],
            "dimension_weights":        json.loads(hire_row[2]) if hire_row[2] else {},
            "recommendation_rationale": hire_row[3],
            "is_overridden":            bool(hire_row[4]),
            "override_recommendation":  hire_row[5],
            "override_rationale":       hire_row[6],
            "evaluated_at":             hire_row[7],
        }
    else:
        hire_data = None

    # Guarded-mode injection outcome (Story 9.3) — surfaces whether a
    # "guarded" assessment actually got its GEMINI.md restriction applied.
    ai_mode, guarded_enforced = db_service.get_session_link_assistance_info(row[1])

    # Raw AI token usage (party-mode review 2026-07-11): neutral telemetry
    # only, mode-stamped via ai_assistance_mode above so a recruiter doesn't
    # compare guarded/unguarded token counts apples-to-oranges — never
    # scored, never a gate, never folded into hire_evaluation.
    total_tokens_used = db_service.get_total_tokens_for_submission(submission_id)

    return jsonify({
        # Core submission fields
        "submission_id":    row[0],
        "link_id":          row[1],
        "assignment_id":    row[2],
        "code":             row[3],
        "submitted_at":     row[4],
        "evaluation_result": row[5],
        "score":            row[6],
        "feedback":         row[7],
        "assignment_title": row[8],
        # Flag status (Story 4.3)
        "is_flagged":  bool(row[10]) if len(row) > 10 and row[10] is not None else False,
        "flag_reason": row[11] if len(row) > 11 else None,
        "flag_by":     row[12] if len(row) > 12 else None,
        "flagged_at":  row[13] if len(row) > 13 else None,
        # AI assistance mode + guarded-mode enforcement outcome (Story 9.3)
        "ai_assistance_mode":    ai_mode,
        "guarded_mode_enforced": bool(guarded_enforced) if guarded_enforced is not None else None,
        # Raw AI token usage — informational only, see comment above
        "total_tokens_used": total_tokens_used,
        # Supporting content
        "instructions_md":  instructions_md,
        "gemini_logs":      gemini_logs or "No Gemini session logs available",
        # 8-dimension scoring
        "dimensions":       dimensions,
        "hire_evaluation":  hire_data,
    })

@submissions_bp.route('/session-logs/<submission_id>', methods=['GET'])
def get_session_logs(submission_id):
    """Get Gemini session logs for a submission"""
    rows = db_service.get_session_logs(submission_id)

    logs = [
        {
            'timestamp': row[0],
            'interaction_type': row[1],
            'prompt': row[2],
            'response_summary': row[3],
            'file_changes_count': row[4],
            'token_count': row[5] if len(row) > 5 and row[5] is not None else 0,
        }
        for row in rows
    ]

    return jsonify({
        "submission_id": submission_id,
        "logs": logs,
        "total_interactions": len(logs),
        "total_tokens_used": sum(l['token_count'] for l in logs),
    })


@submissions_bp.route('/submissions/<submission_id>', methods=['DELETE'])
def delete_submission(submission_id):
    """Permanently delete a submission and its owned rows (files, session
    logs, dimension scores, hire evaluation) from the results view. The
    append-only score_overrides/flag_events audit logs are preserved."""
    if not db_service.get_submission(submission_id):
        return jsonify({'error': 'Submission not found'}), 404

    if not db_service.delete_submission(submission_id):
        return jsonify({'error': 'Failed to delete submission'}), 500

    return jsonify({
        'submission_id': submission_id,
        'deleted': True,
        'message': 'Submission deleted',
    }), 200


@submissions_bp.route('/submissions/<submission_id>/flag', methods=['POST'])
def flag_submission(submission_id):
    """Flag a submission for manual review"""
    data = request.get_json() or {}
    reason = _str_field(data, 'reason')
    if not reason:
        return jsonify({'error': 'reason is required'}), 400

    if not db_service.get_submission(submission_id):
        return jsonify({'error': 'Submission not found'}), 404

    flagged_by = _str_field(data, 'flagged_by') or None
    # event_id is written to the flag_events audit log in the SAME
    # transaction as the flag update (Story 9.2 hardening) — a crash or
    # transient error between two separate writes could otherwise leave a
    # submission flagged with no corresponding audit-trail entry.
    event_id = IDGenerator.generate_uuid()
    if not db_service.flag_submission(submission_id, reason, flagged_by, event_id=event_id):
        return jsonify({'error': 'Failed to flag submission'}), 500

    return jsonify({
        'submission_id': submission_id,
        'is_flagged':    True,
        'flag_reason':   reason,
        'flag_by':       flagged_by,
        'message':       'Submission flagged for manual review',
    }), 200


@submissions_bp.route('/submissions/<submission_id>/override', methods=['POST'])
def override_submission(submission_id):
    """Apply human override to the AI hire recommendation"""
    data = request.get_json() or {}
    override_rec       = _str_field(data, 'override_recommendation')
    override_rationale = _str_field(data, 'override_rationale')

    if not override_rec or not override_rationale:
        return jsonify({'error': 'override_recommendation and override_rationale are both required'}), 400
    if override_rec not in VALID_RECOMMENDATIONS:
        return jsonify({'error': f'override_recommendation must be one of: {sorted(VALID_RECOMMENDATIONS)}'}), 400

    if not db_service.get_submission(submission_id):
        return jsonify({'error': 'Submission not found'}), 404

    hire_row = db_service.get_hire_evaluation(submission_id)
    if not hire_row:
        return jsonify({'error': 'No evaluation found for this submission — cannot override'}), 409

    # override_id is written to the score_overrides audit log in the SAME
    # transaction as the override update (Story 9.2 hardening) — a crash or
    # transient error between two separate writes could otherwise leave an
    # override applied with no corresponding audit-trail entry.
    override_id = IDGenerator.generate_uuid()
    if not db_service.override_hire_evaluation(
            submission_id, override_rec, override_rationale,
            ai_recommendation=hire_row[1], override_id=override_id):
        return jsonify({'error': 'Failed to apply override'}), 500

    return jsonify({
        'submission_id':            submission_id,
        'is_overridden':            True,
        'override_recommendation':  override_rec,
        'override_rationale':       override_rationale,
        'original_composite_score': hire_row[0],
        'original_recommendation':  hire_row[1],
        'message':                  'Human override applied. Original AI score preserved.',
    }), 200
