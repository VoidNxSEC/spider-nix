# SpiderNix Justfile

set shell := ["bash", "-c"]

default:
    @just --list

# Install the package in editable mode
install:
    uv venv
    uv pip install -e ".[dev]"

# Run the test suite
test:
    python -m pytest tests/

# Run tests with coverage report
test-cov:
    pytest tests/ --cov=spider_nix --cov-report=html --cov-report=term
    @echo "\n✓ Coverage report: htmlcov/index.html"

# Run tests with coverage and open browser
test-cov-view: test-cov
    python -m webbrowser htmlcov/index.html

# Run linters and checks
check:
    ruff check .
    ruff format --check .

# Install pre-commit hooks
hooks-install:
    pre-commit install
    @echo "✓ Pre-commit hooks installed"

# Run pre-commit on all files
hooks-run:
    pre-commit run --all-files

# Run type checking
typecheck:
    mypy src/spider_nix --ignore-missing-imports

# Run security scans locally
security:
    @echo "Running Bandit..."
    bandit -r src/ -f screen
    @echo "\nRunning Safety..."
    safety check || true
    @echo "\nRunning pip-audit..."
    pip-audit || true

# Full quality check (CI simulation)
ci-local: check typecheck test-cov security
    @echo "\n✅ All CI checks passed!"

# Run the crawler (example)
run url *args:
    python -m spider_nix.cli crawl {{url}} {{args}}

# Fetch public proxies
proxies:
    python -m spider_nix.cli proxy-fetch

# Clean build artifacts and cache
clean:
    rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} +

# Clean including coverage artifacts
clean-all: clean
    rm -rf htmlcov/ .coverage coverage.xml coverage.json
    rm -rf .mypy_cache/ .bandit
    rm -rf *-report.json
