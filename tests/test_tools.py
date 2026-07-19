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

    def test_code_fenced_press_button(self) -> None:
        resp = '```json\n{"name": "press_button", "arguments": {"button": "a"}}\n```'
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "press_button"
        assert result["arguments"] == {"button": "a"}

    def test_code_fenced_wait(self) -> None:
        resp = '```json\n{"name": "wait", "arguments": {"frames": 60}}\n```'
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "wait"
        assert result["arguments"] == {"frames": 60}

    def test_code_fenced_combo(self) -> None:
        resp = (
            '```json\n'
            '{"name": "combo", "arguments": {"buttons": ["up", "right"], "duration": 10}}\n'
            '```'
        )
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "combo"
        assert result["arguments"] == {"buttons": ["up", "right"], "duration": 10}

    def test_code_fenced_no_json_tag(self) -> None:
        """Code fence without explicit 'json' language tag still works."""
        resp = '```\n{"name": "press_button", "arguments": {"button": "b"}}\n```'
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "press_button"
        assert result["arguments"] == {"button": "b"}

    def test_code_fenced_with_extra_text(self) -> None:
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

    def test_code_fenced_invalid_json_returns_none(self) -> None:
        resp = '```json\n{not valid json}\n```'
        result = parse_tool_call(resp)
        assert result is None


# ── AC-015: parse_tool_call inline / bare JSON ──────────────────────────────

class TestParseToolCallInline:
    """AC-015: inline format → extracted action."""

    def test_bare_json_press_button(self) -> None:
        resp = '{"name": "press_button", "arguments": {"button": "start", "duration": 3}}'
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "press_button"
        assert result["arguments"] == {"button": "start", "duration": 3}

    def test_bare_json_wait(self) -> None:
        resp = '{"name": "wait", "arguments": {"frames": 30}}'
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "wait"
        assert result["arguments"] == {"frames": 30}

    def test_openai_style_tool_calls_array(self) -> None:
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

    def test_openai_style_uses_first_tool_call(self) -> None:
        resp = (
            '{"tool_calls": ['
            '  {"function": {"name": "wait", "arguments": {"frames": 10}}},'
            '  {"function": {"name": "press_button", "arguments": {"button": "b"}}}'
            ']}'
        )
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "wait"

    def test_empty_response_returns_none(self) -> None:
        result = parse_tool_call("")
        assert result is None

    def test_no_tool_call_returns_none(self) -> None:
        resp = "The screen shows Professor Oak's lab. I see a Poké Ball on the table."
        result = parse_tool_call(resp)
        assert result is None

    def test_garbage_json_fallback(self) -> None:
        """Malformed JSON should not crash — returns None."""
        result = parse_tool_call("{ broken json {{{")
        assert result is None


# ── COV-26: parse_tool_call XML (owl-alpha) format ──────────────────────────

