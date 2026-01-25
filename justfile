# Spider-Nix Task Runner
# Use: just <command>

# Default recipe
default:
    @just --list

# Install spider-nix in editable mode
install:
    uv pip install -e .

# Run all tests
test:
    pytest tests/ -v

# Run tests with coverage
test-cov:
    pytest tests/ --cov=src/spider_nix --cov-report=html --cov-report=term

# Run specific test file
test-file FILE:
    pytest tests/{{FILE}} -v

# Install pre-commit hooks
hooks-install:
    pre-commit install

# Run pre-commit on all files
hooks-run:
    pre-commit run --all-files

# Security scan with bandit
security:
    bandit -r src/spider_nix -ll

# Type checking with mypy
typecheck:
    mypy src/spider_nix --ignore-missing-imports

# Lint with ruff
lint:
    ruff check src/spider_nix

# Format code with ruff
fmt:
    ruff format src/spider_nix tests

# Run full CI pipeline locally
ci-local: lint typecheck security test

# Clean build artifacts
clean:
    rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache htmlcov
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete

# Run crawler (basic)
run URL:
    python -m spider_nix.cli crawl {{URL}}

# Run multimodal extraction
extract-multimodal URL:
    python -m spider_nix.cli recon multimodal {{URL}}

# Fetch fresh proxies
proxies:
    python -m spider_nix.cli proxies fetch --limit 50

# Show ML feedback stats
ml-stats:
    python -m spider_nix.cli ml stats

# Show ML stats for specific domain
ml-domain DOMAIN:
    python -m spider_nix.cli ml domain {{DOMAIN}}

# Initialize feedback database
ml-init:
    python -m spider_nix.ml.feedback_logger

# Start Go network proxy (separate terminal)
proxy-start:
    cd ../spider-nix-network && ./spider-network-proxy -config configs/test.toml

# Build Go network proxy
proxy-build:
    cd ../spider-nix-network && make build

# Run browser-based crawl
browser URL:
    python -m spider_nix.cli crawl {{URL}} --browser

# Run OSINT scan
osint URL:
    python -m spider_nix.cli osint scan {{URL}}

# Generate crawl report
report:
    python -m spider_nix.cli report generate

# Show version
version:
    python -c "from spider_nix import __version__; print(__version__)"

# Development mode (watch and reload)
dev:
    @echo "Development mode - use 'just test' in another terminal"
    @echo "Watching for changes..."

# Benchmark performance
benchmark URL:
    @echo "Running performance benchmark on {{URL}}"
    hyperfine --warmup 3 "python -m spider_nix.cli crawl {{URL}}"
