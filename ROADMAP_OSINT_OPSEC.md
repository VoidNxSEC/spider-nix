# Spider-Nix OSINT | OPSEC Integration Roadmap

**Status:** Fase 1 MVP
**Goal:** Enterprise anti-detection scraping with multimodal extraction
**Total Estimated Cost:** ~25,000 tokens | 4-6 weeks implementation
**Generated:** 2026-01-23

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Spider-Nix OSINT Platform                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐      ┌──────────────┐                   │
│  │   Browser    │─────→│   Stealth    │                   │
│  │  (Playwright)│      │    Engine    │                   │
│  └──────┬───────┘      └──────────────┘                   │
│         │                                                   │
│         │ Screenshot                                        │
│         ↓                                                   │
│  ┌──────────────────────────────────────┐                 │
│  │      Vision-DOM Fusion Pipeline      │                 │
│  ├──────────────────────────────────────┤                 │
│  │  Vision Client → ml-offload-api      │                 │
│  │       ↓                               │                 │
│  │  CLIP/LLaVA → Bounding Boxes         │                 │
│  │       ↓                               │                 │
│  │  DOM Analyzer (parallel)             │                 │
│  │       ↓                               │                 │
│  │  Fusion Engine (IoU matching)        │                 │
│  │       ↓                               │                 │
│  │  FusedElement (high confidence)      │                 │
│  └──────────────────────────────────────┘                 │
│         │                                                   │
│         ↓                                                   │
│  ┌──────────────────────────────────────┐                 │
│  │     ML Feedback & Strategy Loop      │                 │
│  ├──────────────────────────────────────┤                 │
│  │  Failure Classifier                  │                 │
│  │    → RATE_LIMIT / FINGERPRINT /      │                 │
│  │       CAPTCHA / IP_BLOCKED           │                 │
│  │       ↓                               │                 │
│  │  Strategy Selector (epsilon-greedy)  │                 │
│  │    → TLS rotation / Proxy / Delays   │                 │
│  │       ↓                               │                 │
│  │  feedback.db (SQLite)                │                 │
│  └──────────────────────────────────────┘                 │
│         │                                                   │
│         ↓                                                   │
│  ┌──────────────────────────────────────┐                 │
│  │     Network OPSEC Layer              │                 │
│  ├──────────────────────────────────────┤                 │
│  │  spider-nix-network (Go)             │                 │
│  │    → uTLS fingerprint randomization  │                 │
│  │    → HTTP/2 customization            │                 │
│  │    → SOCKS5/HTTP proxy @ :8080      │                 │
│  └──────────────────────────────────────┘                 │
│         │                                                   │
│         ↓                                                   │
│     Internet                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1A: OPSEC Hardening

**Goal:** Bulletproof anti-detection before aggressive scraping
**Duration:** 3-5 days
**Token Cost:** ~3,000 tokens

### Task 1.1: Enhanced Stealth Engine

**File:** `src/spider_nix/stealth.py`

**Patches to Add:**

1. **Function.toString Override** (Hide patched functions)
```javascript
const originalToString = Function.prototype.toString;
Function.prototype.toString = function() {
    if (this === navigator.webdriver ||
        this === HTMLCanvasElement.prototype.toDataURL ||
        this === CanvasRenderingContext2D.prototype.getImageData) {
        return 'function () { [native code] }';
    }
    return originalToString.call(this);
};
```

2. **Battery API Blocking**
```javascript
delete navigator.getBattery;
Object.defineProperty(navigator, 'getBattery', {
    get: () => undefined,
    configurable: false
});
```

3. **Chrome DevTools Protocol Cleanup**
```javascript
// Delete CDP markers
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
delete window.$chrome_asyncScriptInfo;
delete document.__playwright_evaluation_script__;
delete document.__puppeteer_evaluation_script__;
```

4. **Permissions API Hardening**
```javascript
const originalQuery = navigator.permissions.query;
navigator.permissions.query = function(parameters) {
    // Always return 'prompt' for fingerprinting permissions
    if (parameters.name === 'notifications' ||
        parameters.name === 'geolocation' ||
        parameters.name === 'midi') {
        return Promise.resolve({state: 'prompt'});
    }
    return originalQuery.call(navigator.permissions, parameters);
};
```

5. **MediaDevices Enumeration Blocking**
```javascript
navigator.mediaDevices.enumerateDevices = async () => {
    return []; // Return empty to prevent device fingerprinting
};
```

6. **WebDriver Property (Strict Override)**
```javascript
Object.defineProperty(navigator, 'webdriver', {
    get: () => false,
    configurable: false,
    writable: false
});
```

**Success Criteria:**
- [ ] All 6 patches integrated in `get_playwright_stealth_script()`
- [ ] No console errors on injection
- [ ] Function.toString() returns `[native code]` for patched functions

---

### Task 1.2: Fingerprint Randomization Enhancement

**File:** `src/spider_nix/stealth.py`

**Enhancements:**

1. **Canvas Noise Calibration**
```python
# Current: Fixed 0.0001 noise
# Enhancement: Per-session random noise factor
noise_factor = random.uniform(0.00001, 0.0001)  # Variable noise
```

2. **WebGL Vendor Pool Expansion**
```python
WEBGL_VENDORS = [
    # Add more realistic combinations
    ("Intel Inc.", "Intel Iris OpenGL Engine"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060)"),
    ("AMD", "AMD Radeon RX 6800 XT"),
    ("Apple", "Apple M1 GPU"),
]
```

3. **AudioContext Timing Jitter**
```python
# Current: Fixed 0.00001 offset
# Enhancement: Random jitter per context
jitter = random.uniform(0.000001, 0.00002)
```

4. **Screen Metrics Realistic Pools**
```python
REALISTIC_RESOLUTIONS = [
    # MacBook Pro
    (2560, 1600, 2.0, 30),  # width, height, pixel_ratio, color_depth
    (3024, 1964, 2.0, 30),  # M1 Pro 14"
    # Common Windows
    (1920, 1080, 1.0, 24),
    (2560, 1440, 1.5, 24),
    (3840, 2160, 1.5, 30),  # 4K
    # Linux workstation
    (1920, 1080, 1.0, 24),
    (2560, 1440, 1.0, 24),
]
```

**Success Criteria:**
- [ ] Per-session randomization (not per-request)
- [ ] Fingerprints pass realistic distribution tests
- [ ] No outlier values that trigger suspicion

---

### Task 1.3: Detection Testing Suite

**File:** `tests/test_stealth_detection.py` (NEW)

**Tests:**

1. **Sannysoft Bot Detection Test**
```python
async def test_sannysoft_detection():
    crawler = BrowserCrawler(config, proxy_rotator)
    result = await crawler.crawl("https://bot.sannysoft.com")

    # Parse results page
    assert "WebDriver: false" in result.content
    assert "Chrome: present" in result.content
    assert "Permissions: present" in result.content
```

2. **Incolumitas Bot Test**
```python
async def test_incolumitas_detection():
    result = await crawler.crawl("https://arh.antoinevastel.com/bots/areyouheadless")

    # Check for headless detection flags
    assert "You are not Chrome headless" in result.content
```

3. **Canvas Fingerprint Consistency**
```python
async def test_canvas_consistency():
    # Take 10 screenshots, verify canvas fingerprint varies slightly
    fingerprints = []
    for _ in range(10):
        result = await crawler.crawl("canvas-fingerprint-test.html")
        fingerprints.append(extract_canvas_hash(result))

    # All should be unique (due to noise)
    assert len(set(fingerprints)) == 10
```

