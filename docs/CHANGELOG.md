# Changelog

All notable changes to Spider-Nix will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

**Professional Job Intelligence System (v0.3.0)**

- **Multi-source job search**: Greenhouse, Lever, Ashby ATS scrapers + RemoteOK, WeWorkRemotely, HackerNews job boards
- **Smart matching engine**: 5-dimension scoring (skills 40%, seniority 20%, location 15%, salary 15%, title 10%)
- **Application pipeline tracker**: Full CRM with status transitions (saved→applied→phone_screen→technical→onsite→offer→accepted)
- **Auto-fill system**: Analyze HTML forms, match fields to profile with confidence scoring (0-100%)
- **Live interactive mode**: Playwright-based browser automation with visual feedback (green/yellow/red borders)
- **ATS template knowledge base**: External YAML templates for Greenhouse, Lever, Ashby (25 fields each, 150+ name variations)
- **Resume parser**: Extract name, email, phone, skills, experience, education from PDF/DOCX/TXT
- **Web GUI**: FastAPI + Alpine.js + Tailwind dashboard with 4 pages (Hunt, Pipeline, Auto-fill, Profile)
- **CLI improvements**: `spider job` subcommand group, `spider status` dashboard, shell completion
- **214 tests** (183 offline + 19 integration), zero breaking changes

### Changed

- Rewrote `intel/jobs.py` with professional data models (30+ fields, enums, Salary, CompanyProfile)
- Added confidence-based field matching replacing naive keyword matching
- Grouped job commands under `spider job` subcommand (hunt, track, profile, fill)
- Updated dev shell banner with new commands
- Type checking with mypy configuration
- Enhanced Justfile with new commands:
  - `just hooks-install` - Install pre-commit hooks
  - `just test-cov` - Run tests with coverage
  - `just typecheck` - Run type checking
  - `just security` - Run security scans
  - `just ci-local` - Simulate full CI locally
  - `just clean-all` - Clean including coverage artifacts
- Comprehensive documentation:
  - Complete README.md overhaul with badges, architecture diagram, and metrics
  - CONTRIBUTING.md with development guidelines
  - SECURITY.md with vulnerability reporting process
  - This CHANGELOG.md
  - MIT LICENSE file
- Enhanced Nix flake with dev tools (pytest-cov, mypy, bandit, pre-commit)
- Codecov configuration for coverage reporting
- Dependabot configuration for automated dependency updates

### Changed
- Enhanced pyproject.toml with comprehensive tool configurations
  - Added pytest coverage options and settings
  - Added mypy type checking configuration
  - Added bandit security scanning configuration
  - Added coverage.run and coverage.report settings
- Updated .gitignore with coverage, type checking, and security artifacts
- Improved development environment setup documentation

## [0.1.0] - 2026-01-15

### Added
- HTTP async crawler with httpx and asyncio
- Browser crawler with Playwright for JavaScript rendering
- Advanced anti-detection stealth techniques:
  - Canvas fingerprinting protection
  - WebGL vendor/renderer spoofing
  - Navigator properties masking
  - Screen resolution randomization
  - Automation detection bypass
- Intelligent proxy rotation engine with 4 strategies:
  - Round-robin
  - Random selection
  - Least-used
  - Best-performer (health-based)
- OSINT reconnaissance module:
  - DNS enumeration (7 record types)
  - WHOIS lookups
  - Subdomain discovery (Certificate Transparency + bruteforce)
- Port scanner with service detection:
  - Async TCP/UDP scanning
  - 25+ service signatures
  - Banner grabbing and version fingerprinting
  - Configurable concurrency (100 concurrent connections)
- Vulnerability scanner:
  - Security header analysis (HSTS, CSP, X-Frame-Options, etc.)
  - CVE matching for detected services
  - Misconfiguration detection
  - Security score calculation (0-100)
- Content analyzer:
  - Technology detection (Wappalyzer-style, 50+ frameworks/CMS)
  - Email/phone/social media harvesting
  - API endpoint discovery
  - Metadata extraction
- External API integrations:
  - Shodan client (host lookup, IP intelligence)
  - VirusTotal client (URL/domain/IP reputation)
  - URLScan.io client (scan submission and results)
- Correlation engine:
  - Entity-relationship graph building
  - Multi-source data aggregation
  - Graph export (JSON, Graphviz DOT)
  - Relationship querying
- Job intelligence module:
  - Career page discovery (subdomains + path-based)
  - Job opportunity analyzer
  - Seniority level detection (Junior/Mid/Senior/Staff)
  - Salary range extraction
  - Tech stack identification
- Storage backends:
  - JSON (JSONL format)
  - CSV (flattened export)
  - SQLite with FTS5 full-text search
- CLI with Typer and Rich:
  - `crawl` - Web crawling (HTTP/browser modes)
  - `recon dns` - DNS enumeration
  - `recon whois` - WHOIS lookups
  - `recon subdomains` - Subdomain discovery
  - `recon portscan` - Port scanning
  - `job-hunt` - Career opportunity discovery
  - `proxy-fetch` - Public proxy fetching
  - `proxy-stats` - Proxy validation
- Test suite with pytest and pytest-asyncio (63 test cases)
- NixOS flake for reproducible development environment
- Justfile for common development commands
- Configuration management with Pydantic models
- Basic README with project description and usage examples

[Unreleased]: https://github.com/VoidNxSEC/spider-nix/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/VoidNxSEC/spider-nix/releases/tag/v0.1.0
