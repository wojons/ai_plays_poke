"""
Vision Pipeline Headless Tests — NO API KEY REQUIRED.

Tests for VisionClient parsing/encoding, OCR extraction, and
PromptStack assembly without calling OpenRouter or loading a ROM.

AC-006: VisionClient parsing returns valid classification for known screen types
AC-007: OCR extracts recognizable text from frame buffer regions (encoding + extraction)
AC-008: PromptStack assembles correctly from vision output
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest
from PIL import Image

from src.core.prompt_assembler import (
    PromptStack,
    SafeDict,
    _build_enemy_info,
    _build_hp_info,
    _join_list,
)
from src.core.vision import VisionClient


# ── helpers ────────────────────────────────────────────────────────────────

_PROJECT = Path(__file__).resolve().parent.parent


def _make_rgb_array(height: int = 144, width: int = 160) -> np.ndarray:
    """Return a deterministic RGB array (not a real game frame)."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    rows = np.arange(height * width, dtype=np.uint32)
    img[:, :, 0] = (rows % 255).reshape(height, width)
    img[:, :, 1] = ((rows * 3) % 255).reshape(height, width)
    img[:, :, 2] = ((rows * 7) % 255).reshape(height, width)
    return img


def _make_blank_rgb(height: int = 144, width: int = 160) -> np.ndarray:
    """Return a flat-colour RGB array."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = [64, 128, 192]
    return img


# ════════════════════════════════════════════════════════════════════════════
# AC-006: VisionClient.parse_response returns valid ScreenClassification
#         for known screen types
# ════════════════════════════════════════════════════════════════════════════


class TestVisionClientParsing:
    """Test _parse_response, _clean_json_text, _regex_extract."""

    # ── clean JSON - direct parse ───────────────────────────────────────

    def test_parse_clean_battle_json(self):  # type: ignore
        text = json.dumps({
            "screen_type": "battle",
            "enemy_pokemon": "Pidgey",
            "player_hp_pct": 85,
            "enemy_hp_pct": 40,
            "text_lines": ["What will", "PIKACHU do?"],
            "menu_items": ["FIGHT", "BAG", "POKéMON", "RUN"],
            "adjacent_info": "grass all around",
            "status_icons": [],
            "dialog_prompt": None,
        })
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["screen_type"] == "battle"
        assert result["enemy_pokemon"] == "Pidgey"
        assert result["player_hp_pct"] == 85
        assert result["enemy_hp_pct"] == 40
        assert result["menu_items"] == ["FIGHT", "BAG", "POKéMON", "RUN"]

    def test_parse_clean_overworld_json(self):  # type: ignore
        text = json.dumps({
            "screen_type": "overworld",
            "enemy_pokemon": None,
            "player_hp_pct": 0,
            "enemy_hp_pct": 0,
            "text_lines": [],
            "menu_items": [],
            "adjacent_info": "path leading north, grass to the east",
            "status_icons": [],
            "dialog_prompt": None,
        })
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["screen_type"] == "overworld"
        assert result["enemy_pokemon"] is None

    def test_parse_menu_json(self):  # type: ignore
        text = json.dumps({
            "screen_type": "menu",
            "enemy_pokemon": None,
            "player_hp_pct": 0,
            "enemy_hp_pct": 0,
            "text_lines": [],
            "menu_items": ["POKéDEX", "POKéMON", "BAG", "TRAINER", "SAVE", "OPTIONS"],
            "adjacent_info": "",
            "status_icons": [],
            "dialog_prompt": None,
        })
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["screen_type"] == "menu"
        assert len(result["menu_items"]) == 6

    def test_parse_dialog_json(self):  # type: ignore
        text = json.dumps({
            "screen_type": "dialog",
            "enemy_pokemon": None,
            "player_hp_pct": 0,
            "enemy_hp_pct": 0,
            "text_lines": ["Welcome to the world", "of Pokémon!"],
            "menu_items": [],
            "adjacent_info": "",
            "status_icons": [],
            "dialog_prompt": None,
        })
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["screen_type"] == "dialog"
        assert len(result["text_lines"]) == 2

    def test_parse_title_json(self):  # type: ignore
        text = json.dumps({
            "screen_type": "title",
            "enemy_pokemon": None,
            "player_hp_pct": 0,
            "enemy_hp_pct": 0,
            "text_lines": ["POKéMON FIRE RED"],
            "menu_items": ["NEW GAME", "CONTINUE"],
            "adjacent_info": "",
            "status_icons": [],
            "dialog_prompt": None,
        })
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["screen_type"] == "title"

    # ── markdown fence removal ──────────────────────────────────────────

    def test_clean_json_strips_markdown_fences(self):  # type: ignore
        text = '```json\n{"screen_type": "battle"}\n```'
        cleaned = VisionClient._clean_json_text(text)
        assert cleaned == '{"screen_type": "battle"}'

    def test_clean_json_strips_bare_fences(self):  # type: ignore
        text = '```\n{"screen_type": "overworld"}\n```'
        cleaned = VisionClient._clean_json_text(text)
        assert cleaned == '{"screen_type": "overworld"}'

    def test_clean_json_no_fences(self):  # type: ignore
        text = '{"screen_type": "menu"}'
        cleaned = VisionClient._clean_json_text(text)
        assert cleaned == text

    def test_parse_fenced_json(self):  # type: ignore
        text = '```json\n{"screen_type": "dialog", "text_lines": ["Hello!"]}\n```'
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["screen_type"] == "dialog"
        assert result["text_lines"] == ["Hello!"]

    def test_parse_json_with_surrounding_text(self):  # type: ignore
        text = (
            "Here is the analysis:\n\n"
            '{"screen_type": "battle", "enemy_pokemon": "Rattata"}\n\n'
            "End of response."
        )
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["screen_type"] == "battle"
        assert result["enemy_pokemon"] == "Rattata"

    def test_parse_json_with_nested_braces(self):  # type: ignore
        text = json.dumps({
            "screen_type": "battle",
            "enemy_pokemon": "Charmander",
            "player_hp_pct": 67,
            "enemy_hp_pct": 22,
            "text_lines": ["PIKACHU used", "THUNDERBOLT!"],
            "menu_items": ["FIGHT", "BAG", "POKéMON", "RUN"],
            "adjacent_info": "grass",
            "status_icons": ["par"],
            "dialog_prompt": None,
        })
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["status_icons"] == ["par"]
        assert result["player_hp_pct"] == 67

    # ── regex fallback ──────────────────────────────────────────────────

    def test_regex_extract_screen_type(self):  # type: ignore
        text = 'some garbled text "screen_type": "overworld" more junk'
        result = VisionClient._regex_extract(text)
        assert result is not None
        assert result.get("screen_type") == "overworld"

    def test_regex_extract_hp_values(self):  # type: ignore
        text = '{"screen_type": "battle", "player_hp_pct": 42, "enemy_hp_pct": 88}'
        # This parses cleanly, but also verify regex fallback works
        # by breaking the JSON just enough
        broken = '"screen_type": "battle",\n"player_hp_pct": 42,\n"enemy_hp_pct": 88'
        result = VisionClient._regex_extract(broken)
        assert result is not None
        assert result["player_hp_pct"] == 42
        assert result["enemy_hp_pct"] == 88

    def test_regex_extract_text_lines(self):  # type: ignore
        text = '"text_lines": ["Welcome!", "Press A to continue"]'
        result = VisionClient._regex_extract(text)
        assert result is not None
        assert "text_lines" in result
        assert result["text_lines"] == ["Welcome!", "Press A to continue"]

    def test_regex_extract_empty(self):  # type: ignore
        text = "Just some words, no JSON at all really."
        result = VisionClient._regex_extract(text)
        assert result is None

    # ── null / empty input ──────────────────────────────────────────────

    def test_parse_empty_string(self):  # type: ignore
        result = VisionClient._parse_response("")
        assert result is None

    def test_parse_whitespace_only(self):  # type: ignore
        result = VisionClient._parse_response("   \n  ")
        assert result is None

    def test_parse_none(self):  # type: ignore
        # parse_response should handle None gracefully
        result = VisionClient._parse_response(None)  # type: ignore
        assert result is None


# ════════════════════════════════════════════════════════════════════════════
# AC-007: OCR extracts recognizable text from frame buffer regions
# ════════════════════════════════════════════════════════════════════════════


class TestVisionClientEncoding:
    """Test _encode_image, _compute_hash — the data pipeline before the API call."""

    def test_encode_image_produces_valid_png_base64(self):  # type: ignore
        img = _make_rgb_array(144, 160)
        b64 = VisionClient._encode_image(img)
        # Decode back and verify
        decoded = base64.b64decode(b64)
        buf = io.BytesIO(decoded)
        pil_img = Image.open(buf)
        assert pil_img.format == "PNG"
        assert pil_img.size == (160, 144)

    def test_encode_blank_image(self):  # type: ignore
        img = _make_blank_rgb(144, 160)
        b64 = VisionClient._encode_image(img)
        decoded = base64.b64decode(b64)
        buf = io.BytesIO(decoded)
        pil_img = Image.open(buf)
        np_img = np.array(pil_img.convert("RGB"))
        assert np_img.shape == (144, 160, 3)
        # Verify all pixels match (minus compression artefacts — PNG is lossless)
        assert np.array_equal(np_img, img)

    def test_encode_wide_image_resizes(self):  # type: ignore
        """Images wider than 1024 px should be resized."""
        img = _make_rgb_array(200, 1200)
        b64 = VisionClient._encode_image(img)
        decoded = base64.b64decode(b64)
        buf = io.BytesIO(decoded)
        pil_img = Image.open(buf)
        assert pil_img.size[0] == 1024
        assert pil_img.size[1] < 200

    def test_compute_hash_same_image(self):  # type: ignore
        img = _make_rgb_array()
        h1 = VisionClient._compute_hash(img)
        h2 = VisionClient._compute_hash(img)
        assert h1 == h2

    def test_compute_hash_different_images(self):  # type: ignore
        img1 = _make_rgb_array()
        img2 = _make_blank_rgb()
        h1 = VisionClient._compute_hash(img1)
        h2 = VisionClient._compute_hash(img2)
        assert h1 != h2

    def test_compute_hash_is_hex_string(self):  # type: ignore
        img = _make_rgb_array()
        h = VisionClient._compute_hash(img)
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    # ── text extraction from parsed responses (OCR equivalent) ──────────

    def test_text_extraction_from_battle_response(self):  # type: ignore
        text = json.dumps({
            "screen_type": "battle",
            "enemy_pokemon": "Geodude",
            "player_hp_pct": 55,
            "enemy_hp_pct": 30,
            "text_lines": ["Go! PIKACHU!", "PIKACHU used", "THUNDER SHOCK!"],
            "menu_items": ["FIGHT", "BAG", "POKéMON", "RUN"],
            "adjacent_info": "cave",
            "status_icons": [],
            "dialog_prompt": None,
        })
        result = VisionClient._parse_response(text)
        assert result is not None
        assert len(result["text_lines"]) == 3
        assert "PIKACHU used" in result["text_lines"]
        assert result["menu_items"][0] == "FIGHT"

    def test_text_extraction_from_dialog_with_yes_no(self):  # type: ignore
        text = json.dumps({
            "screen_type": "dialog",
            "enemy_pokemon": None,
            "player_hp_pct": 0,
            "enemy_hp_pct": 0,
            "text_lines": ["Would you like to", "save the game?"],
            "menu_items": ["YES", "NO"],
            "adjacent_info": "",
            "status_icons": [],
            "dialog_prompt": "Would you like to save the game?",
        })
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["dialog_prompt"] == "Would you like to save the game?"
        assert result["menu_items"] == ["YES", "NO"]

    def test_text_extraction_special_chars(self):  # type: ignore
        """Verify that PokéMon-specific characters survive parsing."""
        text = json.dumps({
            "screen_type": "menu",
            "enemy_pokemon": "Farfetch'd",
            "player_hp_pct": 0,
            "enemy_hp_pct": 0,
            "text_lines": [],
            "menu_items": ["POKéDEX", "POKéMON", "BAG", "PIKACHU♂", "SAVE"],
            "adjacent_info": "",
            "status_icons": [],
            "dialog_prompt": None,
        })
        result = VisionClient._parse_response(text)
        assert result is not None
        assert "POKéDEX" in result["menu_items"]
        assert "PIKACHU♂" in result["menu_items"]

    def test_text_extraction_all_caps(self):  # type: ignore
        """Game text is ALL CAPS — verify preservation."""
        text = json.dumps({
            "screen_type": "battle",
            "enemy_pokemon": "SQUIRTLE",
            "player_hp_pct": 100,
            "enemy_hp_pct": 100,
            "text_lines": ["A wild SQUIRTLE", "appeared!"],
            "menu_items": ["FIGHT", "BAG", "POKéMON", "RUN"],
            "adjacent_info": "route 1",
            "status_icons": [],
            "dialog_prompt": None,
        })
        result = VisionClient._parse_response(text)
        assert result is not None
        assert result["enemy_pokemon"] == "SQUIRTLE"
        assert "A wild SQUIRTLE" in result["text_lines"]


# ════════════════════════════════════════════════════════════════════════════
# AC-008: PromptStack assembles correctly from vision output
# ════════════════════════════════════════════════════════════════════════════


class TestPromptStackCore:
    """Test PromptStack loading, assembly, and introspection."""

    @pytest.fixture
    def stack(self):  # type: ignore
        return PromptStack(str(_PROJECT / "configs" / "prompts"))

    # ── loading ─────────────────────────────────────────────────────────

    def test_load_valid_stack(self, stack):  # type: ignore
        layers = stack.load_stack("gen3", "battle")
        assert "system" in layers
        assert "tools" in layers
        assert "observation" in layers
        assert "memory" in layers
        assert "examples" in layers

    def test_load_overworld_stack(self, stack):  # type: ignore
        layers = stack.load_stack("gen3", "overworld")
        assert "system" in layers
        assert "You are an AI" in layers["system"]

    def test_load_gen1_stack(self, stack):  # type: ignore
        layers = stack.load_stack("gen1", "battle")
        assert "system" in layers
        assert "Generation:" in layers["system"] or "Gen 1" in layers["system"].lower()

    def test_load_missing_stack(self, stack):  # type: ignore
        with pytest.raises(FileNotFoundError):
            stack.load_stack("gen3", "nonexistent_screen")

    # ── assembly ────────────────────────────────────────────────────────

    def test_assemble_battle_prompt(self, stack):  # type: ignore
        vision = {
            "screen_type": "battle",
            "enemy_pokemon": "Pidgey",
            "player_hp_pct": 85,
            "enemy_hp_pct": 100,
            "text_lines": ["What will", "CHARMANDER do?"],
            "menu_items": ["FIGHT", "BAG", "POKéMON", "RUN"],
        }
        memory: Dict[str, Any] = {
            "recent_actions": ["move up", "move up"],
            "party_status": "CHARMANDER Lv5 HP 20/20",
            "active_goal": "reach Viridian City",
        }
        prompt = stack.assemble("gen3", "battle", vision, memory)
        assert "FireRed" in prompt
        assert "Pidgey" in prompt
        assert "CHARMANDER" in prompt
        assert "85%" in prompt
        assert "100%" in prompt
        assert "FIGHT" in prompt

    def test_assemble_overworld_prompt(self, stack):  # type: ignore
        vision = {  # type: ignore
            "screen_type": "overworld",
            "enemy_pokemon": None,
            "player_hp_pct": 0,
            "enemy_hp_pct": 0,
            "text_lines": [],
            "menu_items": [],
            "adjacent_info": "path north, tall grass east",
        }
        memory: Dict[str, Any] = {
            "recent_actions": ["press a", "wait 30"],
            "party_status": "SQUIRTLE Lv7 HP 25/25",
            "active_goal": "find Professor Oak",
        }
        prompt = stack.assemble("gen3", "overworld", vision, memory)
        assert "FireRed" in prompt
        assert "overworld" in prompt.lower()
        assert "SQUIRTLE" in prompt
        assert "Professor Oak" in prompt

    def test_assemble_with_menu_options_fallback(self):  # type: ignore
        """PromptStack should use menu_options as fallback for menu_items."""
        stack = PromptStack(str(_PROJECT / "configs" / "prompts"))
        vision: Dict[str, Any] = {
            "screen_type": "menu",
            "menu_options": ["POKéDEX", "POKéMON", "BAG"],
        }
        memory: Dict[str, Any] = {
            "recent_actions": [],
            "party_status": "",
            "active_goal": "",
        }
        prompt = stack.assemble("gen3", "menu", vision, memory)
        assert "POKéDEX" in prompt
        assert "POKéMON" in prompt

    def test_assemble_with_minimal_input(self):  # type: ignore
        """SafeDict should handle missing keys gracefully without crashing."""
        stack = PromptStack(str(_PROJECT / "configs" / "prompts"))
        vision: Dict[str, Any] = {"screen_type": "battle"}
        memory: Dict[str, Any] = {
            "recent_actions": [],
            "party_status": "",
            "active_goal": "",
        }
        prompt = stack.assemble("gen3", "battle", vision, memory)
        # Assembly should succeed without crashing — basic structure present
        assert "battle" in prompt.lower()
        assert "FireRed" in prompt
        # Enemy info is empty but that's fine — the template variable resolved to ""
        # Missing keys from fmt dict would show as {missing_key} via SafeDict

    def test_assemble_memory_context(self, stack):  # type: ignore
        vision: Dict[str, Any] = {"screen_type": "overworld"}
        memory: Dict[str, Any] = {
            "recent_actions": ["move north", "press a", "battle Pidgey"],
            "party_status": "PIKACHU Lv12 HP 40/40, BULBASAUR Lv10 HP 35/35",
            "active_goal": "defeat Brock at Pewter Gym",
        }
        prompt = stack.assemble("gen3", "overworld", vision, memory)
        assert "move north" in prompt
        assert "press a" in prompt
        assert "PIKACHU" in prompt
        assert "BULBASAUR" in prompt
        assert "Brock" in prompt

    # ── available stacks ────────────────────────────────────────────────

    def test_available_stacks(self, stack):  # type: ignore
        stacks = stack.available_stacks()
        assert len(stacks) >= 2  # at least gen1 and gen3 have files
        assert "gen3/battle" in stacks
        assert "gen3/overworld" in stacks
        assert "gen1/battle" in stacks

    def test_available_stacks_with_missing_dir(self):  # type: ignore
        stack = PromptStack("/tmp/no_such_prompt_dir_xyz_9999")
        stacks = stack.available_stacks()
        assert stacks == []


class TestPromptStackHelpers:
    """Unit tests for PromptStack internal helpers."""

    def test_safe_dict_missing_key(self):  # type: ignore
        d = SafeDict()
        assert d["any_key"] == "{any_key}"

    def test_safe_dict_existing_key(self):  # type: ignore
        d = SafeDict({"hello": "world"})
        assert d["hello"] == "world"

    def test_join_list_none(self):  # type: ignore
        assert _join_list(None) == ""

    def test_join_list_empty_list(self):  # type: ignore
        assert _join_list([]) == ""

    def test_join_list_basic(self):  # type: ignore
        assert _join_list(["a", "b", "c"], sep=", ") == "a, b, c"

    def test_join_list_newline(self):  # type: ignore
        result = _join_list(["line1", "line2"], sep="\n  ")
        assert "line1" in result
        assert "line2" in result

    def test_join_list_string_passthrough(self):  # type: ignore
        assert _join_list("just a string") == "just a string"

    def test_build_hp_info_both_values(self):  # type: ignore
        vision = {"player_hp_pct": 75, "enemy_hp_pct": 30}
        hp = _build_hp_info(vision)
        assert "75%" in hp
        assert "30%" in hp

    def test_build_hp_info_player_only(self):  # type: ignore
        vision = {"player_hp_pct": 100}
        hp = _build_hp_info(vision)
        assert "100%" in hp
        assert "Enemy" not in hp

    def test_build_hp_info_none_values(self):  # type: ignore
        vision: Dict[str, Any] = {}
        hp = _build_hp_info(vision)
        assert hp == ""

    def test_build_hp_info_fallback_hp_info_key(self):  # type: ignore
        vision = {"hp_info": "PIKACHU hp: 20/35"}
        hp = _build_hp_info(vision)
        assert "PIKACHU" in hp

    def test_build_enemy_info_direct(self):  # type: ignore
        vision = {"enemy_pokemon": "Zubat"}
        info = _build_enemy_info(vision)
        assert info == "Enemy: Zubat"

    def test_build_enemy_info_fallback(self):  # type: ignore
        vision = {"enemy_info": "Wild ZUBAT appeared!"}
        info = _build_enemy_info(vision)
        assert info == "Wild ZUBAT appeared!"

    def test_build_enemy_info_none(self):  # type: ignore
        vision: Dict[str, Any] = {}
        info = _build_enemy_info(vision)
        assert info == ""


class TestPromptStackAssemblyEdgeCases:
    """Edge cases for assemble()."""

    @pytest.fixture
    def stack(self):  # type: ignore
        return PromptStack(str(_PROJECT / "configs" / "prompts"))

    def test_empty_vision_and_memory(self, stack):  # type: ignore
        """Should not crash with empty inputs."""
        prompt = stack.assemble("gen3", "battle", {}, {})
        assert "battle" in prompt.lower()
        assert "FireRed" in prompt

    def test_unknown_screen_type_still_formats(self, stack):  # type: ignore
        """If the screen type config exists, VisionClient dict keys are used."""
        prompt = stack.assemble("gen3", "battle", {"screen_type": "not_real_screen"}, {})
        assert "not_real_screen" in prompt.lower()

    def test_examples_layer_present(self, stack):  # type: ignore
        vision = {"screen_type": "battle"}
        memory: Dict[str, Any] = {
            "recent_actions": [],
            "party_status": "",
            "active_goal": "",
        }
        prompt = stack.assemble("gen3", "battle", vision, memory)
        assert "Example 1:" in prompt
        assert "Example 2:" in prompt