4. **WebGL Fingerprint Test**
```python
async def test_webgl_fingerprint():
    result = await crawler.crawl("https://webglreport.com")

    # Verify vendor randomization worked
    assert result.metadata.get("webgl_vendor") in WEBGL_VENDORS
```

**Success Criteria:**
- [ ] Pass 4/4 detection tests
- [ ] Zero red flags on Sannysoft
- [ ] Headless detection: NEGATIVE
- [ ] Fingerprint consistency: PASS

---

## Phase 1B: Network OPSEC Layer

**Goal:** TLS/HTTP fingerprint evasion + IP rotation infrastructure
**Duration:** 6-8 days
**Token Cost:** ~8,000 tokens

### Task 2.1: Go Proxy Repository Setup

**Directory:** `/home/kernelcore/arch/spider-nix-network/`

**Structure:**
```
spider-nix-network/
├── go.mod
├── go.sum
├── cmd/
│   └── spider-network-proxy/
│       └── main.go                    # HTTP/SOCKS5 server
├── internal/
│   ├── config/
│   │   ├── config.go                  # TOML parser
│   │   └── config_test.go
│   ├── tls/
│   │   ├── fingerprint.go             # uTLS integration
│   │   ├── profiles.go                # Browser profiles
│   │   └── randomizer.go              # Per-request rotation
│   ├── http2/
│   │   ├── customizer.go              # SETTINGS frame randomization
│   │   └── priority.go                # Priority frame tuning
│   ├── proxy/
│   │   ├── http_handler.go            # HTTP proxy
│   │   ├── socks5_handler.go          # SOCKS5 proxy
│   │   └── middleware.go              # Logging, metrics
│   └── metrics/
│       └── prometheus.go              # /metrics endpoint
├── configs/
│   ├── example.toml                   # Public template
│   └── production.toml                # .gitignore
├── README.md
└── Makefile
```

**Dependencies (go.mod):**
```go
module github.com/kernelcore/spider-nix-network

go 1.21

require (
    github.com/refraction-networking/utls v1.6.0  // TLS fingerprinting
    github.com/elazarl/goproxy v0.0.0-20231117061959-7cc037d33fb5  // HTTP proxy
    github.com/things-go/go-socks5 v0.0.4         // SOCKS5
    github.com/BurntSushi/toml v1.3.2             // Config
    github.com/prometheus/client_golang v1.18.0   // Metrics
    golang.org/x/net v0.19.0                      // HTTP/2
)
```

**Success Criteria:**
- [ ] Go module initialized
- [ ] Directory structure complete
- [ ] Dependencies downloaded (`go mod tidy`)

---

### Task 2.2: uTLS Fingerprint Implementation

**File:** `internal/tls/fingerprint.go`

**Browser Profiles:**
```go
type BrowserProfile struct {
    Name            string
    ClientHelloID   tls.ClientHelloID
    HTTP2Settings   []http2.Setting
    PriorityFrames  []http2.PriorityFrame
}

var profiles = []BrowserProfile{
    {
        Name: "Chrome_120_Windows",
        ClientHelloID: tls.HelloChrome_120,
        HTTP2Settings: []http2.Setting{
            {ID: http2.SettingHeaderTableSize, Val: 65536},
            {ID: http2.SettingEnablePush, Val: 1},
            {ID: http2.SettingMaxConcurrentStreams, Val: 1000},
            {ID: http2.SettingInitialWindowSize, Val: 6291456},
            {ID: http2.SettingMaxHeaderListSize, Val: 262144},
        },
    },
    {
        Name: "Firefox_121_Windows",
        ClientHelloID: tls.HelloFirefox_121,
        HTTP2Settings: []http2.Setting{
            {ID: http2.SettingHeaderTableSize, Val: 65536},
            {ID: http2.SettingEnablePush, Val: 0}, // Firefox disables push
            {ID: http2.SettingMaxConcurrentStreams, Val: 1000},
            {ID: http2.SettingInitialWindowSize, Val: 131072},
            {ID: http2.SettingMaxFrameSize, Val: 16384},
        },
    },
    {
        Name: "Safari_17_MacOS",
        ClientHelloID: tls.HelloSafari_17_0,
        HTTP2Settings: []http2.Setting{
            {ID: http2.SettingHeaderTableSize, Val: 4096},
            {ID: http2.SettingEnablePush, Val: 1},
            {ID: http2.SettingMaxConcurrentStreams, Val: 100},
            {ID: http2.SettingInitialWindowSize, Val: 2097152},
        },
    },
    {
        Name: "Edge_120_Windows",
        ClientHelloID: tls.HelloChrome_120, // Edge uses Chromium
        HTTP2Settings: []http2.Setting{
            {ID: http2.SettingHeaderTableSize, Val: 65536},
            {ID: http2.SettingEnablePush, Val: 1},
            {ID: http2.SettingMaxConcurrentStreams, Val: 1000},
            {ID: http2.SettingInitialWindowSize, Val: 6291456},
        },
    },
}

func GetRandomProfile() BrowserProfile {
    return profiles[rand.Intn(len(profiles))]
}

func (p *BrowserProfile) BuildTLSConfig() *tls.Config {
    return &tls.Config{
        GetClientHelloSpec: func(hello *tls.ClientHelloMsg) (*tls.ClientHelloSpec, error) {
            return &tls.ClientHelloSpec{
                TLSVersMax: tls.VersionTLS13,
                TLSVersMin: tls.VersionTLS12,
                CipherSuites: p.ClientHelloID.CipherSuites,
                Extensions: p.ClientHelloID.Extensions,
            }, nil
        },
    }
}
```

**Randomization Logic:**
```go
type FingerprintManager struct {
    profiles []BrowserProfile
    mu       sync.RWMutex
    cache    map[string]BrowserProfile // Domain → Profile mapping
}

func (fm *FingerprintManager) GetProfileForDomain(domain string) BrowserProfile {
    fm.mu.RLock()
    if profile, ok := fm.cache[domain]; ok {
        fm.mu.RUnlock()
        return profile
    }
    fm.mu.RUnlock()

    // Assign random profile for new domain
    profile := GetRandomProfile()

    fm.mu.Lock()
    fm.cache[domain] = profile
    fm.mu.Unlock()

    return profile
}
```

**Success Criteria:**
- [ ] 4 browser profiles implemented
- [ ] uTLS integration working
- [ ] Per-domain profile caching
- [ ] TLS handshake succeeds with all profiles

---

### Task 2.3: HTTP/2 Customization

**File:** `internal/http2/customizer.go`

**SETTINGS Frame Randomization:**
```go
func (p *BrowserProfile) CustomizeHTTP2Transport(t *http2.Transport) {
    // Apply SETTINGS from profile
    t.Settings = p.HTTP2Settings

    // Add slight randomization to avoid perfect fingerprinting
    for i := range t.Settings {
        if t.Settings[i].ID == http2.SettingInitialWindowSize {
            // Add ±10% jitter to window size
            jitter := int32(float64(t.Settings[i].Val) * 0.1)
            t.Settings[i].Val = uint32(int32(t.Settings[i].Val) + rand.Int31n(jitter*2) - jitter)
        }
    }

    // Priority frames (Chrome-specific)
    if strings.Contains(p.Name, "Chrome") {
        t.PriorityFrames = []http2.PriorityFrame{
            {StreamID: 3, PriorityParam: http2.PriorityParam{Weight: 201, Exclusive: false}},
            {StreamID: 5, PriorityParam: http2.PriorityParam{Weight: 101, Exclusive: false}},
        }
    }
}
```

