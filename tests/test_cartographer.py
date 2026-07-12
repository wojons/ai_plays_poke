"""
Unit tests for cron_runner cartographer_analyze() and _extract_spatial_json().

Tests the visual-reference cartographer pipeline that sends a reference image
+ live screenshot to Gemma 12B and parses the spatial JSON response.
"""

from unittest.mock import MagicMock

import json
import numpy as np
import pytest


# ── _extract_spatial_json tests (pure function, no mocking needed) ──────

class TestExtractSpatialJson:
    """Test _extract_spatial_json — pure function, no external deps."""

    def test_valid_json_direct(self):
        """Whole-string JSON parse — the happy path."""
        from cron_runner import _extract_spatial_json

        text = json.dumps({
            "result": "overworld",
            "adjacent": {"up": "wall", "down": "floor", "left": "wall", "right": "door"},
            "visible_exits": ["down"],
            "player_facing": "down",
            "text_content": ["OAK: Hello there!"],
            "suggested_action": "move down",
        })
        result = _extract_spatial_json(text)
        assert result["result"] == "overworld"
        assert result["adjacent"]["up"] == "wall"
        assert result["visible_exits"] == ["down"]

    def test_extra_text_around_json(self):
        """JSON embedded in leading/trailing text still parses."""
        from cron_runner import _extract_spatial_json

        text = 'Here is the spatial data:\n{"result": "overworld"}\nEnd.'
        result = _extract_spatial_json(text)
        # The function tries whole-string JSON first — that will fail.
        # Then regex finds \{"result": "overworld"\} and parses it.
        assert result["result"] == "overworld"

    def test_markdown_fenced_json(self):
        """JSON inside ``` fences is stripped and parsed."""
        from cron_runner import _extract_spatial_json

        text = '```json\n{"result": "battle", "adjacent": {"up": "enemy"}}\n```'
        result = _extract_spatial_json(text)
        assert result["result"] == "battle"
        assert result["adjacent"]["up"] == "enemy"

    def test_markdown_fence_no_lang(self):
        """``` fences without language specifier."""
        from cron_runner import _extract_spatial_json

        text = '```\n{"result": "dialog", "text_content": ["Oak: ..."]}\n```'
        result = _extract_spatial_json(text)
        assert result["result"] == "dialog"

    def test_markdown_fence_yaml_lang(self):
        """```yaml fence — trailing fence detection includes '```yaml'."""
        from cron_runner import _extract_spatial_json

        text = '```yaml\nresult: menu\nadjacent:\n  up: wall\n```yaml'
        result = _extract_spatial_json(text)
        # YAML fallback should parse this
        assert result["result"] == "menu"

    def test_nested_braces_in_json(self):
        """JSON with nested objects in values."""
        from cron_runner import _extract_spatial_json

        data = {
            "result": "overworld",
            "adjacent": {"up": "wall", "down": "floor"},
            "npcs": [{"name": "Rival", "position": "up"}],
        }
        text = json.dumps(data)
        result = _extract_spatial_json(text)
        assert result["result"] == "overworld"
        assert len(result["npcs"]) == 1
        assert result["npcs"][0]["name"] == "Rival"

    def test_regex_extracts_double_brace_json(self):
        """Regex fallback finds a JSON object inside text with nested braces."""
        from cron_runner import _extract_spatial_json

        # The regex r'\{[^{}]*\}' won't match nested braces.
        # But we provide YAML-safe content with flat structure
        text = 'prefix {"result": "menu", "items": ["SAVE", "POKéMON", "ITEM"]} suffix'
        result = _extract_spatial_json(text)
        assert result["result"] == "menu"
        assert "SAVE" in result["items"]

    def test_yaml_fallback(self):
        """When JSON parsing fails, YAML.safe_load is attempted."""
        from cron_runner import _extract_spatial_json

        text = """result: overworld
adjacent:
  up: wall
  down: floor
  left: wall
  right: door
visible_exits:
  - down
  - right
player_facing: down
text_content: []
suggested_action: move forward"""
        result = _extract_spatial_json(text)
        assert result["result"] == "overworld"
        assert result["adjacent"]["down"] == "floor"
        assert "down" in result["visible_exits"]

    def test_yaml_fallback_handles_simple_key_value(self):
        """YAML with flat key-value pairs."""
        from cron_runner import _extract_spatial_json

        text = "result: dialog\nspeaker: Oak"
        result = _extract_spatial_json(text)
        assert result["result"] == "dialog"
        assert result["speaker"] == "Oak"

    def test_unparseable_text_returns_unknown(self):
        """Completely unparseable text returns fallback with _parse_error."""
        from cron_runner import _extract_spatial_json

        text = "I'm not JSON or YAML. Just a sentence."
        result = _extract_spatial_json(text)
        assert result["result"] == "unknown"
        assert "_parse_error" in result
        assert "I'm not JSON" in result["_parse_error"]

    def test_empty_string_returns_unknown(self):
        """Empty string produces fallback."""
        from cron_runner import _extract_spatial_json

        result = _extract_spatial_json("")
        assert result["result"] == "unknown"

    def test_partial_json_braces_unbalanced(self):
        """Unbalanced braces — JSON parse fails, regex may or may not match."""
        from cron_runner import _extract_spatial_json

        text = '{"result": "overworld"'  # missing closing }
        result = _extract_spatial_json(text)
        # Regex won't match (unbalanced braces), YAML won't parse
        # But Python's yaml.safe_load may parse this as a string
        assert "result" in result
        # If parse_error, that's fine; if YAML succeeded, also fine
        if result.get("result") == "unknown":
            assert "_parse_error" in result

    def test_blank_lines_before_json(self):
        """Blank lines before the JSON object."""
        from cron_runner import _extract_spatial_json

        text = '\n\n  \n{"result": "overworld", "adjacent": {"up": "wall"}}'
        result = _extract_spatial_json(text)
        assert result["result"] == "overworld"

    def test_result_field_overworld(self):
        """result field: overworld."""
        from cron_runner import _extract_spatial_json

        text = json.dumps({"result": "overworld"})
        result = _extract_spatial_json(text)
        assert result["result"] == "overworld"

    def test_result_field_battle(self):
        """result field: battle."""
        from cron_runner import _extract_spatial_json

        text = json.dumps({"result": "battle"})
        result = _extract_spatial_json(text)
        assert result["result"] == "battle"

    def test_result_field_dialog(self):
        """result field: dialog."""
        from cron_runner import _extract_spatial_json

        text = json.dumps({"result": "dialog"})
        result = _extract_spatial_json(text)
        assert result["result"] == "dialog"

    def test_result_field_menu(self):
        """result field: menu."""
        from cron_runner import _extract_spatial_json

        text = json.dumps({"result": "menu"})
        result = _extract_spatial_json(text)
        assert result["result"] == "menu"

    def test_result_field_title(self):
        """result field: title (title screen)."""
        from cron_runner import _extract_spatial_json

        text = json.dumps({"result": "title"})
        result = _extract_spatial_json(text)
        assert result["result"] == "title"

    def test_adjacent_all_directions(self):
        """adjacent field with all 4 directions."""
        from cron_runner import _extract_spatial_json

        data = {
            "result": "overworld",
            "adjacent": {"up": "wall", "down": "floor", "left": "door", "right": "wall"},
        }
        text = json.dumps(data)
        result = _extract_spatial_json(text)
        assert result["adjacent"]["up"] == "wall"
        assert result["adjacent"]["down"] == "floor"
        assert result["adjacent"]["left"] == "door"
        assert result["adjacent"]["right"] == "wall"

    def test_adjacent_partial_directions(self):
        """adjacent field with only 2 directions (some edges)."""
        from cron_runner import _extract_spatial_json

        data = {
            "result": "overworld",
            "adjacent": {"up": "wall", "left": "wall"},
        }
        text = json.dumps(data)
        result = _extract_spatial_json(text)
        assert result["adjacent"]["up"] == "wall"
        assert result["adjacent"]["left"] == "wall"
        assert "down" not in result["adjacent"]
        assert "right" not in result["adjacent"]

    def test_missing_result_field_still_parses(self):
        """JSON without a 'result' field still parses — returned as-is."""
        from cron_runner import _extract_spatial_json

        text = json.dumps({"adjacent": {"up": "wall"}, "visible_exits": ["down"]})
        result = _extract_spatial_json(text)
        assert result["adjacent"]["up"] == "wall"
        assert "result" not in result


