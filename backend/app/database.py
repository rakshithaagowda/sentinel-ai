import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "sentinel_ai.db"))


@contextmanager
def get_db():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def row_to_dict(row):
    return dict(row) if row else None


def init_db():
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Citizen', 'Responder')),
                responder_type TEXT,
                location TEXT,
                availability_status TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                citizen_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                location TEXT NOT NULL,
                latitude TEXT,
                longitude TEXT,
                people_affected TEXT,
                image_path TEXT,
                audio_path TEXT,
                incident_type TEXT NOT NULL DEFAULT 'Pending Analysis',
                incident_category TEXT NOT NULL DEFAULT 'General',
                severity TEXT NOT NULL DEFAULT 'Medium',
                confidence INTEGER NOT NULL DEFAULT 0,
                priority_reason TEXT NOT NULL DEFAULT '',
                ai_reason TEXT NOT NULL DEFAULT '[]',
                ai_summary TEXT NOT NULL DEFAULT '',
                impact_analysis TEXT NOT NULL DEFAULT '',
                safety_recommendations TEXT NOT NULL DEFAULT '[]',
                recommended_responder TEXT NOT NULL DEFAULT '',
                responder_reason TEXT NOT NULL DEFAULT '',
                emergency_contact TEXT NOT NULL DEFAULT '{}',
                public_advisory TEXT NOT NULL DEFAULT '',
                is_emergency INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Reported',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(citizen_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS responder_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL,
                responder_id INTEGER,
                recommended_responder TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Assigned',
                assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(incident_id) REFERENCES incidents(id),
                FOREIGN KEY(responder_id) REFERENCES users(id)
            );
            """
        )
        _ensure_column(db, "users", "responder_type", "TEXT")
        _ensure_column(db, "users", "location", "TEXT")
        _ensure_column(db, "users", "availability_status", "TEXT")
        _ensure_column(db, "incidents", "emergency_contact", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(db, "incidents", "incident_category", "TEXT NOT NULL DEFAULT 'General'")
        _ensure_column(db, "incidents", "priority_reason", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(db, "incidents", "is_emergency", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(db, "incidents", "latitude", "TEXT")
        _ensure_column(db, "incidents", "longitude", "TEXT")


def _ensure_column(db, table_name: str, column_name: str, definition: str):
    columns = [row["name"] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()]
    if column_name not in columns:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
