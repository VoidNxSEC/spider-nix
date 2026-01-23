"""Multimodal extraction system for SpiderNix.

This module provides enterprise-grade web content extraction combining:
- Vision AI (CLIP/Qwen-VL) for screenshot analysis
- DOM parsing for structural content extraction
- Fusion engine for mapping visual detections to DOM elements
"""

from .models import (
    BoundingBox,
    DOMElement,
    FusedElement,
    VisionDetection,
)
from .vision_extractor import VisionExtractor
from .dom_analyzer import DOMAnalyzer
from .fusion_engine import FusionEngine

__all__ = [
    "BoundingBox",
    "VisionDetection",
    "DOMElement",
    "FusedElement",
    "VisionExtractor",
    "DOMAnalyzer",
    "FusionEngine",
]
