# Spider-Nix Dockerfile
# Multi-stage build for production deployment

# Build stage
FROM python:3.13-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml .

# Install the package with dependencies
RUN pip install --no-cache-dir --user -e ".[resume]"

# Runtime stage
FROM python:3.13-slim

WORKDIR /app

# Install runtime dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    # Additional dependencies
    wget \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy built package from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app /app

# Ensure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Install Playwright browsers
RUN playwright install --with-deps chromium

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security
RUN useradd -m spideruser && \
    chown -R spideruser:spideruser /app
USER spideruser

WORKDIR /app

# Expose default ports
EXPOSE 8000 8080 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import spider_nix; print('OK')" || exit 1

# Default command
ENTRYPOINT ["python", "-m", "spider_nix.cli"]
CMD ["--help"]
