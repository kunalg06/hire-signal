import sqlite3
import json
from datetime import datetime
from app.models.database import Database
from app.config import Config

class DatabaseService:
    """Service for database operations"""

    def __init__(self, db_path=None):
        self.db = Database(db_path)

    def create_assignment(self, assignment_id, title, description, starter_code, evaluation_criteria, challenge_id=None):
        """Create a new assignment, optionally linked to a catalog challenge"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO assignments (id, title, description, starter_code, evaluation_criteria, challenge_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (assignment_id, title, description, starter_code, evaluation_criteria, challenge_id))
            conn.commit()

    def get_assignment(self, assignment_id):
        """Get assignment details"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM assignments WHERE id = ?', (assignment_id,))
            return cursor.fetchone()

    def list_assignments(self):
        """List all assignments"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM assignments ORDER BY created_at DESC')
            return cursor.fetchall()

    def create_session_link(self, link_id, assignment_id, container_id, port, expires_at):
        """Create a new session link"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO session_links (link_id, assignment_id, container_id, port, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (link_id, assignment_id, container_id, port, expires_at))
            conn.commit()

    def get_session_link(self, link_id):
        """Get session link details"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT sl.assignment_id, sl.port, a.title, a.description, a.evaluation_criteria, a.starter_code, sl.expires_at
                FROM session_links sl
                JOIN assignments a ON sl.assignment_id = a.id
                WHERE sl.link_id = ?
            ''', (link_id,))
            return cursor.fetchone()

    def create_submission(self, submission_id, link_id, assignment_id, files_json):
        """Create a new submission"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO submissions (submission_id, link_id, assignment_id, files_json)
                VALUES (?, ?, ?, ?)
            ''', (submission_id, link_id, assignment_id, files_json))
            conn.commit()

    def add_submission_file(self, file_id, submission_id, filename, file_content, file_size):
        """Add file to submission"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO submission_files (file_id, submission_id, filename, file_content, file_size)
                VALUES (?, ?, ?, ?, ?)
            ''', (file_id, submission_id, filename, file_content, file_size))
            conn.commit()

    def add_session_log(self, log_id, submission_id, timestamp, interaction_type, prompt, response_summary, file_changes_count, raw_json):
        """Add session log entry"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO session_logs (log_id, submission_id, timestamp, interaction_type, prompt, response_summary, file_changes_count, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (log_id, submission_id, timestamp, interaction_type, prompt, response_summary, file_changes_count, raw_json))
            conn.commit()

    def update_submission_evaluation(self, submission_id, score, feedback, evaluation_result):
        """Update submission with evaluation results"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE submissions
                SET score = ?, feedback = ?, evaluation_result = ?, evaluated_at = ?
                WHERE submission_id = ?
            ''', (score, feedback, json.dumps(evaluation_result), datetime.now().isoformat(), submission_id))
            conn.commit()

    def get_submission(self, submission_id):
        """Get submission and evaluation results including flag status"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.submission_id, s.link_id, s.assignment_id, s.code, s.submitted_at,
                       s.evaluation_result, s.score, s.feedback, a.title, a.evaluation_criteria,
                       s.is_flagged, s.flag_reason, s.flag_by, s.flagged_at
                FROM submissions s
                JOIN assignments a ON s.assignment_id = a.id
                WHERE s.submission_id = ?
            ''', (submission_id,))
            return cursor.fetchone()

    def flag_submission(self, submission_id, reason, flagged_by=None, event_id=None):
        """Flag a submission for manual review. When event_id is provided,
        also appends one row to the append-only flag_events audit log in
        the SAME transaction as the flag update — so a crash or transient
        error between the two writes can never leave a submission flagged
        with no corresponding audit-trail entry (Story 9.2 hardening)."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE submissions
                SET is_flagged = 1, flag_reason = ?, flag_by = ?, flagged_at = ?
                WHERE submission_id = ?
            ''', (reason, flagged_by, datetime.now().isoformat(), submission_id))
            updated = cursor.rowcount > 0
            if updated and event_id:
                cursor.execute('''
                    INSERT INTO flag_events (id, submission_id, reason, flagged_by)
                    VALUES (?, ?, ?, ?)
                ''', (event_id, submission_id, reason, flagged_by))
            conn.commit()
            return updated

    def override_hire_evaluation(self, submission_id, override_recommendation, override_rationale,
                                 ai_recommendation=None, override_id=None):
        """Apply human override — original AI composite_score and
        recommendation are never changed. When override_id is provided
        (with ai_recommendation), also appends one row to the append-only
        score_overrides audit log in the SAME transaction as the override
        update — so a crash or transient error between the two writes can
        never leave an override applied with no corresponding audit-trail
        entry (Story 9.2 hardening)."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE hire_evaluations
                SET is_overridden = 1,
                    override_recommendation = ?,
                    override_rationale = ?
                WHERE submission_id = ?
            ''', (override_recommendation, override_rationale, submission_id))
            updated = cursor.rowcount > 0
            if updated and override_id:
                cursor.execute('''
                    INSERT INTO score_overrides
                        (id, submission_id, ai_recommendation, human_recommendation, override_rationale)
                    VALUES (?, ?, ?, ?, ?)
                ''', (override_id, submission_id, ai_recommendation,
                      override_recommendation, override_rationale))
            conn.commit()
            return updated

    def list_submissions(self, recommendation_filter=None, assignment_id_filter=None):
        """List all submissions with hire evaluation, newest first. Optional filters."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            query = '''
                SELECT
                    s.submission_id,
                    s.assignment_id,
                    a.title            AS assignment_title,
                    s.submitted_at,
                    s.score,
                    s.evaluated_at,
                    he.composite_score,
                    he.recommendation
                FROM submissions s
                JOIN assignments a ON s.assignment_id = a.id
                LEFT JOIN hire_evaluations he ON he.submission_id = s.submission_id
                WHERE 1=1
            '''
            params = []
            if recommendation_filter:
                query += ' AND he.recommendation = ?'
                params.append(recommendation_filter)
            if assignment_id_filter:
                query += ' AND s.assignment_id = ?'
                params.append(assignment_id_filter)
            query += ' ORDER BY s.submitted_at DESC'
            cursor.execute(query, params)
            return cursor.fetchall()

    def get_submission_files(self, submission_id):
        """Get files from submission"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT filename, file_content FROM submission_files
                WHERE submission_id = ?
                ORDER BY created_at DESC
            ''', (submission_id,))
            return cursor.fetchall()

    def get_session_logs(self, submission_id):
        """Get Gemini session logs for submission"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, interaction_type, prompt, response_summary, file_changes_count
                FROM session_logs
                WHERE submission_id = ?
                ORDER BY timestamp ASC
            ''', (submission_id,))
            return cursor.fetchall()

    def get_link_container_info(self, link_id):
        """Get container and assignment info for a link"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT sl.container_id, sl.assignment_id, a.title, a.description, a.evaluation_criteria, sl.created_at
                FROM session_links sl
                JOIN assignments a ON sl.assignment_id = a.id
                WHERE sl.link_id = ?
            ''', (link_id,))
            return cursor.fetchone()

    def get_link_created_time(self, link_id):
        """Get link creation time"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT created_at FROM session_links WHERE link_id = ?', (link_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    # ── 8-Dimension scoring methods ───────────────────────────────────────

    def create_dimension_score(self, score_id, submission_id, dimension,
                               score, rationale, scoring_method='llm_judge'):
        """Persist one dimension score row"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO dimension_scores
                    (id, submission_id, dimension, score, rationale, scoring_method)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (score_id, submission_id, dimension, score, rationale, scoring_method))
            conn.commit()

    def get_dimension_scores(self, submission_id):
        """Return all dimension scores for a submission as a list of rows"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT dimension, score, rationale, scoring_method, scored_at
                FROM dimension_scores
                WHERE submission_id = ?
                ORDER BY dimension ASC
            ''', (submission_id,))
            return cursor.fetchall()

    def get_dimension_scores_for_submissions(self, submission_ids):
        """Batch-fetch dimension scores for multiple submissions in one query,
        grouped by submission_id — avoids the N+1 pattern in candidate ranking
        (see deferred-work.md / Story 9.1). Each value has the same row shape
        get_dimension_scores() returns (dimension, score, rationale,
        scoring_method, scored_at), just grouped instead of pre-filtered.
        """
        if not submission_ids:
            return {}
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(submission_ids))
            cursor.execute(f'''
                SELECT submission_id, dimension, score, rationale, scoring_method, scored_at
                FROM dimension_scores
                WHERE submission_id IN ({placeholders})
                ORDER BY submission_id, dimension ASC
            ''', submission_ids)
            rows = cursor.fetchall()
        grouped = {}
        for row in rows:
            grouped.setdefault(row[0], []).append(row[1:])
        return grouped

    def create_hire_evaluation(self, eval_id, submission_id, composite_score,
                               recommendation, dimension_weights_json, narrative):
        """Persist hire verdict with dimension weights snapshot"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO hire_evaluations
                    (id, submission_id, composite_score, recommendation,
                     dimension_weights_json, narrative)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (eval_id, submission_id, composite_score, recommendation,
                  dimension_weights_json, narrative))
            conn.commit()

    def get_hire_evaluation(self, submission_id):
        """Fetch the hire evaluation for a submission"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT composite_score, recommendation, dimension_weights_json,
                       narrative, is_overridden, override_recommendation,
                       override_rationale, evaluated_at
                FROM hire_evaluations
                WHERE submission_id = ?
                ORDER BY evaluated_at DESC
                LIMIT 1
            ''', (submission_id,))
            return cursor.fetchone()

    def get_candidates_for_assignment(self, assignment_id):
        """Return all submissions for an assignment ranked by composite score"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    s.submission_id,
                    s.link_id,
                    s.submitted_at,
                    s.score,
                    he.composite_score,
                    he.recommendation,
                    he.narrative,
                    he.evaluated_at
                FROM submissions s
                LEFT JOIN hire_evaluations he ON s.submission_id = he.submission_id
                WHERE s.assignment_id = ?
                ORDER BY COALESCE(he.composite_score, s.score, 0) DESC
            ''', (assignment_id,))
            return cursor.fetchall()

    def get_candidates_for_challenge(self, challenge_id):
        """Return all submissions across all assignments linked to a challenge, ranked by composite score"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    s.submission_id,
                    s.link_id,
                    s.submitted_at,
                    s.score,
                    he.composite_score,
                    he.recommendation,
                    he.narrative,
                    he.evaluated_at,
                    s.is_flagged
                FROM submissions s
                JOIN assignments a ON s.assignment_id = a.id
                LEFT JOIN hire_evaluations he ON s.submission_id = he.submission_id
                WHERE a.challenge_id = ?
                ORDER BY COALESCE(he.composite_score, s.score, 0) DESC
            ''', (challenge_id,))
            return cursor.fetchall()

    # ── Challenge catalog methods ──────────────────────────────────────────

    def create_challenge(self, challenge_id, title, domain, description,
                         starter_code, challenge_type, skill_area, difficulty,
                         ai_assistance_mode, evaluation_rubric_json=None):
        """Persist a generated challenge to the catalog (unpublished by default)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO challenges
                    (id, title, domain, description, evaluation_rubric_json,
                     starter_code, challenge_type, skill_area, difficulty, ai_assistance_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (challenge_id, title, domain, description, evaluation_rubric_json,
                  starter_code, challenge_type, skill_area, difficulty, ai_assistance_mode))
            conn.commit()

    def get_challenge(self, challenge_id):
        """Fetch a single challenge by ID regardless of publish status"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM challenges WHERE id = ?', (challenge_id,))
            return cursor.fetchone()

    def list_challenges(self, challenge_type=None, skill_area=None,
                        difficulty=None, ai_assistance_mode=None):
        """List published challenges with optional filters"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM challenges WHERE is_published = 1'
            params = []
            if challenge_type:
                query += ' AND challenge_type = ?'
                params.append(challenge_type)
            if skill_area:
                query += ' AND skill_area = ?'
                params.append(skill_area)
            if difficulty:
                query += ' AND difficulty = ?'
                params.append(difficulty)
            if ai_assistance_mode:
                query += ' AND ai_assistance_mode = ?'
                params.append(ai_assistance_mode)
            query += ' ORDER BY created_at DESC'
            cursor.execute(query, params)
            return cursor.fetchall()

    def publish_challenge(self, challenge_id):
        """Mark a challenge as published (visible in catalog)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE challenges SET is_published = 1 WHERE id = ?',
                (challenge_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def unpublish_challenge(self, challenge_id):
        """Soft-delete: hide challenge from catalog"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE challenges SET is_published = -1 WHERE id = ?',
                (challenge_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    # ── Comparison session methods ─────────────────────────────────────────

    def create_comparison_session(self, session_id, challenge_id, name, submission_ids):
        """Create a named comparison session grouping submissions for a challenge"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO comparison_sessions (id, challenge_id, name, submission_ids_json)
                VALUES (?, ?, ?, ?)
            ''', (session_id, challenge_id, name, json.dumps(submission_ids)))
            conn.commit()

    def get_comparison_session(self, session_id):
        """Fetch a single comparison session by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM comparison_sessions WHERE id = ?', (session_id,))
            return cursor.fetchone()

    def list_comparison_sessions(self, challenge_id=None):
        """List comparison sessions, optionally filtered by challenge, newest first"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if challenge_id:
                cursor.execute(
                    'SELECT * FROM comparison_sessions WHERE challenge_id = ? ORDER BY created_at DESC',
                    (challenge_id,)
                )
            else:
                cursor.execute('SELECT * FROM comparison_sessions ORDER BY created_at DESC')
            return cursor.fetchall()

    # ── Override calibration audit methods ────────────────────────────────────
    # log_score_override()/log_flag_event() no longer exist as separate calls —
    # their INSERTs were folded into override_hire_evaluation()/flag_submission()
    # above so the audit-log write is atomic with the state-mutating update
    # (Story 9.2 hardening: a crash between two separate commits could
    # otherwise leave a flag/override applied with no audit-trail row).

    def get_override_analytics(self):
        """Return aggregated override stats for the analytics endpoint"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM score_overrides')
            total = cursor.fetchone()[0]

            cursor.execute('''
                SELECT ai_recommendation, human_recommendation, COUNT(*) AS cnt
                FROM score_overrides
                GROUP BY ai_recommendation, human_recommendation
                ORDER BY cnt DESC
            ''')
            direction_rows = cursor.fetchall()

            cursor.execute('''
                SELECT id, submission_id, ai_recommendation, human_recommendation,
                       override_rationale, overridden_at
                FROM score_overrides
                ORDER BY overridden_at DESC
                LIMIT 20
            ''')
            recent_rows = cursor.fetchall()

        overrides_by_direction = {
            f"{r[0]} -> {r[1]}": r[2]
            for r in direction_rows
        }

        recent_overrides = [
            {
                "override_id":           r[0],
                "submission_id":         r[1],
                "ai_recommendation":     r[2],
                "human_recommendation":  r[3],
                "override_rationale":    r[4],
                "overridden_at":         r[5],
            }
            for r in recent_rows
        ]

        pattern_summary = []
        if total >= 10:
            for direction, count in overrides_by_direction.items():
                if count / total >= 0.20:
                    pattern_summary.append({
                        "direction": direction,
                        "count":     count,
                        "pct":       round(count / total * 100, 1),
                    })

        return {
            "total_overrides":        total,
            "overrides_by_direction": overrides_by_direction,
            "recent_overrides":       recent_overrides,
            "pattern_summary":        pattern_summary,
        }
