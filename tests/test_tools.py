"""
Unit tests for tools.py — parse_tool_call and execute_tool_call.

Tests the tool-call parser (JSON, code-fenced, bare object, fallback)
and the executor (press_button, wait, combo, invalid tool, error paths).
"""

from __future__ import annotations

from unittest.mock import MagicMock


from src.core.tools import (
    TOOL_SCHEMA,
    execute_tool_call,
    parse_tool_call,
)

# ── helpers ────────────────────────────────────────────────────────────────

def _mock_emulator() -> MagicMock:
    """Return a MagicMock with press_button, wait, and combo methods."""
    emu = MagicMock()
    emu.press_button = MagicMock()
    emu.wait = MagicMock()
    emu.combo = MagicMock()
    return emu


# ── AC-014: parse_tool_call code-fenced JSON ────────────────────────────────

class TestParseToolCallCodeFenced:
    """AC-014: code-fenced JSON → correct tool name + args."""

    def test_code_fenced_press_button(self):
        resp = '```json\n{"name": "press_button", "arguments": {"button": "a"}}\n```'
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "press_button"
        assert result["arguments"] == {"button": "a"}

    def test_code_fenced_wait(self):
        resp = '```json\n{"name": "wait", "arguments": {"frames": 60}}\n```'
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "wait"
        assert result["arguments"] == {"frames": 60}

    def test_code_fenced_combo(self):
        resp = (
            '```json\n'
            '{"name": "combo", "arguments": {"buttons": ["up", "right"], "duration": 10}}\n'
            '```'
        )
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "combo"
        assert result["arguments"] == {"buttons": ["up", "right"], "duration": 10}

    def test_code_fenced_no_json_tag(self):
        """Code fence without explicit 'json' language tag still works."""
        resp = '```\n{"name": "press_button", "arguments": {"button": "b"}}\n```'
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "press_button"
        assert result["arguments"] == {"button": "b"}

    def test_code_fenced_with_extra_text(self):
        """Text before/after the code fence should not confuse the parser."""
        resp = (
            "I think we should press A.\n"
            '```json\n{"name": "press_button", "arguments": {"button": "a"}}\n```\n'
            "Let me know if you agree."
        )
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "press_button"
        assert result["arguments"] == {"button": "a"}

    def test_code_fenced_invalid_json_returns_none(self):
        resp = '```json\n{not valid json}\n```'
        result = parse_tool_call(resp)
        assert result is None


# ── AC-015: parse_tool_call inline / bare JSON ──────────────────────────────

class TestParseToolCallInline:
    """AC-015: inline format → extracted action."""

    def test_bare_json_press_button(self):
        resp = '{"name": "press_button", "arguments": {"button": "start", "duration": 3}}'
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "press_button"
        assert result["arguments"] == {"button": "start", "duration": 3}

    def test_bare_json_wait(self):
        resp = '{"name": "wait", "arguments": {"frames": 30}}'
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "wait"
        assert result["arguments"] == {"frames": 30}

    def test_openai_style_tool_calls_array(self):
        """OpenAI-style response with tool_calls array."""
        resp = (
            '{"tool_calls": ['
            '  {"function": {"name": "press_button", "arguments": {"button": "a"}}}'
            ']}'
        )
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "press_button"
        assert result["arguments"] == {"button": "a"}

    def test_openai_style_uses_first_tool_call(self):
        resp = (
            '{"tool_calls": ['
            '  {"function": {"name": "wait", "arguments": {"frames": 10}}},'
            '  {"function": {"name": "press_button", "arguments": {"button": "b"}}}'
            ']}'
        )
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "wait"

    def test_empty_response_returns_none(self):
        result = parse_tool_call("")
        assert result is None

    def test_no_tool_call_returns_none(self):
        resp = "The screen shows Professor Oak's lab. I see a Poké Ball on the table."
        result = parse_tool_call(resp)
        assert result is None

    def test_garbage_json_fallback(self):
        """Malformed JSON should not crash — returns None."""
        result = parse_tool_call("{ broken json {{{")
        assert result is None


# ── AC-016: execute_tool_call press_button ──────────────────────────────────

