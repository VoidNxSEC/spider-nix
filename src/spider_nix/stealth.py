"""Anti-detection stealth module for SpiderNix."""

import random
from typing import Any
from fake_useragent import UserAgent


# Pool of realistic browser fingerprints
# Expanded with MacBook, 4K, and ultrawide resolutions
SCREEN_RESOLUTIONS = [
    # Common Windows
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
    (1280, 720), (1600, 900), (1680, 1050), (1280, 1024),
    # High-end Windows/Linux
    (2560, 1440), (3840, 2160), (2560, 1080),  # Ultrawide
    # MacBook Pro
    (2560, 1600), (3024, 1964), (3456, 2234),  # M1/M2/M3 Pro
    (3840, 2400),  # 16" M1 Max
    # MacBook Air
    (2560, 1664), (2880, 1800),
]

WEBGL_VENDORS = [
    # NVIDIA (Windows/Linux)
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660)"),
    # Intel (Windows)
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) HD Graphics 620)"),
    # AMD (Windows/Linux)
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 6800 XT)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 7900 XT)"),
    ("AMD", "AMD Radeon RX 6700 XT"),
    # Apple Silicon (macOS)
    ("Apple", "Apple M1 GPU"),
    ("Apple", "Apple M2 GPU"),
    ("Apple", "Apple M3 GPU"),
    # Intel macOS (legacy)
    ("Intel Inc.", "Intel Iris OpenGL Engine"),
    ("Intel Inc.", "Intel Iris Pro OpenGL Engine"),
]

LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "pt-BR,pt;q=0.9,en;q=0.8",
    "es-ES,es;q=0.9,en;q=0.8",
    "de-DE,de;q=0.9,en;q=0.8",
]

TIMEZONES = [
    "America/New_York", "America/Los_Angeles", "America/Chicago",
    "America/Sao_Paulo", "Europe/London", "Europe/Berlin",
]


