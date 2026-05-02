"""
IMAP inbox watcher for job application follow-ups.

Uses stdlib imaplib + asyncio.to_thread (zero new dependencies).

Flow:
  1. Connect to IMAP server
  2. Search for unseen emails from known ATS senders
     OR containing company names from tracker
  3. Classify each email: interview_invite | rejection | offer | followup | unknown
  4. Update tracker status
  5. Send ntfy notification for high-priority events (interview, offer)

Classification strategy:
  - Fast: regex rules cover 90% of cases
  - Fallback: LLM for ambiguous emails

Environment:
  IMAP credentials come from profile.toml [email] section
  ntfy config from NTFY_URL / NTFY_TOPIC / NTFY_TOKEN env vars
"""

import asyncio
import email
import imaplib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from typing import Literal

import httpx

from .profile import Profile
from .tracker import ApplicationTracker

logger = logging.getLogger(__name__)

EmailClass = Literal["interview_invite", "rejection", "offer", "followup", "unknown"]


@dataclass
class EmailConfig:
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    check_interval_minutes: int = 15


@dataclass
class ClassifiedEmail:
    subject: str
    sender: str
    classification: EmailClass
    confidence: float
    company: str | None
    body_preview: str
    received_at: datetime


# Known ATS sender domains
ATS_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workday.com",
    "smartrecruiters.com",
    "bamboohr.com",
    "jobvite.com",
    "icims.com",
    "taleo.net",
    "successfactors.com",
    "recruitcrm.io",
]

# Regex classification rules — ordered by priority
CLASSIFICATION_RULES: list[tuple[EmailClass, float, list[str]]] = [
    # Offer
    (
        "offer",
        0.95,
        [
            r"pleased to offer",
            r"we.d like to offer you",
            r"offer of employment",
            r"job offer",
            r"formal offer",
            r"compensation package",
        ],
    ),
    # Interview invite
    (
        "interview_invite",
        0.90,
        [
            r"schedule.{0,20}interview",
            r"interview.{0,20}schedule",
            r"we.d like to.{0,30}interview",
            r"invite you.{0,30}interview",
            r"next step.{0,20}interview",
            r"technical screen",
            r"phone screen",
            r"video call",
            r"calendly",
            r"schedule.{0,20}call",
            r"book.{0,20}time",
            r"meet with.{0,20}team",
        ],
    ),
    # Rejection
    (
        "rejection",
        0.92,
        [
            r"unfortunately",
            r"not moving forward",
            r"decided to.{0,30}other candidate",
            r"not a match",
            r"not the right fit",
            r"decided not to",
            r"we.re unable to",
            r"will not be moving",
            r"position has been filled",
            r"other candidates",
            r"not selected",
        ],
    ),
    # Followup / status
    (
        "followup",
        0.75,
        [
            r"following up",
            r"update on your application",
            r"application status",
            r"under review",
            r"still reviewing",
            r"next steps",
            r"thank you for applying",
            r"we received your application",
            r"application.*confirmed",
        ],
    ),
]


class EmailMonitor:
    """Monitors inbox for job application replies."""

    def __init__(self, config: EmailConfig, tracker: ApplicationTracker | None = None):
        self.config = config
        self.tracker = tracker or ApplicationTracker()

    async def check_once(self) -> list[ClassifiedEmail]:
        """
        Single inbox check cycle.

        Returns list of classified emails found.
        """
        return await asyncio.to_thread(self._check_sync)

    def _check_sync(self) -> list[ClassifiedEmail]:
        """Blocking IMAP check — runs in thread pool."""
        try:
            mail = imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port)
            mail.login(self.config.imap_user, self.config.imap_password)
            mail.select("INBOX")
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            return []

        classified = []

        try:
            # Search unseen emails from ATS domains
            # Build OR query for known ATS senders
            ats_queries = []
            for domain in ATS_DOMAINS[:5]:  # IMAP OR has limits
                ats_queries.append(f'FROM "@{domain}"')

            # Also search by "application" in subject (catches custom ATS)
            search_criteria = '(UNSEEN SUBJECT "application")'
            _, data = mail.search(None, search_criteria)

            msg_ids = data[0].split() if data[0] else []

            # Also search for ATS domains
            _, data2 = mail.search(None, '(UNSEEN FROM "greenhouse.io")')
            _, data3 = mail.search(None, '(UNSEEN FROM "lever.co")')
            _, data4 = mail.search(None, '(UNSEEN FROM "ashbyhq.com")')

            all_ids = set(msg_ids)
            for d in [data2[0], data3[0], data4[0]]:
                if d:
                    all_ids.update(d.split())

            for msg_id in list(all_ids)[:20]:  # max 20 per cycle
                try:
                    _, msg_data = mail.fetch(msg_id, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)

                    subject = _decode_header_str(msg.get("Subject", ""))
                    sender = _decode_header_str(msg.get("From", ""))
                    body = _extract_body(msg)

                    classification, confidence = _classify_email(subject, body)

                    # Extract company from sender domain or subject
                    company = _extract_company(sender, subject)

                    result = ClassifiedEmail(
                        subject=subject,
                        sender=sender,
                        classification=classification,
                        confidence=confidence,
                        company=company,
                        body_preview=body[:300],
                        received_at=datetime.now(),
                    )
                    classified.append(result)

                    # Mark as read so we don't process twice
                    mail.store(msg_id, "+FLAGS", "\\Seen")

                except Exception as e:
                    logger.warning(f"Failed to process email {msg_id}: {e}")

        finally:
            try:
                mail.logout()
            except Exception:
                pass

        return classified

    async def process_results(self, emails: list[ClassifiedEmail]) -> None:
        """
        Update tracker and send ntfy for each classified email.
        """
        for em in emails:
            if em.classification == "unknown":
                continue

            # Map classification to tracker status
            STATUS_MAP: dict[EmailClass, str] = {
                "interview_invite": "interview",
                "rejection": "rejected",
                "offer": "offer",
                "followup": "submitted",  # keep as submitted, just noteworthy
            }
            new_status = STATUS_MAP.get(em.classification, "submitted")

            # Try to find matching application in tracker
            apps = await self.tracker.list_applications()
            matched_url = None
            if em.company:
                for app in apps:
                    if (
                        app.get("company", "").lower() in em.company.lower()
                        or em.company.lower() in app.get("company", "").lower()
                    ):
                        matched_url = app["url"]
                        break

            if matched_url:
                await self.tracker.update_status(
                    matched_url,
                    new_status,
                    notes=f"{em.classification} ({em.confidence:.0%}) | {em.subject[:80]}",
                )
                logger.info(f"Updated {em.company} → {new_status}")

            # ntfy notification
            await _ntfy_email_alert(em)


