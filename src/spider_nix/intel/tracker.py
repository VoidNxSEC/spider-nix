"""
Application history tracker using SQLite.

Tracks every application attempt with status, screenshots, and events.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    company TEXT,
    role TEXT,
    ats_platform TEXT,
    status TEXT DEFAULT 'pending',
    -- status: pending | submitted | rejected | interview | ghosted | offer
    applied_at DATETIME,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    screenshot_path TEXT,
    cover_letter TEXT,
    field_mapping TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER REFERENCES applications(id),
    event_type TEXT,
    -- event_type: applied | email_received | interview_scheduled | rejected | offer
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    raw_data TEXT
);

CREATE INDEX IF NOT EXISTS idx_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_company ON applications(company);
"""


@dataclass
class Application:
    url: str
    company: str
    role: str
    ats_platform: str
    status: str = "pending"
    applied_at: datetime | None = None
    screenshot_path: str | None = None
    cover_letter: str | None = None
    notes: str | None = None


class ApplicationTracker:
    def __init__(self, db_path: Path = Path("applications.db")):
        self.db_path = db_path
        self._initialized = False

    async def _init(self):
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        self._initialized = True

    async def record_application(self, app: Application) -> int:
        """Insert or update application record. Returns row id."""
        import json

        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO applications (url, company, role, ats_platform, status,
                    applied_at, screenshot_path, cover_letter)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    status = excluded.status,
                    last_updated = CURRENT_TIMESTAMP
                """,
                (
                    app.url,
                    app.company,
                    app.role,
                    app.ats_platform,
                    app.status,
                    app.applied_at,
                    app.screenshot_path,
                    app.cover_letter,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_status(self, url: str, status: str, notes: str | None = None):
        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE applications SET status=?, notes=?, last_updated=CURRENT_TIMESTAMP WHERE url=?",
                (status, notes, url),
            )
            await db.commit()

    async def list_applications(self, status: str | None = None) -> list[dict]:
        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                cursor = await db.execute(
                    "SELECT * FROM applications WHERE status=? ORDER BY applied_at DESC", (status,)
                )
            else:
                cursor = await db.execute("SELECT * FROM applications ORDER BY applied_at DESC")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
