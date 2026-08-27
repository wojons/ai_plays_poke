#!/usr/bin/env python3
"""Cron-friendly Pokemon AI runner with RAM reader / cartographer → controller pipeline.

Flow:
  1. Observe game state (RAM reader OR Gemma 12B cartographer)
  2. If overworld: controller (openai/gpt-5.6-luna via OpenRouter) reads spatial data → button plan
  3. Execute plan with direction-locking detection, checkpoint rollback
  4. Non-overworld: existing StateWindow flow
"""
import builtins as _builtins
_original_print = _builtins.print
def safe_print(*args, **kwargs):
    """Print that survives broken stdout (piped background processes)."""
    try:
        _original_print(*args, **kwargs)
    except (BrokenPipeError, OSError):
        pass

import argparse
from dataclasses import dataclass
from typing import Any, cast
import sys
import os
import time
import json
import traceback
import base64
import io
import threading
from pathlib import Path
from datetime import datetime

# ── Config constants (early) ─────────────────────────────────────────
# Defined before the heavy third-party imports (yaml/numpy/PIL/src.*) so
# the --dry-run precheck below can validate setup under bare python3 too.
ROM = "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
DEFAULT_BOOT_STATE = Path("data/boot.state")  # known-good overworld checkpoint
CYCLES = 200
USE_RAM_READER = True   # True = RAM-based state reader (instant, free), False = Gemma 12B cartographer

# ── --dry-run precheck (GAP-032) ────────────────────────────────────
# Lightweight argparse pass that runs BEFORE yaml/numpy/PIL/src.* are
# imported, so `--dry-run` validates setup without booting the emulator
# or spending LLM calls — even under bare python3 (stdlib only).


def _load_dotenv_stdlib(env_path: Path | None = None) -> None:
    """Minimal stdlib .env loader (mirrors src/core/ai_client.py's fallback).

    Lets --dry-run report API-key presence from the real setup without
    importing python-dotenv or any project package.
    """
    path = env_path if env_path is not None else Path(".env")
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and value and not os.environ.get(key):
            os.environ[key] = value


def _dry_run_summary(
    run_id_arg: str | None,
    cycles: int,
    boot_state_arg: str | None,
    rom_arg: str | None = None,
) -> int:
    """Validate ROM/boot-state paths and print the pipeline config summary.

    Shared by the early precheck (import time, before heavy imports) and
    main() (defensive — the precheck normally exits first). Returns 0
    when the setup validates; 1 when the ROM is missing (a real run
    would crash at boot). Never boots the emulator and never makes an
    LLM/API call.
    """
    _load_dotenv_stdlib()
    rom = rom_arg if rom_arg is not None else ROM  # resolved ROM (GAP-033 --rom)
    rom_ok = Path(rom).is_file()
    if boot_state_arg is None:
        boot_path = DEFAULT_BOOT_STATE
    elif boot_state_arg.lower() == "skip":
        boot_path = None
    else:
        boot_path = Path(boot_state_arg)
    safe_print("[DRY-RUN] cron_runner.py — setup validation "
               "(no emulator boot, no LLM/API calls)")
    safe_print(f"  ROM path:       {rom}  [{'OK' if rom_ok else 'MISSING'}]")
    if boot_path is None:
        safe_print("  Boot state:     skip (legacy intro bypass)")
    else:
        boot_ok = boot_path.is_file()
        fallback = ("will boot from checkpoint" if boot_ok
                    else "missing — will fall back to intro bypass")
        safe_print(f"  Boot state:     {boot_path}  "
                   f"[{'OK' if boot_ok else 'MISSING — fallback'}] ({fallback})")
    safe_print(f"  Cycles:         {cycles}")
    safe_print(f"  Run ID:         {run_id_arg or time.strftime('%Y%m%d_%H%M%S')}")
    safe_print(f"  Pipeline:       {'RAM reader' if USE_RAM_READER else 'cartographer'} "
               f"(USE_RAM_READER={USE_RAM_READER!r})")
    safe_print("  Model/provider: controller=openai/gpt-5.6-luna (OpenRouter) · "
               "state_window=deepseek-v4-flash (api.deepseek.com when DEEPSEEK_API_KEY "
               "set, else OpenRouter) · cartographer=google/gemma-3-12b-it (only when "
               "USE_RAM_READER=False)")
    key_states = " · ".join(
        f"{k}={'set' if os.environ.get(k) else 'not set'}"
        for k in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
    )
    safe_print(f"  API keys:       {key_states}")
    if not rom_ok:
        safe_print(f"[DRY-RUN] ERROR: ROM not found at {rom} — a real run would crash at boot.")
        return 1
    safe_print("[DRY-RUN] Validation OK — exiting 0.")
    return 0


def _dry_run_precheck(argv: list[str] | None = None) -> None:
    """Handle --dry-run at import time, before heavy third-party imports.

    Lightweight argparse pass that only knows the flags --dry-run needs.
    Exits 0 (or 1 on a missing ROM) when --dry-run is present; otherwise
    returns and normal execution proceeds. Malformed values are left for
    the real parser in main() to report.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--cycles", type=int, default=CYCLES)
    parser.add_argument("--boot-state", default=None)
    parser.add_argument("--rom", default=None)
    try:
        args, _ = parser.parse_known_args(argv)
    except SystemExit:
        return
    if not args.dry_run:
        return
    sys.exit(_dry_run_summary(args.run_id, args.cycles, args.boot_state, args.rom))


_dry_run_precheck()

import yaml
import numpy as np
from PIL import Image

# ── Suppress emulator SGB warnings ──────────────────────────────────
# mGBA core prints "GB: Unimplemented SGB command: 0F" to stderr when
# running SGB-enhanced ROMs. These are harmless noise in cron runs.
class _SGBSuppress:
    """Context manager that filters SGB warnings from stderr.

    GAMEPLAY-LEAK-001 fix: the original implementation (a) wrote non-SGB
    lines back through the ``sys.stderr`` file object, whose fd was
    already dup2'd to this class's own pipe — so filtered lines re-entered
    the pipe and looped forever, growing an unbounded ``_buf`` at
    70-100 MB/s; and (b) split lines at 4096-byte read boundaries, so
    truncated ``Unimplemented SGB`` lines bypassed the filter and fed the
    loop. Now: writes go to the dup'd original stderr fd (no loop),
    partial lines are carried across reads (no bypass), and ``_buf`` is a
    bounded debug tail.
    """

    _MAX_BUF_LINES = 200

    def __init__(self) -> None:
        # These get set in __enter__
        self._real_stderr = sys.stderr
        self._real_stderr_fd = -1
        self._pipe_r = -1
        self._pipe_w = -1
        self._thread: threading.Thread | None = None
        self._buf: list[str] = []

    def __enter__(self) -> '_SGBSuppress':
        self._pipe_r, self._pipe_w = os.pipe()
        self._real_stderr_fd = os.dup(2)
        os.dup2(self._pipe_w, 2)
        os.close(self._pipe_w)
        self._buf = []

        def _filter() -> None:
            pending = ""  # incomplete line carried across read boundaries
            while True:
                data = os.read(self._pipe_r, 4096)
                if not data:
                    break
                pending += data.decode(errors="replace")
                lines = pending.split("\n")
                pending = lines.pop()  # last element is an incomplete tail
                for line in lines:
                    if not line or "Unimplemented SGB" in line:
                        continue  # drop SGB noise (even truncated fragments)
                    if len(self._buf) < self._MAX_BUF_LINES:
                        self._buf.append(line)
                    # Write to the dup'd ORIGINAL stderr fd, never fd 2
                    # (fd 2 is this class's own pipe — writing there would
                    # feed the feedback loop).
                    try:
                        os.write(
                            self._real_stderr_fd,
                            line.encode(errors="replace") + b"\n",
                        )
                    except OSError:
                        pass

        self._thread = threading.Thread(target=_filter, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        os.dup2(self._real_stderr_fd, 2)
        os.close(self._real_stderr_fd)
        if self._pipe_r:
            os.close(self._pipe_r)
        # thread is daemon — will exit on its own

sys.path.insert(0, str(Path(__file__).parent))
# ruff: noqa: E402 — sys.path must be modified before project imports
from src.core.emulator import Emulator
from src.core.global_context import GlobalContext
from src.core.state_window import StateWindow
from src.core.ai_client import OpenRouterClient
from src.core.prompt_loader import load_system_prompt
from src.core.ram_reader import RAMReader
from src.core.frame_cache import FrameCache
from src.core.tools import execute_tool_call

# ── Config ──────────────────────────────────────────────────────────
# ROM / DEFAULT_BOOT_STATE / CYCLES / USE_RAM_READER are defined at the
# top of the file (before the heavy imports) so the --dry-run precheck
# (GAP-032) can validate setup under bare python3.
STATE_STEPS = 12
USE_VISION_CLIENT = False  # True = debug mode (cheap classifier), False = Gemma 12B cartographer
HINT_LEVEL = 4  # 0=benchmark, 1=mechanics, 2=genre, 3=starter, 4=navigation
FAST_FORWARD_FRAMES = 600  # ~10s game time, ~50ms wall time
CART_STEPS = 6  # controller steps per overworld cycle (reduced from 12 — short moves, more cartographer feedback)
PRESS_FRAMES = 5  # one deliberate D-pad/button press (roughly one tile)
STEP_FORWARD = 15  # settle without triggering D-pad key repeat
LOG_DIR = Path("cron_logs")
LOG_DIR.mkdir(exist_ok=True)
run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = LOG_DIR / f"run_{run_id}.jsonl"
SCREENSHOT_DIR = Path("screenshots") / f"run_{run_id}"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ── Debug: optional VisionClient (cheap classifier, disabled by default) ──
if USE_VISION_CLIENT:
    from src.core.vision import VisionClient  # noqa: E402

# ── Checkpointing ───────────────────────────────────────────────────
CHECKPOINT_INTERVAL = 10   # save state every N cycles
CHECKPOINT_SLOTS = 5       # rotating slots 0-4
MAX_SAME_DIRECTION = 5     # blocked-direction threshold before rollback (legacy)

# ── Recovery (STUCK-RECOVER) ──────────────────────────────────────
MAX_RECOVERY_ATTEMPTS = 5     # total recovery escalations before giving up
MAX_SAME_SCREEN_CYCLES = 5    # same screen for N cycles → stuck
MAX_SAME_TILE_CYCLES = 8      # same RAM tile across any screen types → stuck
MAX_VOID_CYCLES = 3           # >95% unknown-tile cycles → void
MAX_STUCK_SAME_DIR = 4        # same direction N times → direction-locked
OAKS_LAB_MAP_ID = 40
STARTER_ACTION_FRAMES = 20
STARTER_ADVANCE_FRAMES = 120
# Opposite direction map for step-back recovery
_OPPOSITE_DIR = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}
# Direction rotation map for alternate-direction recovery (90° clockwise)
_DIR_ROTATION = {"UP": "RIGHT", "RIGHT": "DOWN", "DOWN": "LEFT", "LEFT": "UP"}

# ── Load visual-reference cartographer prompt (only if not using RAM reader) ──
if not USE_RAM_READER:
    _carto_cfg = yaml.safe_load(
        Path("configs/prompts/gen1/cartographer.yaml").read_text()
    )
    CARTOGRAPHER_SYSTEM = _carto_cfg["system"]
    CARTOGRAPHER_TEMPLATE = _carto_cfg["user_template"]

    # ── Load reference image (bedroom overworld — shows walls, doors, stairs, character) ──
    _ref_img = Image.open("reference/bedroom_overworld.png")
    _ref_buf = io.BytesIO()
    _ref_img.save(_ref_buf, format="PNG")
    REFERENCE_IMAGE_B64 = base64.b64encode(_ref_buf.getvalue()).decode()
else:
    CARTOGRAPHER_SYSTEM = ""
    CARTOGRAPHER_TEMPLATE = ""
    REFERENCE_IMAGE_B64 = ""

# ── Helpers ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _RecoveryTrackers:
    same_dir: str | None
    same_dir_count: int
    same_screen_count: int
    same_tile_count: int
    void_cycles: int
    a_press_count: int


def _reset_recovery_trackers(
    recovery_reason: str,
    *,
    same_dir: str | None,
    same_dir_count: int,
    same_screen_count: int,
    same_tile_count: int,
    void_cycles: int,
    a_press_count: int,
) -> _RecoveryTrackers:
    """Clear the tracker that fired, including A presses after any recovery."""
    if "direction-locked" in recovery_reason:
        same_dir = None
        same_dir_count = 0
    elif "screen-locked" in recovery_reason:
        same_screen_count = 0
    elif "tile-locked" in recovery_reason:
        same_tile_count = 0
    elif "void-locked" in recovery_reason:
        void_cycles = 0

    return _RecoveryTrackers(
        same_dir=same_dir,
        same_dir_count=same_dir_count,
        same_screen_count=same_screen_count,
        same_tile_count=same_tile_count,
        void_cycles=void_cycles,
        a_press_count=0,
    )


def _track_same_tile(
    current_tile: tuple[int, int, int] | None,
    last_tile: tuple[int, int, int] | None,
    same_tile_count: int,
) -> tuple[tuple[int, int, int] | None, int]:
    """Track a RAM map/tile tuple without considering the screen type."""
    if current_tile is None:
        return None, 0
    if current_tile == last_tile:
        return current_tile, same_tile_count + 1
    return current_tile, 1


def _tile_lock_reason(
    tile: tuple[int, int, int] | None, same_tile_count: int
) -> str:
    """Return the recovery reason for a tile streak at the configured limit."""
    if tile is None or same_tile_count < MAX_SAME_TILE_CYCLES:
        return ""
    map_id, tile_x, tile_y = tile
    return (
        f"tile-locked (map {map_id} @ ({tile_x},{tile_y}) "
        f"x{same_tile_count} cycles)"
    )


def _should_select_starter(
    *,
    map_id: int,
    party_count: int,
    screen_type: str,
    menu_state: dict[str, Any],
) -> bool:
    """Return whether Oak's empty-party starter menu must bypass the LLM."""
    menu_detected = (
        int(menu_state.get("menu_id", 0)) > 0
        or screen_type in ("menu", "list_menu")
    )
    return (
        map_id == OAKS_LAB_MAP_ID
        and party_count == 0
        and menu_detected
    )


