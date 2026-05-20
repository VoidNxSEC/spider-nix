"""
Job Storage — SQLite persistence with FTS5 full-text search.

Stores job opportunities, application tracking, and profile data.
Provides CRUD operations with async interface.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from spider_nix.intel.job_matcher import JobSeekerProfile
from spider_nix.intel.jobs import (
    ApplicationStatus,
    JobOpportunity,
    JobSource,
    RemotePolicy,
    Seniority,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT DEFAULT '',
    remote_policy TEXT DEFAULT 'unknown',
    employment_type TEXT DEFAULT 'full_time',
    seniority TEXT DEFAULT 'unknown',
    description TEXT DEFAULT '',
    requirements TEXT DEFAULT '[]',
    responsibilities TEXT DEFAULT '[]',
    benefits TEXT DEFAULT '[]',
    qualifications TEXT DEFAULT '[]',
    tech_stack TEXT DEFAULT '[]',
    salary_min REAL,
    salary_max REAL,
    salary_currency TEXT DEFAULT 'USD',
    salary_period TEXT DEFAULT 'yearly',
    salary_equity TEXT,
    salary_raw TEXT,
    apply_url TEXT DEFAULT '',
    application_deadline TEXT,
    date_posted TEXT,
    date_found TEXT NOT NULL,
    score REAL DEFAULT 0.0,
    match_details TEXT DEFAULT '{}',
    raw_data TEXT DEFAULT '{}',
    company_data TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
    title, company, description, location, tech_stack,
    content='jobs', content_rowid='rowid'
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'saved',
    notes TEXT DEFAULT '',
    resume_version TEXT,
    cover_letter_path TEXT,
    contact_name TEXT,
    contact_email TEXT,
    contact_phone TEXT,
    interview_date TEXT,
    follow_up_date TEXT,
    applied_date TEXT,
    rejected_date TEXT,
    offer_amount REAL,
    offer_details TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS profile (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Triggers for FTS sync
CREATE TRIGGER IF NOT EXISTS jobs_ai AFTER INSERT ON jobs BEGIN
    INSERT INTO jobs_fts(rowid, title, company, description, location, tech_stack)
    VALUES (new.rowid, new.title, new.company, new.description, new.location, new.tech_stack);
END;

CREATE TRIGGER IF NOT EXISTS jobs_ad AFTER DELETE ON jobs BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, title, company, description, location, tech_stack)
    VALUES ('delete', old.rowid, old.title, old.company, old.description, old.location, old.tech_stack);
END;

CREATE TRIGGER IF NOT EXISTS jobs_au AFTER UPDATE ON jobs BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, title, company, description, location, tech_stack)
    VALUES ('delete', old.rowid, old.title, old.company, old.description, old.location, old.tech_stack);
    INSERT INTO jobs_fts(rowid, title, company, description, location, tech_stack)
    VALUES (new.rowid, new.title, new.company, new.description, new.location, new.tech_stack);
END;
"""


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


