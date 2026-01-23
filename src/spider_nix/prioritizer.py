"""Smart link prioritization with scoring for intelligent crawling."""

import asyncio
import heapq
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse


@dataclass(order=True)
class PrioritizedLink:
    """Link with priority score for queue ordering."""

    priority: float = field(compare=True)
    url: str = field(compare=False)
    depth: int = field(default=0, compare=False)
    parent_url: str = field(default="", compare=False)
    metadata: dict = field(default_factory=dict, compare=False)

    def __post_init__(self):
        # Negate priority for min-heap (higher priority first)
        self.priority = -self.priority


class LinkPrioritizer:
    """
    Smart link prioritization engine with configurable scoring.

    Prioritizes links based on:
    - URL patterns (e.g., /api/, /docs/, /product/)
    - Content keywords
    - Link depth
    - URL length
    - File extensions
    - Custom scoring functions
    """

    def __init__(
        self,
        pattern_scores: dict[str, float] | None = None,
        keyword_scores: dict[str, float] | None = None,
        depth_penalty: float = 0.1,
        max_url_length: int = 200,
        length_penalty: float = 0.01,
        prioritize_shallow: bool = True,
        custom_scorer: Callable[[str], float] | None = None,
    ):
        """
        Initialize link prioritizer.

        Args:
            pattern_scores: URL patterns to score (regex -> score)
            keyword_scores: Keywords in path to score (keyword -> score)
            depth_penalty: Score penalty per depth level
            max_url_length: Maximum URL length before penalty
            length_penalty: Penalty per character over max_url_length
            prioritize_shallow: Higher priority for shallow links
            custom_scorer: Optional custom scoring function
        """
        self.pattern_scores = pattern_scores or self._default_patterns()
        self.keyword_scores = keyword_scores or self._default_keywords()
        self.depth_penalty = depth_penalty
        self.max_url_length = max_url_length
        self.length_penalty = length_penalty
        self.prioritize_shallow = prioritize_shallow
        self.custom_scorer = custom_scorer

        self._queue: list[PrioritizedLink] = []
        self._lock = asyncio.Lock()
        self._counter = 0  # For FIFO when priorities are equal

    @staticmethod
    def _default_patterns() -> dict[str, float]:
        """Default URL pattern scores."""
        return {
            r"/api/": 5.0,
            r"/docs?/": 4.0,
            r"/documentation/": 4.0,
            r"/reference/": 4.0,
            r"/guide/": 3.5,
            r"/tutorial/": 3.5,
            r"/product/": 3.0,
            r"/pricing/": 2.5,
            r"/blog/": 2.0,
            r"/article/": 2.0,
            r"/news/": 2.0,
            r"/about/": 1.5,
            r"/contact/": 1.0,
            r"/login/": 0.5,
            r"/logout/": 0.5,
            r"/search\?": 0.3,
            r"/tag/": 0.2,
            r"/category/": 0.2,
        }

    @staticmethod
    def _default_keywords() -> dict[str, float]:
        """Default keyword scores."""
        return {
            "documentation": 3.0,
            "tutorial": 2.5,
            "guide": 2.5,
            "reference": 2.5,
            "api": 3.0,
            "sdk": 2.0,
            "example": 2.0,
            "integration": 1.5,
            "feature": 1.5,
            "product": 1.5,
            "pricing": 1.0,
            "download": 1.5,
            "install": 1.5,
        }

    def calculate_score(
        self,
        url: str,
        depth: int = 0,
        parent_url: str = "",
    ) -> float:
        """
        Calculate priority score for URL.

        Higher score = higher priority.

        Returns:
            Priority score (0.0 - 10.0+)
        """
        score = 1.0  # Base score

        parsed = urlparse(url)
        path = parsed.path.lower()
        query = parsed.query.lower()

        # Pattern matching
        for pattern, pattern_score in self.pattern_scores.items():
            if re.search(pattern, path):
                score += pattern_score

        # Keyword matching
        for keyword, keyword_score in self.keyword_scores.items():
            if keyword in path or keyword in query:
                score += keyword_score

        # Depth penalty
        if self.prioritize_shallow:
            score -= depth * self.depth_penalty

        # URL length penalty (very long URLs often less important)
        url_length = len(url)
        if url_length > self.max_url_length:
            score -= (url_length - self.max_url_length) * self.length_penalty

        # File extension penalties/bonuses
        if path.endswith((".pdf", ".doc", ".docx")):
            score += 1.0
        elif path.endswith((".jpg", ".png", ".gif", ".svg", ".ico")):
            score -= 2.0  # Deprioritize images
        elif path.endswith((".css", ".js", ".woff", ".ttf")):
            score -= 3.0  # Deprioritize assets
        elif path.endswith((".html", ".htm", "/")):
            score += 0.5  # Slight bonus for HTML pages

        # Custom scorer
        if self.custom_scorer:
            custom_score = self.custom_scorer(url)
            score += custom_score

        # Ensure non-negative
        return max(score, 0.0)

    async def add_link(
        self,
        url: str,
        depth: int = 0,
        parent_url: str = "",
        metadata: dict | None = None,
    ):
        """Add link to priority queue."""
        score = self.calculate_score(url, depth, parent_url)

        link = PrioritizedLink(
            priority=score,
            url=url,
            depth=depth,
            parent_url=parent_url,
            metadata=metadata or {},
        )

        async with self._lock:
            heapq.heappush(self._queue, link)
            self._counter += 1

    async def get_next_link(self, timeout: float = 2.0) -> PrioritizedLink | None:
        """Get next highest-priority link."""
        start_time = asyncio.get_event_loop().time()

        while True:
            async with self._lock:
                if self._queue:
                    return heapq.heappop(self._queue)

            # Check timeout
            if asyncio.get_event_loop().time() - start_time > timeout:
                return None

            await asyncio.sleep(0.1)

    async def get_link_nowait(self) -> PrioritizedLink | None:
        """Get next link without waiting."""
        async with self._lock:
            if self._queue:
                return heapq.heappop(self._queue)
            return None

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._queue) == 0

    def size(self) -> int:
        """Get queue size."""
        return len(self._queue)

    def clear(self):
        """Clear all links from queue."""
        self._queue.clear()
        self._counter = 0

    def peek_top(self, n: int = 10) -> list[tuple[str, float]]:
        """Peek at top N links without removing them."""
        top_links = heapq.nsmallest(n, self._queue)
        return [(link.url, -link.priority) for link in top_links]