class TestExecuteToolCallPressButton:
    """AC-016: press_button call → emulator receives correct method."""

    def test_press_button_calls_emulator(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "press_button", {"button": "a", "duration": 10})
        assert "Pressed a for 10 frames" in result
        emu.press_button.assert_called_once_with("a", frames=10)

    def test_press_button_default_duration(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "press_button", {"button": "b"})
        assert "Pressed b for 5 frames" in result
        emu.press_button.assert_called_once_with("b", frames=5)

    def test_press_button_up(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "press_button", {"button": "up", "duration": 1})
        assert "Pressed up for 1 frames" in result
        emu.press_button.assert_called_once_with("up", frames=1)

    def test_press_button_missing_button_raises(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "press_button", {})
        assert result.startswith("Error:")
        emu.press_button.assert_not_called()


# ── AC-017: execute_tool_call wait ──────────────────────────────────────────

class TestExecuteToolCallWait:
    """AC-017: wait call → emulator advances correct frames."""

    def test_wait_calls_emulator(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "wait", {"frames": 60})
        assert "Waited 60 frames" in result
        emu.wait.assert_called_once_with(60)

    def test_wait_zero_frames(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "wait", {"frames": 0})
        assert "Waited 0 frames" in result
        emu.wait.assert_called_once_with(0)

    def test_wait_missing_frames_raises(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "wait", {})
        assert result.startswith("Error:")
        emu.wait.assert_not_called()


# ── AC-018: execute_tool_call invalid / unknown tool ─────────────────────────

class TestExecuteToolCallInvalid:
    """AC-018: unknown tool name → handled gracefully."""

    def test_unknown_tool_returns_error(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "jump", {"height": 10})
        assert result == "Error: Unknown tool 'jump'."
        emu.press_button.assert_not_called()
        emu.wait.assert_not_called()

    def test_nonexistent_tool_returns_error(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "fly", {})
        assert result == "Error: Unknown tool 'fly'."
        emu.press_button.assert_not_called()
        emu.wait.assert_not_called()

    def test_empty_tool_name_returns_error(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "", {})
        assert result == "Error: Unknown tool ''."
        emu.press_button.assert_not_called()
        emu.wait.assert_not_called()


# ── additional coverage: combo tool ─────────────────────────────────────────

class TestExecuteToolCallCombo:
    """Combo execution — multiple simultaneous buttons."""

    def test_combo_presses_multiple_buttons(self):
        emu = _mock_emulator()
        result = execute_tool_call(
            emu, "combo", {"buttons": ["up", "right"], "duration": 5}
        )
        assert "Pressed ['up', 'right'] simultaneously for 5 frames" in result
        emu.combo.assert_called_once_with(["up", "right"], frames=5)

    def test_combo_single_button(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "combo", {"buttons": ["a"], "duration": 3})
        assert "Pressed ['a'] simultaneously for 3 frames" in result
        emu.combo.assert_called_once_with(["a"], frames=3)

    def test_combo_default_duration(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "combo", {"buttons": ["a", "b"]})
        assert "Pressed ['a', 'b'] simultaneously for 5 frames" in result
        emu.combo.assert_called_once_with(["a", "b"], frames=5)

    def test_combo_missing_buttons_raises(self):
        emu = _mock_emulator()
        result = execute_tool_call(emu, "combo", {})
        assert result.startswith("Error:")
        emu.combo.assert_not_called()


# ── additional coverage: TOOL_SCHEMA validation ─────────────────────────────

class TestToolSchema:
    """Verify the TOOL_SCHEMA is well-formed."""

    def test_all_tools_have_required_fields(self):
        for tool in TOOL_SCHEMA:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func

    def test_tool_schema_names_match(self):
        """Schema names match what execute_tool_call accepts."""
        expected_names = {"press_button", "wait", "combo"}
        actual_names = {t["function"]["name"] for t in TOOL_SCHEMA}
        assert actual_names == expected_names

    def test_press_button_has_required_button(self):
        press = next(t for t in TOOL_SCHEMA if t["function"]["name"] == "press_button")
        required = press["function"]["parameters"].get("required", [])
        assert "button" in required

    def test_wait_has_required_frames(self):
        wait = next(t for t in TOOL_SCHEMA if t["function"]["name"] == "wait")
        required = wait["function"]["parameters"].get("required", [])
        assert "frames" in required

    def test_combo_has_required_buttons(self):
        combo = next(t for t in TOOL_SCHEMA if t["function"]["name"] == "combo")
        required = combo["function"]["parameters"].get("required", [])
        assert "buttons" in required
