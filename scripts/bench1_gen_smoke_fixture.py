"""Generate a fixture BENCH-1 episode log under cron_logs/ (gitignored) for
the CLI smoke of `benchmark_llm_vs_jev.py report`. Rows carry NO guard stamp
on purpose: report must stamp-and-verify them itself."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
# reuse the fixture builders from the driver test module
sys.path.insert(0, str(Path(__file__).resolve().parent))


def episode_row(**over):
    row = {
        "at": "2026-09-28T00:00:00Z",
        "run_id": "bench1_llm_ep1_smoke",
        "arm": "llm",
        "episode": 1,
        "exit_code": 0,
        "wall_time_s": 25.0,
        "cycles_requested": 5,
        "boot_state": "data/boot.state",
        "boot_sha256": "a" * 64,
        "ram_md5_before_episode": None,
        "cycles": 5,
        "decisions": 5,
        "real_decisions": 5,
        "fallback_decisions": 0,
        "jev_answered": 0,
        "jev_answered_true_rows": [],
        "escalated": 0,
        "jev_transport_failures": 0,
        "jev_error_rows": 0,
        "missing_classes": {},
        "teacher_calls": 0,
        "teacher_improved": 0,
        "model_build": None,
        "cost_usd_observed": 0.01,
        "tiles_visited_distinct": 4,
        "map_sequence": [{"cycle": 1, "map": "Pallet Town"}],
        "maps_seen": ["Pallet Town"],
        "map_transitions": [],
        "first_map_transition_cycle": None,
        "final_map": "Pallet Town",
        "recovery_events": 1,
        "lock_warn_cycles": 1,
        "lock_total_cycles": 5,
        "lock_rate": 0.2,
        "autonomy": {
            "decisions_total": 5,
            "jev_answered": 0,
            "escalated": 0,
            "autonomy_ratio": 0.0,
            "teacher_escalations": {"count": 0, "improved": 0},
        },
        "decision_mode_log": "llm",
        "run_completed": True,
        "errors": [],
    }
    row.update(over)
    return row


rows = [
    episode_row(),
    episode_row(
        run_id="bench1_jev_ep1_smoke",
        arm="jev",
        decisions=7,
        real_decisions=6,
        fallback_decisions=1,
        jev_answered=7,
        teacher_calls=2,
        teacher_improved=1,
        cost_usd_observed=0.0004,
        lock_warn_cycles=0,
        lock_total_cycles=5,
        lock_rate=0.0,
        autonomy={
            "decisions_total": 7,
            "jev_answered": 7,
            "escalated": 0,
            "autonomy_ratio": 1.0,
            "teacher_escalations": {"count": 2, "improved": 1},
        },
        decision_mode_log="jev",
    ),
]
out = (
    Path(__file__).resolve().parent.parent / "cron_logs" / "bench1_fixture_smoke.jsonl"
)
out.write_text("".join(json.dumps(r) + "\n" for r in rows))
print(f"wrote {out}")
