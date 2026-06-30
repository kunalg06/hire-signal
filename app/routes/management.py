"""Management routes for system health and Docker operations"""

from flask import Blueprint, request, jsonify
from app.services.management_service import ManagementService

management_bp = Blueprint('management', __name__, url_prefix='/api/system')


@management_bp.route('/status', methods=['GET'])
def get_system_status():
    """Get current system status including Docker health and running containers"""
    status = ManagementService.get_system_status()
    return jsonify(status), 200


@management_bp.route('/health', methods=['GET'])
def health_check():
    """Comprehensive health check of all system components"""
    health = ManagementService.health_check()
    return jsonify(health), 200


@management_bp.route('/cleanup-old', methods=['POST'])
def cleanup_old_containers():
    """Clean up containers older than specified hours"""
    hours_old = request.args.get('hours', 24, type=int)
    result = ManagementService.cleanup_old_containers(hours_old=hours_old)
    return jsonify(result), 200


@management_bp.route('/cleanup-all', methods=['POST'])
def cleanup_all_containers():
    """Force cleanup all assignment containers"""
    result = ManagementService.cleanup_all_containers()
    return jsonify(result), 200


@management_bp.route('/containers/<container_id>/info', methods=['GET'])
def get_container_info(container_id):
    """Get detailed info about a container"""
    info = ManagementService.get_container_info(container_id)
    if 'error' in info:
        return jsonify(info), 404
    return jsonify(info), 200


@management_bp.route('/containers/<container_id>/logs', methods=['GET'])
def get_container_logs(container_id):
    """Get container logs"""
    lines = request.args.get('lines', 100, type=int)
    logs = ManagementService.get_logs(container_id, lines=lines)
    return {'logs': logs}, 200


@management_bp.route('/containers/<container_id>/restart', methods=['POST'])
def restart_container(container_id):
    """Restart a specific container"""
    result = ManagementService.restart_container(container_id)
    if not result.get('success'):
        return jsonify(result), 400
    return jsonify(result), 200


@management_bp.route('/containers/<container_id>/stop', methods=['POST'])
def stop_container(container_id):
    """Stop a specific container"""
    result = ManagementService.stop_container(container_id)
    if not result.get('success'):
        return jsonify(result), 400
    return jsonify(result), 200
