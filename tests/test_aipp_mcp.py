"""Regression tests for scripts/aipp_mcp.py MCP tool handlers.

DF-MCP-1: game_step must surface bridge errors (ok=false) as error text
instead of the success-shaped stepped screen=None tile=None that misled
MCP clients into thinking the step succeeded.

DF-AIPP-9: game_save / game_load / game_delete_save must enforce the
required 'slot' key declared in their inputSchema instead of silently
substituting a default (a 'name' typo wrote to slot1; a missing slot
forwarded None and produced 'no such save .../None.state').
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts import aipp_mcp


def _text_content(result):
    for item in result:
        if item.get("type") == "text":
            return item["text"]
    return ""


class TestGameStepErrorSurfacing:

    def test_game_step_paused_bridge_returns_error_text(self):
        fake_reply = {
            "ok": False,
            "error": "paused - call resume first",
            "paused": True,
        }
        with patch.object(aipp_mcp, "bridge", return_value=fake_reply):
            result = aipp_mcp.call_tool("game_step", {"n": 10})
        text = _text_content(result)
        assert text.startswith("error:"), f"expected error text, got: {text!r}"
        assert "paused" in text
        assert "stepped." not in text
        assert "screen=None" not in text

    def test_game_step_ok_bridge_returns_stepped_text(self):
        fake_reply = {"ok": True, "screen": "overworld", "player": "(40, 2, 2)"}
        with patch.object(aipp_mcp, "bridge", return_value=fake_reply):
            result = aipp_mcp.call_tool("game_step", {"n": 5})
        text = _text_content(result)
        assert text.startswith("stepped.")
        assert "screen=overworld" in text
        assert "tile=(40, 2, 2)" in text

    def test_game_step_bridge_down_returns_error_text(self):
        fake_reply = {"ok": False, "error": "bridge not reachable on 127.0.0.1:8770"}
        with patch.object(aipp_mcp, "bridge", return_value=fake_reply):
            result = aipp_mcp.call_tool("game_step", {"n": 1})
        text = _text_content(result)
        assert text.startswith("error:")
        assert "bridge not reachable" in text


class TestRequiredSlotValidation:
    """DF-AIPP-9: required keys declared in inputSchema are enforced by the
    handlers — a missing/misspelled key returns an error naming the key and
    never reaches the bridge."""

    @staticmethod
    def _run_with_spy(tool, args):
        spy = MagicMock(return_value={"ok": True})
        with patch.object(aipp_mcp, "bridge", spy):
            result = aipp_mcp.call_tool(tool, args)
        return _text_content(result), spy

    def test_game_save_missing_slot_errors(self):
        text, spy = self._run_with_spy("game_save", {"name": "test"})
        assert "slot" in text
        assert "required" in text
        assert spy.call_count == 0, "handler must not touch the bridge"

    def test_game_delete_save_missing_slot_errors_no_none_path(self):
        text, spy = self._run_with_spy("game_delete_save", {"name": "test"})
        assert "slot" in text
        assert "required" in text
        assert "None.state" not in text
        assert spy.call_count == 0, "handler must not touch the bridge"

    def test_game_load_missing_slot_errors(self):
        text, spy = self._run_with_spy("game_load", {"name": "test"})
        assert "slot" in text
        assert "required" in text
        assert spy.call_count == 0, "handler must not touch the bridge"

    def test_game_save_with_slot_still_works(self):
        text, spy = self._run_with_spy("game_save", {"slot": "slot1"})
        assert "error" not in text.lower()
        spy.assert_called_once()
        sent = spy.call_args[0][0]
        assert sent["cmd"] == "save"
        assert sent["slot"] == "slot1"

    def test_game_load_with_slot_still_works(self):
        text, spy = self._run_with_spy("game_load", {"slot": "slot2"})
        spy.assert_called_once()
        sent = spy.call_args[0][0]
        assert sent == {"cmd": "load", "slot": "slot2"}
        assert "error" not in text.lower()

    def test_game_delete_save_with_slot_still_works(self):
        text, spy = self._run_with_spy("game_delete_save", {"slot": "old"})
        spy.assert_called_once()
        sent = spy.call_args[0][0]
        assert sent == {"cmd": "delete_save", "slot": "old"}
        assert "error" not in text.lower()

    def test_schemas_unchanged_required_declarations_kept(self):
        """The schemas keep their required declarations — the handlers now
        enforce them. Guards against 'fixing' the bug by weakening the
        schemas instead."""
        required = {t["name"]: t["inputSchema"].get("required") for t in aipp_mcp.TOOLS}
        assert required["game_save"] == ["slot"]
        assert required["game_load"] == ["slot"]
        assert required["game_delete_save"] == ["slot"]