def _approach_first_starter(
    emu: Any,
    ram_reader: RAMReader,
    *,
    max_dialog_advances: int = 12,
) -> bool:
    """Leave Oak's tile loop and interact with the nearest starter ball."""
    # A just-triggered interaction can still look like overworld for a few
    # frames; settle before deciding whether movement is controllable.
    emu.fast_forward(STARTER_ADVANCE_FRAMES)
    screen_type = ram_reader.screen_type()
    if screen_type != "overworld":
        for _ in range(max_dialog_advances):
            emu.press_button("a", frames=STARTER_ACTION_FRAMES)
            emu.fast_forward(STARTER_ADVANCE_FRAMES)
            screen_type = ram_reader.screen_type()
            if screen_type == "overworld":
                break
    if screen_type != "overworld":
        return False

    tile_x = ram_reader.player_tile_x()
    tile_y = ram_reader.player_tile_y()
    moves: list[str] = []
    moves.extend(["down"] * max(0, 4 - tile_y))
    moves.extend(["up"] * max(0, tile_y - 4))
    moves.extend(["right"] * max(0, 6 - tile_x))
    moves.extend(["left"] * max(0, tile_x - 6))
    if len(moves) > 12:
        return False

    for button in moves:
        emu.press_button(button, frames=PRESS_FRAMES)
        emu.fast_forward(STEP_FORWARD)
    emu.press_button("up", frames=PRESS_FRAMES)
    emu.fast_forward(STEP_FORWARD)
    emu.press_button("a", frames=STARTER_ACTION_FRAMES)
    emu.fast_forward(STARTER_ADVANCE_FRAMES)

    # Do not return control to the LLM during the transient overworld frames:
    # an A-heavy generic plan can race straight through the YES/NO prompt.
    # Advance only until the starter choice is visibly active, then let the
    # deterministic menu branch confirm it on the next cycle.
    for _ in range(max_dialog_advances):
        current_screen = ram_reader.screen_type()
        current_menu = ram_reader.read_menu_state()
        if (
            current_screen in ("menu", "list_menu")
            or int(current_menu.get("menu_id", 0)) > 0
        ):
            return True
        emu.press_button("a", frames=STARTER_ACTION_FRAMES)
        emu.fast_forward(STARTER_ADVANCE_FRAMES)
    return False


def _select_starter_from_menu(
    emu: Any,
    ram_reader: RAMReader,
    *,
    max_advances: int = 16,
    decline_presses: int = 8,
) -> int:
    """Confirm the first starter, then B through the nickname prompt as NO."""
    party_count = ram_reader.party_count()
    emu.press_button("a", frames=STARTER_ACTION_FRAMES)
    emu.fast_forward(STARTER_ADVANCE_FRAMES)

    for _ in range(max_advances):
        party_count = ram_reader.party_count()
        if party_count > 0:
            break
        emu.press_button("a", frames=STARTER_ACTION_FRAMES)
        emu.fast_forward(STARTER_ADVANCE_FRAMES)

    if party_count > 0:
        # Verified live against Pokémon Blue: B advances the remaining text and
        # resolves the default-YES nickname prompt as NO without name entry.
        for _ in range(decline_presses):
            emu.press_button("b", frames=STARTER_ACTION_FRAMES)
            emu.fast_forward(STARTER_ADVANCE_FRAMES)
    return party_count


def _starter_picked_event(
    previous_party_count: int,
    current_party_count: int,
    species_hint: str | None,
) -> dict[str, Any] | None:
    """Build the one-time milestone for the starter 0→1 party transition."""
    if previous_party_count != 0 or current_party_count != 1:
        return None
    return {
        "event": "starter_picked",
        "party_count": 1,
        "species_hint": species_hint,
    }


def _starter_milestone_for_cycle(
    *,
    previous_party_count: int,
    current_party_count: int,
    species_hint: str | None,
    baseline_starter_name: str | None,
    milestone_emitted: bool,
) -> tuple[dict[str, Any] | None, bool]:
    """One-shot starter milestone for one decision-loop cycle.

    Fires at most once per run, from either path:

    1. In-run 0→1 party transition (fresh boot: deterministic starter branch
       or LLM-driven dialog advance) — the classic ``starter_picked`` event.
    2. Post-pick boot baseline: runs loading a known-good checkpoint
       (``data/boot.state`` was saved after the starter was received) start
       with ``party_count == 1``, so no 0→1 transition is ever observable and
       the strict transition check would stay silent forever even though the
       party visibly holds a starter (GAMEPLAY-STARTER-002). The milestone
       then fires from the baseline party's starter species instead, tagged
       with ``"source": "boot_baseline"``.

    Returns ``(event, milestone_emitted)`` — pass the previous cycle's
    ``milestone_emitted`` back in to keep the event one-shot across cycles.
    """
    if milestone_emitted:
        return None, True
    event = _starter_picked_event(
        previous_party_count, current_party_count, species_hint
    )
    if event is not None:
        return event, True
    if baseline_starter_name is not None and previous_party_count > 0:
        return (
            {
                "event": "starter_picked",
                "party_count": 1,
                "species_hint": baseline_starter_name,
                "source": "boot_baseline",
            },
            True,
        )
    return None, False


def _blocked_spatial_directions(spatial_desc: dict[str, Any]) -> set[str]:
    """Return blocked directions, preserving known map-edge exits."""
    adjacent = spatial_desc.get("adjacent", {})
    blocked = {
        direction
        for direction, tile_type in adjacent.items()
        if tile_type in ("wall", "object")
    }

    # Route 1 is a map-edge warp, so the coarse 2×2 block classifier sees
    # its north-edge tile as a wall. At the center opening, UP is the exit.
    if spatial_desc.get("map_name") == "Pallet Town":
        tile_x = int(spatial_desc.get("player_tile_x", -1))
        tile_y = int(spatial_desc.get("player_tile_y", 99))
        if 8 <= tile_x <= 12 and tile_y <= 2:
            blocked.discard("up")

    return blocked