**HPACK Compression:**
```go
func (c *Customizer) SetHPACKTableSize(size uint32) {
    // Dynamic table size (default: 4096 for most browsers)
    c.hpackEncoder.SetMaxDynamicTableSize(size)
}
```

**Success Criteria:**
- [ ] SETTINGS frame matches browser profiles
- [ ] Priority frames sent (Chrome/Edge only)
- [ ] HPACK table size configurable
- [ ] HTTP/2 negotiation successful

---

### Task 2.4: Proxy Server Implementation

**File:** `cmd/spider-network-proxy/main.go`

**Main Server:**
```go
func main() {
    cfg := config.LoadConfig("configs/production.toml")

    fm := tls.NewFingerprintManager()

    // HTTP Proxy
    httpProxy := goproxy.NewProxyHttpServer()
    httpProxy.OnRequest().DoFunc(func(req *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
        // Get profile for target domain
        profile := fm.GetProfileForDomain(req.URL.Hostname())

        // Customize TLS + HTTP/2
        transport := &http.Transport{
            TLSClientConfig: profile.BuildTLSConfig(),
            // ... other settings
        }

        ctx.RoundTripper = transport
        return req, nil
    })

    // SOCKS5 Proxy
    socks5Server, _ := socks5.New(&socks5.Config{
        Dial: func(ctx context.Context, network, addr string) (net.Conn, error) {
            // Apply uTLS wrapper
            profile := fm.GetProfileForDomain(addr)
            return tls.DialWithProfile(network, addr, profile)
        },
    })

    // Start servers
    go http.ListenAndServe(cfg.Proxy.HTTPListen, httpProxy)
    http.ListenAndServe(cfg.Proxy.SOCKS5Listen, socks5Server)
}
```

**Config File:** `configs/production.toml`
```toml
[proxy]
http_listen = "127.0.0.1:8080"
socks5_listen = "127.0.0.1:1080"

[tls]
fingerprint_rotation = true
profile_cache_ttl_hours = 24

[http2]
randomize_settings = true
priority_frames_enabled = true

[metrics]
enabled = true
listen = "127.0.0.1:9090"
```

**Success Criteria:**
- [ ] HTTP proxy listening on :8080
- [ ] SOCKS5 proxy listening on :1080
- [ ] uTLS applied to all TLS connections
- [ ] Config loaded from TOML

---

### Task 2.5: Integration with Spider-Nix

**File:** `src/spider_nix/session.py`

**Proxy Configuration:**
```python
class SessionManager:
    def __init__(self, config: CrawlerConfig):
        self.config = config

        # Add spider-nix-network proxy
        self.network_proxy = "http://127.0.0.1:8080"
        self.socks5_proxy = "socks5://127.0.0.1:1080"

    async def create_session(self) -> httpx.AsyncClient:
        proxies = {
            "http://": self.network_proxy,
            "https://": self.network_proxy,
        }

        return httpx.AsyncClient(
            proxies=proxies,
            timeout=self.config.timeout,
            follow_redirects=True,
        )
```

**Playwright Integration:**
```python
# src/spider_nix/browser.py
async def _create_browser_context(self):
    context = await self.browser.new_context(
        proxy={
            "server": "http://127.0.0.1:8080",  # Route through Go proxy
        },
        # ... other settings
    )
```

**Success Criteria:**
- [ ] spider-nix routes HTTP through Go proxy
- [ ] Playwright routes browser through proxy
- [ ] TLS fingerprints verified as randomized
- [ ] No performance degradation (< 10ms overhead)

---

## Phase 1C: Vision OSINT (Multimodal Extraction)

**Goal:** CSS-independent extraction via Vision-DOM fusion
**Duration:** 8-10 days
**Token Cost:** ~10,000 tokens

### Task 3.1: Data Models

**File:** `src/spider_nix/extraction/models.py` (NEW)

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

@dataclass
class BoundingBox:
    """Normalized bounding box (0-1 coordinates)"""
    x: float  # Left edge (0 = left, 1 = right)
    y: float  # Top edge (0 = top, 1 = bottom)
    width: float  # Box width
    height: float  # Box height

    def area(self) -> float:
        return self.width * self.height

    def intersects(self, other: "BoundingBox") -> bool:
        return not (
            self.x + self.width < other.x or
            other.x + other.width < self.x or
            self.y + self.height < other.y or
            other.y + other.height < self.y
        )

@dataclass
class VisionDetection:
    """Element detected by vision model"""
    element_type: str  # button, link, text, image, input, form, nav
    bounding_box: BoundingBox
    confidence: float  # 0.0-1.0
    text_content: str | None = None  # OCR text
    ocr_confidence: float | None = None
    attributes: dict = field(default_factory=dict)  # Visual attributes
    model_id: str = "clip-vit-b32"  # Which model detected it

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        return self.confidence >= threshold

@dataclass
class DOMElement:
    """Element extracted from DOM"""
    xpath: str
    css_selector: str
    tag_name: str
    text_content: str
    attributes: dict
    bounding_box: BoundingBox | None = None  # From JS getBoundingClientRect()

    def matches_type(self, element_type: str) -> bool:
        """Check if DOM element matches vision detection type"""
        type_map = {
            "button": ["button", "input[type=button]", "input[type=submit]"],
            "link": ["a"],
            "input": ["input", "textarea"],
            "image": ["img"],
            "form": ["form"],
        }
        return self.tag_name.lower() in type_map.get(element_type, [])

@dataclass
class FusedElement:
    """High-confidence element from Vision+DOM fusion"""
    vision: VisionDetection
    dom: DOMElement | None  # None if vision-only
    iou_score: float  # Intersection over Union quality (0-1)
    extraction_confidence: float  # Combined confidence
    extraction_method: Literal["vision_only", "dom_only", "fused"]
    fusion_metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def selector(self) -> str | None:
        """Get best selector (prefer XPath > CSS > None)"""
        if self.dom:
            return self.dom.xpath or self.dom.css_selector
        return None

    @property
    def is_resilient(self) -> bool:
        """Fused elements are resilient to CSS changes"""
        return self.extraction_method == "fused" and self.iou_score > 0.7

@dataclass
class ExtractionResult:
    """Complete extraction result for a page"""
    url: str
    screenshot_path: str
    vision_detections: list[VisionDetection]
    dom_elements: list[DOMElement]
    fused_elements: list[FusedElement]
    extraction_time_ms: float
    model_inference_time_ms: float
    fusion_time_ms: float
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
```

**Success Criteria:**
- [ ] All dataclasses defined
- [ ] Methods tested (area(), intersects(), is_high_confidence())
- [ ] Type hints correct
- [ ] Serializable to JSON

---

### Task 3.2: Vision Client (ml-offload-api Integration)

**File:** `src/spider_nix/ml/vision_client.py` (NEW)

```python
import httpx
import asyncio
from pathlib import Path
from typing import List
from ..extraction.models import VisionDetection, BoundingBox

