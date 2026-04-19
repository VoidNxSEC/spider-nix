# Contributing to Spider-Nix

Thank you for your interest in contributing to Spider-Nix! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- NixOS or Nix package manager (2.4+)
- Git
- Basic Python knowledge

### Getting Started

1. **Fork and Clone**
   ```bash
   git clone https://github.com/VoidNxSEC/spider-nix.git
   cd spider-nix
   ```

2. **Enter Development Environment**
   ```bash
   nix develop
   ```

   This command:
   - Installs Python 3.13 with all dependencies
   - Sets up Playwright browsers
   - Configures development tools (pytest, ruff, mypy, bandit)
   - Adds `spider`, uv, pre-commit, and compatibility tooling

3. **Install Hooks**
   ```bash
   spider hooks-install
   ```

4. **Verify Setup**
   ```bash
   spider test
   spider check
   ```

## Development Workflow

### Branch Strategy

- `main` - Production-ready code
- `feature/*` - New features
- `fix/*` - Bug fixes
- `docs/*` - Documentation updates

### Making Changes

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Write code following our [Code Style](#code-style)
   - Add tests for new functionality
   - Update documentation if needed

3. **Run Quality Checks**
   ```bash
   spider ci-local  # Runs full CI pipeline locally
   ```

4. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: add awesome feature"
   ```

   Pre-commit hooks will:
   - Auto-format code with ruff
   - Run type checking with mypy
   - Check for secrets and large files
   - Run quick test suite

5. **Push and Create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

   Open a Pull Request on GitHub.

## Code Style

### Python Style Guide

We use **Ruff** for both linting and formatting:

```bash
# Format code
ruff format .

# Check linting
ruff check .

# Fix auto-fixable issues
ruff check --fix .
```

**Key Conventions**:
- Line length: 100 characters
- Python 3.11+ features encouraged
- Type hints preferred (but not required yet)
- Docstrings for public APIs

### Async/Await Patterns

```python
# Good: Use async/await throughout
async def fetch_data(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()

# Bad: Mixing sync and async
def fetch_data(url: str) -> dict:
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(async_fetch(url))
```

### Configuration Management

Use **Pydantic** models for configuration:

```python
from pydantic import BaseModel, Field

class FeatureConfig(BaseModel):
    timeout: int = Field(default=30, gt=0)
    retries: int = Field(default=3, ge=0)
```

## Testing

### Writing Tests

Tests live in `tests/` and mirror the `src/` structure:

```
tests/
├── test_crawler.py
├── test_browser.py
├── osint/
│   ├── test_reconnaissance.py
│   └── test_scanner.py
```

**Test Requirements**:
- All new features must have tests
- Aim for 80%+ coverage
- Use pytest fixtures for setup
- Use pytest-asyncio for async tests

**Example Test**:
```python
import pytest
from spider_nix.crawler import SpiderNix

@pytest.mark.asyncio
async def test_crawler_basic():
    """Test basic crawling functionality."""
    crawler = SpiderNix(max_pages=5)
    results = await crawler.crawl("https://example.com")

    assert len(results) > 0
    assert results[0]["url"] == "https://example.com"
    assert "title" in results[0]
```

### Running Tests

```bash
# All tests
spider test

# With coverage
spider test-cov

# Specific file
pytest tests/test_crawler.py

# Specific test
pytest tests/test_crawler.py::test_crawler_basic

# Watch mode (re-run on changes)
pytest-watch
```

### Coverage Goals

- **Minimum**: 70% overall coverage
- **Target**: 80%+ coverage
- **Critical paths**: 90%+ (crawler, OSINT modules)

## Security

### Security Guidelines

1. **Never commit secrets**
   - Use environment variables
   - Add secrets to `.env` (ignored by git)
   - Use pre-commit hooks to detect accidental commits

2. **Input Validation**
   - Validate all user inputs
   - Use Pydantic models for structured data
   - Sanitize URLs and file paths

3. **Dependency Management**
   - Review dependencies before adding
   - Run `spider security` to scan for vulnerabilities
   - Update dependencies regularly

### Reporting Security Issues

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## Pull Request Process

### PR Checklist

Before submitting, ensure:

- [ ] Code follows style guidelines (ruff passes)
- [ ] Tests added for new functionality
- [ ] All tests pass (`spider test`)
- [ ] Type checking passes (`spider typecheck`)
- [ ] Security scans pass (`spider security`)
- [ ] Documentation updated if needed
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)

### PR Guidelines

**Good PR Title Examples**:
- `feat: add subdomain enumeration via certificate transparency`
- `fix: resolve race condition in proxy rotator`
- `docs: add examples for job-hunt command`
- `perf: optimize crawler request pooling`

**PR Description Should Include**:
- Summary of changes
- Motivation/context
- Testing performed
- Screenshots (if UI changes)
- Breaking changes (if any)

### Review Process

1. Automated CI runs (lint, test, security)
2. Code review by maintainer
3. Requested changes addressed
4. Final approval and merge

## Development Commands Reference

```bash
# Setup
spider hooks-install  # Install pre-commit hooks

# Development
spider test           # Run tests
spider test-cov       # Tests with coverage
spider check          # Run linters
spider typecheck      # Run type checking
spider security       # Run security scans
spider ci-local       # Full CI simulation

# Utilities
spider crawl <url>    # Quick crawler test
spider proxy-fetch    # Fetch public proxies
spider clean          # Clean artifacts
```

## Questions?

- **Bug reports**: [Open an issue](https://github.com/VoidNxSEC/spider-nix/issues)
- **Feature requests**: [Start a discussion](https://github.com/VoidNxSEC/spider-nix/discussions)
- **Security issues**: See [SECURITY.md](SECURITY.md)

---

Thank you for contributing to Spider-Nix!
