"""Story 9.3 review follow-up — regression test for the ALTER TABLE
DEFAULT-backfill bug caught in code review: a session_links row that
predates the ai_assistance_mode/guarded_mode_enforced migration must read
back as (None, None), not get silently backfilled to a truthy default.

Builds a genuine pre-migration row by creating the session_links table
without the Story 9.3 columns, inserting a row, then running init_db()
(which runs the ALTER TABLE migration) — mirroring what happens to a real
production database that predates this story.
"""
import sqlite3

from app.models.database import Database
from app.services.database_service import DatabaseService


def test_legacy_session_link_reads_back_as_none_none(tmp_path, monkeypatch):
    db_path = str(tmp_path / "legacy.db")

    # Simulate the pre-Story-9.3 schema: session_links without the new columns.
    conn = sqlite3.connect(db_path)
    conn.execute('''
        CREATE TABLE session_links (
            link_id TEXT PRIMARY KEY,
            assignment_id TEXT NOT NULL,
            container_id TEXT,
            port INTEGER,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute(
        "INSERT INTO session_links (link_id, assignment_id, container_id, port, expires_at) "
        "VALUES ('legacy-link', 'assign-1', 'container-1', 7100, '2099-01-01T00:00:00')")
    conn.commit()
    conn.close()

    # init_db() runs the Story 9.3 ALTER TABLE migration against this
    # pre-existing database, same as it would on a real deployment.
    db = Database(db_path)
    db.init_db()

    db_service = DatabaseService()
    monkeypatch.setattr(db_service, "db", db)

    ai_mode, guarded_enforced = db_service.get_session_link_assistance_info("legacy-link")

    assert ai_mode is None
    assert guarded_enforced is None
