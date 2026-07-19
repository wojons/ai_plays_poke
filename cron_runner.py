#!/usr/bin/env python3
"""Cron-friendly Pokemon AI runner with RAM reader / cartographer → controller pipeline.

Flow:
  1. Observe game state (RAM reader OR Gemma 12B cartographer)
  2. If overworld: controller (DeepSeek V4 Flash) reads spatial data → button plan
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

from typing import Any
import sys
import os
import time
import json
import traceback
import base64
import io
import threading
import yaml
import numpy as np
from pathlib import Path
from datetime import datetime
from PIL import Image

# ── Suppress emulator SGB warnings ──────────────────────────────────
# mGBA core prints "GB: Unimplemented SGB command: 0F" to stderr when
# running SGB-enhanced ROMs. These are harmless noise in cron runs.
class _SGBSuppress:
    """Context manager that filters SGB warnings from stderr."""
    def __init__(self) -> None:
        # These get set in __enter__
        self._real_stderr = sys.stderr
        self._real_stderr_fd = -1
        self._pipe_r = -1
        self._pipe_w = -1
        self._thread: threading.Thread | None = None

    def __enter__(self) -> '_SGBSuppress':
        self._pipe_r, self._pipe_w = os.pipe()
        self._real_stderr_fd = os.dup(2)
        os.dup2(self._pipe_w, 2)
        os.close(self._pipe_w)
        self._buf: list[str] = []

        def _filter() -> None:
            while True:
                data = os.read(self._pipe_r, 4096)
                if not data:
                    break
                for line in data.decode(errors="replace").split("\n"):
                    if line and "Unimplemented SGB" not in line:
                        self._buf.append(line)
                        self._real_stderr.write(line + "\n")
                        self._real_stderr.flush()

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

# ── Config ──────────────────────────────────────────────────────────
ROM = "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
CYCLES = 200
STATE_STEPS = 12
USE_VISION_CLIENT = False  # True = debug mode (cheap classifier), False = Gemma 12B cartographer
USE_RAM_READER = True   # True = RAM-based state reader (instant, free), False = Gemma 12B cartographer
HINT_LEVEL = 4  # 0=benchmark, 1=mechanics, 2=genre, 3=starter, 4=navigation
FAST_FORWARD_FRAMES = 600  # ~10s game time, ~50ms wall time
CART_STEPS = 6  # controller steps per overworld cycle (reduced from 12 — short moves, more cartographer feedback)
PRESS_FRAMES = 120  # hold button for 2s game time
STEP_FORWARD = 300  # fast-forward between steps (~5s game time)
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
MAX_VOID_CYCLES = 3           # >95% unknown-tile cycles → void
MAX_STUCK_SAME_DIR = 4        # same direction N times → direction-locked
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

def screenshot_to_base64(screenshot: np.ndarray) -> str:
    """Convert numpy RGB screenshot to base64 data URL."""
    img = Image.fromarray(screenshot)
    # Scale 3x with nearest-neighbor (pixel-perfect) so the vision model
    # can distinguish wall edges from floor seams at 144x160 native res.
    img = img.resize((img.width * 3, img.height * 3), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _escalating_recovery(
    emu,
    recovery_level: int,
    last_direction: str,
    last_saved_slot: int | None,
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
    """
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
        emu, recovery_level + 1, last_direction, last_saved_slot
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
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try finding JSON object with regex
    import re
    m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
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
    last_button: str = "",
    last_result: str = "",
    blocked_dir: str = "",
    blocked_count: int = 0,
    max_actions: int = 12,
) -> dict[str, Any]:
    """Controller model (DeepSeek V4 Flash) outputs a movement PLAN.

    Now takes the cartographer's spatial JSON directly (adjacent tiles,
    visible_exits, player_facing, suggested_action) instead of an ASCII
    tile map. The model gets richer, more accurate spatial info.
    """
    # Build a compact spatial summary string
    facing = spatial_desc.get("player_facing", "?")
    adj = spatial_desc.get("adjacent", {})
    exits = spatial_desc.get("visible_exits", [])
    suggested = spatial_desc.get("suggested_action", "")
    text = spatial_desc.get("text_content", [])

    adj_str = ", ".join(f"{d}={adj.get(d, '?')}" for d in ["up", "down", "left", "right"])
    exits_str = "; ".join(exits) if exits else "none visible"
    text_str = " | ".join(text) if text else "none"

    spatial_summary = (
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
        "- OUTDOOR areas (grass, paths visible): 4-6 tile moves OK.\n"
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
        f"Output a movement plan (max {max_actions} actions). JSON only."
    )

    response = client.chat_completion(
        model="deepseek-chat",  # DeepSeek V4 Flash via direct API
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": msg},
        ],
        temperature=0.3,
        max_tokens=1000,
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

