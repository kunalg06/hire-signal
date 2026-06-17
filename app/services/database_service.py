import sqlite3
import json
from datetime import datetime
from app.models.database import Database
from app.config import Config

class DatabaseService:
    """Service for database operations"""

    def __init__(self, db_path=None):
        self.db = Database(db_path)

    def create_assignment(self, assignment_id, title, description, starter_code, evaluation_criteria):
        """Create a new assignment"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO assignments (id, title, description, starter_code, evaluation_criteria)
                VALUES (?, ?, ?, ?, ?)
            ''', (assignment_id, title, description, starter_code, evaluation_criteria))
            conn.commit()

    def get_assignment(self, assignment_id):
        """Get assignment details"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM assignments WHERE id = ?', (assignment_id,))
            return cursor.fetchone()

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
        """Get submission and evaluation results"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.submission_id, s.link_id, s.assignment_id, s.code, s.submitted_at, s.evaluation_result, s.score, s.feedback, a.title, a.evaluation_criteria
                FROM submissions s
                JOIN assignments a ON s.assignment_id = a.id
                WHERE s.submission_id = ?
            ''', (submission_id,))
            return cursor.fetchone()

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
        """Get Claude session logs for submission"""
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