class VisionClient:
    """Client for ml-offload-api vision inference"""

    def __init__(self, api_url: str = "http://localhost:9000"):
        self.api_url = api_url
        self.client = httpx.AsyncClient(timeout=60.0)
        self.model_loaded = False

    async def ensure_model_loaded(self, model_id: str = "llava-v1.5-7b-q4"):
        """Load vision model if not already loaded"""
        if self.model_loaded:
            return

        # Check if model already loaded
        response = await self.client.get(f"{self.api_url}/models")
        models = response.json()

        loaded_models = [m["name"] for m in models if m.get("loaded", False)]
        if model_id in loaded_models:
            self.model_loaded = True
            return

        # Load model
        load_response = await self.client.post(
            f"{self.api_url}/load",
            json={
                "model_name": model_id,
                "backend": "llamacpp",  # llama.cpp supports vision models
            }
        )
        load_response.raise_for_status()
        self.model_loaded = True

    async def analyze_screenshot(
        self,
        screenshot_path: Path,
        prompt: str = "Identify all interactive elements (buttons, links, inputs, forms) in this screenshot. For each element, provide: type, bounding box coordinates (normalized 0-1), and visible text."
    ) -> List[VisionDetection]:
        """
        Analyze screenshot with vision model

        Returns:
            List of detected elements with bounding boxes
        """
        await self.ensure_model_loaded()

        # Read screenshot
        with open(screenshot_path, "rb") as f:
            screenshot_bytes = f.read()

        # Send to ml-offload-api
        # Note: Using OpenAI-compatible endpoint with vision
        response = await self.client.post(
            f"{self.api_url}/v1/chat/completions",
            json={
                "model": "llava-v1.5-7b-q4",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{self._encode_image(screenshot_bytes)}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 2000,
                "temperature": 0.1,  # Low temp for consistent parsing
            }
        )
        response.raise_for_status()

        # Parse response
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # Parse structured output into VisionDetections
        return self._parse_vision_output(content)

    def _encode_image(self, image_bytes: bytes) -> str:
        import base64
        return base64.b64encode(image_bytes).decode('utf-8')

    def _parse_vision_output(self, output: str) -> List[VisionDetection]:
        """
        Parse model output into structured VisionDetection objects

        Expected format (from model):
        ```
        1. Button at (0.5, 0.3, 0.1, 0.05) - "Submit"
        2. Input at (0.4, 0.2, 0.2, 0.03) - Email field
        3. Link at (0.1, 0.9, 0.15, 0.02) - "Privacy Policy"
        ```
        """
        import re

        detections = []

        # Regex to parse lines
        pattern = r'(\w+)\s+at\s+\(([0-9.]+),\s*([0-9.]+),\s*([0-9.]+),\s*([0-9.]+)\)\s*-\s*"?([^"]*)"?'

        for match in re.finditer(pattern, output, re.MULTILINE):
            element_type = match.group(1).lower()
            x, y, w, h = map(float, match.groups()[1:5])
            text = match.group(6).strip()

            detection = VisionDetection(
                element_type=element_type,
                bounding_box=BoundingBox(x=x, y=y, width=w, height=h),
                confidence=0.85,  # Default confidence (model-dependent)
                text_content=text if text else None,
                ocr_confidence=0.9 if text else None,
                model_id="llava-v1.5-7b-q4"
            )
            detections.append(detection)

        return detections

    async def close(self):
        await self.client.aclose()
```

**Alternative: CLIP-based Detection** (if LLaVA not available)
```python
async def analyze_with_clip(self, screenshot_path: Path) -> List[VisionDetection]:
    """
    Use CLIP for zero-shot element classification

    Strategy:
    1. Segment screenshot into grid (e.g., 10x10)
    2. For each cell, classify with CLIP:
        - "a button", "a link", "an input field", "text", "image"
    3. Merge adjacent cells of same type into bounding boxes
    """
    # TODO: Implement grid-based CLIP classification
    pass
```

**Success Criteria:**
- [ ] VisionClient connects to ml-offload-api
- [ ] Model loads successfully (LLaVA or CLIP)
- [ ] Screenshot analysis returns structured detections
- [ ] Bounding boxes normalized to 0-1
- [ ] Parsing handles malformed model output gracefully

---

### Task 3.3: DOM Analyzer

**File:** `src/spider_nix/extraction/dom_analyzer.py` (NEW)

```python
import asyncio
from lxml import html, etree
from bs4 import BeautifulSoup
from typing import List
from ..extraction.models import DOMElement, BoundingBox

class DOMAnalyzer:
    """Parallel HTML/DOM analysis with position calculation"""

    def __init__(self):
        self.parser = html.HTMLParser()

    async def analyze_page(
        self,
        html_content: str,
        page_handle = None  # Playwright page for getBoundingClientRect
    ) -> List[DOMElement]:
        """
        Extract all interactive elements from DOM with positions

        Args:
            html_content: Raw HTML
            page_handle: Playwright page (optional, for position data)

        Returns:
            List of DOM elements with bounding boxes
        """
        # Parse HTML with lxml (fast) + BeautifulSoup (robust)
        tree = html.fromstring(html_content)
        soup = BeautifulSoup(html_content, 'lxml')

        elements = []

        # Extract all interactive elements
        selectors = [
            ("button", "//button"),
            ("a", "//a[@href]"),
            ("input", "//input"),
            ("textarea", "//textarea"),
            ("select", "//select"),
            ("form", "//form"),
        ]

        for tag, xpath in selectors:
            nodes = tree.xpath(xpath)

            for node in nodes:
                # Generate XPath and CSS selector
                xpath_expr = tree.getpath(node)
                css_selector = self._generate_css_selector(node)

                # Extract attributes
                attrs = dict(node.attrib)
                text = node.text_content().strip()

                # Get position if Playwright page available
                bbox = None
                if page_handle:
                    bbox = await self._get_element_position(page_handle, css_selector)

                element = DOMElement(
                    xpath=xpath_expr,
                    css_selector=css_selector,
                    tag_name=tag,
                    text_content=text,
                    attributes=attrs,
                    bounding_box=bbox
                )
                elements.append(element)

        return elements

    def _generate_css_selector(self, node) -> str:
        """Generate unique CSS selector for element"""
        # Priority: ID > unique class > nth-child path

        # Check for ID
        if node.get('id'):
            return f"#{node.get('id')}"

        # Check for unique class
        classes = node.get('class', '').split()
        for cls in classes:
            if cls:
                selector = f"{node.tag}.{cls}"
                # TODO: Verify uniqueness with tree.cssselect()
                return selector

        # Fallback: nth-child path
        path = []
        current = node
        while current.getparent() is not None:
            parent = current.getparent()
            siblings = [n for n in parent if n.tag == current.tag]
            index = siblings.index(current) + 1
            path.insert(0, f"{current.tag}:nth-child({index})")
            current = parent

        return " > ".join(path)

    async def _get_element_position(self, page, css_selector: str) -> BoundingBox | None:
        """Get element position using Playwright"""
        try:
            element = await page.query_selector(css_selector)
            if not element:
                return None

            # Get bounding box via JS
            box = await element.bounding_box()
            if not box:
                return None

            # Get viewport size for normalization
            viewport = page.viewport_size

            # Normalize to 0-1
            return BoundingBox(
                x=box['x'] / viewport['width'],
                y=box['y'] / viewport['height'],
                width=box['width'] / viewport['width'],
                height=box['height'] / viewport['height']
            )
        except Exception as e:
            # Element not visible or removed
            return None
