from flask import Blueprint, jsonify
from app.services.database_service import DatabaseService
from app.services.docker_service import DockerService
from app.utils.helpers import IDGenerator, DateTimeHelper
from app.config import Config

links_bp = Blueprint('links', __name__, url_prefix='/api')
db_service = DatabaseService()

@links_bp.route('/generate-link/<assignment_id>', methods=['POST'])
def generate_link(assignment_id):
    """Generate student access link"""
    # Get assignment
    assignment_row = db_service.get_assignment(assignment_id)

    if not assignment_row:
        return jsonify({"detail": "Assignment not found"}), 404

    # Create unique link
    link_id = IDGenerator.generate_link_id()

    # Create Docker container
    container_id = None
    port = None
    max_retries = 100  # Limit retries to 100 ports instead of 1000
    retry_count = 0

    for port_attempt in range(Config.DOCKER_PORT_RANGE_START, Config.DOCKER_PORT_RANGE_START + max_retries):
        if retry_count >= max_retries:
            print(f"Max retries ({max_retries}) reached. Could not find available port.")
            break

        try:
            container_id, port = DockerService.create_container(assignment_id, port_attempt)

            if container_id:
                print(f"Container started successfully: {container_id[:12]} on port {port}")
                break
            retry_count += 1

        except Exception as e:
            error_msg = str(e)
            if "already allocated" in error_msg or "port is already allocated" in error_msg:
                retry_count += 1
                continue
            else:
                print(f"Container creation error: {e}")
                retry_count += 1
                continue

    # Store link
    expires_at = DateTimeHelper.get_future_timestamp(hours=24)
    db_service.create_session_link(link_id, assignment_id, container_id, port, expires_at)

    return jsonify({
        "link_id": link_id,
        "assignment_id": assignment_id,
        "access_url": f"http://localhost:{port}" if port else "N/A",
        "vscode_port": port,
        "expires_at": expires_at
    }), 201
