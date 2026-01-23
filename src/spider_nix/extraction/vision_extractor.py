"""Vision AI extractor using ml-offload-api for local inference."""

import asyncio
import base64
from io import BytesIO
from typing import Any

import httpx
from PIL import Image

from .models import BoundingBox, VisionDetection


class VisionExtractor:
    """Extract elements from screenshots using Vision AI models.

    Integrates with ml-offload-api for local model inference,
    supporting CLIP, Qwen-VL, and other vision models.
    """

    def __init__(
        self,
        api_url: str = "http://localhost:9000",
        model_id: str = "openai-clip-vit-b32",
        backend: str = "ollama",
        timeout: float = 30.0,
    ):
        """Initialize vision extractor.

        Args:
            api_url: ml-offload-api base URL
            model_id: Vision model identifier
            backend: Backend to use (ollama, mlx, transformers)
            timeout: Request timeout in seconds
        """
        self.api_url = api_url
        self.model_id = model_id
        self.backend = backend
        self.timeout = timeout
        self._model_loaded = False
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        await self._ensure_model_loaded()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    async def _ensure_model_loaded(self):
        """Ensure vision model is loaded in ml-offload-api."""
        if self._model_loaded:
            return

        if not self._client:
            raise RuntimeError("VisionExtractor not initialized - use async with")

        try:
            # Check if model is already loaded
            response = await self._client.get(f"{self.api_url}/models")
            if response.status_code == 200:
                models = response.json().get("models", [])
                if any(m.get("model_id") == self.model_id for m in models):
                    self._model_loaded = True
                    return

            # Load model
            response = await self._client.post(
                f"{self.api_url}/models/load",
                json={
                    "model_id": self.model_id,
                    "backend": self.backend,
                },
            )
            response.raise_for_status()
            self._model_loaded = True

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Failed to load vision model {self.model_id}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise RuntimeError(
                f"Cannot connect to ml-offload-api at {self.api_url}: {e}"
            ) from e

    async def analyze_screenshot(
        self,
        screenshot: bytes,
        detect_types: list[str] | None = None,
        confidence_threshold: float = 0.5,
    ) -> list[VisionDetection]:
        """Analyze screenshot to detect UI elements.

        Args:
            screenshot: Screenshot image bytes (PNG/JPEG)
            detect_types: Element types to detect (None = all)
            confidence_threshold: Minimum confidence score

        Returns:
            List of vision detections with bounding boxes
        """
        if not self._client:
            raise RuntimeError("VisionExtractor not initialized - use async with")

        await self._ensure_model_loaded()

        # Get image dimensions for normalization
        image = Image.open(BytesIO(screenshot))
        width, height = image.size

        # Prepare request
        files = {"image": ("screenshot.png", screenshot, "image/png")}
        data = {
            "model_id": self.model_id,
            "confidence_threshold": confidence_threshold,
        }
        if detect_types:
            data["detect_types"] = ",".join(detect_types)

        try:
            # Call vision inference endpoint
            response = await self._client.post(
                f"{self.api_url}/inference/vision",
                files=files,
                data=data,
            )
            response.raise_for_status()
            result = response.json()

            # Parse detections
            detections = []
            for detection in result.get("detections", []):
                # Convert absolute coordinates to normalized (0-1)
                bbox = detection.get("bounding_box", {})
                normalized_bbox = BoundingBox(
                    x=bbox.get("x", 0) / width,
                    y=bbox.get("y", 0) / height,
                    width=bbox.get("width", 0) / width,
                    height=bbox.get("height", 0) / height,
                )

                detections.append(
                    VisionDetection(
                        element_type=detection.get("element_type", "unknown"),
                        bounding_box=normalized_bbox,
                        confidence=detection.get("confidence", 0.0),
                        text=detection.get("text"),
                        attributes=detection.get("attributes", {}),
                    )
                )

            return detections

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Vision inference failed: {e.response.text}"
            ) from e

    async def extract_text_regions(
        self,
        screenshot: bytes,
        ocr_model: str = "tesseract",
    ) -> list[VisionDetection]:
        """Extract text regions using OCR.

        Args:
            screenshot: Screenshot image bytes
            ocr_model: OCR engine to use

        Returns:
            List of text detections with bounding boxes
        """
        if not self._client:
            raise RuntimeError("VisionExtractor not initialized - use async with")

        # Get image dimensions
        image = Image.open(BytesIO(screenshot))
        width, height = image.size

        files = {"image": ("screenshot.png", screenshot, "image/png")}
        data = {"engine": ocr_model}

        try:
            response = await self._client.post(
                f"{self.api_url}/inference/ocr",
                files=files,
                data=data,
            )
            response.raise_for_status()
            result = response.json()

            detections = []
            for region in result.get("text_regions", []):
                bbox = region.get("bounding_box", {})
                normalized_bbox = BoundingBox(
                    x=bbox.get("x", 0) / width,
                    y=bbox.get("y", 0) / height,
                    width=bbox.get("width", 0) / width,
                    height=bbox.get("height", 0) / height,
                )

                detections.append(
                    VisionDetection(
                        element_type="text",
                        bounding_box=normalized_bbox,
                        confidence=region.get("confidence", 1.0),
                        text=region.get("text"),
                        attributes={"ocr_engine": ocr_model},
                    )
                )

            return detections

        except httpx.HTTPStatusError as e:
            # OCR endpoint may not exist - return empty list
            return []

    def analyze_screenshot_sync(
        self,
        screenshot: bytes,
        detect_types: list[str] | None = None,
        confidence_threshold: float = 0.5,
    ) -> list[VisionDetection]:
        """Synchronous wrapper for analyze_screenshot.

        For compatibility with sync code. Prefer async version.
        """
        async def _run():
            async with self:
                return await self.analyze_screenshot(
                    screenshot,
                    detect_types,
                    confidence_threshold,
                )

        return asyncio.run(_run())
