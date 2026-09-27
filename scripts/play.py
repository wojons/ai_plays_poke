#!/usr/bin/env python3
"""Client for the ai-plays-poke game bridge.

Reads the session token from $AIPP_BRIDGE_TOKEN_FILE (or --token-file), sends one
command, and prints the state in a form an agent can read directly.

    python3 scripts/play.py observe
    python3 scripts/play.py press UP UP UP
    python3 scripts/play.py step 30
    python3 scripts/play.py frame step007
    python3 scripts/play.py save checkpoint1
    python3 scripts/play.py load checkpoint1
    python3 scripts/play.py goal "walk north out of Pallet Town"
    python3 scripts/play.py health

The bridge is loopback-only and every request carries the session token, so this
works only while a bridge is running for THIS session and this process can read
the token file.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

DEFAULT_TOKEN_FILE = Path.home() / ".hermes" / "aipp_bridge" / "session.token"
PORT = int(os.environ.get("AIPP_BRIDGE_PORT", "8770"))


def call(req: dict) -> dict:
    tf = Path(os.environ.get("AIPP_BRIDGE_TOKEN_FILE", str(DEFAULT_TOKEN_FILE)))
    if not tf.exists():
        return {
            "ok": False,
            "error": f"no session token at {tf} — the bridge is off for this session",
        }
    req["token"] = tf.read_text().strip()
    s = socket.create_connection(("127.0.0.1", PORT), timeout=180)
    with s:
        s.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    raw = buf.split(b"\n", 1)[0].decode()
    loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        return {"ok": False, "error": "bridge returned a non-object reply"}
    return loaded


def render(r: dict) -> str:
    if not r.get("ok"):
        return f"ERROR: {r.get('error')}"
    out = []
    if "map_name" in r:
        out.append(
            f"MAP: {r.get('map_name')} (id {r.get('map_id')})   "
            f"SCREEN: {r.get('screen')}   TILE: {r.get('player')}   FACING: {r.get('facing')}"
        )
        out.append(
            f"PARTY: {r.get('party')} ({r.get('species')})   cycle: {r.get('cycle')}"
        )
        if "pressed" in r:
            out.append(
                f"PRESSED: {' '.join(r['pressed'])}   state_changed: {r.get('state_changed')}"
            )
            out.append(f"  before {r.get('before')} -> after {r.get('after')}")
            if r.get("settled_frames"):
                out.append(
                    f"  settled after {r['settled_frames']} frames (waiting for the walk to finish)"
                )
        adj = r.get("adjacent_walkability")
        if adj:
            out.append(f"ADJACENT WALKABILITY: {adj}")
        ex = r.get("visible_exits")
        if ex:
            out.append(f"VISIBLE EXITS: {ex}")
        if r.get("projection"):
            out.append("")
            out.append(
                f"--- what the model sees ({r.get('projection_chars')} chars) ---"
            )
            out.append(r["projection"])
            out.append("--- end projection ---")
    if "frame" in r:
        out.append(f"FRAME: {r['frame']}")
    if "saved" in r:
        out.append(f"SAVED: {r['saved']} ({r['bytes']} bytes)")
    if "goal" in r:
        out.append(f"GOAL: {r['goal']}")
    if r.get("rom"):
        out.append(
            f"BRIDGE UP · rom={r['rom']} boot={r.get('boot_state')} "
            f"cycles={r.get('cycles')} map={r.get('map')}"
        )
    if r.get("paused") is not None and not out:
        out.append(f"paused: {r['paused']}")
    if not out:
        out.append(json.dumps(r, indent=2))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "cmd",
        choices=[
            "observe",
            "press",
            "step",
            "frame",
            "save",
            "load",
            "goal",
            "health",
            "pause",
            "resume",
            "list_saves",
            "delete_save",
            "reset",
        ],
    )
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    req: dict[str, Any] = {}
    if a.cmd == "press":
        req = {"cmd": "press", "buttons": [x.upper() for x in a.args]}
    elif a.cmd == "step":
        req = {"cmd": "step", "n": int(a.args[0]) if a.args else 30}
    elif a.cmd == "frame":
        req = {"cmd": "frame", "label": a.args[0] if a.args else "now"}
    elif a.cmd in ("save", "load"):
        req = {"cmd": a.cmd, "slot": a.args[0] if a.args else "slot1"}
    elif a.cmd == "delete_save":
        req = {"cmd": "delete_save", "slot": a.args[0] if a.args else ""}
    elif a.cmd == "goal":
        req = {"cmd": "goal", "text": " ".join(a.args)}
    else:
        req = {"cmd": a.cmd}
    print(render(call(req)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
