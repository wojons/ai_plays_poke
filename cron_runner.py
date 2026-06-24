#!/usr/bin/env python3
"""Cron-friendly Pokemon AI runner with cartographer → controller pipeline.

Flow:
  1. Screenshot → classify screen type (VisionClient)
  2. If overworld: cartographer mode (Gemma 12B → OBS_PATCH → MapIntegrator)
  3. Controller (DeepSeek V4 Flash) reads composed view → button press
  4. Non-overworld: existing StateWindow flow
"""
import sys, os, time, json, traceback, base64, io
from pathlib import Path
from datetime import datetime

# ── Suppress emulator SGB warnings ──────────────────────────────────
# mGBA core prints "GB: Unimplemented SGB command: 0F" to stderr when
# running SGB-enhanced ROMs. These are harmless noise in cron runs.
class _SGBSuppress:
    """Context manager that filters SGB warnings from stderr."""
    def __init__(self):
        # These get set in __enter__
        self._real_stderr = sys.stderr
        self._real_stderr_fd = -1
        self._pipe_r = -1
        self._pipe_w = -1
        self._thread = None

    def __enter__(self):
        import threading
        self._pipe_r, self._pipe_w = os.pipe()
        self._real_stderr_fd = os.dup(2)
        os.dup2(self._pipe_w, 2)
        os.close(self._pipe_w)
        self._buf = []

        def _filter():
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

    def __exit__(self, *args):
        import threading
        os.dup2(self._real_stderr_fd, 2)
        os.close(self._real_stderr_fd)
        if self._pipe_r:
            os.close(self._pipe_r)
        # thread is daemon — will exit on its own

import yaml
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from src.core.emulator import Emulator
from src.core.global_context import GlobalContext
from src.core.state_window import StateWindow
from src.core.vision import VisionClient
from src.core.ai_client import OpenRouterClient
from src.core.world_state import WorldState
from src.core.map_integrator import MapIntegrator
from src.core.symbols import SYMBOL_REFERENCE

# ── Config ──────────────────────────────────────────────────────────
ROM = "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
CYCLES = 20
STATE_STEPS = 5
FAST_FORWARD_FRAMES = 600  # ~10s game time, ~50ms wall time
CART_STEPS = 12  # controller steps per overworld cycle
PRESS_FRAMES = 120  # hold button for 2s game time
STEP_FORWARD = 300  # fast-forward between steps (~5s game time)
WORLD_DIR = Path("world")
LOG_DIR = Path("cron_logs")
LOG_DIR.mkdir(exist_ok=True)
WORLD_DIR.mkdir(exist_ok=True)
run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = LOG_DIR / f"run_{run_id}.jsonl"

# ── Load cartographer prompt ────────────────────────────────────────
_carto_cfg = yaml.safe_load(
    Path("configs/prompts/gen1/cartographer.yaml").read_text()
)
CARTOGRAPHER_SYSTEM = _carto_cfg["system"].format(symbol_reference=SYMBOL_REFERENCE)
CARTOGRAPHER_TEMPLATE = _carto_cfg["user_template"]

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
    world: WorldState,
    last_result: str = "unknown",
) -> dict:
    """Send screenshot + world state to Gemma 12B, return OBS_PATCH dict."""
    # Build the user prompt
    current_terrain = world.composed_view()
    current_objects = "\n".join("".join(row) for row in world.objects[:15])
    current_actors = "\n".join(
        f"  {a.kind} at {a.pos} facing {a.facing} (conf={a.confidence:.0%})"
        for a in list(world.actors.values())[:10]
    )

    user_prompt = CARTOGRAPHER_TEMPLATE.format(
        prev_tick=world.tick,
        map_id=world.map_id,
        player_pos=str(list(world.player.pos)),
        player_facing=world.player.facing,
        player_mode=world.player.mode,
        viewport_origin=str(list(world.viewport.origin)),
        viewport_size=str(list(world.viewport.size)),
        last_button=world.last_button,
        last_result=last_result,
        current_terrain=current_terrain,
        current_objects=current_objects or "(empty)",
        current_actors=current_actors or "(none)",
    )

    img_b64 = screenshot_to_base64(screenshot)

    # Call Gemma 12B vision with OBS_PATCH prompt
    response = client.chat_completion(
        model="google/gemma-3-12b-it",
        messages=[
            {"role": "system", "content": CARTOGRAPHER_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                ],
            },
        ],
        temperature=0.1,
        max_tokens=4000,
    )

    text = response.get("content", "")
    return _extract_obs_patch(text)


def _extract_obs_patch(text: str) -> dict:
    """Extract OBS_PATCH from model response (handles markdown fences)."""
    text = text.strip()
    # Strip ``` fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if len(lines) > 1 else lines
        if lines and lines[-1].strip() in ("```", "```yaml", "```json"):
            lines = lines[:-1]
        text = "\n".join(lines)

    # Try JSON first, then YAML
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        return yaml.safe_load(text) or {}
    except Exception:
        return {"_parse_error": text[:500]}


