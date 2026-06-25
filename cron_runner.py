#!/usr/bin/env python3
"""Cron-friendly Pokemon AI runner with cartographer → controller pipeline.

Flow:
  1. Screenshot → classify screen type (VisionClient)
  2. If overworld: cartographer mode (Gemma 12B → OBS_PATCH → MapIntegrator)
  3. Controller (DeepSeek V4 Flash) reads composed view → button press
  4. Non-overworld: existing StateWindow flow
"""
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

# ── Config ──────────────────────────────────────────────────────────
ROM = "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
CYCLES = 200
STATE_STEPS = 12
USE_VISION_CLIENT = False  # True = debug mode (cheap classifier), False = Gemma 12B cartographer
HINT_LEVEL = 4  # 0=benchmark, 1=mechanics, 2=genre, 3=starter, 4=navigation
FAST_FORWARD_FRAMES = 600  # ~10s game time, ~50ms wall time
CART_STEPS = 12  # controller steps per overworld cycle
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
MAX_SAME_DIRECTION = 5     # blocked-direction threshold before rollback

# ── Load visual-reference cartographer prompt ────────────────────────
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

# ── Helpers ─────────────────────────────────────────────────────────

def screenshot_to_base64(screenshot: np.ndarray) -> str:
    """Convert numpy RGB screenshot to base64 data URL."""
    img = Image.fromarray(screenshot)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


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
        "- Walk toward visible exits (doors, stairs, paths).\n"
        "- If adjacent tile is 'wall' in one direction, do NOT try that direction.\n"
        "- If adjacent tile is 'door', walk into it (or press A on it).\n"
        "- If adjacent tile is 'npc', walk toward it and press A to talk.\n"
        "- If adjacent tile is 'stair', walk onto it.\n"
        "- When ALL directions are blocked (walls/objects all around): press A.\n"
        "- NEVER spam repeated button presses — plan one action per tile.\n"
        "- After interacting (A), next action should move away.\n"
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

    # Init AI clients
    if USE_VISION_CLIENT:
        vision = VisionClient()  # noqa: F841 — conditionally enabled debug classifier
    controller_client = OpenRouterClient()  # uses DEEPSEEK_API_KEY from .env

    print(f"[{run_id}] Starting run with visual-reference cartographer pipeline...")
    print(f"  Reference image: reference/bedroom_overworld.png")

    # ── Checkpoint / recovery state ────────────────────────────────
    _same_dir: str | None = None
    _same_dir_count: int = 0
    _checkpoint_slot: int = 0
    _last_saved_slot: int | None = None
    _dir_blacklist: set[str] = set()  # directions that caused checkpoint recovery
    _dir_rotation = {"UP": "RIGHT", "RIGHT": "DOWN", "DOWN": "LEFT", "LEFT": "UP"}
    _last_direction: str = ""  # last direction pressed (for controller context)
    _last_result: str = "unknown"  # last movement result

    # ── Void state recovery tracking ──────────────────────────────
    _void_cycles: int = 0       # consecutive cycles with >95% unknown tiles
    _recovery_attempts: int = 0  # recovery attempts in current void sequence
    _stuck_cycles: int = 0       # consecutive cycles with same screen + no progress
    _last_screen_type: str = ""  # for stuck detection

    # ── Deterministic intro bypass ──────────────────────────────────
    # Decoupled: A-mash aggressively in large batches, sparse cartographer
    # checks. Each cartographer call has 1-60s latency; we maximize
    # A-presses between checks so the intro progresses during API waits.
    print(f"[{run_id}] Bypassing intro via cartographer...")

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

        # Use cartographer for reliable screen classification
        patch_data, carto_raw = cartographer_analyze(
            controller_client, screenshot
        )
        st = patch_data.get("result", "unknown")

        # ── Save file detection: if we're in overworld without naming ──
        if st == "overworld" and not _player_named:
            tc = patch_data.get("text_content", [])
            if not tc:  # no dialog — definitely not intro
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
            print(f"  [intro] Cartographer says overworld — intro complete ({_intro_checks} checks)")
            break
        elif st == "name_entry":
            if not _player_named:
                print("  [intro] Entering player name ASH...")
                emu.enter_name("ASH")
                _player_named = True
                emu.wait(60)
                emu.press_button("a", frames=30)
                emu.wait(120)
            elif not _rival_named:
                print("  [intro] Entering rival name GARY...")
                emu.enter_name("GARY")
                _rival_named = True
                emu.wait(60)
                emu.press_button("a", frames=30)
                emu.wait(120)
            else:
                # Already named both — A-mash through naming screen
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

    # ── Step away from whatever we're facing ──────────────────────
    # The bedroom start position faces the TV; A-pressing creates an
    # infinite TV-interaction loop. Walk DOWN to get clear.
    print("  [intro] Stepping away from start position...")
    for _ in range(4):
        emu.press_button("down", frames=30)
        emu.fast_forward(60)
    # Clear any lingering dialog box
    emu.press_button("b", frames=30)
    emu.wait(30)

    # Save state after intro
    try:
        emu.save_state(0)
        _last_saved_slot = 0
        print("  [CKPT] Post-intro state saved to slot 0")
    except Exception as exc:
        print(f"  [CKPT] Failed to save post-intro state: {exc}")

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

            # Step 1: Cartographer classifies screen + spatial analysis
            patch_data, carto_raw = cartographer_analyze(
                controller_client, screenshot
            )
            st = patch_data.get("result", "unknown")

            t0 = time.time()

            if st == "overworld":
                # ── Visual-Reference Pipeline ──────────────────────
                # Cartographer already gave us spatial info (adjacent tiles,
                # visible_exits, player_facing, suggested_action).
                # Feed this directly to the controller — no MapIntegrator needed.

                # ── Void state detection (simplified: check if cartographer classified correctly) ──
                if st == "unknown":
                    _void_cycles += 1
                    print(f"  [VOID] Cartographer returned unknown (cycle {_void_cycles}/3)")
                else:
                    _void_cycles = 0
                    _recovery_attempts = 0

                if _void_cycles >= 3:
                    _recovery_attempts += 1
                    # Strategy: open/close menu to force redraw
                    emu.press_button("start", frames=30)
                    emu.wait(60)
                    emu.press_button("b", frames=10)
                    emu.wait(30)
                    emu.press_button("b", frames=10)
                    emu.wait(30)
                    strategy = "menu_redraw"

                    evt = {
                        "cycle": cycle + 1,
                        "event": "void_recovery",
                        "recovery_attempt": _recovery_attempts,
                        "strategy": strategy,
                    }
                    results.append(evt)
                    log_file.write(json.dumps(evt, default=str) + "\n")
                    log_file.flush()
                    print(f"  [RECOVER] Void recovery attempt {_recovery_attempts}: {strategy}")
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
                                if direction in _dir_blacklist and direction in _dir_rotation:
                                    direction = _dir_rotation[direction]
                                else:
                                    break
                            # If we cycled back to a blacklisted direction, all 4 blocked
                            if direction in _dir_blacklist:
                                direction = "A"  # interact instead
                        filtered_plan.append(direction)
                    if filtered_plan != [b.upper() for b in plan]:
                        print(f"  [OVERRIDE] Blacklisted {_dir_blacklist}, plan {plan[:6]}→{filtered_plan[:6]}...")
                    plan = filtered_plan

                plan_entry = {
                    "cycle": cycle + 1,
                    "screen": st,
                    "pipeline": "cartographer",
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
                        print(f"  [WARN] Direction-locking detected: {_same_dir} x3")

                    if _same_dir_count >= MAX_SAME_DIRECTION:
                        if _last_saved_slot is not None:
                            try:
                                emu.load_state(_last_saved_slot)
                                evt = {
                                    "cycle": cycle + 1,
                                    "event": "state_loaded",
                                    "slot": _last_saved_slot,
                                    "reason": f"blocked_{_same_dir}_x{_same_dir_count}",
                                }
                                results.append(evt)
                                log_file.write(json.dumps(evt, default=str) + "\n")
                                log_file.flush()
                                print(f"  [RECOVER] Loaded checkpoint slot {_last_saved_slot} (blocked {_same_dir} x{_same_dir_count})")
                                blocked = _same_dir
                                _same_dir = None
                                _same_dir_count = 0
                                if blocked and blocked in _dir_rotation:
                                    _dir_blacklist.add(blocked)
                                    print(f"  [BLACKLIST] {blocked} added to blacklist: {_dir_blacklist}")
                                break  # exit plan execution early
                            except Exception as exc:
                                print(f"  [RECOVER] Failed to load slot {_last_saved_slot}: {exc}")
                        else:
                            print(f"  [RECOVER] Direction-locked {_same_dir} x{_same_dir_count} but NO checkpoint available")

                elapsed = time.time() - t0
                print(f"  [{cycle+1}/{CYCLES}] {st} | cartographer x{CART_STEPS} | {elapsed:.1f}s")

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
                }

                # ── Stuck detection: if same non-overworld screen for 5+ cycles, break out ──
                if st == _last_screen_type and st != "overworld":
                    _stuck_cycles += 1
                else:
                    _stuck_cycles = 0
                _last_screen_type = st

                if _stuck_cycles >= 5:
                    print(f"  [STUCK] Same screen ({st}) for {_stuck_cycles} cycles — injecting breakout")
                    emu.press_button("b", frames=30)  # close any lingering dialog
                    emu.wait(30)
                    emu.press_button("down", frames=30)  # move away
                    emu.fast_forward(120)
                    _stuck_cycles = 0
                    # Log it
                    evt = {"cycle": cycle + 1, "event": "stuck_breakout", "screen": st}
                    results.append(evt)
                    log_file.write(json.dumps(evt, default=str) + "\n")
                    log_file.flush()
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
                    print(f"  [!] RIVAL BATTLE REACHED at cycle {cycle+1}")

                win = StateWindow(state_type, ctx, emu, vis_dict, generation="gen1", max_steps=STATE_STEPS, hint_level=HINT_LEVEL)
                win.run()
                emu.fast_forward(FAST_FORWARD_FRAMES)
                elapsed = time.time() - t0

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
                }
                results.append(entry)
                log_file.write(json.dumps(entry, default=str) + "\n")
                log_file.flush()
                print(f"  [{cycle+1}/{CYCLES}] {st} | {last_action} | {elapsed:.1f}s")

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
                    print(f"  [CKPT] Saved state to slot {_checkpoint_slot}")
                    _last_saved_slot = _checkpoint_slot
                    _checkpoint_slot = (_checkpoint_slot + 1) % CHECKPOINT_SLOTS
                except Exception as exc:
                    print(f"  [CKPT] Failed to save state: {exc}")

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
    print(f"\n[{run_id}] Done. {len(results)} actions. Screens: {screens}")
    print(f"Log: {log_path}")
    print(f"Screenshots: {SCREENSHOT_DIR}")


if __name__ == "__main__":
    with _SGBSuppress():
        main()
