#!/usr/bin/env python3
"""Cron-friendly Pokemon AI runner. Designed to run autonomously."""
import sys, os, time, json, traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.core.emulator import Emulator
from src.core.global_context import GlobalContext
from src.core.state_window import StateWindow
from src.core.vision import VisionClient

# ── Config ──────────────────────────────────────────────────────────
ROM = "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
CYCLES = 20
STATE_STEPS = 5
FAST_FORWARD_FRAMES = 180  # ~3s of game time at 60fps, runs in ~14ms
LOG_DIR = Path("cron_logs")
LOG_DIR.mkdir(exist_ok=True)
run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = LOG_DIR / f"run_{run_id}.jsonl"

# ── Run ────────────────────────────────────────────────────────────
def main():
    results = []
    emu = Emulator(ROM)
    
    print(f"[{run_id}] Starting run...")
    
    # Skip intro
    emu.skip_intro(press_frames=30, wait_frames=60, repetitions=60)
    
    # Init
    ctx = GlobalContext(generation="gen1", location="intro")
    vision = VisionClient()
    
    for cycle in range(CYCLES):
        try:
            vis = vision.analyze(emu.capture(), game="gen1")
            st = vis.get("screen_type", "unknown")
            
            # Classify state
            state_type = st
            if vis.get("screen_subtype") == "keyboard":
                state_type = "name_entry"
            
            t0 = time.time()
            win = StateWindow(state_type, ctx, emu, vis, generation="gen1", max_steps=STATE_STEPS)
            result = win.run()
            emu.fast_forward(FAST_FORWARD_FRAMES)  # let game state settle
            elapsed = time.time() - t0
            
            # Extract last action
            last_action = "?"
            for h in reversed(win._history):
                tc = h.get("tool_call", {})
                if tc:
                    last_action = f"{tc.get('name','?')}({tc.get('arguments',{})})"
                    break
                elif h.get("role") == "recall":
                    last_action = f"recall({h.get('query','')})"
                    break
            
            entry = {
                "cycle": cycle + 1,
                "screen": st,
                "state": state_type,
                "action": last_action,
                "elapsed_s": round(elapsed, 1),
                "location": ctx.location,
                "goals": ctx.goals,
            }
            results.append(entry)
            
            # Handle name detection
            if st == "name_confirm" and vis.get("name_field"):
                if not ctx.player_name:
                    ctx.player_name = vis["name_field"]
                elif not ctx.rival_name:
                    ctx.rival_name = vis["name_field"]
            
            if st == "overworld" and ctx.location == "intro":
                ctx.set_location("bedroom")
                ctx.add_goal("leave bedroom")
                ctx.add_goal("reach rival battle")
            
            print(f"  [{cycle+1}/{CYCLES}] {st} | {last_action} | {elapsed:.1f}s")
            
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
    print(f"\n[{run_id}] Done. {len(results)} cycles. Screens: {screens}")
    print(f"Global: {ctx.compact()}")
    print(f"Log: {log_path}")

if __name__ == "__main__":
    main()
