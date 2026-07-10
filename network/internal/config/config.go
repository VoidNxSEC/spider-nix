package config

import (
	"fmt"
	"os"

	"github.com/BurntSushi/toml"
)

// Config represents the complete configuration
type Config struct {
	Proxy   ProxyConfig   `toml:"proxy"`
	TLS     TLSConfig     `toml:"tls"`
	HTTP2   HTTP2Config   `toml:"http2"`
	Metrics MetricsConfig `toml:"metrics"`
}

// ProxyConfig contains proxy server settings
type ProxyConfig struct {
	HTTPListen   string `toml:"http_listen"`
	SOCKS5Listen string `toml:"socks5_listen"`
}

// TLSConfig contains TLS fingerprinting settings
type TLSConfig struct {
	FingerprintRotation bool   `toml:"fingerprint_rotation"`
	ProfileCacheTTL     int    `toml:"profile_cache_ttl_hours"`
	BrowserPool         []string `toml:"browser_pool"`
}

// HTTP2Config contains HTTP/2 customization settings
type HTTP2Config struct {
	RandomizeSettings     bool `toml:"randomize_settings"`
	PriorityFramesEnabled bool `toml:"priority_frames_enabled"`
}

// MetricsConfig contains Prometheus metrics settings
type MetricsConfig struct {
	Enabled bool   `toml:"enabled"`
	Listen  string `toml:"listen"`
}

// LoadConfig loads configuration from TOML file
func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config: %w", err)
	}

	var cfg Config
	if err := toml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse config: %w", err)
	}

	// Set defaults
	if cfg.Proxy.HTTPListen == "" {
		cfg.Proxy.HTTPListen = "127.0.0.1:8080"
	}
	if cfg.Proxy.SOCKS5Listen == "" {
		cfg.Proxy.SOCKS5Listen = "127.0.0.1:1080"
	}
	if cfg.TLS.ProfileCacheTTL == 0 {
		cfg.TLS.ProfileCacheTTL = 24
	}
	if cfg.Metrics.Listen == "" {
		cfg.Metrics.Listen = "127.0.0.1:9090"
	}

	return &cfg, nil
}
