# Spider-Nix Real Examples

Exemplos práticos usando as ferramentas de verdade.

## Setup

```bash
# Enter nix shell
nix develop

# Or use venv
source .venv/bin/activate
```

## Examples

### 1. Scrape Hacker News

Scraping real do HackerNews com extração DOM:

```bash
python examples/scrape_hackernews.py
```

**O que faz**:
- Fetches https://news.ycombinator.com com stealth
- Extrai título, links, metadata
- Parsing DOM com DOMAnalyzer
- Mostra top 10 stories

**Output esperado**:
```
🕸️  Spider-Nix - Real Scraping Demo
Target: news.ycombinator.com

📡 Fetching...
✓ Status: 200
✓ Size: 45231 bytes
✓ Time: 532ms

📰 Top Stories (30):
1. Show HN: I built a distributed database in Rust
   https://github.com/...
...
```

### 2. ML Feedback System

Sistema de feedback ML gravando dados reais:

```bash
python examples/ml_feedback_demo.py
```

**O que faz**:
- Testa múltiplos cenários (200, 429, 403, timeout)
- Classifica failures automaticamente
- Salva em SQLite database
- Aprende qual estratégia funciona por domain
- Mostra estatísticas reais

**Output esperado**:
```
🧠 Spider-Nix ML Feedback System Demo

🎯 Testing: https://httpbin.org/status/200
   Strategies: ['tls_fingerprint_rotation', 'headers_variation']
   Classification: success

🎯 Testing: https://httpbin.org/status/429
   Classification: rate_limit
   🔄 Should retry in 10000ms

📈 Statistics
Total attempts: 4
Success rate: 25.0%
Avg response time: 1234ms
...
```

**Database criado**:
```bash
# Query the database
sqlite3 demo_feedback.db 'SELECT * FROM crawl_attempts;'
sqlite3 demo_feedback.db 'SELECT * FROM strategy_effectiveness;'

# View schema
sqlite3 demo_feedback.db '.schema'
```

### 3. Stress Test

Testa rate limiter, circuit breaker, deduplication:

```bash
python examples/stress_test.py
```

**O que faz**:
- **Test 1**: 20 requests rápidos → rate limiter adapta delay
- **Test 2**: Trigger circuit breaker com 503 errors
- **Test 3**: 5x mesma URL → deduplication

**Output esperado**:
```
⚡ Spider-Nix Stress Test

🔥 Test 1: Rapid fire requests (20 requests)
  Successes: 18
  Failures: 2
  Current delay: 1247ms
  Success rate: 90.0%

🔌 Test 2: Circuit breaker
  [6/10] ⚠️  Circuit breaker OPEN
  ✓ Circuit breaker triggered successfully

🔄 Test 3: Deduplication
  Expected: 1 actual request, 4 deduplicated
  Actual: 1 request(s)
  ✓ Deduplication working
```

## Real Use Cases

### Scrape Product Prices

```python
from spider_nix import SpiderNix
from spider_nix.extraction import DOMAnalyzer

spider = SpiderNix()
results = await spider.crawl("https://example-store.com/product/123")

analyzer = DOMAnalyzer()
elements = analyzer.parse_html(results[0].content)

# Find price element
for elem in elements:
    if 'price' in elem.css_selector:
        print(f"Price: {elem.text_content}")
```

### Monitor API Status

```python
from spider_nix import SpiderNix
from spider_nix.ml import FeedbackLogger, FailureClassifier

logger = FeedbackLogger("api_health.db")
await logger.initialize()

classifier = FailureClassifier()

spider = SpiderNix()
results = await spider.crawl("https://api.example.com/health")

failure = classifier.classify(
    status_code=results[0].status_code,
    response_time_ms=results[0].fetch_duration_ms,
)

# Log to database for analytics
await logger.log_attempt(...)
```

### Distributed Web Archiving

```python
from spider_nix import SpiderNix
from spider_nix.ml import StrategySelector, FeedbackLogger

logger = FeedbackLogger("archive.db")
selector = StrategySelector(logger)

urls = load_urls_from_queue()

for url in urls:
    # Adaptive strategy per domain
    strategies = await selector.select_strategies(url)

    spider = SpiderNix()
    results = await spider.crawl(url)

    # Save to archive
    save_to_warc(results[0])
```

## Advanced

### Custom Stealth Script

```python
from spider_nix import SpiderNix
from spider_nix.stealth import StealthEngine

stealth = StealthEngine(seed=42)  # Reproducible fingerprints

# Generate custom JS
js = stealth.get_playwright_stealth_script()

# Use in Playwright (Phase 2)
# await page.evaluate(js)
```

### Proxy Rotation

```python
from spider_nix.proxy import ProxyRotator

# Load from file
rotator = ProxyRotator.from_file("proxies.txt")

# Or manual
rotator = ProxyRotator(
    proxies=[
        "http://proxy1:8080",
        "http://proxy2:8080",
    ],
    strategy="best_performer"  # or round_robin, random, least_used
)

spider = SpiderNix(proxy_rotator=rotator)
```

### Go uTLS Proxy (Phase 1 - WIP)

```python
from spider_nix.proxy import ProxyRotator

# Use local Go proxy for TLS fingerprint randomization
rotator = ProxyRotator.with_network_proxy("http://localhost:8080")

spider = SpiderNix(proxy_rotator=rotator)
# All requests will route through Go proxy with randomized TLS
```

## Performance Tips

1. **Enable all protections**: Circuit breaker prevents wasted requests
2. **Use deduplication**: Avoids re-fetching same URLs
3. **Tune delays**: Balance speed vs detection risk
4. **Monitor feedback DB**: Learn which strategies work

## Troubleshooting

**Import errors**:
```bash
# Make sure you're in nix shell or venv
nix develop
# OR
source .venv/bin/activate
```

**Database locked**:
```bash
# Close all sqlite connections
rm demo_feedback.db
python examples/ml_feedback_demo.py
```

**Slow requests**:
- Check `config.request_timeout_seconds`
- Reduce `config.stealth.max_delay_ms`
- Disable adaptive rate limiting for speed

## Next Steps

- Read `PHASE1_IMPLEMENTATION.md` for architecture details
- Check `src/spider_nix/` for full API
- Phase 2: Playwright integration, Prefect workflows