class TestParseToolCallXML:
    """COV-26: longcat XML tool call format parsing."""

    def test_xml_press_button(self) -> None:
        """Basic XML format: press_button with string arg."""
        resp = (
            "<longcat_tool_call>press_button"
            "<longcat_arg_key>button</longcat_arg_key>"
            "<longcat_arg_value>a</longcat_arg_value>"
            "</longcat_tool_call>"
        )
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "press_button"
        assert result["arguments"] == {"button": "a"}

    def test_xml_wait_with_int_value(self) -> None:
        """XML format with int arg value — should be parsed as int."""
        resp = (
            "<longcat_tool_call>wait"
            "<longcat_arg_key>frames</longcat_arg_key>"
            "<longcat_arg_value>60</longcat_arg_value>"
            "</longcat_tool_call>"
        )
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "wait"
        assert result["arguments"] == {"frames": 60}

    def test_xml_multiple_args(self) -> None:
        """XML format with multiple key-value pairs."""
        resp = (
            "<longcat_tool_call>combo"
            "<longcat_arg_key>buttons</longcat_arg_key>"
            "<longcat_arg_value>up</longcat_arg_value>"
            "<longcat_arg_key>duration</longcat_arg_key>"
            "<longcat_arg_value>10</longcat_arg_value>"
            "</longcat_tool_call>"
        )
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "combo"
        assert result["arguments"] == {"buttons": "up", "duration": 10}

    def test_xml_with_extra_text(self) -> None:
        """XML call embedded in natural language text."""
        resp = (
            "I'll press the A button.\n"
            "<longcat_tool_call>press_button"
            "<longcat_arg_key>button</longcat_arg_key>"
            "<longcat_arg_value>a</longcat_arg_value>"
            "</longcat_tool_call>\n"
            "That should advance the dialog."
        )
        result = parse_tool_call(resp)
        assert result is not None
        assert result["name"] == "press_button"
        assert result["arguments"] == {"button": "a"}

    def test_xml_malformed_no_longcat_tag_returns_none(self) -> None:
        """Text without longcat tags returns None."""
        resp = "Just some regular text, no XML tools here."
        result = parse_tool_call(resp)
        assert result is None

    def test_xml_malformed_no_name(self) -> None:
        """XML with no tool name before first arg tag — returns None or empty name."""
        resp = (
            "<longcat_tool_call>"
            "<longcat_arg_key>button</longcat_arg_key>"
            "<longcat_arg_value>a</longcat_arg_value>"
            "</longcat_tool_call>"
        )
        result = parse_tool_call(resp)
        # With empty tool name, the parser may return None or a dict with empty name
        if result is not None:
            assert result["name"] == ""


# ── AC-016: execute_tool_call press_button ──────────────────────────────────

class TestExecuteToolCallPressButton:
    """AC-016: press_button call → emulator receives correct method."""

    def test_press_button_calls_emulator(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "press_button", {"button": "a", "duration": 10})
        assert "Pressed a for 10 frames" in result
        emu.press_button.assert_called_once_with("a", frames=10)

    def test_press_button_default_duration(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "press_button", {"button": "b"})
        assert "Pressed b for 5 frames" in result
        emu.press_button.assert_called_once_with("b", frames=5)

    def test_press_button_up(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "press_button", {"button": "up", "duration": 1})
        assert "Pressed up for 1 frames" in result
        emu.press_button.assert_called_once_with("up", frames=1)

    def test_press_button_missing_button_raises(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "press_button", {})
        assert result.startswith("Error:")
        emu.press_button.assert_not_called()


# ── AC-017: execute_tool_call wait ──────────────────────────────────────────

class TestExecuteToolCallWait:
    """AC-017: wait call → emulator advances correct frames."""

    def test_wait_calls_emulator(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "wait", {"frames": 60})
        assert "Waited 60 frames" in result
        emu.wait.assert_called_once_with(60)

    def test_wait_zero_frames(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "wait", {"frames": 0})
        assert "Waited 0 frames" in result
        emu.wait.assert_called_once_with(0)

    def test_wait_missing_frames_raises(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "wait", {})
        assert result.startswith("Error:")
        emu.wait.assert_not_called()


# ── AC-018: execute_tool_call invalid / unknown tool ─────────────────────────

class TestExecuteToolCallInvalid:
    """AC-018: unknown tool name → handled gracefully."""

    def test_unknown_tool_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "jump", {"height": 10})
        assert result == "Error: Unknown tool 'jump'."
        emu.press_button.assert_not_called()
        emu.wait.assert_not_called()

    def test_nonexistent_tool_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "fly", {})
        assert result == "Error: Unknown tool 'fly'."
        emu.press_button.assert_not_called()
        emu.wait.assert_not_called()

    def test_empty_tool_name_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "", {})
        assert result == "Error: Unknown tool ''."
        emu.press_button.assert_not_called()
        emu.wait.assert_not_called()


# ── additional coverage: combo tool ─────────────────────────────────────────

