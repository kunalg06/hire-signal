"""Routes for AI-based challenge generation and catalog management"""

from flask import Blueprint, request, jsonify
from app.services.evaluation_service import EvaluationService
from app.services.database_service import DatabaseService
from app.utils.helpers import IDGenerator

challenges_bp = Blueprint('challenges', __name__, url_prefix='/api')
db_service = DatabaseService()

VALID_CHALLENGE_TYPES = {'bug_fix', 'feature_extension', 'refactoring', 'optimization'}
VALID_SKILL_AREAS = {'api_integration', 'rate_limiting', 'data_pipeline', 'llm_usage', 'server_monitoring', 'game_logic'}
VALID_DIFFICULTIES = {'easy', 'medium', 'hard'}
VALID_MODES = {'guarded', 'unguarded'}


def _challenge_row_to_dict(row):
    """Map a challenges table row to a dict (column order matches CREATE TABLE)"""
    return {
        'id':                   row[0],
        'title':                row[1],
        'domain':               row[2],
        'description':          row[3],
        'evaluation_rubric':    row[4],
        'starter_code':         row[5],
        'challenge_type':       row[6],
        'skill_area':           row[7],
        'difficulty':           row[8],
        'ai_assistance_mode':   row[9],
        'is_published':         bool(row[10]),
        'created_at':           row[11],
    }


# ── Generation ────────────────────────────────────────────────────────────────

