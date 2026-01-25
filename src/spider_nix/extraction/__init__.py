"""
Multimodal extraction module for spider-nix.

Vision-DOM fusion pipeline for CSS-independent element extraction.
"""

from .models import (
    BoundingBox,
    VisionDetection,
    DOMElement,
    FusedElement,
    ExtractionResult,
)
from .dom_analyzer import DOMAnalyzer
from .fusion_engine import FusionEngine
from .extractor import MultimodalExtractor
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
