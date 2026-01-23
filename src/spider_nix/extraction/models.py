"""Data models for multimodal extraction."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BoundingBox:
    """Normalized bounding box coordinates (0-1 range).

    Attributes:
        x: Left edge (0-1 normalized)
        y: Top edge (0-1 normalized)
        width: Box width (0-1 normalized)
        height: Box height (0-1 normalized)
    """
    x: float
    y: float
    width: float
    height: float

    def iou(self, other: "BoundingBox") -> float:
        """Calculate Intersection over Union with another bounding box.

        Args:
            other: Another bounding box

        Returns:
            IoU score (0-1), where 1 is perfect overlap
        """
        # Calculate intersection rectangle
        x_left = max(self.x, other.x)
        y_top = max(self.y, other.y)
        x_right = min(self.x + self.width, other.x + other.width)
        y_bottom = min(self.y + self.height, other.y + other.height)

        # No intersection
        if x_right < x_left or y_bottom < y_top:
            return 0.0

        # Calculate areas
        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        box1_area = self.width * self.height
        box2_area = other.width * other.height
        union_area = box1_area + box2_area - intersection_area

        return intersection_area / union_area if union_area > 0 else 0.0

    def to_absolute(self, viewport_width: int, viewport_height: int) -> tuple[int, int, int, int]:
        """Convert normalized coordinates to absolute pixel coordinates.

        Args:
            viewport_width: Viewport width in pixels
            viewport_height: Viewport height in pixels

        Returns:
            Tuple of (x, y, width, height) in absolute pixels
        """
        return (
            int(self.x * viewport_width),
            int(self.y * viewport_height),
            int(self.width * viewport_width),
            int(self.height * viewport_height),
        )


@dataclass
class VisionDetection:
    """Vision AI detection result from screenshot analysis.

    Attributes:
        element_type: Detected element type (button, input, link, image, text, etc.)
        bounding_box: Normalized bounding box coordinates
        confidence: Model confidence score (0-1)
        text: Extracted text from element (OCR/OCI)
        attributes: Additional vision model outputs
    """
    element_type: str
    bounding_box: BoundingBox
    confidence: float
    text: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class DOMElement:
    """Parsed DOM element with position information.

    Attributes:
        tag_name: HTML tag name
        xpath: Full XPath to element
        css_selector: CSS selector path
        bounding_box: Element position (from getBoundingClientRect)
        text_content: Visible text content
        attributes: HTML attributes dict
        inner_html: Element inner HTML
    """
    tag_name: str
    xpath: str
    css_selector: str
    bounding_box: BoundingBox | None = None
    text_content: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    inner_html: str | None = None


@dataclass
class FusedElement:
    """Result of vision-DOM fusion.

    Combines visual detection with DOM structural information,
    providing CSS-resilient extraction anchored to visual coordinates.

    Attributes:
        vision: Vision AI detection
        dom: Matched DOM element (None if no match found)
        iou_score: Intersection over Union score for the match
        extraction_confidence: Overall confidence in this extraction
        strategy: How this element was matched ('vision_only', 'dom_only', 'fused')
    """
    vision: VisionDetection | None
    dom: DOMElement | None
    iou_score: float
    extraction_confidence: float
    strategy: str = "fused"

    @property
    def is_high_confidence(self) -> bool:
        """Check if extraction meets high confidence threshold."""
        return self.extraction_confidence >= 0.7

    @property
    def best_text(self) -> str | None:
        """Get best available text (prefer vision OCR, fallback to DOM)."""
        if self.vision and self.vision.text:
            return self.vision.text
        if self.dom and self.dom.text_content:
            return self.dom.text_content
        return None

    @property
    def best_selector(self) -> str | None:
        """Get best available selector for future extraction."""
        if self.dom:
            # Prefer CSS selector for readability
            return self.dom.css_selector or self.dom.xpath
        return None
