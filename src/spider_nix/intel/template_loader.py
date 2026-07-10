"""
ATS Template Loader — reads YAML field templates from disk.

Auto-discovers templates in the templates/ directory and provides
a unified interface for the ConfidenceFieldMatcher.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Cache of loaded templates
_TEMPLATE_CACHE: dict[str, dict[str, Any]] = {}


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, trying multiple methods."""
    # Try PyYAML first
    try:
        import yaml

        with open(path) as f:
            return yaml.safe_load(f)
    except ImportError:
        pass

    # Fallback: simple YAML parser for our straightforward format
    return _parse_simple_yaml(path)


def _parse_simple_yaml(path: Path) -> dict[str, Any]:
    """
    Simple YAML parser for our template format.
    Handles: platform, url_patterns, flags, fields (nested lists).
    """
    with open(path) as f:
        text = f.read()

    result: dict[str, Any] = {"platform": "", "url_patterns": [], "flags": {}, "fields": {}}
    current_section: str | None = None
    current_field: str | None = None
    for line in text.split("\n"):
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level key: value
        if not line.startswith(" ") and ":" in stripped and not stripped.startswith("-"):
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")

            if key in ("platform",):
                result[key] = val
            elif key in ("url_patterns",):
                current_section = "url_patterns"
            elif key in ("flags",):
                current_section = "flags"
            elif key in ("fields",):
                current_section = "fields"
            elif current_section == "flags" and val:
                result["flags"][key] = _parse_bool(val)

        # List item: - value
        elif stripped.startswith("- "):
            val = stripped[2:].strip().strip('"').strip("'")
            if current_section == "url_patterns":
                result["url_patterns"].append(val)
            elif current_section == "fields" and current_field:
                result["fields"][current_field].append(val)

        # Field key under fields:
        elif current_section == "fields" and ":" in stripped and not stripped.startswith("-"):
            key = stripped.rstrip(":").strip()
            current_field = key
            result["fields"][key] = []

    return result


def _parse_bool(val: str) -> bool:
    """Parse a boolean value."""
    return val.lower() in ("true", "yes", "1", "on")


def get_template_dir() -> Path:
    """Get the path to the templates directory."""
    return Path(__file__).parent / "templates"


def load_template(platform: str) -> dict[str, Any] | None:
    """
    Load an ATS template by platform name.

    Returns None if no template found.
    """
    if platform in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[platform]

    template_dir = get_template_dir()
    yaml_path = template_dir / f"{platform}.yaml"

    if not yaml_path.exists():
        logger.debug(f"No template file for platform: {platform}")
        return None

    try:
        template = _load_yaml(yaml_path)
        _TEMPLATE_CACHE[platform] = template
        logger.info(f"Loaded template: {platform} ({len(template.get('fields', {}))} fields)")
        return template
    except Exception as e:
        logger.warning(f"Failed to load template {platform}: {e}")
        return None


def load_all_templates() -> dict[str, dict[str, Any]]:
    """Load all available ATS templates from disk."""
    templates: dict[str, dict[str, Any]] = {}
    template_dir = get_template_dir()

    if not template_dir.exists():
        return templates

    for yaml_file in template_dir.glob("*.yaml"):
        platform = yaml_file.stem
        template = load_template(platform)
        if template:
            templates[platform] = template

    return templates


def detect_platform_from_url(url: str) -> str | None:
    """
    Detect ATS platform from URL using loaded templates.

    Checks all loaded templates' url_patterns against the URL.
    """
    url_lower = url.lower()
    templates = load_all_templates()

    for platform, template in templates.items():
        for pattern in template.get("url_patterns", []):
            if pattern in url_lower:
                return platform

    return None


def reload_templates() -> None:
    """Clear the template cache (useful for development)."""
    _TEMPLATE_CACHE.clear()
