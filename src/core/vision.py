"""
Vision Client for AI Plays Pokémon

Uses OpenRouter API with Gemma 3 12B (google/gemma-3-12b-it) to analyze
Game Boy / GBA screenshots and return structured JSON about game state.
"""

import os
import io
import json
import base64
import hashlib
import re
from typing import Optional, cast, Any

import numpy as np
from PIL import Image

from src.core.ai_client import OpenRouterClient


class VisionClient:
    """Analyzes Pokémon game screenshots using a vision-language model.

    Converts numpy screenshots to base64 PNG, sends them to OpenRouter
    with a surgical prompt, and parses structured JSON responses.
    """

    VISION_PROMPT = (
        "You are a precise game screen analyzer. Examine this Pokémon game "
        "screenshot and return ONLY a JSON object. Do not describe, narrate, "
        "or explain.\n\n"
        "Return exactly this JSON structure:\n"
        "{\n"
        '  "screen_type": "battle|overworld|dialog|name_entry|name_confirm|menu|title|unknown",\n'
        '  "screen_subtype": "start_menu|item_menu|battle_menu|yes_no|keyboard|rival_battle|or null",\n'
        '  "enemy_pokemon": "Pokemon name or null",\n'
        '  "player_hp_pct": 0-100,\n'
        '  "enemy_hp_pct": 0-100,\n'
        '  "text_lines": ["exact text line 1", "line 2", ...],\n'
        '  "menu_items": ["item1", "item2", ...],\n'
        '  "adjacent_tiles": {"up": "wall|stairs|path|grass|npc|door|empty",\n'
        '                     "down": "...", "left": "...", "right": "..."},\n'
        '  "name_field": "text in name entry field or null",\n'
        '  "status_icons": ["par","slp","psn","brn","frz"],\n'
        '  "dialog_prompt": "yes/no question or null"\n'
        "}\n\n"
        "CRITICAL RULES:\n"
        '- screen_type: "battle" if HP bars visible. '
        '"overworld" if walking around (no text boxes). '
        '"name_entry" if a letter grid/keyboard is visible with "YOUR NAME?" '
        "or \"RIVAL'S NAME?\" at top. "
        '"name_confirm" if text says "Right! So your name is..."'
        '"dialog" if text box visible but NO letter grid and NO HP bars. '
        '"menu" if a list menu (POKéDEX, ITEM, SAVE etc) is open. '
        '"title" if title screen.\n'
        "- screen_subtype: for menus, specify which kind. "
        'For name_entry, always "keyboard". '
        'For battles against the rival (Gary/Blue), set to "rival_battle" '
        "— look for the rival's unique sprite (spiky hair) and no wild "
        "encounter animation/flash.\n"
        "- adjacent_tiles: for overworld ONLY. Describe what is ONE TILE in "
        "each direction from the player. Use: wall, stairs, path, grass, "
        "npc, door, empty, bed, table, pc, plant.\n"
        "- name_field: for name_entry/name_confirm screens, copy the name "
        "text from the entry field.\n"
        "- text_lines: copy text verbatim from any visible text boxes.\n"
        "- menu_items: list visible menu options in order.\n"
        "- dialog_prompt: if there's a yes/no choice, what's the question?\n\n"
        "DO NOT write anything except the JSON object. No markdown fences, "
        "no explanation."
    )

    _FALLBACK_RESULT: dict[str, Any] = {"screen_type": "unknown"}

    def __init__(self, model: str = "google/gemma-3-12b-it") -> None:
        """Initialise the vision client.

        Args:
            model: OpenRouter model ID for vision analysis.

        Raises:
            ValueError: If ``OPENROUTER_API_KEY`` is not set in the environment.
        """
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable is not set. "
                "Create a .env file or export the variable.\n"
                "  echo 'OPENROUTER_API_KEY=sk-or-v1-...' > .env"
            )

        self.model = model
        self._client = OpenRouterClient(api_key=api_key)

        # Cache: avoid re-calling vision for unchanged screenshots.
        self._last_hash: Optional[str] = None
        self._last_result: Optional[dict[str, Any]] = None

    # ── public API ──────────────────────────────────────────────────────────

    def analyze(self, screenshot: np.ndarray, game: str = "gen1") -> dict[str, Any]:
        """Analyze a game screenshot and return structured game state.

        Args:
            screenshot: RGB numpy array (height, width, 3), uint8.
            game: Game generation hint (``"gen1"``, ``"gen2"``, ``"gen3"``).

        Returns:
            Dictionary with screen_type, enemy_pokemon, hp values,
            text_lines, menu_items, and other fields.
            Falls back to ``{"screen_type": "unknown"}`` on persistent failure.
        """
        # ── cache check ─────────────────────────────────────────────────
        current_hash = self._compute_hash(screenshot)
        if current_hash == self._last_hash and self._last_result is not None:
            return self._last_result

        # ── encode screenshot as base64 PNG ──────────────────────────────
        image_b64 = self._encode_image(screenshot)

        # ── call vision model with retries ───────────────────────────────
        for attempt in range(3):  # up to 2 retries (3 total attempts)
            temperature = 0.1 + (attempt * 0.15)  # vary temperature on retry

            try:
                response_text = self._client.send_vision_request(
                    prompt=self.VISION_PROMPT,
                    image_b64=image_b64,
                    model=self.model,
                    max_tokens=300,
                    temperature=temperature,
                )

                result = self._parse_response(response_text)
                if result is not None:
                    self._last_hash = current_hash
                    self._last_result = result
                    return result

            except Exception:
                if attempt >= 2:
                    break

        # ── fallback ─────────────────────────────────────────────────────
        return dict(self._FALLBACK_RESULT)

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_hash(screenshot: np.ndarray) -> str:
        """MD5 hash of the first 1 KB of pixel data."""
        head = screenshot.tobytes()[:1024]
        return hashlib.md5(head).hexdigest()

    @staticmethod
    def _encode_image(screenshot: np.ndarray) -> str:
        """Convert a numpy RGB array to a base64-encoded PNG string.

        Resizes images wider than 1024 px (unlikely for GB/GBA).
        """
        pil_img = Image.fromarray(screenshot)

        if pil_img.size[0] > 1024:
            ratio = 1024 / pil_img.size[0]
            new_h = int(pil_img.size[1] * ratio)
            pil_img = pil_img.resize((1024, new_h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    @classmethod
    def _parse_response(cls, text: str) -> Optional[dict[str, Any]]:
        """Extract and parse a JSON object from the model response.

        Returns:
            Parsed dict, or *None* if parsing fails.
        """
        if not text or not text.strip():
            return None

        cleaned = cls._clean_json_text(text)

        # Direct parse.
        try:
            return cast(dict[str, Any], json.loads(cleaned))
        except json.JSONDecodeError:
            pass

        # Try to find a JSON object with regex (handles nested braces).
        # Strategy: find the outermost { ... }.
        for pattern in (
            r"\{(?:[^{}]|\{[^{}]*\})*\}",
            r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}",  # slightly deeper nesting
        ):
            match = re.search(pattern, cleaned, re.DOTALL)
            if match:
                try:
                    return cast(dict[str, Any], json.loads(match.group()))
                except json.JSONDecodeError:
                    continue

        # Last resort: extract individual fields with field-level regex.
        return cls._regex_extract(text)

    @staticmethod
    def _clean_json_text(text: str) -> str:
        """Strip markdown fences and surrounding whitespace."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")].strip()
        return cleaned

    @staticmethod
    def _regex_extract(text: str) -> Optional[dict[str, Any]]:
        """Fallback: extract known fields from unstructured text via regex."""
        field_patterns = {
            "screen_type": r'"screen_type"\s*:\s*"(\w+)"',
            "enemy_pokemon": r'"enemy_pokemon"\s*:\s*"([^"]+)"',
            "player_hp_pct": r'"player_hp_pct"\s*:\s*(\d+)',
            "enemy_hp_pct": r'"enemy_hp_pct"\s*:\s*(\d+)',
            "dialog_prompt": r'"dialog_prompt"\s*:\s*"([^"]+)"',
            "adjacent_info": r'"adjacent_info"\s*:\s*"([^"]+)"',
        }

        result: dict[str, Any] = {}
        for field, pattern in field_patterns.items():
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                val = m.group(1)
                if field in ("player_hp_pct", "enemy_hp_pct"):
                    try:
                        val = int(val)
                    except ValueError:
                        continue
                result[field] = val

        # Try to get text_lines and menu_items as arrays.
        for arr_field, arr_pattern in (
            ("text_lines", r'"text_lines"\s*:\s*\[(.*?)\]'),
            ("menu_items", r'"menu_items"\s*:\s*\[(.*?)\]'),
            ("status_icons", r'"status_icons"\s*:\s*\[(.*?)\]'),
        ):
            m = re.search(arr_pattern, text, re.DOTALL)
            if m:
                items_str = m.group(1)
                items = re.findall(r'"([^"]*)"', items_str)
                result[arr_field] = items

        return result if result else None
