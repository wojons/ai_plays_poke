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
import queue
import secrets
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.core.ram_reader import RAMReader

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

ROM = REPO / "data" / "rom" / "Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
FRAME_DIR = REPO / "play_frames"
BUTTONS = {"a", "b", "start", "select", "up", "down", "left", "right"}
DEFAULT_MAX_WORKERS = 4
DEFAULT_REQUEST_TIMEOUT = 30.0
MAX_REQUEST_BYTES = 1024 * 1024
SHUTDOWN_JOIN_TIMEOUT = 5.0


def _safe_grid(reader: RAMReader, cols: int = 10, rows: int = 9) -> str:
    """The reader's display grid, or an empty string rather than an exception.

    observe() is the bridge's hot path. A tile or graphics lookup problem must not take the whole
    observation down and leave the console with nothing to show.
    """
    try:
        return reader.render_tile_grid(cols, rows)
    except Exception:  # noqa: BLE001
        return ""


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
        self.visited: dict[tuple[int, int], int] = {}
        self._visited_map_id: int | None = None
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
        # The projection renders visited tiles as ``tuple(tile)``, so the key
        # must be an (x, y) tuple — a joined string key gets iterated into
        # characters. Reset on a map change so counts are per-map, not merged.
        mid = obs.get("map_id")
        if mid != self._visited_map_id:
            self.visited = {}
            self._visited_map_id = mid
        ptx, pty = obs.get("player_tile_x"), obs.get("player_tile_y")
        if isinstance(ptx, int) and isinstance(pty, int):
            self.visited[(ptx, pty)] = self.visited.get((ptx, pty), 0) + 1
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
            # The reader's own display grid at the geometry the SCREEN actually is: 160x144 px at
            # 16 px per game cell = 10 wide by 9 tall, anchored on the player's measured pixel box
            # (the player sits at column 4, not 5 - the midpoint falls between cells on an even
            # width). render_tile_grid has existed for a while but nothing called it, so the console
            # was re-deriving a 5x5 window out of the projection text instead - which meant the RAM
            # panel and the vision grid were describing different windows and every cell comparison
            # was meaningless. Guards stay on: a grid failure must not take observe() down.
            "grid": _safe_grid(self.reader),
            "grid_cols": 10,
            "grid_rows": 9,
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

    def raw(self) -> dict:
        """The full observation dict, unfiltered — so nothing available is hidden.

        Also carries the reader's display grid at the screen's true geometry: 160x144 px at 16 px
        per cell = 10 wide by 9 tall. ``overworld_grid`` INSIDE the observation is a narrower 5x5
        window, and that is what the console was drawing - a RAM panel 5 cells wide sitting next to
        a vision grid asked to describe the whole screen, so the two described different windows and
        every cell of the comparison was against the wrong cell.
        """
        return {
            "ok": True,
            "obs": self.reader.observe(),
            "grid": _safe_grid(self.reader),
            "grid_cols": 10,
            "grid_rows": 9,
        }

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


def _dispatch(req: dict, game: Game) -> dict:
    """Dispatch exactly one authenticated request while the caller owns the Game lock."""
    cmd = req.get("cmd")
    if cmd == "health":
        return game.health()
    if cmd == "observe":
        return game.observe()
    if cmd == "press":
        return game.press(
            req.get("buttons") or [],
            int(req.get("frames", 5)),
            bool(req.get("settle", True)),
        )
    if cmd == "step":
        if game.paused:
            return {
                "ok": False,
                "error": "paused — call resume first",
                "paused": True,
            }
        return game.step(int(req.get("n", 30)))
    if cmd == "save":
        return game.save(str(req.get("slot", "slot1")))
    if cmd == "load":
        return game.load(str(req.get("slot", "slot1")))
    if cmd == "frame":
        return game.frame(str(req.get("label", "now")))
    if cmd == "raw":
        return game.raw()
    if cmd == "pause":
        return game.pause()
    if cmd == "resume":
        return game.resume()
    if cmd == "list_saves":
        return game.list_saves()
    if cmd == "delete_save":
        return game.delete_save(str(req.get("slot", "")))
    if cmd == "reset":
        return game.reset()
    if cmd == "goal":
        game.goal = str(req.get("text") or game.goal)
        return {"ok": True, "goal": game.goal}
    return {"ok": False, "error": f"unknown cmd {cmd!r}"}


def _send_json(conn: socket.socket, payload: dict) -> None:
    conn.sendall((json.dumps(payload) + "\n").encode())


