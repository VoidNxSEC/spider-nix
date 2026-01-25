"""
Data models for multimodal extraction (Vision + DOM fusion).

Core models for the vision-DOM fusion pipeline that enables CSS-independent
element extraction using computer vision and IoU (Intersection over Union) matching.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class BoundingBox:
    """
    Normalized bounding box coordinates (0-1 range).
    
    Origin is top-left (0,0), bottom-right is (1,1).
    """
    x: float  # Left edge (0 = left, 1 = right)
    y: float  # Top edge (0 = top, 1 = bottom)
    width: float  # Box width
    height: float  # Box height

    def area(self) -> float:
        """Calculate box area."""
        return self.width * self.height

    def intersects(self, other: "BoundingBox") -> bool:
        """Check if this box intersects with another."""
        return not (
            self.x + self.width < other.x or
            other.x + other.width < self.x or
            self.y + self.height < other.y or
            other.y + other.height < self.y
        )

    def iou(self, other: "BoundingBox") -> float:
        """Calculate Intersection over Union (IoU) with another box."""
        # Calculate intersection area
        x_overlap = max(0, min(self.x + self.width, other.x + other.width) - max(self.x, other.x))
        y_overlap = max(0, min(self.y + self.height, other.y + other.height) - max(self.y, other.y))
        intersection = x_overlap * y_overlap

        # Calculate union area
        area1 = self.area()
        area2 = other.area()
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0.0

    def to_absolute(self, viewport_width: int, viewport_height: int) -> tuple[int, int, int, int]:
        """Convert normalized coordinates to absolute pixels."""
        return (
            int(self.x * viewport_width),
            int(self.y * viewport_height),
            int(self.width * viewport_width),
            int(self.height * viewport_height),
        )


@dataclass
class VisionDetection:
    """
    Element detected by vision model (CLIP, LLaVA, Qwen-VL).

    Represents visual understanding of page elements independent of DOM/CSS.
    """
    element_type: str  # button, link, text, image, input, form, nav, menu
    bounding_box: BoundingBox
    confidence: float  # 0.0-1.0 model confidence
    text: str | None = None  # OCR extracted text
    ocr_confidence: float | None = None
    attributes: dict = field(default_factory=dict)  # Visual attributes (color, size, etc)
    model_id: str = "clip-vit-b32"  # Which model detected it

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """Check if detection confidence meets threshold."""
        return self.confidence >= threshold

    def has_text(self) -> bool:
        """Check if OCR extracted any text."""
        return self.text is not None and len(self.text.strip()) > 0


@dataclass
class DOMElement:
    """
    Element extracted from HTML DOM.

    Represents traditional DOM-based element with selectors and attributes.
    """
    tag_name: str
    xpath: str
    css_selector: str
    text_content: str = ""
    attributes: dict = field(default_factory=dict)
    bounding_box: BoundingBox | None = None  # From JS getBoundingClientRect()

    def matches_type(self, element_type: str) -> bool:
        """
        Check if DOM element matches vision detection type.
        
        Maps visual element types to DOM tag names.
        """
        type_map = {
            "button": ["button", "input"],
            "link": ["a"],
            "input": ["input", "textarea", "select"],
            "image": ["img", "picture"],
            "form": ["form"],
            "nav": ["nav"],
            "menu": ["ul", "ol", "menu"],
        }
        
        tag_lower = self.tag_name.lower()
        
        # Special handling for input types
        if tag_lower == "input" and element_type == "button":
            input_type = self.attributes.get("type", "").lower()
            return input_type in ["submit", "button", "reset"]
        
        return tag_lower in type_map.get(element_type, [])

    def is_interactive(self) -> bool:
        """Check if element is interactive (clickable, typeable, etc)."""
        interactive_tags = ["a", "button", "input", "textarea", "select"]
        return self.tag_name.lower() in interactive_tags


@dataclass
class FusedElement:
    """
    High-confidence element from Vision+DOM fusion.

    Represents the core innovation: combining visual detection with DOM analysis
    for CSS-independent extraction that's resilient to class name changes.
    """
    iou_score: float  # Intersection over Union quality (0-1)
    extraction_confidence: float  # Combined confidence score
    vision: VisionDetection | None = None  # None if DOM-only extraction
    dom: DOMElement | None = None  # None if vision-only extraction
    extraction_method: Literal["vision_only", "dom_only", "fused"] = "vision_only"
    fusion_metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def selector(self) -> str | None:
        """Get best CSS/XPath selector (prefer CSS > XPath > None)."""
        if self.dom:
            return self.dom.css_selector or self.dom.xpath
        return None

    @property
    def is_resilient(self) -> bool:
        """
        Check if extraction is resilient to CSS changes.
        
        Fused elements with high IoU are resilient because they combine
        visual position (doesn't change) with DOM structure.
        """
        return self.extraction_method == "fused" and self.iou_score > 0.7

    @property
    def text(self) -> str:
        """Get element text (prefer Vision OCR > DOM)."""
        if self.vision and self.vision.text:
            return self.vision.text
        elif self.dom and self.dom.text_content:
            return self.dom.text_content
        return ""

    @property
    def best_selector(self) -> str | None:
        """Alias for selector property (backward compatibility)."""
        return self.selector

    @property
    def best_text(self) -> str:
        """Alias for text property (backward compatibility)."""
        return self.text

    @property
    def is_high_confidence(self) -> bool:
        """Check if fusion has high confidence (IoU > 0.7 and vision confidence > 0.8)."""
        return self.iou_score > 0.7 and (self.vision.confidence > 0.8 if self.vision else False)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "text": self.text,
            "selector": self.selector,
            "confidence": self.extraction_confidence,
            "iou_score": self.iou_score,
            "method": self.extraction_method,
            "is_resilient": self.is_resilient,
            "attributes": self.dom.attributes if self.dom else {},
        }

        if self.vision:
            result["element_type"] = self.vision.element_type
            result["bounding_box"] = {
                "x": self.vision.bounding_box.x,
                "y": self.vision.bounding_box.y,
                "width": self.vision.bounding_box.width,
                "height": self.vision.bounding_box.height,
            }

        return result


@dataclass
class ExtractionResult:
    """
    Complete extraction result for a page.
    
    Contains all detections, elements, and fusion results with performance metrics.
    """
    url: str
    screenshot_path: str
    vision_detections: list[VisionDetection]
    dom_elements: list[DOMElement]
    fused_elements: list[FusedElement]
    extraction_time_ms: float
    model_inference_time_ms: float
    fusion_time_ms: float
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def total_elements(self) -> int:
        """Total number of fused elements."""
        return len(self.fused_elements)

    @property
    def fused_count(self) -> int:
        """Number of successfully fused elements."""
        return len([e for e in self.fused_elements if e.extraction_method == "fused"])

    @property
    def vision_only_count(self) -> int:
        """Number of vision-only elements."""
        return len([e for e in self.fused_elements if e.extraction_method == "vision_only"])

    @property
    def dom_only_count(self) -> int:
        """Number of DOM-only elements."""
        return len([e for e in self.fused_elements if e.extraction_method == "dom_only"])

    @property
    def fusion_success_rate(self) -> float:
        """Percentage of elements successfully fused."""
        if self.total_elements == 0:
            return 0.0
        return (self.fused_count / self.total_elements) * 100

    @property
    def average_iou(self) -> float:
        """Average IoU score for fused elements."""
        fused = [e for e in self.fused_elements if e.extraction_method == "fused"]
        if not fused:
            return 0.0
        return sum(e.iou_score for e in fused) / len(fused)

    def get_resilient_elements(self) -> list[FusedElement]:
        """Get only resilient (high-confidence fused) elements."""
        return [e for e in self.fused_elements if e.is_resilient]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "url": self.url,
            "screenshot_path": self.screenshot_path,
            "timestamp": self.timestamp.isoformat(),
            "performance": {
                "extraction_time_ms": self.extraction_time_ms,
                "model_inference_time_ms": self.model_inference_time_ms,
                "fusion_time_ms": self.fusion_time_ms,
            },
            "counts": {
                "total_elements": self.total_elements,
                "fused": self.fused_count,
                "vision_only": self.vision_only_count,
                "dom_only": self.dom_only_count,
            },
            "metrics": {
                "fusion_success_rate": self.fusion_success_rate,
                "average_iou": self.average_iou,
            },
            "elements": [e.to_dict() for e in self.fused_elements],
            "metadata": self.metadata,
        }
