package proxy

import (
	"crypto/tls"
	"fmt"
	"log"
	"net"
	"net/http"

	"github.com/elazarl/goproxy"
	"github.com/kernelcore/spider-nix-network/internal/config"
	tlsmanager "github.com/kernelcore/spider-nix-network/internal/tls"
)

// Server represents the proxy server
type Server struct {
	config            *config.Config
	proxy             *goproxy.ProxyHttpServer
	fingerprintMgr    *tlsmanager.FingerprintManager
	requestCount      int64
	fingerprintStats  map[string]int
}

// NewServer creates a new proxy server
func NewServer(cfg *config.Config) *Server {
	proxy := goproxy.NewProxyHttpServer()
	proxy.Verbose = false

	fingerprintMgr := tlsmanager.NewFingerprintManager(
		cfg.TLS.BrowserPool,
		cfg.TLS.FingerprintRotation,
	)

	s := &Server{
		config:           cfg,
		proxy:            proxy,
		fingerprintMgr:   fingerprintMgr,
		fingerprintStats: make(map[string]int),
	}

	s.setupHandlers()

	return s
}

// setupHandlers configures proxy request handlers
func (s *Server) setupHandlers() {
	// HTTP handler
	s.proxy.OnRequest().DoFunc(func(req *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
		s.requestCount++

		// Log request
		log.Printf("[HTTP] %s %s", req.Method, req.URL.String())

		// Add custom headers if needed
		// req.Header.Set("X-Proxy-By", "spider-nix-network")

		return req, nil
	})

	// HTTPS handler with uTLS
	s.proxy.OnRequest().HandleConnect(goproxy.FuncHttpsHandler(func(host string, ctx *goproxy.ProxyCtx) (*goproxy.ConnectAction, string) {
		log.Printf("[HTTPS] CONNECT %s", host)

		// Get random fingerprint
		fp := s.fingerprintMgr.GetFingerprint()
		s.fingerprintStats[fp.Name]++

		log.Printf("[HTTPS] Using fingerprint: %s for %s", fp.Name, host)

		// Return CONNECT action with TLS config
		// Note: Full uTLS integration requires custom dialer
		return goproxy.OkConnect, host
	}))

	// Response handler
	s.proxy.OnResponse().DoFunc(func(resp *http.Response, ctx *goproxy.ProxyCtx) *http.Response {
		if resp != nil {
			log.Printf("[RESPONSE] %d %s", resp.StatusCode, ctx.Req.URL.String())
		}
		return resp
	})
}

// Start starts the proxy server
func (s *Server) Start() error {
	addr := fmt.Sprintf("%s:%d", s.config.Proxy.Listen, s.config.Proxy.Port)

	log.Printf("Starting spider-network-proxy on %s", addr)
	log.Printf("TLS fingerprint rotation: %v", s.config.TLS.FingerprintRotation)
	log.Printf("Browser pool: %v", s.config.TLS.BrowserPool)

	return http.ListenAndServe(addr, s.proxy)
}

// GetStats returns proxy statistics
func (s *Server) GetStats() map[string]interface{} {
	return map[string]interface{}{
		"requests":            s.requestCount,
		"fingerprint_stats":   s.fingerprintStats,
		"fingerprint_manager": s.fingerprintMgr.GetStats(),
	}
}

// customDialTLS creates a TLS connection with uTLS fingerprinting
func (s *Server) customDialTLS(network, addr string) (net.Conn, error) {
	// Parse host for SNI
	host, _, err := net.SplitHostPort(addr)
	if err != nil {
		host = addr
	}

	// Dial TCP
	conn, err := net.Dial(network, addr)
	if err != nil {
		return nil, err
	}

	// Create standard TLS conn first
	tlsConn := tls.Client(conn, &tls.Config{
		ServerName:         host,
		InsecureSkipVerify: false,
	})

	// Upgrade to uTLS
	uconn, err := s.fingerprintMgr.CreateUTLSConn(tlsConn, host)
	if err != nil {
		conn.Close()
		return nil, err
	}

	// Perform handshake
	if err := uconn.Handshake(); err != nil {
		uconn.Close()
		return nil, err
	}

	return uconn, nil
}
