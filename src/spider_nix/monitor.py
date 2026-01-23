"""Real-time crawl monitoring and statistics."""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text


@dataclass
class CrawlStatistics:
    """Real-time crawl statistics."""

    start_time: float = field(default_factory=time.monotonic)
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    blocked_requests: int = 0
    duplicate_urls: int = 0
    duplicate_content: int = 0

    # Performance metrics
    total_bytes_downloaded: int = 0
    avg_response_time_ms: float = 0.0
    min_response_time_ms: float = float("inf")
    max_response_time_ms: float = 0.0

    # Rate limiting
    current_rate_limit_delay_ms: float = 500.0
    backpressure_detected: bool = False

    # Circuit breaker
    circuit_state: str = "closed"

    # Per-status code breakdown
    status_code_counts: dict[int, int] = field(default_factory=lambda: defaultdict(int))

    # Timing buckets (response time distribution)
    response_time_buckets: dict[str, int] = field(
        default_factory=lambda: {
            "0-500ms": 0,
            "500-1000ms": 0,
            "1-2s": 0,
            "2-5s": 0,
            ">5s": 0,
        }
    )

    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        return time.monotonic() - self.start_time

    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    def requests_per_second(self) -> float:
        """Calculate current requests per second."""
        elapsed = self.elapsed_time()
        if elapsed == 0:
            return 0.0
        return self.total_requests / elapsed

    def update_response_time(self, response_time_ms: float):
        """Update response time statistics."""
        self.min_response_time_ms = min(self.min_response_time_ms, response_time_ms)
        self.max_response_time_ms = max(self.max_response_time_ms, response_time_ms)

        # Update average (running average)
        n = self.total_requests
        if n > 0:
            self.avg_response_time_ms = (
                (self.avg_response_time_ms * (n - 1) + response_time_ms) / n
            )

        # Update bucket
        if response_time_ms < 500:
            self.response_time_buckets["0-500ms"] += 1
        elif response_time_ms < 1000:
            self.response_time_buckets["500-1000ms"] += 1
        elif response_time_ms < 2000:
            self.response_time_buckets["1-2s"] += 1
        elif response_time_ms < 5000:
            self.response_time_buckets["2-5s"] += 1
        else:
            self.response_time_buckets[">5s"] += 1


