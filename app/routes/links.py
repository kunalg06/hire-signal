import logging

from flask import Blueprint, jsonify
from app.services.database_service import DatabaseService
from app.services.docker_service import DockerService
from app.utils.helpers import IDGenerator, DateTimeHelper
from app.config import Config

links_bp = Blueprint('links', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)
db_service = DatabaseService()

@links_bp.route('/generate-link/<assignment_id>', methods=['POST'])
def generate_link(assignment_id):
    """Generate student access link"""
    # Get assignment
    assignment_row = db_service.get_assignment(assignment_id)

    if not assignment_row:
        return jsonify({"detail": "Assignment not found"}), 404

    # Unpack assignment fields (id, title, description, starter_code, evaluation_criteria, ...)
    _, title, description, starter_code, evaluation_criteria = assignment_row[:5]

    # challenge_id is appended at index 6 (via ALTER TABLE migration), not adjacent
    # to evaluation_criteria — index 5 is created_at. See Story 6.5 Dev Notes.
    challenge_id = assignment_row[6] if len(assignment_row) > 6 else None

    ai_assistance_mode = Config.DEFAULT_ASSISTANCE_MODE
    if challenge_id:
        challenge_row = db_service.get_challenge(challenge_id)
        if challenge_row:
            mode = challenge_row[9]
            if mode in Config.VALID_ASSISTANCE_MODES:
                ai_assistance_mode = mode
            else:
                logger.warning(
                    "Challenge %s has unrecognized ai_assistance_mode %r - "
                    "falling back to %s", challenge_id, mode,
                    Config.DEFAULT_ASSISTANCE_MODE)

    # Create unique link
    link_id = IDGenerator.generate_link_id()

    # Create Docker container
    container_id = None
    port = None
    max_retries = 100
    retry_count = 0
    # Default when no container is ever created — nothing was injected, and
    # guarded_mode_enforced stays True only because there's nothing to
    # contradict (no container means no assessment can start at all; this
    # is not the "silently ran unguarded" case Story 9.3 is about).
    guarded_mode_enforced = True

    for port_attempt in range(Config.DOCKER_PORT_RANGE_START, Config.DOCKER_PORT_RANGE_START + max_retries):
        if retry_count >= max_retries:
            logger.warning("Max retries (%s) reached. Could not find available port.", max_retries)
            break

        try:
            container_id, port, guarded_mode_enforced = DockerService.create_container(
                assignment_id, port_attempt, ai_assistance_mode=ai_assistance_mode)

            if container_id:
                logger.info("Container started successfully: %s on port %s", container_id[:12], port)
                # Inject starter code + instructions into /workspace
                DockerService.inject_workspace_files(
                    container_id=container_id,
                    title=title,
                    description=description,
                    criteria=evaluation_criteria or '',
                    starter_code=starter_code or '',
                )
                break
            retry_count += 1

        except Exception as e:
            error_msg = str(e)
            if "already allocated" in error_msg or "port is already allocated" in error_msg:
                retry_count += 1
                continue
            else:
                logger.error("Container creation error: %s", e)
                retry_count += 1
                continue

    # Store link
    expires_at = DateTimeHelper.get_future_timestamp(hours=24)
    db_service.create_session_link(
        link_id, assignment_id, container_id, port, expires_at,
        ai_assistance_mode=ai_assistance_mode,
        guarded_mode_enforced=guarded_mode_enforced,
    )

    return jsonify({
        "link_id": link_id,
        "assignment_id": assignment_id,
        "access_url": f"http://localhost:{port}" if port else "N/A",
        "vscode_port": port,
        "expires_at": expires_at
    }), 201
