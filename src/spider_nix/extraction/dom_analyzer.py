"""DOM analyzer for structural HTML/DOM parsing."""

import json
from typing import Any
from urllib.parse import urljoin

from lxml import html as lxml_html
from lxml.cssselect import CSSSelector

from .models import BoundingBox, DOMElement


class DOMAnalyzer:
    """Analyze HTML/DOM structure to extract elements with positions.

    Uses lxml for fast parsing and XPath generation.
    Positions come from browser's getBoundingClientRect via Playwright.
    """

    def __init__(self, viewport_width: int = 1920, viewport_height: int = 1080):
        """Initialize DOM analyzer.

        Args:
            viewport_width: Browser viewport width (for normalization)
            viewport_height: Browser viewport height (for normalization)
        """
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height

    def parse_html(
        self,
        html_content: str,
        base_url: str | None = None,
        element_positions: dict[str, dict] | None = None,
    ) -> list[DOMElement]:
        """Parse HTML and extract DOM elements.

        Args:
            html_content: Raw HTML content
            base_url: Base URL for resolving relative links
            element_positions: Dict mapping xpath -> position data from browser

        Returns:
            List of parsed DOM elements
        """
        try:
            tree = lxml_html.fromstring(html_content)
        except Exception as e:
            # Fallback to recovery mode for malformed HTML
            try:
                parser = lxml_html.HTMLParser(recover=True)
                tree = lxml_html.fromstring(html_content, parser)
            except Exception:
                raise ValueError(f"Failed to parse HTML: {e}") from e

        # Make URLs absolute if base_url provided
        if base_url:
            tree.make_links_absolute(base_url)

        elements = []

        # Extract interactive and content elements
        selectors = [
            "//a",  # Links
            "//button",  # Buttons
            "//input",  # Inputs
            "//textarea",  # Textareas
            "//select",  # Dropdowns
            "//img",  # Images
            "//h1 | //h2 | //h3 | //h4 | //h5 | //h6",  # Headers
            "//p",  # Paragraphs
            "//div[@role='button']",  # DIV buttons
            "//span[@onclick]",  # Clickable spans
            "//*[@data-testid]",  # Test IDs (common in modern apps)
        ]

        seen_elements = set()

        for selector in selectors:
            for element in tree.xpath(selector):
                xpath = tree.getpath(element)

                # Avoid duplicates
                if xpath in seen_elements:
                    continue
                seen_elements.add(xpath)

                # Generate CSS selector (simple version)
                css_selector = self._generate_css_selector(element)

                # Get position if available
                bounding_box = None
                if element_positions and xpath in element_positions:
                    pos = element_positions[xpath]
                    # Normalize coordinates
                    bounding_box = BoundingBox(
                        x=pos.get("x", 0) / self.viewport_width,
                        y=pos.get("y", 0) / self.viewport_height,
                        width=pos.get("width", 0) / self.viewport_width,
                        height=pos.get("height", 0) / self.viewport_height,
                    )

                # Extract attributes
                attributes = dict(element.attrib)

                # Get text content
                text_content = element.text_content().strip() if element.text_content() else None

                # Get inner HTML (first 500 chars to avoid bloat)
                try:
                    inner_html = lxml_html.tostring(element, encoding="unicode")[:500]
                except Exception:
                    inner_html = None

                elements.append(
                    DOMElement(
                        tag_name=element.tag,
                        xpath=xpath,
                        css_selector=css_selector,
                        bounding_box=bounding_box,
                        text_content=text_content,
                        attributes=attributes,
                        inner_html=inner_html,
                    )
                )

        return elements

    def _generate_css_selector(self, element) -> str:
        """Generate CSS selector for element.

        Creates a simple but unique CSS selector.
        Prefers: id > class > tag + nth-child
        """
        # Use ID if available
        if element.get("id"):
            return f"#{element.get('id')}"

        # Use class if available
        classes = element.get("class")
        if classes:
            class_selector = "." + ".".join(classes.split()[:2])  # Max 2 classes
            return f"{element.tag}{class_selector}"

        # Use tag with nth-child
        parent = element.getparent()
        if parent is not None:
            siblings = [e for e in parent if e.tag == element.tag]
            if len(siblings) > 1:
                index = siblings.index(element) + 1
                return f"{element.tag}:nth-child({index})"

        return element.tag

    def extract_links(self, html_content: str, base_url: str | None = None) -> list[str]:
        """Extract all links from HTML.

        Args:
            html_content: Raw HTML content
            base_url: Base URL for resolving relative links

        Returns:
            List of absolute URLs
        """
        try:
            tree = lxml_html.fromstring(html_content)
        except Exception:
            return []

        if base_url:
            tree.make_links_absolute(base_url)

        links = set()
        for element in tree.xpath("//a[@href]"):
            href = element.get("href")
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                links.add(href)

        return list(links)

    def extract_metadata(self, html_content: str) -> dict[str, Any]:
        """Extract page metadata (title, description, OG tags, etc).

        Args:
            html_content: Raw HTML content

        Returns:
            Dictionary of metadata
        """
        try:
            tree = lxml_html.fromstring(html_content)
        except Exception:
            return {}

        metadata = {}

        # Title
        title_elements = tree.xpath("//title/text()")
        if title_elements:
            metadata["title"] = title_elements[0].strip()

        # Meta description
        desc_elements = tree.xpath("//meta[@name='description']/@content")
        if desc_elements:
            metadata["description"] = desc_elements[0].strip()

        # Open Graph tags
        og_tags = {}
        for meta in tree.xpath("//meta[starts-with(@property, 'og:')]"):
            prop = meta.get("property", "").replace("og:", "")
            content = meta.get("content", "")
            if prop and content:
                og_tags[prop] = content
        if og_tags:
            metadata["og"] = og_tags

        # Twitter Card tags
        twitter_tags = {}
        for meta in tree.xpath("//meta[starts-with(@name, 'twitter:')]"):
            name = meta.get("name", "").replace("twitter:", "")
            content = meta.get("content", "")
            if name and content:
                twitter_tags[name] = content
        if twitter_tags:
            metadata["twitter"] = twitter_tags

        # Canonical URL
        canonical = tree.xpath("//link[@rel='canonical']/@href")
        if canonical:
            metadata["canonical"] = canonical[0]

        return metadata

    @staticmethod
    def get_playwright_position_script() -> str:
        """JavaScript to inject in Playwright to get element positions.

        Returns positions as dict mapping XPath -> {x, y, width, height}
        """
        return """
        () => {
            const positions = {};

            // Helper to get XPath for element
            function getXPath(element) {
                if (element.id) {
                    return `//*[@id="${element.id}"]`;
                }

                const parts = [];
                let current = element;

                while (current && current.nodeType === Node.ELEMENT_NODE) {
                    let index = 0;
                    let sibling = current.previousSibling;

                    while (sibling) {
                        if (sibling.nodeType === Node.ELEMENT_NODE &&
                            sibling.nodeName === current.nodeName) {
                            index++;
                        }
                        sibling = sibling.previousSibling;
                    }

                    const tagName = current.nodeName.toLowerCase();
                    const pathIndex = index > 0 ? `[${index + 1}]` : '';
                    parts.unshift(`${tagName}${pathIndex}`);

                    current = current.parentNode;
                }

                return '/' + parts.join('/');
            }

            // Get positions for all visible elements
            const selectors = [
                'a', 'button', 'input', 'textarea', 'select',
                'img', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'p', '[role="button"]', '[onclick]', '[data-testid]'
            ];

            selectors.forEach(selector => {
                const elements = document.querySelectorAll(selector);
                elements.forEach(element => {
                    const rect = element.getBoundingClientRect();

                    // Only include visible elements
                    if (rect.width > 0 && rect.height > 0) {
                        const xpath = getXPath(element);
                        positions[xpath] = {
                            x: rect.left + window.scrollX,
                            y: rect.top + window.scrollY,
                            width: rect.width,
                            height: rect.height
                        };
                    }
                });
            });

            return positions;
        }
        """
