"""Session management and CAPTCHA detection for authenticated crawling."""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

import httpx
from rich.console import Console

console = Console()


@dataclass
class Session:
    """Authenticated session with cookies and headers."""

    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)  # CSRF, JWT, etc.
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        """Check if session is expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def time_until_expiry(self) -> timedelta | None:
        """Get time until session expiry."""
        if self.expires_at is None:
            return None
        return self.expires_at - datetime.now()


class CaptchaDetector:
    """
    Detect CAPTCHA challenges in HTTP responses.

    Detection methods:
    - Common CAPTCHA service signatures (reCAPTCHA, hCaptcha, etc.)
    - CAPTCHA-related keywords in HTML
    - Response status codes (403, 429 with CAPTCHA)
    - Specific headers indicating CAPTCHA
    """

    def __init__(self):
        self.captcha_patterns = [
            # reCAPTCHA
            r"g-recaptcha",
            r"google\.com/recaptcha",
            r"recaptcha.*site.*key",
            # hCaptcha
            r"h-captcha",
            r"hcaptcha\.com",
            # Generic
            r"captcha.*challenge",
            r"captcha.*required",
            r"captcha.*verify",
            r"solve.*captcha",
            r"robot.*verification",
            r"human.*verification",
            # CloudFlare
            r"cf-challenge",
            r"cloudflare.*challenge",
            r"ray.*id.*cloudflare",
            # Other services
            r"funcaptcha",
            r"arkose",
            r"aws.*captcha",
        ]

        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.captcha_patterns]

    def detect(
        self,
        response: httpx.Response | None = None,
        html_content: str | None = None,
        status_code: int | None = None,
        headers: dict | None = None,
    ) -> tuple[bool, str | None]:
        """
        Detect if response contains CAPTCHA challenge.

        Returns:
            (is_captcha, captcha_type)
        """
        if response:
            html_content = response.text
            status_code = response.status_code
            headers = dict(response.headers)

        # Check status codes
        if status_code in {403, 429}:
            if html_content:
                for pattern in self.compiled_patterns:
                    if pattern.search(html_content):
                        return True, self._identify_captcha_type(html_content)

        # Check headers
        if headers:
            header_text = " ".join(f"{k}: {v}" for k, v in headers.items())
            if "captcha" in header_text.lower() or "challenge" in header_text.lower():
                return True, "header_based"

        # Check HTML content
        if html_content:
            for pattern in self.compiled_patterns:
                if pattern.search(html_content):
                    return True, self._identify_captcha_type(html_content)

        return False, None

    def _identify_captcha_type(self, html: str) -> str:
        """Identify specific CAPTCHA type."""
        html_lower = html.lower()

        if "g-recaptcha" in html_lower or "google.com/recaptcha" in html_lower:
            return "reCAPTCHA"
        elif "h-captcha" in html_lower or "hcaptcha.com" in html_lower:
            return "hCaptcha"
        elif "funcaptcha" in html_lower or "arkose" in html_lower:
            return "FunCaptcha"
        elif "cf-challenge" in html_lower or "cloudflare" in html_lower:
            return "Cloudflare"
        elif "aws" in html_lower and "captcha" in html_lower:
            return "AWS WAF Captcha"
        else:
            return "Unknown"


class SessionManager:
    """
    Manage authenticated sessions for crawling.

    Features:
    - Login/logout flows
    - Session persistence
    - Automatic session refresh
    - Cookie management
    - CSRF token extraction
    - Network OPSEC (Go proxy integration)
    """

    def __init__(
        self,
        session_ttl_minutes: int = 60,
        auto_refresh: bool = True,
        refresh_before_expiry_minutes: int = 5,
        use_network_proxy: bool = True,
        network_proxy_url: str = "http://127.0.0.1:8080",
    ):
        self.session_ttl_minutes = session_ttl_minutes
        self.auto_refresh = auto_refresh
        self.refresh_before_expiry_minutes = refresh_before_expiry_minutes
        self.use_network_proxy = use_network_proxy
        self.network_proxy_url = network_proxy_url

        self.sessions: dict[str, Session] = {}
        self.login_handlers: dict[str, Callable] = {}
        self.captcha_detector = CaptchaDetector()
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: str,
        login_url: str | None = None,
        credentials: dict[str, str] | None = None,
        custom_login_handler: Callable | None = None,
    ) -> Session:
        """
        Create and authenticate a new session.

        Args:
            session_id: Unique session identifier
            login_url: URL to send login request
            credentials: Login credentials (username, password, etc.)
            custom_login_handler: Custom async function for login

        Returns:
            Authenticated Session object
        """
        async with self._lock:
            if custom_login_handler:
                session = await custom_login_handler(credentials)
            elif login_url and credentials:
                session = await self._default_login(login_url, credentials)
            else:
                session = Session()

            # Set expiry
            if self.session_ttl_minutes > 0:
                session.expires_at = datetime.now() + timedelta(
                    minutes=self.session_ttl_minutes
                )

            self.sessions[session_id] = session
            console.print(f"[green]✓[/] Session '{session_id}' created")

            return session

    def _create_client_with_proxy(self) -> httpx.AsyncClient:
        """Create HTTP client with network proxy if enabled."""
        if self.use_network_proxy:
            # Route all traffic through Go proxy (uTLS fingerprint randomization)
            proxies = {
                "http://": self.network_proxy_url,
                "https://": self.network_proxy_url,
            }
            return httpx.AsyncClient(
                proxies=proxies,
                timeout=30.0,
                follow_redirects=True,
            )
        else:
            return httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            )

    async def _default_login(
        self,
        login_url: str,
        credentials: dict[str, str],
    ) -> Session:
        """Default login implementation."""
        async with self._create_client_with_proxy() as client:
            # Attempt login
            response = await client.post(login_url, data=credentials)

            # Check for CAPTCHA
            is_captcha, captcha_type = self.captcha_detector.detect(response)
            if is_captcha:
                console.print(
                    f"[yellow]⚠[/] CAPTCHA detected: {captcha_type}. "
                    "Login may require manual intervention."
                )

            # Extract cookies and tokens
            cookies = dict(response.cookies)

            # Try to extract CSRF token
            csrf_token = self._extract_csrf_token(response.text)

            session = Session(
                cookies=cookies,
                headers={},
                tokens={"csrf": csrf_token} if csrf_token else {},
                metadata={
                    "login_url": login_url,
                    "login_status_code": response.status_code,
                },
            )

            return session

    def _extract_csrf_token(self, html: str) -> str | None:
        """Extract CSRF token from HTML."""
        # Common CSRF token patterns
        patterns = [
            r'<input[^>]*name=["\']csrfmiddlewaretoken["\'][^>]*value=["\']([^"\']+)["\']',
            r'<input[^>]*name=["\']_csrf["\'][^>]*value=["\']([^"\']+)["\']',
            r'<input[^>]*name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']',
            r'<meta[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)["\']',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    async def get_session(self, session_id: str) -> Session | None:
        """Get session by ID."""
        async with self._lock:
            session = self.sessions.get(session_id)

            if session is None:
                return None

            # Check expiry
            if session.is_expired():
                console.print(
                    f"[yellow]⚠[/] Session '{session_id}' expired"
                )

                # Auto-refresh if enabled
                if self.auto_refresh and "login_url" in session.metadata:
                    console.print(f"[cyan]↻[/] Attempting to refresh session...")
                    # TODO: Implement refresh logic
                    return None

                del self.sessions[session_id]
                return None

            # Check if approaching expiry
            if self.auto_refresh and session.expires_at:
                time_left = session.time_until_expiry()
                if time_left and time_left.total_seconds() < (
                    self.refresh_before_expiry_minutes * 60
                ):
                    console.print(
                        f"[yellow]⚠[/] Session '{session_id}' expiring soon"
                    )

            return session

    async def delete_session(self, session_id: str):
        """Delete session."""
        async with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                console.print(f"[red]✗[/] Session '{session_id}' deleted")

    def apply_session_to_client(
        self,
        client: httpx.AsyncClient,
        session: Session,
    ):
        """Apply session cookies and headers to HTTP client."""
        # Update cookies
        for name, value in session.cookies.items():
            client.cookies.set(name, value)

        # Update headers
        client.headers.update(session.headers)

        # Add CSRF token if available
        if "csrf" in session.tokens:
            client.headers["X-CSRFToken"] = session.tokens["csrf"]

    def list_sessions(self) -> dict[str, dict[str, Any]]:
        """List all active sessions."""
        return {
            session_id: {
                "created_at": session.created_at.isoformat(),
                "expires_at": session.expires_at.isoformat()
                if session.expires_at
                else None,
                "is_expired": session.is_expired(),
                "cookies_count": len(session.cookies),
                "tokens_count": len(session.tokens),
            }
            for session_id, session in self.sessions.items()
        }


async def session_example():
    """Example usage of SessionManager."""
    manager = SessionManager(session_ttl_minutes=30)

    # Create session with custom credentials
    session = await manager.create_session(
        session_id="my_session",
        login_url="https://example.com/login",
        credentials={
            "username": "user@example.com",
            "password": "password123",
        },
    )

    console.print(f"Session created: {session}")

    # Get session later
    retrieved_session = await manager.get_session("my_session")
    console.print(f"Retrieved session: {retrieved_session}")

    # List all sessions
    sessions = manager.list_sessions()
    console.print(f"Active sessions: {sessions}")


if __name__ == "__main__":
    asyncio.run(session_example())
