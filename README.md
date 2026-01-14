# spider-nix

Web crawler + OSINT toolkit. Daily workflow tool for reconnaissance and data collection.

## Stack

- Python 3.13 + asyncio
- httpx/Playwright for crawling
- aiodns, pycares, python-whois for OSINT
- SQLite FTS5 for data storage
- NixOS environment

## Quick Start

```bash
nix develop
just install
```

## Commands

### Crawling

```bash
spider-nix crawl <url> [--browser] [--pages N] [--follow] [--aggressive]
spider-nix crawl <url> --output results.db --format sqlite
spider-nix crawl <url> --proxy-file proxies.txt
```

### Reconnaissance

````bash
# DNS
spider-nix recon dns <domain>
spider-nix recon dns <domain> --type MX
spider-nix recon dns --reverse <ip>

# WHOIS
spider-nix recon whois <domain>

# Subdomains
spider-nix recon subdomains <domain> -o subdomains.json
spider-nix recon subdomains <domain> --no-bruteforce  # CRT only
spider-nix recon subdomains <domain> -w wordlist.txt -c 100

# Port Scanning
spider-nix recon portscan <target>                      # common ports
spider-nix recon portscan <target> -p 80,443,8080       # specific ports
spider-nix recon portscan <target> -p 1-1000            # port range
spider-nix recon portscan <target> --protocol both      # TCP + UDP
spider-nix recon portscan <target> -o portscan.json     # save results

### Job Hunting
```bash
# Scan a company domain for career opportunities
# 1. Finds career subdomains (careers.company.com)
# 2. Scans pages for job keywords, tech stack, and salary info
# 3. Scores opportunities based on relevance
spider-nix job-hunt <domain> [--pages 5] [--output jobs.json]
````

````

### Job Hunting
```bash
# Scan a company domain for career opportunities
# 1. Finds career subdomains (careers.company.com)
# 2. Scans pages for job keywords, tech stack, and salary info
# 3. Scores opportunities based on relevance
spider-nix job-hunt <domain> [--pages 5] [--output jobs.json]
```

### Proxies
```bash
spider-nix proxy-fetch                    # fetch public proxies
spider-nix proxy-stats proxies.txt --test # validate
````

## Dev

```bash
just install    # editable install
just test       # pytest
just run <url>  # quick test
just clean      # cleanup
```

## Modules

### Core Crawling

- **crawler.py** - HTTP async crawler (httpx)
- **browser.py** - JS rendering (Playwright)
- **proxy.py** - rotation engine
- **stealth.py** - anti-fingerprinting (WebGL + Canvas 2D masking)
- **storage.py** - JSON/CSV/SQLite backends

### OSINT

- **osint/reconnaissance.py** - DNS, WHOIS, subdomain enum
- **osint/analyzer.py** - tech detection, contact harvesting, API discovery
- **osint/scanner.py** - async port scanner, banner grabbing, service detection

### Intel

- **intel/jobs.py** - career page finder, job opportunity analyzer, seniority/salary detection

## Features Implemented

### Stealth & Anti-Fingerprinting

- ✓ WebGL fingerprinting protection
- ✓ Canvas 2D noise injection
- ✓ Navigator properties spoofing
- ✓ Screen resolution randomization
- ✓ Timezone/language randomization
- ✓ Automation flag removal

### Content Analysis

- ✓ Technology detection (Wappalyzer-style)
- ✓ Framework/CMS/library identification
- ✓ Email/phone/social media harvesting
- ✓ API endpoint discovery (fetch/axios patterns)
- ✓ Metadata extraction

### Port Scanning

- ✓ Async TCP/UDP port scanning
- ✓ Service detection (25+ common services)
- ✓ Banner grabbing
- ✓ Version fingerprinting
- ✓ Configurable concurrency and timeouts
- ✓ Range scanning (1-65535)

### Vulnerability Scanning

- ✓ Security header analysis (HSTS, CSP, X-Frame-Options, etc)
- ✓ Common misconfiguration detection
- ✓ Debug mode detection
- ✓ Directory listing checks
- ✓ CVE matching for detected services
- ✓ Security score calculation

### API Integrations

- ✓ Shodan client (host lookup, search)
- ✓ URLScan.io client (scan submission, results)
- ✓ VirusTotal client (URL/domain reputation)
- ✓ OSINTAggregator (multi-source correlation)

### Correlation Engine

- ✓ Entity-relationship graph building
- ✓ Multi-source data correlation
- ✓ Graph export (JSON, Graphviz DOT)
- ✓ Relationship queries
- ✓ Statistics and reporting

### Job Intelligence

- ✓ Career page discovery (subdomains + paths)
- ✓ Keyword based job detection
- ✓ Seniority & Remote policy extraction
- ✓ Salary range extraction
- ✓ Opportunity scoring engine

## Arsenal Complete

**20 OSINT modules** across 6 categories:

- Reconnaissance (3): DNS, WHOIS, Subdomain enumeration
- Analysis (4): Content analyzer, tech detector, contact harvester, API discovery
- Scanning (2): Port scanner, service detector
- Vulnerability (3): Scanner, header checker, CVE matcher
- Integrations (4): Shodan, URLScan, VirusTotal, aggregator
- Correlation (4): Engine, graph, entity, relationship