class CrawlMonitor:
    """Real-time crawl monitoring with rich UI."""

    def __init__(self, max_pages: int = 100, show_live: bool = True):
        self.stats = CrawlStatistics()
        self.max_pages = max_pages
        self.show_live = show_live
        self.console = Console()

        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            console=self.console,
            transient=False,
        )

        self.task_id: TaskID | None = None
        self.live: Live | None = None
        self._running = False

    def start(self):
        """Start monitoring."""
        self._running = True
        self.task_id = self.progress.add_task(
            "[cyan]Crawling...",
            total=self.max_pages,
        )

        if self.show_live:
            self.live = Live(
                self._build_layout(),
                console=self.console,
                refresh_per_second=2,
                transient=False,
            )
            self.live.start()

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self.live:
            self.live.stop()

    def update(
        self,
        url: str | None = None,
        status_code: int | None = None,
        response_time_ms: float | None = None,
        success: bool = False,
        blocked: bool = False,
        failed: bool = False,
        duplicate_url: bool = False,
        duplicate_content: bool = False,
        bytes_downloaded: int = 0,
    ):
        """Update statistics."""
        self.stats.total_requests += 1

        if success:
            self.stats.successful_requests += 1
        if blocked:
            self.stats.blocked_requests += 1
        if failed:
            self.stats.failed_requests += 1
        if duplicate_url:
            self.stats.duplicate_urls += 1
        if duplicate_content:
            self.stats.duplicate_content += 1

        if status_code:
            self.stats.status_code_counts[status_code] += 1

        if response_time_ms:
            self.stats.update_response_time(response_time_ms)

        if bytes_downloaded:
            self.stats.total_bytes_downloaded += bytes_downloaded

        # Update progress bar
        if self.task_id is not None:
            self.progress.update(
                self.task_id,
                completed=self.stats.successful_requests,
            )

        # Update live display
        if self.live and self.show_live:
            self.live.update(self._build_layout())

    def update_rate_limiter(self, delay_ms: float, backpressure: bool):
        """Update rate limiter stats."""
        self.stats.current_rate_limit_delay_ms = delay_ms
        self.stats.backpressure_detected = backpressure

    def update_circuit_breaker(self, state: str):
        """Update circuit breaker state."""
        self.stats.circuit_state = state

    def _build_layout(self) -> Group:
        """Build rich layout with all panels."""
        return Group(
            self.progress,
            self._build_overview_panel(),
            self._build_performance_panel(),
            self._build_status_codes_panel(),
        )

    def _build_overview_panel(self) -> Panel:
        """Build overview statistics panel."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        elapsed = self.stats.elapsed_time()
        elapsed_str = f"{int(elapsed // 3600):02d}:{int((elapsed % 3600) // 60):02d}:{int(elapsed % 60):02d}"

        table.add_row("Elapsed Time", elapsed_str)
        table.add_row(
            "Total Requests",
            f"{self.stats.total_requests}",
        )
        table.add_row(
            "Success Rate",
            f"[green]{self.stats.success_rate():.1f}%[/]",
        )
        table.add_row(
            "Requests/sec",
            f"{self.stats.requests_per_second():.2f}",
        )
        table.add_row(
            "✓ Successful",
            f"[green]{self.stats.successful_requests}[/]",
        )
        table.add_row(
            "✗ Failed",
            f"[red]{self.stats.failed_requests}[/]",
        )
        table.add_row(
            "⚠ Blocked",
            f"[yellow]{self.stats.blocked_requests}[/]",
        )
        table.add_row(
            "⊗ Duplicate URLs",
            f"[dim]{self.stats.duplicate_urls}[/]",
        )
        table.add_row(
            "⊗ Duplicate Content",
            f"[dim]{self.stats.duplicate_content}[/]",
        )

        # Format bytes
        bytes_downloaded = self.stats.total_bytes_downloaded
        if bytes_downloaded > 1024 * 1024:
            bytes_str = f"{bytes_downloaded / (1024 * 1024):.2f} MB"
        elif bytes_downloaded > 1024:
            bytes_str = f"{bytes_downloaded / 1024:.2f} KB"
        else:
            bytes_str = f"{bytes_downloaded} B"

        table.add_row("Downloaded", bytes_str)

        return Panel(table, title="[bold]Overview", border_style="blue")

    def _build_performance_panel(self) -> Panel:
        """Build performance metrics panel."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        # Response times
        if self.stats.min_response_time_ms != float("inf"):
            table.add_row(
                "Min Response Time",
                f"{self.stats.min_response_time_ms:.0f}ms",
            )
        table.add_row(
            "Avg Response Time",
            f"{self.stats.avg_response_time_ms:.0f}ms",
        )
        table.add_row(
            "Max Response Time",
            f"{self.stats.max_response_time_ms:.0f}ms",
        )

        # Rate limiter
        table.add_row(
            "Current Delay",
            f"{self.stats.current_rate_limit_delay_ms:.0f}ms",
        )

        backpressure_text = Text()
        if self.stats.backpressure_detected:
            backpressure_text.append("⚠ YES", style="bold yellow")
        else:
            backpressure_text.append("✓ NO", style="green")
        table.add_row("Backpressure", backpressure_text)

        # Circuit breaker
        circuit_text = Text()
        if self.stats.circuit_state == "closed":
            circuit_text.append("CLOSED", style="green")
        elif self.stats.circuit_state == "open":
            circuit_text.append("OPEN", style="bold red")
        else:
            circuit_text.append("HALF-OPEN", style="yellow")
        table.add_row("Circuit Breaker", circuit_text)

        return Panel(table, title="[bold]Performance", border_style="green")

    def _build_status_codes_panel(self) -> Panel:
        """Build status codes breakdown panel."""
        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("Status Code", style="cyan")
        table.add_column("Count", style="white", justify="right")
        table.add_column("Distribution", style="white")

        total = max(sum(self.stats.status_code_counts.values()), 1)

        # Sort by count descending
        sorted_codes = sorted(
            self.stats.status_code_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        for code, count in sorted_codes[:10]:  # Top 10
            percentage = (count / total) * 100
            bar_length = int(percentage / 2)  # Scale to 50 chars max
            bar = "█" * bar_length

            # Color based on status code
            if 200 <= code < 300:
                style = "green"
            elif 300 <= code < 400:
                style = "blue"
            elif 400 <= code < 500:
                style = "yellow"
            else:
                style = "red"

            table.add_row(
                str(code),
                str(count),
                Text(bar, style=style),
            )

        return Panel(
            table,
            title="[bold]Status Codes (Top 10)",
            border_style="magenta",
        )

    def print_summary(self):
        """Print final summary."""
        self.console.print("\n")
        self.console.rule("[bold]Crawl Summary", style="cyan")
        self.console.print(self._build_overview_panel())
        self.console.print(self._build_performance_panel())
        self.console.print(self._build_status_codes_panel())

        # Response time distribution
        self.console.print("\n[bold cyan]Response Time Distribution:[/]")
        for bucket, count in self.stats.response_time_buckets.items():
            percentage = (
                (count / max(self.stats.total_requests, 1)) * 100
            )
            bar = "█" * int(percentage / 2)
            self.console.print(f"  {bucket:12s} {count:5d} {bar}")


async def monitor_example():
    """Example usage of CrawlMonitor."""
    monitor = CrawlMonitor(max_pages=100, show_live=True)
    monitor.start()

    try:
        for i in range(100):
            await asyncio.sleep(0.1)

            # Simulate different outcomes
            import random
            outcome = random.choice(["success", "blocked", "failed"])

            if outcome == "success":
                monitor.update(
                    url=f"https://example.com/page{i}",
                    status_code=200,
                    response_time_ms=random.uniform(100, 2000),
                    success=True,
                    bytes_downloaded=random.randint(1000, 50000),
                )
            elif outcome == "blocked":
                monitor.update(
                    status_code=429,
                    response_time_ms=random.uniform(50, 500),
                    blocked=True,
                )
            else:
                monitor.update(
                    status_code=500,
                    failed=True,
                )

            # Update rate limiter
            monitor.update_rate_limiter(
                delay_ms=random.uniform(100, 1000),
                backpressure=random.random() > 0.8,
            )

    finally:
        monitor.stop()
        monitor.print_summary()


if __name__ == "__main__":
    asyncio.run(monitor_example())
