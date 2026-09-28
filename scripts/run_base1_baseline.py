#!/usr/bin/env python3
"""BASE-1: lock the S0 control baseline — N identical jev episodes, one artifact.

Prerequisite measurement for CTRL-WIN (llm-vs-jev), HOLD-1 and BASE-REPIN: the
number the later stages must beat. Every episode is IDENTICAL by construction:

  - same boot state (data/boot.state, the known-good overworld checkpoint)
  - same episode length (--cycles)
  - same decision mode (--decision-mode jev, the fast tier)
  - distinct --run-id per episode (base1_ep<N>_<date>)

Per-episode metrics are derived ONLY from what cron_runner already writes to
cron_logs/run_<id>.jsonl (the same field names scripts/long_run.py and
scripts/dist1_episodes.py read): decision rows carry cycle / map_name /
jev_answered / escalated, teacher_escalation rows count teacher calls, and the
run_autonomy row stamps decision_mode. Model/provider is recovered from the
teacher_escalation patch's model_build when an episode escalated at least once
(jev_client records it there); it is None with an explicit reason otherwise —
never guessed.

Usage (from the repo root, with .venv on PATH or via --python):

    .venv/bin/python scripts/run_base1_baseline.py run
    .venv/bin/python scripts/run_base1_baseline.py report \
        cron_logs/base1_20260927T..._episodes.jsonl

``run`` executes the episodes and appends one JSON row per episode to
cron_logs/base1_<stamp>_episodes.jsonl; ``report`` aggregates an episode log
into data/baselines/base1_control_<date>.json. Resume-safe: an episode whose
runner already printed its final summary is skipped on re-run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RUNNER = REPO / "cron_runner.py"
BOOT_STATE = REPO / "data" / "boot.state"
ROM_PATH = (
    REPO / "data" / "rom" / "Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
)
# SRAM twin of the ROM: snapshot once, restore before EVERY episode so
# battery-side save-file drift can never differentiate episode N from
# episode 1 (same discipline as dist1_episodes.py).
RAM_PATH = ROM_PATH.parent / (ROM_PATH.name + ".ram")
RAM_SNAPSHOT = REPO / "long_run" / "base1_ram.ram"

EPISODES = 5
EPISODE_CYCLES = 5
DECISION_MODE = os.environ.get("BASE1_DECISION_MODE", "jev")
RUN_ID_TAG = os.environ.get("BASE1_RUN_ID_TAG", "base1")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# Default is computed at call time (today()) rather than import time: a
# hardcoded date made every report after that date write to a stale filename
# and broke the test contract `base1_control_{today()}.json` (CI red since
# 2026-09-28). The env override is still honored.
OUTPUT_PATH = os.environ.get(
    "BASE1_OUTPUT_PATH", f"data/baselines/base1_control_{today()}.json"
)
EPISODE_TIMEOUT_S = 1800  # same guard as long_run.py / dist1_episodes.py


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def md5_of(path: Path) -> str | None:
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324
    except OSError:
        return None


def load_env_abs(path: Path, names: tuple[str, ...]) -> None:
    """Load the named keys from an absolute .env into the process env.

    cron_runner's own dotenv loader is CWD-relative (``Path(".env")``), so a
    run from a worktree checkout would export with an unset OPENROUTER_API_KEY
    and silently produce a zero-decision episode. This loader reads the
    canonical main-tree .env by absolute path instead. Only key NAMES are
    accepted here; values are moved env-var style and never printed.
    """
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key in names and value and not os.environ.get(key):
                os.environ[key] = value
    except OSError:
        pass


# ------------------------------------------------------------------ metrics
def _episode_skeleton() -> dict[str, Any]:
    return {
        "cycles": 0,
        "decisions": 0,
        "jev_answered": 0,
        "escalated": 0,
        "jev_transport_failures": 0,
        "teacher_calls": 0,
        "teacher_improved": 0,
        "missing_classes": {},
        "map_sequence": [],
        "maps_seen": [],
        "map_transitions": [],
        "final_map": None,
        "autonomy": None,
        "decision_mode_log": None,
        "model_build": None,
        "run_completed": False,
        "errors": [],
    }


def episode_metrics_from_log(log_path: Path) -> dict[str, Any]:
    """Per-episode BASE-1 metrics from one cron_runner JSONL log.

    A map transition is a consecutive decision-row pair whose map_name
    changes (the same definition scripts/dist1_episodes.py uses). Escalations
    and jev answers are counted per decision row; the run_autonomy row's own
    totals are kept alongside for cross-checking.
    """
    m = _episode_skeleton()
    if not log_path.exists():
        m["errors"].append("log missing")
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
            model_build = ((r.get("post_ask") or {}).get("model_build")) or None
            if model_build and not m["model_build"]:
                m["model_build"] = model_build
        elif ev == "run_autonomy":
            m["autonomy"] = {
                "decisions_total": r.get("decisions_total"),
                "jev_answered": r.get("jev_answered"),
                "escalated": r.get("escalated"),
                "autonomy_ratio": r.get("autonomy_ratio"),
                "teacher_escalations": r.get("teacher_escalations"),
            }
            m["decision_mode_log"] = r.get("decision_mode")
            m["run_completed"] = True
            teacher = r.get("teacher_escalations") or {}
            m["teacher_calls"] = max(m["teacher_calls"], teacher.get("count", 0) or 0)
            m["teacher_improved"] = max(
                m["teacher_improved"], teacher.get("improved", 0) or 0
            )
        elif r.get("missing_class") is not None and "plan" in r:
            cycle = int(r.get("cycle") or 0)
            map_name = r.get("map_name")
            m["decisions"] += 1
            m["cycles"] = max(m["cycles"], cycle)
            m["jev_answered"] += 1 if r.get("jev_answered") else 0
            m["escalated"] += 1 if r.get("escalated") else 0
            m["jev_transport_failures"] += 1 if r.get("jev_ok") is False else 0
            mc = r.get("missing_class")
            m["missing_classes"][mc] = m["missing_classes"].get(mc, 0) + 1
            if map_name:
                prev = m["map_sequence"][-1]["map"] if m["map_sequence"] else None
                m["map_sequence"].append({"cycle": cycle, "map": map_name})
                if map_name not in m["maps_seen"]:
                    m["maps_seen"].append(map_name)
                if prev and map_name != prev:
                    m["map_transitions"].append(
                        {"cycle": cycle, "from_map": prev, "to_map": map_name}
                    )
        elif ev in ("recovery_exhausted", "error"):
            m["errors"].append(str(r)[:200])
    if m["map_sequence"]:
        m["final_map"] = m["map_sequence"][-1]["map"]
    return m


def _ram_restore_summary(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """SRAM-restore evidence across episodes (Bane: a null carries a reason).

    The snapshot is armed during episode 1, so its recorded md5 is legitimately
    None; episodes 2..N report the md5 they actually booted with. Distinct
    values are kept (not folded), so a mid-battery snapshot change is visible
    instead of hidden by a first-row sample.
    """
    raw = {e.get("ram_md5_before_episode") for e in episodes}
    values = sorted((v for v in raw if v), key=str)
    return {
        "distinct_md5": values if values else None,
        "episodes_with_restore": sum(
            1 for e in episodes if e.get("ram_md5_before_episode")
        ),
        "note": (
            "episode 1 arms the snapshot, so its restore md5 is None; later "
            "episodes report the md5 they booted with"
        ),
    }


def summarise_episodes(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-episode rows into the baseline summary block."""
    n = len(episodes)
    totals = {
        "cycles": sum(int(e.get("cycles") or 0) for e in episodes),
        "decisions": sum(int(e.get("decisions") or 0) for e in episodes),
        "jev_answered": sum(int(e.get("jev_answered") or 0) for e in episodes),
        "escalations_jev": sum(int(e.get("escalated") or 0) for e in episodes),
        "teacher_calls": sum(int(e.get("teacher_calls") or 0) for e in episodes),
        "teacher_improved": sum(int(e.get("teacher_improved") or 0) for e in episodes),
        "map_transitions": sum(len(e.get("map_transitions") or []) for e in episodes),
        "wall_time_s": round(
            sum(float(e.get("wall_time_s") or 0.0) for e in episodes), 1
        ),
    }
    transitions = totals["map_transitions"]
    wall_times = [float(e.get("wall_time_s") or 0.0) for e in episodes]
    summary: dict[str, Any] = {
        "episodes": n,
        **totals,
        "escalations_per_map_transition": (
            round(totals["escalations_jev"] / transitions, 2) if transitions else None
        ),
        "wall_time_s_per_episode": {
            "mean": round(statistics.fmean(wall_times), 2) if wall_times else None,
            "min": round(min(wall_times), 2) if wall_times else None,
            "max": round(max(wall_times), 2) if wall_times else None,
            "stdev": round(statistics.stdev(wall_times), 2)
            if len(wall_times) > 1
            else 0.0,
        },
        "maps_visited": sorted(
            {m for e in episodes for m in (e.get("maps_seen") or [])}
        ),
        "episodes_completed": sum(1 for e in episodes if e.get("run_completed")),
        "episodes_with_zero_decisions": sum(
            1 for e in episodes if not int(e.get("decisions") or 0)
        ),
    }
    if not transitions:
        summary["escalations_per_map_transition_note"] = (
            "no map transition occurred in any episode; escalations per "
            "transition is undefined (null), not zero"
        )
    return summary