class TestExecuteToolCallCombo:
    """Combo execution — multiple simultaneous buttons."""

    def test_combo_presses_multiple_buttons(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(
            emu, "combo", {"buttons": ["up", "right"], "duration": 5}
        )
        assert "Pressed ['up', 'right'] simultaneously for 5 frames" in result
        emu.combo.assert_called_once_with(["up", "right"], frames=5)

    def test_combo_single_button(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "combo", {"buttons": ["a"], "duration": 3})
        assert "Pressed ['a'] simultaneously for 3 frames" in result
        emu.combo.assert_called_once_with(["a"], frames=3)

    def test_combo_default_duration(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "combo", {"buttons": ["a", "b"]})
        assert "Pressed ['a', 'b'] simultaneously for 5 frames" in result
        emu.combo.assert_called_once_with(["a", "b"], frames=5)

    def test_combo_missing_buttons_raises(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "combo", {})
        assert result.startswith("Error:")
        emu.combo.assert_not_called()


# ── additional coverage: TOOL_SCHEMA validation ─────────────────────────────

class TestToolSchema:
    """Verify the TOOL_SCHEMA is well-formed."""

    def test_all_tools_have_required_fields(self) -> None:
        for tool in TOOL_SCHEMA:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func

    def test_tool_schema_names_match(self) -> None:
        """Schema names match what execute_tool_call accepts."""
        expected_names = {
            "press_button", "wait", "combo", "fast_forward",
            # Battle composite tools (BATTLE-AGENT task)
            "select_move", "run_from_battle",
            "use_battle_item", "switch_pokemon",
        }
        actual_names = {t["function"]["name"] for t in TOOL_SCHEMA}
        assert actual_names == expected_names

    def test_press_button_has_required_button(self) -> None:
        press = next(t for t in TOOL_SCHEMA if t["function"]["name"] == "press_button")
        required = press["function"]["parameters"].get("required", [])
        assert "button" in required

    def test_wait_has_required_frames(self) -> None:
        wait = next(t for t in TOOL_SCHEMA if t["function"]["name"] == "wait")
        required = wait["function"]["parameters"].get("required", [])
        assert "frames" in required

    def test_combo_has_required_buttons(self) -> None:
        combo = next(t for t in TOOL_SCHEMA if t["function"]["name"] == "combo")
        required = combo["function"]["parameters"].get("required", [])
        assert "buttons" in required

    def test_fast_forward_has_required_frames(self) -> None:
        ff = next(t for t in TOOL_SCHEMA if t["function"]["name"] == "fast_forward")
        required = ff["function"]["parameters"].get("required", [])
        assert "frames" in required

    def test_fast_forward_default_frames(self) -> None:
        ff = next(t for t in TOOL_SCHEMA if t["function"]["name"] == "fast_forward")
        default = ff["function"]["parameters"]["properties"]["frames"].get("default")
        assert default == 180


# ── fast_forward tool execution ────────────────────────────────────────────

class TestExecuteToolCallFastForward:
    """fast_forward execution delegates to emulator.fast_forward."""

    def test_fast_forward_with_frames(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "fast_forward", {"frames": 60})
        assert "Fast-forwarded 60 frames" in result
        emu.fast_forward.assert_called_once_with(60)

    def test_fast_forward_large_frames(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "fast_forward", {"frames": 600})
        assert "Fast-forwarded 600 frames" in result
        emu.fast_forward.assert_called_once_with(600)

    def test_fast_forward_zero_frames(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "fast_forward", {"frames": 0})
        assert "Fast-forwarded 0 frames" in result
        emu.fast_forward.assert_called_once_with(0)

    def test_fast_forward_missing_frames_raises(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "fast_forward", {})
        assert result.startswith("Error:")
        emu.fast_forward.assert_not_called()

    def test_fast_forward_invalid_frames(self) -> None:
        """String frames value — the tool passes it through; emulator handles it."""
        emu = _mock_emulator()
        execute_tool_call(emu, "fast_forward", {"frames": "invalid"})
        # Should still attempt the call — error comes from emulator
        emu.fast_forward.assert_called_once_with("invalid")


# ── BATTLE-AGENT: battle composite tools ────────────────────────────────────
#
# Each battle tool is a thin wrapper around a multi-step button sequence
# targeting the Gen 1 battle menu. Tests verify the right sequence of
# emulator calls is made and that invalid arguments surface as errors.

# Battles always end with an animation wait + fast_forward so the next
# state-window re-read sees fresh RAM.
_BATTLE_ANIM_TAIL = 1  # minimum fast_forward call after action


class TestBattleToolSchema:
    """TOOL_SCHEMA contains well-formed entries for each battle tool."""

    def test_select_move_in_schema(self) -> None:
        tool = next(
            (t for t in TOOL_SCHEMA if t["function"]["name"] == "select_move"), None
        )
        assert tool is not None
        assert "description" in tool["function"]
        params = tool["function"]["parameters"]
        assert params["type"] == "object"
        assert "move_number" in params["required"]
        bounds = params["properties"]["move_number"]
        assert bounds["minimum"] == 1
        assert bounds["maximum"] == 4

    def test_run_from_battle_in_schema(self) -> None:
        tool = next(
            (t for t in TOOL_SCHEMA if t["function"]["name"] == "run_from_battle"),
            None,
        )
        assert tool is not None
        assert "description" in tool["function"]
        assert tool["function"]["parameters"]["type"] == "object"

    def test_use_battle_item_in_schema(self) -> None:
        tool = next(
            (t for t in TOOL_SCHEMA if t["function"]["name"] == "use_battle_item"),
            None,
        )
        assert tool is not None
        assert "item_name" in tool["function"]["parameters"]["required"]

    def test_switch_pokemon_in_schema(self) -> None:
        tool = next(
            (t for t in TOOL_SCHEMA if t["function"]["name"] == "switch_pokemon"),
            None,
        )
        assert tool is not None
        assert "slot" in tool["function"]["parameters"]["required"]
        bounds = tool["function"]["parameters"]["properties"]["slot"]
        assert bounds["minimum"] == 1
        assert bounds["maximum"] == 6


class TestExecuteSelectMove:
    """select_move navigates FIGHT → moves → move N (1-4) → A."""

    def test_move_1_uses_two_a_presses(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "select_move", {"move_number": 1})
        assert "Selected move 1" in result
        a_calls = [
            c for c in emu.press_button.call_args_list if c.args[0] == "a"
        ]
        assert len(a_calls) == 2  # FIGHT confirm + move 1 confirm
        assert emu.fast_forward.call_count >= _BATTLE_ANIM_TAIL

    def test_move_2_uses_right(self) -> None:
        emu = _mock_emulator()
        execute_tool_call(emu, "select_move", {"move_number": 2})
        right_calls = [
            c for c in emu.press_button.call_args_list if c.args[0] == "right"
        ]
        assert len(right_calls) == 1

    def test_move_3_uses_down(self) -> None:
        emu = _mock_emulator()
        execute_tool_call(emu, "select_move", {"move_number": 3})
        down_calls = [
            c for c in emu.press_button.call_args_list if c.args[0] == "down"
        ]
        assert len(down_calls) == 1

    def test_move_4_uses_right_then_down(self) -> None:
        emu = _mock_emulator()
        execute_tool_call(emu, "select_move", {"move_number": 4})
        right_calls = [
            c for c in emu.press_button.call_args_list if c.args[0] == "right"
        ]
        down_calls = [
            c for c in emu.press_button.call_args_list if c.args[0] == "down"
        ]
        assert len(right_calls) == 1
        assert len(down_calls) == 1

    def test_invalid_move_number_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "select_move", {"move_number": 5})
        assert result.startswith("Error:")
        emu.press_button.assert_not_called()

    def test_missing_move_number_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "select_move", {})
        assert result.startswith("Error:")
        emu.press_button.assert_not_called()

    def test_zero_move_number_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "select_move", {"move_number": 0})
        assert result.startswith("Error:")
        emu.press_button.assert_not_called()


