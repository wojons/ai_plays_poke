"""
Shared prompt loader for ai_plays_poke.

Loads core.yaml + hint layers based on HINT_LEVEL.
Core is always loaded. Hints stack: level 1 = mechanics, 2 = genre,
3 = starter, 4 = navigation.

Usage:
    from src.core.prompt_loader import load_system_prompt
    system_prompt = load_system_prompt(hint_level=0)
"""

from pathlib import Path
from typing import Any

import yaml


_PROMPTS_DIR = Path(__file__).parent.parent.parent / "configs" / "prompts" / "gen1"
_HINTS_DIR = _PROMPTS_DIR / "hints"

_HINT_FILES = [
    "01_mechanics.yaml",
    "02_genre.yaml",
    "03_starter.yaml",
    "04_navigation.yaml",
]

# Cache: loaded prompts keyed by hint_level
_cache: dict[int, str] = {}


def _load_yaml_system(path: Path) -> str:
    """Load the 'system' or 'system_extra' key from a YAML file."""
    data = yaml.safe_load(path.read_text())
    if isinstance(data, dict):
        # Check both key names for compatibility
        return str(data.get("system", data.get("system_extra", "")))
    return ""


def load_system_prompt(hint_level: int = 0) -> str:
    """Load the composed system prompt for a given hint level.

    Args:
        hint_level: 0 = benchmark (core only), 1-4 = core + hint layers

    Returns:
        Full system prompt string (core + applicable hints).
    """
    if hint_level in _cache:
        return _cache[hint_level]

    parts: list[str] = []

    # Core is always loaded
    core_path = _PROMPTS_DIR / "core.yaml"
    if core_path.exists():
        parts.append(_load_yaml_system(core_path))

    # Stack hint layers
    for i in range(min(hint_level, len(_HINT_FILES))):
        hint_path = _HINTS_DIR / _HINT_FILES[i]
        if hint_path.exists():
            extra = _load_yaml_system(hint_path)
            if extra:
                parts.append(extra)

    result = "\n\n".join(parts)
    _cache[hint_level] = result
    return result


def get_text_content(vis_dict: dict[str, Any]) -> list[str]:
    """Extract text_content from a vision dict.

    Handles both cartographer output (text_content field) and
    legacy vision output (text_lines field).
    """
    tc = vis_dict.get("text_content", [])
    if tc and isinstance(tc, list):
        return tc
    # Fallback to text_lines
    tl = vis_dict.get("text_lines", [])
    if tl and isinstance(tl, list):
        return tl
    return []