```

**Success Criteria:**
- [ ] Extracts all interactive elements (buttons, links, inputs, forms)
- [ ] Generates XPath and CSS selectors
- [ ] Calculates bounding boxes via Playwright
- [ ] Normalizes positions to 0-1
- [ ] Handles dynamic content (elements removed/added)

---

### Task 3.4: Fusion Engine (Core Innovation)

**File:** `src/spider_nix/extraction/fusion_engine.py` (NEW)

```python
from typing import List, Tuple
from ..extraction.models import (
    VisionDetection,
    DOMElement,
    FusedElement,
    BoundingBox
)

class FusionEngine:
    """Vision-DOM fusion using IoU (Intersection over Union)"""

    def __init__(self, iou_threshold: float = 0.5):
        self.iou_threshold = iou_threshold

    def fuse(
        self,
        vision_detections: List[VisionDetection],
        dom_elements: List[DOMElement]
    ) -> List[FusedElement]:
        """
        Match vision detections to DOM elements using IoU algorithm

        Algorithm:
        1. For each vision detection:
           2. Find DOM elements with matching type
           3. Calculate IoU with each matching element
           4. If IoU > threshold: FUSED
           5. Else: VISION_ONLY
        6. DOM elements not matched: DOM_ONLY (low confidence)

        Returns:
            List of fused elements with confidence scores
        """
        fused = []
        matched_dom_indices = set()

        # Phase 1: Match vision → DOM
        for vision in vision_detections:
            best_match = None
            best_iou = 0.0
            best_dom_idx = None

            # Find matching DOM elements by type
            for idx, dom in enumerate(dom_elements):
                if idx in matched_dom_indices:
                    continue

                # Type compatibility check
                if not dom.matches_type(vision.element_type):
                    continue

                # Position compatibility check
                if dom.bounding_box is None:
                    continue

                # Calculate IoU
                iou = self.calculate_iou(vision.bounding_box, dom.bounding_box)

                if iou > best_iou:
                    best_iou = iou
                    best_match = dom
                    best_dom_idx = idx

            # Create FusedElement
            if best_iou >= self.iou_threshold:
                # FUSED: High confidence
                fused_elem = FusedElement(
                    vision=vision,
                    dom=best_match,
                    iou_score=best_iou,
                    extraction_confidence=self._calculate_confidence(vision, best_match, best_iou),
                    extraction_method="fused",
                    fusion_metadata={
                        "vision_confidence": vision.confidence,
                        "iou": best_iou,
                        "type_match": True
                    }
                )
                matched_dom_indices.add(best_dom_idx)
            else:
                # VISION_ONLY: Medium confidence
                fused_elem = FusedElement(
                    vision=vision,
                    dom=None,
                    iou_score=0.0,
                    extraction_confidence=vision.confidence * 0.7,  # Penalize non-fusion
                    extraction_method="vision_only",
                    fusion_metadata={
                        "vision_confidence": vision.confidence,
                        "reason": "no_dom_match"
                    }
                )

            fused.append(fused_elem)

        # Phase 2: Unmatched DOM elements (DOM_ONLY)
        for idx, dom in enumerate(dom_elements):
            if idx in matched_dom_indices:
                continue

            # Create vision detection from DOM for consistency
            synthetic_vision = VisionDetection(
                element_type=dom.tag_name,
                bounding_box=dom.bounding_box or BoundingBox(0, 0, 0, 0),
                confidence=0.5,  # Low confidence (no visual confirmation)
                text_content=dom.text_content,
                model_id="dom_fallback"
            )

            fused_elem = FusedElement(
                vision=synthetic_vision,
                dom=dom,
                iou_score=0.0,
                extraction_confidence=0.5,  # Low confidence
                extraction_method="dom_only",
                fusion_metadata={
                    "reason": "no_vision_match"
                }
            )
            fused.append(fused_elem)

        return fused

    def calculate_iou(self, box1: BoundingBox, box2: BoundingBox) -> float:
        """
        Calculate Intersection over Union (IoU)

        Formula:
            IoU = Area(Intersection) / Area(Union)

        Returns:
            Score 0.0-1.0 (1.0 = perfect overlap)
        """
        # Calculate intersection
        x_overlap = max(0, min(box1.x + box1.width, box2.x + box2.width) - max(box1.x, box2.x))
        y_overlap = max(0, min(box1.y + box1.height, box2.y + box2.height) - max(box1.y, box2.y))
        intersection = x_overlap * y_overlap

        # Calculate union
        area1 = box1.area()
        area2 = box2.area()
        union = area1 + area2 - intersection

        # IoU
        return intersection / union if union > 0 else 0.0

    def _calculate_confidence(
        self,
        vision: VisionDetection,
        dom: DOMElement,
        iou: float
    ) -> float:
        """
        Calculate combined confidence score

        Formula:
            confidence = (vision_conf * 0.6) + (iou * 0.3) + (type_match * 0.1)
        """
        vision_conf = vision.confidence
        iou_score = iou
        type_match = 1.0 if dom.matches_type(vision.element_type) else 0.5

        return (vision_conf * 0.6) + (iou_score * 0.3) + (type_match * 0.1)
```

**Success Criteria:**
- [ ] IoU algorithm correctly calculates overlap
- [ ] Vision→DOM matching works with 80%+ accuracy
- [ ] Fused elements have higher confidence than vision-only
- [ ] Handles edge cases (no DOM match, no vision match)
- [ ] Performance: <50ms for 100 elements

---

### Task 3.5: End-to-End Pipeline Integration

**File:** `src/spider_nix/extraction/extractor.py` (NEW)

```python
import asyncio
from pathlib import Path
from typing import Optional
from ..browser import BrowserCrawler
from ..ml.vision_client import VisionClient
from .dom_analyzer import DOMAnalyzer
from .fusion_engine import FusionEngine
from .models import ExtractionResult
import time

class MultimodalExtractor:
    """End-to-end vision-DOM fusion pipeline"""

    def __init__(
        self,
        vision_client: VisionClient,
        iou_threshold: float = 0.5
    ):
        self.vision_client = vision_client
        self.dom_analyzer = DOMAnalyzer()
        self.fusion_engine = FusionEngine(iou_threshold=iou_threshold)

    async def extract(
        self,
        url: str,
        browser_crawler: BrowserCrawler,
        screenshot_path: Optional[Path] = None
    ) -> ExtractionResult:
        """
        Complete extraction pipeline:
        1. Render page + capture screenshot
        2. Vision analysis (parallel)
        3. DOM analysis (parallel)
        4. Fusion

        Returns:
            ExtractionResult with fused elements
        """
        start_time = time.time()

        # Step 1: Render page
        if screenshot_path is None:
            screenshot_path = Path(f"/tmp/screenshot_{int(time.time())}.png")

        page = await browser_crawler._create_page()
        await page.goto(url, wait_until='networkidle')
        await page.screenshot(path=str(screenshot_path))

        html_content = await page.content()

        # Step 2 & 3: Vision + DOM analysis (parallel)
        vision_start = time.time()
        dom_task = asyncio.create_task(
            self.dom_analyzer.analyze_page(html_content, page)
        )
        vision_task = asyncio.create_task(
            self.vision_client.analyze_screenshot(screenshot_path)
        )

        dom_elements, vision_detections = await asyncio.gather(dom_task, vision_task)
        vision_time = (time.time() - vision_start) * 1000

        # Step 4: Fusion
        fusion_start = time.time()
        fused_elements = self.fusion_engine.fuse(vision_detections, dom_elements)
        fusion_time = (time.time() - fusion_start) * 1000

        total_time = (time.time() - start_time) * 1000

        await page.close()

        return ExtractionResult(
            url=url,
            screenshot_path=str(screenshot_path),
            vision_detections=vision_detections,
            dom_elements=dom_elements,
            fused_elements=fused_elements,
            extraction_time_ms=total_time,
            model_inference_time_ms=vision_time,
            fusion_time_ms=fusion_time,
            metadata={
                "vision_detections_count": len(vision_detections),
                "dom_elements_count": len(dom_elements),
                "fused_count": len([f for f in fused_elements if f.extraction_method == "fused"]),
                "vision_only_count": len([f for f in fused_elements if f.extraction_method == "vision_only"]),
                "dom_only_count": len([f for f in fused_elements if f.extraction_method == "dom_only"]),
            }
        )