@challenges_bp.route('/generate-challenge', methods=['POST'])
def generate_challenge():
    """Generate a market-aligned coding challenge and persist it to the catalog"""
    data = request.get_json() or {}

    problem_statement  = data.get('problem_statement', '').strip()
    difficulty         = data.get('difficulty', '').strip()
    challenge_type     = data.get('challenge_type', 'feature_extension').strip()
    skill_area         = data.get('skill_area', 'api_integration').strip()
    ai_assistance_mode = data.get('ai_assistance_mode', 'unguarded').strip()

    # Validate required fields
    if not problem_statement:
        return jsonify({'error': 'problem_statement is required'}), 400
    if not difficulty:
        return jsonify({'error': 'difficulty is required'}), 400

    # Validate enums
    if difficulty not in VALID_DIFFICULTIES:
        return jsonify({'error': f'difficulty must be one of: {sorted(VALID_DIFFICULTIES)}'}), 400
    if challenge_type not in VALID_CHALLENGE_TYPES:
        return jsonify({'error': f'challenge_type must be one of: {sorted(VALID_CHALLENGE_TYPES)}'}), 400
    if skill_area not in VALID_SKILL_AREAS:
        return jsonify({'error': f'skill_area must be one of: {sorted(VALID_SKILL_AREAS)}'}), 400
    if ai_assistance_mode not in VALID_MODES:
        return jsonify({'error': f'ai_assistance_mode must be one of: {sorted(VALID_MODES)}'}), 400

    try:
        challenge = EvaluationService.generate_challenge(
            problem_statement=problem_statement,
            difficulty=difficulty,
            challenge_type=challenge_type,
            skill_area=skill_area,
            ai_assistance_mode=ai_assistance_mode,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # Persist to catalog as unpublished draft
    challenge_id = IDGenerator.generate_uuid()
    try:
        db_service.create_challenge(
            challenge_id=challenge_id,
            title=challenge['title'],
            domain=skill_area,
            description=challenge['description'],
            starter_code=challenge['starter_code'],
            challenge_type=challenge_type,
            skill_area=skill_area,
            difficulty=difficulty,
            ai_assistance_mode=ai_assistance_mode,
            evaluation_rubric_json=challenge.get('evaluation_criteria'),
        )
    except Exception as e:
        # Generation succeeded — return it even if persist fails
        print(f"Warning: could not persist challenge to catalog: {e}")
        challenge_id = None

    return jsonify({
        **challenge,
        'challenge_id':       challenge_id,
        'challenge_type':     challenge_type,
        'skill_area':         skill_area,
        'difficulty':         difficulty,
        'ai_assistance_mode': ai_assistance_mode,
        'is_published':       False,
    }), 200


# ── Catalog ───────────────────────────────────────────────────────────────────

@challenges_bp.route('/challenges', methods=['GET'])
def list_challenges():
    """List published challenges with optional filters"""
    challenge_type     = request.args.get('challenge_type')
    skill_area         = request.args.get('skill_area')
    difficulty         = request.args.get('difficulty')
    ai_assistance_mode = request.args.get('ai_assistance_mode')

    # Validate any filter values that were provided
    if challenge_type and challenge_type not in VALID_CHALLENGE_TYPES:
        return jsonify({'error': f'challenge_type must be one of: {sorted(VALID_CHALLENGE_TYPES)}'}), 400
    if skill_area and skill_area not in VALID_SKILL_AREAS:
        return jsonify({'error': f'skill_area must be one of: {sorted(VALID_SKILL_AREAS)}'}), 400
    if difficulty and difficulty not in VALID_DIFFICULTIES:
        return jsonify({'error': f'difficulty must be one of: {sorted(VALID_DIFFICULTIES)}'}), 400
    if ai_assistance_mode and ai_assistance_mode not in VALID_MODES:
        return jsonify({'error': f'ai_assistance_mode must be one of: {sorted(VALID_MODES)}'}), 400

    rows = db_service.list_challenges(
        challenge_type=challenge_type,
        skill_area=skill_area,
        difficulty=difficulty,
        ai_assistance_mode=ai_assistance_mode,
    )

    return jsonify({
        'challenges': [_challenge_row_to_dict(r) for r in rows],
        'total': len(rows),
        'filters': {
            'challenge_type':     challenge_type,
            'skill_area':         skill_area,
            'difficulty':         difficulty,
            'ai_assistance_mode': ai_assistance_mode,
        },
    }), 200


@challenges_bp.route('/challenges/<challenge_id>', methods=['GET'])
def get_challenge(challenge_id):
    """Fetch a single challenge by ID (published or unpublished)"""
    row = db_service.get_challenge(challenge_id)
    if not row:
        return jsonify({'error': 'Challenge not found'}), 404
    return jsonify(_challenge_row_to_dict(row)), 200


@challenges_bp.route('/challenges/<challenge_id>/publish', methods=['POST'])
def publish_challenge(challenge_id):
    """Mark a challenge as published so it appears in the catalog"""
    row = db_service.get_challenge(challenge_id)
    if not row:
        return jsonify({'error': 'Challenge not found'}), 404

    success = db_service.publish_challenge(challenge_id)
    if not success:
        return jsonify({'error': 'Failed to publish challenge'}), 500

    return jsonify({
        'challenge_id': challenge_id,
        'is_published': True,
        'message': 'Challenge published and now visible in catalog',
    }), 200


@challenges_bp.route('/challenges/<challenge_id>', methods=['DELETE'])
def delete_challenge(challenge_id):
    """Soft-delete: hide challenge from catalog (is_published = -1)"""
    row = db_service.get_challenge(challenge_id)
    if not row:
        return jsonify({'error': 'Challenge not found'}), 404

    db_service.unpublish_challenge(challenge_id)
    return jsonify({
        'challenge_id': challenge_id,
        'is_published': False,
        'message': 'Challenge removed from catalog',
    }), 200


# ── Reference ─────────────────────────────────────────────────────────────────

@challenges_bp.route('/challenges/meta/options', methods=['GET'])
def challenge_options():
    """Return valid enum values for all challenge parameters"""
    return jsonify({
        'challenge_types':      sorted(VALID_CHALLENGE_TYPES),
        'skill_areas':          sorted(VALID_SKILL_AREAS),
        'difficulties':         sorted(VALID_DIFFICULTIES),
        'ai_assistance_modes':  sorted(VALID_MODES),
    }), 200
