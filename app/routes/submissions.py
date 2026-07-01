from flask import Blueprint, request, jsonify
import threading
import json
from app.services.database_service import DatabaseService
from app.services.docker_service import DockerService
from app.services.session_log_service import SessionLogService
from app.services.evaluation_service import EvaluationService
from app.utils.helpers import IDGenerator

submissions_bp = Blueprint('submissions', __name__, url_prefix='/api')
db_service = DatabaseService()

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

        print(
            f"Evaluation complete for {submission_id}: "
            f"score={evaluation['composite_score']:.1f} "
            f"({evaluation['hire_recommendation']})"
        )

    except Exception as e:
        print(f"Error evaluating submission {submission_id}: {e}")

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

    container_id, assignment_id, title, description, criteria, container_created_at = row

    # Create assignment dict for evaluation
    assignment = {
        "id": assignment_id,
        "title": title,
        "description": description,
        "evaluation_criteria": criteria
    }

    # Collect files from container
    files_dict = {}

    if container_id:
        print(f"Reading files from container {container_id[:12]}...")

        # Get solution.py
        solution_content = DockerService.get_file_from_container(container_id, '/workspace/solution.py')
        if solution_content and solution_content.strip() != "":
            files_dict['solution.py'] = solution_content
            print(f"  [ok] solution.py ({len(solution_content)} bytes)")

        # Get instructions.md
        instructions_content = DockerService.get_file_from_container(container_id, '/workspace/instructions.md')
        if instructions_content:
            files_dict['instructions.md'] = instructions_content
            print(f"  [ok] instructions.md ({len(instructions_content)} bytes)")

        # Try to get claude session logs
        claude_log_paths = [
            '/tmp/claude_session.log',
            '/root/.claude/logs/session.log',
            '/home/coder/.claude/logs/session.log',
            '/home/coder/.local/share/claude-code/session.log'
        ]

        for log_path in claude_log_paths:
            log_content = DockerService.get_file_from_container(container_id, log_path)
            if log_content:
                files_dict['claude_session.log'] = log_content
                print(f"  [ok] claude_session.log ({len(log_content)} bytes)")
                break

    # If no solution.py found, create default
    if 'solution.py' not in files_dict:
        files_dict['solution.py'] = "# solution.py not found"
        print("  [warn] solution.py not found in workspace")

    # Create submission record
    submission_id = IDGenerator.generate_uuid()
    files_json = json.dumps(list(files_dict.keys()))

    db_service.create_submission(submission_id, link_id, assignment_id, files_json)

    # Store individual files
    for filename, content in files_dict.items():
        file_id = IDGenerator.generate_file_id()
        file_size = len(content.encode('utf-8')) if isinstance(content, str) else len(content)
        db_service.add_submission_file(file_id, submission_id, filename, content, file_size)

    # Parse and store Claude session logs if available
    session_logs = []

    if 'claude_session.log' in files_dict:
        try:
            session_logs = SessionLogService.parse_session_log(files_dict['claude_session.log'])

            # Store parsed logs in session_logs table
            for log_entry in session_logs:
                log_id = IDGenerator.generate_log_id()
                db_service.add_session_log(
                    log_id,
                    submission_id,
                    log_entry.get('timestamp'),
                    log_entry.get('interaction_type', 'claude_cli'),
                    log_entry.get('prompt', ''),
                    log_entry.get('response_summary', ''),
                    log_entry.get('file_changes_count', 0),
                    log_entry.get('raw_json', '')
                )

            print(f"  [ok] Stored {len(session_logs)} session log entries")
        except Exception as e:
            print(f"Warning: Failed to parse/store session logs: {e}")

    # Extract full workspace snapshot NOW (before container cleanup)
    file_snapshot = {}
    if container_id:
        file_snapshot = EvaluationService.extract_container_files(container_id)
        print(f"  [ok] workspace snapshot: {len(file_snapshot)} files")

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
                SELECT s.submission_id, s.link_id, s.assignment_id, s.code, s.submitted_at, s.evaluation_result, s.score, s.feedback, a.title
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
    claude_logs = ""
    for filename, content in files:
        if filename == 'instructions.md':
            instructions_md = content
        elif filename == 'claude_session.log':
            claude_logs = content

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
        # Supporting content
        "instructions_md":  instructions_md,
        "claude_logs":      claude_logs or "No Claude session logs available",
        # 8-dimension scoring
        "dimensions":       dimensions,
        "hire_evaluation":  hire_data,
    })

@submissions_bp.route('/session-logs/<submission_id>', methods=['GET'])
def get_session_logs(submission_id):
    """Get Claude session logs for a submission"""
    rows = db_service.get_session_logs(submission_id)

    logs = [
        {
            'timestamp': row[0],
            'interaction_type': row[1],
            'prompt': row[2],
            'response_summary': row[3],
            'file_changes_count': row[4]
        }
        for row in rows
    ]

    return jsonify({
        "submission_id": submission_id,
        "logs": logs,
        "total_interactions": len(logs)
    })