class JobStorage:
    """Async SQLite storage for job opportunities and applications."""

    def __init__(self, db_path: str | Path = "jobs.db"):
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    # ---- Connection management ----

    async def _ensure_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(str(self.db_path))
            self._conn.row_factory = aiosqlite.Row
            await self._conn.executescript(SCHEMA)
            await self._conn.commit()
        return self._conn

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ---- Job CRUD ----

    async def save_job(self, job: JobOpportunity) -> bool:
        """Insert or replace a job opportunity. Returns True if inserted."""
        conn = await self._ensure_conn()
        data = job.to_dict()
        salary = data["salary"]

        try:
            await conn.execute(
                """INSERT OR REPLACE INTO jobs (
                    id, source, source_url, title, company, location,
                    remote_policy, employment_type, seniority, description,
                    requirements, responsibilities, benefits, qualifications,
                    tech_stack, salary_min, salary_max, salary_currency,
                    salary_period, salary_equity, salary_raw,
                    apply_url, application_deadline, date_posted, date_found,
                    score, match_details, raw_data, company_data,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    data["id"],
                    data["source"],
                    data["source_url"],
                    data["title"],
                    data["company"],
                    data["location"],
                    data["remote_policy"],
                    data["employment_type"],
                    data["seniority"],
                    data["description"],
                    json.dumps(data["requirements"]),
                    json.dumps(data["responsibilities"]),
                    json.dumps(data["benefits"]),
                    json.dumps(data["qualifications"]),
                    json.dumps(data["tech_stack"]),
                    salary["min_amount"],
                    salary["max_amount"],
                    salary["currency"],
                    salary["period"],
                    salary["equity"],
                    salary["raw_text"],
                    data["apply_url"],
                    data["application_deadline"],
                    data["date_posted"],
                    data["date_found"],
                    data["score"],
                    json.dumps(data["match_details"]),
                    json.dumps(data.get("raw_data", {})),
                    json.dumps(data.get("company_profile", {})),
                ),
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save job {job.id}: {e}")
            return False

    async def save_jobs_batch(self, jobs: list[JobOpportunity]) -> int:
        """Save multiple jobs. Returns count of saved jobs."""
        count = 0
        for job in jobs:
            if await self.save_job(job):
                count += 1
        return count

    async def get_job(self, job_id: str) -> JobOpportunity | None:
        """Get a single job by ID."""
        conn = await self._ensure_conn()
        cursor = await conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        return self._row_to_job(row) if row else None

    async def get_jobs(
        self,
        source: JobSource | None = None,
        company: str | None = None,
        seniority: Seniority | None = None,
        remote_policy: RemotePolicy | None = None,
        min_score: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JobOpportunity]:
        """Query jobs with filters."""
        conn = await self._ensure_conn()
        query = "SELECT * FROM jobs WHERE 1=1"
        params: list[Any] = []

        if source:
            query += " AND source = ?"
            params.append(source.value)
        if company:
            query += " AND company LIKE ?"
            params.append(f"%{company}%")
        if seniority:
            query += " AND seniority = ?"
            params.append(seniority.value)
        if remote_policy:
            query += " AND remote_policy = ?"
            params.append(remote_policy.value)
        if min_score is not None:
            query += " AND score >= ?"
            params.append(min_score)

        query += " ORDER BY score DESC, date_found DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_job(r) for r in rows if r]

    async def search_jobs(self, query: str, limit: int = 100) -> list[JobOpportunity]:
        """Full-text search across jobs."""
        conn = await self._ensure_conn()
        try:
            cursor = await conn.execute(
                """SELECT j.* FROM jobs j
                   JOIN jobs_fts f ON j.rowid = f.rowid
                   WHERE jobs_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            )
            rows = await cursor.fetchall()
            return [self._row_to_job(r) for r in rows if r]
        except Exception as e:
            logger.warning(f"FTS search failed: {e}, falling back to LIKE")
            cursor = await conn.execute(
                """SELECT * FROM jobs WHERE title LIKE ? OR company LIKE ? OR description LIKE ?
                   ORDER BY score DESC LIMIT ?""",
                (f"%{query}%", f"%{query}%", f"%{query}%", limit),
            )
            rows = await cursor.fetchall()
            return [self._row_to_job(r) for r in rows if r]

    async def job_exists(self, job_id: str) -> bool:
        """Check if a job already exists in storage."""
        conn = await self._ensure_conn()
        cursor = await conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,))
        return await cursor.fetchone() is not None

    async def count_jobs(self) -> int:
        """Total number of stored jobs."""
        conn = await self._ensure_conn()
        cursor = await conn.execute("SELECT COUNT(*) FROM jobs")
        row = await cursor.fetchone()
        return row[0] if row else 0

    # ---- Application tracking ----

    async def track_application(
        self,
        job_id: str,
        status: ApplicationStatus = ApplicationStatus.SAVED,
        notes: str = "",
    ) -> bool:
        """Create or update an application for a job."""
        conn = await self._ensure_conn()
        now = datetime.now(timezone.utc).isoformat()

        try:
            applied_date = now if status == ApplicationStatus.APPLIED else None
            rejected_date = now if status == ApplicationStatus.REJECTED else None

            await conn.execute(
                """INSERT INTO applications (job_id, status, notes, applied_date, rejected_date, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                   status = excluded.status,
                   notes = excluded.notes,
                   applied_date = COALESCE(excluded.applied_date, applications.applied_date),
                   rejected_date = COALESCE(excluded.rejected_date, applications.rejected_date),
                   updated_at = excluded.updated_at""",
                (job_id, status.value, notes, applied_date, rejected_date, now),
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to track application: {e}")
            return False

    async def get_applications(
        self,
        status: ApplicationStatus | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get applications with joined job data."""
        conn = await self._ensure_conn()
        query = """
            SELECT a.*, j.title, j.company, j.source_url, j.apply_url, j.score
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            WHERE 1=1
        """
        params: list[Any] = []
        if status:
            query += " AND a.status = ?"
            params.append(status.value)

        query += " ORDER BY a.updated_at DESC LIMIT ?"
        params.append(limit)

        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_application_stats(self) -> dict:
        """Get application funnel statistics."""
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT status, COUNT(*) as count FROM applications GROUP BY status"
        )
        rows = await cursor.fetchall()
        stats = {r["status"]: r["count"] for r in rows}
        total = sum(stats.values())
        stats["total"] = total
        return stats

    async def update_application_notes(self, job_id: str, notes: str) -> bool:
        conn = await self._ensure_conn()
        await conn.execute(
            "UPDATE applications SET notes = ?, updated_at = datetime('now') WHERE job_id = ?",
            (notes, job_id),
        )
        await conn.commit()
        return True

    async def set_interview_date(self, job_id: str, interview_date: str) -> bool:
        conn = await self._ensure_conn()
        await conn.execute(
            """UPDATE applications SET
               status = 'technical', interview_date = ?, updated_at = datetime('now')
               WHERE job_id = ?""",
            (interview_date, job_id),
        )
        await conn.commit()
        return True

    # ---- Profile management ----

    async def save_profile(self, profile: JobSeekerProfile) -> bool:
        """Save job seeker profile to storage."""
        conn = await self._ensure_conn()
        profile_json = json.dumps(profile.to_dict())
        await conn.execute(
            "INSERT OR REPLACE INTO profile (key, value) VALUES (?, ?)",
            ("job_seeker_profile", profile_json),
        )
        await conn.commit()
        return True

    async def load_profile(self) -> JobSeekerProfile | None:
        """Load job seeker profile from storage."""
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT value FROM profile WHERE key = ?", ("job_seeker_profile",)
        )
        row = await cursor.fetchone()
        if row:
            return JobSeekerProfile.from_dict(json.loads(row[0]))
        return None

    # ---- Helpers ----

    def _row_to_job(self, row: aiosqlite.Row) -> JobOpportunity:
        """Convert a DB row to a JobOpportunity object."""
        d = dict(row)

        # Parse JSON fields
        for field in [
            "requirements",
            "responsibilities",
            "benefits",
            "qualifications",
            "tech_stack",
        ]:
            try:
                d[field] = json.loads(d.get(field, "[]"))
            except (json.JSONDecodeError, TypeError):
                d[field] = []

        for field in ["match_details", "raw_data", "company_data"]:
            try:
                d[field] = json.loads(d.get(field, "{}"))
            except (json.JSONDecodeError, TypeError):
                d[field] = {}

        # Build salary
        from spider_nix.intel.jobs import Salary

        salary = None
        if d.get("salary_min") or d.get("salary_max"):
            salary = Salary(
                min_amount=d.pop("salary_min", None),
                max_amount=d.pop("salary_max", None),
                currency=d.pop("salary_currency", "USD"),
                period=d.pop("salary_period", "yearly"),
                equity=d.pop("salary_equity", None),
                raw_text=d.pop("salary_raw", None),
            )
        else:
            for k in (
                "salary_min",
                "salary_max",
                "salary_currency",
                "salary_period",
                "salary_equity",
                "salary_raw",
            ):
                d.pop(k, None)

        # Build company profile
        from spider_nix.intel.jobs import CompanyProfile

        company_data = d.pop("company_data", {})
        company_profile = (
            CompanyProfile(**company_data) if company_data and company_data.get("name") else None
        )

        # Parse enums
        source = d.get("source", "other")
        try:
            source = JobSource(source)
        except ValueError:
            source = JobSource.OTHER

        remote_policy = d.get("remote_policy", "unknown")
        try:
            remote_policy = RemotePolicy(remote_policy)
        except ValueError:
            remote_policy = RemotePolicy.UNKNOWN

        seniority = d.get("seniority", "unknown")
        try:
            seniority = Seniority(seniority)
        except ValueError:
            seniority = Seniority.UNKNOWN

        return JobOpportunity(
            id=d.get("id", ""),
            source=source,
            source_url=d.get("source_url", ""),
            title=d.get("title", ""),
            company=d.get("company", ""),
            location=d.get("location", ""),
            remote_policy=remote_policy,
            seniority=seniority,
            description=d.get("description", ""),
            requirements=d.get("requirements", []),
            responsibilities=d.get("responsibilities", []),
            benefits=d.get("benefits", []),
            qualifications=d.get("qualifications", []),
            tech_stack=d.get("tech_stack", []),
            salary=salary,
            apply_url=d.get("apply_url", ""),
            application_deadline=d.get("application_deadline"),
            date_posted=d.get("date_posted"),
            date_found=d.get("date_found", ""),
            score=d.get("score", 0.0),
            match_details=d.get("match_details", {}),
            raw_data=d.get("raw_data", {}),
            company_profile=company_profile,
        )
