# Spider-Nix 🕷️

<div align="center">

[![CI Pipeline](https://github.com/VoidNxSEC/spider-nix/workflows/CI%20Pipeline/badge.svg)](https://github.com/VoidNxSEC/spider-nix/actions)
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Nix](https://img.shields.io/badge/builtwith-nix-5277C3.svg?logo=nixos)](https://nixos.org)

**Professional Job Hunt Toolkit — find, match, track, and auto-fill job applications**

[Quick Start](#quick-start) • [Job Hunt](#-job-hunt) • [Auto-Fill](#-auto-fill) • [Web GUI](#-web-gui) • [Architecture](#-architecture)

</div>

---

## What is this?

Spider-Nix is a **complete job search automation system**. It finds jobs across multiple sources, scores them against your profile, tracks your application pipeline, and can even auto-fill application forms in your browser.

- **🔍 Multi-source job search**: Greenhouse, Lever, Ashby, RemoteOK, WeWorkRemotely, HackerNews
- **🎯 Smart matching**: 5-dimension scoring (skills, seniority, location, salary, title)
- **📊 Pipeline tracking**: Full CRM for your job hunt (saved → applied → interviewed → offer)
- **🤖 Auto-fill forms**: Analyze any application form, match fields to your profile with confidence scoring
- **🖥️ Live mode**: Open browser, fill forms interactively with visual feedback
- **📄 Resume parser**: Auto-extract name, email, skills, experience from PDF/DOCX/TXT
- **🌐 Web GUI**: FastAPI + Alpine.js dashboard (zero node_modules)

---

## Quick Start

```bash
# Clone & enter environment
git clone https://github.com/VoidNxSEC/spider-nix.git && cd spider-nix
nix develop

# Set up your profile (or auto-extract from resume)
spider job profile --from-resume curriculo.pdf

# Search for jobs
spider job hunt --skills 'python,rust,nix,kubernetes' --save-db vagas.db

# Track applications
spider job track --summary

# Auto-fill an application form (interactive live mode)
spider job fill https://jobs.lever.co/company/position --live --use-chrome

# Launch web GUI
spider serve
```

---

## 💼 Job Hunt

```bash
# Search job boards by skills
spider job hunt --skills 'python,rust,kubernetes' --max 100

# Search with full filters
spider job hunt --skills 'go,k8s' --titles 'Platform Engineer,SRE' \
  --remote remote_only --min-salary 120000 --seniority senior

# Target a specific company's ATS
spider job hunt stripe.com --skills 'rust'

# Save results to database for tracking
spider job hunt --skills 'python,rust' --save-db vagas.db --max 200
```

### Sources:

| Source | Type | Method |
|--------|------|--------|
| **Greenhouse** | ATS API | `boards.greenhouse.io/{company}/embed/job_board` |
| **Lever** | ATS API | `jobs.lever.co/{company}?format=json` |
| **Ashby** | ATS API | `jobs.ashbyhq.com/{company}/api/jobs` |
| **RemoteOK** | Job Board | `remoteok.com/api?tag=rust` |
| **WeWorkRemotely** | Job Board | HTML + RSS parsing |
| **HackerNews** | Community | "Who is hiring?" monthly thread |

### Matching Engine:

Jobs are scored 0-100 across 5 dimensions:

| Dimension | Weight | What it checks |
|-----------|--------|----------------|
| Skills | 40pts | Overlap between your skills and job requirements |
| Seniority | 20pts | Alignment with your experience level |
| Location | 15pts | Remote/hybrid/onsite preference match |
| Salary | 15pts | Whether salary meets your minimum |
| Title | 10pts | Role title matches your desired titles |

---

## 🤖 Auto-Fill

```bash
# Analyze a form (shows confidence per field)
spider job fill https://jobs.lever.co/company/position --profile me.json

# Live interactive mode — opens browser, fills forms, pauses for review
spider job fill https://jobs.lever.co/company/position --profile me.json --live

# Use your Chrome profile (cookies, sessions, logins)
spider job fill <url> --profile me.json --live --use-chrome \
  --chrome-profile ~/.config/google-chrome
```

### How it works:

1. **Analyzes** the HTML form using `FormAnalyzer`
2. **Detects** the ATS platform (Greenhouse, Lever, Ashby, etc.)
3. **Matches** each field to your profile using ATS-specific templates + label text
4. **Scores** every match with confidence (0-100%)
5. **Fills** high-confidence fields automatically
6. **Highlights** medium/low confidence fields for manual review
7. In **live mode**: injects visual feedback (green/yellow/red borders) into the browser

### Confidence Scoring:

| Level | Threshold | Behavior |
|-------|-----------|----------|
| 🟢 High | >80% | Auto-filled, green border |
| 🟡 Medium | 50-80% | Auto-filled, yellow border — review recommended |
| 🔴 Low | 30-50% | Not filled, red border — manual input needed |
| ⚫ None | <30% | Ignored |

### ATS Templates (YAML):

```yaml
# templates/greenhouse.yaml — 25 fields, 150+ name variations
platform: greenhouse
url_patterns: [boards.greenhouse.io]
fields:
  first_name: [first_name, firstName, candidate_first_name, given_name]
  email: [email, candidate_email, email_address, candidateEmail]
  resume_path: [resume, resume_upload, attachments[0], resumeFile]
  ...
```

Templates available for **Greenhouse**, **Lever**, **Ashby**, **Workday** — extensible via YAML files in `src/spider_nix/intel/templates/`.

---

## 📊 Pipeline Tracking

```bash
# View dashboard
spider job track --summary

# List by status
spider job track --list applied
spider job track --list phone_screen

# Update status
spider job track --id abc123 --status applied --notes "CV + cover letter sent"
spider job track --id abc123 --status interview --notes "Scheduled Friday 2pm"

# Export
spider job track --export applications.json
```

### Pipeline stages:

```
saved → applied → phone_screen → technical → onsite → offer → accepted
                    ↓              ↓          ↓        ↓
                  rejected      rejected    rejected  rejected
```

---

## 🌐 Web GUI

```bash
spider serve                 # Opens browser at localhost:8000
spider serve --port 3000     # Custom port
```

### Pages:

| Page | What it does |
|------|-------------|
| **🔍 Hunt** | Search jobs with live progress, view scored results, export JSON |
| **📊 Pipeline** | Kanban-style cards, filter by stage, update status inline |
| **🤖 Auto-fill** | Paste application URL, see field-by-field confidence analysis |
| **👤 Profile** | Manage skills, salary, remote preferences; upload resume |

### Tech stack:

- **Backend**: FastAPI (async, WebSocket, 18 routes)
- **Frontend**: Alpine.js + HTMX (reactive, zero build step)
- **CSS**: Tailwind CSS (via CDN)
- **Real-time**: WebSocket for live hunt progress

---

## 📄 Resume Parser

```bash
spider job profile --from-resume curriculo.pdf
```

Auto-extracts: **name**, **email**, **phone**, **LinkedIn**, **GitHub**, **skills** (40+ tech keywords), **years of experience**, **current title/company**, **education**.

Supports: PDF (pypdf/pdfplumber), DOCX (native XML parsing), TXT.

---

## 🏗️ Architecture

```
spider-nix/
├── src/spider_nix/
│   ├── cli.py                   # Typer CLI — 60+ commands
│   ├── crawler.py               # HTTP crawler (httpx + asyncio)
│   ├── browser.py               # Playwright browser crawler
│   ├── stealth.py               # Anti-detection (fingerprint, canvas, WebGL)
│   ├── proxy.py                 # Proxy rotation (4 strategies)
│   ├── storage.py               # JSON / CSV / SQLite backends
│   ├── config.py                # Pydantic configuration models
│   │
│   ├── osint/                   # OSINT reconnaissance
│   │   ├── reconnaissance.py    # DNS, WHOIS, subdomains, cert transparency
│   │   ├── scanner.py           # Port scanner (TCP/UDP, banner grabbing)
│   │   ├── analyzer.py          # Tech detection (50+ frameworks)
│   │   ├── vulnerability.py     # Security headers, CVE matching
│   │   ├── integrations.py      # Shodan, VirusTotal, URLScan
│   │   ├── correlator.py        # Entity-relationship graph
│   │   ├── web_discovery.py     # GraphQL, Forms, Dirs, Well-Known
│   │   └── web_intelligence.py  # Structured data, Sitemap, Robots, Archive
│   │
│   ├── intel/                   # Job intelligence (NEW)
│   │   ├── jobs.py              # Data models (JobOpportunity, Salary, enums)
│   │   ├── job_ats.py           # ATS scrapers (Greenhouse, Lever, Ashby)
│   │   ├── job_scrapers.py      # Job boards (RemoteOK, WWR, HN)
│   │   ├── job_matcher.py       # 5-dimension scoring engine
│   │   ├── job_storage.py       # SQLite + FTS5 persistence
│   │   ├── job_tracker.py       # Application pipeline tracking
│   │   ├── form_filler.py       # Auto-fill + Live mode + confidence scoring
│   │   ├── resume_parser.py     # PDF/DOCX/TXT resume extraction
│   │   ├── template_loader.py   # YAML ATS template system
│   │   └── templates/           # ATS field templates (YAML)
│   │       ├── greenhouse.yaml
│   │       ├── lever.yaml
│   │       └── ashby.yaml
│   │
│   └── server/                  # Web GUI (FastAPI)
│       ├── __init__.py          # 18 routes + WebSocket
│       └── templates/           # HTML pages
│           ├── base.html
│           ├── hunt.html
│           ├── pipeline.html
│           ├── autofill.html
│           └── profile.html
│
├── tests/                       # 214 tests (183 offline + 19 integration)
├── flake.nix                    # NixOS reproducible environment
├── pyproject.toml               # Python package config
└── justfile                     # Dev shortcuts
```

---

## Key Design Patterns

| Pattern | Where | Why |
|---------|-------|-----|
| **Async/Await** | Everywhere | Non-blocking I/O for scraping, DNS, HTTP |
| **Strategy** | ProxyRotator | 4 interchangeable rotation strategies |
| **Circuit Breaker** | RateLimiter | Protects against failing endpoints |
| **Factory** | Storage backends | JSON/CSV/SQLite via single interface |
| **Template Method** | ATS scrapers | Each platform has same interface, different parser |
| **Observer** | CrawlMonitor, WebSocket | Real-time progress streaming |
| **Repository** | JobStorage | Abstract CRUD over SQLite + FTS5 |
| **Confidence Scoring** | FieldMatcher | Multi-strategy field matching with weighted confidence |

---

## Testing

```bash
spider test              # 214 tests (offline, <30s)
spider test-cov          # With coverage report
pytest -m "integration"  # Integration tests (requires network)
```

---

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) and [TODO.md](docs/TODO.md) for the roadmap.

---

<div align="center">
<b>Built for developers who want to automate their job search.</b><br>
<sub>Python 3.13 · asyncio · Playwright · FastAPI · NixOS · SQLite</sub>
</div>
