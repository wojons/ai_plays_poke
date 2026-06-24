"""
Unit tests for VisionClient — encode, parse, clean, and regex extraction paths.
"""
from __future__ import annotations

import json
import base64
import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from src.core.vision import VisionClient


# ── helpers ────────────────────────────────────────────────────────────────

def _make_rgb_array(h: int = 160, w: int = 240) -> np.ndarray:
    """Create a dummy RGB screenshot array."""
    return np.zeros((h, w, 3), dtype=np.uint8)


# ── EncodeImage tests ──────────────────────────────────────────────────────

class TestEncodeImage:
    """_encode_image converts numpy → base64 PNG."""

    def test_encode_returns_string(self) -> None:
        img = _make_rgb_array()
        result = VisionClient._encode_image(img)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_is_valid_base64(self) -> None:
        img = _make_rgb_array()
        result = VisionClient._encode_image(img)
        # Should decode back to bytes
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_encode_produces_png(self) -> None:
        img = _make_rgb_array()
        result = VisionClient._encode_image(img)
        decoded = base64.b64decode(result)
        # PNG magic bytes
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"

    def test_encode_small_image_stays_same_size(self) -> None:
        """Small images (e.g. 160×240) pass through without resize."""
        img = _make_rgb_array(144, 160)
        result = VisionClient._encode_image(img)
        # Verify the decoded PNG has the right dimensions
        decoded = base64.b64decode(result)
        pil = Image.open(io.BytesIO(decoded))
        assert pil.size == (160, 144)

    def test_encode_different_shapes(self) -> None:
        """GB 144×160 and GBA 160×240 both work."""
        for h, w in ((144, 160), (160, 240)):
            img = _make_rgb_array(h, w)
            result = VisionClient._encode_image(img)
            assert len(result) > 0

    def test_encode_nonzero_pixels(self) -> None:
        """Image with actual pixel data encodes correctly."""
        img = np.random.randint(0, 255, (144, 160, 3), dtype=np.uint8)
        result = VisionClient._encode_image(img)
        assert len(result) > 0


# ── CleanJsonText tests ────────────────────────────────────────────────────

class TestCleanJsonText:
    """_clean_json_text strips markdown fences."""

    def test_plain_json_unchanged(self) -> None:
        text = '{"screen_type": "overworld"}'
        assert VisionClient._clean_json_text(text) == text

    def test_json_fence_stripped(self) -> None:
        text = '```json\n{"screen_type": "battle"}\n```'
        result = VisionClient._clean_json_text(text)
        assert result == '{"screen_type": "battle"}'

    def test_plain_fence_stripped(self) -> None:
        text = '```\n{"screen_type": "menu"}\n```'
        result = VisionClient._clean_json_text(text)
        assert result == '{"screen_type": "menu"}'

    def test_trailing_whitespace_stripped(self) -> None:
        text = '  {"key": "val"}  \n'
        result = VisionClient._clean_json_text(text)
        assert result == '{"key": "val"}'

    def test_multiline_json(self) -> None:
        text = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = VisionClient._clean_json_text(text)
        assert "```" not in result
        assert '"a": 1' in result


# ── ParseResponse tests ────────────────────────────────────────────────────

class TestParseResponse:
    """_parse_response extracts JSON from model output."""

    def test_parse_empty_none(self) -> None:
        assert VisionClient._parse_response("") is None

    def test_parse_whitespace_none(self) -> None:
        assert VisionClient._parse_response("   \n  ") is None

    def test_parse_valid_json(self) -> None:
        result = VisionClient._parse_response('{"screen_type": "overworld", "confidence": 0.9}')
        assert result is not None
        assert result["screen_type"] == "overworld"

    def test_parse_json_in_fence(self) -> None:
        result = VisionClient._parse_response('```json\n{"screen_type": "battle"}\n```')
        assert result is not None
        assert result["screen_type"] == "battle"

    def test_parse_nested_braces(self) -> None:
        text = '{"screen_type": "overworld", "adjacent_tiles": {"up": "path", "down": "grass"}}'
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["adjacent_tiles"]["up"] == "path"

    def test_parse_partial_json_uses_regex(self) -> None:
        """When full JSON parse fails, regex extraction gets individual fields."""
        text = 'Something about "screen_type": "dialog" and "text_lines": ["Hello!"]'
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result.get("screen_type") == "dialog"

    def test_parse_invalid_returns_none(self) -> None:
        """Totally unparseable text returns None."""
        result = VisionClient._parse_response("Just some random text without JSON")
        assert result is None


# ── RegexExtract tests ─────────────────────────────────────────────────────

class TestRegexExtract:
    """_regex_extract pulls fields from unstructured text."""

    def test_extract_screen_type(self) -> None:
        text = 'The screen shows "screen_type": "overworld" and more text'
        result = VisionClient._regex_extract(text)
        assert result is not None
        assert result["screen_type"] == "overworld"

    def test_extract_enemy_pokemon(self) -> None:
        text = '["enemy_pokemon": "Pidgey", "player_hp_pct": 85]'
        result = VisionClient._regex_extract(text)
        assert result is not None
        assert result["enemy_pokemon"] == "Pidgey"

    def test_extract_hp_values_as_int(self) -> None:
        text = '"player_hp_pct": 42, "enemy_hp_pct": 99'
        result = VisionClient._regex_extract(text)
        assert result is not None
        assert result["player_hp_pct"] == 42
        assert result["enemy_hp_pct"] == 99

    def test_extract_text_lines_array(self) -> None:
        text = '"text_lines": ["Hi!", "Welcome to Pallet Town", "Good luck!"]'
        result = VisionClient._regex_extract(text)
        assert result is not None
        assert "text_lines" in result
        assert result["text_lines"] == ["Hi!", "Welcome to Pallet Town", "Good luck!"]

    def test_extract_menu_items_array(self) -> None:
        text = '"menu_items": ["POKéDEX", "POKéMON", "ITEM", "SAVE"]'
        result = VisionClient._regex_extract(text)
        assert result is not None
        assert "menu_items" in result
        assert "POKéDEX" in result["menu_items"]

    def test_extract_status_icons(self) -> None:
        text = '"status_icons": ["par", "slp"]'
        result = VisionClient._regex_extract(text)
        assert result is not None
        assert result.get("status_icons") == ["par", "slp"]

    def test_extract_empty_array(self) -> None:
        text = '"text_lines": []'
        result = VisionClient._regex_extract(text)
        if result is not None:
            assert result.get("text_lines") == []

    def test_extract_no_fields_returns_none(self) -> None:
        text = "No recognizable fields in this text at all."
        result = VisionClient._regex_extract(text)
        assert result is None


# ── ComputeHash tests ──────────────────────────────────────────────────────

class TestComputeHash:
    """_compute_hash returns consistent MD5 for identical images."""

    def test_same_image_same_hash(self) -> None:
        img = _make_rgb_array()
        h1 = VisionClient._compute_hash(img)
        h2 = VisionClient._compute_hash(img)
        assert h1 == h2

    def test_different_image_different_hash(self) -> None:
        img1 = np.zeros((160, 240, 3), dtype=np.uint8)
        img2 = np.ones((160, 240, 3), dtype=np.uint8) * 255
        h1 = VisionClient._compute_hash(img1)
        h2 = VisionClient._compute_hash(img2)
        assert h1 != h2

    def test_hash_is_hex_string(self) -> None:
        img = _make_rgb_array()
        h = VisionClient._compute_hash(img)
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)
