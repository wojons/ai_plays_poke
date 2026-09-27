#!/usr/bin/env python3
"""ai-plays-poke game bridge: let a human+agent play the live game, cycle by cycle.

WHY THIS EXISTS
    The decision model sees a bounded text projection of a live RAM snapshot and
    answers with a button plan. To review its judgement from the inside, the
    operator needs the SAME text, not a paraphrase. This bridge boots one
    emulator, keeps it alive, and serves exactly the projection and observation
    the game loop builds:

        obs        = RAMReader.observe()                 (src/core/ram_reader.py:1604)
        projection = state_projection.build(obs, ...)    (src/core/state_projection.py:102)

    Same call, same mechanics list, same cross-cycle material, so what this
    prints is what the model was given.

ACCESS MODEL (deliberate)
    Off by default. Nothing autostarts it and it is not a Hermes plugin, so a
    session does not inherit it. It refuses to boot without a token file, binds
    loopback ONLY, and every request must carry the token. A session that has no
    token simply cannot talk to it. Enable per session, revoke by killing the
    process and deleting the token.

USAGE
    python3 scripts/game_bridge.py --token-file <path> [--port N] [--boot-state P]
    python3 scripts/play.py observe            # via the client
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

ROM = REPO / "data" / "rom" / "Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
FRAME_DIR = REPO / "play_frames"
BUTTONS = {"a", "b", "start", "select", "up", "down", "left", "right"}


class Game:
    """One persistent emulator + reader, the same objects the game loop uses."""

    def __init__(self, boot_state: str | None) -> None:
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader
        from src.core import state_projection

        self.state_projection = state_projection
        self.emu = Emulator(str(ROM))
        self.reader = RAMReader(self.emu, str(ROM))
        self.boot_state = boot_state
        if boot_state and boot_state != "skip":
            self.emu.load_state(str(boot_state))
            self.emu.tick(30)
        # cross-cycle material the game loop owns (kept so the text matches)
        self.goal = os.environ.get(
            "AIPP_PLAY_GOAL", "Explore and make progress; the operator is watching."
        )
        self.visited: dict[str, int] = {}
        self.events: list[str] = []
        self.last_action = ""
        self.last_changed: bool | None = None
        self.cycles = 0
        self.paused = False
        FRAME_DIR.mkdir(exist_ok=True)

    # ---- observation -------------------------------------------------
    def observe(self) -> dict:
        obs = self.reader.observe()
        proj = self.state_projection.build(
            obs,
            goal=self.goal,
            visited=self.visited,
            recent_events=self.events[-12:],
            last_action=self.last_action,
            last_action_changed_state=self.last_changed,
            mechanics=self.state_projection.DEFAULT_MECHANICS,
            extra_facts=None,
        )
        key = (
            f"{obs.get('map_id')}:{obs.get('player_tile_x')},{obs.get('player_tile_y')}"
        )
        self.visited[key] = self.visited.get(key, 0) + 1
        return {
            "ok": True,
            "cycle": self.cycles,
            "projection": proj,
            "map_name": obs.get("map_name"),
            "map_id": obs.get("map_id"),
            "screen": obs.get("result"),
            "player": [obs.get("player_tile_x"), obs.get("player_tile_y")],
            "facing": obs.get("player_facing"),
            "party": obs.get("party_count"),
            "species": obs.get("first_party_species"),
            "adjacent_walkability": obs.get("adjacent_walkability"),
            "visible_exits": obs.get("visible_exits"),
            "projection_chars": len(proj),
            "obs_keys": sorted(obs.keys()),
        }

    # ---- acting ------------------------------------------------------
    def press(self, buttons: list[str], frames: int = 5, settle: bool = True) -> dict:
        bad = [b for b in buttons if b.lower() not in BUTTONS]
        if bad:
            return {
                "ok": False,
                "error": f"unknown buttons {bad}; valid {sorted(BUTTONS)}",
            }
        if self.paused:
            return {"ok": False, "error": "paused — call resume first", "paused": True}
        before = (
            self.reader.current_map_name(),
            self.reader.player_tile_x(),
            self.reader.player_tile_y(),
        )
        settled: list[int] = []
        for b in buttons:
            self.emu.press_button(b.lower(), frames=frames)
            # Gen 1 walk steps take ~16 frames and the tile coordinate updates
            # part-way through the animation, so sampling immediately reports a
            # half-finished step: `state_changed` then lags one press behind and
            # a blocked direction can look like a move. Hold the sample until the
            # player stops moving, exactly as a human holds the d-pad. Found by
            # pressing DOWN (walkable) -> no change, then UP -> a downward move.
            if settle:
                waited = 0
                for _ in range(40):
                    self.emu.tick(2)
                    waited += 2
                    if not self.reader.is_moving():
                        break
            else:
                self.emu.tick(8)
                waited = 8
            settled.append(waited)
        after = (
            self.reader.current_map_name(),
            self.reader.player_tile_x(),
            self.reader.player_tile_y(),
        )
        self.cycles += len(buttons)
        self.last_action = "+".join(b.upper() for b in buttons)
        self.last_changed = after != before
        self.events.append(
            f"cycle {self.cycles}: pressed {self.last_action} -> moved={self.last_changed}"
        )
        out = self.observe()
        out["pressed"] = [b.upper() for b in buttons]
        out["state_changed"] = self.last_changed
        out["before"] = list(before)
        out["after"] = list(after)
        out["settled_frames"] = settled
        return out

    def step(self, n: int) -> dict:
        self.emu.tick(n)
        self.cycles += 1
        self.events.append(f"cycle {self.cycles}: waited {n} frames")
        return self.observe()

    def save(self, slot: str) -> dict:
        p = REPO / "play_states" / f"{slot}.state"
        p.parent.mkdir(exist_ok=True)
        self.emu.save_state(str(p))
        return {"ok": True, "saved": str(p), "bytes": p.stat().st_size}

    def load(self, slot: str) -> dict:
        p = REPO / "play_states" / f"{slot}.state"
        if not p.exists():
            return {"ok": False, "error": f"no such state {p}"}
        self.emu.load_state(str(p))
        self.emu.tick(20)
        return self.observe()

    def frame(self, label: str = "now") -> dict:
        from PIL import Image

        arr = self.emu.capture()
        p = FRAME_DIR / f"{label}.png"
        Image.fromarray(arr).save(p)
        return {"ok": True, "frame": str(p), "size": list(arr.shape[:2][::-1])}

    def pause(self) -> dict:
        self.paused = True
        return {"ok": True, "paused": True}

    def resume(self) -> dict:
        self.paused = False
        return {"ok": True, "paused": False}

    def list_saves(self) -> dict:
        d = REPO / "play_states"
        d.mkdir(exist_ok=True)
        items = []
        for p in sorted(d.glob("*.state")):
            st = p.stat()
            items.append(
                {
                    "slot": p.stem,
                    "bytes": st.st_size,
                    "modified": time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)
                    ),
                }
            )
        return {"ok": True, "count": len(items), "saves": items}

    def delete_save(self, slot: str) -> dict:
        p = REPO / "play_states" / f"{slot}.state"
        if not p.exists():
            return {"ok": False, "error": f"no such save {p}"}
        p.unlink()
        return {"ok": True, "deleted": str(p)}

    def reset(self) -> dict:
        """Cold boot: a fresh emulator with no state loaded, back to the title."""
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        try:
            self.emu.stop()
        except Exception:
            pass
        self.emu = Emulator(str(ROM))
        self.reader = RAMReader(self.emu, str(ROM))
        self.visited = {}
        self.events = []
        self.last_action = ""
        self.last_changed = None
        self.cycles = 0
        self.paused = False
        self.emu.tick(30)
        return {"ok": True, "cold_boot": True, "screen": self.reader.screen_type()}

    def health(self) -> dict:
        return {
            "ok": True,
            "rom": str(ROM),
            "boot_state": self.boot_state,
            "goal": self.goal,
            "cycles": self.cycles,
            "map": self.reader.current_map_name(),
        }


def serve(game: Game, token: str, port: int, log):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))  # loopback only, never 0.0.0.0
    srv.listen(16)
    log(
        f"listening on 127.0.0.1:{port} (loopback only); token required on every request"
    )
    while True:
        conn, _ = srv.accept()
        threading.Thread(
            target=handle, args=(conn, game, token, log), daemon=True
        ).start()


def handle(conn, game: Game, token: str, log):
    with conn:
        conn.settimeout(180)
        buf = b""
        try:
            while b"\n" not in buf:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
            line = buf.split(b"\n", 1)[0].decode()
            req = json.loads(line)
            if not secrets.compare_digest(str(req.get("token", "")), token):
                conn.sendall(
                    (json.dumps({"ok": False, "error": "unauthorized"}) + "\n").encode()
                )
                log("REJECTED unauthorized request")
                return
            cmd = req.get("cmd")
            if cmd == "health":
                rep = game.health()
            elif cmd == "observe":
                rep = game.observe()
            elif cmd == "press":
                rep = game.press(
                    req.get("buttons") or [],
                    int(req.get("frames", 5)),
                    bool(req.get("settle", True)),
                )
            elif cmd == "step":
                if game.paused:
                    rep = {
                        "ok": False,
                        "error": "paused — call resume first",
                        "paused": True,
                    }
                else:
                    rep = game.step(int(req.get("n", 30)))
            elif cmd == "save":
                rep = game.save(str(req.get("slot", "slot1")))
            elif cmd == "load":
                rep = game.load(str(req.get("slot", "slot1")))
            elif cmd == "frame":
                rep = game.frame(str(req.get("label", "now")))
            elif cmd == "pause":
                rep = game.pause()
            elif cmd == "resume":
                rep = game.resume()
            elif cmd == "list_saves":
                rep = game.list_saves()
            elif cmd == "delete_save":
                rep = game.delete_save(str(req.get("slot", "")))
            elif cmd == "reset":
                rep = game.reset()
            elif cmd == "goal":
                game.goal = str(req.get("text") or game.goal)
                rep = {"ok": True, "goal": game.goal}
            else:
                rep = {"ok": False, "error": f"unknown cmd {cmd!r}"}
        except Exception as e:  # noqa: BLE001 - a bridge must not die on one bad request
            rep = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        try:
            conn.sendall((json.dumps(rep) + "\n").encode())
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--token-file",
        required=True,
        help="file holding the per-session token; must exist and be 0600",
    )
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument(
        "--boot-state", default=str(REPO / "data" / "baselines" / "base-1_boot.state")
    )
    ap.add_argument("--log", default="/tmp/aipp_bridge.log")
    a = ap.parse_args()

    tf = Path(a.token_file)
    if not tf.exists():
        print(f"refusing to start: no token file at {tf}")
        return 2
    mode = tf.stat().st_mode & 0o777
    if mode & 0o077:
        print(
            f"refusing to start: {tf} mode {oct(mode)} is group/world readable (want 0600)"
        )
        return 2
    token = tf.read_text().strip()
    if len(token) < 24:
        print("refusing to start: token too short")
        return 2

    def log(m: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {m}"
        print(line, flush=True)
        with open(a.log, "a") as fh:
            fh.write(line + "\n")

    log(f"booting emulator, boot_state={a.boot_state}")
    game = Game(a.boot_state)
    log(
        f"ready: map={game.reader.current_map_name()} screen={game.reader.screen_type()}"
    )
    serve(game, token, a.port, log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
