from flask import Blueprint, request, jsonify
from app.services.database_service import DatabaseService
from app.utils.helpers import IDGenerator, ValidationHelper

assignments_bp = Blueprint('assignments', __name__, url_prefix='/api')
db_service = DatabaseService()

DIM_KEYS = [
    'problem_decomposition', 'first_principles_thinking', 'creative_problem_solving',
    'iteration_quality', 'debugging_with_ai', 'architecture_decisions',
    'communication_clarity', 'token_efficiency',
]

@assignments_bp.route('/assignments', methods=['GET', 'POST'])
def assignments():
    """List all assignments (GET) or create new (POST)"""
    if request.method == 'GET':
        rows = db_service.list_assignments()
        assignments_list = [
            {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "starter_code": row[3],
                "evaluation_criteria": row[4]
            }
            for row in rows
        ]
        return jsonify(assignments_list), 200

    # POST - Create new assignment
    data = request.get_json()

    # Validate required fields
    is_valid, error_msg = ValidationHelper.validate_required_fields(
        data, ['title', 'evaluation_criteria']
    )
    if not is_valid:
        return jsonify({"detail": error_msg}), 400

    assignment_id = IDGenerator.generate_uuid()
    challenge_id = data.get('challenge_id') or None

    db_service.create_assignment(
        assignment_id,
        data.get('title'),
        data.get('description', ''),
        data.get('starter_code', ''),
        data.get('evaluation_criteria'),
        challenge_id=challenge_id,
    )

    return jsonify({
        "id": assignment_id,
        "title": data.get('title'),
        "description": data.get('description', ''),
        "starter_code": data.get('starter_code', ''),
        "evaluation_criteria": data.get('evaluation_criteria'),
        "challenge_id": challenge_id,
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


@assignments_bp.route('/assignments/<assignment_id>', methods=['DELETE'])
def delete_assignment(assignment_id):
    """Soft-delete: hide assignment from lists/pickers. Historical
    submissions/results tied to this assignment_id are left untouched and
    remain reachable by direct id."""
    if not db_service.get_assignment(assignment_id):
        return jsonify({"detail": "Assignment not found"}), 404

    db_service.soft_delete_assignment(assignment_id)
    return jsonify({
        "id": assignment_id,
        "deleted": True,
        "message": "Assignment removed from lists",
    }), 200


@assignments_bp.route('/assignments/<assignment_id>/candidates', methods=['GET'])
def get_candidates(assignment_id):
    """Return all candidates for an assignment ranked by composite score"""
    if not db_service.get_assignment(assignment_id):
        return jsonify({"detail": "Assignment not found"}), 404

    rows = db_service.get_candidates_for_assignment(assignment_id)
    submission_ids = [row[0] for row in rows]
    dims_by_submission = db_service.get_dimension_scores_for_submissions(submission_ids)

    candidates = []
    for rank, row in enumerate(rows, 1):
        submission_id = row[0]
        dim_rows = dims_by_submission.get(submission_id, [])
        dimensions = {r[0]: {"score": r[1], "rationale": r[2]} for r in dim_rows}
        candidates.append({
            "rank":                     rank,
            "submission_id":            row[0],
            "link_id":                  row[1],
            "submitted_at":             row[2],
            "score":                    row[3],
            "composite_score":          row[4],
            "hire_recommendation":      row[5],
            "recommendation_rationale": row[6],
            "evaluated_at":             row[7],
            "dimensions":               dimensions,
        })

    # Cohort averages per dimension (for quartile context in UI)
    evaluated = [c for c in candidates if c["dimensions"]]
    dim_averages = {}
    if evaluated:
        for dim in DIM_KEYS:
            scores = [c["dimensions"].get(dim, {}).get("score", 0) for c in evaluated]
            dim_averages[dim] = round(sum(scores) / len(scores), 1)

    return jsonify({
        "assignment_id":    assignment_id,
        "candidates":       candidates,
        "total":            len(candidates),
        "dimension_averages": dim_averages,
    }), 200
