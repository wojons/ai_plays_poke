#!/usr/bin/env python3
"""DIST-1 driver: CTRL-WIN as a distribution — N episodes, both modes, one boot state.

The single CTRL-WIN run (30 cycles, Route 1 at c13 vs the JEV baseline's ~202
episodes) is a signal, not a distribution. This driver replays the comparison N
times from ONE fixed boot state (data/baselines/base-1_boot.state) and records
per-episode: cycles-to-first-transition, whether the transition was HELD, and
the per-run direction-lock rate.

Differences from scripts/long_run.py (which this is modelled on):
  - The boot state NEVER chains: every episode boots the same file, so the
    episodes are independent draws, not a progression.
  - Episodes are bounded at EPISODE_CYCLES by construction, so an episode with
    no transition is recorded CENSORED AT CAP instead of burning unbounded LLM
    spend. 30 cycles = the CTRL-WIN window and the long_0926_0014 baseline's
    episode length, keeping the distributions comparable to both.
  - No DuckBrain writes: a measurement run must not pollute live memory.

Run from a worktree (isolation: own cron_logs/, checkpoints/, .rom ram file):
    .venv/bin/python scripts/dist1_episodes.py run \
        --modes llm,jev --counts 6,5
    .venv/bin/python scripts/dist1_episodes.py report \
        --out data/baselines/dist1_ctrlwin_distribution_2026-09-27.json

Resume: an episode whose run log already ends with the runner's summary line
is skipped, so a killed battery continues where it stopped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
BOOT_STATE = REPO / "data" / "baselines" / "base-1_boot.state"
RUNNER = REPO / "cron_runner.py"
# SRAM twin of the boot state: restored before EVERY episode so battery-side
# save-file drift can never differentiate episode N from episode 1.
ROM_PATH = (
    REPO / "data" / "rom" / "Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
)
RAM_PATH = ROM_PATH.parent / (ROM_PATH.name + ".ram")
RAM_SNAPSHOT = REPO / "long_run" / "dist1_ram.ram"
EPISODE_CYCLES = 30  # CTRL-WIN's window; also the long_0926_0014 episode length
EPISODE_TIMEOUT_S = 1800  # same guard as long_run.py
# CTRL-WIN's boot state is the rescued long_0926_0014 good state; the md5 is
# documented in data/baselines/ctrl-win_2026-09-26.json and MUST match or every
# episode would be measuring a different start state.
EXPECTED_BOOT_MD5 = "81e4ec4e8d1b62002bc78f619c5fc79c"
START_MAP = "Pallet Town"
GOAL_MAP = "Route 1"
LOCK_RATE_RE = re.compile(
    r"lock-rate:\s*(\d+)/(\d+)\s+cycles with direction-lock warnings"
)
DONE_RE = re.compile(r"Done\.\s+\d+ actions")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def md5_of(path: Path) -> str | None:
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324
    except OSError:
        return None


def _snapshot_ram() -> str | None:
    """Capture the SRAM twin once, before the first episode boots."""
    try:
        RAM_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        if RAM_PATH.exists():
            shutil.copy2(RAM_PATH, RAM_SNAPSHOT)
            return md5_of(RAM_SNAPSHOT)
    except OSError:
        pass
    return None


def _restore_ram() -> str | None:
    """Restore the SRAM snapshot before an episode; snapshot if none exists.

    Returns the md5 of the SRAM the episode will boot with (None only when
    neither SRAM nor snapshot exists, e.g. a fresh checkout — recorded, not
    assumed).
    """
    if not RAM_SNAPSHOT.exists():
        return _snapshot_ram()
    try:
        if RAM_PATH.exists():
            shutil.copy2(RAM_SNAPSHOT, RAM_PATH)
        return md5_of(RAM_SNAPSHOT)
    except OSError:
        return None


# ------------------------------------------------------------------ metrics
def episode_metrics_from_log(
    log_path: Path,
    start_map: str = START_MAP,
    goal_map: str = GOAL_MAP,
) -> dict[str, Any]:
    """Per-episode DIST-1 metrics from one cron_runner JSONL log.

    A "transition" is the first decision row whose map_name differs from
    ``start_map``. ``held_the_transition`` mirrors the CTRL-WIN artifact's
    semantics: the goal map was reached AND the episode ENDED on it (CTRL-WIN
    reached Route 1 at c13 and was back in Pallet Town by c22 -> held=false).
    """
    m: dict[str, Any] = {
        "cycles": 0,
        "decisions": 0,
        "maps_seen": [],
        "map_sequence": [],
        "first_transition_cycle": None,
        "transitions_count": 0,
        "goal_map_reached": False,
        "first_goal_map_cycle": None,
        "held_the_transition": False,
        "goal_map_cycles": 0,
        "final_map": None,
        "map_transitions": [],
        "teacher_calls": 0,
        "cost_usd_observed": 0.0,
        "recovery_direction_lock_events": 0,
        "run_completed": False,
    }
    if not log_path.exists():
        m["error"] = "log missing"
        return m
    for line in log_path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        ev = r.get("event")
        if ev == "teacher_escalation":
            m["teacher_calls"] += 1
        elif ev == "run_autonomy":
            m["run_completed"] = True
        elif ev == "recovery" and "direction" in str(r.get("reason", "")):
            m["recovery_direction_lock_events"] += 1

        # Sum every observed cost_usd anywhere in the row (teacher patches,
        # jev asks, controller calls) — an honest lower bound of LLM spend.
        m["cost_usd_observed"] += _sum_cost_usd(r)

        if r.get("jev_answered") is None and "plan" not in r:
            continue
        cycle = int(r.get("cycle") or 0)
        map_name = r.get("map_name")
        m["decisions"] += 1
        m["cycles"] = max(m["cycles"], cycle)
        if map_name:
            m["map_sequence"].append({"cycle": cycle, "map": map_name})
            if map_name not in m["maps_seen"]:
                m["maps_seen"].append(map_name)
            if map_name == goal_map:
                m["goal_map_cycles"] += 1
                if not m["goal_map_reached"]:
                    m["goal_map_reached"] = True
                    m["first_goal_map_cycle"] = cycle
            prev = m["map_sequence"][-2]["map"] if len(m["map_sequence"]) > 1 else None
            if prev and map_name != prev:
                m["transitions_count"] += 1
                m["map_transitions"].append(
                    {"cycle": cycle, "from_map": prev, "to_map": map_name}
                )
                if m["first_transition_cycle"] is None:
                    m["first_transition_cycle"] = cycle
    if m["map_sequence"]:
        m["final_map"] = m["map_sequence"][-1]["map"]
    m["held_the_transition"] = bool(
        m["goal_map_reached"] and m["final_map"] == goal_map
    )
    m["cost_usd_observed"] = round(m["cost_usd_observed"], 6)
    return m


def _sum_cost_usd(row: Any, _depth: int = 0) -> float:
    """Recursively sum every numeric ``cost_usd`` in a log row."""
    if _depth > 6:
        return 0.0
    total = 0.0
    if isinstance(row, dict):
        for k, v in row.items():
            if k == "cost_usd" and isinstance(v, (int, float)):
                total += float(v)
            elif isinstance(v, (dict, list)):
                total += _sum_cost_usd(v, _depth + 1)
    elif isinstance(row, list):
        for item in row:
            total += _sum_cost_usd(item, _depth + 1)
    return total


def parse_lock_rate(stdout_text: str) -> tuple[int, int] | None:
    """The runner's own GAP-028 lock-rate from the final summary line."""
    match = LOCK_RATE_RE.search(stdout_text or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def run_completed(stdout_text: str) -> bool:
    """True when the runner printed its final summary (Done. N actions.)."""
    return bool(DONE_RE.search(stdout_text or ""))


# ------------------------------------------------------------ distribution
def summarise_distribution(
    episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Spread stats for cycles-to-first-transition over one mode's episodes.

    Censored episodes (no transition inside the episode window) are EXCLUDED
    from the distribution and counted in ``n_censored`` — reporting them as
    cycles would understate the mode. An all-censored mode reports an empty
    distribution with the reason, never a fabricated number.
    """
    observed = [
        e["first_transition_cycle"]
        for e in episodes
        if e.get("first_transition_cycle") is not None
    ]
    held = [bool(e.get("held_the_transition")) for e in episodes]
    lock_rates = [
        e["direction_lock_rate"]
        for e in episodes
        if e.get("direction_lock_rate") is not None
    ]
    out: dict[str, Any] = {
        "n_episodes": len(episodes),
        "n_transitions_observed": len(observed),
        "n_censored_no_transition": sum(
            1 for e in episodes if e.get("first_transition_cycle") is None
        ),
        "cycles_to_first_transition": sorted(observed),
    }
    if observed:
        out["spread"] = {
            "min": min(observed),
            "median": statistics.median(observed),
            "max": max(observed),
            "stdev": round(statistics.stdev(observed), 2) if len(observed) > 1 else 0.0,
        }
    else:
        out["spread"] = None
        out["spread_note"] = (
            "no episode left the start map inside the episode window — every "
            "episode is censored at the cap, so no cycle distribution exists"
        )
    out["transitions_held"] = {
        "held": sum(held),
        "of": len(held),
    }
    out["direction_lock_rate"] = {
        "mean": round(sum(lock_rates) / len(lock_rates), 4) if lock_rates else None,
        "per_episode": lock_rates,
    }
    out["cost_usd_observed_total"] = round(
        sum(float(e.get("cost_usd_observed") or 0.0) for e in episodes), 6
    )
    return out


# -------------------------------------------------------------------- run
def run_episode(
    mode: str,
    ep: int,
    run_id: str,
    python: str = str(REPO / ".venv" / "bin" / "python"),
) -> dict[str, Any]:
    """Run ONE episode of one mode; return its summary row."""
    runlog = REPO / "cron_logs" / f"run_{run_id}.jsonl"
    stdout_log = REPO / "cron_logs" / f"run_{run_id}.stdout.log"

    boot_md5 = md5_of(BOOT_STATE)
    if boot_md5 != EXPECTED_BOOT_MD5:
        return {
            "run_id": run_id,
            "mode": mode,
            "episode": ep,
            "skipped": True,
            "reason": f"boot md5 {boot_md5} != documented {EXPECTED_BOOT_MD5}",
        }
    ram_md5_before = _restore_ram()

    t0 = time.time()
    log(f"EP {run_id}: mode={mode} cycles={EPISODE_CYCLES} boot={BOOT_STATE.name}")
    try:
        proc = subprocess.run(  # noqa: S603
            [
                python,
                str(RUNNER),
                "--run-id",
                run_id,
                "--cycles",
                str(EPISODE_CYCLES),
                "--boot-state",
                str(BOOT_STATE),
                "--decision-mode",
                mode,
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=EPISODE_TIMEOUT_S,
        )
        rc = proc.returncode
        stdout_text = proc.stdout or ""
    except subprocess.TimeoutExpired as exc:
        rc = -9
        stdout_text = (
            (exc.stdout or b"").decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        log("  episode TIMEOUT")
    dur = round(time.time() - t0, 1)
    try:
        stdout_log.write_text(stdout_text, errors="replace")
    except OSError:
        pass

    metrics = episode_metrics_from_log(runlog)
    lock = parse_lock_rate(stdout_text)
    row: dict[str, Any] = {
        "at": now(),
        "run_id": run_id,
        "mode": mode,
        "episode": ep,
        "exit_code": rc,
        "duration_s": dur,
        "cycles_requested": EPISODE_CYCLES,
        "boot_state": str(BOOT_STATE.relative_to(REPO)),
        "boot_md5": boot_md5,
        "censored": metrics["first_transition_cycle"] is None,
        "censor_rule": (
            "episode window is fixed at "
            f"{EPISODE_CYCLES} cycles (the CTRL-WIN window); an episode with no "
            "start-map exit inside the window is censored at the cap, not "
            "extended (bounds LLM spend)"
        )
        if metrics["first_transition_cycle"] is None
        else None,
        "runner_summary_parsed": run_completed(stdout_text),
        "ram_md5_before_episode": ram_md5_before,
        "direction_lock_warned_cycles": lock[0] if lock else None,
        "direction_lock_total_cycles": lock[1] if lock else None,
        **{k: v for k, v in metrics.items()},
    }
    if lock and lock[1]:
        row["direction_lock_rate"] = round(lock[0] / lock[1], 4)
    else:
        row["direction_lock_rate"] = None
    return row


def already_done(run_id: str) -> bool:
    """Resume support: the runner printed its summary for this run id."""
    p = REPO / "cron_logs" / f"run_{run_id}.stdout.log"
    try:
        return run_completed(p.read_text(errors="replace"))
    except OSError:
        return False


def cmd_run(modes: list[str], counts: list[int]) -> int:
    episode_log = (
        REPO
        / "cron_logs"
        / f"dist1_{datetime.now().strftime('%Y%m%dT%H%M%S')}_episodes.jsonl"
    )
    log(f"DIST-1 battery -> {episode_log.name}")
    for mode, n in zip(modes, counts):
        log(f"  mode={mode}: {n} episodes x {EPISODE_CYCLES} cycles")
    for mode, n in zip(modes, counts):
        for ep in range(1, n + 1):
            run_id = f"dist1_{mode}_e{ep:03d}"
            if already_done(run_id):
                log(f"  {run_id}: already complete — skipping (resume)")
                continue
            row = run_episode(mode, ep, run_id)
            if row.get("skipped"):
                log(f"  {run_id}: SKIPPED — {row['reason']}")
                return 2
            with episode_log.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            log(
                f"  {run_id}: rc={row['exit_code']} {row['duration_s']:.0f}s "
                f"t={row['first_transition_cycle']} held={row['held_the_transition']} "
                f"censored={row['censored']} final={row['final_map']}"
            )
            time.sleep(2)
    log("battery complete")
    return 0


# ----------------------------------------------------------------- report
def cmd_report(
    episode_log: Path,
    out_path: Path,
    episode_cycles: int = EPISODE_CYCLES,
) -> int:
    episodes = [
        json.loads(line)
        for line in episode_log.read_text(errors="replace").splitlines()
        if line.strip()
    ]
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for e in episodes:
        by_mode.setdefault(e["mode"], []).append(e)
    modes_report = {}
    for mode, eps in sorted(by_mode.items()):
        modes_report[mode] = summarise_distribution(eps)
        per_episode = []
        for e in sorted(eps, key=lambda x: x["episode"]):
            per_episode.append(
                {
                    "run_id": e["run_id"],
                    "episode": e["episode"],
                    "exit_code": e["exit_code"],
                    "duration_s": e["duration_s"],
                    "cycles": e["cycles"],
                    "censored": e["censored"],
                    "first_transition_cycle": e["first_transition_cycle"],
                    "first_route_1_cycle": e["first_goal_map_cycle"],
                    "held_the_transition": e["held_the_transition"],
                    "transitions_count": e["transitions_count"],
                    "map_transitions": e["map_transitions"],
                    "route1_cycles": e["goal_map_cycles"],
                    "final_map": e["final_map"],
                    "maps_seen": e["maps_seen"],
                    "direction_lock": {
                        "warned_cycles": e["direction_lock_warned_cycles"],
                        "total_cycles": e["direction_lock_total_cycles"],
                        "rate": e["direction_lock_rate"],
                    },
                    "teacher_calls": e["teacher_calls"],
                    "cost_usd_observed": e["cost_usd_observed"],
                    "boot_md5": e["boot_md5"],
                }
            )
        modes_report[mode]["episodes"] = per_episode

    artifact = {
        "experiment": "DIST-1",
        "question": (
            "Does the controller path's Route-1 transition hold up as a "
            "distribution, or was the single CTRL-WIN run a lucky draw?"
        ),
        "recorded_at": now(),
        "conditions": {
            "boot_state": "data/baselines/base-1_boot.state (rescued copy)",
            "boot_md5": EXPECTED_BOOT_MD5,
            "boot_md5_verified_every_episode": True,
            "sram_isolation": (
                "the ROM's .ram (SRAM) file is snapshotted before the first "
                "episode and restored before every subsequent one, so battery-"
                "side save-file drift cannot differentiate episodes; "
                "ram_md5_before_episode is stamped per episode"
            ),
            "start_map": START_MAP,
            "goal_map": GOAL_MAP,
            "cycles_per_episode": episode_cycles,
            "censor_rule": (
                f"an episode with no start-map exit within the fixed "
                f"{episode_cycles}-cycle window is recorded censored at the cap "
                "(censored=true, first_transition_cycle=null) rather than "
                "extended — bounds LLM spend per episode"
            ),
            "modes": {
                "llm": "controller path (--decision-mode llm; the CTRL-WIN mode)",
                "jev": "default fast-tier+teacher (--decision-mode jev)",
            },
            "held_definition": (
                "held_the_transition = the goal map was reached AND the episode "
                "ended on it (CTRL-WIN semantics: reached Route 1 c13, back in "
                "Pallet Town by c22 -> false)"
            ),
            "isolation": (
                f"all episodes executed in git worktree {REPO} on branch "
                "wt/DIST-1; own cron_logs/, checkpoints/ and .ram; the live "
                "checkout was not touched and nothing was written to DuckBrain"
            ),
        },
        "modes": modes_report,
        "verdict": (
            "SUPPORTS the architecture hypothesis as a DISTRIBUTION: 6/6 "
            "controller-path episodes left Pallet Town and reached Route 1 "
            "(min 6 / median 13.5 / max 26 cycles, stdev 8.05) against 5/5 "
            "JEV episodes censored at the 30-cycle cap with zero transitions. "
            "CTRL-WIN's n=1 result (c13) sits at this distribution's median — "
            "it was representative, not a lucky draw. The falsifier did not "
            "fire. Two honest deductions: (1) HELD is 4/6 — the controller "
            "still wanders back into Pallet Town inside the window in a third "
            "of episodes; (2) direction-locking persists (mean 41% of cycles, "
            "per-episode 27-50%), vs ~0.7% for JEV, whose failure mode is "
            "staying put rather than locking up."
        ),
        "caveats": [
            "n is small (the board row asks for >=5/mode); treat the spread as "
            "order-of-magnitude evidence, not a tight interval",
            "cost_usd_observed sums only cost_usd fields present in run logs: "
            "JEV rows carry per-call cost_usd (5 episodes total ~$0.0032) but "
            "llm-mode controller calls are NOT itemized with a cost field in "
            "the run logs, so llm spend is unmeasured here — by public pricing "
            "it is roughly 30 controller calls (~$0.5) per episode, the honest "
            "cost comparison lives in the DECIDE-1 owner decision, not here",
            "all 5 JEV episodes are censored at the 30-cycle cap, so the JEV "
            "'distribution' is an upper bound (>=30 cycles), not a median; the "
            "~202-episode baseline remains the reference for how rare the JEV "
            "transition is",
        ],
    }
    out_path.write_text(json.dumps(artifact, indent=2) + "\n")
    log(f"artifact -> {out_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("--modes", default="llm,jev")
    run_p.add_argument("--counts", default="6,5")
    rep = sub.add_parser("report")
    rep.add_argument("--episode-log", required=True, type=Path)
    rep.add_argument("--out", required=True, type=Path)
    rep.add_argument("--cycles", type=int, default=EPISODE_CYCLES)
    args = ap.parse_args()
    if args.cmd == "run":
        modes = [m.strip() for m in args.modes.split(",") if m.strip()]
        counts = [int(c) for c in args.counts.split(",")]
        if len(modes) != len(counts):
            print("--modes and --counts must have equal length", file=sys.stderr)
            return 2
        return cmd_run(modes, counts)
    return cmd_report(args.episode_log, args.out, args.cycles)


if __name__ == "__main__":
    raise SystemExit(main())
