"""
Asyncio orchestrator for the 3 job hunt loops.

Runs three concurrent tasks:
  1. discovery_loop  — finds new jobs on a schedule
  2. apply_loop      — processes queued jobs with TUI approval
  3. email_loop      — monitors inbox for replies

Graceful shutdown: SIGINT cancels all tasks cleanly.
"""

import asyncio
import logging
import signal
from dataclasses import dataclass

from rich.console import Console

from .email_monitor import EmailConfig, EmailMonitor
from .job_discovery import DiscoveryResult, JobDiscovery
from .profile import Profile
from .tracker import ApplicationTracker

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class SchedulerConfig:
    discovery_interval_hours: float = 4.0
    email_interval_minutes: float = 15.0
    apply_after_discovery: bool = True  # process queue after each discovery run
    max_applies_per_cycle: int = 5  # max TUI approvals per discovery cycle


class JobHuntScheduler:
    """
    Orchestrates discovery, application, and email monitoring loops.

    Usage:
        scheduler = JobHuntScheduler(profile, config)
        await scheduler.run()         # blocks until SIGINT
        await scheduler.run_once()    # single discovery cycle, no loop
    """

    def __init__(
        self,
        profile: Profile,
        config: SchedulerConfig | None = None,
        email_config: EmailConfig | None = None,
    ):
        self.profile = profile
        self.config = config or SchedulerConfig()
        self.email_config = email_config
        self.tracker = ApplicationTracker()
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        """Run all loops until SIGINT."""
        console.print("[bold cyan]🤖 Job Hunt Agent starting...[/]")
        console.print(f"  Discovery: every {self.config.discovery_interval_hours}h")
        if self.email_config:
            console.print(f"  Email: every {self.config.email_interval_minutes}m")
        console.print("  [dim]Press Ctrl+C to stop[/]\n")

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self._stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, self._stop_event.set)

        tasks = [
            asyncio.create_task(self._discovery_loop(), name="discovery"),
        ]

        if self.email_config:
            tasks.append(asyncio.create_task(self._email_loop(), name="email"))

        try:
            await self._stop_event.wait()
        finally:
            console.print("\n[yellow]Shutting down...[/]")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            console.print("[green]✓ Stopped cleanly[/]")

    async def run_once(self) -> DiscoveryResult:
        """
        Single discovery cycle — no loop, no SIGINT handling.
        Useful for cron jobs or manual triggers.
        """
        return await self._discovery_cycle()

    # ── Loops ──────────────────────────────────────────────────────────────────

    async def _discovery_loop(self) -> None:
        """Discovery loop — runs every N hours."""
        while not self._stop_event.is_set():
            try:
                result = await self._discovery_cycle()
                console.print(
                    f"[dim]{result.timestamp.strftime('%H:%M')}[/] "
                    f"Discovery: [green]+{result.new_jobs}[/] new jobs "
                    f"({result.total_scanned} scanned)"
                )
            except Exception as e:
                logger.error(f"Discovery cycle failed: {e}")

            # Wait for next cycle (or stop signal)
            interval = self.config.discovery_interval_hours * 3600
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _email_loop(self) -> None:
        """Email monitoring loop — runs every N minutes."""
        assert self.email_config is not None
        monitor = EmailMonitor(self.email_config, self.tracker)

        while not self._stop_event.is_set():
            try:
                emails = await monitor.check_once()
                if emails:
                    await monitor.process_results(emails)
                    for em in emails:
                        if em.classification != "unknown":
                            console.print(
                                f"[dim]{em.received_at.strftime('%H:%M')}[/] "
                                f"Email: [cyan]{em.classification}[/] "
                                f"from {em.company or em.sender[:30]}"
                            )
            except Exception as e:
                logger.error(f"Email check failed: {e}")

            interval = self.email_config.check_interval_minutes * 60
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _discovery_cycle(self) -> DiscoveryResult:
        """Single discovery + optional apply pass."""
        discovery = JobDiscovery(self.profile, self.tracker)
        result = await discovery.run()

        if result.new_jobs > 0:
            console.print(f"\n[bold green]Found {result.new_jobs} new matching jobs![/]")
            for opp, score, reasons in result.top_matches[:5]:
                console.print(
                    f"  [{_score_color(score)}]{score:.0f}[/] "
                    f"[cyan]{opp.company}[/] — {opp.title or 'Unknown'} "
                    f"[dim]{opp.url[:60]}[/]"
                )

        if self.config.apply_after_discovery and result.new_jobs > 0:
            await self._apply_queued(max_jobs=self.config.max_applies_per_cycle)

        return result

    async def _apply_queued(self, max_jobs: int = 5) -> None:
        """
        Process queued jobs through TUI approval + submission.

        Each job requires explicit user approval before submitting.
        """
        from datetime import datetime

        import httpx

        from .approval_gate import ApprovalContext, request_approval
        from .ats.api_submit import (
            ashby_api_submit,
            browser_submit_headless,
            greenhouse_api_submit,
            lever_api_submit,
        )
        from .ats.detector import ATSPlatform, detect_from_url
        from .llm_mapper import generate_mapping
        from .personal_scorer import score_opportunity
        from .tracker import Application

        queued = await self.tracker.list_applications(status="queued")
        if not queued:
            return

        console.print(f"\n[bold]{len(queued)} jobs in queue[/] (processing up to {max_jobs})\n")

        processed = 0
        for app_row in queued[:max_jobs]:
            if self._stop_event.is_set():
                break

            url = app_row["url"]
            company = app_row.get("company", "")
            role = app_row.get("role", "")

            console.print(f"[cyan]Processing:[/] {company} — {role}")

            # Detect ATS
            ats = detect_from_url(url)

            # Fetch description
            job_description = ""
            try:
                if ats == ATSPlatform.GREENHOUSE:
                    from .ats.greenhouse import fetch_job_description

                    job_description = await fetch_job_description(url)
                elif ats == ATSPlatform.LEVER:
                    from .ats.lever import fetch_job_description

                    job_description = await fetch_job_description(url)
                elif ats == ATSPlatform.ASHBY:
                    from .ats.ashby import fetch_job_description

                    job_description = await fetch_job_description(url)
            except Exception:
                pass

            # Re-score with full description
            from .jobs import JobOpportunity

            opp = JobOpportunity(
                company=company,
                url=url,
                title=role,
                remote_policy="remote" if "remote" in job_description.lower() else None,
                tech_stack=[
                    s for s in self.profile.primary_skills if s.lower() in job_description.lower()
                ],
            )
            score, reasons = score_opportunity(opp, self.profile)

            if score == 0.0:
                await self.tracker.update_status(
                    url, "rejected", notes="Dealbreaker detected on full description"
                )
                continue

            # LLM mapping
            mapping_result = await generate_mapping(job_description, self.profile)
            field_mapping = mapping_result.get("field_mapping", {})
            cover_letter = mapping_result.get("cover_letter", self.profile.cover_letter_template)

            # TUI approval
            ctx = ApprovalContext(
                job_url=url,
                company=company,
                role=role,
                ats_platform=ats.value,
                score=score,
                score_reasons=reasons,
                field_mapping=field_mapping,
                cover_letter=cover_letter,
                salary_expectation=str(self.profile.preferences.min_salary_usd),
            )

            approved, final_mapping = await request_approval(ctx)

            if not approved:
                await self.tracker.update_status(url, "skipped")
                continue

            # Submit
            if ats == ATSPlatform.GREENHOUSE:
                result = await greenhouse_api_submit(url, final_mapping, cover_letter)
            elif ats == ATSPlatform.LEVER:
                result = await lever_api_submit(url, final_mapping, cover_letter)
            elif ats == ATSPlatform.ASHBY:
                result = await ashby_api_submit(url, final_mapping, cover_letter)
            else:
                result = await browser_submit_headless(url, final_mapping, cover_letter)

            if result.success:
                await self.tracker.update_status(url, "submitted")
                console.print(f"[green]✅ {result.message}[/]")
            else:
                await self.tracker.update_status(
                    url, "queued", notes=f"Submit failed: {result.message}"
                )
                console.print(f"[red]✗ {result.message}[/]")

            processed += 1

        if processed:
            console.print(f"\n[dim]Processed {processed} applications[/]")


def _score_color(score: float) -> str:
    if score >= 70:
        return "green"
    if score >= 40:
        return "yellow"
    return "red"