```

**CLI Integration:** `src/spider_nix/cli.py`
```python
@recon_app.command("multimodal")
def multimodal_extract(
    url: str = typer.Argument(..., help="Target URL"),
    output: Path = typer.Option("extraction.json", help="Output file"),
):
    """Extract elements using vision-DOM fusion"""

    async def run():
        config = CrawlerConfig()
        browser = BrowserCrawler(config, proxy_rotator=None)
        vision = VisionClient()
        extractor = MultimodalExtractor(vision)

        result = await extractor.extract(url, browser)

        # Save results
        with open(output, 'w') as f:
            json.dump(asdict(result), f, indent=2, default=str)

        console.print(f"[green]✓[/green] Extracted {len(result.fused_elements)} elements")
        console.print(f"  Vision detections: {len(result.vision_detections)}")
        console.print(f"  DOM elements: {len(result.dom_elements)}")
        console.print(f"  Fused: {result.metadata['fused_count']}")
        console.print(f"  Time: {result.extraction_time_ms:.0f}ms")

    asyncio.run(run())
```

**Success Criteria:**
- [ ] End-to-end pipeline works on test URLs
- [ ] Vision + DOM run in parallel
- [ ] Extraction time < 3 seconds (p95)
- [ ] Fused elements > 50% of total
- [ ] CLI command works: `spider-nix recon multimodal https://example.com`

---

## Phase 1D: ML Feedback Loop

**Goal:** Adaptive strategies per domain based on success/failure patterns
**Duration:** 4-5 days
**Token Cost:** ~4,000 tokens

### Task 4.1: Database Schema Update

**File:** `src/spider_nix/ml/schema.sql`

**New Fields:**
```sql
-- Existing: crawl_attempts table
ALTER TABLE crawl_attempts ADD COLUMN vision_confidence REAL;
ALTER TABLE crawl_attempts ADD COLUMN fusion_method TEXT; -- "fused", "vision_only", "dom_only"
ALTER TABLE crawl_attempts ADD COLUMN extraction_time_ms REAL;

-- New index for ML queries
CREATE INDEX IF NOT EXISTS idx_fusion_method ON crawl_attempts(fusion_method);
CREATE INDEX IF NOT EXISTS idx_vision_confidence ON crawl_attempts(vision_confidence);
```

**Migration Script:** `src/spider_nix/ml/migrations/001_vision_fields.py`
```python
async def migrate(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("ALTER TABLE crawl_attempts ADD COLUMN vision_confidence REAL")
        await db.execute("ALTER TABLE crawl_attempts ADD COLUMN fusion_method TEXT")
        await db.execute("ALTER TABLE crawl_attempts ADD COLUMN extraction_time_ms REAL")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_fusion_method ON crawl_attempts(fusion_method)")
        await db.commit()
```

**Success Criteria:**
- [ ] Migration runs without errors
- [ ] New columns appear in schema
- [ ] Existing data preserved
- [ ] Indices created

---

### Task 4.2: Failure Classifier (Rule-Based MVP)

**File:** `src/spider_nix/ml/failure_classifier.py` (NEW)

```python
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass

class FailureClass(str, Enum):
    SUCCESS = "success"
    RATE_LIMIT = "rate_limit"
    FINGERPRINT_DETECTED = "fingerprint_detected"
    CAPTCHA = "captcha"
    IP_BLOCKED = "ip_blocked"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"

@dataclass
class ClassificationResult:
    failure_class: FailureClass
    confidence: float  # 0.0-1.0
    evidence: Dict[str, any]

class FailureClassifier:
    """Rule-based failure classification (MVP)"""

    def classify(
        self,
        status_code: int,
        response_headers: Dict[str, str],
        response_body: str,
        response_time_ms: float,
        exception: Optional[Exception] = None
    ) -> ClassificationResult:
        """
        Classify why request failed

        Returns:
            ClassificationResult with failure class and confidence
        """
        # SUCCESS
        if 200 <= status_code < 300:
            # Check for soft blocks (200 but blocked content)
            if self._is_soft_block(response_body):
                return ClassificationResult(
                    failure_class=FailureClass.FINGERPRINT_DETECTED,
                    confidence=0.85,
                    evidence={"reason": "soft_block_in_200"}
                )
            return ClassificationResult(
                failure_class=FailureClass.SUCCESS,
                confidence=1.0,
                evidence={}
            )

        # RATE_LIMIT
        if status_code == 429 or "rate limit" in response_body.lower():
            return ClassificationResult(
                failure_class=FailureClass.RATE_LIMIT,
                confidence=0.95,
                evidence={
                    "status_code": status_code,
                    "retry_after": response_headers.get("Retry-After")
                }
            )

        # CAPTCHA
        if self._is_captcha(response_body, response_headers):
            return ClassificationResult(
                failure_class=FailureClass.CAPTCHA,
                confidence=0.90,
                evidence={
                    "captcha_provider": self._detect_captcha_provider(response_body)
                }
            )

        # FINGERPRINT_DETECTED (bot detection)
        if status_code in [403, 401] or self._is_bot_challenge(response_body, response_headers):
            return ClassificationResult(
                failure_class=FailureClass.FINGERPRINT_DETECTED,
                confidence=0.85,
                evidence={
                    "status_code": status_code,
                    "waf": self._detect_waf(response_headers)
                }
            )

        # IP_BLOCKED
        if status_code == 403 and "ip" in response_body.lower():
            return ClassificationResult(
                failure_class=FailureClass.IP_BLOCKED,
                confidence=0.80,
                evidence={"status_code": status_code}
            )

        # TIMEOUT
        if exception and isinstance(exception, TimeoutError):
            return ClassificationResult(
                failure_class=FailureClass.TIMEOUT,
                confidence=1.0,
                evidence={"response_time_ms": response_time_ms}
            )

        # SERVER_ERROR
        if 500 <= status_code < 600:
            return ClassificationResult(
                failure_class=FailureClass.SERVER_ERROR,
                confidence=0.95,
                evidence={"status_code": status_code}
            )

        # NETWORK_ERROR
        if exception and isinstance(exception, (ConnectionError, OSError)):
            return ClassificationResult(
                failure_class=FailureClass.NETWORK_ERROR,
                confidence=0.95,
                evidence={"exception": str(exception)}
            )

        # UNKNOWN
        return ClassificationResult(
            failure_class=FailureClass.UNKNOWN,
            confidence=0.5,
            evidence={"status_code": status_code}
        )

    def _is_captcha(self, body: str, headers: Dict[str, str]) -> bool:
        """Detect CAPTCHA challenges"""
        captcha_indicators = [
            "recaptcha",
            "hcaptcha",
            "cloudflare challenge",
            "verify you are human",
            "captcha",
            "cf-chl-bypass",
        ]
        body_lower = body.lower()
        return any(indicator in body_lower for indicator in captcha_indicators)

    def _detect_captcha_provider(self, body: str) -> str:
        """Identify CAPTCHA provider"""
        if "recaptcha" in body.lower():
            return "recaptcha"
        elif "hcaptcha" in body.lower():
            return "hcaptcha"
        elif "cloudflare" in body.lower():
            return "cloudflare"
        return "unknown"

    def _is_bot_challenge(self, body: str, headers: Dict[str, str]) -> bool:
        """Detect bot challenges (Cloudflare, DataDome, PerimeterX)"""
        # Cloudflare
        if headers.get("Server") == "cloudflare" and "cf_clearance" in body.lower():
            return True

        # DataDome
        if "datadome" in body.lower():
            return True

        # PerimeterX
        if "_px" in body.lower() or "perimeterx" in body.lower():
            return True

        # Generic bot block messages
        bot_messages = [
            "access denied",
            "blocked",
            "automated",
            "bot detected",
            "suspicious activity"
        ]
        return any(msg in body.lower() for msg in bot_messages)

    def _is_soft_block(self, body: str) -> bool:
        """Detect soft blocks (200 status but blocked content)"""
        if len(body) < 500:  # Suspiciously small response
            return True
        return False

    def _detect_waf(self, headers: Dict[str, str]) -> Optional[str]:
        """Detect Web Application Firewall"""
        waf_headers = {
            "cloudflare": ["cf-ray", "cf-cache-status"],
            "akamai": ["akamai-grn"],
            "incapsula": ["x-cdn"],
            "aws-waf": ["x-amzn-requestid"],
        }

        for waf, header_keys in waf_headers.items():
            if any(key.lower() in [h.lower() for h in headers.keys()] for key in header_keys):
                return waf

        return None
```