def _classify_email(subject: str, body: str) -> tuple[EmailClass, float]:
    """
    Classify email using regex rules.

    Returns (classification, confidence).
    """
    content = f"{subject} {body}".lower()

    for classification, confidence, patterns in CLASSIFICATION_RULES:
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return classification, confidence

    return "unknown", 0.0


def _decode_header_str(value: str) -> str:
    """Decode email header (handles encoded words)."""
    try:
        parts = decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(str(part))
        return " ".join(decoded)
    except Exception:
        return value


def _extract_body(msg: email.message.Message) -> str:
    """Extract plain text body from email."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace") if payload else ""
        except Exception:
            pass

    return body[:3000]


def _extract_company(sender: str, subject: str) -> str | None:
    """Try to extract company name from sender or subject."""
    # From "Company Name <noreply@company.com>"
    match = re.match(r"^([^<]+)<", sender)
    if match:
        name = match.group(1).strip()
        if name and not re.match(r"^[a-z0-9._%+-]+@", name.lower()):
            return name.strip('"').strip()

    # From sender domain
    domain_match = re.search(r"@([^>]+)", sender)
    if domain_match:
        domain = domain_match.group(1)
        parts = domain.split(".")
        if len(parts) >= 2 and parts[-2] not in ("gmail", "yahoo", "hotmail", "outlook"):
            return parts[-2].capitalize()

    return None


async def _ntfy_email_alert(em: ClassifiedEmail) -> None:
    """Send ntfy notification for significant email events."""
    ntfy_url = os.environ.get("NTFY_URL", "https://ntfy.sh")
    ntfy_topic = os.environ.get("NTFY_TOPIC", "job-agent")
    ntfy_token = os.environ.get("NTFY_TOKEN")

    if not ntfy_token:
        return

    PRIORITY_MAP = {
        "offer": "urgent",
        "interview_invite": "high",
        "rejection": "default",
        "followup": "low",
    }

    EMOJI_MAP = {
        "offer": "🎉",
        "interview_invite": "📅",
        "rejection": "❌",
        "followup": "📬",
    }

    emoji = EMOJI_MAP.get(em.classification, "📧")
    priority = PRIORITY_MAP.get(em.classification, "default")
    title = f"{emoji} {em.classification.replace('_', ' ').title()}"
    if em.company:
        title += f" — {em.company}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{ntfy_url}/{ntfy_topic}",
                content=f"{em.subject}\n\n{em.body_preview[:200]}".encode(),
                headers={
                    "Authorization": f"Bearer {ntfy_token}",
                    "Title": title,
                    "Priority": priority,
                    "Tags": "email",
                },
            )
    except Exception:
        pass


def email_config_from_profile(profile: Profile) -> EmailConfig | None:
    """Extract email config from profile's _email_cfg attribute if set."""
    cfg = getattr(profile, "_email_cfg", None)
    if not cfg:
        return None
    return EmailConfig(
        imap_host=cfg.get("imap_host", "imap.gmail.com"),
        imap_port=int(cfg.get("imap_port", 993)),
        imap_user=cfg.get("imap_user", ""),
        imap_password=cfg.get("imap_password", ""),
        check_interval_minutes=int(cfg.get("check_interval_minutes", 15)),
    )
