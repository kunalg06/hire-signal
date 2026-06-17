from flask import Blueprint, request, jsonify
from app.services.database_service import DatabaseService
from app.utils.helpers import IDGenerator, ValidationHelper

assignments_bp = Blueprint('assignments', __name__, url_prefix='/api')
db_service = DatabaseService()

@assignments_bp.route('/assignments', methods=['POST'])
def create_assignment():
    """Create a new assignment"""
    data = request.get_json()

    # Validate required fields
    is_valid, error_msg = ValidationHelper.validate_required_fields(
        data, ['title', 'evaluation_criteria']
    )
    if not is_valid:
        return jsonify({"detail": error_msg}), 400

    assignment_id = IDGenerator.generate_uuid()

    db_service.create_assignment(
        assignment_id,
        data.get('title'),
        data.get('description', ''),
        data.get('starter_code', ''),
        data.get('evaluation_criteria')
    )

    return jsonify({
        "id": assignment_id,
        "title": data.get('title'),
        "description": data.get('description', ''),
        "starter_code": data.get('starter_code', ''),
        "evaluation_criteria": data.get('evaluation_criteria')
    }), 201

@assignments_bp.route('/assignments/<assignment_id>', methods=['GET'])
def get_assignment(assignment_id):
    """Get assignment details"""
    row = db_service.get_assignment(assignment_id)

    if not row:
        return jsonify({"detail": "Assignment not found"}), 404

    return jsonify({
        "id": row[0],
        "title": row[1],
        "description": row[2],
        "starter_code": row[3],
        "evaluation_criteria": row[4]
    })