**Success Criteria:**
- [ ] Classifies 8 failure types correctly
- [ ] CAPTCHA detection works (reCAPTCHA, hCaptcha, Cloudflare)
- [ ] WAF detection works (Cloudflare, DataDome, PerimeterX)
- [ ] Confidence scores calibrated
- [ ] Unit tests pass (mock responses)

---

### Task 4.3: Strategy Selector (Epsilon-Greedy)

**File:** `src/spider_nix/ml/strategy_selector.py` (NEW)

```python
import random
from typing import Dict, List
from enum import Enum

class EvasionStrategy(str, Enum):
    TLS_FINGERPRINT_ROTATION = "tls_fingerprint_rotation"
    PROXY_ROTATION = "proxy_rotation"
    BROWSER_MODE = "browser_mode"  # Use Playwright instead of httpx
    EXTENDED_DELAYS = "extended_delays"
    HEADERS_VARIATION = "headers_variation"
    COOKIE_PERSISTENCE = "cookie_persistence"

class StrategySelector:
    """Epsilon-greedy multi-armed bandit for strategy selection"""

    def __init__(self, epsilon: float = 0.1):
        """
        Args:
            epsilon: Exploration rate (0.1 = 10% random exploration)
        """
        self.epsilon = epsilon
        self.strategy_stats: Dict[str, Dict[EvasionStrategy, dict]] = {}
        # Format: {domain: {strategy: {"success": int, "failure": int}}}

    def select_strategy(self, domain: str) -> EvasionStrategy:
        """
        Select best strategy for domain using epsilon-greedy

        Algorithm:
        - With probability epsilon: explore (random strategy)
        - With probability (1-epsilon): exploit (best strategy)
        """
        if domain not in self.strategy_stats:
            # First time seeing domain: initialize
            self.strategy_stats[domain] = {
                strategy: {"success": 0, "failure": 0}
                for strategy in EvasionStrategy
            }

        # Exploration vs Exploitation
        if random.random() < self.epsilon:
            # EXPLORE: Random strategy
            return random.choice(list(EvasionStrategy))
        else:
            # EXPLOIT: Best strategy
            return self._best_strategy(domain)

    def _best_strategy(self, domain: str) -> EvasionStrategy:
        """Select strategy with highest success rate"""
        stats = self.strategy_stats[domain]

        best_strategy = None
        best_rate = -1

        for strategy, counts in stats.items():
            total = counts["success"] + counts["failure"]
            if total == 0:
                # Never tried: high priority
                success_rate = 1.0
            else:
                success_rate = counts["success"] / total

            if success_rate > best_rate:
                best_rate = success_rate
                best_strategy = strategy

        return best_strategy or EvasionStrategy.TLS_FINGERPRINT_ROTATION

    def update(self, domain: str, strategy: EvasionStrategy, success: bool):
        """Update strategy statistics after request"""
        if domain not in self.strategy_stats:
            self.strategy_stats[domain] = {
                s: {"success": 0, "failure": 0} for s in EvasionStrategy
            }

        if success:
            self.strategy_stats[domain][strategy]["success"] += 1
        else:
            self.strategy_stats[domain][strategy]["failure"] += 1

    def get_stats(self, domain: str) -> Dict[EvasionStrategy, dict]:
        """Get strategy statistics for domain"""
        return self.strategy_stats.get(domain, {})

    async def load_from_db(self, db_path: str):
        """Load historical stats from feedback.db"""
        import aiosqlite

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("""
                SELECT site_domain, strategy_name, success_count, failure_count
                FROM strategy_effectiveness
            """)

            rows = await cursor.fetchall()
            for domain, strategy_name, success, failure in rows:
                if domain not in self.strategy_stats:
                    self.strategy_stats[domain] = {}

                try:
                    strategy = EvasionStrategy(strategy_name)
                    self.strategy_stats[domain][strategy] = {
                        "success": success,
                        "failure": failure
                    }
                except ValueError:
                    # Unknown strategy in DB
                    continue

    async def save_to_db(self, db_path: str):
        """Persist stats to feedback.db"""
        import aiosqlite

        async with aiosqlite.connect(db_path) as db:
            for domain, strategies in self.strategy_stats.items():
                for strategy, counts in strategies.items():
                    await db.execute("""
                        INSERT INTO strategy_effectiveness
                        (site_domain, strategy_name, success_count, failure_count)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(site_domain, strategy_name) DO UPDATE SET
                            success_count = excluded.success_count,
                            failure_count = excluded.failure_count
                    """, (domain, strategy.value, counts["success"], counts["failure"]))

            await db.commit()
```

