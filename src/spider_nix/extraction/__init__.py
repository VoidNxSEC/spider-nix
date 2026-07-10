"""
Multimodal extraction module for spider-nix.

Vision-DOM fusion pipeline for CSS-independent element extraction.
"""

from .dom_analyzer import DOMAnalyzer
from .extractor import MultimodalExtractor
from .fusion_engine import FusionEngine
from .models import (
    BoundingBox,
    DOMElement,
    ExtractionResult,
    FusedElement,
    VisionDetection,
)
from .vision_extractor import VisionExtractor

__all__ = [
    "BoundingBox",
    "VisionDetection",
    "DOMElement",
    "FusedElement",
    "ExtractionResult",
    "DOMAnalyzer",
    "FusionEngine",
    "MultimodalExtractor",
    "VisionExtractor",
]
