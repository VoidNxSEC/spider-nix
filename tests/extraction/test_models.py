"""Tests for extraction data models."""

import pytest
from spider_nix.extraction.models import BoundingBox, DOMElement, FusedElement, VisionDetection


class TestBoundingBox:
    """Test BoundingBox model."""

    def test_iou_perfect_overlap(self):
        """Test IoU calculation with perfect overlap."""
        box1 = BoundingBox(x=0.1, y=0.1, width=0.2, height=0.2)
        box2 = BoundingBox(x=0.1, y=0.1, width=0.2, height=0.2)

        assert box1.iou(box2) == pytest.approx(1.0)

    def test_iou_no_overlap(self):
        """Test IoU calculation with no overlap."""
        box1 = BoundingBox(x=0.0, y=0.0, width=0.1, height=0.1)
        box2 = BoundingBox(x=0.5, y=0.5, width=0.1, height=0.1)

        assert box1.iou(box2) == 0.0

    def test_iou_partial_overlap(self):
        """Test IoU calculation with partial overlap."""
        box1 = BoundingBox(x=0.0, y=0.0, width=0.2, height=0.2)
        box2 = BoundingBox(x=0.1, y=0.1, width=0.2, height=0.2)

        iou = box1.iou(box2)
        assert 0.0 < iou < 1.0

    def test_to_absolute(self):
        """Test conversion to absolute coordinates."""
        box = BoundingBox(x=0.5, y=0.5, width=0.2, height=0.1)
        abs_x, abs_y, abs_width, abs_height = box.to_absolute(1920, 1080)

        assert abs_x == 960
        assert abs_y == 540
        assert abs_width == 384
        assert abs_height == 108


class TestVisionDetection:
    """Test VisionDetection model."""

    def test_creation(self):
        """Test creating vision detection."""
        bbox = BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4)
        detection = VisionDetection(
            element_type="button",
            bounding_box=bbox,
            confidence=0.95,
            text="Click Me",
        )

        assert detection.element_type == "button"
        assert detection.confidence == 0.95
        assert detection.text == "Click Me"
        assert detection.bounding_box == bbox


class TestDOMElement:
    """Test DOMElement model."""

    def test_creation(self):
        """Test creating DOM element."""
        bbox = BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4)
        element = DOMElement(
            tag_name="button",
            xpath="/html/body/button[1]",
            css_selector="button.primary",
            bounding_box=bbox,
            text_content="Submit",
            attributes={"class": "primary", "type": "submit"},
        )

        assert element.tag_name == "button"
        assert element.xpath == "/html/body/button[1]"
        assert element.text_content == "Submit"


class TestFusedElement:
    """Test FusedElement model."""

    def test_high_confidence_threshold(self):
        """Test high confidence check."""
        vision = VisionDetection(
            element_type="button",
            bounding_box=BoundingBox(0.1, 0.2, 0.3, 0.4),
            confidence=0.9,
        )

        fused = FusedElement(
            vision=vision,
            dom=None,
            iou_score=0.8,
            extraction_confidence=0.75,
        )

        assert fused.is_high_confidence

        fused2 = FusedElement(
            vision=vision,
            dom=None,
            iou_score=0.5,
            extraction_confidence=0.6,
        )

        assert not fused2.is_high_confidence

    def test_best_text_priority(self):
        """Test text extraction priority (vision > DOM)."""
        vision = VisionDetection(
            element_type="button",
            bounding_box=BoundingBox(0.1, 0.2, 0.3, 0.4),
            confidence=0.9,
            text="Vision Text",
        )

        dom = DOMElement(
            tag_name="button",
            xpath="/html/body/button",
            css_selector="button",
            text_content="DOM Text",
        )

        fused = FusedElement(vision=vision, dom=dom, iou_score=0.9, extraction_confidence=0.9)

        # Vision text should take priority
        assert fused.best_text == "Vision Text"

    def test_best_text_fallback(self):
        """Test text fallback to DOM when vision has no text."""
        vision = VisionDetection(
            element_type="button",
            bounding_box=BoundingBox(0.1, 0.2, 0.3, 0.4),
            confidence=0.9,
            text=None,
        )

        dom = DOMElement(
            tag_name="button",
            xpath="/html/body/button",
            css_selector="button",
            text_content="DOM Text",
        )

        fused = FusedElement(vision=vision, dom=dom, iou_score=0.9, extraction_confidence=0.9)

        assert fused.best_text == "DOM Text"

    def test_best_selector(self):
        """Test selector extraction from DOM."""
        dom = DOMElement(
            tag_name="button",
            xpath="/html/body/button",
            css_selector="button.primary",
        )

        fused = FusedElement(vision=None, dom=dom, iou_score=0.9, extraction_confidence=0.9)

        assert fused.best_selector == "button.primary"