# ----------------------------------------------------------------- episode
def _snapshot_ram() -> str | None:
    try:
        RAM_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        if RAM_PATH.exists():
            shutil.copy2(RAM_PATH, RAM_SNAPSHOT)
            return md5_of(RAM_SNAPSHOT)
    except OSError:
        pass
    return None


def _restore_ram() -> str | None:
    if not RAM_SNAPSHOT.exists():
        return _snapshot_ram()
    try:
        if RAM_PATH.exists():
            shutil.copy2(RAM_SNAPSHOT, RAM_PATH)
        return md5_of(RAM_SNAPSHOT)
    except OSError:
        return None


def run_episode(
    ep: int,
    run_id: str,
    python: str = str(REPO / ".venv" / "bin" / "python"),
) -> dict[str, Any]:
    """Run ONE episode; return its summary row (dist1_episodes.py shape)."""
    runlog = REPO / "cron_logs" / f"run_{run_id}.jsonl"
    stdout_log = REPO / "cron_logs" / f"run_{run_id}.stdout.log"

    ram_md5_before = _restore_ram()
    t0 = time.time()
    log(f"EP {run_id}: mode={DECISION_MODE} cycles={EPISODE_CYCLES} boot=boot.state")
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
                DECISION_MODE,
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
    wall_time_s = round(time.time() - t0, 1)
    try:
        stdout_log.write_text(stdout_text, errors="replace")
    except OSError:
        pass

    metrics = episode_metrics_from_log(runlog)
    row: dict[str, Any] = {
        "at": now(),
        "run_id": run_id,
        "episode": ep,
        "exit_code": rc,
        "wall_time_s": wall_time_s,
        "cycles_requested": EPISODE_CYCLES,
        "boot_state": "data/boot.state",
        "boot_sha256": sha256_of(BOOT_STATE),
        "ram_md5_before_episode": ram_md5_before,
        **metrics,
    }
    return row


