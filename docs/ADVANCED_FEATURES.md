# 🚀 SpiderNix Advanced Features

Version 0.2.0 introduces enterprise-grade features for advanced crawling, monitoring, and UX improvements.

## 📋 Table of Contents

1. [Adaptive Rate Limiting](#adaptive-rate-limiting)
2. [Circuit Breaker Pattern](#circuit-breaker-pattern)
3. [Request Deduplication](#request-deduplication)
4. [Real-time Monitoring](#real-time-monitoring)
5. [Smart Link Prioritization](#smart-link-prioritization)
6. [Configuration Presets](#configuration-presets)
7. [Interactive Wizard](#interactive-wizard)
8. [HTML Report Generation](#html-report-generation)
9. [CAPTCHA Detection](#captcha-detection)
10. [Session Management](#session-management)
11. [CLI Commands](#cli-commands)

---

## 🎯 Adaptive Rate Limiting

Automatically adjusts request rate based on server responses to avoid blocks and optimize crawl speed.

### Features
- **Backpressure Detection**: Detects when server is under load (429, 503 responses, slow response times)
- **Dynamic Adjustment**: Increases delay when blocked, decreases when server responds well
- **Configurable Thresholds**: Customize min/max delays and adjustment factors

### Usage

```python
from spider_nix import SpiderNix, CrawlerConfig

config = CrawlerConfig()
crawler = SpiderNix(
    config=config,
    enable_adaptive_rate_limiting=True,  # Enable adaptive rate limiting
)

results = await crawler.crawl("https://example.com", max_pages=100)

# Check rate limiter stats
if crawler.rate_limiter:
    stats = crawler.rate_limiter.get_stats()
    print(f"Current delay: {stats.current_delay_ms}ms")
    print(f"Backpressure detected: {stats.backpressure_detected}")
```

### CLI Usage

```bash
# Adaptive rate limiting is enabled by default in advanced-crawl
spider-nix advanced-crawl https://example.com --pages 100
```

---

## ⚡ Circuit Breaker Pattern

Prevents cascading failures by temporarily stopping requests to failing servers.

### Features
- **3 States**: Closed (normal), Open (failing), Half-Open (testing recovery)
- **Automatic Recovery**: Tests server health after timeout
- **Configurable Thresholds**: Customize failure counts and timeout periods

### Usage

```python
from spider_nix import SpiderNix, CircuitBreakerConfig

# Configure circuit breaker
cb_config = CircuitBreakerConfig(
    failure_threshold=5,  # Open after 5 failures
    success_threshold=2,  # Close after 2 successes in half-open
    timeout_seconds=60.0,  # Wait 60s before testing recovery
)

crawler = SpiderNix(
    enable_circuit_breaker=True,
)

# Circuit breaker automatically protects requests
results = await crawler.crawl("https://example.com")

# Check state
if crawler.circuit_breaker:
    print(f"Circuit state: {crawler.circuit_breaker.get_state()}")
```

### States

- **CLOSED**: Normal operation, all requests allowed
- **OPEN**: Too many failures, requests rejected immediately
- **HALF_OPEN**: Testing recovery with limited requests

---

## 🔄 Request Deduplication

Prevents crawling duplicate URLs and content, saving bandwidth and time.

### Features
- **URL Normalization**: Sorts query params, removes fragments, normalizes domains
- **Content Hashing**: Detects duplicate content even with different URLs
- **TTL Cache**: Automatically expires old entries
- **Memory Efficient**: Limits cache size

### Usage

```python
from spider_nix import SpiderNix

crawler = SpiderNix(
    enable_deduplication=True,  # Enable deduplication
)

results = await crawler.crawl("https://example.com", follow_links=True)

# Check deduplication stats
if crawler.deduplicator:
    stats = crawler.deduplicator.get_stats()
    print(f"URLs cached: {stats['url_cache_size']}")
    print(f"Content cached: {stats['content_cache_size']}")
```

### URL Normalization Example

```python
from spider_nix import RequestDeduplicator

dedup = RequestDeduplicator()

# These are considered the same:
url1 = "https://example.com/page?b=2&a=1#section"
url2 = "https://example.com/page?a=1&b=2"

normalized1 = dedup.normalize_url(url1)
normalized2 = dedup.normalize_url(url2)
# Both become: "https://example.com/page?a=1&b=2"
```

---

## 📊 Real-time Monitoring

Beautiful terminal UI showing live crawl statistics and progress.

### Features
- **Live Progress Bar**: Shows crawl completion in real-time
- **Overview Stats**: Total requests, success rate, speed
- **Performance Metrics**: Response times, rate limiting status
- **Status Code Distribution**: Visual breakdown of HTTP responses
- **Response Time Buckets**: Histogram of response time distribution

### Usage

```python
from spider_nix import SpiderNix, CrawlMonitor

monitor = CrawlMonitor(max_pages=100, show_live=True)
monitor.start()

try:
    crawler = SpiderNix()
    results = await crawler.crawl("https://example.com")

    # Update monitor with results
    for result in results:
        monitor.update(
            url=result.url,
            status_code=result.status_code,
            response_time_ms=result.metadata.get("elapsed_ms", 0),
            success=200 <= result.status_code < 300,
        )
finally:
    monitor.stop()
    monitor.print_summary()
```

### CLI Usage

```bash
# Monitoring enabled by default
spider-nix advanced-crawl https://example.com --pages 100 --monitor
```

### Display Panels

1. **Overview Panel**: Total requests, success rate, duplicates
2. **Performance Panel**: Response times, backpressure, circuit state
3. **Status Codes Panel**: Top 10 status codes with visual bars

---

## 🎯 Smart Link Prioritization

Intelligent link ordering for focused and efficient crawling.

### Features
- **Pattern-based Scoring**: Prioritize URLs matching patterns (e.g., `/api/`, `/docs/`)
- **Keyword Scoring**: Boost priority for relevant keywords
- **Depth Control**: Prioritize shallow or deep links
- **Multiple Strategies**: Breadth-first, depth-first, or focused crawling

### Usage

```python
from spider_nix import LinkPrioritizer

# Create custom prioritizer
prioritizer = LinkPrioritizer(
    pattern_scores={
        r"/api/": 10.0,      # High priority for API endpoints
        r"/docs/": 8.0,      # High priority for documentation
        r"/blog/": 2.0,      # Lower priority for blog posts
    },
    keyword_scores={
        "documentation": 5.0,
        "tutorial": 4.0,
    },
    depth_penalty=0.5,  # Penalize deep links
)

# Add links
await prioritizer.add_link("https://example.com/api/v1", depth=1)
await prioritizer.add_link("https://example.com/blog/post", depth=1)

# Get next highest-priority link
link = await prioritizer.get_next_link()
print(f"Crawl next: {link.url} (priority: {-link.priority:.2f})")
```

### Preset Prioritizers

```python
from spider_nix import (
    BreadthFirstPrioritizer,    # Shallow links first
    DepthFirstPrioritizer,      # Deep links first
    FocusedCrawlPrioritizer,    # Keyword-focused
)

# Breadth-first crawling
prioritizer = BreadthFirstPrioritizer()

# Focused on API documentation
prioritizer = FocusedCrawlPrioritizer(
    focus_keywords=["api", "documentation", "reference"]
)
```

---

## ⚙️ Configuration Presets

Pre-configured settings for common use cases.

### Available Presets

| Preset | Description | Best For |
|--------|-------------|----------|
| `balanced` | Default balanced configuration | General purpose |
| `aggressive` | 50 concurrent, minimal delays | Fast scraping |
| `stealth` | Browser mode, long delays, low concurrency | Avoiding detection |
| `fast` | 30 concurrent, short timeouts | Quick scans |
| `api` | Optimized for API endpoints | REST API scraping |
| `browser` | Heavy browser usage, JavaScript | Dynamic sites |
| `research` | High limits, SQLite storage | Large-scale research |

### Usage

```python
from spider_nix import get_preset, SpiderNix

# Load preset
config = get_preset("stealth")

# Customize if needed
config.max_requests_per_crawl = 500

# Use with crawler
crawler = SpiderNix(config=config)
```

### CLI Usage

```bash
# List presets
spider-nix presets

# Use preset
spider-nix advanced-crawl https://example.com --preset stealth --pages 100
```

### Preset Details

#### Aggressive
```python
max_concurrent_requests: 50
max_retries: 10
human_like_delays: False
min_delay_ms: 100
max_delay_ms: 500
```

#### Stealth
```python
max_concurrent_requests: 3
use_browser: True
human_like_delays: True
min_delay_ms: 2000
max_delay_ms: 5000
```

---

## 🧙 Interactive Wizard

Guided configuration setup with interactive prompts.

### Features
- **Preset Selection**: Start from a preset or build from scratch
- **Step-by-step Customization**: Configure basic, stealth, proxy, browser, and output settings
- **Rich UI**: Beautiful terminal interface with tables and panels
- **Config Export**: Save configuration to JSON file

### Usage

```bash
# Run wizard
spider-nix wizard

# Follow interactive prompts:
# 1. Choose preset or start from scratch
# 2. Customize basic settings (pages, concurrency, timeouts)
# 3. Configure stealth settings
# 4. Setup proxies
# 5. Configure browser options
# 6. Choose output format
# 7. Review and save
```

### Programmatic Usage

```python
from spider_nix import run_wizard

# Run interactive wizard
config = run_wizard()

# Use the config
crawler = SpiderNix(config=config)
```

---

## 📈 HTML Report Generation

Generate beautiful HTML reports with charts and visualizations.

### Features
- **Interactive Charts**: Status codes, response times, timeline (Chart.js)
- **Summary Statistics**: Success rate, avg response time, total requests
- **Results Table**: Detailed view of crawled URLs
- **Responsive Design**: Works on all screen sizes
- **Professional Styling**: Gradient backgrounds, hover effects

### Usage

```python
from spider_nix import generate_report, SpiderNix

# Crawl
crawler = SpiderNix()
results = await crawler.crawl("https://example.com")

# Generate report
report_path = generate_report(
    results=results,
    output_path="crawl_report.html",
    title="My Crawl Report",
)

print(f"Report saved to: {report_path}")
```

### CLI Usage

```bash
# Generate report during crawl
spider-nix advanced-crawl https://example.com \
    --pages 100 \
    --report \
    --report-path report.html

# Generate report from existing results
spider-nix generate-html-report results.json \
    --output report.html \
    --title "My Crawl Report"
```

### Report Sections

1. **Summary**: Overview statistics with color-coded metrics
2. **Status Code Distribution**: Bar chart of HTTP status codes
3. **Response Time Distribution**: Histogram of response times
4. **Requests Timeline**: Line chart showing requests over time
5. **Crawl Results**: Detailed table of URLs with metadata

---

## 🔍 CAPTCHA Detection

Automatically detect CAPTCHA challenges during crawling.

### Supported CAPTCHAs
- Google reCAPTCHA
- hCaptcha
- FunCaptcha / Arkose Labs
- Cloudflare Challenge
- AWS WAF Captcha
- Generic CAPTCHA patterns

### Usage

```python
from spider_nix import CaptchaDetector

detector = CaptchaDetector()

# Detect from response
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get("https://example.com")

    is_captcha, captcha_type = detector.detect(response=response)

    if is_captcha:
        print(f"CAPTCHA detected: {captcha_type}")
        # Handle CAPTCHA (pause, notify, solve, etc.)
```

### Detection Methods

1. **Status Codes**: 403, 429 with CAPTCHA indicators
2. **HTML Patterns**: Common CAPTCHA service signatures
3. **Headers**: CAPTCHA-related response headers
4. **Keywords**: Challenge, verification, robot detection

---

## 🔐 Session Management

Manage authenticated sessions for crawling protected content.

### Features
- **Login Automation**: Automated login with credentials
- **Cookie Management**: Persist and rotate cookies
- **CSRF Token Extraction**: Automatically extract and use CSRF tokens
- **Session Expiry**: Automatic session refresh
- **Multi-session Support**: Manage multiple authenticated sessions

### Usage

```python
from spider_nix import SessionManager

manager = SessionManager(
    session_ttl_minutes=60,      # Session expires after 60 min
    auto_refresh=True,           # Auto-refresh before expiry
)

# Create session with login
session = await manager.create_session(
    session_id="my_session",
    login_url="https://example.com/login",
    credentials={
        "username": "user@example.com",
        "password": "password123",
    },
)

# Apply session to HTTP client
import httpx
async with httpx.AsyncClient() as client:
    manager.apply_session_to_client(client, session)

    # Now all requests use authenticated session
    response = await client.get("https://example.com/protected")

# List active sessions
sessions = manager.list_sessions()
```

### Custom Login Handler

```python
async def custom_login(credentials):
    # Implement custom login logic
    async with httpx.AsyncClient() as client:
        # Step 1: Get login page
        response = await client.get("https://example.com/login")

        # Step 2: Submit login form with CSRF token
        csrf_token = extract_csrf(response.text)
        response = await client.post(
            "https://example.com/login",
            data={
                **credentials,
                "csrf_token": csrf_token,
            }
        )

        return Session(
            cookies=dict(response.cookies),
            tokens={"csrf": csrf_token},
        )

# Use custom login
session = await manager.create_session(
    session_id="custom",
    custom_login_handler=custom_login,
    credentials={"username": "user", "password": "pass"},
)
```

---

## 💻 CLI Commands

### New Commands

#### `wizard`
Interactive configuration wizard
```bash
spider-nix wizard
```

#### `presets`
List available configuration presets
```bash
spider-nix presets
```

#### `advanced-crawl`
Advanced crawl with all features enabled
```bash
spider-nix advanced-crawl https://example.com \
    --pages 100 \
    --preset stealth \
    --follow \
    --monitor \
    --report \
    --output results.json
```

**Options:**
- `--preset`: Use configuration preset
- `--pages`: Max pages to crawl
- `--follow`: Follow links
- `--monitor`: Show live monitoring (default: true)
- `--report`: Generate HTML report
- `--report-path`: Path to save HTML report
- `--output`: Output file path
- `--format`: Output format (json, csv, sqlite)

#### `generate-html-report`
Generate HTML report from existing results
```bash
spider-nix generate-html-report results.json \
    --output report.html \
    --title "My Crawl Report"
```

### Updated Commands

#### `crawl` (legacy)
Standard crawl command (still available for backward compatibility)
```bash
spider-nix crawl https://example.com --pages 10
```

---

## 🔧 Programmatic API

### Complete Example

```python
import asyncio
from spider_nix import (
    SpiderNix,
    get_preset,
    CrawlMonitor,
    generate_report,
)

async def advanced_crawl():
    # Load preset config
    config = get_preset("balanced")
    config.max_requests_per_crawl = 100

    # Initialize crawler with all features
    crawler = SpiderNix(
        config=config,
        enable_adaptive_rate_limiting=True,
        enable_circuit_breaker=True,
        enable_deduplication=True,
    )

    # Setup monitoring
    monitor = CrawlMonitor(max_pages=100, show_live=True)
    monitor.start()

    try:
        # Crawl
        results = await crawler.crawl(
            "https://example.com",
            max_pages=100,
            follow_links=True,
        )

        # Update monitor
        for result in results:
            monitor.update(
                url=result.url,
                status_code=result.status_code,
                response_time_ms=result.metadata.get("elapsed_ms", 0),
                success=200 <= result.status_code < 300,
            )

        # Print stats
        monitor.print_summary()

        # Generate report
        report_path = generate_report(
            results=results,
            stats=monitor.stats,
            title="Advanced Crawl Report",
        )

        print(f"Report: {report_path}")

        return results

    finally:
        monitor.stop()

# Run
results = asyncio.run(advanced_crawl())
```

---

## 📚 Additional Resources

- [Main README](README.md) - Project overview and installation
- [CHANGELOG](CHANGELOG.md) - Version history
- [CONTRIBUTING](CONTRIBUTING.md) - Contribution guidelines
- [API Documentation](docs/) - Full API reference

---

## 🆕 What's New in v0.2.0

### Advanced Crawling
- ✅ Adaptive rate limiting with backpressure detection
- ✅ Circuit breaker pattern for fault tolerance
- ✅ Request deduplication (URL + content)
- ✅ Smart link prioritization with scoring

### UX Improvements
- ✅ Real-time monitoring with rich UI
- ✅ HTML report generation with charts
- ✅ Interactive configuration wizard
- ✅ 7 configuration presets

### Security & Authentication
- ✅ CAPTCHA detection (reCAPTCHA, hCaptcha, etc.)
- ✅ Session management for authenticated crawling
- ✅ Cookie and CSRF token handling

### Developer Experience
- ✅ Enhanced CLI with new commands
- ✅ Comprehensive API documentation
- ✅ Type-safe interfaces with Pydantic
- ✅ Better error messages and logging

---

## 🚀 Performance Comparison

| Feature | v0.1.0 | v0.2.0 |
|---------|--------|--------|
| Rate Limiting | Fixed delays | Adaptive (dynamic) |
| Deduplication | None | URL + Content |
| Monitoring | Basic console logs | Real-time rich UI |
| Reports | JSON/CSV only | HTML with charts |
| Configuration | Manual code | Presets + Wizard |
| Circuit Breaker | None | ✅ 3-state pattern |
| Link Priority | FIFO queue | Smart scoring |

---

## 📝 License

MIT License - See [LICENSE](LICENSE) for details

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

---

**Built with ❤️ using Python, httpx, Playwright, Rich, and Chart.js**
