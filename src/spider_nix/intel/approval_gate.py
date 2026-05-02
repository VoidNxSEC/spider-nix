"""
Human-in-the-loop approval gate.

Architecture:
- Rich TUI shows full field diff in terminal
- User approves/edits/rejects interactively
- ntfy push notification sent in parallel if NTFY_TOKEN is set
  (notification is informational only — approval is always terminal-first)
- Zero Telegram, zero browser window

Environment variables (all optional):
  NTFY_URL    default: https://ntfy.sh
  NTFY_TOPIC  default: job-agent
  NTFY_TOKEN  if set, enables push notifications
"""

import asyncio
import os
from dataclasses import dataclass

import httpx
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()


@dataclass
class ApprovalContext:
    job_url: str
    company: str
    role: str
    ats_platform: str
    score: float
    score_reasons: list[str]
    field_mapping: dict
    cover_letter: str
    salary_expectation: str | None = None


async def request_approval(ctx: ApprovalContext) -> tuple[bool, dict]:
    """
    Show TUI diff and wait for human approval.

    Returns (approved: bool, final_mapping: dict).
    final_mapping may differ from ctx.field_mapping if user edited fields.

    Fires ntfy notification in background if NTFY_TOKEN configured.
    Does NOT wait for ntfy response — terminal is always the gate.
    """
    asyncio.create_task(_ntfy_notify(ctx))
    return await _tui_approval(ctx)


async def _tui_approval(ctx: ApprovalContext) -> tuple[bool, dict]:
    """
    Rich TUI interactive approval.

    Layout:
    ┌──────────────────────────────────────────────────┐
    │  🎯  Cloudflare · Senior Security Architect       │
    │  Score: 94/100 · Remote · greenhouse              │
    ├──────────────────────────────────────────────────┤
    │  Field              Value                         │
    │  first_name         Marcos                        │
    │  email              mar***ail.com                 │
    │  cover_letter       I build systems where...      │
    ├──────────────────────────────────────────────────┤
    │  [s] submit  [e] edit field  [v] view CL  [q] skip
    └──────────────────────────────────────────────────┘
    """
    mapping = dict(ctx.field_mapping)
    cover_letter = ctx.cover_letter

    while True:
        console.clear()
        _render_approval_panel(ctx, mapping, cover_letter)

        choice = Prompt.ask(
            "\n[bold cyan]>[/]",
            choices=["s", "e", "v", "q"],
            default="q",
        )

        if choice == "q":
            console.print("[yellow]⊘ Skipped[/]")
            return False, mapping

        elif choice == "s":
            console.print("\n[bold green]✓ Approved — submitting...[/]")
            return True, mapping

        elif choice == "v":
            console.clear()
            console.print(Panel(
                cover_letter,
                title="[bold]Cover Letter[/]",
                border_style="cyan",
                padding=(1, 2),
            ))
            Prompt.ask("\n[dim]Press Enter to go back[/]", default="")

        elif choice == "e":
            console.print("\n[dim]Available fields:[/]")
            editable = [k for k in mapping if k != "cover_letter"]
            editable.append("cover_letter")

            for i, key in enumerate(editable):
                val = mapping.get(key, cover_letter if key == "cover_letter" else "")
                preview = str(val)[:60] + "..." if len(str(val)) > 60 else str(val)
                console.print(f"  [cyan]{i+1:2}.[/] {key:25} [dim]{preview}[/]")

            field_idx = Prompt.ask("\n[cyan]Field number[/] (or Enter to cancel)", default="")
            if not field_idx.strip():
                continue

            try:
                idx = int(field_idx) - 1
                field_key = editable[idx]
            except (ValueError, IndexError):
                console.print("[red]Invalid selection[/]")
                await asyncio.sleep(1)
                continue

            if field_key == "cover_letter":
                console.print(Panel(cover_letter, title="Current cover letter"))
                new_val = Prompt.ask("[cyan]New cover letter[/] (Enter to keep)")
                if new_val.strip():
                    cover_letter = new_val
            else:
                current = mapping.get(field_key, "")
                new_val = Prompt.ask(
                    f"[cyan]{field_key}[/]",
                    default=str(current),
                )
                mapping[field_key] = new_val


def _render_approval_panel(ctx: ApprovalContext, mapping: dict, cover_letter: str) -> None:
    """Render the approval TUI panel."""
    score_color = "green" if ctx.score >= 70 else "yellow" if ctx.score >= 40 else "red"
    console.print(Panel(
        f"[bold]{ctx.role}[/] @ [cyan]{ctx.company}[/]  "
        f"[{score_color}]Score: {ctx.score:.0f}/100[/]  "
        f"[dim]{ctx.ats_platform} · {ctx.job_url}[/]",
        border_style=score_color,
        padding=(0, 1),
    ))

    table = Table(box=box.SIMPLE, padding=(0, 1), show_header=True)
    table.add_column("Field", style="cyan", width=25)
    table.add_column("Value", style="white")

    SENSITIVE = {"email", "phone"}

    for key, value in mapping.items():
        if not value:
            continue
        if key == "cover_letter":
            preview = str(value)[:80].replace("\n", " ") + "..."
            table.add_row(key, f"[dim]{preview}[/]")
        elif key in SENSITIVE:
            s = str(value)
            masked = s[:3] + "***" + s[-4:] if len(s) > 7 else "***"
            table.add_row(key, f"[dim]{masked}[/]")
        else:
            table.add_row(key, str(value)[:80])

    console.print(table)

    if ctx.score_reasons:
        reasons_text = "  ".join(
            f"[red]✗ {r}[/]" if "DEALBREAKER" in r or "penalty" in r.lower()
            else f"[green]✓ {r}[/]"
            for r in ctx.score_reasons
        )
        console.print(Panel(
            reasons_text,
            title="[dim]Score breakdown[/]",
            border_style="dim",
            padding=(0, 1),
        ))

    console.print(
        "\n  [bold cyan][s][/] submit  "
        "[bold cyan][e][/] edit field  "
        "[bold cyan][v][/] view cover letter  "
        "[bold cyan][q][/] skip"
    )


async def _ntfy_notify(ctx: ApprovalContext) -> None:
    """
    Fire-and-forget ntfy notification.

    Self-hosted ntfy (e.g. push.voidnx.com) — no intermediary.
    Configure via environment:
      NTFY_URL    https://push.voidnx.com
      NTFY_TOPIC  job-agent
      NTFY_TOKEN  tk_xxxxxxxxxxxx

    Notification is informational only.
    It does NOT gate the approval — terminal does.
    """
    ntfy_url = os.environ.get("NTFY_URL", "https://ntfy.sh")
    ntfy_topic = os.environ.get("NTFY_TOPIC", "job-agent")
    ntfy_token = os.environ.get("NTFY_TOKEN")

    if not ntfy_token:
        return

    score_emoji = "🟢" if ctx.score >= 70 else "🟡" if ctx.score >= 40 else "🔴"
    message = (
        f"{score_emoji} Score: {ctx.score:.0f}/100\n"
        f"ATS: {ctx.ats_platform}\n"
        f"{ctx.job_url}"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{ntfy_url}/{ntfy_topic}",
                content=message.encode(),
                headers={
                    "Authorization": f"Bearer {ntfy_token}",
                    "Title": f"{ctx.role} @ {ctx.company}",
                    "Tags": "briefcase",
                    "Priority": "default",
                    "Actions": f"view, Abrir vaga, {ctx.job_url}",
                },
            )
    except Exception:
        pass  # notification failure never blocks the agent
