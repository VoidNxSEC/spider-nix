"""
Fusion Engine - Core Innovation for Vision-DOM matching.

Uses IoU (Intersection over Union) algorithm to match visual detections
with DOM elements, creating high-confidence extractions that are resilient
to CSS class changes.

This is the key innovation that enables CSS-independent web scraping.
"""

from typing import List, Tuple, Set

from .models import (
    VisionDetection,
    DOMElement,
    FusedElement,
    BoundingBox
)


class FusionEngine:
    """
    Vision-DOM fusion using IoU (Intersection over Union) matching.
    
    Algorithm:
    1. For each vision detection:
       a. Find DOM elements with matching type
       b. Calculate IoU with each matching element
       c. If IoU > threshold: FUSED (high confidence)
       d. Else: VISION_ONLY (medium confidence)
    2. Unmatched DOM elements: DOM_ONLY (low confidence)
    
    The fusion creates extractions resilient to CSS changes because:
    - Visual position doesn't change when CSS classes change
    - DOM structure is more stable than CSS class names
    - IoU ensures spatial correlation even with minor shifts
    """

    def __init__(self, iou_threshold: float = 0.5, confidence_weights: dict | None = None):
        """
        Initialize fusion engine.
        
        Args:
            iou_threshold: Minimum IoU to consider elements matched
            confidence_weights: Custom weights for confidence calculation
                               (vision_weight, iou_weight, type_match_weight)
        """
        self.iou_threshold = iou_threshold
        self.confidence_weights = confidence_weights or {
            'vision': 0.6,
            'iou': 0.3,
            'type_match': 0.1
        }

    def fuse(
        self,
        vision_detections: List[VisionDetection],
        dom_elements: List[DOMElement]
    ) -> List[FusedElement]:
        """
        Match vision detections to DOM elements using IoU algorithm.
        
        Args:
            vision_detections: Elements detected by vision model
            dom_elements: Elements extracted from DOM
            
        Returns:
            List of fused elements with confidence scores
        """
        fused = []
        matched_dom_indices: Set[int] = set()

        # Phase 1: Match vision → DOM
        for vision in vision_detections:
            best_match = None
            best_iou = 0.0
            best_dom_idx = None

            # Find matching DOM elements by type
            for idx, dom in enumerate(dom_elements):
                if idx in matched_dom_indices:
                    continue  # Already matched

                # Type compatibility check
                if not self._types_compatible(vision.element_type, dom):
                    continue

                # Position compatibility check (DOM must have position)
                if dom.bounding_box is None:
                    continue

                # Calculate IoU
                iou = self.calculate_iou(vision.bounding_box, dom.bounding_box)

                if iou > best_iou:
                    best_iou = iou
                    best_match = dom
                    best_dom_idx = idx

            # Create FusedElement based on match quality
            if best_iou >= self.iou_threshold:
                # FUSED: High confidence extraction
                fused_elem = FusedElement(
                    vision=vision,
                    dom=best_match,
                    iou_score=best_iou,
                    extraction_confidence=self._calculate_confidence(
                        vision, best_match, best_iou, True
                    ),
                    extraction_method="fused",
                    fusion_metadata={
                        "vision_confidence": vision.confidence,
                        "iou": best_iou,
                        "type_match": True,
                        "matching_method": "iou_spatial"
                    }
                )
                matched_dom_indices.add(best_dom_idx)
            else:
                # VISION_ONLY: Medium confidence (no DOM match)
                fused_elem = FusedElement(
                    vision=vision,
                    dom=None,
                    iou_score=0.0,
                    extraction_confidence=vision.confidence * 0.7,  # Penalize non-fusion
                    extraction_method="vision_only",
                    fusion_metadata={
                        "vision_confidence": vision.confidence,
                        "reason": "no_dom_match" if best_dom_idx is None else "iou_too_low",
                        "best_iou": best_iou
                    }
                )

            fused.append(fused_elem)

        # Phase 2: Unmatched DOM elements (DOM_ONLY)
        for idx, dom in enumerate(dom_elements):
            if idx in matched_dom_indices:
                continue  # Already matched

            # Create synthetic vision detection for consistency
            synthetic_vision = VisionDetection(
                element_type=dom.tag_name,
                bounding_box=dom.bounding_box or BoundingBox(0, 0, 0, 0),
                confidence=0.5,  # Low confidence (no visual confirmation)
                text_content=dom.text_content,
                model_id="dom_fallback"
            )

            fused_elem = FusedElement(
                vision=synthetic_vision,
                dom=dom,
                iou_score=0.0,
                extraction_confidence=0.5,  # Low confidence
                extraction_method="dom_only",
                fusion_metadata={
                    "reason": "no_vision_match",
                    "dom_selector": dom.css_selector
                }
            )
            fused.append(fused_elem)

        return fused

    def calculate_iou(self, box1: BoundingBox, box2: BoundingBox) -> float:
        """
        Calculate Intersection over Union (IoU).
        
        IoU measures overlap between two bounding boxes:
        - IoU = Area(Intersection) / Area(Union)
        - Range: 0.0 (no overlap) to 1.0 (perfect overlap)
        
        Args:
            box1: First bounding box
            box2: Second bounding box
            
        Returns:
            IoU score (0.0-1.0)
        """
        # Calculate intersection rectangle
        x_left = max(box1.x, box2.x)
        y_top = max(box1.y, box2.y)
        x_right = min(box1.x + box1.width, box2.x + box2.width)
        y_bottom = min(box1.y + box1.height, box2.y + box2.height)

        # Check if boxes intersect
        if x_right < x_left or y_bottom < y_top:
            return 0.0  # No intersection

        # Calculate areas
        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        box1_area = box1.area()
        box2_area = box2.area()
        union_area = box1_area + box2_area - intersection_area

        # Calculate IoU
        if union_area == 0:
            return 0.0

        iou = intersection_area / union_area
        return max(0.0, min(1.0, iou))  # Clamp to [0, 1]

    def _types_compatible(self, vision_type: str, dom_element: DOMElement) -> bool:
        """
        Check if vision detection type is compatible with DOM element.
        
        Uses fuzzy matching for better recall:
        - "button" matches: button, input[type=button|submit]
        - "link" matches: a[href]
        - "input" matches: input, textarea, select
        """
        return dom_element.matches_type(vision_type)

    def _calculate_confidence(
        self,
        vision: VisionDetection,
        dom: DOMElement,
        iou: float,
        type_match: bool
    ) -> float:
        """
        Calculate combined confidence score using weighted formula.
        
        Formula:
            confidence = (vision_conf * w1) + (iou * w2) + (type_match * w3)
        
        Where:
            w1 = vision weight (default 0.6) - model confidence
            w2 = iou weight (default 0.3) - spatial correlation
            w3 = type_match weight (default 0.1) - semantic match
            
        Returns:
            Combined confidence (0.0-1.0)
        """
        vision_conf = vision.confidence
        iou_score = iou
        type_match_score = 1.0 if type_match else 0.5

        confidence = (
            vision_conf * self.confidence_weights['vision'] +
            iou_score * self.confidence_weights['iou'] +
            type_match_score * self.confidence_weights['type_match']
        )

        return max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

    def get_fusion_statistics(self, fused_elements: List[FusedElement]) -> dict:
        """
        Calculate fusion statistics for quality assessment.
        
        Returns:
            Dict with metrics: fusion_rate, avg_iou, avg_confidence, etc.
        """
        if not fused_elements:
            return {
                "total": 0,
                "fused": 0,
                "vision_only": 0,
                "dom_only": 0,
                "fusion_rate": 0.0,
                "avg_iou": 0.0,
                "avg_confidence": 0.0,
                "high_confidence_count": 0
            }

        fused = [e for e in fused_elements if e.extraction_method == "fused"]
        vision_only = [e for e in fused_elements if e.extraction_method == "vision_only"]
        dom_only = [e for e in fused_elements if e.extraction_method == "dom_only"]

        avg_iou = sum(e.iou_score for e in fused) / len(fused) if fused else 0.0
        avg_confidence = sum(e.extraction_confidence for e in fused_elements) / len(fused_elements)
        high_conf = [e for e in fused_elements if e.extraction_confidence > 0.8]

        return {
            "total": len(fused_elements),
            "fused": len(fused),
            "vision_only": len(vision_only),
            "dom_only": len(dom_only),
            "fusion_rate": (len(fused) / len(fused_elements)) * 100,
            "avg_iou": avg_iou,
            "avg_confidence": avg_confidence,
            "high_confidence_count": len(high_conf),
            "resilient_count": len([e for e in fused_elements if e.is_resilient])
        }
