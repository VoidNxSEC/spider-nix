"""
DOM Analyzer for parallel HTML/DOM analysis with position calculation.

Extracts all interactive elements from HTML with their bounding boxes,
generating XPath and CSS selectors for reliable element targeting.
"""

import asyncio
from typing import List, Optional

from lxml import html, etree
from bs4 import BeautifulSoup

from .models import DOMElement, BoundingBox


class DOMAnalyzer:
    """
    Parallel HTML/DOM analysis with position calculation.
    
    Uses both lxml (fast) and BeautifulSoup (robust) for comprehensive parsing.
    Calculates element positions via Playwright's getBoundingClientRect().
    """

    def __init__(self):
        self.parser = html.HTMLParser()

    async def analyze_page(
        self,
        html_content: str,
        page_handle=None,  # Playwright page for getBoundingClientRect
        viewport_width: int = 1920,
        viewport_height: int = 1080,
    ) -> List[DOMElement]:
        """
        Extract all interactive elements from DOM with positions.
        
        Args:
            html_content: Raw HTML string
            page_handle: Playwright page (optional, for position data)
            viewport_width: Viewport width for normalization
            viewport_height: Viewport height for normalization
            
        Returns:
            List of DOM elements with bounding boxes
        """
        # Parse HTML with lxml (fast) + BeautifulSoup (robust)
        tree = html.fromstring(html_content)
        soup = BeautifulSoup(html_content, 'lxml')

        elements = []

        # Target interactive elements only
        selectors = [
            ("button", "//button"),
            ("a", "//a[@href]"),
            ("input", "//input"),
            ("textarea", "//textarea"),
            ("select", "//select"),
            ("form", "//form"),
            # Additional semantic elements
            ("nav", "//nav"),
            ("menu", "//menu"),
        ]

        for tag, xpath_query in selectors:
            nodes = tree.xpath(xpath_query)

            for node in nodes:
                try:
                    # Generate XPath and CSS selector
                    xpath_expr = tree.getpath(node)
                    css_selector = self._generate_css_selector(node, tree)

                    # Extract attributes
                    attrs = dict(node.attrib)
                    text = (node.text_content() or "").strip()

                    # Get position if Playwright page available
                    bbox = None
                    if page_handle:
                        bbox = await self._get_element_position(
                            page_handle,
                            css_selector,
                            viewport_width,
                            viewport_height
                        )

                    element = DOMElement(
                        xpath=xpath_expr,
                        css_selector=css_selector,
                        tag_name=tag,
                        text_content=text,
                        attributes=attrs,
                        bounding_box=bbox
                    )
                    elements.append(element)

                except Exception as e:
                    # Skip problematic elements
                    continue

        return elements

    def _generate_css_selector(self, node, tree) -> str:
        """
        Generate unique CSS selector for element.
        
        Priority: ID > unique class > data-testid > nth-child path
        """
        # Check for ID (most unique)
        if node.get('id'):
            element_id = node.get('id')
            # Escape special characters in ID
            escaped_id = element_id.replace(':', '\\:').replace('.', '\\.')
            return f"#{escaped_id}"

        # Check for data-testid (common in modern apps)
        if node.get('data-testid'):
            return f"[data-testid='{node.get('data-testid')}']"

        # Check for unique class
        classes = node.get('class', '').split()
        for cls in classes:
            if cls:
                # Test if class is unique
                selector = f"{node.tag}.{cls}"
                matches = tree.cssselect(selector)
                if len(matches) == 1:
                    return selector

        # Fallback: nth-child path (always unique but fragile)
        return self._generate_nth_child_path(node)

    def _generate_nth_child_path(self, node) -> str:
        """
        Generate nth-child CSS path (guaranteed unique but fragile).
        
        Example: body > div:nth-child(1) > main:nth-child(2) > button:nth-child(3)
        """
        path = []
        current = node

        while current.getparent() is not None:
            parent = current.getparent()
            siblings = [n for n in parent if n.tag == current.tag]
            
            if len(siblings) > 1:
                index = siblings.index(current) + 1
                path.insert(0, f"{current.tag}:nth-child({index})")
            else:
                path.insert(0, current.tag)
            
            current = parent

        return " > ".join(path)

    async def _get_element_position(
        self,
        page,
        css_selector: str,
        viewport_width: int,
        viewport_height: int
    ) -> Optional[BoundingBox]:
        """
        Get element position using Playwright's getBoundingClientRect().
        
        Returns normalized bounding box (0-1 coordinates).
        """
        try:
            # Query element
            element = await page.query_selector(css_selector)
            if not element:
                return None

            # Get bounding box via JS
            box = await element.bounding_box()
            if not box:
                return None

            # Normalize to 0-1 coordinates
            return BoundingBox(
                x=box['x'] / viewport_width,
                y=box['y'] / viewport_height,
                width=box['width'] / viewport_width,
                height=box['height'] / viewport_height
            )

        except Exception as e:
            # Element not visible, removed, or inaccessible
            return None

    async def get_all_clickable_elements(
        self,
        page,
        viewport_width: int = 1920,
        viewport_height: int = 1080
    ) -> List[DOMElement]:
        """
        Alternative: Get all clickable elements via JS query.
        
        Uses document.querySelectorAll for elements with:
        - onclick handler
        - cursor: pointer
        - role="button"
        """
        js_query = """
        () => {
            const elements = [];
            const clickable = document.querySelectorAll(
                'button, a[href], input[type="button"], input[type="submit"], ' +
                '[onclick], [role="button"], [role="link"], ' +
                '*[style*="cursor: pointer"]'
            );
            
            clickable.forEach((el, index) => {
                const rect = el.getBoundingClientRect();
                elements.push({
                    tag: el.tagName.toLowerCase(),
                    text: el.textContent?.trim() || '',
                    id: el.id || '',
                    className: el.className || '',
                    bbox: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    }
                });
            });
            
            return elements;
        }
        """

        try:
            result = await page.evaluate(js_query)
            
            elements = []
            for item in result:
                bbox = BoundingBox(
                    x=item['bbox']['x'] / viewport_width,
                    y=item['bbox']['y'] / viewport_height,
                    width=item['bbox']['width'] / viewport_width,
                    height=item['bbox']['height'] / viewport_height
                )

                # Generate CSS selector from ID or class
                if item['id']:
                    css_selector = f"#{item['id']}"
                elif item['className']:
                    classes = item['className'].split()[0] if item['className'] else ''
                    css_selector = f"{item['tag']}.{classes}" if classes else item['tag']
                else:
                    css_selector = item['tag']

                element = DOMElement(
                    xpath=f"//{item['tag']}",  # Simplified XPath
                    css_selector=css_selector,
                    tag_name=item['tag'],
                    text_content=item['text'],
                    attributes={'id': item['id'], 'class': item['className']},
                    bounding_box=bbox
                )
                elements.append(element)

            return elements

        except Exception as e:
            return []
