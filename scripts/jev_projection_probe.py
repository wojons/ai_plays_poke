#!/usr/bin/env python3
"""Live end-to-end: real emulator RAM -> bounded projection -> Jev decision.

Runs a short deterministic walk to generate GENUINE cross-cycle state (visited
tiles with repeat counts, whether the last action changed anything), builds the
projection, and asks Jev. Prints the exact text Jev saw plus its answer and the
gate verdict — so the projection's adequacy is measured, not asserted.

Usage:
  python3 scripts/jev_projection_probe.py [state_path] [--presses RIGHT,DOWN,A]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.emulator import Emulator  # noqa: E402
from src.core.ram_reader import RAMReader  # noqa: E402
from src.core.state_projection import DEFAULT_MECHANICS, build  # noqa: E402
from src.core.jev_client import decide  # noqa: E402

ROM = "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"


def run(state_path: str, presses: list[str]) -> dict:
    emu = Emulator(ROM)
    emu.load_state(Path(state_path))
    emu.fast_forward(60)
    rr = RAMReader(emu, ROM)

    visited: dict[tuple[int, int], int] = {}
    events: list[dict] = []
    last_action, last_changed = "", None

    obs = rr.observe()
    tile_x = obs.get("player_tile_x")
    tile_y = obs.get("player_tile_y")
    tile = (
        tile_x if isinstance(tile_x, int) else 0,
        tile_y if isinstance(tile_y, int) else 0,
    )
    visited[tile] = visited.get(tile, 0) + 1

    for i, btn in enumerate(presses, 1):
        before = (rr.player_tile_x(), rr.player_tile_y())
        emu.press_button(btn.lower(), frames=8)
        emu.fast_forward(40)
        after = (rr.player_tile_x(), rr.player_tile_y())
        changed = before != after
        visited[after] = visited.get(after, 0) + 1
        events.append(
            {"cycle": i, "action": btn, "result": "moved" if changed else "no change"}
        )
        last_action, last_changed = btn, changed

    obs = rr.observe()
    projection = build(
        obs,
        goal="obtain a usable Pokemon and progress the game",
        visited=visited,
        recent_events=events,
        last_action=last_action,
        last_action_changed_state=last_changed,
        mechanics=DEFAULT_MECHANICS,
    )

    print("=" * 74)
    print(f"PROJECTION SENT TO JEV  (state={state_path}, {len(projection)} chars)")
    print("=" * 74)
    print(projection)
    print("=" * 74)

    d = decide(projection, last_action_failed=(last_changed is False))
    print("\nJEV DECISION")
    print(
        f"  ok={d.get('ok')}  model={d.get('model_build')}  "
        f"latency={d.get('latency_s')}s  cost=${(d.get('cost_usd') or 0):.8f}"
    )
    if d.get("ok"):
        print(f"  next_action      = {d['next_action']}")
        print(f"  phase            = {d['phase']}")
        print(f"  action_confidence= {d['action_confidence']}")
        print(f"  sufficient_state = {d['sufficient_state']}")
        print(f"  ambiguity        = {d['ambiguity']}")
        print(f"  missing_class    = {d['missing_class']}")
        print(f"  progress         = {d['progress']}")
    else:
        print("  ERROR:", d.get("error"))
    print(f"  --> ESCALATE={d['escalate']}  ({d['escalate_reason']})")

    emu.stop()
    return {"state": state_path, "chars": len(projection), "decision": d}


if __name__ == "__main__":
    state = sys.argv[1] if len(sys.argv) > 1 else "data/boot.state"
    presses = ["RIGHT", "RIGHT", "DOWN", "DOWN", "A", "A"]
    if "--presses" in sys.argv:
        presses = sys.argv[sys.argv.index("--presses") + 1].split(",")
    out = run(state, presses)
    Path("/tmp/jev_projection_probe.json").write_text(
        json.dumps(out, indent=1, default=str)
    )
    print("\nWROTE /tmp/jev_projection_probe.json")
