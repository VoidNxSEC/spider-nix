"""Tests for FusionEngine."""

import pytest
from spider_nix.extraction.fusion_engine import FusionEngine
from spider_nix.extraction.models import BoundingBox, DOMElement, VisionDetection


class TestFusionEngine:
    """Test fusion engine functionality."""

    def test_greedy_fusion_perfect_match(self):
        """Test greedy fusion with perfect match."""
        engine = FusionEngine(iou_threshold=0.5)

        # Create matching vision and DOM elements
        vision = VisionDetection(
            element_type="button",
            bounding_box=BoundingBox(0.1, 0.1, 0.2, 0.1),
            confidence=0.9,
            text="Click",
        )

        dom = DOMElement(
            tag_name="button",
            xpath="/html/body/button",
            css_selector="button",
            bounding_box=BoundingBox(0.1, 0.1, 0.2, 0.1),
            text_content="Click",
        )

        result = engine.fuse([vision], [dom], strategy="greedy")

        assert len(result) == 1
        assert result[0].vision == vision
        assert result[0].dom == dom
        assert result[0].iou_score == pytest.approx(1.0)
        assert result[0].strategy == "fused"

    def test_greedy_fusion_no_match(self):
        """Test greedy fusion with no matching DOM."""
        engine = FusionEngine(iou_threshold=0.5)

        vision = VisionDetection(
            element_type="button",
            bounding_box=BoundingBox(0.1, 0.1, 0.2, 0.1),
            confidence=0.9,
        )

        dom = DOMElement(
            tag_name="button",
            xpath="/html/body/button",
            css_selector="button",
            bounding_box=BoundingBox(0.5, 0.5, 0.2, 0.1),  # Far away
        )

        result = engine.fuse([vision], [dom], strategy="greedy")

        assert len(result) >= 1
        # Vision-only element
        vision_only = [f for f in result if f.strategy == "vision_only"]
        assert len(vision_only) == 1
        assert vision_only[0].vision == vision
        assert vision_only[0].dom is None

    def test_text_similarity(self):
        """Test text similarity scoring."""
        engine = FusionEngine()

        # Exact match
        assert engine._text_similarity("Hello", "Hello") == 1.0

        # Case insensitive
        assert engine._text_similarity("Hello", "hello") == 1.0

        # Containment
        assert engine._text_similarity("Hello World", "Hello") >= 0.8

        # No match
        assert engine._text_similarity("Hello", "Goodbye") < 0.5

    def test_types_match(self):
        """Test element type matching."""
        engine = FusionEngine()

        assert engine._types_match("button", "button")
        assert engine._types_match("button", "input")
        assert engine._types_match("link", "a")
        assert not engine._types_match("button", "div")

    def test_filter_high_confidence(self):
        """Test filtering by confidence threshold."""
        engine = FusionEngine()

        vision1 = VisionDetection(
            element_type="button",
            bounding_box=BoundingBox(0.1, 0.1, 0.1, 0.1),
            confidence=0.9,
        )

        vision2 = VisionDetection(
            element_type="button",
            bounding_box=BoundingBox(0.3, 0.3, 0.1, 0.1),
            confidence=0.5,
        )

        dom1 = DOMElement(
            tag_name="button",
            xpath="/html/body/button[1]",
            css_selector="button:nth-child(1)",
            bounding_box=BoundingBox(0.1, 0.1, 0.1, 0.1),
        )

        dom2 = DOMElement(
            tag_name="button",
            xpath="/html/body/button[2]",
            css_selector="button:nth-child(2)",
            bounding_box=BoundingBox(0.3, 0.3, 0.1, 0.1),
        )

        fused = engine.fuse([vision1, vision2], [dom1, dom2])
        high_conf = engine.filter_high_confidence(fused, min_confidence=0.7)

        # Should only have high-confidence elements
        assert all(f.extraction_confidence >= 0.7 for f in high_conf)

    def test_is_important_element(self):
        """Test important element filtering."""
        engine = FusionEngine()

        # Element with text - important
        dom1 = DOMElement(
            tag_name="div",
            xpath="/html/body/div",
            css_selector="div",
            bounding_box=BoundingBox(0.1, 0.1, 0.2, 0.1),
            text_content="Important text",
        )
        assert engine._is_important_element(dom1)

        # Element with onclick - important
        dom2 = DOMElement(
            tag_name="div",
            xpath="/html/body/div",
            css_selector="div",
            bounding_box=BoundingBox(0.1, 0.1, 0.2, 0.1),
            attributes={"onclick": "doSomething()"},
        )
        assert engine._is_important_element(dom2)

        # Empty div with no attributes - not important
        dom3 = DOMElement(
            tag_name="div",
            xpath="/html/body/div",
            css_selector="div",
            bounding_box=BoundingBox(0.1, 0.1, 0.2, 0.1),
        )
        assert not engine._is_important_element(dom3)

        # Very small element - not important
        dom4 = DOMElement(
            tag_name="div",
            xpath="/html/body/div",
            css_selector="div",
            bounding_box=BoundingBox(0.1, 0.1, 0.0001, 0.0001),
            text_content="Text",
        )
        assert not engine._is_important_element(dom4)
