import sqlite3
from contextlib import contextmanager
from app.config import Config

class Database:
    """SQLite database manager"""

    def __init__(self, db_path=None):
        self.db_path = db_path or Config.DB_PATH

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        """Initialize database with required tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Assignments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS assignments (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    starter_code TEXT,
                    evaluation_criteria TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Session links table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_links (
                    link_id TEXT PRIMARY KEY,
                    assignment_id TEXT NOT NULL,
                    container_id TEXT,
                    port INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    FOREIGN KEY(assignment_id) REFERENCES assignments(id)
                )
            ''')

            # Submissions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS submissions (
                    submission_id TEXT PRIMARY KEY,
                    link_id TEXT NOT NULL,
                    assignment_id TEXT NOT NULL,
                    code TEXT,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    evaluation_result TEXT,
                    score REAL,
                    feedback TEXT,
                    files_json TEXT,
                    evaluated_at TIMESTAMP,
                    FOREIGN KEY(link_id) REFERENCES session_links(link_id),
                    FOREIGN KEY(assignment_id) REFERENCES assignments(id)
                )
            ''')

            # Submission files table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS submission_files (
                    file_id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_content TEXT,
                    file_size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
                )
            ''')

            # Session logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_logs (
                    log_id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    interaction_type TEXT,
                    prompt TEXT,
                    response_summary TEXT,
                    file_changes_count INTEGER DEFAULT 0,
                    raw_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
                )
            ''')

            conn.commit()
