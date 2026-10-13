"""Regression tests for scripts/aipp_mcp.py MCP tool handlers.

DF-MCP-1: game_step must surface bridge errors (ok=false) as error text
instead of the success-shaped stepped screen=None tile=None that misled
MCP clients into thinking the step succeeded.
"""

from __future__ import annotations

from unittest.mock import patch

from scripts import aipp_mcp


def _text_content(result):
    for item in result:
        if item.get("type") == "text":
            return item["text"]
    return ""


class TestGameStepErrorSurfacing:

    def test_game_step_paused_bridge_returns_error_text(self):
        fake_reply = {"ok": False, "error": "paused - call resume first", "paused": True}
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
