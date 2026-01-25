#!/usr/bin/env python
"""Quick import validation script."""

print("Testing Phase 1 imports...")

# Extraction module
print("  ├─ extraction.models...", end=" ")
from spider_nix.extraction.models import BoundingBox, VisionDetection, DOMElement, FusedElement
print("✓")

print("  ├─ extraction.VisionExtractor...", end=" ")
from spider_nix.extraction.vision_extractor import VisionExtractor
print("✓")

print("  ├─ extraction.DOMAnalyzer...", end=" ")
from spider_nix.extraction.dom_analyzer import DOMAnalyzer
print("✓")

print("  ├─ extraction.FusionEngine...", end=" ")
from spider_nix.extraction.fusion_engine import FusionEngine
print("✓")

# ML module
print("  ├─ ml.models...", end=" ")
from spider_nix.ml.models import FailureClass, Strategy, CrawlAttempt, StrategyEffectiveness
print("✓")

print("  ├─ ml.FeedbackLogger...", end=" ")
from spider_nix.ml.feedback_logger import FeedbackLogger
print("✓")

print("  ├─ ml.FailureClassifier...", end=" ")
from spider_nix.ml.failure_classifier import FailureClassifier
print("✓")

print("  ├─ ml.StrategySelector...", end=" ")
from spider_nix.ml.strategy_selector import StrategySelector
print("✓")

# Main module imports
print("  ├─ spider_nix.ml...", end=" ")
from spider_nix.ml import (
    CrawlAttempt,
    FailureClass,
    Strategy,
    StrategyEffectiveness,
    FeedbackLogger,
    FailureClassifier,
    StrategySelector,
)
print("✓")

print("  └─ spider_nix.extraction...", end=" ")
from spider_nix.extraction import (
    BoundingBox,
    VisionDetection,
    DOMElement,
    FusedElement,
    VisionExtractor,
    DOMAnalyzer,
    FusionEngine,
)
print("✓")

print("\n✅ All Phase 1 imports successful!")