def main() -> None:
    results = []
    emu = Emulator(ROM)

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

    # ── Stuck detection (3 independent dimensions) ──────────────────
    _same_dir: str | None = None   # last repeated direction
    _same_dir_count: int = 0       # consecutive same-direction presses
    _same_screen_count: int = 0    # consecutive cycles on same screen type
    _last_screen_type: str = ""    # for same-screen detection
    _void_tile_pct: float = 0.0    # % of tiles classified as unknown/void
    _void_cycles: int = 0          # consecutive cycles with >95% void tiles

    # ── Escalating recovery ────────────────────────────────────────
    _recovery_level: int = 0       # current rung of the escalation ladder
    _recovery_attempts: int = 0    # total recovery escalations (capped at MAX)
    _last_state_key: str = ""      # composite key for state-change detection
    _gave_up: bool = False         # True once max recovery attempts exhausted

    # ── Frame hashing for cartographer cache ───────────────────────
    _last_frame_hash: str = ""   # for frame hashing — skip cartographer on identical frames
    _cached_patch: dict[str, Any] = {}  # cached cartographer output
    _cached_carto_raw: str = ""  # cached raw cartographer text

    # ── Deterministic intro bypass ──────────────────────────────────
    # Decoupled: A-mash aggressively in large batches, sparse
    # observation checks (RAM reader is instant, cartographer has 1-60s latency).
    # RAM reader path: instant state reads, no LLM calls.
    safe_print(f"[{run_id}] Bypassing intro via {pipeline_name}...")

    # Step 1: Title screen → press START
    emu.bypass_title()
    # Wait for Oak's intro to finish and main menu to appear
    emu.wait(120)
    # Press A — if no save file, this selects NEW GAME directly.
    # If save exists, cursor is on CONTINUE — we'll detect old save below.
    emu.press_button("a", frames=15)
    emu.wait(120)  # let game load (or Oak appear)

    _player_named = False
    _rival_named = False
    _intro_checks = 0
    _MAX_INTRO_CHECKS = 12
    _A_BURST = 60       # A-presses per batch (was 10 — not enough for full intro)
    _A_FRAMES = 20      # hold A for 20 frames each press
    _FF_FRAMES = 120    # fast-forward between presses
    _save_detected = False  # set True if we loaded a save file by mistake

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
            print(f"  [intro] {pipeline_name} says overworld — intro complete ({_intro_checks} checks)")
            break
        elif st == "name_entry":
            # A-mash through name entry screens during intro bypass.
            # The proper keyboard navigation (StateWindow + keyboard_grid)
            # handles naming in the main loop. Here we just rush past.
            if not _player_named:
                _player_named = True
            elif not _rival_named:
                _rival_named = True
            for _ in range(_A_BURST):
                emu.press_button("a", frames=_A_FRAMES)
                emu.fast_forward(_FF_FRAMES)
        elif st == "title":
            emu.press_button("start", frames=30)
            emu.wait(90)
        else:
            # dialog / name_confirm / cutscene / unknown — A-mash aggressively
            for _ in range(_A_BURST):
                emu.press_button("a", frames=_A_FRAMES)
                emu.fast_forward(_FF_FRAMES)

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
    # Path: center → DOWN to bottom row → LEFT along bottom to stairs.
    # Sleeping Pokémon Red/Blue speedrun strat. DOWN from center is
    # obstacle-free; LEFT traverses the bottom row to the stairs at
    # bottom-left. Stairs auto-transition on contact.
    safe_print("  [intro] Walking to bedroom stairs (DOWN then LEFT)...")
    for _ in range(5):
        emu.press_button("down", frames=30)
        emu.fast_forward(60)
    emu.wait(15)
    for _ in range(4):
        emu.press_button("left", frames=30)
        emu.fast_forward(60)
    emu.wait(90)  # let the stairs transition happen

    ctx = GlobalContext(generation="gen1", location="bedroom")
    # If we bypassed the intro, set player/rival names
    if _player_named:
        ctx.player_name = "ASH"
    if _rival_named:
        ctx.rival_name = "GARY"

    # Open log file for incremental writing (web viewer polls this)
    log_file = open(log_path, "w")
    log_file.write("")  # create/truncate
    log_file.flush()

    for cycle in range(CYCLES):
        try:
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

            t0 = time.time()

            if st == "overworld":
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
                        safe_print(f"  [VOID] {unknown_tiles}/{total_tiles} tiles unknown ({_void_tile_pct:.0%}) — cycle {_void_cycles}/{MAX_VOID_CYCLES}")
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
                elif _same_dir_count >= MAX_STUCK_SAME_DIR:
                    needs_recovery = True
                    recovery_reason = f"direction-locked ({_same_dir} x{_same_dir_count})"
                elif _same_screen_count >= MAX_SAME_SCREEN_CYCLES and _last_screen_type != "overworld":
                    needs_recovery = True
                    recovery_reason = f"screen-locked ({_last_screen_type} x{_same_screen_count})"
                elif _void_cycles >= MAX_VOID_CYCLES:
                    needs_recovery = True
                    recovery_reason = f"void-locked ({_void_cycles} cycles, {_void_tile_pct:.0%} unknown)"

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
                        strategy, desc = _escalating_recovery(
                            emu, _recovery_level, _last_direction,
                            _last_saved_slot
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
                        # Reset the triggering tracker
                        if "direction-locked" in recovery_reason:
                            _same_dir = None
                            _same_dir_count = 0
                        elif "screen-locked" in recovery_reason:
                            _same_screen_count = 0
                        elif "void-locked" in recovery_reason:
                            _void_cycles = 0

                # Step 2b: Controller outputs movement PLAN from spatial description
                decision = controller_plan(
                    controller_client, patch_data,
                    _last_direction or "",
                    _last_result,
                    blocked_dir=_same_dir or "",
                    blocked_count=_same_dir_count,
                    max_actions=CART_STEPS,
                )
                plan = decision.get("plan", ["A"])
                intent = decision.get("intent", "")

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
                adj_data = patch_data.get("adjacent", {})
                _blocked_spatial = {d for d, v in adj_data.items()
                                    if v in ("wall", "object")}
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
                    "cartographer_raw": carto_raw,
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
                    else:
                        _same_dir = None
                        _same_dir_count = 0

                    if _same_dir_count == 3:
                        safe_print(f"  [WARN] Direction-locking detected: {_same_dir} x3")
                    # Recovery is now handled centrally in the stuck-detection block
                    # after cartographer analysis, using the escalating recovery ladder.

                elapsed = time.time() - t0
                safe_print(f"  [{cycle+1}/{CYCLES}] {st} | {pipeline_name} x{CART_STEPS} | {elapsed:.1f}s")

            elif st == "name_entry":
                # ── Name entry bypass ─────────────────────────────
                # pygba/mGBA doesn't register directional input on the
                # name entry keyboard. The cursor never moves with
                # press_button('down', frames=N). So we A-mash through
                # name entry just like the intro bypass: 60 rapid A
                # presses to type characters, eventually filling the
                # name field and advancing past the screen.
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
                safe_print(f"  [{cycle+1}/{CYCLES}] {st} | name_bypass (x{_A_BURST}) | {elapsed:.1f}s")

            else:
                # ── Traditional StateWindow flow ───────────────────
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
                elif _same_screen_count >= MAX_SAME_SCREEN_CYCLES and st != "overworld":
                    needs_recovery = True
                    recovery_reason = f"screen-locked ({st} x{_same_screen_count})"
                elif _same_dir_count >= MAX_STUCK_SAME_DIR:
                    needs_recovery = True
                    recovery_reason = f"direction-locked ({_same_dir} x{_same_dir_count})"

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
                        strategy, desc = _escalating_recovery(
                            emu, _recovery_level, _last_direction,
                            _last_saved_slot
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
                        _same_screen_count = 0
                        _same_dir = None
                        _same_dir_count = 0
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

                win = StateWindow(state_type, ctx, emu, vis_dict, generation="gen1", max_steps=(1 if state_type == "name_entry" else STATE_STEPS), hint_level=HINT_LEVEL, use_ram_prompts=True)
                result = win.run()
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
                }
                results.append(entry)
                log_file.write(json.dumps(entry, default=str) + "\n")
                log_file.flush()
                safe_print(f"  [{cycle+1}/{CYCLES}] {st} | {last_action} | {elapsed:.1f}s")

            # Handle progression
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
    safe_print(f"\n[{run_id}] Done. {len(results)} actions. Screens: {screens}")
    safe_print(f"Log: {log_path}")
    safe_print(f"Screenshots: {SCREENSHOT_DIR}")


if __name__ == "__main__":
    with _SGBSuppress():
        main()
