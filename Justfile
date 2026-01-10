# SpiderNix Justfile

set shell := ["bash", "-c"]

default:
    @just --list

# Install the package in editable mode
install:
    pip install -e .

# Run the test suite
test:
    pytest tests/

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
