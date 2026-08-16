#!/usr/bin/env python3
"""Live RAM Map Viewer server — serves the HTML page, live JSON data, and input.

Usage:
  ./venv/bin/python ram_map_server.py

Then open http://localhost:8099 in your browser.
The page auto-refreshes every second with live emulator state; the button
row (or POST /input) drives the emulator with button presses.
"""
from __future__ import annotations

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))
from src.core.emulator import Emulator
from src.core.ram_reader import RAMReader

ROM_PATH = Path(__file__).parent / "data" / "rom" / "pokemon_red.gb"

# Name-entry state addresses (mirrors src/core/ram_reader.py)
ADDR_NAMING_NAME_LENGTH = 0xCC48  # wNamingScreenNameLength
ADDR_SPRITE_STATE_DATA = 0xC100  # wSpriteStateData1 — non-zero in overworld

# Buttons accepted by POST /input (mirrors Emulator._BUTTON_EVENTS)
VALID_BUTTONS = frozenset(
    {"a", "b", "up", "down", "left", "right", "start", "select"}
)

# ── Global emulator state ──────────────────────────────────────────────

emu: Emulator | None = None
reader: RAMReader | None = None


def boot_emulator() -> tuple[Emulator, RAMReader]:
    """Boot the emulator and deterministically reach the overworld."""
    global emu, reader
    if emu is not None and reader is not None:
        return emu, reader

    emu = Emulator(str(ROM_PATH))
    reader = RAMReader(emu, ROM_PATH)

    # Boot
    for _ in range(60):
        emu.tick()
    emu.bypass_title()
    emu.skip_intro(repetitions=30)

    _advance_to_overworld(emu, reader)

    return emu, reader


def _advance_to_overworld(
    emu: Emulator, reader: RAMReader, max_cycles: int = 120
) -> None:
    """Progress from the name-entry screen(s) to a controllable overworld.

    ``bypass_title()`` + ``skip_intro()`` leave the game sitting on the
    new-game name-entry keyboard (verified 2026-08-16).  Gen 1 asks for the
    player's name and then the rival's name — two name-entry screens — with
    intro dialogs in between.  This loop drives through all of them:

      * ``name_entry`` with an empty name buffer → type a full name via
        ``enter_name("ASH")`` (cursor sits on the A key on a fresh screen);
      * ``name_entry`` with a non-empty buffer (skip_intro's A-mashing may
        have typed into it) → accept it via ``submit_name()``;
      * any other screen → A-mash to advance intro dialogs.

    Exits as soon as the RAM reader reports an overworld screen (which
    requires a live player sprite state), or raises after *max_cycles*.
    """
    name_entries = 0
    for _ in range(max_cycles):
        screen = reader.screen_type()
        if screen == "name_entry":
            if name_entries == 0 and emu.read_u8(ADDR_NAMING_NAME_LENGTH) == 0:
                emu.enter_name("ASH")
            else:
                emu.submit_name()
            name_entries += 1
        elif screen == "overworld" and emu.read_u8(ADDR_SPRITE_STATE_DATA) != 0:
            return
        else:
            emu.press_button("a", frames=20)
            emu.fast_forward(60)
    raise RuntimeError(
        f"Failed to reach overworld after {max_cycles} cycles "
        f"(last screen={reader.screen_type()}, name entries={name_entries})"
    )


def get_state() -> dict:
    """Read current emulator state and return JSON-serializable dict."""
    emu, reader = boot_emulator()

    mid = reader.current_map_id()
    info = reader._mapdb.get_map(mid)

    obs = reader.observe()
    adj = obs["adjacent"]

    # Build block_types array from block data
    block_types = []
    blocks = []
    if info:
        blocks = info["block_data"]
        tileset = info["tileset"]
        for b in blocks:
            block_types.append(reader._mapdb.classify_block(b, tileset))

    return {
        "map_name": reader.current_map_name(),
        "map_id": mid,
        "tileset": info["tileset"] if info else -1,
        "w": info["width"] if info else 0,
        "h": info["height"] if info else 0,
        "blocks": blocks,
        "block_types": block_types,
        "player_x": reader.player_x(),
        "player_y": reader.player_y(),
        "facing": reader.player_facing(),
        "moving": reader.is_moving(),
        "screen_type": reader.screen_type(),
        "adjacent": adj,
        "minimap": obs["minimap"],
    }


def handle_input(payload: dict) -> tuple[int, dict]:
    """Validate and apply a JSON input payload; returns (status_code, body).

    Accepts ``{"button": "a"}``, ``{"buttons": ["a", "start"]}`` or
    ``{"combo": [...]}``, optionally with ``{"frames": N}``.  Unknown
    buttons and malformed payloads return 400 without touching the
    emulator; exceptions from the emulator itself are also folded into a
    400 so the HTTP handler never crashes.
    """
    emu, reader = boot_emulator()

    if not isinstance(payload, dict):
        return 400, {"ok": False, "error": "payload must be a JSON object"}

    buttons = payload.get("buttons")
    if buttons is None:
        buttons = payload.get("combo")
    if buttons is None and isinstance(payload.get("button"), str):
        buttons = [payload["button"]]

    if not isinstance(buttons, list) or not buttons:
        return 400, {
            "ok": False,
            "error": 'expected {"button": "a"} or {"buttons": [...]} / {"combo": [...]}',
        }

    frames = payload.get("frames", 5)
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < 1:
        return 400, {"ok": False, "error": "frames must be a positive int"}

    normalized: list[str] = []
    for btn in buttons:
        if not isinstance(btn, str) or btn.lower() not in VALID_BUTTONS:
            return 400, {"ok": False, "error": f"unknown button: {btn!r}"}
        normalized.append(btn.lower())

    try:
        if len(normalized) == 1:
            emu.press_button(normalized[0], frames=frames)
        else:
            emu.combo(normalized, frames=frames)
    except Exception as exc:  # noqa: BLE001 — never crash the handler
        return 400, {"ok": False, "error": f"input failed: {exc}"}

    return 200, {
        "ok": True,
        "buttons": normalized,
        "frames": frames,
        "screen_type": reader.screen_type(),
        "map_name": reader.current_map_name(),
    }


# ── HTTP server ────────────────────────────────────────────────────────

HTML_PATH = Path(__file__).parent / "ram_map_viewer.html"
HTML_CONTENT = HTML_PATH.read_text()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/data.json":
            data = json.dumps(get_state(), indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode())
        elif self.path == "/" or self.path == "/index.html":
            # Inject live-data poll script into the HTML
            html = HTML_CONTENT.replace(
                "render(SAMPLE);",
                'fetch("/data.json").then(r=>r.json()).then(render).catch(()=>render(SAMPLE));'
                'setInterval(()=>fetch("/data.json").then(r=>r.json()).then(render),1000);'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/input":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length > 0 else b""
            payload = json.loads(raw.decode("utf-8")) if raw.strip() else {}
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        status, body = handle_input(payload)
        data = json.dumps(body, indent=2)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data.encode())

    def log_message(self, format, *args):
        pass  # quiet


def main():
    print("Booting emulator (this takes a few seconds)...")
    boot_emulator()
    state = get_state()
    print(f"  Map: {state['map_name']} ({state['w']}×{state['h']})")
    print(f"  Player: ({state['player_x']}, {state['player_y']}) facing {state['facing']}")
    print("  Screen: %s" % state["screen_type"])
    print("\n  Open http://localhost:8099 in your browser\n")

    server = HTTPServer(("0.0.0.0", 8099), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
