"""Fusion engine for combining vision and DOM extraction results."""

from typing import Literal

from .models import DOMElement, FusedElement, VisionDetection


class FusionEngine:
    """Fuse vision AI detections with DOM structure using IoU matching.

    This provides CSS-resilient extraction by anchoring to visual coordinates
    as ground truth, then mapping to DOM elements for selector generation.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        confidence_threshold: float = 0.5,
    ):
        """Initialize fusion engine.

        Args:
            iou_threshold: Minimum IoU score to consider a match
            confidence_threshold: Minimum vision confidence to trust detection
        """
        self.iou_threshold = iou_threshold
        self.confidence_threshold = confidence_threshold

    def fuse(
        self,
        vision_detections: list[VisionDetection],
        dom_elements: list[DOMElement],
        strategy: Literal["greedy", "optimal"] = "greedy",
    ) -> list[FusedElement]:
        """Fuse vision detections with DOM elements.

        Args:
            vision_detections: Vision AI detections with bounding boxes
            dom_elements: Parsed DOM elements with positions
            strategy: Matching strategy ('greedy' or 'optimal')

        Returns:
            List of fused elements with vision-DOM mappings
        """
        if strategy == "greedy":
            return self._fuse_greedy(vision_detections, dom_elements)
        elif strategy == "optimal":
            return self._fuse_optimal(vision_detections, dom_elements)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _fuse_greedy(
        self,
        vision_detections: list[VisionDetection],
        dom_elements: list[DOMElement],
    ) -> list[FusedElement]:
        """Greedy fusion: match each vision detection to best DOM element.

        Simple but fast. May have multiple vision detections map to same DOM element.
        """
        fused = []

        # Filter DOM elements with positions
        positioned_dom = [e for e in dom_elements if e.bounding_box is not None]

        for vision in vision_detections:
            best_match = None
            best_iou = 0.0

            # Find best matching DOM element by IoU
            for dom in positioned_dom:
                iou = vision.bounding_box.iou(dom.bounding_box)
                if iou > best_iou and iou >= self.iou_threshold:
                    best_iou = iou
                    best_match = dom

            # Calculate extraction confidence
            confidence = self._calculate_confidence(vision, best_match, best_iou)

            # Determine strategy used
            if best_match and vision.confidence >= self.confidence_threshold:
                strategy_used = "fused"
            elif vision.confidence >= self.confidence_threshold:
                strategy_used = "vision_only"
            elif best_match:
                strategy_used = "dom_only"
            else:
                strategy_used = "low_confidence"

            fused.append(
                FusedElement(
                    vision=vision,
                    dom=best_match,
                    iou_score=best_iou,
                    extraction_confidence=confidence,
                    strategy=strategy_used,
                )
            )

        # Add unmatched high-quality DOM elements
        matched_dom_xpaths = {f.dom.xpath for f in fused if f.dom}
        for dom in positioned_dom:
            if dom.xpath not in matched_dom_xpaths and self._is_important_element(dom):
                fused.append(
                    FusedElement(
                        vision=None,
                        dom=dom,
                        iou_score=0.0,
                        extraction_confidence=0.6,  # DOM-only confidence
                        strategy="dom_only",
                    )
                )

        return fused

    def _fuse_optimal(
        self,
        vision_detections: list[VisionDetection],
        dom_elements: list[DOMElement],
    ) -> list[FusedElement]:
        """Optimal fusion using Hungarian algorithm for bipartite matching.

        Ensures 1:1 mapping between vision and DOM, maximizing global IoU.
        More accurate but slower for large element counts.
        """
        # Filter positioned DOM elements
        positioned_dom = [e for e in dom_elements if e.bounding_box is not None]

        if not vision_detections or not positioned_dom:
            return self._fuse_greedy(vision_detections, dom_elements)

        # Build cost matrix (negative IoU for maximization)
        n_vision = len(vision_detections)
        n_dom = len(positioned_dom)
        cost_matrix = []

        for vision in vision_detections:
            row = []
            for dom in positioned_dom:
                iou = vision.bounding_box.iou(dom.bounding_box)
                # Negative because scipy minimizes
                cost = -iou if iou >= self.iou_threshold else 0
                row.append(cost)
            cost_matrix.append(row)

        # Try to use scipy for optimal matching
        try:
            from scipy.optimize import linear_sum_assignment
            vision_indices, dom_indices = linear_sum_assignment(cost_matrix)
        except ImportError:
            # Fallback to greedy if scipy not available
            return self._fuse_greedy(vision_detections, dom_elements)

        # Build fused results
        fused = []
        matched_dom_indices = set()

        for v_idx, d_idx in zip(vision_indices, dom_indices):
            vision = vision_detections[v_idx]
            dom = positioned_dom[d_idx]
            iou = vision.bounding_box.iou(dom.bounding_box)

            if iou >= self.iou_threshold:
                confidence = self._calculate_confidence(vision, dom, iou)
                matched_dom_indices.add(d_idx)

                fused.append(
                    FusedElement(
                        vision=vision,
                        dom=dom,
                        iou_score=iou,
                        extraction_confidence=confidence,
                        strategy="fused",
                    )
                )
            else:
                # No good match, vision-only
                fused.append(
                    FusedElement(
                        vision=vision,
                        dom=None,
                        iou_score=0.0,
                        extraction_confidence=vision.confidence,
                        strategy="vision_only",
                    )
                )

        # Add unmatched DOM elements
        for idx, dom in enumerate(positioned_dom):
            if idx not in matched_dom_indices and self._is_important_element(dom):
                fused.append(
                    FusedElement(
                        vision=None,
                        dom=dom,
                        iou_score=0.0,
                        extraction_confidence=0.6,
                        strategy="dom_only",
                    )
                )

        return fused

    def _calculate_confidence(
        self,
        vision: VisionDetection,
        dom: DOMElement | None,
        iou_score: float,
    ) -> float:
        """Calculate overall extraction confidence.

        Combines:
        - Vision model confidence
        - IoU score (spatial agreement)
        - Text matching score
        - Element type consistency
        """
        # Base confidence from vision
        confidence = vision.confidence

        # Boost if DOM matched with good IoU
        if dom and iou_score > 0:
            confidence *= (0.7 + 0.3 * iou_score)  # IoU bonus

            # Text similarity bonus
            if vision.text and dom.text_content:
                text_sim = self._text_similarity(vision.text, dom.text_content)
                confidence *= (0.8 + 0.2 * text_sim)

            # Element type consistency
            if self._types_match(vision.element_type, dom.tag_name):
                confidence *= 1.1

        # Clamp to [0, 1]
        return min(max(confidence, 0.0), 1.0)

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Simple text similarity (case-insensitive containment).

        Returns:
            Similarity score 0-1
        """
        if not text1 or not text2:
            return 0.0

        t1 = text1.lower().strip()
        t2 = text2.lower().strip()

        # Exact match
        if t1 == t2:
            return 1.0

        # Containment
        if t1 in t2 or t2 in t1:
            return 0.8

        # Word overlap
        words1 = set(t1.split())
        words2 = set(t2.split())
        if words1 and words2:
            overlap = len(words1 & words2) / max(len(words1), len(words2))
            return overlap

        return 0.0

    def _types_match(self, vision_type: str, dom_tag: str) -> bool:
        """Check if vision element type matches DOM tag."""
        type_mapping = {
            "button": ["button", "input"],
            "input": ["input", "textarea"],
            "link": ["a"],
            "image": ["img"],
            "text": ["p", "span", "div", "h1", "h2", "h3", "h4", "h5", "h6"],
        }

        expected_tags = type_mapping.get(vision_type.lower(), [])
        return dom_tag.lower() in expected_tags

    def _is_important_element(self, dom: DOMElement) -> bool:
        """Check if DOM element is important enough to include.

        Filters out noise like empty divs, invisible elements, etc.
        """
        # Must have some content or be interactive
        if not dom.text_content and dom.tag_name not in ["input", "button", "a", "img"]:
            return False

        # Must have reasonable size (filter tiny elements)
        if dom.bounding_box:
            area = dom.bounding_box.width * dom.bounding_box.height
            if area < 0.0001:  # Very small (< 0.01% of viewport)
                return False

        # Has interactive attributes
        if any(attr in dom.attributes for attr in ["onclick", "href", "role", "data-testid"]):
            return True

        # Has text content
        if dom.text_content and len(dom.text_content.strip()) > 2:
            return True

        return False

    def filter_high_confidence(
        self,
        fused_elements: list[FusedElement],
        min_confidence: float = 0.7,
    ) -> list[FusedElement]:
        """Filter fused elements by confidence threshold.

        Args:
            fused_elements: Fused elements to filter
            min_confidence: Minimum confidence threshold

        Returns:
            Filtered list of high-confidence elements
        """
        return [e for e in fused_elements if e.extraction_confidence >= min_confidence]
