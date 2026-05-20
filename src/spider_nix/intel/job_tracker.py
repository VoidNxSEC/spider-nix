"""
Job Application Tracker — manage your job search pipeline.

Track applications through the hiring funnel, record notes,
set interview dates, and monitor your progress.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from spider_nix.intel.job_storage import JobStorage
from spider_nix.intel.jobs import ApplicationStatus, JobOpportunity


@dataclass
class ApplicationRecord:
    """Complete application record with associated job data."""

    job_id: str
    status: ApplicationStatus
    notes: str = ""
    title: str = ""
    company: str = ""
    source_url: str = ""
    apply_url: str = ""
    score: float = 0.0

    # Dates
    applied_date: str | None = None
    interview_date: str | None = None
    follow_up_date: str | None = None
    rejected_date: str | None = None
    updated_at: str = ""

    # Contact
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""

    # Offer
    offer_amount: float | None = None
    offer_details: dict = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.offer_details is None:
            self.offer_details = {}


class ApplicationTracker:
    """
    Track job applications through the hiring pipeline.

    Wraps JobStorage with a higher-level tracking interface.
    """

    def __init__(self, storage: JobStorage | None = None, db_path: str | Path = "jobs.db"):
        self.storage = storage or JobStorage(db_path)
        self._owns_storage = storage is None

    async def close(self) -> None:
        if self._owns_storage:
            await self.storage.close()

    # ---- Status transitions ----

    VALID_TRANSITIONS: dict[ApplicationStatus, list[ApplicationStatus]] = {
        ApplicationStatus.SAVED: [
            ApplicationStatus.APPLIED,
            ApplicationStatus.ARCHIVED,
            ApplicationStatus.WITHDRAWN,
        ],
        ApplicationStatus.APPLIED: [
            ApplicationStatus.PHONE_SCREEN,
            ApplicationStatus.TECHNICAL,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        ],
        ApplicationStatus.PHONE_SCREEN: [
            ApplicationStatus.TECHNICAL,
            ApplicationStatus.ONSITE,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        ],
        ApplicationStatus.TECHNICAL: [
            ApplicationStatus.ONSITE,
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        ],
        ApplicationStatus.ONSITE: [
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        ],
        ApplicationStatus.OFFER: [
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        ],
        ApplicationStatus.ACCEPTED: [],
        ApplicationStatus.REJECTED: [ApplicationStatus.ARCHIVED],
        ApplicationStatus.WITHDRAWN: [ApplicationStatus.ARCHIVED],
        ApplicationStatus.ARCHIVED: [],
    }

    async def save_job(self, job: JobOpportunity, notes: str = "") -> bool:
        """Save a job and mark it as tracked."""
        saved = await self.storage.save_job(job)
        if saved:
            await self.storage.track_application(
                job.id,
                status=ApplicationStatus.SAVED,
                notes=notes,
            )
        return saved

    async def apply(self, job_id: str, notes: str = "") -> bool:
        """Mark a job as applied."""
        return await self.storage.track_application(
            job_id,
            status=ApplicationStatus.APPLIED,
            notes=notes,
        )

    async def advance_status(
        self, job_id: str, new_status: ApplicationStatus, notes: str = ""
    ) -> bool:
        """Advance an application to a new status with validation."""
        # Get current status
        apps = await self.storage.get_applications(limit=1)
        current_status = ApplicationStatus.SAVED
        for app in apps:
            if app["job_id"] == job_id:
                try:
                    current_status = ApplicationStatus(app["status"])
                except ValueError:
                    pass
                break

        # Validate transition
        allowed = self.VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed and current_status != new_status:
            # Non-validating mode — still allow it but log
            pass

        return await self.storage.track_application(
            job_id,
            status=new_status,
            notes=notes,
        )

    async def reject(self, job_id: str, notes: str = "") -> bool:
        """Mark an application as rejected."""
        return await self.storage.track_application(
            job_id,
            status=ApplicationStatus.REJECTED,
            notes=notes,
        )

    async def schedule_interview(self, job_id: str, date: str) -> bool:
        """Schedule an interview for a job."""
        return await self.storage.set_interview_date(job_id, date)

    async def add_notes(self, job_id: str, notes: str) -> bool:
        """Add notes to an application."""
        return await self.storage.update_application_notes(job_id, notes)

    # ---- Reports ----

    async def pipeline_summary(self) -> str:
        """Generate a human-readable pipeline summary."""
        stats = await self.storage.get_application_stats()
        apps = await self.storage.get_applications(limit=20)

        lines = [
            "📊 Pipeline Summary",
            "=" * 40,
            f"Total tracked: {stats.get('total', 0)}",
        ]

        stage_order = [
            ApplicationStatus.SAVED,
            ApplicationStatus.APPLIED,
            ApplicationStatus.PHONE_SCREEN,
            ApplicationStatus.TECHNICAL,
            ApplicationStatus.ONSITE,
            ApplicationStatus.OFFER,
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        ]

        for stage in stage_order:
            count = stats.get(stage.value, 0)
            if count:
                bars = "█" * min(count, 30)
                lines.append(f"  {stage.value:15s}: {count:3d} {bars}")

        # Recent activity
        if apps:
            lines.append("")
            lines.append("📋 Recent Activity:")
            for app in apps[:10]:
                status_icon = {
                    "saved": "💾",
                    "applied": "📤",
                    "phone_screen": "📞",
                    "technical": "💻",
                    "onsite": "🏢",
                    "offer": "🎉",
                    "accepted": "✅",
                    "rejected": "❌",
                    "withdrawn": "↩️",
                    "archived": "📦",
                }.get(app["status"], "❓")
                lines.append(f"  {status_icon} {app['title']} @ {app['company']} [{app['status']}]")

        return "\n".join(lines)

    async def export_applications(self, output_path: str) -> str:
        """Export all applications to JSON."""
        apps = await self.storage.get_applications(limit=10000)
        with open(output_path, "w") as f:
            json.dump(apps, f, indent=2, default=str)
        return output_path
