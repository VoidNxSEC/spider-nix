# Spider-Nix Task Runner
# Compatibility layer. Prefer: spider <command>

# Default recipe
default:
    @spider --help

# Install spider-nix in editable mode
# Install (No-op in Nix)
install:
    @echo "Dependencies are managed by Nix. No installation needed."
    @echo "If you need to install the package in editable mode for tools not using PYTHONPATH:"
    @echo "  uv pip install -e . --no-deps"

# Run all tests
test:
    spider test

# Run tests with coverage
test-cov:
    spider test-cov

# Run specific test file
test-file FILE:
    python -m pytest tests/{{FILE}} -v

# Install pre-commit hooks
hooks-install:
    spider hooks-install

# Run pre-commit on all files
hooks-run:
    spider hooks-run

# Run security scans
security:
    spider security

# Type checking with mypy
typecheck:
    spider typecheck

# Lint with ruff
lint:
    spider lint

# Compatibility alias used in docs
check: lint

# Format code with ruff
fmt:
    spider fmt

# Run full CI pipeline locally
ci-local: lint typecheck security test

# Clean build artifacts
clean:
    spider clean

# Run crawler (basic)
run URL:
    spider crawl {{URL}}

# Run multimodal extraction
extract-multimodal URL:
    spider recon multimodal {{URL}}

# Fetch fresh proxies
proxies:
    spider proxy-fetch

# Show ML feedback stats
ml-stats:
    @echo "Not yet exposed via 'spider'. Use: python -m spider_nix.cli ml stats"

# Show ML stats for specific domain
ml-domain DOMAIN:
    @echo "Not yet exposed via 'spider'. Use: python -m spider_nix.cli ml domain {{DOMAIN}}"

# Initialize feedback database
ml-init:
    python -m spider_nix.ml.feedback_logger

# Start Go network proxy (separate terminal)
proxy-start:
    spider proxy-start

# Build Go network proxy
proxy-build:
    spider proxy-build


# Run browser-based crawl
browser URL:
    spider crawl {{URL}} --browser

# Run OSINT scan
osint URL:
    @echo "Not yet exposed via 'spider'. Use: spider recon ..."

# Generate crawl report
report:
    @echo "Not yet exposed via 'spider'. Use: spider generate-html-report <results.json>"

# Show version
version:
    spider version

# Development mode (watch and reload)
dev:
    @echo "Development mode - use 'spider test' in another terminal"
    @echo "Watching for changes..."

# Benchmark performance
benchmark URL:
    spider benchmark {{URL}}
