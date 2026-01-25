"""
Vision Client for ml-offload-api integration.

Provides interface to vision models (CLIP, LLaVA, Qwen-VL) for screenshot analysis
and element detection via the ml-offload-api REST endpoint.
"""

import base64
import json
import re
from pathlib import Path
from typing import List

import httpx

from ..extraction.models import VisionDetection, BoundingBox


class VisionClient:
    """
    Client for ml-offload-api vision inference.
    
    Supports:
    - LLaVA (multimodal vision-language model)
    - CLIP (zero-shot image classification)
    - Qwen-VL (advanced multimodal understanding)
    """

    def __init__(self, api_url: str = "http://localhost:9000", timeout: float = 120.0):
        """
        Initialize vision client.
        
        Args:
            api_url: ml-offload-api base URL
            timeout: Request timeout in seconds (vision models are slow)
        """
        self.api_url = api_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=timeout)
        self.model_loaded = False
        self.current_model = None

    async def ensure_model_loaded(self, model_id: str = "llava-v1.5-7b-q4"):
        """
        Load vision model if not already loaded.
        
        Args:
            model_id: Model identifier (e.g., "llava-v1.5-7b-q4", "openai-clip-vit-b32")
        """
        if self.model_loaded and self.current_model == model_id:
            return

        # Check if model already loaded
        try:
            response = await self.client.get(f"{self.api_url}/models")
            response.raise_for_status()
            models = response.json()

            # Check if model is in loaded state
            loaded_models = [
                m.get("name") or m.get("id")
                for m in models
                if m.get("loaded", False) or m.get("status") == "loaded"
            ]

            if model_id in loaded_models:
                self.model_loaded = True
                self.current_model = model_id
                return

        except Exception as e:
            print(f"Warning: Failed to check loaded models: {e}")

        # Load model
        try:
            load_response = await self.client.post(
                f"{self.api_url}/load",
                json={
                    "model_name": model_id,
                    "backend": "llamacpp",  # llama.cpp supports vision models
                }
            )
            load_response.raise_for_status()
            self.model_loaded = True
            self.current_model = model_id
        except Exception as e:
            raise RuntimeError(f"Failed to load model {model_id}: {e}")

    async def analyze_screenshot(
        self,
        screenshot_path: Path,
        prompt: str | None = None,
        model_id: str = "llava-v1.5-7b-q4",
    ) -> List[VisionDetection]:
        """
        Analyze screenshot with vision model to detect interactive elements.
        
        Args:
            screenshot_path: Path to screenshot PNG/JPEG
            prompt: Custom prompt (uses default if None)
            model_id: Vision model to use
            
        Returns:
            List of detected elements with bounding boxes
        """
        await self.ensure_model_loaded(model_id)

        # Default prompt optimized for element detection
        if prompt is None:
            prompt = (
                "Analyze this webpage screenshot and identify all interactive elements. "
                "For each element, provide:\n"
                "1. Element type (button, link, input, form, image, nav, menu)\n"
                "2. Bounding box coordinates as (x, y, width, height) normalized to 0-1\n"
                "3. Visible text content (if any)\n\n"
                "Format each detection as:\n"
                "TYPE at (X, Y, W, H) - \"Text\"\n\n"
                "Example:\n"
                "button at (0.5, 0.3, 0.1, 0.05) - \"Submit\"\n"
                "link at (0.1, 0.9, 0.15, 0.02) - \"Privacy Policy\""
            )

        # Read screenshot
        with open(screenshot_path, "rb") as f:
            screenshot_bytes = f.read()

        # Encode as base64 for OpenAI-compatible API
        image_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        # Send to ml-offload-api (OpenAI-compatible endpoint)
        try:
            response = await self.client.post(
                f"{self.api_url}/v1/chat/completions",
                json={
                    "model": model_id,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_b64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.1,  # Low temp for consistent structured output
                }
            )
            response.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Vision inference failed: {e}")

        # Parse response
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # Parse structured output into VisionDetection objects
        return self._parse_vision_output(content, model_id)

    def _parse_vision_output(self, output: str, model_id: str) -> List[VisionDetection]:
        """
        Parse model output into structured VisionDetection objects.
        
        Expected format from model:
        ```
        button at (0.5, 0.3, 0.1, 0.05) - "Submit"
        input at (0.4, 0.2, 0.2, 0.03) - "Email field"
        link at (0.1, 0.9, 0.15, 0.02) - "Privacy Policy"
        ```
        """
        detections = []

        # Regex to parse lines
        # Matches: "TYPE at (X, Y, W, H) - TEXT" or "TYPE at (X,Y,W,H) - TEXT"
        pattern = r'(\w+)\s+at\s+\(([0-9.]+),?\s*([0-9.]+),?\s*([0-9.]+),?\s*([0-9.]+)\)\s*[-–]\s*["\']?([^"\'\n]*)["\']?'

        for match in re.finditer(pattern, output, re.MULTILINE | re.IGNORECASE):
            try:
                element_type = match.group(1).lower()
                x = float(match.group(2))
                y = float(match.group(3))
                w = float(match.group(4))
                h = float(match.group(5))
                text = match.group(6).strip()

                # Validate coordinates (0-1 normalized)
                if not (0 <= x <= 1 and 0 <= y <= 1 and 0 <= w <= 1 and 0 <= h <= 1):
                    continue  # Skip invalid coordinates

                detection = VisionDetection(
                    element_type=element_type,
                    bounding_box=BoundingBox(x=x, y=y, width=w, height=h),
                    confidence=0.85,  # Default confidence (model-dependent)
                    text_content=text if text else None,
                    ocr_confidence=0.9 if text else None,
                    model_id=model_id,
                    attributes={}
                )
                detections.append(detection)

            except (ValueError, IndexError) as e:
                # Skip malformed lines
                continue

        return detections

    async def analyze_with_clip(
        self,
        screenshot_path: Path,
        element_types: List[str] | None = None
    ) -> List[VisionDetection]:
        """
        Alternative: Use CLIP for zero-shot element classification.
        
        Strategy:
        1. Segment screenshot into grid (e.g., 10x10 cells)
        2. For each cell, classify with CLIP: "a button", "a link", etc.
        3. Merge adjacent cells of same type into bounding boxes
        
        Args:
            screenshot_path: Path to screenshot
            element_types: Types to detect (default: button, link, input, image)
            
        Returns:
            List of detected elements
            
        Note: This is a simpler alternative when LLaVA is unavailable.
        Currently returns empty list (TODO: implement grid-based CLIP classification).
        """
        # TODO: Implement grid-based CLIP classification
        # This requires:
        # 1. Load CLIP model
        # 2. Slice image into grid
        # 3. Classify each cell
        # 4. Merge adjacent cells of same type
        # 5. Return bounding boxes
        return []

    async def health_check(self) -> bool:
        """
        Check if ml-offload-api is reachable and healthy.
        
        Returns:
            True if API is healthy
        """
        try:
            response = await self.client.get(f"{self.api_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    async def get_available_models(self) -> List[dict]:
        """
        Get list of available vision models.
        
        Returns:
            List of model metadata dicts
        """
        try:
            response = await self.client.get(f"{self.api_url}/models")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to get models: {e}")

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