class BreadthFirstPrioritizer(LinkPrioritizer):
    """Prioritizer that prefers breadth-first traversal (shallow links first)."""

    def __init__(self, **kwargs):
        super().__init__(
            pattern_scores={},
            keyword_scores={},
            depth_penalty=1.0,  # Strong depth penalty
            prioritize_shallow=True,
            **kwargs,
        )

    def calculate_score(self, url: str, depth: int = 0, parent_url: str = "") -> float:
        """Score based primarily on depth."""
        return 10.0 - (depth * self.depth_penalty)


class DepthFirstPrioritizer(LinkPrioritizer):
    """Prioritizer that prefers depth-first traversal (deep links first)."""

    def __init__(self, **kwargs):
        super().__init__(
            pattern_scores={},
            keyword_scores={},
            depth_penalty=-1.0,  # Negative penalty = bonus for depth
            prioritize_shallow=False,
            **kwargs,
        )

    def calculate_score(self, url: str, depth: int = 0, parent_url: str = "") -> float:
        """Score based primarily on depth."""
        return 1.0 + (depth * abs(self.depth_penalty))


class FocusedCrawlPrioritizer(LinkPrioritizer):
    """Prioritizer for focused/topical crawling with keyword emphasis."""

    def __init__(self, focus_keywords: list[str], **kwargs):
        """
        Initialize focused crawler.

        Args:
            focus_keywords: Keywords to focus on (e.g., ["api", "docs"])
        """
        # Build keyword scores
        keyword_scores = {kw.lower(): 10.0 for kw in focus_keywords}

        super().__init__(
            keyword_scores=keyword_scores,
            depth_penalty=0.2,
            prioritize_shallow=False,
            **kwargs,
        )


async def prioritizer_example():
    """Example usage of LinkPrioritizer."""
    from rich.console import Console

    console = Console()

    # Create prioritizer
    prioritizer = LinkPrioritizer()

    # Add various links
    test_urls = [
        ("https://example.com/", 0),
        ("https://example.com/api/v1/users", 1),
        ("https://example.com/blog/post-1", 1),
        ("https://example.com/docs/getting-started", 1),
        ("https://example.com/product/features", 1),
        ("https://example.com/about/team", 1),
        ("https://example.com/contact", 1),
        ("https://example.com/style.css", 1),
        ("https://example.com/image.png", 1),
        ("https://example.com/api/v1/products", 1),
        ("https://example.com/docs/api-reference", 2),
        ("https://example.com/docs/tutorial/intro", 2),
    ]

    for url, depth in test_urls:
        await prioritizer.add_link(url, depth=depth)

    console.print("[bold cyan]Link Priority Queue:[/]\n")

    # Show prioritized order
    rank = 1
    while not prioritizer.is_empty():
        link = await prioritizer.get_next_link()
        if link:
            score = -link.priority
            console.print(
                f"[cyan]{rank:2d}.[/] [white]{link.url:60s}[/] "
                f"[yellow]Score: {score:5.2f}[/] [dim]Depth: {link.depth}[/]"
            )
            rank += 1


if __name__ == "__main__":
    asyncio.run(prioritizer_example())
