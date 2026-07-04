"""Routes for AI-based challenge generation and catalog management"""

import logging
import math
from flask import Blueprint, request, jsonify
from app.services.evaluation_service import EvaluationService
from app.services.database_service import DatabaseService
from app.utils.helpers import IDGenerator
from app.config import Config

challenges_bp = Blueprint('challenges', __name__, url_prefix='/api')
db_service = DatabaseService()
logger = logging.getLogger(__name__)

VALID_CHALLENGE_TYPES = {'bug_fix', 'feature_extension', 'refactoring', 'optimization'}
VALID_SKILL_AREAS = {'api_integration', 'rate_limiting', 'data_pipeline', 'llm_usage', 'server_monitoring', 'game_logic'}
VALID_DIFFICULTIES = {'easy', 'medium', 'hard'}
# Shared with app/routes/links.py and app/services/docker_service.py — see
# Config.VALID_ASSISTANCE_MODES's own comment on why this must not be a
# second independent literal.
VALID_MODES = Config.VALID_ASSISTANCE_MODES

DIM_KEYS = [
    'problem_decomposition', 'first_principles_thinking', 'creative_problem_solving',
    'iteration_quality', 'debugging_with_ai', 'architecture_decisions',
    'communication_clarity', 'token_efficiency',
]
VALID_SORT_FIELDS = {'composite_score'} | set(DIM_KEYS)


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

    def _str_field(key, default=''):
        # Coerce non-string values (e.g. an explicit `null`) to the default
        # instead of crashing .strip() with an AttributeError.
        value = data.get(key)
        return (value if isinstance(value, str) else default).strip()

    problem_statement  = _str_field('problem_statement')
    difficulty         = _str_field('difficulty')
    challenge_type     = _str_field('challenge_type', 'feature_extension')
    skill_area         = _str_field('skill_area', 'api_integration')
    ai_assistance_mode = _str_field('ai_assistance_mode', 'unguarded')

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
    persisted = True
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
        logger.warning("Could not persist challenge to catalog: %s", e)
        challenge_id = None
        persisted = False

    return jsonify({
        **challenge,
        'challenge_id':       challenge_id,
        'persisted':          persisted,
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


# ── Candidate comparison ──────────────────────────────────────────────────────

@challenges_bp.route('/challenges/<challenge_id>/candidates', methods=['GET'])
def get_challenge_candidates(challenge_id):
    """Return all candidates for a challenge, ranked and filterable by sort_by/order"""
    if not db_service.get_challenge(challenge_id):
        return jsonify({'error': 'Challenge not found'}), 404

    sort_by = request.args.get('sort_by', 'composite_score')
    order   = request.args.get('order', 'desc')

    if sort_by not in VALID_SORT_FIELDS:
        return jsonify({'error': f'sort_by must be one of: {sorted(VALID_SORT_FIELDS)}'}), 400
    if order not in ('asc', 'desc'):
        return jsonify({'error': 'order must be asc or desc'}), 400

    rows = db_service.get_candidates_for_challenge(challenge_id)
    submission_ids = [row[0] for row in rows]
    dims_by_submission = db_service.get_dimension_scores_for_submissions(submission_ids)
    candidates = []
    for row in rows:
        submission_id = row[0]
        dim_rows = dims_by_submission.get(submission_id, [])
        dimensions = {r[0]: {'score': r[1], 'rationale': r[2]} for r in dim_rows}
        candidates.append({
            'submission_id':            row[0],
            'link_id':                  row[1],
            'submitted_at':             row[2],
            'score':                    row[3],
            'composite_score':          row[4],
            'hire_recommendation':      row[5],
            'recommendation_rationale': row[6],
            'evaluated_at':             row[7],
            'is_evaluated':             row[7] is not None,
            'is_flagged':               bool(row[8]),
            'dimensions':               dimensions,
        })

    # Sort by requested field (Python-side — dimension scores are in a separate table)
    # Un-evaluated candidates (None values) always sort to the end regardless of direction.
    reverse = (order == 'desc')
    def sort_key(c):
        if sort_by == 'composite_score':
            val = c.get('composite_score')
        else:
            val = c.get('dimensions', {}).get(sort_by, {}).get('score')
        if val is None:
            return -math.inf if reverse else math.inf
        return float(val)
    candidates.sort(key=sort_key, reverse=reverse)

    # Assign rank after sort
    for i, c in enumerate(candidates, 1):
        c['rank'] = i

    # Dimension averages across evaluated candidates only.
    # Use is_evaluated (not dict truthiness) so partially-evaluated candidates aren't excluded.
    # Skip None/missing per-dimension scores rather than defaulting to 0.
    evaluated = [c for c in candidates if c['is_evaluated']]
    dim_averages = {}
    if evaluated:
        for dim in DIM_KEYS:
            scores = [
                c['dimensions'][dim]['score']
                for c in evaluated
                if dim in c['dimensions'] and c['dimensions'][dim].get('score') is not None
            ]
            if scores:
                dim_averages[dim] = round(sum(scores) / len(scores), 1)

    return jsonify({
        'challenge_id':       challenge_id,
        'candidates':         candidates,
        'total':              len(candidates),
        'dimension_averages': dim_averages,
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
