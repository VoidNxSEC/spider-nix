"""SpiderNix - Enterprise Web Crawler for Public Data."""

__version__ = "0.2.0"

from .config import (
    AGGRESSIVE_CONFIG,
    API_SCRAPING_CONFIG,
    BALANCED_CONFIG,
    BROWSER_HEAVY_CONFIG,
    FAST_CONFIG,
    PRESETS,
    RESEARCH_CONFIG,
    STEALTH_CONFIG,
    CrawlerConfig,
    ProxyConfig,
    StealthConfig,
    get_preset,
    list_presets,
)
from .crawler import SpiderNix, quick_crawl
from .monitor import CrawlMonitor, CrawlStatistics
from .prioritizer import (
    BreadthFirstPrioritizer,
    DepthFirstPrioritizer,
    FocusedCrawlPrioritizer,
    LinkPrioritizer,
    PrioritizedLink,
)
from .rate_limiter import (
    AdaptiveRateLimiter,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    RequestDeduplicator,
)
from .report import HTMLReportGenerator, generate_report
from .session import CaptchaDetector, Session, SessionManager
from .wizard import ConfigurationWizard, run_wizard

# Multimodal extraction (Phase 1)
from .extraction import (
    BoundingBox,
    DOMAnalyzer,
    DOMElement,
    FusedElement,
    FusionEngine,
    VisionDetection,
    VisionExtractor,
)

# ML feedback system (Phase 1)
from .ml import (
    CrawlAttempt,
    FailureClass,
    FailureClassifier,
    FeedbackLogger,
    Strategy,
    StrategyEffectiveness,
    StrategySelector,
)

__all__ = [
    # Version
    "__version__",
    # Config
    "CrawlerConfig",
    "ProxyConfig",
    "StealthConfig",
    "AGGRESSIVE_CONFIG",
    "STEALTH_CONFIG",
    "BALANCED_CONFIG",
    "FAST_CONFIG",
    "API_SCRAPING_CONFIG",
    "BROWSER_HEAVY_CONFIG",
    "RESEARCH_CONFIG",
    "PRESETS",
    "get_preset",
    "list_presets",
    # Crawler
    "SpiderNix",
    "quick_crawl",
    # Rate Limiting
    "AdaptiveRateLimiter",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "RequestDeduplicator",
    # Monitoring
    "CrawlMonitor",
    "CrawlStatistics",
    # Prioritization
    "LinkPrioritizer",
    "PrioritizedLink",
    "BreadthFirstPrioritizer",
    "DepthFirstPrioritizer",
    "FocusedCrawlPrioritizer",
    # Reports
    "HTMLReportGenerator",
    "generate_report",
    # Session
    "Session",
    "SessionManager",
    "CaptchaDetector",
    # Wizard
    "ConfigurationWizard",
    "run_wizard",
    # Multimodal Extraction (Phase 1)
    "VisionExtractor",
    "DOMAnalyzer",
    "FusionEngine",
    "BoundingBox",
    "VisionDetection",
    "DOMElement",
    "FusedElement",
    # ML Feedback (Phase 1)
    "FeedbackLogger",
    "FailureClassifier",
    "StrategySelector",
    "CrawlAttempt",
    "FailureClass",
    "Strategy",
    "StrategyEffectiveness",
]
