-- ML Feedback Database Schema
-- SQLite schema for storing crawl attempts and strategy effectiveness

-- Crawl attempts log (for ML training)
CREATE TABLE IF NOT EXISTS crawl_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_time_ms REAL NOT NULL,
    response_size INTEGER NOT NULL,
    failure_class TEXT NOT NULL,
    strategies_used TEXT NOT NULL,  -- JSON array
    proxy_used TEXT,
    tls_fingerprint TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT  -- JSON blob
);

-- Indexes for fast querying
CREATE INDEX IF NOT EXISTS idx_domain ON crawl_attempts(domain);
CREATE INDEX IF NOT EXISTS idx_failure_class ON crawl_attempts(failure_class);
CREATE INDEX IF NOT EXISTS idx_timestamp ON crawl_attempts(timestamp);

-- Strategy effectiveness per domain
CREATE TABLE IF NOT EXISTS strategy_effectiveness (
    domain TEXT NOT NULL,
    strategy TEXT NOT NULL,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    avg_response_time_ms REAL DEFAULT 0.0,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (domain, strategy)
);

-- Index for domain lookups
CREATE INDEX IF NOT EXISTS idx_strategy_domain ON strategy_effectiveness(domain);

-- ML model metadata (for versioning trained models)
CREATE TABLE IF NOT EXISTS ml_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    accuracy REAL,
    trained_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    training_samples INTEGER,
    metadata TEXT  -- JSON blob
);

-- Proxy health tracking (for intelligent rotation)
CREATE TABLE IF NOT EXISTS proxy_health (
    proxy_url TEXT PRIMARY KEY,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_success DATETIME,
    last_failure DATETIME,
    avg_response_time_ms REAL DEFAULT 0.0,
    consecutive_failures INTEGER DEFAULT 0,
    is_healthy BOOLEAN DEFAULT 1
);

-- Domain-specific settings learned from feedback
CREATE TABLE IF NOT EXISTS domain_profiles (
    domain TEXT PRIMARY KEY,
    best_strategy TEXT,  -- Most effective strategy
    detection_level TEXT,  -- low, medium, high
    rate_limit_threshold REAL,  -- Requests per second
    recommended_delay_ms INTEGER,
    last_analyzed DATETIME DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT  -- JSON blob
);