def screenshot_to_base64(screenshot: np.ndarray) -> str:
    """Convert numpy RGB screenshot to base64 data URL."""
    img = Image.fromarray(screenshot)
    # Scale 3x with nearest-neighbor (pixel-perfect) so the vision model
    # can distinguish wall edges from floor seams at 144x160 native res.
    img = img.resize((img.width * 3, img.height * 3), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _is_battle_game_state(game_state: dict[str, Any] | None) -> bool:
    """Return whether an observed game-state dict represents an active battle."""
    if not game_state:
        return False
    screen = game_state.get(
        "result", game_state.get("screen_type", game_state.get("screen", ""))
    )
    return screen == "battle" or bool(game_state.get("battle_state"))


def _escalating_recovery(
    emu,
    recovery_level: int,
    last_direction: str,
    last_saved_slot: int | None,
    game_state: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Execute escalating recovery action. Returns (strategy_name, description).

    Ladder:
      Level 0 — Alternate direction: rotate 90° from last direction
      Level 1 — Menu redraw: START, B, B (force screen refresh)
      Level 2 — Step back: press opposite of last direction
      Level 3 — Load checkpoint: restore last saved state
      Level 4 — A-mash + B: rapid A presses (dialog stuck) then B to close

    If no last_direction or no checkpoint available, skips to next level.
    Recovery level wraps at 4 (always does A-mash on max).

    Battles bypass every generic rung. Loading a checkpoint can erase the
    encounter, START/B/direction recovery is not a legal turn, and blind A-mash
    can choose an unintended move. Re-issue a normalized move action instead.
    """
    if _is_battle_game_state(game_state):
        result = execute_tool_call(emu, "select_move", {"move_number": 1})
        return (
            "battle_select_move",
            f"select_move(1) re-issued from live battle state — {result}",
        )

    # Clamp level
    level = min(recovery_level, 4)

    if level == 0 and last_direction in _DIR_ROTATION:
        alt = _DIR_ROTATION[last_direction]
        emu.press_button(alt.lower(), frames=60)
        emu.fast_forward(120)
        return ("alternate_direction", f"rotated from {last_direction} → {alt}")

    elif level == 1:
        # Menu redraw: open menu, close it — forces screen re-render
        emu.press_button("start", frames=30)
        emu.wait(60)
        emu.press_button("b", frames=10)
        emu.wait(30)
        emu.press_button("b", frames=10)
        emu.wait(30)
        return ("menu_redraw", "START → B → B (force screen redraw)")

    elif level == 2 and last_direction in _OPPOSITE_DIR:
        opp = _OPPOSITE_DIR[last_direction]
        emu.press_button(opp.lower(), frames=60)
        emu.fast_forward(120)
        return ("step_back", f"pressed {opp} (opposite of {last_direction})")

    elif level == 3 and last_saved_slot is not None:
        try:
            emu.load_state(last_saved_slot)
            return ("load_checkpoint", f"loaded slot {last_saved_slot}")
        except Exception as exc:
            return ("load_checkpoint_failed", f"slot {last_saved_slot}: {exc}")

    elif level >= 4 or (level >= 2 and last_direction not in _OPPOSITE_DIR):
        # A-mash: 20 rapid A presses (dialog stuck) then B to close menus
        for _ in range(20):
            emu.press_button("a", frames=3)
            emu.fast_forward(1)
        emu.wait(30)
        emu.press_button("b", frames=30)
        emu.wait(30)
        return ("a_mash", "20× A + B (dialog/menu escape)")

    # Fallback: try next level
    return _escalating_recovery(
        emu,
        recovery_level + 1,
        last_direction,
        last_saved_slot,
        game_state=game_state,
    )


def cartographer_analyze(
    client: OpenRouterClient,
    screenshot: np.ndarray,
) -> tuple[dict[str, Any], str]:
    """Send reference image + live screenshot to Gemma 12B.

    Returns (parsed spatial JSON, raw_text). No WorldState dependency —
    the vision model looks at the game directly and describes what it sees.
    """
    img_b64 = screenshot_to_base64(screenshot)

    response = client.chat_completion(
        model="google/gemma-3-12b-it",
        messages=[
            {"role": "system", "content": CARTOGRAPHER_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CARTOGRAPHER_TEMPLATE},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{REFERENCE_IMAGE_B64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                ],
            },
        ],
        temperature=0.1,
        max_tokens=2048,
    )

    text = response.get("content", "")
    return _extract_spatial_json(text), text


def _extract_spatial_json(text: str) -> dict[str, Any]:
    """Extract spatial observation JSON from model response.

    Handles markdown fences, leading/trailing text, and partial JSON.
    Much simpler than the old OBS_PATCH parser — just finds the JSON object.
    """
    text = text.strip()

    # Strip ``` fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if len(lines) > 1 else lines
        if lines and lines[-1].strip() in ("```", "```json", "```yaml"):
            lines = lines[:-1]
        text = "\n".join(lines)

    # Try whole-string JSON first
    try:
        return cast(dict[str, Any], json.loads(text))
    except (json.JSONDecodeError, ValueError):
        pass

    # Try finding JSON object with regex
    import re
    m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return cast(dict[str, Any], json.loads(m.group()))
        except (json.JSONDecodeError, ValueError):
            pass

    # Try YAML fallback
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    return {"result": "unknown", "_parse_error": text[:500]}


def controller_plan(
    client: OpenRouterClient,
    spatial_desc: dict[str, Any],
    last_button: str,
    last_result: str,
    blocked_dir: str = "",
    blocked_count: int = 0,
    max_actions: int = 6,
    screenshot: Any = None,
    frame_ref: str | None = None,
    goal: str = "",
    notes: str = "",
    last_dialog: str = "",
    study_result: str = "",
) -> dict[str, Any]:
    """Controller model (Luna via OpenRouter) outputs a movement PLAN.

    Now takes the cartographer's spatial JSON directly (adjacent tiles,
    visible_exits, player_facing, suggested_action) instead of an ASCII
    tile map. The model gets richer, more accurate spatial info.

    When `screenshot` is provided, the live game frame is attached as an
    image so Luna can use its own vision to see the screen.

    When `frame_ref` is provided (uuid of a previously-seen identical
    frame from the persistent FrameCache), NO image is attached — the
    prompt instead carries a text marker telling Luna this exact frame
    was already sent before, so it should rely on the spatial summary
    (identical visuals). Saves the image tokens on repeat sightings.
    """
    # Build a compact spatial summary string
    facing = spatial_desc.get("player_facing", "?")
    adj = spatial_desc.get("adjacent", {})
    exits = spatial_desc.get("visible_exits", [])
    suggested = spatial_desc.get("suggested_action", "")
    text = spatial_desc.get("text_content", [])
    map_name = spatial_desc.get("map_name", "Unknown")
    tile_x = spatial_desc.get("player_tile_x", "?")
    tile_y = spatial_desc.get("player_tile_y", "?")

    adj_str = ", ".join(f"{d}={adj.get(d, '?')}" for d in ["up", "down", "left", "right"])
    exits_str = "; ".join(exits) if exits else "none visible"
    text_str = " | ".join(text) if text else "none"

    spatial_summary = (
        f"MAP: {map_name}\n"
        f"PLAYER TILE: x={tile_x}, y={tile_y}\n"
        f"PLAYER FACING: {facing}\n"
        f"ADJACENT TILES: {adj_str}\n"
        f"VISIBLE EXITS: {exits_str}\n"
        f"SCREEN TEXT: {text_str}\n"
        f"SUGGESTED ACTION: {suggested}"
    )

    system = load_system_prompt(hint_level=HINT_LEVEL) + "\n\n" + (
        "You are controlling a Game Boy game player character.\n\n"
        "You receive a SPATIAL OBSERVATION describing what's around the player.\n"
        "Output a MOVEMENT PLAN — a sequence of button presses to execute.\n\n"
        "Respond with ONLY a JSON object:\n"
        '{"plan": ["UP","DOWN","LEFT","RIGHT","A","B","START","SELECT",...], "intent": "reason"}\n\n'
        "RULES:\n"
        f"- Maximum {max_actions} actions in the plan.\n"
        "- UP/DOWN/LEFT/RIGHT move one tile in that direction.\n"
        "- A interacts with adjacent objects/NPCs/doors.\n"
        "- B cancels, START opens menu.\n\n"
        "EXPLORATION STRATEGY:\n"
        "- Start with SHORT moves (2-3 tiles) in new areas.\n"
        "- MAX 3 of the SAME direction in a plan. Never 4+ of any direction.\n"
        "- If you hit a wall, switch directions immediately.\n"
        "- Walk toward visible exits (doors, stairs, paths).\n"
        "- If adjacent tile is 'wall' in one direction, do NOT try that direction.\n"
        "- If adjacent tile is 'door', walk into it (or press A on it).\n"
        "- If adjacent tile is 'npc', walk toward it and press A to talk.\n"
        "- If adjacent tile is 'stair', walk onto it.\n"
        "- When ALL directions are blocked (walls/objects all around): press A.\n"
        "- After interacting (A), next action should move away.\n"
        "- INDOOR rooms are small (3-6 tiles wide). Plan 2-3 tile moves.\n"
        "- OUTDOOR areas (grass, paths visible): 4-6 tile moves OK.\n\n"
        "MEMORY — you maintain your own knowledge in DuckBrain (persists across runs):\n"
        "- ACTIVE GOAL / RECENT NOTES / LAST DIALOG are injected each cycle.\n"
        "- Optional output fields (JSON only):\n"
        '  "note": a fact you just learned (NPC info, map info, objective, mechanic).\n'
        '  "goal": your current objective — include it when it changes or is new.\n'
        '  "study": a memory key to read next cycle, e.g. "/maps/oaks-lab" or "/guides/how-battles-work".\n'
        "- Use note/goal/study when you learn something — memory is how you win.\n"
        "- NEVER guess: read text, note what it says, act on it.\n"
    )

    blocked_msg = ""
    if blocked_dir and blocked_count >= 2:
        blocked_msg = (
            f"\n⚠️  WARNING: Previously pressed {blocked_dir} {blocked_count}+ times "
            f"with no progress. That direction is likely BLOCKED. "
            f"Do NOT include {blocked_dir} in your plan.\n"
        )

    msg = (
        f"{spatial_summary}\n\n"
        f"LAST BUTTON: {last_button or 'none'}\n"
        f"LAST RESULT: {last_result or 'unknown'}\n"
        f"{blocked_msg}\n"
    )

    memory_ctx = (
        "MEMORY CONTEXT:\n"
        f"ACTIVE GOAL: {goal or '(not set yet — set one when you learn an objective from text)'}\n"
        f"RECENT NOTES: {notes or 'none yet'}\n"
        f"LAST DIALOG: {last_dialog or 'none'}\n"
        f"STUDY RESULT: {study_result or '(none)'}\n"
    )
    msg += memory_ctx + "\nOutput a movement plan (max {max_actions} actions). JSON only.\n".format(max_actions=max_actions)

    # Build user message — include live screenshot for Luna's own vision.
    # On a FrameCache hit (frame_ref set), attach a text marker instead of
    # the image: Luna has seen this exact frame before, so the spatial
    # summary + reference carry the same information at ~zero image tokens.
    user_content: Any
    if frame_ref:
        ref_marker = (
            f"\n[SCREEN REF {frame_ref}] This exact game frame was sent to you "
            f"in a previous cycle — identical pixels (same location, same "
            f"dialog/state). Use the spatial summary above; no new image needed.\n"
        )
        user_content = f"{ref_marker}{msg}"
    elif screenshot is not None:
        try:
            img_b64 = screenshot_to_base64(screenshot)
            user_content = [
                {"type": "text", "text": msg},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ]
        except Exception:
            user_content = msg
    else:
        user_content = msg

    response = client.chat_completion(
        model="openai/gpt-5.6-luna",  # Luna via OpenRouter (double-discount pricing)
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        max_tokens=300,
        thinking={"type": "disabled"},
    )

    text = response.get("content", "{}")
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if len(lines) > 1 else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        result = json.loads(text)
        # Accept both {"plan": [...]} and legacy {"button": "UP"} format
        if "plan" in result:
            result["raw_response"] = text
            return result  # type: ignore[no-any-return]
        if "button" in result:
            return {"plan": [result["button"]], "intent": result.get("intent", ""), "raw_response": text}
        return {"plan": ["A"], "intent": "parse_fallback", "raw_response": text}
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{[^}]+\}', text)
        if m:
            try:
                result = json.loads(m.group())
                if "plan" in result:
                    result["raw_response"] = text
                    return result  # type: ignore[no-any-return]
                if "button" in result:
                    return {"plan": [result["button"]], "intent": result.get("intent", ""), "raw_response": text}
            except json.JSONDecodeError:
                pass
        return {"plan": ["A"], "intent": "parse_failure_fallback", "raw_response": text}


# ── Main ────────────────────────────────────────────────────────────

def _resolve_boot_state(arg: str | None) -> Path | None:
    """Resolve the checkpoint to boot from, or None to intro-bypass.

    - ``None`` (flag omitted): use ``DEFAULT_BOOT_STATE`` when it exists.
    - ``"skip"``: never boot from a checkpoint (legacy intro bypass).
    - otherwise: treat the argument as a literal path.
    Returns ``None`` when no usable checkpoint file exists.
    """
    if arg is not None and arg.lower() == "skip":
        return None
    candidate = Path(arg) if arg else DEFAULT_BOOT_STATE
    return candidate if candidate.is_file() else None


def _format_summary(
    run_id: str,
    n_actions: int,
    screens: set[str],
    lock_warn_cycles: int,
    total_cycles: int,
    distinct_tiles: int,
) -> str:
    """Format the final summary line, including the per-run lock-rate."""
    lock_rate = lock_warn_cycles / total_cycles
    return (
        f"[{run_id}] Done. {n_actions} actions. Screens: {screens} "
        f"| lock-rate: {lock_warn_cycles}/{total_cycles} cycles with "
        f"direction-lock warnings ({lock_rate:.0%}) "
        f"| distinct tiles: {distinct_tiles}"
    )


def _main_parser() -> argparse.ArgumentParser:
    """Build the real CLI parser main() uses (module-level so tests can parse)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--cycles", type=int, default=CYCLES)
    parser.add_argument(
        "--rom",
        default=None,
        help=(
            "Path to the Gen-1 GB ROM to boot (default: "
            "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb)."
        ),
    )
    parser.add_argument(
        "--boot-state",
        default=None,
        help=(
            "Path to a known-good .state checkpoint to boot from instead of "
            "the intro bypass (default: data/boot.state when present; "
            "'skip' forces the legacy intro bypass)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate setup (ROM + boot-state paths, config summary) and exit "
            "0 — no emulator boot, no LLM/API calls (GAP-032)."
        ),
    )
    return parser


def main() -> None:
    global CYCLES, ROM, run_id, log_path, SCREENSHOT_DIR

    parser = _main_parser()
    args = parser.parse_args()
    if args.dry_run:
        # The import-time precheck normally exits first; this branch is a
        # defensive backstop for programmatic main() calls.
        sys.exit(_dry_run_summary(args.run_id, max(1, args.cycles), args.boot_state, args.rom))
    if args.rom:
        ROM = args.rom
    CYCLES = max(1, args.cycles)
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"run_{run_id}.jsonl"
    SCREENSHOT_DIR = Path("screenshots") / f"run_{run_id}"
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    emu = Emulator(ROM)

    # ── Boot state (GAP-028) ────────────────────────────────────────
    # A fresh run that boots from the title screen and A-mashes through
    # the intro can land in a degenerate overworld state (player facing
    # a wall) that direction-locks on every cycle. When a known-good
    # checkpoint is available, boot from it instead so the run starts
    # from a verified overworld position with the starter already picked.
    boot_path = _resolve_boot_state(args.boot_state)
    boot_from_state = boot_path is not None
    if boot_from_state:
        emu.load_state(boot_path)
        emu.wait(30)  # settle after state restore
        safe_print(f"[{run_id}] Booting from checkpoint {boot_path} — skipping intro bypass")
    elif args.boot_state and args.boot_state.lower() != "skip":
        safe_print(f"[{run_id}] Boot checkpoint {args.boot_state} not found — falling back to intro bypass")

    # Init RAM reader (instant state reads) or fall back to vision cartographer
    pipeline_name: str
    if USE_RAM_READER:
        ram_reader = RAMReader(emu, ROM)
        pipeline_name = "RAM reader"
        safe_print(f"[{run_id}] Starting run with RAM reader pipeline...")
    else:
        pipeline_name = "cartographer"
        safe_print(f"[{run_id}] Starting run with visual-reference cartographer pipeline...")
        safe_print("  Reference image: reference/bedroom_overworld.png")

    # Persistent frame cache — UUID references for repeated screenshots.
    # Survives runs, so revisiting a map in a later session also hits.
    _frame_cache = FrameCache("data/frame_cache.json")
    safe_print(f"[{run_id}] Frame cache: {_frame_cache.unique_frames} known frames "
               f"({_frame_cache.total_seen} total references) — {_frame_cache.MAX_ENTRIES} max")

    # Init AI clients
    if USE_VISION_CLIENT:
        vision = VisionClient()  # noqa: F841 — conditionally enabled debug classifier
    controller_client = OpenRouterClient()  # uses DEEPSEEK_API_KEY from .env

    # ── Checkpoint / recovery state (STUCK-RECOVER) ─────────────────
    _checkpoint_slot: int = 0
    _last_saved_slot: int | None = None
    _dir_blacklist: set[str] = set()  # directions that caused checkpoint recovery
    _last_direction: str = ""  # last direction pressed (for controller context)
    _last_result: str = "unknown"  # last movement result

    # ── Stuck detection (4 independent dimensions) ──────────────────
    _same_dir: str | None = None   # last repeated direction
    _same_dir_count: int = 0       # consecutive same-direction presses
    _same_screen_count: int = 0    # consecutive cycles on same screen type
    _last_screen_type: str = ""    # for same-screen detection
    _same_tile_count: int = 0      # consecutive cycles on same RAM tile
    _last_tile: tuple[int, int, int] | None = None
    _void_tile_pct: float = 0.0    # % of tiles classified as unknown/void
    _void_cycles: int = 0          # consecutive cycles with >95% void tiles

    # ── A-press loop detection (STUCK-A-LOOP) ──────────────────────
    _a_press_count: int = 0        # consecutive A presses without direction change
    _MAX_A_PRESS = 3               # after 3 consecutive A presses → trigger recovery
    _last_action_button: str = ""  # last non-direction button pressed

    # ── Escalating recovery ────────────────────────────────────────
    _recovery_level: int = 0       # current rung of the escalation ladder
    _recovery_attempts: int = 0    # total recovery escalations (capped at MAX)
    _last_state_key: str = ""      # composite key for state-change detection
    _gave_up: bool = False         # True once max recovery attempts exhausted

    # ── Frame hashing for cartographer cache ───────────────────────
    _last_frame_hash: str = ""   # for frame hashing — skip cartographer on identical frames
    _cached_patch: dict[str, Any] = {}  # cached cartographer output
    _cached_carto_raw: str = ""  # cached raw cartographer text

    # ── Frame hashing for Luna vision (controller screenshot dedup) ─
    # Only attach the screenshot to the controller prompt when the
    # frame CHANGED since the last call. Identical frames (standing
    # still, dialog open) re-send the same ~2500 image tokens every
    # cycle — pure waste. RAM text still flows every cycle.
    _last_controller_frame_hash: str = ""

    # ── Persistent frame cache (UUID references across runs) ──────
    # Screenshots are md5-hashed and stored in a disk-backed LRU cache
    # (max 1000). First sighting sends the image; any repeat sighting
    # (battle loop, re-walking the same tile, same dialog box) sends a
    # short text reference "<uuid>" instead of the image bytes — same
    # visual info, ~zero image tokens. Survives restarts, so revisiting
    # a map in a later session still hits.
    # NOTE: bound at line ~543 in the pipeline-init block, before the
    # main loop. Do NOT declare here — an assignment would wipe it.
    assert _frame_cache is not None  # bound in pipeline-init block above

    # ── Deterministic intro bypass ──────────────────────────────────
    # Only runs when no boot checkpoint was loaded (GAP-028): the intro
    # A-mash can land in a degenerate wall-facing overworld state that
    # direction-locks on the very first cycles. Booting from a known-good
    # checkpoint skips all of this.
    # A-mash batch constants — also used by the main-loop name_entry
    # handler, so they live OUTSIDE the guarded intro block (booting from
    # a checkpoint skips the intro but can still re-enter name_entry).
    _A_BURST = 10       # A-presses per batch — Gen 1 text advances in a few presses
    _A_FRAMES = 5       # hold A for 5 frames each press
    _FF_FRAMES = 30     # fast-forward between presses (~350 frames per burst total)
    _NAME_ENTRY_STUCK_MAX = 3  # after 3 cycles → programmatic entry
    if not boot_from_state:
        # ── Deterministic intro bypass ──────────────────────────────────
        # Decoupled: A-mash aggressively in large batches, sparse
        # observation checks (RAM reader is instant, cartographer has 1-60s latency).
        # RAM reader path: instant state reads, no LLM calls.
        safe_print(f"[{run_id}] Bypassing intro via {pipeline_name}...")

        # Step 1: Title screen → press START. PyBoy starts before the title is
        # ready for input, so let it finish drawing before sending START.
        emu.wait(180)
        emu.bypass_title()
        # Brief settle — intro loop detects state changes via RAM, no need for long waits.
        emu.wait(30)
        # Press A — if no save file, this selects NEW GAME directly.
        # If save exists, cursor is on CONTINUE — we'll detect old save below.
        emu.press_button("a", frames=15)
        emu.fast_forward(60)  # let game load (or Oak appear)

        _player_named = False
        _rival_named = False
        _intro_checks = 0
        _MAX_INTRO_CHECKS = 15   # raised from 12 — programmatic name entry takes fewer cycles
        _save_detected = False  # set True if we loaded a save file by mistake
        _name_entry_stuck = 0   # consecutive name_entry cycles without progress
        _last_intro_phase = None   # track phase transitions for logging

        while _intro_checks < _MAX_INTRO_CHECKS:
            _intro_checks += 1
            screenshot = emu.capture()

            # Use RAM reader or cartographer for screen classification
            if USE_RAM_READER:
                patch_data = ram_reader.observe()
                carto_raw = json.dumps({"source": "ram_reader", "result": patch_data.get("result")})
            else:
                patch_data, carto_raw = cartographer_analyze(
                    controller_client, screenshot
                )
            st = patch_data.get("result", "unknown")

            # ── Save file detection: if we're in overworld without naming ──
            if st == "overworld" and not _player_named:
                tc = patch_data.get("text_content", [])
                if not tc and not USE_RAM_READER:  # RAM reader always returns empty text_content
                    if not _save_detected:
                        _save_detected = True
                        print("  [intro] SAVE DETECTED — restarting with NEW GAME")
                        # Reset the emulator from scratch
                        emu.stop()
                        emu = Emulator(ROM)
                        emu.bypass_title()
                        emu.wait(120)
                        # Move cursor from CONTINUE (default) to NEW GAME
                        emu.press_button("down", frames=15)
                        emu.wait(15)
                        emu.press_button("a", frames=15)
                        emu.wait(120)
                        _intro_checks = 0  # reset counter
                        continue

            if st == "overworld":
                if _last_intro_phase != "overworld":
                    safe_print(f"  [intro] Phase: {_last_intro_phase} → overworld — intro complete ({_intro_checks} checks)")
                print(f"  [intro] {pipeline_name} says overworld — intro complete ({_intro_checks} checks)")
                break
            elif st == "name_entry":
                _name_entry_stuck += 1
                if _name_entry_stuck >= _NAME_ENTRY_STUCK_MAX:
                    # A-mashing may already have filled the name. Navigate from
                    # the default A key directly to END and accept it.
                    if not _player_named:
                        safe_print("  [intro] Name entry stuck — accepting player name")
                        emu.submit_name()
                        _player_named = True
                    elif not _rival_named:
                        safe_print("  [intro] Rival name stuck — accepting rival name")
                        emu.submit_name()
                        _rival_named = True
                    _name_entry_stuck = 0
                else:
                    # Not stuck yet — A-mash to advance through any pending dialog
                    # that sits between cycles (e.g. "So, your name is X?" confirmation).
                    # NOTE: do NOT set _player_named/_rival_named here — only programmatic
                    # typing actually writes the name, so flags must wait until enter_name()
                    # has run. Setting them prematurely caused the second name_entry
                    # cycle to be skipped and the rival to be named "----" (default).
                    for _ in range(_A_BURST):
                        emu.press_button("a", frames=_A_FRAMES)
                        emu.fast_forward(_FF_FRAMES)
            elif st == "title":
                _name_entry_stuck = 0  # reset — we're not in name entry
                emu.press_button("start", frames=30)
                emu.wait(90)
            else:
                # dialog / name_confirm / cutscene / unknown — A-mash aggressively
                _name_entry_stuck = 0  # reset — out of name entry
                for _ in range(_A_BURST):
                    emu.press_button("a", frames=_A_FRAMES)
                    emu.fast_forward(_FF_FRAMES)

            # ── Phase transition logging ───────────────────────────
            if st != _last_intro_phase:
                if _last_intro_phase is not None:
                    safe_print(f"  [intro] Phase: {_last_intro_phase} → {st} (check {_intro_checks})")
                _last_intro_phase = st

        if _intro_checks >= _MAX_INTRO_CHECKS:
            print(f"  [!] Intro bypass hit {_MAX_INTRO_CHECKS} check cap — proceeding anyway")
        else:
            print(f"  Intro bypass complete in {_intro_checks} checks")

        # ── Save state at center of bedroom (before moving) ──────────
        # The bedroom start position faces the TV; saving before we move
        # gives the controller a clean starting position to navigate from.
        try:
            emu.save_state(0)
            _last_saved_slot = 0
            print("  [CKPT] Post-intro state saved to slot 0")
        except Exception as exc:
            print(f"  [CKPT] Failed to save post-intro state: {exc}")

        # ── Step away from what we're facing ─────────────────────────
        # Walk LEFT (toward the bed/stairs area). The stairs down are on
        # the left side of the bedroom; walking LEFT avoids the TV loop
        # AND positions the character near the exit.
        safe_print("  [intro] Stepping away from TV...")
        emu.press_button("up", frames=15)   # face away from TV
        emu.fast_forward(30)
        # Clear any lingering dialog box
        emu.press_button("b", frames=30)
        emu.wait(30)

        # ── Leave bedroom ────────────────────────────────────────────
        # A 30-frame press advances roughly two tiles. The collision-verified path
        # from spawn (3,6) to the bedroom warp (7,1) is R,U,U,U,R.
        safe_print("  [intro] Walking to bedroom stairs (R,U,U,U,R)...")
        for button in ("right", "up", "up", "up", "right"):
            emu.press_button(button, frames=30)
            emu.fast_forward(60)
        emu.wait(90)

        # Continue through the ground floor so the controller starts outdoors.
        if emu.read_u8(0xD35E) == 0x25:  # wCurMap: Red's House 1F
            safe_print("  [intro] Leaving ground floor for Pallet Town...")
            for button in ("down", "down", "down", "left", "left", "down"):
                emu.press_button(button, frames=30)
                emu.fast_forward(60)
            emu.wait(90)
    else:
        _player_named = False
        _rival_named = False

    ctx = GlobalContext(generation="gen1", location="pallet_town" if boot_from_state else "bedroom")
    # If we bypassed the intro, set player/rival names
    if _player_named:
        ctx.player_name = "ASH"
    if _rival_named:
        ctx.rival_name = "GARY"

    # Open log file for incremental writing (web viewer polls this)
    log_file = open(log_path, "w")
    log_file.write("")  # create/truncate
    log_file.flush()

    # Persistent counter for the main loop's name_entry handler. The
    # intro loop has its own `_name_entry_stuck`; this list-of-one is
    # scoped to the main loop so a re-entry into name_entry outside
    # the intro phase still escalates to programmatic typing after 3
    # cycles.
    _main_ne_stuck_box: list[int] = [0]
    _last_party_count = ram_reader.party_count() if USE_RAM_READER else 0
    # One-shot starter-pick milestone flag: the milestone fires once per run,
    # either on an in-run 0→1 transition or from a post-pick boot baseline.
    _starter_milestone_emitted = False
    _failed_flee_attempts = 0

    # ── Per-run metrics (GAP-028) ──────────────────────────────────
    _dir_lock_warn_cycles = 0   # cycles with >=1 direction-lock warning
    _visited_tiles: set[tuple[int, int, int]] = set()  # (map_id, x, y) seen

    # ── Agent memory state (self-maintained, DuckBrain-backed) ──
    # The agent tracks its own goal, notes, and world map across cycles
    # AND across runs. goal/notes/last_dialog/study are injected into the
    # controller prompt each cycle; note/goal/study outputs are executed
    # here and persisted to DuckBrain (namespace pokemon-global).
    _mem_goal = ""
    _mem_notes: list[str] = []   # most recent first, capped at 6
    _last_dialog_text = ""
    _pending_study_key = ""      # controller asked to study a key
    _pending_study_result = ""   # fetched content, injected once
    if USE_RAM_READER:
        try:
            from src.core import duckbrain_client as _dbc
            _goal_rec = _dbc.get(key="/goals/current")
            if _goal_rec:
                attrs = _goal_rec.get("attributes", {})
                _mem_goal = str(attrs.get("goal") or _goal_rec.get("embedding_text", ""))[:200]
        except Exception as _e:
            safe_print(f"  [MEM] goal load failed: {_e}")

    for cycle in range(CYCLES):
        try:
            _cycle_dir_lock_warned = False  # per-cycle flag (GAP-028 metric)
            screenshot = emu.capture()

            # Save screenshot every cycle for progress tracking
            img = Image.fromarray(screenshot)
            img.save(SCREENSHOT_DIR / f"step_{cycle+1:04d}.png")

            # Step 1: Classify screen + spatial analysis
            # RAM reader: instant reads, no frame hashing needed.
            # Cartographer: Gemma 12B vision model with frame hashing cache.
            if USE_RAM_READER:
                # RAM reader is instant — always re-observe for accurate state
                patch_data = ram_reader.observe()
                carto_raw = json.dumps({"source": "ram_reader", "result": patch_data.get("result")})
            else:
                # ── Frame hashing: skip cartographer if nothing changed ──
                # Hash the raw screenshot bytes. If identical to last frame,
                # the character hasn't moved — reuse cached observation.
                # Works for ALL screen types including battles. During battle idle
                # (both Pokémon standing, same HP), the frame is identical and
                # the cached observation is still valid. The Controller/StateWindow
                # still runs and makes decisions — we just skip re-observing.
                import hashlib
                frame_bytes = screenshot.tobytes()
                frame_hash = hashlib.md5(frame_bytes).hexdigest()
                if _last_frame_hash != frame_hash or not _cached_patch:
                    # Frame changed (or first cycle) — call cartographer
                    patch_data, carto_raw = cartographer_analyze(controller_client, screenshot)
                    _cached_patch = patch_data
                    _cached_carto_raw = carto_raw
                    _last_frame_hash = frame_hash
                else:
                    # Frame unchanged — reuse cached observation
                    patch_data = _cached_patch
                    carto_raw = _cached_carto_raw
                    safe_print(f"  [SKIP] Frame unchanged, reusing cached cartographer ({patch_data.get('result','?')})")
            st = patch_data.get("result", "unknown")
            if st != "battle":
                _failed_flee_attempts = 0

            # ── Dialog text carry-over ──
            # When a dialog box is on screen, capture its text so the NEXT
            # overworld decision can see what was said (Oak's instructions,
            # NPC hints). This is the agent's information channel.
            if st == "dialog" and patch_data.get("text_content"):
                _last_dialog_text = str(patch_data["text_content"][0])[:200]

            raw_map_id = patch_data.get("map_id")
            raw_tile_x = patch_data.get("player_tile_x")
            raw_tile_y = patch_data.get("player_tile_y")
            current_tile = None
            if (
                isinstance(raw_map_id, int)
                and isinstance(raw_tile_x, int)
                and isinstance(raw_tile_y, int)
            ):
                current_tile = (raw_map_id, raw_tile_x, raw_tile_y)
            if current_tile is not None:
                _visited_tiles.add(current_tile)
            _last_tile, _same_tile_count = _track_same_tile(
                current_tile, _last_tile, _same_tile_count
            )
            tile_recovery_reason = _tile_lock_reason(
                _last_tile, _same_tile_count
            )

            map_id = int(raw_map_id) if isinstance(raw_map_id, int) else -1
            if USE_RAM_READER:
                party_count = ram_reader.party_count()
                menu_state = ram_reader.read_menu_state()
            else:
                raw_party_count = patch_data.get("party_count", 0)
                party_count = (
                    int(raw_party_count) if isinstance(raw_party_count, int) else 0
                )
                raw_menu_state = patch_data.get("menu_state", {})
                menu_state = raw_menu_state if isinstance(raw_menu_state, dict) else {}

            starter_event, _starter_milestone_emitted = _starter_milestone_for_cycle(
                previous_party_count=_last_party_count,
                current_party_count=party_count,
                species_hint=(
                    ram_reader.first_party_species_hint() if USE_RAM_READER else None
                ),
                baseline_starter_name=(
                    ram_reader.first_party_starter_name() if USE_RAM_READER else None
                ),
                milestone_emitted=_starter_milestone_emitted,
            )
            if starter_event is not None:
                milestone = {"cycle": cycle + 1, **starter_event}
                results.append(milestone)
                log_file.write(json.dumps(milestone, default=str) + "\n")
                log_file.flush()
                safe_print(
                    "  [STARTER-PICKED] "
                    f"party_count={party_count} "
                    f"species_hint={starter_event['species_hint']}"
                )
            _last_party_count = party_count

            t0 = time.time()

            # Deterministic starter selection must pre-empt generic menu handling.
            if USE_RAM_READER and _should_select_starter(
                map_id=map_id,
                party_count=party_count,
                screen_type=st,
                menu_state=menu_state,
            ):
                safe_print(
                    f"  [STARTER] Oak's Lab menu detected at cycle {cycle + 1}; "
                    "selecting first starter"
                )
                selected_party_count = _select_starter_from_menu(emu, ram_reader)
                selection_entry = {
                    "cycle": cycle + 1,
                    "screen": st,
                    "event": "starter_selection",
                    "action": "confirm_first_starter_then_decline_nickname",
                    "map_id": map_id,
                    "party_count_before": party_count,
                    "party_count_after": selected_party_count,
                    "player_tile_x": raw_tile_x,
                    "player_tile_y": raw_tile_y,
                }
                results.append(selection_entry)
                log_file.write(json.dumps(selection_entry, default=str) + "\n")
                log_file.flush()

                starter_event, _starter_milestone_emitted = _starter_milestone_for_cycle(
                    previous_party_count=party_count,
                    current_party_count=selected_party_count,
                    species_hint=ram_reader.first_party_species_hint(),
                    baseline_starter_name=None,
                    milestone_emitted=_starter_milestone_emitted,
                )
                if starter_event is not None:
                    milestone = {"cycle": cycle + 1, **starter_event}
                    results.append(milestone)
                    log_file.write(json.dumps(milestone, default=str) + "\n")
                    log_file.flush()
                    safe_print(
                        "  [STARTER-PICKED] "
                        f"party_count={selected_party_count} "
                        f"species_hint={starter_event['species_hint']}"
                    )
                _last_party_count = selected_party_count
                safe_print(
                    f"  [{cycle + 1}/{CYCLES}] starter_selection | "
                    f"party={selected_party_count} | {time.time() - t0:.1f}s"
                )
                continue

            if st == "overworld":
                # Out of name_entry — reset stuck counter for any future re-entry.
                _main_ne_stuck_box[0] = 0
                # ── Visual-Reference Pipeline ──────────────────────
                # Cartographer already gave us spatial info (adjacent tiles,
                # visible_exits, player_facing, suggested_action).
                # Feed this directly to the controller — no MapIntegrator needed.

                # ── Stuck detection: track void tiles from cartographer output ──
                adj = patch_data.get("adjacent", {})
                if adj:
                    unknown_tiles = sum(1 for v in adj.values() if v in ("unknown", "?", ""))
                    total_tiles = len(adj)
                    _void_tile_pct = unknown_tiles / total_tiles if total_tiles > 0 else 0.0
                    if _void_tile_pct > 0.95:
                        _void_cycles += 1
                        safe_print(f"  [VOID] {unknown_tiles}/{total_tiles} tiles unknown ({_void_tile_pct:.0%}) — cycle {_void_cycles}/{MAX_VOID_CYCLES} | map_id={patch_data.get('map_id')} map={patch_data.get('map_name')} player=({patch_data.get('player_tile_x')},{patch_data.get('player_tile_y')})")
                    else:
                        _void_cycles = 0
                else:
                    _void_tile_pct = 0.0
                    _void_cycles = 0

                # ── Same-screen tracking ───────────────────────────
                if st == _last_screen_type:
                    _same_screen_count += 1
                else:
                    _same_screen_count = 0
                _last_screen_type = st

                # ── State-change detection (resets recovery counter) ──
                state_key = f"{st}:{patch_data.get('screen_subtype','')}:{adj.get('up','')}{adj.get('down','')}{adj.get('left','')}{adj.get('right','')}"
                if state_key != _last_state_key and _last_state_key != "":
                    _recovery_attempts = 0
                    _recovery_level = 0
                    safe_print(f"  [STATE] Changed → {st} — recovery counter reset")
                _last_state_key = state_key

                # ── Recovery check: any stuck condition triggers escalation ──
                needs_recovery = False
                recovery_reason = ""
                if _gave_up:
                    pass  # already exhausted — no more recovery
                elif tile_recovery_reason:
                    needs_recovery = True
                    recovery_reason = tile_recovery_reason
                elif _same_dir_count >= MAX_STUCK_SAME_DIR:
                    needs_recovery = True
                    recovery_reason = f"direction-locked ({_same_dir} x{_same_dir_count})"
                elif _same_screen_count >= MAX_SAME_SCREEN_CYCLES and _last_screen_type != "overworld":
                    needs_recovery = True
                    recovery_reason = f"screen-locked ({_last_screen_type} x{_same_screen_count})"
                elif _void_cycles >= MAX_VOID_CYCLES:
                    needs_recovery = True
                    recovery_reason = f"void-locked ({_void_cycles} cycles, {_void_tile_pct:.0%} unknown)"
                elif _a_press_count >= _MAX_A_PRESS:
                    needs_recovery = True
                    recovery_reason = f"A-press locked (A x{_a_press_count})"

                starter_approached = False
                if needs_recovery:
                    if _recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
                        if not _gave_up:
                            _gave_up = True
                            safe_print(f"  [RECOVER] GIVING UP after {_recovery_attempts} recovery attempts ({recovery_reason})")
                            evt = {"cycle": cycle + 1, "event": "recovery_exhausted",
                                   "reason": recovery_reason, "attempts": _recovery_attempts}
                            results.append(evt)
                            log_file.write(json.dumps(evt, default=str) + "\n")
                            log_file.flush()
                    else:
                        _recovery_attempts += 1
                        if (
                            "tile-locked" in recovery_reason
                            and USE_RAM_READER
                            and map_id == OAKS_LAB_MAP_ID
                            and party_count == 0
                        ):
                            starter_approached = _approach_first_starter(
                                emu, ram_reader
                            )
                        if starter_approached:
                            strategy, desc = (
                                "starter_approach",
                                "moved to the first Poké Ball and pressed A",
                            )
                        else:
                            strategy, desc = _escalating_recovery(
                                emu,
                                _recovery_level,
                                _last_direction,
                                _last_saved_slot,
                                game_state=patch_data,
                            )
                        _recovery_level += 1
                        # Blacklist the blocked direction on checkpoint restore
                        if strategy == "load_checkpoint" and _same_dir and _same_dir in _DIR_ROTATION:
                            _dir_blacklist.add(_same_dir)
                            safe_print(f"  [BLACKLIST] {_same_dir} added to blacklist: {_dir_blacklist}")
                        safe_print(f"  [RECOVER] Level {_recovery_level-1}: {strategy} — {desc} ({recovery_reason}) [attempt {_recovery_attempts}/{MAX_RECOVERY_ATTEMPTS}]")
                        evt = {"cycle": cycle + 1, "event": "recovery",
                               "level": _recovery_level - 1, "strategy": strategy,
                               "reason": recovery_reason, "attempt": _recovery_attempts,
                               "description": desc}
                        results.append(evt)
                        log_file.write(json.dumps(evt, default=str) + "\n")
                        log_file.flush()
                        trackers = _reset_recovery_trackers(
                            recovery_reason,
                            same_dir=_same_dir,
                            same_dir_count=_same_dir_count,
                            same_screen_count=_same_screen_count,
                            same_tile_count=_same_tile_count,
                            void_cycles=_void_cycles,
                            a_press_count=_a_press_count,
                        )
                        _same_dir = trackers.same_dir
                        _same_dir_count = trackers.same_dir_count
                        _same_screen_count = trackers.same_screen_count
                        _same_tile_count = trackers.same_tile_count
                        _void_cycles = trackers.void_cycles
                        _a_press_count = trackers.a_press_count
                        if starter_approached:
                            continue

                # Step 2b: Controller outputs movement PLAN from spatial description
                # Frame-cache dedup: hash the raw screenshot; if this exact
                # frame was seen before (same tile, same dialog box, battle
                # idle, looping flow), pass a text UUID reference instead of
                # re-sending the image bytes. First sighting → send image.
                import hashlib as _hashlib
                _ctrl_frame_hash = _hashlib.md5(screenshot.tobytes()).hexdigest()
                _frame_ref = None
                _cached_entry = _frame_cache.lookup(_ctrl_frame_hash) if _frame_cache else None
                if _cached_entry is not None:
                    # Repeat sighting — reference, don't re-send the image
                    _frame_cache.touch(_cached_entry, cycle + 1)
                    _vision_frame = None
                    _frame_ref = _cached_entry["uuid"]
                    _seen_n = _cached_entry.get("seen_count", 1)
                    safe_print(f"  [CACHE-HIT] frame {_ctrl_frame_hash[:8]} → ref {_frame_ref} (seen {_seen_n}x)")
                else:
                    # New frame — send the image, remember it
                    _vision_frame = screenshot
                    _frame_ref = None
                    if _frame_cache is not None:
                        _frame_cache.register(
                            _ctrl_frame_hash, cycle + 1,
                            map_name=patch_data.get("map_name", ""),
                            screen=st,
                        )
                decision = controller_plan(
                    controller_client, patch_data,
                    _last_direction or "",
                    _last_result,
                    blocked_dir=_same_dir or "",
                    blocked_count=_same_dir_count,
                    max_actions=CART_STEPS,
                    screenshot=_vision_frame,   # None on cache hit → no image cost
                    frame_ref=_frame_ref,        # UUID text ref on cache hit
                    goal=_mem_goal,
                    notes=" | ".join(_mem_notes[:6])[:300],
                    last_dialog=_last_dialog_text,
                    study_result=_pending_study_result,
                )
                # Study result is injected once, then cleared
                _pending_study_result = ""
                plan = decision.get("plan", ["A"])
                intent = decision.get("intent", "")

                # ── Agent memory outputs: note / goal / study ──────
                # The controller maintains its own knowledge. These fields
                # are optional; when present they are executed here and
                # persisted to DuckBrain (namespace pokemon-global).
                if USE_RAM_READER:
                    from src.core import duckbrain_client as _dbc
                    _mem_note = (decision.get("note") or "").strip()
                    _mem_new_goal = (decision.get("goal") or "").strip()
                    _mem_study_key = (decision.get("study") or "").strip()
                    _mapn = patch_data.get("map_name", "unknown")
                    if _mem_note:
                        try:
                            _dbc.remember(
                                key=f"/notes/overworld-{cycle}",
                                domain="concept",
                                attributes={"fact": _mem_note[:300], "source": "agent",
                                            "map": _mapn, "cycle": cycle},
                                embedding_text=_mem_note[:300],
                            )
                            _mem_notes.insert(0, f"[{_mapn}] {_mem_note[:120]}")
                            _mem_notes = _mem_notes[:6]
                            safe_print(f"  [MEM] note: {_mem_note[:80]}")
                            log_file.write(json.dumps(
                                {"cycle": cycle, "event": "memory_note", "map": _mapn,
                                 "note": _mem_note[:300]}, default=str) + "\n")
                            log_file.flush()
                        except Exception as _e:
                            safe_print(f"  [MEM] note failed: {_e}")
                    if _mem_new_goal:
                        _mem_goal = _mem_new_goal[:200]
                        try:
                            _dbc.remember(
                                key="/goals/current",
                                domain="goal",
                                attributes={"goal": _mem_goal, "source": "agent"},
                                embedding_text=f"Current goal: {_mem_goal}",
                            )
                            safe_print(f"  [MEM] goal: {_mem_goal[:80]}")
                            log_file.write(json.dumps(
                                {"cycle": cycle, "event": "memory_goal",
                                 "goal": _mem_goal}, default=str) + "\n")
                            log_file.flush()
                        except Exception as _e:
                            safe_print(f"  [MEM] goal failed: {_e}")
                    if _mem_study_key:
                        try:
                            _rec = _dbc.get(key=_mem_study_key)
                            if _rec:
                                _attrs = _rec.get("attributes", {})
                                _body = _attrs.get("fact") or _attrs.get("goal") or _rec.get("embedding_text", "")
                                _pending_study_result = f"{_rec.get('key')}: {str(_body)[:250]}"
                            else:
                                _pending_study_result = (
                                    f"(nothing at {_mem_study_key} — you haven't "
                                    f"learned it yet; explore and remember it)")
                            safe_print(f"  [MEM] study {_mem_study_key} -> {_pending_study_result[:60]}")
                            log_file.write(json.dumps(
                                {"cycle": cycle, "event": "memory_study",
                                 "key": _mem_study_key, "result": _pending_study_result[:250]},
                                default=str) + "\n")
                            log_file.flush()
                        except Exception as _e:
                            _pending_study_result = f"(study failed: {_e})"

                # ── Programmatic direction override ───────────────
                # Chain-rotate through blacklist. If ALL 4 directions
                # blacklisted, use A (interact) instead — stop walking.
                if _dir_blacklist:
                    filtered_plan = []
                    for btn in plan:
                        btn_upper = btn.upper()
                        direction = btn_upper
                        if direction in ("UP", "DOWN", "LEFT", "RIGHT"):
                            for _ in range(4):
                                if direction in _dir_blacklist and direction in _DIR_ROTATION:
                                    direction = _DIR_ROTATION[direction]
                                else:
                                    break
                            # If we cycled back to a blacklisted direction, all 4 blocked
                            if direction in _dir_blacklist:
                                direction = "A"  # interact instead
                        filtered_plan.append(direction)
                    if filtered_plan != [b.upper() for b in plan]:
                        safe_print(f"  [OVERRIDE] Blacklisted {_dir_blacklist}, plan {plan[:6]}→{filtered_plan[:6]}...")
                    plan = filtered_plan

                # ── Spatial pre-filter: strip wall/object directions ──
                # The cartographer tells us what's actually adjacent. If it says
                # a tile is "wall" or "object", walking there is impossible.
                # Strip those directions BEFORE execution regardless of LLM output.
                _blocked_spatial = _blocked_spatial_directions(patch_data)
                if _blocked_spatial:
                    _before_filter = plan[:]
                    _blocked_upper = {d.upper() for d in _blocked_spatial}
                    _filtered = [b for b in plan
                            if b.upper() not in _blocked_upper
                            or b.upper() not in ("UP", "DOWN", "LEFT", "RIGHT")]
                    # If filtering removed everything, keep the original plan.
                    # The cartographer's adjacent data can be wrong (e.g. bed
                    # mislabeled as "wall"), and the LLM may know better.
                    if _filtered:
                        plan = _filtered
                    if len(plan) < len(_before_filter):
                        safe_print(f"  [SPATIAL] Removed {_blocked_spatial} from "
                              f"plan {_before_filter[:3]}→{plan[:3]}...")

                # ── Run-length cap: max 3 consecutive same direction ──
                # The cartographer only sees the immediate adjacent tile.
                # Long plans (6x RIGHT) walk into walls 2-3 tiles away.
                # Cap consecutive same-direction moves to 3 regardless of LLM.
                _rle = 1
                for i in range(1, len(plan)):
                    if plan[i].upper() == plan[i-1].upper() and plan[i].upper() in ("UP","DOWN","LEFT","RIGHT"):
                        _rle += 1
                    else:
                        _rle = 1
                    if _rle > 3:
                        plan[i] = "A"  # replace with interact
                        _rle = 1
                        safe_print(f"  [CAP] Truncated same-direction run at position {i}")

                plan_entry = {
                    "cycle": cycle + 1,
                    "screen": st,
                    "pipeline": pipeline_name,
                    "plan": plan,
                    "intent": intent,
                    "controller_raw": decision.get("raw_response", ""),
                    "frame_cache": "hit" if _frame_ref else "miss",
                    "frame_uuid": _frame_ref,
                    "cartographer_raw": carto_raw,
                    "map_id": patch_data.get("map_id"),
                    "map_name": patch_data.get("map_name"),
                    "player_x": patch_data.get("player_x"),
                    "player_y": patch_data.get("player_y"),
                    "player_tile_x": patch_data.get("player_tile_x"),
                    "player_tile_y": patch_data.get("player_tile_y"),
                }
                results.append(plan_entry)
                log_file.write(json.dumps(plan_entry, default=str) + "\n")
                log_file.flush()

                # ── Execute the plan ──────────────────────────────
                btn_map = {
                    "UP": "up", "DOWN": "down", "LEFT": "left", "RIGHT": "right",
                    "A": "a", "B": "b", "START": "start", "SELECT": "select",
                }
                for button in plan:
                    button = button.upper()
                    btn = btn_map.get(button, "a")
                    emu.press_button(btn, frames=PRESS_FRAMES)
                    emu.fast_forward(STEP_FORWARD)
                    _last_direction = button

                    # Blocked-direction tracking (per-button for recovery)
                    if button in ("UP", "DOWN", "LEFT", "RIGHT"):
                        if button == _same_dir:
                            _same_dir_count += 1
                        else:
                            _same_dir = button
                            _same_dir_count = 1
                        # Direction press resets A-press counter
                        _a_press_count = 0
                    elif button == "A":
                        _same_dir = None
                        _same_dir_count = 0
                        _a_press_count += 1
                        _last_action_button = "A"
                        if _a_press_count == 3:
                            safe_print("  [WARN] A-press lock detected: A x3 — triggering recovery")
                    else:
                        _same_dir = None
                        _same_dir_count = 0
                        _a_press_count = 0

                    if _same_dir_count == 3:
                        safe_print(f"  [WARN] Direction-locking detected: {_same_dir} x3")
                        _cycle_dir_lock_warned = True
                    # Recovery is now handled centrally in the stuck-detection block
                    # after cartographer analysis, using the escalating recovery ladder.

                elapsed = time.time() - t0
                safe_print(f"  [{cycle+1}/{CYCLES}] {st} | {pipeline_name} x{CART_STEPS} | {elapsed:.1f}s")

            elif st == "name_entry":
                # ── Name entry bypass (main loop) ──────────────────
                # Use programmatic typing after 3 stuck cycles. The intro
                # loop handles the first two name_entry screens; if we
                # hit one again here (e.g. New Game from title without
                # intro), drive the keyboard directly. A-mashing alone
                # fills the name field with "AAAAAAAA" / "A..." rather
                # than the canonical ASH/BLUE, so always prefer enter_name.
                # Counter held in a single-element list so it persists
                # across main-loop cycles without adding new state attrs
                # to emu/ctx or a new import.
                _main_ne_stuck_box[0] += 1
                _main_ne_stuck = _main_ne_stuck_box[0]

                if _main_ne_stuck >= _NAME_ENTRY_STUCK_MAX:
                    if not _player_named:
                        safe_print("  [main] Name entry stuck — accepting player name")
                        emu.submit_name()
                        _player_named = True
                        ctx.player_name = "ASH"
                    elif not _rival_named:
                        safe_print("  [main] Rival name stuck — accepting rival name")
                        emu.submit_name()
                        _rival_named = True
                        ctx.rival_name = "GARY"
                    _main_ne_stuck_box[0] = 0
                else:
                    # Not yet stuck — A-mash briefly to give dialog time to advance
                    for _ in range(_A_BURST):
                        emu.press_button("a", frames=_A_FRAMES)
                        emu.fast_forward(_FF_FRAMES)

                elapsed = time.time() - t0
                entry = {
                    "cycle": cycle + 1,
                    "screen": st,
                    "action": "name_bypass",
                    "elapsed_s": round(elapsed, 1),
                    "cartographer_raw": carto_raw,
                }
                results.append(entry)
                log_file.write(json.dumps(entry, default=str) + "\n")
                log_file.flush()
                safe_print(
                    f"  [{cycle+1}/{CYCLES}] {st} | name_bypass "
                    f"(stuck={_main_ne_stuck}/{_NAME_ENTRY_STUCK_MAX}) | {elapsed:.1f}s"
                )

            else:
                # ── Traditional StateWindow flow ───────────────────
                # Reset name_entry stuck counter — we've left name_entry.
                _main_ne_stuck_box[0] = 0
                # Build StateWindow-compatible vision dict from cartographer output
                vis_dict = {
                    "screen_type": st,
                    "screen_subtype": patch_data.get("screen_subtype", ""),
                    "name_field": patch_data.get("name_field", ""),
                    "text_lines": patch_data.get("text_lines", []),
                    "text_content": patch_data.get("text_content", patch_data.get("text_lines", [])),
                    "menu_items": patch_data.get("menu_items", []),
                    "adjacent_tiles": patch_data.get("adjacent_tiles", {}),
                    "keyboard_grid": patch_data.get("keyboard_grid", {}),
                }

                # ── RAM reader enrichment for battle/dialog screens ──
                # When USE_RAM_READER is True, inject live RAM state into
                # the StateWindow vision dict so it can build compact prompts.
                if USE_RAM_READER:
                    if st == "battle":
                        bs = ram_reader.read_battle_state()
                        vis_dict["battle_state"] = bs
                        vis_dict["render"] = ram_reader.render_battle()
                        vis_dict["result"] = "battle"
                    elif st == "dialog":
                        vis_dict["render"] = ram_reader.render_dialog()
                        vis_dict["result"] = "dialog"
                    elif st == "menu" or st == "list_menu":
                        ms = ram_reader.read_menu_state()
                        if ms.get("menu_id", 0) > 0:
                            vis_dict["render"] = ram_reader.render_menu()
                            vis_dict["result"] = "menu"

                # ── Battle start/end logging ──────────────────────
                if st == "battle" and _last_screen_type != "battle":
                    evt = {"cycle": cycle + 1, "event": "battle_start",
                           "battle_type": vis_dict.get("battle_state", {}).get("battle_type", "unknown")}
                    results.append(evt)
                    log_file.write(json.dumps(evt, default=str) + "\n")
                    log_file.flush()
                    safe_print(f"  [BATTLE-START] {vis_dict.get('battle_state', {}).get('battle_type', 'unknown')} battle began")
                elif st != "battle" and _last_screen_type == "battle":
                    evt = {"cycle": cycle + 1, "event": "battle_end", "next_screen": st}
                    results.append(evt)
                    log_file.write(json.dumps(evt, default=str) + "\n")
                    log_file.flush()
                    safe_print(f"  [BATTLE-END] → {st}")

                # ── Stuck detection: unified tracking + escalating recovery ──
                # Track same-screen (already tracked in overworld pipeline, but
                # StateWindow path handles other screen types — dialog, battle, menu)
                if st == _last_screen_type:
                    _same_screen_count += 1
                else:
                    _same_screen_count = 0
                _last_screen_type = st

                # State-change detection resets recovery counter
                state_key = f"{st}:{vis_dict.get('screen_subtype','')}"
                if state_key != _last_state_key and _last_state_key != "":
                    _recovery_attempts = 0
                    _recovery_level = 0
                    safe_print(f"  [STATE] Changed → {st} — recovery counter reset")
                _last_state_key = state_key

                # Check if recovery needed
                needs_recovery = False
                recovery_reason = ""
                if _gave_up:
                    pass
                elif tile_recovery_reason:
                    needs_recovery = True
                    recovery_reason = tile_recovery_reason
                elif _same_screen_count >= MAX_SAME_SCREEN_CYCLES and st != "overworld":
                    needs_recovery = True
                    recovery_reason = f"screen-locked ({st} x{_same_screen_count})"
                elif _same_dir_count >= MAX_STUCK_SAME_DIR:
                    needs_recovery = True
                    recovery_reason = f"direction-locked ({_same_dir} x{_same_dir_count})"

                starter_approached = False
                if needs_recovery:
                    if _recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
                        if not _gave_up:
                            _gave_up = True
                            safe_print(f"  [RECOVER] GIVING UP after {_recovery_attempts} attempts ({recovery_reason})")
                            evt = {"cycle": cycle + 1, "event": "recovery_exhausted",
                                   "reason": recovery_reason, "attempts": _recovery_attempts}
                            results.append(evt)
                            log_file.write(json.dumps(evt, default=str) + "\n")
                            log_file.flush()
                    else:
                        _recovery_attempts += 1
                        if (
                            "tile-locked" in recovery_reason
                            and USE_RAM_READER
                            and map_id == OAKS_LAB_MAP_ID
                            and party_count == 0
                        ):
                            starter_approached = _approach_first_starter(
                                emu, ram_reader
                            )
                        # ── Dialog fast-path ─────────────────────────
                        # A dialog box is NOT a stuck state — it needs A
                        # presses to advance the text. The generic ladder
                        # (START→B→B menu_redraw) is wrong here and was
                        # keeping the agent trapped in Oak's dialog for
                        # 70+ cycles. A-mash to advance the conversation.
                        if st == "dialog" and not starter_approached:
                            for _ in range(12):
                                emu.press_button("a", frames=_A_FRAMES)
                                emu.fast_forward(_FF_FRAMES)
                            strategy, desc = ("dialog_advance", "12× A — advancing dialog text")
                            safe_print(f"  [RECOVER] {strategy} — {desc} ({recovery_reason}) [attempt {_recovery_attempts}/{MAX_RECOVERY_ATTEMPTS}]")
                            evt = {"cycle": cycle + 1, "event": "recovery",
                                   "level": _recovery_level, "strategy": strategy,
                                   "reason": recovery_reason, "attempt": _recovery_attempts,
                                   "description": desc}
                            results.append(evt)
                            log_file.write(json.dumps(evt, default=str) + "\n")
                            log_file.flush()
                            trackers = _reset_recovery_trackers(
                                recovery_reason,
                                same_dir=_same_dir,
                                same_dir_count=_same_dir_count,
                                same_screen_count=_same_screen_count,
                                same_tile_count=_same_tile_count,
                                void_cycles=_void_cycles,
                                a_press_count=_a_press_count,
                            )
                            _same_dir = trackers.same_dir
                            _same_dir_count = trackers.same_dir_count
                            _same_screen_count = trackers.same_screen_count
                            _same_tile_count = trackers.same_tile_count
                            _void_cycles = trackers.void_cycles
                            _a_press_count = trackers.a_press_count
                            continue  # skip StateWindow, let next cycle re-classify
                        if starter_approached:
                            strategy, desc = (
                                "starter_approach",
                                "moved to the first Poké Ball and pressed A",
                            )
                        else:
                            strategy, desc = _escalating_recovery(
                                emu,
                                _recovery_level,
                                _last_direction,
                                _last_saved_slot,
                                game_state=patch_data,
                            )
                        _recovery_level += 1
                        # Blacklist the blocked direction on checkpoint restore
                        if strategy == "load_checkpoint" and _same_dir and _same_dir in _DIR_ROTATION:
                            _dir_blacklist.add(_same_dir)
                            safe_print(f"  [BLACKLIST] {_same_dir} added to blacklist: {_dir_blacklist}")
                        safe_print(f"  [RECOVER] Level {_recovery_level-1}: {strategy} — {desc} ({recovery_reason}) [attempt {_recovery_attempts}/{MAX_RECOVERY_ATTEMPTS}]")
                        evt = {"cycle": cycle + 1, "event": "recovery",
                               "level": _recovery_level - 1, "strategy": strategy,
                               "reason": recovery_reason, "attempt": _recovery_attempts,
                               "description": desc}
                        results.append(evt)
                        log_file.write(json.dumps(evt, default=str) + "\n")
                        log_file.flush()
                        trackers = _reset_recovery_trackers(
                            recovery_reason,
                            same_dir=_same_dir,
                            same_dir_count=_same_dir_count,
                            same_screen_count=_same_screen_count,
                            same_tile_count=_same_tile_count,
                            void_cycles=_void_cycles,
                            a_press_count=_a_press_count,
                        )
                        _same_dir = trackers.same_dir
                        _same_dir_count = trackers.same_dir_count
                        _same_screen_count = trackers.same_screen_count
                        _same_tile_count = trackers.same_tile_count
                        _void_cycles = trackers.void_cycles
                        _a_press_count = trackers.a_press_count
                        continue  # skip StateWindow, let next cycle re-classify

                state_type = st
                if vis_dict.get("screen_subtype") == "keyboard":
                    state_type = "name_entry"

                # ── Rival battle detection ────────────────────────
                if vis_dict.get("screen_subtype") == "rival_battle":
                    ctx.set_location("rival_battle")
                    battle_png = SCREENSHOT_DIR / f"BATTLE_{cycle+1:04d}.png"
                    img.save(battle_png)
                    evt = {
                        "cycle": cycle + 1,
                        "event": "RIVAL_BATTLE_REACHED",
                    }
                    results.append(evt)
                    log_file.write(json.dumps(evt, default=str) + "\n")
                    log_file.flush()
                    safe_print(f"  [!] RIVAL BATTLE REACHED at cycle {cycle+1}")

                # Battle windows execute one action against one fresh RAM read.
                # The former 12-step loop reused a stale cycle-20 move-menu
                # snapshot and generated multiple empty-arg RUN calls before
                # cron_runner could observe the next battle phase.
                win = StateWindow(
                    state_type,
                    ctx,
                    emu,
                    vis_dict,
                    generation="gen1",
                    max_steps=(
                        # Battle needs room to act: query → attack → verify
                        # within one window. max_steps=1 meant a single
                        # query_global consumed the whole budget each cycle
                        # and the battle never progressed (T192/T197 stall).
                        5 if state_type == "battle" else
                        (1 if state_type == "name_entry" else STATE_STEPS)
                    ),
                    hint_level=HINT_LEVEL,
                    use_ram_prompts=True,
                    failed_flee_attempts=_failed_flee_attempts,
                )
                result = win.run()
                if state_type == "battle":
                    _failed_flee_attempts = int(
                        result.get("_failed_flee_attempts", _failed_flee_attempts)
                    )
                emu.fast_forward(FAST_FORWARD_FRAMES)
                elapsed = time.time() - t0

                # --- Battle event logging ---
                battle_events = result.get("_battle_events", [])
                for be in battle_events:
                    safe_print(f"  [BATTLE] {be.get('event')}: {be.get('screen_type', be.get('outcome', '?'))}")

                # Extract last action
                last_action = "?"
                for h in reversed(win._history):
                    tc = h.get("tool_call", {})
                    if tc:
                        last_action = f"{tc.get('name','?')}({tc.get('arguments',{})})"
                        break

                entry = {
                    "cycle": cycle + 1,
                    "screen": st,
                    "state": state_type,
                    "action": last_action,
                    "elapsed_s": round(elapsed, 1),
                    "cartographer_raw": carto_raw,
                    "state_window_raw": "\n\n---\n".join(win._raw_responses) if getattr(win, '_raw_responses', None) else "",
                    "battle_events": battle_events,
                    "failed_flee_attempts": _failed_flee_attempts,
                }
                results.append(entry)
                log_file.write(json.dumps(entry, default=str) + "\n")
                log_file.flush()
                safe_print(f"  [{cycle+1}/{CYCLES}] {st} | {last_action} | {elapsed:.1f}s")

            # Handle progression
            if _cycle_dir_lock_warned:
                _dir_lock_warn_cycles += 1  # GAP-028 per-run lock-rate metric
            if st == "name_confirm" and patch_data.get("name_field"):
                if not ctx.player_name:
                    ctx.player_name = patch_data["name_field"]
                elif not ctx.rival_name:
                    ctx.rival_name = patch_data["name_field"]

            if st == "overworld" and ctx.location in ("title", "intro"):
                ctx.set_location("bedroom")
                ctx.add_goal("leave bedroom")
                ctx.add_goal("reach rival battle")

            # ── Checkpoint save every N cycles ────────────────────
            if (cycle + 1) % CHECKPOINT_INTERVAL == 0:
                try:
                    emu.save_state(_checkpoint_slot)
                    evt = {
                        "cycle": cycle + 1,
                        "event": "state_saved",
                        "slot": _checkpoint_slot,
                    }
                    results.append(evt)
                    log_file.write(json.dumps(evt, default=str) + "\n")
                    log_file.flush()
                    safe_print(f"  [CKPT] Saved state to slot {_checkpoint_slot}")
                    _last_saved_slot = _checkpoint_slot
                    _checkpoint_slot = (_checkpoint_slot + 1) % CHECKPOINT_SLOTS
                except Exception as exc:
                    safe_print(f"  [CKPT] Failed to save state: {exc}")

        except Exception:
            traceback.print_exc()
            err_entry = {"cycle": cycle + 1, "error": traceback.format_exc()}
            results.append(err_entry)
            log_file.write(json.dumps(err_entry, default=str) + "\n")
            log_file.flush()

    emu.stop()

    # Write log
    log_file.seek(0)
    log_file.truncate()
    for entry in results:
        log_file.write(json.dumps(entry, default=str) + "\n")
    log_file.close()

    # Summary
    screens = set(r.get("screen", "?") for r in results)
    safe_print(f"\n{_format_summary(run_id, len(results), screens, _dir_lock_warn_cycles, CYCLES, len(_visited_tiles))}")
    safe_print(f"Log: {log_path}")
    safe_print(f"Screenshots: {SCREENSHOT_DIR}")

    # Persist frame cache for the next run (cross-run dedup)
    if _frame_cache is not None:
        _frame_cache.save()
        safe_print(f"[{run_id}] Frame cache saved: {_frame_cache.unique_frames} unique "
                   f"frames / {_frame_cache.total_seen} total references "
                   f"({_frame_cache.stats()['max_entries']} max)")


if __name__ == "__main__":
    with _SGBSuppress():
        main()
