"""Configuration management for SpiderNix."""

from pydantic import BaseModel, Field
from typing import Literal


class ProxyConfig(BaseModel):
    """Proxy rotation configuration."""
    
    urls: list[str] = Field(default_factory=list)
    rotate_on_block: bool = True
    rotation_strategy: Literal["round_robin", "random", "least_used"] = "random"


class StealthConfig(BaseModel):
    """Anti-detection configuration."""
    
    randomize_user_agent: bool = True
    randomize_fingerprint: bool = True
    human_like_delays: bool = True
    min_delay_ms: int = 500
    max_delay_ms: int = 3000


class CrawlerConfig(BaseModel):
    """Main crawler configuration."""
    
    # Request settings
    max_requests_per_crawl: int = 1000
    max_concurrent_requests: int = 10
    request_timeout_ms: int = 30000
    
    # Retry settings
    max_retries: int = 5
    retry_on_status_codes: list[int] = Field(default_factory=lambda: [429, 500, 502, 503, 504])
    
    # Browser settings
    use_browser: bool = False
    headless: bool = True
    browser_type: Literal["chromium", "firefox", "webkit"] = "chromium"
    
    # Anti-detection
    stealth: StealthConfig = Field(default_factory=StealthConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    
    # Output
    output_format: Literal["json", "csv", "sqlite"] = "json"
    output_path: str = "output"


# Configuration Presets for Common Use Cases

AGGRESSIVE_CONFIG = CrawlerConfig(
    max_concurrent_requests=50,
    max_retries=10,
    stealth=StealthConfig(
        randomize_user_agent=True,
        randomize_fingerprint=True,
        human_like_delays=False,  # Faster
        min_delay_ms=100,
        max_delay_ms=500,
    ),
)

STEALTH_CONFIG = CrawlerConfig(
    max_requests_per_crawl=500,
    max_concurrent_requests=3,
    request_timeout_ms=45000,
    max_retries=8,
    retry_on_status_codes=[429, 500, 502, 503, 504],
    use_browser=True,
    headless=True,
    browser_type="chromium",
    stealth=StealthConfig(
        randomize_user_agent=True,
        randomize_fingerprint=True,
        human_like_delays=True,
        min_delay_ms=2000,
        max_delay_ms=5000,
    ),
)

BALANCED_CONFIG = CrawlerConfig(
    max_requests_per_crawl=1000,
    max_concurrent_requests=10,
    request_timeout_ms=30000,
    max_retries=5,
    stealth=StealthConfig(
        randomize_user_agent=True,
        randomize_fingerprint=True,
        human_like_delays=True,
        min_delay_ms=500,
        max_delay_ms=2000,
    ),
)

FAST_CONFIG = CrawlerConfig(
    max_requests_per_crawl=2000,
    max_concurrent_requests=30,
    request_timeout_ms=15000,
    max_retries=3,
    stealth=StealthConfig(
        randomize_user_agent=True,
        randomize_fingerprint=False,
        human_like_delays=False,
        min_delay_ms=50,
        max_delay_ms=200,
    ),
)

API_SCRAPING_CONFIG = CrawlerConfig(
    max_requests_per_crawl=5000,
    max_concurrent_requests=20,
    request_timeout_ms=20000,
    max_retries=5,
    retry_on_status_codes=[429, 500, 502, 503, 504],
    use_browser=False,
    stealth=StealthConfig(
        randomize_user_agent=True,
        randomize_fingerprint=False,
        human_like_delays=True,
        min_delay_ms=300,
        max_delay_ms=1000,
    ),
)

BROWSER_HEAVY_CONFIG = CrawlerConfig(
    max_requests_per_crawl=200,
    max_concurrent_requests=2,
    request_timeout_ms=60000,
    max_retries=3,
    use_browser=True,
    headless=True,
    browser_type="chromium",
    stealth=StealthConfig(
        randomize_user_agent=True,
        randomize_fingerprint=True,
        human_like_delays=True,
        min_delay_ms=3000,
        max_delay_ms=7000,
    ),
)

RESEARCH_CONFIG = CrawlerConfig(
    max_requests_per_crawl=10000,
    max_concurrent_requests=15,
    request_timeout_ms=40000,
    max_retries=7,
    stealth=StealthConfig(
        randomize_user_agent=True,
        randomize_fingerprint=True,
        human_like_delays=True,
        min_delay_ms=1000,
        max_delay_ms=3000,
    ),
    output_format="sqlite",
)

# Preset mapping for easy access
PRESETS = {
    "aggressive": AGGRESSIVE_CONFIG,
    "stealth": STEALTH_CONFIG,
    "balanced": BALANCED_CONFIG,
    "fast": FAST_CONFIG,
    "api": API_SCRAPING_CONFIG,
    "browser": BROWSER_HEAVY_CONFIG,
    "research": RESEARCH_CONFIG,
}


def get_preset(name: str) -> CrawlerConfig:
    """
    Get a configuration preset by name.

    Args:
        name: Preset name (aggressive, stealth, balanced, fast, api, browser, research)

    Returns:
        CrawlerConfig instance

    Raises:
        ValueError: If preset name is invalid
    """
    if name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise ValueError(
            f"Invalid preset '{name}'. Available presets: {available}"
        )
    return PRESETS[name]


def list_presets() -> dict[str, str]:
    """
    List all available presets with descriptions.

    Returns:
        Dict mapping preset name to description
    """
    return {
        "aggressive": "High-speed crawling with 50 concurrent requests, minimal delays",
        "stealth": "Maximum stealth with browser rendering, long delays, low concurrency",
        "balanced": "Default balanced configuration for general use",
        "fast": "Fast crawling with 30 concurrent requests, short timeouts",
        "api": "Optimized for API endpoint scraping without browser",
        "browser": "Heavy browser usage with JavaScript rendering, low concurrency",
        "research": "Large-scale research crawls with SQLite storage, high limits",
    }
