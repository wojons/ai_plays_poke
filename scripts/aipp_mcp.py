#!/usr/bin/env python3
"""MCP server: play Pokemon Blue as tool calls.

Exposes the live game as MCP tools over stdio, so an agent drives it with
tools, not shell commands:

    game_observe      the exact state text the decision model receives
    game_screenshot   a real IMAGE returned inline (not a file path to read)
    game_press        press buttons: UP/DOWN/LEFT/RIGHT/A/B/START/SELECT
    game_step         advance N frames (wait / let animations play)
    game_pause        freeze input so nothing advances while we plan
    game_resume       unfreeze
    game_save         write a named save
    game_load         load a named save
    game_list_saves   list saves with size and mtime
    game_delete_save  remove a save
    game_reset        cold-boot the ROM to the title screen (blank run)
    game_health       bridge status

It talks to the bridge daemon (scripts/game_bridge.py), which owns the emulator.
The bridge is loopback-only and token-authenticated, so this server needs the
same per-session token. If the token is absent the tools fail closed with a clear
message instead of silently doing nothing.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import sys
from pathlib import Path

PORT = int(os.environ.get("AIPP_BRIDGE_PORT", "8770"))
TOKEN_FILE = Path(
    os.environ.get(
        "AIPP_BRIDGE_TOKEN_FILE",
        str(Path.home() / ".hermes" / "aipp_bridge" / "session.token"),
    )
)
PROTOCOL_VERSION = "2024-11-05"


def bridge(req: dict) -> dict:
    if not TOKEN_FILE.exists():
        return {
            "ok": False,
            "error": f"bridge is off for this session (no token at {TOKEN_FILE})",
        }
    req["token"] = TOKEN_FILE.read_text().strip()
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=180)
    except OSError as e:
        return {"ok": False, "error": f"bridge not reachable on 127.0.0.1:{PORT}: {e}"}
    with s:
        s.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    loaded = json.loads(buf.split(b"\n", 1)[0].decode())
    if not isinstance(loaded, dict):
        return {"ok": False, "error": "bridge returned a non-object reply"}
    return loaded


BUTTONS = ["UP", "DOWN", "LEFT", "RIGHT", "A", "B", "START", "SELECT"]

TOOLS = [
    {
        "name": "game_observe",
        "description": "The current game state as the decision model receives it: map, player tile, "
        "facing, party, screen type, ROM collision truth for the next move, local "
        "collision map, visible exits, recent events and the goal text.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "game_screenshot",
        "description": "Capture the current screen and return it as an inline IMAGE so you can look at "
        "it directly. Use alongside game_observe: the text says what is walkable, the "
        "image shows why.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scale": {
                    "type": "integer",
                    "description": "nearest-neighbour upscale factor, default 3",
                    "default": 3,
                }
            },
        },
    },
    {
        "name": "game_press",
        "description": "Press one or more buttons in sequence, e.g. ['UP','UP','A']. Waits for each walk "
        "to finish before returning the new state, and reports whether the state changed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "buttons": {
                    "type": "array",
                    "items": {"type": "string", "enum": BUTTONS},
                },
                "settle": {
                    "type": "boolean",
                    "description": "wait for movement to finish (default true)",
                    "default": True,
                },
            },
            "required": ["buttons"],
        },
    },
    {
        "name": "game_step",
        "description": "Advance N frames without pressing anything (let an animation or text box play).",
        "inputSchema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "default": 60}},
            "required": ["n"],
        },
    },
    {
        "name": "game_pause",
        "description": "Freeze input so the game cannot advance while we stop and plan. Presses and "
        "steps are refused until game_resume.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "game_resume",
        "description": "Unfreeze after game_pause.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "game_save",
        "description": "Write an emulator save to a named slot.",
        "inputSchema": {
            "type": "object",
            "properties": {"slot": {"type": "string", "default": "slot1"}},
            "required": ["slot"],
        },
    },
    {
        "name": "game_load",
        "description": "Load a named emulator save.",
        "inputSchema": {
            "type": "object",
            "properties": {"slot": {"type": "string"}},
            "required": ["slot"],
        },
    },
    {
        "name": "game_list_saves",
        "description": "List the saves available to load, with size and modification time.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "game_delete_save",
        "description": "Delete a named save.",
        "inputSchema": {
            "type": "object",
            "properties": {"slot": {"type": "string"}},
            "required": ["slot"],
        },
    },
    {
        "name": "game_reset",
        "description": "Cold-boot the ROM with no save state: a blank run starting at the title "
        "screen. Clears the emulator back to power-on.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "game_health",
        "description": "Bridge status: ROM, boot state, cycles, current map.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def text(s: str) -> dict:
    return {"type": "text", "text": s}


def call_tool(name: str, args: dict) -> list[dict]:
    if name == "game_observe":
        r = bridge({"cmd": "observe"})
        if not r.get("ok"):
            return [text(f"error: {r.get('error')}")]
        lines = [
            f"MAP: {r.get('map_name')} (id {r.get('map_id')})   SCREEN: {r.get('screen')}   "
            f"TILE: {r.get('player')}   FACING: {r.get('facing')}",
            f"PARTY: {r.get('party')} ({r.get('species')})   cycle: {r.get('cycle')}",
            f"ADJACENT WALKABILITY: {r.get('adjacent_walkability')}",
            "",
            f"--- model's state text ({r.get('projection_chars')} chars) ---",
            r.get("projection", ""),
            "--- end ---",
        ]
        return [text("\n".join(lines))]
    if name == "game_screenshot":
        r = bridge({"cmd": "frame", "label": "mcp"})
        if not r.get("ok"):
            return [text(f"error: {r.get('error')}")]
        from PIL import Image

        im = Image.open(r["frame"]).convert("RGB")
        scale = max(1, int(args.get("scale", 3)))
        im = im.resize((im.width * scale, im.height * scale), Image.Resampling.NEAREST)
        out = Path(r["frame"]).with_name("mcp_scaled.png")
        im.save(out)
        data = base64.b64encode(out.read_bytes()).decode()
        return [
            text(
                f"screen {im.width}x{im.height} (nearest-neighbour x{scale}) from {r['frame']}"
            ),
            {"type": "image", "data": data, "mimeType": "image/png"},
        ]
    if name == "game_press":
        r = bridge(
            {
                "cmd": "press",
                "buttons": args.get("buttons", []),
                "settle": bool(args.get("settle", True)),
            }
        )
        if not r.get("ok"):
            return [text(f"error: {r.get('error')}")]
        return [
            text(
                f"pressed {' '.join(r.get('pressed', []))}   state_changed: {r.get('state_changed')}\n"
                f"  {r.get('before')} -> {r.get('after')}   settled: {r.get('settled_frames')}\n"
                f"  now at {r.get('map_name')} tile {r.get('player')} facing {r.get('facing')}"
            )
        ]
    if name == "game_step":
        r = bridge({"cmd": "step", "n": int(args.get("n", 60))})
        return [text(f"stepped. screen={r.get('screen')} tile={r.get('player')}")]
    if name in ("game_pause", "game_resume"):
        r = bridge({"cmd": name.split("_")[1]})
        return [
            text(f"{name.split('_')[1]}: ok={r.get('ok')} paused={r.get('paused')}")
        ]
    if name in ("game_save", "game_load"):
        r = bridge({"cmd": name.split("_")[1], "slot": args.get("slot", "slot1")})
        return [text(json.dumps(r))]
    if name == "game_list_saves":
        r = bridge({"cmd": "list_saves"})
        return [text(json.dumps(r, indent=2))]
    if name == "game_delete_save":
        r = bridge({"cmd": "delete_save", "slot": args.get("slot")})
        return [text(json.dumps(r))]
    if name == "game_reset":
        r = bridge({"cmd": "reset"})
        return [text(f"cold boot: {json.dumps(r)}")]
    if name == "game_health":
        return [text(json.dumps(bridge({"cmd": "health"}), indent=2))]
    return [text(f"unknown tool {name}")]


def reply(rid, result=None, error=None) -> None:
    msg = {"jsonrpc": "2.0", "id": rid}
    msg["error"] = error if error else None
    if error is None:
        msg["result"] = result
    else:
        msg.pop("result", None)
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method, rid = req.get("method"), req.get("id")
        if method == "initialize":
            reply(
                rid,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "aipp-game", "version": "1.0.0"},
                },
            )
        elif method in ("notifications/initialized", "initialized"):
            continue
        elif method == "tools/list":
            reply(rid, {"tools": TOOLS})
        elif method == "tools/call":
            p = req.get("params") or {}
            try:
                content = call_tool(p.get("name", ""), p.get("arguments") or {})
                reply(rid, {"content": content})
            except Exception as e:  # noqa: BLE001
                reply(
                    rid,
                    {
                        "content": [text(f"tool error: {type(e).__name__}: {e}")],
                        "isError": True,
                    },
                )
        elif method == "ping":
            reply(rid, {})
        else:
            reply(rid, error={"code": -32601, "message": f"method not found: {method}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
