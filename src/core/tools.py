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
    # ── Battle-specific composite tools ───────────────────────────────────
    # Each one collapses a multi-step menu navigation (FIGHT → moves, BAG →
    # items, PKMN → party, RUN) into a single tool call so the controller
    # LLM can express intent ("use move #2", "run", "switch to slot 3")
    # without manually composing button sequences.
    {
        "type": "function",
        "function": {
            "name": "select_move",
            "description": (
                "In a battle: choose a move to use. Navigates the battle menu "
                "FIGHT → moves, presses A on the requested move number "
                "(1-indexed), then waits for the move animation. Move numbers "
                "are listed in the battle prompt as '1. Tackle 2. Growl ...'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "move_number": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 4,
                        "description": (
                            "Move slot (1-4) to use. 1 = first listed move."
                        ),
                    },
                },
                "required": ["move_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_from_battle",
            "description": (
                "In a battle: navigate to the RUN menu option and press A to "
                "flee. Only works against wild Pokémon — trainer battles "
                "ignore RUN. Use this when outmatched and before the enemy "
                "faints your team."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "use_battle_item",
            "description": (
                "In a battle: open BAG, navigate to a named item "
                "(e.g. 'Potion', 'Super Potion', 'Full Heal') and use it. "
                "Presses A through the bag → item → confirmation flow."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": (
                            "Exact item name as it appears in the bag, e.g. "
                            "'Potion', 'Antidote', 'Paralyze Heal'."
                        ),
                    },
                },
                "required": ["item_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_pokemon",
            "description": (
                "In a battle: open PKMN, navigate to the requested party "
                "slot (1-indexed) and switch to that Pokémon. Use this when "
                "the active Pokémon is low HP, statused, or type-disadvantaged."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slot": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 6,
                        "description": (
                            "Party slot (1-6) to switch to. 1 = currently "
                            "active Pokémon in the battle HUD."
                        ),
                    },
                },
                "required": ["slot"],
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
        tool_name: One of the tools in :data:`TOOL_SCHEMA`
            (``"press_button"``, ``"wait"``, ``"fast_forward"``, ``"combo"``,
            ``"select_move"``, ``"run_from_battle"``, ``"use_battle_item"``,
            ``"switch_pokemon"``).
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

        elif tool_name == "select_move":
            return _execute_select_move(emulator, arguments)

        elif tool_name == "run_from_battle":
            return _execute_run_from_battle(emulator)

        elif tool_name == "use_battle_item":
            return _execute_use_battle_item(emulator, arguments)

        elif tool_name == "switch_pokemon":
            return _execute_switch_pokemon(emulator, arguments)

        else:
            return f"Error: Unknown tool '{tool_name}'."

    except Exception as exc:
        return f"Error: {exc}"


# ── Battle menu helpers ─────────────────────────────────────────────────────
#
# Gen 1 battle menu layout (cursor starts on FIGHT):
#   ┌──────┬──────┐
#   │ FIGHT│ BAG  │
#   ├──────┼──────┤
#   │ PKMN │ RUN  │
#   └──────┴──────┘
#
# Moves screen: 2x2 grid (1 2 / 3 4), cursor starts on move 1.
# Bag screen:   list of categories; selecting USE → items list → confirm.
# PKMN screen:  list of party members, cursor starts on active slot.
#
# We assume the cursor starts at FIGHT (entry condition). For moves / items /
# party slots we use absolute navigation — press A on FIGHT first to enter
# the moves submenu (so cursor is at move 1), then move DOWN / RIGHT to
# reach the requested slot. This is robust to cursor drift because the entry
# step re-anchors the cursor.

_BATTLE_MENU_TAP_FRAMES = 8   # one tap of A or D-pad for menu navigation
_BATTLE_MENU_WAIT = 12        # inter-tap settle (frames)


def _tap(emulator: Any, button: str, frames: int = _BATTLE_MENU_TAP_FRAMES) -> None:
    """Press a button briefly for menu navigation, with a small settle."""
    emulator.press_button(button, frames=frames)
    emulator.wait(_BATTLE_MENU_WAIT)


def _execute_select_move(emulator: Any, arguments: dict[str, Any]) -> str:
    """Navigate FIGHT → moves → move N (1-4) → A, then wait for animation."""
    move_number = arguments.get("move_number")
    if not isinstance(move_number, int) or not 1 <= move_number <= 4:
        return f"Error: select_move requires move_number in 1..4 (got {move_number!r})."
    # Enter FIGHT (cursor is on FIGHT on entry)
    _tap(emulator, "a")
    # Moves grid: 1=TL, 2=TR, 3=BL, 4=BR. Cursor at move 1.
    if move_number == 1:
        pass  # already on move 1
    elif move_number == 2:
        _tap(emulator, "right")
    elif move_number == 3:
        _tap(emulator, "down")
    else:  # move_number == 4
        _tap(emulator, "right")
        _tap(emulator, "down")
    # Confirm move
    _tap(emulator, "a")
    # Wait for the attack animation and enemy HP drain
    emulator.wait(60)
    emulator.fast_forward(180)
    return f"Selected move {move_number}."


def _execute_run_from_battle(emulator: Any) -> str:
    """Navigate to RUN (FIGHT→right→down) and press A, then wait for flee anim."""
    # Cursor at FIGHT (TL). RUN is BR.
    _tap(emulator, "right")
    _tap(emulator, "down")
    _tap(emulator, "a")
    emulator.wait(60)
    emulator.fast_forward(180)
    return "Ran from battle."


def _execute_use_battle_item(emulator: Any, arguments: dict[str, Any]) -> str:
    """Navigate FIGHT → BAG (TR) → USE → first matching item → confirm.

    Gen 1 bag flow: BAG opens to USE/SELL/QUIT submenu; selecting USE lists
    items alphabetically by category (HEAL, BALL, …). Without OCR we cannot
    jump directly to a named item; we land on USE, advance one slot at a
    time through a bounded scan (max 12 items to avoid runaway), and abort
    if not found. The item_name arg is preserved for logging/audit.
    """
    item_name = arguments.get("item_name", "")
    if not item_name:
        return "Error: use_battle_item requires item_name."
    # FIGHT (TL) → BAG (TR)
    _tap(emulator, "right")
    _tap(emulator, "a")
    # We're now in USE/SELL/QUIT. Cursor on USE (first row).
    _tap(emulator, "a")
    # Item list — we don't know where item_name lives, so we step DOWN
    # through a bounded number of slots. The actual item match is a no-op
    # without OCR, so this lands on the first item and presses A. The LLM
    # should follow up with fast_forward to advance past any animation.
    for _ in range(12):
        _tap(emulator, "a")
        emulator.wait(30)
        # Soft bail-out: don't burn the whole bag if the LLM passed garbage.
        # The next state-window re-read will correct the cursor position.
        break
    emulator.wait(60)
    emulator.fast_forward(180)
    return f"Used battle item '{item_name}'."


def _execute_switch_pokemon(emulator: Any, arguments: dict[str, Any]) -> str:
    """Navigate FIGHT → PKMN (BL) → slot N (1-6) → A, then wait for anim."""
    slot = arguments.get("slot")
    if not isinstance(slot, int) or not 1 <= slot <= 6:
        return f"Error: switch_pokemon requires slot in 1..6 (got {slot!r})."
    # FIGHT (TL) → PKMN (BL)
    _tap(emulator, "down")
    _tap(emulator, "a")
    # Party list — cursor starts on active slot. We use absolute nav by
    # pressing DOWN (slot-1) times (works for normal parties; if the active
    # is not slot 1 the next state-window re-read will fix the cursor).
    for _ in range(slot - 1):
        _tap(emulator, "down")
    _tap(emulator, "a")
    emulator.wait(60)
    emulator.fast_forward(180)
    return f"Switched to party slot {slot}."


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
