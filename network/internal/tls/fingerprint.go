package tls

import (
	"crypto/tls"
	"math/rand"
	"sync"
	"time"

	utls "github.com/refraction-networking/utls"
	"golang.org/x/net/http2"
)

// BrowserProfile represents a complete browser fingerprint
type BrowserProfile struct {
	Name           string
	ClientHelloID  utls.ClientHelloID
	HTTP2Settings  []http2.Setting
	PriorityFrames []http2.PriorityParam
}

// Predefined browser profiles (4 major browsers)
var profiles = []BrowserProfile{
	{
		Name:          "Chrome_120_Windows",
		ClientHelloID: utls.HelloChrome_120,
		HTTP2Settings: []http2.Setting{
			{ID: http2.SettingHeaderTableSize, Val: 65536},
			{ID: http2.SettingEnablePush, Val: 1},
			{ID: http2.SettingMaxConcurrentStreams, Val: 1000},
			{ID: http2.SettingInitialWindowSize, Val: 6291456},
			{ID: http2.SettingMaxHeaderListSize, Val: 262144},
		},
		PriorityFrames: []http2.PriorityParam{
			{Weight: 201, StreamDep: 0, Exclusive: false},
		},
	},
	{
		Name:          "Firefox_Auto",
		ClientHelloID: utls.HelloFirefox_Auto,
		HTTP2Settings: []http2.Setting{
			{ID: http2.SettingHeaderTableSize, Val: 65536},
			{ID: http2.SettingEnablePush, Val: 0}, // Firefox disables push
			{ID: http2.SettingMaxConcurrentStreams, Val: 1000},
			{ID: http2.SettingInitialWindowSize, Val: 131072},
			{ID: http2.SettingMaxFrameSize, Val: 16384},
		},
	},
	{
		Name:          "Safari_Auto",
		ClientHelloID: utls.HelloSafari_Auto,
		HTTP2Settings: []http2.Setting{
			{ID: http2.SettingHeaderTableSize, Val: 4096},
			{ID: http2.SettingEnablePush, Val: 1},
			{ID: http2.SettingMaxConcurrentStreams, Val: 100},
			{ID: http2.SettingInitialWindowSize, Val: 2097152},
		},
	},
	{
		Name:          "Edge_120_Windows",
		ClientHelloID: utls.HelloChrome_120, // Edge uses Chromium
		HTTP2Settings: []http2.Setting{
			{ID: http2.SettingHeaderTableSize, Val: 65536},
			{ID: http2.SettingEnablePush, Val: 1},
			{ID: http2.SettingMaxConcurrentStreams, Val: 1000},
			{ID: http2.SettingInitialWindowSize, Val: 6291456},
		},
	},
}

// FingerprintManager manages TLS fingerprint rotation
type FingerprintManager struct {
	mu     sync.RWMutex
	cache  map[string]BrowserProfile // domain -> profile
	rng    *rand.Rand
	cacheTTL time.Duration
}

// NewFingerprintManager creates a new fingerprint manager
func NewFingerprintManager(cacheTTLHours int) *FingerprintManager {
	return &FingerprintManager{
		cache:    make(map[string]BrowserProfile),
		rng:      rand.New(rand.NewSource(time.Now().UnixNano())),
		cacheTTL: time.Duration(cacheTTLHours) * time.Hour,
	}
}

// GetProfileForDomain returns a cached or new profile for domain
func (fm *FingerprintManager) GetProfileForDomain(domain string) BrowserProfile {
	fm.mu.RLock()
	if profile, ok := fm.cache[domain]; ok {
		fm.mu.RUnlock()
		return profile
	}
	fm.mu.RUnlock()

	// Assign random profile
	profile := fm.getRandomProfile()

	fm.mu.Lock()
	fm.cache[domain] = profile
	fm.mu.Unlock()

	return profile
}

// getRandomProfile selects a random browser profile
func (fm *FingerprintManager) getRandomProfile() BrowserProfile {
	return profiles[fm.rng.Intn(len(profiles))]
}

// BuildTLSConfig creates uTLS config for the profile
func (p *BrowserProfile) BuildTLSConfig() *tls.Config {
	return &tls.Config{
		InsecureSkipVerify: false, // Verify certificates
		MinVersion:         tls.VersionTLS12,
		MaxVersion:         tls.VersionTLS13,
	}
}

// GetUTLSConfig returns the uTLS ClientHelloSpec
func (p *BrowserProfile) GetUTLSConfig() *utls.Config {
	return &utls.Config{
		ServerName:         "", // Set dynamically per request
		InsecureSkipVerify: false,
		ClientSessionCache: utls.NewLRUClientSessionCache(32),
	}
}