def controller_decide(
    client: OpenRouterClient,
    world_view: str,
    last_button: str = "",
    last_result: str = "",
) -> dict:
    """Controller model (DeepSeek V4 Flash) decides next button press."""
    system = (
        "You are controlling a Pokémon game player character.\n\n"
        "Given the current world map and state, output exactly one button press.\n"
        "Respond with ONLY a JSON object:\n"
        '{"button": "UP|DOWN|LEFT|RIGHT|A|B|START|SELECT", "intent": "short reason"}\n\n'
        "RULES:\n"
        "- Prefer exploring unvisited tiles (? or never-seen areas)\n"
        "- If blocked, try another direction\n"
        "- Use A to interact with signs/doors/NPCs when adjacent\n"
        "- Use START to open menu if needed\n"
        "- Don't repeat the same blocked direction 3+ times in a row\n"
    )

    msg = (
        f"{world_view}\n\n"
        f"LAST BUTTON: {last_button or 'none'}\n"
        f"LAST RESULT: {last_result or 'unknown'}\n\n"
        "What button should I press next?  Output JSON only."
    )

    response = client.chat_completion(
        model="deepseek-chat",  # DeepSeek V4 Flash via direct API
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": msg},
        ],
        temperature=0.3,
        max_tokens=500,
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
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: try to find "{...}" 
        import re
        m = re.search(r'\{[^}]+\}', text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return {"button": "A", "intent": "parse_failure_fallback"}


# ── Main ────────────────────────────────────────────────────────────

def main():
    results = []
    emu = Emulator(ROM)

    # Init world state
    world = WorldState()
    world.init_blank(300, 280)  # generous for any Gen 1 map
    world.map_id = "pallet_town_unknown"
    integrator = MapIntegrator(world)

    # Init AI clients
    vision = VisionClient()
    controller_client = OpenRouterClient()  # uses DEEPSEEK_API_KEY from .env

    print(f"[{run_id}] Starting run with cartographer pipeline...")

    # Skip intro
    emu.skip_intro(press_frames=10, wait_frames=30, repetitions=120)

    ctx = GlobalContext(generation="gen1", location="intro")

    for cycle in range(CYCLES):
        try:
            screenshot = emu.capture()

            # Step 1: Quick screen classification
            vis = vision.analyze(screenshot, game="gen1")
            st = vis.get("screen_type", "unknown")

            t0 = time.time()

            if st == "overworld":
                # ── Cartographer pipeline ──────────────────────────
                # Step 2a: Cartographer → OBS_PATCH
                patch_data = cartographer_analyze(
                    controller_client, screenshot, world, world.last_result
                )

                if not patch_data.get("_parse_error"):
                    ok = integrator.apply(patch_data)
                    if not ok:
                        print(f"  [!] Patch rejected: {integrator.stats['recent_rejections'][-1:] if integrator.stats['recent_rejections'] else 'unknown'}")

                # Mark visited at player position
                px, py = world.player.pos
                integrator.world.visited[py][px] = "@" if 0 <= py < len(integrator.world.visited) and 0 <= px < len(integrator.world.visited[0]) else "?"

                # Save world state
                integrator.save(WORLD_DIR)

                # Step 2b: Controller decides actions (multiple steps)
                for _ in range(CART_STEPS):
                    world_view = integrator.compose_for_controller()
                    decision = controller_decide(
                        controller_client, world_view,
                        world.last_button, world.last_result,
                    )
                    button = decision.get("button", "A").upper()
                    intent = decision.get("intent", "")

                    # Execute
                    btn_map = {
                        "UP": "up", "DOWN": "down", "LEFT": "left", "RIGHT": "right",
                        "A": "a", "B": "b", "START": "start", "SELECT": "select",
                    }
                    btn = btn_map.get(button, "a")
                    emu.press_button(btn, frames=PRESS_FRAMES)
                    emu.fast_forward(STEP_FORWARD)  # let game respond

                    world.last_button = button
                    results.append({
                        "cycle": cycle + 1,
                        "screen": st,
                        "pipeline": "cartographer",
                        "button": button,
                        "intent": intent,
                    })

                elapsed = time.time() - t0
                print(f"  [{cycle+1}/{CYCLES}] {st} | cartographer x{CART_STEPS} | {elapsed:.1f}s")

            else:
                # ── Traditional StateWindow flow ───────────────────
                state_type = st
                if vis.get("screen_subtype") == "keyboard":
                    state_type = "name_entry"

                win = StateWindow(state_type, ctx, emu, vis, generation="gen1", max_steps=STATE_STEPS)
                result = win.run()
                emu.fast_forward(FAST_FORWARD_FRAMES)
                elapsed = time.time() - t0

                # Extract last action
                last_action = "?"
                for h in reversed(win._history):
                    tc = h.get("tool_call", {})
                    if tc:
                        last_action = f"{tc.get('name','?')}({tc.get('arguments',{})})"
                        break

                results.append({
                    "cycle": cycle + 1,
                    "screen": st,
                    "state": state_type,
                    "action": last_action,
                    "elapsed_s": round(elapsed, 1),
                })
                print(f"  [{cycle+1}/{CYCLES}] {st} | {last_action} | {elapsed:.1f}s")

            # Handle progression
            if st == "name_confirm" and vis.get("name_field"):
                if not ctx.player_name:
                    ctx.player_name = vis["name_field"]
                elif not ctx.rival_name:
                    ctx.rival_name = vis["name_field"]

            if st == "overworld" and ctx.location == "intro":
                ctx.set_location("bedroom")
                ctx.add_goal("leave bedroom")
                ctx.add_goal("reach rival battle")

        except Exception:
            traceback.print_exc()
            results.append({"cycle": cycle + 1, "error": traceback.format_exc()})

    emu.stop()

    # Write log
    with open(log_path, "w") as f:
        for entry in results:
            f.write(json.dumps(entry, default=str) + "\n")

    # Summary
    screens = set(r.get("screen", "?") for r in results)
    buttons = [r.get("button", r.get("action", "?")) for r in results if r.get("button")]
    print(f"\n[{run_id}] Done. {len(results)} actions. Screens: {screens}")
    print(f"Buttons: {buttons[-20:] if len(buttons) > 20 else buttons}")
    print(f"Integrator stats: {integrator.stats}")
    print(f"World saved to: {WORLD_DIR}")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    with _SGBSuppress():
        main()
