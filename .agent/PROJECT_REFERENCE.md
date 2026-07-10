# Project Reference — Spider-Nix

## Project Purpose

Spider-Nix is a **local-first JobOps toolkit** for engineers and technical job seekers. It combines:

- Multi-source job scraping (Greenhouse, Lever, Ashby, RemoteOK, WeWorkRemotely, HackerNews)
- Smart matching engine (5-dimension scoring)
- Application pipeline tracking (CRM-like)
- Auto-fill system with confidence scoring
- OSINT reconnaissance suite
- Enterprise web crawler with anti-detection

## Architecture Overview

```
src/spider_nix/
├── cli.py          # Typer CLI — 70+ commands, ~2600 lines
├── crawler.py      # HTTP async crawler (httpx + asyncio)
├── browser.py      # Playwright browser crawler
├── stealth.py      # Anti-detection (canvas, WebGL, audio fingerprint spoofing)
├── proxy.py        # Proxy rotation (4 strategies)
├── rate_limiter.py # Adaptive rate limiter + circuit breaker + dedup
├── storage.py      # JSON/CSV/SQLite backends
├── config.py       # Pydantic config models + 7 presets
├── session.py      # Session mgmt + CAPTCHA detection
├── wizard.py       # Interactive config wizard (Rich)
├── monitor.py      # Real-time crawl monitoring
├── prioritizer.py  # URL prioritization
├── report.py       # Report generation
│
├── intel/          # Job Intelligence (core product)
│   ├── jobs.py         # Data models (JobOpportunity, Salary, enums)
│   ├── job_ats.py      # Greenhouse/Lever/Ashby scrapers
│   ├── job_scrapers.py # RemoteOK, WWR, HN scrapers
│   ├── job_matcher.py  # 5-dimension scoring engine
│   ├── job_storage.py  # SQLite + FTS5 persistence
│   ├── job_tracker.py  # Application pipeline (status transitions)
│   ├── form_filler.py  # Auto-fill + Live mode + confidence scoring
│   ├── resume_parser.py # PDF/DOCX/TXT extraction
│   ├── template_loader.py # YAML ATS template loader
│   └── templates/      # Greenhouse/Lever/Ashby YAML templates
│
├── server/         # Web GUI (FastAPI + Alpine.js + HTMX)
│   ├── __init__.py     # 18 routes + WebSocket
│   └── templates/      # hunt.html, pipeline.html, autofill.html, profile.html
│
├── osint/          # OSINT reconnaissance
│   ├── reconnaissance.py   # DNS, WHOIS, subdomains, cert transparency
│   ├── scanner.py          # Port scanner (TCP/UDP, banner grabbing)
│   ├── analyzer.py         # Tech detection (50+ frameworks)
│   ├── vulnerability.py    # Security headers, CVE matching
│   ├── integrations.py     # Shodan, VirusTotal, URLScan
│   ├── correlator.py       # Entity-relationship graph
│   ├── web_discovery.py    # GraphQL, Forms, Dirs, Well-Known
│   └── web_intelligence.py # Structured data, Sitemap, Robots, Archive
│
├── extraction/     # Multimodal extraction
│   ├── dom_analyzer.py, extractor.py, fusion_engine.py, models.py, vision_extractor.py
│
└── ml/             # ML feedback loop
    ├── failure_classifier.py, feedback_logger.py, models.py, strategy_selector.py, vision_client.py

network/            # Go network proxy (spider-network-proxy)
├── cmd/, internal/, go.mod, Makefile
```

## Important Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Python package config, deps, tooling (ruff, mypy, bandit, pytest) |
| `flake.nix` | NixOS reproducible dev environment |
| `justfile` | Task runner — wraps spider CLI commands |
| `spider_config.json` | Default crawler config |
| `uv.lock` | Locked Python deps (uv) |
| `jobs.db` | Default SQLite DB for job data |
| `docs/TODO.md` | Roadmap and quick wins |
| `docs/GUI_DESIGN.md` | Frontend architecture spec |
| `.github/workflows/` | 8 CI workflows (ci.yml, nix-build.yml, security.yml, etc.) |

## Build and Development Commands

```bash
# Enter dev environment
nix develop

# Run tests (214 tests — 183 offline + 19 integration)
spider test

# Run with coverage
spider test-cov

# Lint
spider check

# Format
spider fmt

# Typecheck
spider typecheck

# Security scan
spider security

# Full CI pipeline locally
spider ci-local

# Start web GUI
spider serve

# Alternative via uv
uv run pytest tests/
```

## Runtime Assumptions

- **Python**: >=3.11 (tested on 3.11, 3.12, 3.13)
- **Playwright**: requires `playwright install` or `PLAYWRIGHT_BROWSERS_PATH` set by Nix
- **Go proxy**: `network/spider-network-proxy` optional, for TLS fingerprint rotation
- **Browser**: Chromium/Firefox/WebKit via Playwright
- **Ports**: 8000 (web GUI), 8080 (Go proxy), 9000 (vision ML offload)
- **Secrets/API keys** (optional): Shodan, VirusTotal, URLScan

## Security Boundaries

- **Local-first**: All data in SQLite by default, no cloud dependency
- **Proxy**: Support for HTTP proxies, Go uTLS proxy for TLS fingerprinting
- **Stealth**: Canvas/WebGL/AudioContext fingerprint spoofing, navigator masking
- **Secrets**: Not stored in repo — placeholders in config
- **MITM**: Go proxy acts as MITM for TLS inspection, SSL verification disabled for localhost proxy
- **Input validation**: Present in form_filler and resume_parser

## Testing Strategy

- **214 tests** total: 183 offline + 19 integration + 12 misc
- `tests/conftest.py`: HTTPX mock auto-config, mock fixtures
- `tests/test_intel_jobs.py`: Extractor tests, model tests, scorer tests, profile tests
- `tests/test_cli.py`, `tests/test_crawler.py`: Core CLI and crawler tests
- `tests/test_stealth_engine.py`, `tests/test_stealth_detection.py`: Anti-detection tests
- `tests/test_osint_*.py`: OSINT module tests
- `tests/test_resume_parser_privacy.py`: Privacy-focused resume tests
- Integration markers: `@pytest.mark.integration`, `@pytest.mark.slow`

## Known Risks

- **Single-threaded CLI**: The CLI is a massive monolithic file (~2600 lines) — hard to maintain
- **Weak test isolation**: Some tests depend on external network (integration markers exist)
- **No API key rotation**: OSINT integrations use hardcoded key config
- **Go proxy binary**: Pre-built binary in repo (`network/spider-network-proxy`) — should be build artifact
- **Vision/ML disabled by default**: Phase 1C/1D features not battle-tested
- **No auth on web GUI**: FastAPI server has no authentication
- **Currency conversion hardcoded**: `job_matcher.py` has hardcoded exchange rates

## Agent Notes

- `AGENTS.md` in repo root defines the operating contract for AI agents
- `INIT.md` defines the local reference file convention
- `.agent/BACKLOG.md` should accumulate discovered issues
- All changes should be scoped, tested, and documented per AGENTS.md