def handle(
    conn: socket.socket,
    game: Game,
    token: str,
    log: Callable[[str], None],
    *,
    game_lock: threading.Lock | None = None,
    stop_event: threading.Event | None = None,
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
) -> None:
    """Read and answer one line-delimited request, then close the connection.

    Socket parsing may happen on several fixed workers, but every Game operation is
    serialized. PyBoy, RAMReader, and the bridge's cross-cycle state are one mutable
    unit and are not safe to enter concurrently.
    """
    stop = stop_event or threading.Event()
    with conn:
        conn.settimeout(request_timeout)
        buf = b""
        try:
            while b"\n" not in buf:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
                if len(buf) > MAX_REQUEST_BYTES:
                    raise ValueError(f"request exceeds {MAX_REQUEST_BYTES} bytes")
            line = buf.split(b"\n", 1)[0].decode()
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("request must be a JSON object")
            if not secrets.compare_digest(str(req.get("token", "")), token):
                _send_json(conn, {"ok": False, "error": "unauthorized"})
                log("REJECTED unauthorized request")
                return

            acquired = False
            lock = game_lock or threading.Lock()
            while not stop.is_set():
                acquired = lock.acquire(timeout=0.1)
                if acquired:
                    break
            if not acquired:
                rep = {"ok": False, "error": "server shutting down"}
            else:
                try:
                    rep = _dispatch(req, game)
                finally:
                    lock.release()
        except Exception as e:  # noqa: BLE001 - a bridge must not die on one bad request
            rep = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        try:
            _send_json(conn, rep)
        except Exception:
            pass


def serve(
    game: Game,
    token: str,
    port: int,
    log: Callable[[str], None],
    *,
    max_workers: int = DEFAULT_MAX_WORKERS,
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
    stop_event: threading.Event | None = None,
    on_ready: Callable[[int], None] | None = None,
) -> None:
    """Serve with a fixed worker set and a bounded pending-connection queue.

    The incident path was the console's ``GET /api/stream`` loop, which repeatedly
    opens line-delimited ``{"cmd": "raw"}`` connections. When one Game call stopped
    completing, console retries reached this accept loop and the old implementation
    created one more daemon thread for every retry. The fixed workers below make the
    connection/thread boundary explicit and the shared ``game_lock`` keeps all Game
    access serial.
    """
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")
    if request_timeout <= 0:
        raise ValueError("request_timeout must be positive")

    stop = stop_event or threading.Event()
    pending: queue.Queue[socket.socket] = queue.Queue(maxsize=max_workers)
    game_lock = threading.Lock()
    active_lock = threading.Lock()
    active: set[socket.socket] = set()
    instance = f"{id(stop):x}"

    def worker() -> None:
        while True:
            try:
                conn = pending.get(timeout=0.1)
            except queue.Empty:
                if stop.is_set():
                    return
                continue
            try:
                if stop.is_set():
                    conn.close()
                    continue
                with active_lock:
                    active.add(conn)
                try:
                    handle(
                        conn,
                        game,
                        token,
                        log,
                        game_lock=game_lock,
                        stop_event=stop,
                        request_timeout=request_timeout,
                    )
                finally:
                    with active_lock:
                        active.discard(conn)
            finally:
                pending.task_done()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))  # loopback only, never 0.0.0.0
    srv.listen(max_workers)
    srv.settimeout(0.2)
    workers = [
        threading.Thread(
            target=worker,
            name=f"aipp-bridge-worker-{instance}-{index}",
            daemon=True,
        )
        for index in range(max_workers)
    ]
    for thread in workers:
        thread.start()

    bound_port = int(srv.getsockname()[1])
    log(
        f"listening on 127.0.0.1:{bound_port} (loopback only); token required; "
        f"workers={max_workers}; pending={max_workers}"
    )
    if on_ready is not None:
        on_ready(bound_port)

    try:
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                if stop.is_set():
                    break
                raise
            try:
                pending.put_nowait(conn)
            except queue.Full:
                try:
                    conn.settimeout(1.0)
                    _send_json(conn, {"ok": False, "error": "server busy"})
                except OSError:
                    pass
                finally:
                    conn.close()
    finally:
        stop.set()
        srv.close()

        while True:
            try:
                queued = pending.get_nowait()
            except queue.Empty:
                break
            queued.close()
            pending.task_done()

        with active_lock:
            open_connections = list(active)
        for conn in open_connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()

        deadline = time.monotonic() + SHUTDOWN_JOIN_TIMEOUT
        for thread in workers:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        still_running = [thread.name for thread in workers if thread.is_alive()]
        if still_running:
            log(f"shutdown timed out waiting for workers: {still_running}")
        else:
            log("shutdown complete; all bridge workers joined")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--token-file",
        required=True,
        help="file holding the per-session token; must exist and be 0600",
    )
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="fixed bridge worker-thread ceiling (pending queue has the same bound)",
    )
    ap.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT,
        help="seconds allowed to receive one newline-terminated request",
    )
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

    stop = threading.Event()

    def request_stop(signum: int, _frame: object) -> None:
        log(f"shutdown requested by signal {signum}")
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        serve(
            game,
            token,
            a.port,
            log,
            max_workers=a.max_workers,
            request_timeout=a.request_timeout,
            stop_event=stop,
        )
    finally:
        try:
            game.emu.stop()
        except Exception as e:  # noqa: BLE001 - shutdown remains best-effort
            log(f"emulator shutdown warning: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