def already_done(run_id: str) -> bool:
    """Resume support: the autonomy summary row landed for this run id."""
    runlog = REPO / "cron_logs" / f"run_{run_id}.jsonl"
    if not runlog.exists():
        return False
    for line in runlog.read_text(errors="replace").splitlines()[::-1]:
        try:
            if json.loads(line).get("event") == "run_autonomy":
                return True
        except Exception:
            continue
    return False


def cmd_run(n_episodes: int, cycles: int) -> int:
    for name in ("OPENROUTER_API_KEY",):
        load_env_abs(Path("/home/kara/ai_plays_poke/.env"), (name,))
    if not __import__("os").environ.get("OPENROUTER_API_KEY"):
        log(
            "ABORT: OPENROUTER_API_KEY not resolvable — refusing to burn episodes "
            "on a zero-decision run (stale base1_ram.ram/long_run snapshot can "
            "be deleted to re-arm the SRAM snapshot)"
        )
        return 2
    if not ROM_PATH.is_file():
        log(f"ABORT: ROM missing at {ROM_PATH} — a run would crash at boot")
        return 2
    if not BOOT_STATE.is_file():
        log(f"ABORT: boot state missing at {BOOT_STATE}")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    episode_log = REPO / "cron_logs" / f"base1_{stamp}_episodes.jsonl"
    log(f"BASE-1 battery -> {episode_log.name}")
    log(f"  {n_episodes} episodes x {cycles} cycles, mode={DECISION_MODE}")
    rows: list[dict[str, Any]] = []
    for ep in range(1, n_episodes + 1):
        run_id = f"{RUN_ID_TAG}_ep{ep}_{today().replace('-', '')}"
        if already_done(run_id):
            log(f"  {run_id}: already complete — skipping (resume)")
            continue
        row = run_episode(ep, run_id)
        with episode_log.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        rows.append(row)
        log(
            f"  {run_id}: rc={row['exit_code']} {row['wall_time_s']:.0f}s "
            f"dec={row['decisions']} esc={row['escalated']} "
            f"teacher={row['teacher_calls']} transitions={len(row['map_transitions'])} "
            f"final={row['final_map']}"
        )
        time.sleep(2)
    log("battery complete; now run the report subcommand to write the artifact")
    return 0