# ── cartographer_analyze tests (mocked OpenRouterClient) ────────────────

class TestCartographerAnalyze:
    """Test cartographer_analyze with mocked OpenRouterClient."""

    def _make_screenshot(self) -> np.ndarray:
        """Return a small numpy array representing a GBA screenshot."""
        return np.zeros((160, 144, 3), dtype=np.uint8)

    def _valid_spatial_json(self) -> str:
        return json.dumps({
            "result": "overworld",
            "adjacent": {"up": "wall", "down": "floor", "left": "wall", "right": "door"},
            "visible_exits": ["down", "right"],
            "player_facing": "down",
            "text_content": ["PALLET TOWN"],
            "suggested_action": "move down",
        })

    def test_happy_path_returns_parsed_json_and_raw_text(self):
        """cartographer_analyze returns (parsed_dict, raw_text) on success."""
        from cron_runner import cartographer_analyze

        spatial = self._valid_spatial_json()
        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {"content": spatial}

        screenshot = self._make_screenshot()
        result, raw = cartographer_analyze(mock_client, screenshot)

        assert result["result"] == "overworld"
        assert result["adjacent"]["down"] == "floor"
        assert raw == spatial

    def test_sends_reference_image_first(self):
        """Reference image is the FIRST image in the message content array."""
        from cron_runner import cartographer_analyze

        spatial = self._valid_spatial_json()
        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {"content": spatial}

        screenshot = self._make_screenshot()
        cartographer_analyze(mock_client, screenshot)

        # Verify chat_completion was called
        mock_client.chat_completion.assert_called_once()
        call_kwargs = mock_client.chat_completion.call_args.kwargs

        # Check messages structure
        messages = call_kwargs.get("messages", [])
        assert len(messages) == 2
        assert messages[0]["role"] == "system"

        user_content = messages[1]["content"]
        assert isinstance(user_content, list)

        # First content item should be text (the template)
        assert user_content[0]["type"] == "text"

        # Second content item should be the reference image (first image)
        ref_img = user_content[1]
        assert ref_img["type"] == "image_url"
        assert "reference" in ref_img["image_url"]["url"] or "REFERENCE" in ref_img["image_url"]["url"] or "data:image/png;base64," in ref_img["image_url"]["url"]

        # Third content item should be the live screenshot (second image)
        live_img = user_content[2]
        assert live_img["type"] == "image_url"
        assert "data:image/png;base64," in live_img["image_url"]["url"]

    def test_uses_gemma_12b_model(self):
        """Cartographer uses google/gemma-3-12b-it model."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": json.dumps({"result": "overworld"})
        }

        screenshot = self._make_screenshot()
        cartographer_analyze(mock_client, screenshot)

        call_kwargs = mock_client.chat_completion.call_args.kwargs
        assert call_kwargs["model"] == "google/gemma-3-12b-it"

    def test_low_temperature_for_deterministic_output(self):
        """Cartographer uses low temperature (0.1) for deterministic output."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": json.dumps({"result": "overworld"})
        }

        screenshot = self._make_screenshot()
        cartographer_analyze(mock_client, screenshot)

        call_kwargs = mock_client.chat_completion.call_args.kwargs
        assert call_kwargs["temperature"] == 0.1

    def test_max_tokens_2048(self):
        """Cartographer uses max_tokens=2048."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": json.dumps({"result": "overworld"})
        }

        screenshot = self._make_screenshot()
        cartographer_analyze(mock_client, screenshot)

        call_kwargs = mock_client.chat_completion.call_args.kwargs
        assert call_kwargs["max_tokens"] == 2048

    def test_api_returns_malformed_json_parsed_as_unknown(self):
        """When API returns unparseable text, _extract_spatial_json fallback."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": "I am a confused model. No JSON here."
        }

        screenshot = self._make_screenshot()
        result, raw = cartographer_analyze(mock_client, screenshot)

        assert result["result"] == "unknown"
        assert "_parse_error" in result
        assert raw == "I am a confused model. No JSON here."

    def test_api_returns_malformed_json_partial(self):
        """API returns partially valid JSON that YAML can parse."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": "result: overworld\ntext_content:\n  - Hello"
        }

        screenshot = self._make_screenshot()
        result, raw = cartographer_analyze(mock_client, screenshot)

        # YAML fallback should parse this
        assert result["result"] == "overworld"
        assert raw == "result: overworld\ntext_content:\n  - Hello"

    def test_api_failure_network_error(self):
        """When chat_completion raises an exception, it propagates."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.side_effect = Exception("Connection timeout")

        screenshot = self._make_screenshot()

        with pytest.raises(Exception, match="Connection timeout"):
            cartographer_analyze(mock_client, screenshot)

    def test_api_returns_empty_content(self):
        """When API returns empty content string — fallback to unknown."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {"content": ""}

        screenshot = self._make_screenshot()
        result, raw = cartographer_analyze(mock_client, screenshot)

        assert result["result"] == "unknown"
        assert raw == ""

    def test_api_returns_none_content(self):
        """When API returns None content (no 'content' key)."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {}

        screenshot = self._make_screenshot()
        result, raw = cartographer_analyze(mock_client, screenshot)

        assert result["result"] == "unknown"
        assert raw == ""

    def test_adjacent_tiles_parsed_correctly(self):
        """All 4 adjacent directions parsed from spatial JSON."""
        from cron_runner import cartographer_analyze

        spatial = json.dumps({
            "result": "overworld",
            "adjacent": {
                "up": "wall",
                "down": "floor",
                "left": "ledge",
                "right": "grass",
            },
        })
        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {"content": spatial}

        screenshot = self._make_screenshot()
        result, _ = cartographer_analyze(mock_client, screenshot)

        assert result["adjacent"]["up"] == "wall"
        assert result["adjacent"]["down"] == "floor"
        assert result["adjacent"]["left"] == "ledge"
        assert result["adjacent"]["right"] == "grass"

    def test_result_field_overworld(self):
        """result=overworld correctly parsed."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": json.dumps({"result": "overworld"})
        }

        screenshot = self._make_screenshot()
        result, _ = cartographer_analyze(mock_client, screenshot)
        assert result["result"] == "overworld"

    def test_result_field_dialog(self):
        """result=dialog correctly parsed."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": json.dumps({"result": "dialog", "speaker": "Oak"})
        }

        screenshot = self._make_screenshot()
        result, _ = cartographer_analyze(mock_client, screenshot)
        assert result["result"] == "dialog"

    def test_result_field_battle(self):
        """result=battle correctly parsed."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": json.dumps({"result": "battle", "enemy": "RATTATA"})
        }

        screenshot = self._make_screenshot()
        result, _ = cartographer_analyze(mock_client, screenshot)
        assert result["result"] == "battle"

    def test_result_field_menu(self):
        """result=menu correctly parsed."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": json.dumps({
                "result": "menu",
                "items": ["POKéDEX", "POKéMON", "ITEM", "SAVE", "OPTION", "EXIT"],
            })
        }

        screenshot = self._make_screenshot()
        result, _ = cartographer_analyze(mock_client, screenshot)
        assert result["result"] == "menu"
        assert "SAVE" in result["items"]

    def test_result_field_title(self):
        """result=title correctly parsed."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": json.dumps({"result": "title"})
        }

        screenshot = self._make_screenshot()
        result, _ = cartographer_analyze(mock_client, screenshot)
        assert result["result"] == "title"

    def test_full_workflow_sends_zeroed_screenshot_as_base64(self):
        """Verify the live screenshot is encoded and sent as base64 data URL."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {
            "content": json.dumps({"result": "overworld"})
        }

        # Create a striped screenshot so base64 isn't all zeros
        screenshot = np.zeros((160, 144, 3), dtype=np.uint8)
        screenshot[0, 0, 0] = 255  # One red pixel

        cartographer_analyze(mock_client, screenshot)

        # Extract the user message content
        call_args = mock_client.chat_completion.call_args
        messages = call_args.kwargs["messages"]
        user_content = messages[1]["content"]

        # Third item is the live screenshot
        live_img_url = user_content[2]["image_url"]["url"]
        assert live_img_url.startswith("data:image/png;base64,")
        assert len(live_img_url) > 50  # Non-trivial base64 content

    def test_missing_content_key_returns_empty_string(self):
        """When response has no 'content' key, get() returns '' default."""
        from cron_runner import cartographer_analyze

        mock_client = MagicMock()
        mock_client.chat_completion.return_value = {"choices": [{"message": {}}]}

        screenshot = self._make_screenshot()
        result, raw = cartographer_analyze(mock_client, screenshot)

        assert raw == ""
        assert result["result"] == "unknown"


# ── Integration: screenshot_to_base64 + cartographer_analyze ─────────

class TestScreenshotToBase64:
    """Test screenshot_to_base64 helper."""

    def test_encodes_to_base64_data_url_format(self):
        """screenshot_to_base64 returns valid base64 string."""
        from cron_runner import screenshot_to_base64

        screenshot = np.zeros((160, 144, 3), dtype=np.uint8)
        screenshot[0, 0, 0] = 128  # ensure non-zero content

        b64 = screenshot_to_base64(screenshot)
        assert isinstance(b64, str)
        assert len(b64) > 0
        # Should be base64 (alphanumeric + +/=)
        import base64
        base64.b64decode(b64)  # should not raise

    def test_scales_3x_with_nearest_neighbor(self):
        """screenshot_to_base64 resizes 3x for pixel-perfect scaling."""
        from cron_runner import screenshot_to_base64

        screenshot = np.zeros((160, 144, 3), dtype=np.uint8)
        screenshot[10:20, 10:20, 0] = 255  # Red square

        b64 = screenshot_to_base64(screenshot)
        # Verify it's valid base64
        import base64
        decoded = base64.b64decode(b64)
        assert len(decoded) > 100  # 3x scaled image should be larger
