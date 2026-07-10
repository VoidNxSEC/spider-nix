# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Security Measures

Spider-Nix implements multiple layers of security scanning:

### Automated Security Scans

**SAST (Static Application Security Testing)**
- **Bandit**: Python-specific security linting
- **Ruff Security Rules**: Flake8-bandit integration
- **Frequency**: Every commit via pre-commit hooks and CI

**Dependency Scanning**
- **Safety**: Checks for known security vulnerabilities in dependencies
- **pip-audit**: Audits Python packages against PyPI advisory database
- **Frequency**: Every PR + weekly scheduled scans

**Secret Detection**
- **Gitleaks**: Scans git history for leaked credentials
- **Pre-commit hooks**: Prevents secret commits locally
- **Frequency**: Every commit + full history scan in CI

### Security Best Practices

**Input Validation**
- All user inputs validated via Pydantic models
- URL sanitization before HTTP requests
- File path validation for storage operations

**Dependency Management**
- Minimal dependency footprint
- Pinned versions in Nix flake
- Regular updates via scheduled scans

**Network Security**
- Timeout enforcement on all HTTP requests
- Proxy validation before use
- SSL/TLS certificate verification enabled

## Reporting a Vulnerability

**We take security seriously.** If you discover a security vulnerability, please follow responsible disclosure practices:

### How to Report

**DO NOT** open a public GitHub issue for security vulnerabilities.

Instead, report privately via:

1. **GitHub Security Advisories** (Preferred)
   - Go to: https://github.com/VoidNxSEC/spider-nix/security/advisories
   - Click "Report a vulnerability"
   - Provide detailed description

2. **Email** (Alternative)
   - Email: security@yourdomain.com
   - Subject: "[SECURITY] Spider-Nix Vulnerability Report"
   - Include:
     - Description of the vulnerability
     - Steps to reproduce
     - Potential impact
     - Suggested fix (if any)

### What to Include

A good vulnerability report includes:

- **Type of vulnerability** (e.g., SQL injection, XSS, RCE)
- **Affected component** (file, module, function)
- **Attack scenario** (how it could be exploited)
- **Proof of concept** (code, curl commands, etc.)
- **Impact assessment** (what data/systems at risk)
- **Suggested remediation** (if you have ideas)

### Response Timeline

| Stage                  | Timeline     |
| ---------------------- | ------------ |
| Initial Response       | 48 hours     |
| Vulnerability Triage   | 1 week       |
| Fix Development        | 2-4 weeks    |
| Security Advisory      | After fix    |
| Public Disclosure      | After patch  |

### What to Expect

1. **Acknowledgment**: We'll confirm receipt within 48 hours
2. **Assessment**: We'll validate and assess severity
3. **Communication**: We'll keep you updated on progress
4. **Credit**: With your permission, we'll credit you in advisory
5. **Disclosure**: Coordinated disclosure after patch release

## Security Advisory Policy

When we release a security patch:

1. **Security Advisory Published**: Details after mitigation
2. **CVE Assignment**: For high/critical vulnerabilities
3. **Changelog Entry**: Documented in CHANGELOG.md
4. **GitHub Release**: Tagged with security notes

## Scope

### In Scope

Security issues in:
- Core crawling logic
- OSINT modules
- CLI command handling
- Data storage and retrieval
- Proxy handling
- External API integrations

### Out of Scope

- Vulnerabilities in third-party dependencies (report to upstream)
- Social engineering attacks
- Physical security issues
- Issues requiring privileged system access
- DDoS attacks

## Responsible Use

**Spider-Nix is a security research tool.** Users are responsible for:

- Complying with applicable laws
- Obtaining authorization before scanning targets
- Respecting robots.txt and rate limits
- Not using for malicious purposes

**We assume no liability for misuse.**

## Security Updates

Subscribe to security updates:
- **Watch** this repository on GitHub
- Enable **Security Alerts** in your account settings
- Follow releases for security patches

---

**Last Updated**: 2026-01-15