# ------------------------------------------------------------------ report
def cmd_report(episode_log: Path) -> int:
    # Accept both absolute and cwd-relative paths; REPO-relative rendering
    # below needs a resolved absolute path.
    episode_log = episode_log.resolve()
    episodes = [
        json.loads(line)
        for line in episode_log.read_text(errors="replace").splitlines()
        if line.strip()
    ]
    if len(episodes) < 5:
        log(
            f"ABORT: {len(episodes)} episodes in {episode_log.name}; BASE-1 "
            "requires >= 5 identical episodes — refusing to write a thin baseline"
        )
        return 2
    mode_seen = {e.get("decision_mode_log") for e in episodes}
    # Evidence-quality: prefer the mode actually stamped in the episode logs
    # over the env default (a `report` subprocess invoked without
    # BASE1_DECISION_MODE would otherwise mis-stamp llm runs as jev).
    report_mode = (
        mode_seen.pop()
        if len(mode_seen) == 1 and None not in mode_seen
        else DECISION_MODE
    )
    models = sorted({e.get("model_build") for e in episodes if e.get("model_build")})
    summary = summarise_episodes(episodes)
    if report_mode == "llm":
        summary["llm_decisions_total"] = sum(
            int((e.get("autonomy") or {}).get("decisions_total") or 0) for e in episodes
        )
    artifact = {
        "baseline_id": "BASE-1",
        "role": (
            "S0 control baseline: the number CTRL-WIN (llm-vs-jev), HOLD-1 and "
            "BASE-REPIN must beat or reproduce"
        ),
        "recorded_at": now(),
        "conditions": {
            "decision_mode": report_mode,
            "boot_state": "data/boot.state",
            "boot_state_sha256": episodes[0].get("boot_sha256"),
            "cycles_per_episode": EPISODE_CYCLES,
            "episodes": len(episodes),
            "episode_run_ids": [e.get("run_id") for e in episodes],
            "ram_restore": _ram_restore_summary(episodes),
            "model_build_seen": models or None,
            "model_build_reason": (
                "jev model identity from teacher_escalation post_ask.model_build; "
                "None when no episode escalated (fast tier answered everything)"
                if not models
                else "jev model identity from teacher_escalation post_ask.model_build"
            ),
        },
        "summary": summary,
        "episodes": [
            {
                "run_id": e.get("run_id"),
                "at": e.get("at"),
                "exit_code": e.get("exit_code"),
                "wall_time_s": e.get("wall_time_s"),
                "cycles": e.get("cycles"),
                "cycles_requested": e.get("cycles_requested"),
                "decisions": e.get("decisions"),
                "jev_answered": e.get("jev_answered"),
                "escalations_jev": e.get("escalated"),
                "teacher_calls": e.get("teacher_calls"),
                "teacher_improved": e.get("teacher_improved"),
                "map_transitions_count": len(e.get("map_transitions") or []),
                "map_transitions": e.get("map_transitions"),
                "escalations_per_map_transition": (
                    round(e["escalated"] / len(e["map_transitions"]), 2)
                    if e.get("map_transitions")
                    else None
                ),
                "final_map": e.get("final_map"),
                "maps_seen": e.get("maps_seen"),
                "missing_classes": e.get("missing_classes"),
                "autonomy": e.get("autonomy"),
                "decision_mode_log": e.get("decision_mode_log"),
                "model_build": e.get("model_build"),
                "boot_state_sha256": e.get("boot_sha256"),
                "run_completed": e.get("run_completed"),
                "errors": e.get("errors"),
            }
            for e in episodes
        ],
        "episode_log": str(episode_log.relative_to(REPO)),
        "falsifier_for_CTRL-WIN": (
            "CTRL-WIN fails to improve on S0 if its llm-vs-jev comparison does "
            "not reduce escalations_per_map_transition below this baseline's "
            "value at equal cycles/episode"
        ),
    }
    if mode_seen - {report_mode}:
        log(f"WARN: decision_mode_log values {sorted(mode_seen)} != '{report_mode}'")
    out = REPO / OUTPUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2) + "\n")
    log(f"artifact -> {out.relative_to(REPO)}")
    log(
        f"  episodes={summary['episodes']} decisions={summary['decisions']} "
        f"escalations_jev={summary['escalations_jev']} "
        f"teacher={summary['teacher_calls']} "
        f"transitions={summary['map_transitions']} "
        f"esc/transition={summary['escalations_per_map_transition']} "
        f"wall_mean={summary['wall_time_s_per_episode']['mean']}s"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="execute the identical-episode battery")
    run_p.add_argument("--episodes", type=int, default=EPISODES)
    run_p.add_argument("--cycles", type=int, default=EPISODE_CYCLES)
    report_p = sub.add_parser(
        "report", help="aggregate an episode log into the baseline artifact"
    )
    report_p.add_argument("episode_log", type=Path)
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args.episodes, args.cycles)
    return cmd_report(args.episode_log)


if __name__ == "__main__":
    raise SystemExit(main())