**Integration with Crawler:** `src/spider_nix/crawler.py`
```python
class EnhancedCrawler:
    def __init__(self, config, feedback_logger, strategy_selector):
        self.config = config
        self.feedback_logger = feedback_logger
        self.strategy_selector = strategy_selector
        self.classifier = FailureClassifier()

    async def crawl_with_feedback(self, url: str):
        """Crawl with adaptive strategies"""
        domain = urlparse(url).netloc

        # Select strategy
        strategy = self.strategy_selector.select_strategy(domain)

        # Apply strategy
        config = self._apply_strategy(strategy)

        # Execute request
        try:
            response = await self.session.get(url, **config)

            # Classify result
            classification = self.classifier.classify(
                status_code=response.status_code,
                response_headers=dict(response.headers),
                response_body=response.text,
                response_time_ms=response.elapsed.total_seconds() * 1000
            )

            success = classification.failure_class == FailureClass.SUCCESS

            # Update strategy stats
            self.strategy_selector.update(domain, strategy, success)

            # Log to feedback.db
            await self.feedback_logger.log_attempt(
                url=url,
                status_code=response.status_code,
                failure_class=classification.failure_class.value,
                strategies_used=[strategy.value],
                response_time_ms=response.elapsed.total_seconds() * 1000,
                metadata={
                    "confidence": classification.confidence,
                    "evidence": classification.evidence
                }
            )

            return response

        except Exception as e:
            # Classify exception
            classification = self.classifier.classify(
                status_code=0,
                response_headers={},
                response_body="",
                response_time_ms=0,
                exception=e
            )

            # Update as failure
            self.strategy_selector.update(domain, strategy, False)

            raise

    def _apply_strategy(self, strategy: EvasionStrategy) -> dict:
        """Apply evasion strategy to request config"""
        config = {}

        if strategy == EvasionStrategy.TLS_FINGERPRINT_ROTATION:
            config["proxy"] = "http://127.0.0.1:8080"  # Route through Go proxy

        elif strategy == EvasionStrategy.EXTENDED_DELAYS:
            config["timeout"] = 30.0
            # Add delay before request
            import asyncio
            asyncio.sleep(random.uniform(2, 5))

        elif strategy == EvasionStrategy.HEADERS_VARIATION:
            config["headers"] = self._generate_varied_headers()

        # ... other strategies

        return config
```

**Success Criteria:**
- [ ] Epsilon-greedy selection works
- [ ] Strategies improve success rate over time
- [ ] Stats persist to/from feedback.db
- [ ] Integration with crawler complete
- [ ] Per-domain learning converges after 50+ requests

---

## Testing & Validation

### Integration Tests

**File:** `tests/test_osint_opsec_integration.py`

```python
import pytest
from spider_nix.extraction import MultimodalExtractor
from spider_nix.ml import VisionClient, FailureClassifier, StrategySelector

@pytest.mark.asyncio
async def test_full_pipeline():
    """Test complete OSINT | OPSEC pipeline"""

    # Setup
    vision = VisionClient()
    extractor = MultimodalExtractor(vision)
    classifier = FailureClassifier()
    selector = StrategySelector(epsilon=0.2)

    # Test extraction
    result = await extractor.extract("https://example.com", browser)

    assert len(result.fused_elements) > 0
    assert result.extraction_time_ms < 5000
    assert result.metadata["fused_count"] > 0

    # Test classification
    classification = classifier.classify(
        status_code=403,
        response_headers={"Server": "cloudflare"},
        response_body="Access Denied",
        response_time_ms=100
    )

    assert classification.failure_class == FailureClass.FINGERPRINT_DETECTED
    assert classification.confidence > 0.8

    # Test strategy selection
    strategy = selector.select_strategy("example.com")
    assert strategy in EvasionStrategy

    selector.update("example.com", strategy, True)
    stats = selector.get_stats("example.com")
    assert stats[strategy]["success"] == 1

@pytest.mark.asyncio
async def test_stealth_effectiveness():
    """Validate anti-detection effectiveness"""

    browser = BrowserCrawler(config, proxy_rotator)

    # Test against detection sites
    result = await browser.crawl("https://bot.sannysoft.com")

    assert "WebDriver: false" in result.content
    assert "Chrome: present" in result.content

@pytest.mark.asyncio
async def test_go_proxy_integration():
    """Verify Go proxy TLS randomization"""

    session = SessionManager(config)
    client = await session.create_session()

    # Route through Go proxy
    response = await client.get("https://www.howsmyssl.com/a/check")
    data = response.json()

    # Verify TLS fingerprint is not Python (indicates Go proxy working)
    assert "python" not in data.get("given_cipher_suites", "").lower()
```

---

## Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| **OPSEC** |  |  |
| Sannysoft detection flags | 0 red flags | TBD |
| Headless detection | NEGATIVE | TBD |
| Canvas fingerprint uniqueness | 100% unique per session | TBD |
| Go proxy overhead | < 10ms p95 | TBD |
| **OSINT** |  |  |
| Vision extraction accuracy | 80%+ | TBD |
| Fusion success rate | 50%+ fused | TBD |
| Extraction time | < 3s p95 | TBD |
| IoU threshold effectiveness | 0.5-0.7 optimal | TBD |
| **Intelligence** |  |  |
| Failure classification accuracy | 85%+ | TBD |
| Strategy convergence | 50 requests | TBD |
| Success rate improvement | +20% vs baseline | TBD |
| Feedback DB size | < 100MB / 10k requests | TBD |

---

## Deployment Checklist

- [ ] **Phase 1A: OPSEC Hardening**
  - [ ] Enhanced stealth patches deployed
  - [ ] Fingerprint randomization tested
  - [ ] Detection tests passing

- [ ] **Phase 1B: Network OPSEC**
  - [ ] Go proxy compiled and running
  - [ ] uTLS profiles validated
  - [ ] HTTP/2 customization working
  - [ ] Spider-nix routes through proxy

- [ ] **Phase 1C: Vision OSINT**
  - [ ] ml-offload-api connected
  - [ ] LLaVA/CLIP model loaded
  - [ ] Vision client working
  - [ ] DOM analyzer extracting elements
  - [ ] Fusion engine matching > 50%
  - [ ] End-to-end pipeline tested

- [ ] **Phase 1D: ML Feedback**
  - [ ] Database schema migrated
  - [ ] Failure classifier deployed
  - [ ] Strategy selector integrated
  - [ ] Feedback loop converging

- [ ] **Documentation**
  - [ ] README.private.md updated
  - [ ] ADRs written (adr-ledger/private/)
  - [ ] Runbook created
  - [ ] .gitignore covers sensitive configs

- [ ] **Monitoring**
  - [ ] Prometheus metrics exposed (Go proxy)
  - [ ] Logs configured (journalctl)
  - [ ] Success rate dashboard
  - [ ] VRAM monitoring

---

## Phase 2 Preview (Future)

After Phase 1 MVP is stable, consider:

1. **Advanced ML Classifier** (replace rule-based)
   - PyTorch model trained on feedback.db
   - Transfer learning from pre-trained anomaly detector

2. **IP Rotation Infrastructure**
   - Proxy pool management
   - Residential proxy integration
   - IP reputation tracking

3. **Agent-Hub Orchestration**
   - Multi-domain parallel crawling
   - Distributed task decomposition
   - gRPC coordination

4. **Advanced Evasion**
   - TCP/TLS spoofing (Rust)
   - Timing fingerprint evasion
   - Mouse movement simulation

---

## Cost Summary

| Phase | Token Cost | Implementation Days |
|-------|-----------|---------------------|
| 1A: OPSEC Hardening | ~3,000 | 3-5 |
| 1B: Network OPSEC | ~8,000 | 6-8 |
| 1C: Vision OSINT | ~10,000 | 8-10 |
| 1D: ML Feedback | ~4,000 | 4-5 |
| **TOTAL** | **~25,000** | **21-28 days** |

**Projected Delivery:** 4-6 weeks (single engineer, full-time)

---

**Next Step:** Awaiting approval to begin implementation starting with Phase 1A.
