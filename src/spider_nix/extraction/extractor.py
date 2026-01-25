"""
Multimodal Extractor - End-to-end vision-DOM fusion pipeline.

Orchestrates the complete extraction flow:
1. Render page + capture screenshot
2. Vision analysis (parallel)
3. DOM analysis (parallel)
4. Fusion via IoU matching
"""

import asyncio
import time
from pathlib import Path
from typing import Optional

from ..ml.vision_client import VisionClient
from .dom_analyzer import DOMAnalyzer
from .fusion_engine import FusionEngine
from .models import ExtractionResult


class MultimodalExtractor:
    """
    End-to-end vision-DOM fusion pipeline.
    
    Combines:
    - Vision AI (via ml-offload-api)
    - DOM parsing (lxml + BeautifulSoup)
    - IoU-based fusion
    
    To create CSS-independent element extractions.
    """

    def __init__(
        self,
        vision_client: Optional[VisionClient] = None,
        iou_threshold: float = 0.5,
        vision_api_url: str = "http://localhost:9000",
        vision_model: str = "llava-v1.5-7b-q4"
    ):
        """
        Initialize multimodal extractor.
        
        Args:
            vision_client: Pre-initialized VisionClient (or None to create)
            iou_threshold: IoU threshold for fusion matching
            vision_api_url: ml-offload-api URL
            vision_model: Vision model to use
        """
        self.vision_client = vision_client or VisionClient(api_url=vision_api_url)
        self.dom_analyzer = DOMAnalyzer()
        self.fusion_engine = FusionEngine(iou_threshold=iou_threshold)
        self.vision_model = vision_model

    async def extract(
        self,
        url: str,
        page,  # Playwright page handle
        screenshot_path: Optional[Path] = None,
        viewport_width: int = 1920,
        viewport_height: int = 1080
    ) -> ExtractionResult:
        """
        Complete extraction pipeline.
        
        Steps:
        1. Capture screenshot
        2. Vision analysis (parallel with DOM)
        3. DOM analysis (parallel with Vision)
        4. Fusion via IoU
        
        Args:
            url: Page URL
            page: Playwright page handle
            screenshot_path: Custom screenshot path (or auto-generate)
            viewport_width: Viewport width
            viewport_height: Viewport height
            
        Returns:
            ExtractionResult with all detections and fusion data
        """
        start_time = time.time()

        # Step 1: Capture screenshot
        if screenshot_path is None:
            screenshot_path = Path(f"/tmp/screenshot_{int(time.time())}.png")

        await page.screenshot(path=str(screenshot_path))
        html_content = await page.content()

        # Step 2 & 3: Vision + DOM analysis (parallel)
        vision_start = time.time()

        vision_task = asyncio.create_task(
            self.vision_client.analyze_screenshot(
                screenshot_path,
                model_id=self.vision_model
            )
        )

        dom_task = asyncio.create_task(
            self.dom_analyzer.analyze_page(
                html_content,
                page,
                viewport_width,
                viewport_height
            )
        )

        # Wait for both to complete
        vision_detections, dom_elements = await asyncio.gather(
            vision_task,
            dom_task,
            return_exceptions=False
        )

        vision_time = (time.time() - vision_start) * 1000  # ms

        # Step 4: Fusion
        fusion_start = time.time()
        fused_elements = self.fusion_engine.fuse(vision_detections, dom_elements)
        fusion_time = (time.time() - fusion_start) * 1000  # ms

        total_time = (time.time() - start_time) * 1000  # ms

        # Get fusion statistics
        fusion_stats = self.fusion_engine.get_fusion_statistics(fused_elements)

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
                **fusion_stats,
                "viewport": {"width": viewport_width, "height": viewport_height},
                "vision_model": self.vision_model,
                "iou_threshold": self.fusion_engine.iou_threshold
            }
        )

    async def extract_from_url(
        self,
        url: str,
        headless: bool = True,
        use_network_proxy: bool = True
    ) -> ExtractionResult:
        """
        Extract from URL (handles browser launch automatically).
        
        Convenience method that launches Playwright, navigates to URL,
        and performs extraction.
        
        Args:
            url: Target URL
            headless: Run browser in headless mode
            use_network_proxy: Use network OPSEC proxy
            
        Returns:
            ExtractionResult
        """
        from playwright.async_api import async_playwright
        from ..config import CrawlerConfig
        from ..browser import BrowserCrawler

        # Create browser crawler for page rendering
        config = CrawlerConfig(use_browser=True, headless=headless)
        crawler = BrowserCrawler(
            config=config,
            use_network_proxy=use_network_proxy
        )

        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=headless)
            
            # Create page with stealth
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=crawler.stealth.get_user_agent()
            )
            await context.add_init_script(crawler.stealth.get_playwright_stealth_script())
            
            page = await context.new_page()
            
            # Navigate
            await page.goto(url, wait_until='networkidle')
            
            # Extract
            result = await self.extract(url, page)
            
            # Cleanup
            await browser.close()
            
            return result

    async def close(self):
        """Close resources."""
        await self.vision_client.close()
