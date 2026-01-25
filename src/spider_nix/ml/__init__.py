"""
Machine Learning module for spider-nix.

Adaptive scraping strategies using ML feedback loops.
"""

from .models import (
    CrawlAttempt,
    FailureClass,
    Strategy,
    StrategyEffectiveness,
)
from .feedback_logger import FeedbackLogger
from .failure_classifier import FailureClassifier, ClassificationResult
from .strategy_selector import StrategySelector
from .vision_client import VisionClient

__all__ = [
    # Models
    "CrawlAttempt",
    "FailureClass",
    "Strategy",
    "StrategyEffectiveness",
    # Feedback
    "FeedbackLogger",
    # Classification
    "FailureClassifier",
    "ClassificationResult",
    # Strategy Selection
    "StrategySelector",
    # Vision
    "VisionClient",
]