class StealthEngine:
    """Generate realistic browser fingerprints to avoid detection."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self._ua = UserAgent(browsers=["chrome", "firefox", "edge"])

        # Per-session noise factors (not per-request)
        self._canvas_noise = self._rng.uniform(0.00001, 0.0001)
        self._audio_noise = self._rng.uniform(0.000001, 0.00002)
    
    def get_user_agent(self) -> str:
        """Get random realistic user agent."""
        return self._ua.random
    
    def get_headers(self) -> dict[str, str]:
        """Generate realistic request headers."""
        ua = self.get_user_agent()
        
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": self._rng.choice(LANGUAGES),
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
    
    def get_fingerprint(self) -> dict[str, Any]:
        """Generate randomized browser fingerprint."""
        resolution = self._rng.choice(SCREEN_RESOLUTIONS)
        webgl_vendor, webgl_renderer = self._rng.choice(WEBGL_VENDORS)

        # Correlate platform with screen resolution for realism
        if resolution in [(2560, 1600), (3024, 1964), (3456, 2234), (3840, 2400), (2560, 1664), (2880, 1800)]:
            platform = "MacIntel"
            # Ensure Apple GPU for MacBooks
            if not webgl_vendor.startswith("Apple"):
                webgl_vendor, webgl_renderer = ("Apple", "Apple M1 GPU")
        else:
            platform = self._rng.choice(["Win32", "Linux x86_64"])

        # Realistic pixel ratios
        if platform == "MacIntel":
            pixel_ratio = 2.0  # Retina displays
        else:
            pixel_ratio = self._rng.choice([1, 1.25, 1.5, 2])

        return {
            "screen": {
                "width": resolution[0],
                "height": resolution[1],
                "colorDepth": self._rng.choice([24, 30]),  # 30-bit for high-end displays
                "pixelRatio": pixel_ratio,
            },
            "webgl": {
                "vendor": webgl_vendor,
                "renderer": webgl_renderer,
            },
            "timezone": self._rng.choice(TIMEZONES),
            "language": self._rng.choice(LANGUAGES).split(",")[0],
            "platform": platform,
            "hardwareConcurrency": self._rng.choice([4, 8, 12, 16, 20, 24]),  # Modern CPUs
            "deviceMemory": self._rng.choice([4, 8, 16, 32, 64]),  # 64GB for workstations
        }
    
    def get_random_delay_ms(self, min_ms: int = 500, max_ms: int = 3000) -> int:
        """Get humanized random delay."""
        # Use log-normal distribution for more human-like delays
        mean = (min_ms + max_ms) / 2
        return int(self._rng.gauss(mean, (max_ms - min_ms) / 4))
    
    def get_playwright_stealth_script(self) -> str:
        """JavaScript to inject for Playwright stealth (enterprise anti-detection)."""
        fingerprint = self.get_fingerprint()

        # Use per-session noise factors
        canvas_noise = self._canvas_noise
        audio_noise = self._audio_noise

        return f"""
        // ============================================================
        // CRITICAL: Function.toString override to hide all patches
        // Must be first to protect subsequent modifications
        // ============================================================
        const originalFunctionToString = Function.prototype.toString;
        const patchedFunctions = new WeakSet();

        Function.prototype.toString = function() {{
            if (patchedFunctions.has(this)) {{
                // Return native-looking code for patched functions
                return 'function () {{ [native code] }}';
            }}
            return originalFunctionToString.call(this);
        }};

        // Helper to mark function as patched
        function markPatched(fn) {{
            patchedFunctions.add(fn);
            return fn;
        }}

        // ============================================================
        // Navigator properties override
        // ============================================================
        Object.defineProperty(navigator, 'webdriver', {{
            get: markPatched(() => undefined),
            configurable: true
        }});
        Object.defineProperty(navigator, 'languages', {{
            get: markPatched(() => ['{fingerprint["language"]}', 'en']),
            configurable: true
        }});
        Object.defineProperty(navigator, 'platform', {{
            get: markPatched(() => '{fingerprint["platform"]}'),
            configurable: true
        }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{
            get: markPatched(() => {fingerprint["hardwareConcurrency"]}),
            configurable: true
        }});
        Object.defineProperty(navigator, 'deviceMemory', {{
            get: markPatched(() => {fingerprint["deviceMemory"]}),
            configurable: true
        }});

        // ============================================================
        // Screen properties override
        // ============================================================
        Object.defineProperty(screen, 'width', {{
            get: markPatched(() => {fingerprint["screen"]["width"]}),
            configurable: true
        }});
        Object.defineProperty(screen, 'height', {{
            get: markPatched(() => {fingerprint["screen"]["height"]}),
            configurable: true
        }});
        Object.defineProperty(screen, 'colorDepth', {{
            get: markPatched(() => {fingerprint["screen"]["colorDepth"]}),
            configurable: true
        }});

        // ============================================================
        // WebGL fingerprinting protection
        // ============================================================
        const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = markPatched(function(parameter) {{
            // 37445 = UNMASKED_VENDOR_WEBGL
            if (parameter === 37445) return '{fingerprint["webgl"]["vendor"]}';
            // 37446 = UNMASKED_RENDERER_WEBGL
            if (parameter === 37446) return '{fingerprint["webgl"]["renderer"]}';
            return originalGetParameter.call(this, parameter);
        }});

        // ============================================================
        // Canvas 2D fingerprinting protection with noise
        // ============================================================
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        const canvasNoise = {canvas_noise};

        HTMLCanvasElement.prototype.toDataURL = markPatched(function() {{
            const context = this.getContext('2d');
            if (context) {{
                const imageData = context.getImageData(0, 0, this.width, this.height);
                for (let i = 0; i < imageData.data.length; i += 4) {{
                    imageData.data[i] += Math.floor((Math.random() - 0.5) * canvasNoise * 255);
                    imageData.data[i + 1] += Math.floor((Math.random() - 0.5) * canvasNoise * 255);
                    imageData.data[i + 2] += Math.floor((Math.random() - 0.5) * canvasNoise * 255);
                }}
                context.putImageData(imageData, 0, 0);
            }}
            return originalToDataURL.apply(this, arguments);
        }});

        CanvasRenderingContext2D.prototype.getImageData = markPatched(function() {{
            const imageData = originalGetImageData.apply(this, arguments);
            for (let i = 0; i < imageData.data.length; i += 4) {{
                imageData.data[i] += Math.floor((Math.random() - 0.5) * canvasNoise * 255);
                imageData.data[i + 1] += Math.floor((Math.random() - 0.5) * canvasNoise * 255);
                imageData.data[i + 2] += Math.floor((Math.random() - 0.5) * canvasNoise * 255);
            }}
            return imageData;
        }});

        // ============================================================
        // AudioContext fingerprinting protection
        // ============================================================
        const audioNoise = {audio_noise};

        if (window.AudioContext || window.webkitAudioContext) {{
            const OriginalAudioContext = window.AudioContext || window.webkitAudioContext;

            // Override createOscillator to add timing noise
            const originalCreateOscillator = OriginalAudioContext.prototype.createOscillator;
            OriginalAudioContext.prototype.createOscillator = markPatched(function() {{
                const oscillator = originalCreateOscillator.call(this);
                const originalStart = oscillator.start;

                oscillator.start = markPatched(function(when) {{
                    // Add subtle timing noise to prevent fingerprinting
                    const noisyWhen = when + (Math.random() - 0.5) * audioNoise;
                    return originalStart.call(this, noisyWhen);
                }});

                return oscillator;
            }});

            // Override createDynamicsCompressor (common fingerprinting target)
            const originalCreateDynamicsCompressor = OriginalAudioContext.prototype.createDynamicsCompressor;
            OriginalAudioContext.prototype.createDynamicsCompressor = markPatched(function() {{
                const compressor = originalCreateDynamicsCompressor.call(this);

                // Add noise to threshold parameter
                const originalThreshold = compressor.threshold;
                Object.defineProperty(compressor, 'threshold', {{
                    get: markPatched(() => {{
                        const value = originalThreshold.value + (Math.random() - 0.5) * audioNoise * 10;
                        return {{ value, defaultValue: originalThreshold.defaultValue }};
                    }}),
                    configurable: true
                }});

                return compressor;
            }});
        }}

        // ============================================================
        // WebRTC IP leak prevention
        // ============================================================
        if (window.RTCPeerConnection || window.webkitRTCPeerConnection || window.mozRTCPeerConnection) {{
            const OriginalRTCPeerConnection =
                window.RTCPeerConnection ||
                window.webkitRTCPeerConnection ||
                window.mozRTCPeerConnection;

            const PatchedRTCPeerConnection = markPatched(function(config, constraints) {{
                // Disable STUN/TURN servers to prevent IP leaks
                if (config && config.iceServers) {{
                    config.iceServers = [];
                }}

                return new OriginalRTCPeerConnection(config, constraints);
            }});

            // Preserve original properties
            PatchedRTCPeerConnection.prototype = OriginalRTCPeerConnection.prototype;

            // Replace global constructors
            window.RTCPeerConnection = PatchedRTCPeerConnection;
            if (window.webkitRTCPeerConnection) {{
                window.webkitRTCPeerConnection = PatchedRTCPeerConnection;
            }}
            if (window.mozRTCPeerConnection) {{
                window.mozRTCPeerConnection = PatchedRTCPeerConnection;
            }}
        }}

        // ============================================================
        // Permissions API spoofing (prevent permission fingerprinting)
        // ============================================================
        if (navigator.permissions && navigator.permissions.query) {{
            const originalQuery = navigator.permissions.query;

            navigator.permissions.query = markPatched(function(parameters) {{
                // Always return 'prompt' for common fingerprinting permissions
                const fingerprintPermissions = ['notifications', 'geolocation', 'camera', 'microphone'];

                if (fingerprintPermissions.includes(parameters.name)) {{
                    return Promise.resolve({{ state: 'prompt' }});
                }}

                return originalQuery.call(this, parameters);
            }});
        }}

        // ============================================================
        // Chrome automation flags cleanup
        // ============================================================
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        delete window.$cdc_asdjflasutopfhvcZLmcfl_;
        delete window.$chrome_asyncScriptInfo;

        // ============================================================
        // Plugin array spoofing (modern browsers have empty plugins)
        // ============================================================
        Object.defineProperty(navigator, 'plugins', {{
            get: markPatched(() => []),
            configurable: true
        }});

        // ============================================================
        // Battery API blocking (fingerprinting vector)
        // ============================================================
        if (navigator.getBattery) {{
            navigator.getBattery = markPatched(() => {{
                return Promise.reject(new Error('Battery API not available'));
            }});
        }}
        """
