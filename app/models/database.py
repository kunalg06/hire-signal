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

            # Per-dimension scores (one row per dimension per submission)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dimension_scores (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    rationale TEXT,
                    scoring_method TEXT NOT NULL DEFAULT 'llm_judge',
                    scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
                )
            ''')

            # Hire verdict with weight snapshot for auditability
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS hire_evaluations (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    composite_score REAL NOT NULL,
                    recommendation TEXT NOT NULL,
                    dimension_weights_json TEXT NOT NULL,
                    narrative TEXT,
                    is_overridden INTEGER DEFAULT 0,
                    override_recommendation TEXT,
                    override_rationale TEXT,
                    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
                )
            ''')

            # Challenges catalog table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS challenges (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    description TEXT NOT NULL,
                    evaluation_rubric_json TEXT,
                    starter_code TEXT,
                    challenge_type TEXT NOT NULL,
                    skill_area TEXT NOT NULL,
                    difficulty TEXT NOT NULL DEFAULT 'medium',
                    ai_assistance_mode TEXT NOT NULL DEFAULT 'unguarded',
                    is_published INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Comparison sessions — group candidate submissions for side-by-side review
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comparison_sessions (
                    id TEXT PRIMARY KEY,
                    challenge_id TEXT NOT NULL,
                    name TEXT,
                    submission_ids_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(challenge_id) REFERENCES challenges(id)
                )
            ''')

            # Override audit log — immutable event log for AI calibration analytics
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS score_overrides (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    ai_recommendation TEXT NOT NULL,
                    human_recommendation TEXT NOT NULL,
                    override_rationale TEXT NOT NULL,
                    overridden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
                )
            ''')

            # Flag audit log — immutable event log for flag lifecycle history
            # (Story 9.2; mirrors score_overrides exactly — see deferred-work.md)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS flag_events (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    flagged_by TEXT,
                    flagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
                )
            ''')

            conn.commit()

        # Schema migration: add challenge_id to assignments if not present
        # (SQLite has no ALTER TABLE ... ADD COLUMN IF NOT EXISTS)
        try:
            with self.get_connection() as conn:
                conn.execute('ALTER TABLE assignments ADD COLUMN challenge_id TEXT')
                conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists — expected on all runs after the first

        # Schema migration: add flag columns to submissions (Story 4.3)
        for _col_sql in [
            'ALTER TABLE submissions ADD COLUMN is_flagged INTEGER DEFAULT 0',
            'ALTER TABLE submissions ADD COLUMN flag_reason TEXT',
            'ALTER TABLE submissions ADD COLUMN flag_by TEXT',
            'ALTER TABLE submissions ADD COLUMN flagged_at TIMESTAMP',
        ]:
            try:
                with self.get_connection() as conn:
                    conn.execute(_col_sql)
                    conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Schema migration: surface guarded-mode injection outcome on
        # session_links (Story 9.3)
        for _col_sql in [
            'ALTER TABLE session_links ADD COLUMN ai_assistance_mode TEXT',
            'ALTER TABLE session_links ADD COLUMN guarded_mode_enforced INTEGER',
        ]:
            try:
                with self.get_connection() as conn:
                    conn.execute(_col_sql)
                    conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Schema migration: soft-delete flag for assignments, so removing one
        # from the employer-facing catalog/list doesn't orphan historical
        # submissions/results still referencing it by id
        try:
            with self.get_connection() as conn:
                conn.execute('ALTER TABLE assignments ADD COLUMN is_deleted INTEGER DEFAULT 0')
                conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Schema migration: per-challenge dimension applicability + optional
        # decision-point fork, both nullable (NULL = all 8 dimensions apply,
        # no decision point) so existing challenges keep scoring exactly as
        # before. See party-mode review 2026-07-11: scoring "Architecture
        # Decisions" (or any dimension) at 0 for a challenge that structurally
        # never offered that opportunity is a validity bug, not a fair score.
        for _col_sql in [
            'ALTER TABLE challenges ADD COLUMN applicable_dimensions_json TEXT',
            'ALTER TABLE challenges ADD COLUMN decision_point_json TEXT',
        ]:
            try:
                with self.get_connection() as conn:
                    conn.execute(_col_sql)
                    conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