class TestExecuteRunFromBattle:
    """run_from_battle navigates FIGHT→right→down→A (RUN is BR)."""

    def test_presses_right_down_a(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "run_from_battle", {})
        assert "Ran from battle" in result
        rights = [c for c in emu.press_button.call_args_list if c.args[0] == "right"]
        downs = [c for c in emu.press_button.call_args_list if c.args[0] == "down"]
        a_calls = [c for c in emu.press_button.call_args_list if c.args[0] == "a"]
        assert len(rights) == 1
        assert len(downs) == 1
        assert len(a_calls) == 1
        assert emu.fast_forward.call_count >= _BATTLE_ANIM_TAIL


class TestExecuteUseBattleItem:
    """use_battle_item navigates FIGHT→BAG→USE→item→A."""

    def test_uses_right_and_two_as(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "use_battle_item", {"item_name": "Potion"})
        assert "Potion" in result
        rights = [c for c in emu.press_button.call_args_list if c.args[0] == "right"]
        a_calls = [c for c in emu.press_button.call_args_list if c.args[0] == "a"]
        assert len(rights) == 1
        assert len(a_calls) >= 2  # BAG confirm + USE confirm

    def test_missing_item_name_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "use_battle_item", {})
        assert result.startswith("Error:")
        emu.press_button.assert_not_called()

    def test_empty_item_name_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "use_battle_item", {"item_name": ""})
        assert result.startswith("Error:")
        emu.press_button.assert_not_called()


