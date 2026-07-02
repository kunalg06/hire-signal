from flask import Blueprint, jsonify
from app.services.database_service import DatabaseService

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api')
db_service = DatabaseService()


@analytics_bp.route('/analytics/overrides', methods=['GET'])
def get_override_analytics():
    """Admin: aggregated override stats for AI calibration.
    Always returns 200 — empty state is zero counts and empty lists."""
    data = db_service.get_override_analytics()
    return jsonify(data), 200
