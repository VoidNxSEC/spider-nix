package main

import (
	"context"
	"crypto/tls"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/elazarl/goproxy"

	"github.com/kernelcore/spider-nix-network/internal/config"
	tlsutil "github.com/kernelcore/spider-nix-network/internal/tls"
)

var (
	configPath = flag.String("config", "configs/production.toml", "Path to config file")
)

func main() {
	flag.Parse()

	// Load configuration
	cfg, err := config.LoadConfig(*configPath)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	log.Printf("Spider Network Proxy starting...")
	log.Printf("  HTTP Proxy: %s", cfg.Proxy.HTTPListen)
	log.Printf("  TLS Fingerprinting: %v", cfg.TLS.FingerprintRotation)

	// Initialize fingerprint manager
	fm := tlsutil.NewFingerprintManager(cfg.TLS.ProfileCacheTTL)

	// Start HTTP proxy (simplified for MVP)
	httpProxy := createHTTPProxy(fm, cfg)
	httpServer := &http.Server{
		Addr:    cfg.Proxy.HTTPListen,
		Handler: httpProxy,
	}

	go func() {
		log.Printf("HTTP proxy listening on %s", cfg.Proxy.HTTPListen)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("HTTP proxy error: %v", err)
		}
	}()

	// Graceful shutdown
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
	<-sigCh

	log.Println("Shutting down...")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	httpServer.Shutdown(ctx)
}

// createHTTPProxy creates basic proxy with TLS fingerprint awareness
func createHTTPProxy(fm *tlsutil.FingerprintManager, cfg *config.Config) *goproxy.ProxyHttpServer {
	proxy := goproxy.NewProxyHttpServer()
	proxy.Verbose = false

	// HTTPS CONNECT handler with profile logging
	proxy.OnRequest().HandleConnect(goproxy.FuncHttpsHandler(func(host string, ctx *goproxy.ProxyCtx) (*goproxy.ConnectAction, string) {
		// Get profile for target domain
		profile := fm.GetProfileForDomain(host)

		log.Printf("[HTTPS] %s - Profile: %s", host, profile.Name)

		// Use standard TLS config (uTLS integration for Phase 2)
		return &goproxy.ConnectAction{
			Action: goproxy.ConnectMitm,
			TLSConfig: func(host string, ctx *goproxy.ProxyCtx) (*tls.Config, error) {
				return profile.BuildTLSConfig(), nil
			},
		}, host
	}))

	// HTTP request handler
	proxy.OnRequest().DoFunc(func(req *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
		// Get profile for domain
		domain := req.URL.Hostname()
		profile := fm.GetProfileForDomain(domain)

		log.Printf("[HTTP] %s %s - Profile: %s", req.Method, req.URL, profile.Name)

		return req, nil
	})

	return proxy
}
