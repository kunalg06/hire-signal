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

def evaluate_submission_files(submission_id, assignment, session_logs=None, container_created_at=None):
    """Evaluate submitted files with session log scoring"""
    try:
        # Get solution.py content
        files = db_service.get_submission_files(submission_id)
        code = None

        for filename, content in files:
            if filename == 'solution.py':
                code = content
                break

        if not code:
            code = "# No solution.py found"

        # If session_logs not provided, retrieve from database
        if session_logs is None:
            log_rows = db_service.get_session_logs(submission_id)
            session_logs = [
                {
                    'timestamp': row[0],
                    'interaction_type': row[1],
                    'prompt': row[2],
                    'response_summary': row[3],
                    'file_changes_count': row[4]
                }
                for row in log_rows
            ] if log_rows else []

        # If container_created_at not provided, get from session_links
        if container_created_at is None:
            container_created_at = db_service.get_link_created_time(
                [row for row in db_service.get_submission_files(submission_id)][0][1] if db_service.get_submission_files(submission_id) else None
            )

        # Evaluate with Claude
        evaluation = EvaluationService.evaluate_code(code, assignment, session_logs, container_created_at)

        # Update submission with evaluation results
        db_service.update_submission_evaluation(
            submission_id,
            evaluation["score"],
            evaluation["feedback"],
            evaluation["evaluation_details"]
        )

        print(f"Evaluation complete for submission {submission_id}: score={evaluation['score']:.1f}")

    except Exception as e:
        print(f"Error evaluating submission {submission_id}: {e}")

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
            print(f"  ✓ solution.py ({len(solution_content)} bytes)")

        # Get instructions.md
        instructions_content = DockerService.get_file_from_container(container_id, '/workspace/instructions.md')
        if instructions_content:
            files_dict['instructions.md'] = instructions_content
            print(f"  ✓ instructions.md ({len(instructions_content)} bytes)")

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
                print(f"  ✓ claude_session.log ({len(log_content)} bytes)")
                break

    # If no solution.py found, create default
    if 'solution.py' not in files_dict:
        files_dict['solution.py'] = "# solution.py not found"
        print("  ⚠ solution.py not found in workspace")

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

            print(f"  ✓ Stored {len(session_logs)} session log entries")
        except Exception as e:
            print(f"Warning: Failed to parse/store session logs: {e}")

    # Schedule evaluation in background
    thread = threading.Thread(
        target=evaluate_submission_files,
        args=(submission_id, assignment, session_logs, container_created_at)
    )
    thread.daemon = True
    thread.start()

    # Schedule container cleanup
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

@submissions_bp.route('/submission/<submission_id>', methods=['GET'])
def get_submission(submission_id):
    """Retrieve submission and evaluation results"""
    row = db_service.get_submission(submission_id)

    if not row:
        return jsonify({"detail": "Submission not found"}), 404

    files = db_service.get_submission_files(submission_id)

    instructions_md = ""
    claude_logs = ""

    for filename, content in files:
        if filename == 'instructions.md':
            instructions_md = content
        elif filename == 'claude_session.log':
            claude_logs = content

    return jsonify({
        "submission_id": row[0],
        "link_id": row[1],
        "assignment_id": row[2],
        "code": row[3],
        "submitted_at": row[4],
        "evaluation_result": row[5],
        "score": row[6],
        "feedback": row[7],
        "assignment_title": row[8],
        "instructions_md": instructions_md,
        "claude_logs": claude_logs if claude_logs else "No Claude session logs available"
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