class TestExecuteSwitchPokemon:
    """switch_pokemon navigates FIGHT→PKMN→slot N→A."""

    def test_slot_1_uses_one_down(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "switch_pokemon", {"slot": 1})
        assert "slot 1" in result
        downs = [c for c in emu.press_button.call_args_list if c.args[0] == "down"]
        # FIGHT→PKMN is one down. No additional party navigation for slot 1.
        assert len(downs) == 1

    def test_slot_3_uses_three_downs(self) -> None:
        emu = _mock_emulator()
        execute_tool_call(emu, "switch_pokemon", {"slot": 3})
        downs = [c for c in emu.press_button.call_args_list if c.args[0] == "down"]
        # 1 menu nav (FIGHT→PKMN) + 2 party navigations = 3
        assert len(downs) == 3

    def test_invalid_slot_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "switch_pokemon", {"slot": 7})
        assert result.startswith("Error:")
        emu.press_button.assert_not_called()

    def test_missing_slot_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "switch_pokemon", {})
        assert result.startswith("Error:")
        emu.press_button.assert_not_called()

    def test_zero_slot_returns_error(self) -> None:
        emu = _mock_emulator()
        result = execute_tool_call(emu, "switch_pokemon", {"slot": 0})
        assert result.startswith("Error:")
        emu.press_button.assert_not_called()


class TestBattleToolEmulatorErrorWrapping:
    """Underlying emulator failures are surfaced as Error strings."""

    def test_emulator_runtime_error_wrapped(self) -> None:
        class BadEmu:
            def press_button(self, b, frames=5):
                raise RuntimeError("pyboy disconnected")

        result = execute_tool_call(BadEmu(), "select_move", {"move_number": 1})
        assert result.startswith("Error:")
        assert "pyboy disconnected" in result

    def test_wait_exception_wrapped(self) -> None:
        class BadEmu:
            def press_button(self, b, frames=5):
                return None

            def wait(self, n):
                raise OSError("wait failed")

        result = execute_tool_call(BadEmu(), "run_from_battle", {})
        assert result.startswith("Error:")
