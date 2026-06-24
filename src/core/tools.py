"""
Tool schema and executor for the AI‑Plays‑Pokémon agent.

Defines the Open‑AI‑style function‑calling tool definitions that an LLM can
use to control the emulator, plus helpers to parse tool calls from model
responses and execute them against an :class:`Emulator` instance.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

# ── Tool schema (OpenAI function-calling format) ─────────────────────────────

TOOL_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "press_button",
            "description": (
                "Press and hold a single button for a number of frames. "
                "Valid buttons: a, b, up, down, left, right, start, select, l, r."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "button": {
                        "type": "string",
                        "enum": [
                            "a", "b", "up", "down", "left", "right",
                            "start", "select", "l", "r",
                        ],
                        "description": "Name of the button to press.",
                    },
                    "duration": {
                        "type": "integer",
                        "description": "Number of frames to hold the button (default: 30, ~0.5s at 60fps).",
                        "default": 30,
                    },
                },
                "required": ["button"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Advance the emulator by a number of frames without pressing any button.",
            "parameters": {
                "type": "object",
                "properties": {
                    "frames": {
                        "type": "integer",
                        "description": "Number of frames to wait (default: 60, ~1s at 60fps). Runs at max emulator speed.",
                        "default": 60,
                    },
                },
                "required": ["frames"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fast_forward",
            "description": (
                "Run many frames at maximum emulator speed (~12,000 FPS) "
                "to skip through animations, dialogue, or transitions. "
                "Use this to advance game time quickly without waiting for real-time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "frames": {
                        "type": "integer",
                        "description": "Number of frames to run (default: 180, ~3s at 60fps). Higher = more game progress per call.",
                        "default": 180,
                    },
                },
                "required": ["frames"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "combo",
            "description": (
                "Press multiple buttons simultaneously for a number of frames. "
                "Useful for diagonal movement (e.g. up+right) or A+B combos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "buttons": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of button names to press simultaneously.",
                    },
                    "duration": {
                        "type": "integer",
                        "description": "Number of frames to hold the combo (default: 30, ~0.5s at 60fps).",
                        "default": 30,
                    },
                },
                "required": ["buttons"],
            },
        },
    },
]

# ── Tool execution ───────────────────────────────────────────────────────────


def execute_tool_call(emulator: Any, tool_name: str, arguments: dict[str, Any]) -> str:
    """
    Execute a tool call against *emulator* and return a result string.

    Args:
        emulator: An :class:`Emulator` instance (or compatible object).
        tool_name: One of ``"press_button"``, ``"wait"``, ``"combo"``.
        arguments: Keyword arguments for the tool.

    Returns:
        A human‑readable result string, e.g.
        ``"Pressed a for 5 frames."`` or
        ``"Error: Unknown button 'x'."``.
    """
    try:
        if tool_name == "press_button":
            button = arguments["button"]
            duration = arguments.get("duration", 5)
            emulator.press_button(button, frames=duration)
            return f"Pressed {button} for {duration} frames."

        elif tool_name == "wait":
            frames = arguments["frames"]
            emulator.wait(frames)
            return f"Waited {frames} frames."

        elif tool_name == "fast_forward":
            frames = arguments["frames"]
            emulator.fast_forward(frames)
            return f"Fast-forwarded {frames} frames (~{frames/60:.1f}s game time)."

        elif tool_name == "combo":
            buttons = arguments["buttons"]
            duration = arguments.get("duration", 5)
            emulator.combo(buttons, frames=duration)
            return f"Pressed {buttons} simultaneously for {duration} frames."

        else:
            return f"Error: Unknown tool '{tool_name}'."

    except Exception as exc:
        return f"Error: {exc}"


# ── Response parsing ─────────────────────────────────────────────────────────

_TOOL_CALL_JSON_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL
)


def parse_tool_call(response_text: str) -> dict[str, Any] | None:
    """
    Extract a tool-call payload from a model response string.

    Handles three common formats:

    1.  **Code‑fenced JSON**::
            ```json
            {"name": "press_button", "arguments": {"button": "a"}}
            ```
    2.  **Bare JSON object** on its own line.
    3.  **OpenAI‑style ``tool_calls`` array** (first element is used).

    Returns:
        A dict with keys ``"name"`` and ``"arguments"``, or ``None`` if
        no valid tool call could be parsed.
    """
    text = response_text.strip()

    # --- OpenAI-style tool_calls array ---------------------------------------
    if '"tool_calls"' in text or "'tool_calls'" in text:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and "tool_calls" in data:
            calls = data["tool_calls"]
            if isinstance(calls, list) and calls:
                call = calls[0]
                if isinstance(call, dict):
                    func = call.get("function", call)
                    return {
                        "name": func.get("name", ""),
                        "arguments": func.get("arguments", {}),
                    }

    # --- Owl-alpha XML tool call format --------------------------------------
    # <longcat_tool_call>press_button<longcat_arg_key>button</longcat_arg_key>
    # <longcat_arg_value>a</longcat_arg_value></longcat_tool_call>
    xml_tool = re.search(
        r"<longcat_tool_call>(.*?)</longcat_tool_call>", text, re.DOTALL
    )
    if xml_tool:
        inner = xml_tool.group(1)
        # Extract tool name (first text before any longcat tag)
        tool_name = re.match(r"([^<]+)", inner)
        name = tool_name.group(1).strip() if tool_name else ""
        # Extract key-value pairs
        args: dict[str, Any] = {}
        for match in re.finditer(
            r"<longcat_arg_key>(.*?)</longcat_arg_key>\s*<longcat_arg_value>(.*?)</longcat_arg_value>",
            inner, re.DOTALL,
        ):
            k = match.group(1).strip()
            v = match.group(2).strip()
            # Try to parse int values
            try:
                v = int(v)
            except ValueError:
                pass
            args[k] = v
        if name:
            return {"name": name, "arguments": args}

    # --- Code-fenced JSON ----------------------------------------------------
    m = _TOOL_CALL_JSON_RE.search(text)
    if m:
        try:
            payload = json.loads(m.group(1))
            if isinstance(payload, dict) and "name" in payload:
                return {
                    "name": payload["name"],
                    "arguments": payload.get("arguments", payload.get("parameters", {})),
                }
        except json.JSONDecodeError:
            pass

    # --- Bare JSON -----------------------------------------------------------
    # Try extracting the first JSON object from the text.
    for candidate in _iter_json_objects(text):
        if isinstance(candidate, dict) and "name" in candidate:
            return {
                "name": candidate["name"],
                "arguments": candidate.get("arguments", candidate.get("parameters", {})),
            }

    return None


def _iter_json_objects(text: str) -> "Iterator[dict[str, Any]]":
    """Yield JSON objects found in *text*, attempting from each ``{``."""
    idx = 0
    while idx < len(text):
        brace = text.find("{", idx)
        if brace == -1:
            break
        for end in range(len(text), brace, -1):
            try:
                obj = json.loads(text[brace:end])
                if isinstance(obj, dict):
                    yield obj
                break
            except json.JSONDecodeError:
                continue
        idx = brace + 1
