#!/usr/bin/env python3
"""Long-run driver: chain game episodes for hours.

Designed against the failure that killed the first marathon (330 episodes of a
poison checkpoint): every episode's end-state is BOOTED AND READ BACK before it
is allowed to become the next episode's boot state. A state that does not prove
a live overworld map is rejected and the driver falls back to the last good one.

Outputs, all of which the hourly summary job reads:
  cron_logs/long_run_<RUN_ID>_episodes.jsonl   one row per episode
  long_run_status.json                          live status + cumulative findings
  long_run/<RUN_ID>_good.state                  the last state that passed validation

Goal: reach Viridian City from Pallet Town. map_topology is the single largest
JEV escalation class, so a real map transition is the first honest proof that the
fast tier can navigate without the teacher.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

DURATION_S = int(os.environ.get("LONG_RUN_SECONDS", 3 * 3600))
EPISODE_CYCLES = int(os.environ.get("LONG_RUN_CYCLES", 30))
RUN_ID = os.environ.get("LONG_RUN_ID") or datetime.now().strftime("long_%m%d_%H%M")
EPISODE_LOG = REPO / "cron_logs" / f"long_run_{RUN_ID}_episodes.jsonl"
STATUS = REPO / "long_run_status.json"
FINDINGS_INTERVAL_S = 300.0  # DuckBrain status row: at most one per 5 minutes
JEV_DEGRADED_RATE = 0.5
JEV_DEGRADED_MIN_DECISIONS = 5
_LAST_LOOP_SEEN = [0]
CHAIN_DIR = REPO / "long_run"
GOOD_STATE = CHAIN_DIR / f"{RUN_ID}_good.state"
CHECKPOINT_DIR = REPO / "checkpoints"
ROM = REPO / "data" / "rom" / "Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
BOOT = REPO / "data" / "boot.state"

GOAL = {
    "id": "GOAL-1",
    "text": "Leave Pallet Town and reach Viridian City",
    "why": "map_topology is the largest JEV escalation class; a real map "
    "transition is the first proof the fast tier can navigate unaided",
    "marker": "viridian",
}
LADDER = ["Oak's Lab", "Pallet Town", "Route 1", "Viridian City"]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- validation
def probe_state(path: Path) -> dict[str, Any]:
    """Boot a .state and read the real map back. The anti-poison check."""
    out: dict[str, Any] = {"ok": False, "map_id": None, "map_name": None, "error": None}
    try:
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        emu = Emulator(str(ROM))
        emu.load_state(str(path))
        emu.tick(30)
        reader = RAMReader(emu, str(ROM))
        # RAMReader exposes current_map_id / current_map_name (verified 09-26).
        for meth in ("current_map_id", "current_map", "map_id", "get_map_id"):
            fn = getattr(reader, meth, None)
            if callable(fn):
                try:
                    v = fn()
                    if isinstance(v, dict):
                        out["map_id"] = v.get("id") or v.get("map_id")
                        out["map_name"] = v.get("name") or v.get("map_name")
                    else:
                        out["map_id"] = v
                    break
                except Exception:
                    continue
        namefn = getattr(reader, "current_map_name", None)
        if callable(namefn):
            try:
                out["map_name"] = namefn()
            except Exception:
                pass
        if out["map_name"] is None and out["map_id"] is not None:
            db = getattr(reader, "map_db", None) or getattr(reader, "_mapdb", None)
            if db is not None:
                try:
                    m = db.get_map(int(out["map_id"]))
                    if m:
                        out["map_name"] = m.get("name")
                except Exception:
                    pass
        _ = reader.player_tile_x(), reader.player_tile_y()
        # A RESOLVED MAP NAME is the real proof of a live overworld. The id is
        # only a fallback — and the bound must be inclusive of 0, because
        # PALLET TOWN IS MAP ID 0 (the first map in Gen 1). A `0 < id` test
        # rejected the single most important state in the early game, so the
        # driver rolled back to Oak's Lab on every episode and replayed the
        # same lab -> Pallet segment instead of progressing.
        _mid = out["map_id"]
        out["ok"] = bool(out["map_name"]) or (_mid is not None and 0 <= int(_mid) < 250)
        emu.stop()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def newest_checkpoint(after: float) -> Path | None:
    if not CHECKPOINT_DIR.exists():
        return None
    cands = [p for p in CHECKPOINT_DIR.glob("*.state") if p.stat().st_mtime > after]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


# ---------------------------------------------------------------- episode log
def summarise(path: Path) -> dict[str, Any]:
    """Summarise one cron_runner log, including JEV transport health."""
    s: dict[str, Any] = {
        "cycles": 0,
        "decisions": 0,
        "jev_answered": 0,
        "escalated": 0,
        "jev_transport_failures": 0,
        "jev_error_rows": 0,
        "jev_failure_rate": 0.0,
        "degraded": False,
        "teacher_calls": 0,
        "teacher_improved": 0,
        "maps": [],
        "screens": {},
        "actions": [],
        "missing_classes": {},
        "autonomy": None,
        "errors": [],
    }
    if not path.exists():
        return s
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        ev = r.get("event")
        if ev == "teacher_escalation":
            s["teacher_calls"] += 1
        elif ev == "run_autonomy":
            s["autonomy"] = r
            s["teacher_calls"] = max(
                s["teacher_calls"], (r.get("teacher_escalations") or {}).get("count", 0)
            )
            s["teacher_improved"] = max(
                s["teacher_improved"],
                (r.get("teacher_escalations") or {}).get("improved", 0),
            )
        elif r.get("jev_answered") is not None:
            s["decisions"] += 1
            s["jev_answered"] += 1 if r.get("jev_answered") else 0
            s["escalated"] += 1 if r.get("escalated") else 0
            s["jev_transport_failures"] += 1 if r.get("jev_ok") is False else 0
            s["jev_error_rows"] += 1 if "jev_error" in r else 0
            if r.get("map_name"):
                s["maps"].append(r["map_name"])
            if r.get("screen"):
                s["screens"][r["screen"]] = s["screens"].get(r["screen"], 0) + 1
            for a in (r.get("plan") or [])[:3]:
                s["actions"].append(str(a))
            m = r.get("missing_class")
            if m:
                s["missing_classes"][m] = s["missing_classes"].get(m, 0) + 1
            s["cycles"] = max(s["cycles"], int(r.get("cycle") or 0))
        elif ev in ("recovery_exhausted", "error"):
            s["errors"].append(str(r)[:200])

    decisions = s["decisions"]
    failures = s["jev_transport_failures"]
    raw_failure_rate = failures / decisions if decisions else 0.0
    s["jev_failure_rate"] = round(raw_failure_rate, 4)
    s["degraded"] = bool(
        decisions >= JEV_DEGRADED_MIN_DECISIONS and raw_failure_rate > JEV_DEGRADED_RATE
    )
    if s["degraded"]:
        s["errors"].append(
            f"JEV DEGRADED: {failures}/{decisions} transport failures "
            f"(rate {s['jev_failure_rate']:.0%})"
        )
    return s


# Compatibility for callers outside this script that used the old name.
read_episode_log = summarise


def tail_maps(path: Path, n: int = 40) -> str | None:
    if not path.exists():
        return None
    names = []
    for line in path.read_text(errors="replace").splitlines()[-n * 3 :]:
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("map_name"):
            names.append(r["map_name"])
    return names[-1] if names else None


# ---------------------------------------------------------------- findings
_LAST_FINDINGS_WRITE = [0.0]


def write_findings(state: dict[str, Any]) -> None:
    """Compress what the system learned into DuckBrain (best-effort).

    Throttled to once every FINDINGS_INTERVAL_S: the key is append-only, so
    writing on every ~25s episode would bury the record rather than track it.
    A goal hit or a newly recorded loop warning forces an immediate write.
    """
    try:
        if not _FINDINGS_DUE(state):
            return
        from src.core import duckbrain_client

        totals = state.get("totals") or {}
        last = state.get("last_episode") or {}
        decisions = totals.get("decisions") or 0
        escalated = totals.get("escalated") or 0
        attrs = {
            "run_id": RUN_ID,
            "elapsed_min": state.get("elapsed_min"),
            "episodes": state.get("episodes"),
            "decisions": decisions,
            "escalated": escalated,
            "autonomy_ratio_honest": round((decisions - escalated) / decisions, 3)
            if decisions
            else None,
            "teacher_calls": totals.get("teacher_calls"),
            "teacher_improved": totals.get("teacher_improved"),
            "degraded": bool(state.get("degraded")),
            "jev_transport_failures": totals.get("jev_transport_failures"),
            "jev_failure_rate": totals.get("jev_failure_rate"),
            "maps_visited": state.get("maps_visited"),
            "current_map": last.get("final_map"),
            "goal": GOAL["text"],
            "goal_achieved": state.get("goal_achieved"),
            "top_missing_classes": state.get("top_missing_classes"),
            "loop_warnings": state.get("loop_warnings"),
            "episodes_with_invalid_state": None,
        }
        mem_id = duckbrain_client.remember(
            key=f"/game/long-run/{RUN_ID}/status",
            domain="game/long-run",
            attributes=attrs,
            embedding_text=(
                f"Long run {RUN_ID}: {state.get('episodes')} episodes, "
                f"{decisions} decisions, {escalated} escalated, "
                f"{totals.get('teacher_calls')} teacher calls, "
                f"JEV transport failures {totals.get('jev_transport_failures')} "
                f"({totals.get('jev_failure_rate')}, "
                f"{'DEGRADED' if state.get('degraded') else 'healthy'}), "
                f"maps visited {state.get('maps_visited')}, "
                f"current map {last.get('final_map')}, "
                f"goal '{GOAL['text']}' "
                f"{'ACHIEVED' if state.get('goal_achieved') else 'not yet'}. "
                f"Dominant JEV gap: {state.get('top_missing_classes')}."
            ),
            namespace="pokemon-global",
        )
        _LAST_FINDINGS_WRITE[0] = time.time()
        _LAST_LOOP_SEEN[0] = state.get("loop_warnings") or 0
        log(f"  findings -> DuckBrain {mem_id} (goal={state.get('goal_achieved')})")
    except Exception as exc:  # noqa: BLE001
        log(f"  (findings write failed: {type(exc).__name__}: {exc})")


def _FINDINGS_DUE(state: dict[str, Any]) -> bool:
    """Throttle rule for the DuckBrain status row."""
    if state.get("goal_achieved"):
        return True
    if (state.get("loop_warnings") or 0) != _LAST_LOOP_SEEN[0]:
        return True
    return (time.time() - _LAST_FINDINGS_WRITE[0]) >= FINDINGS_INTERVAL_S


def main() -> int:
    CHAIN_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()

    totals = {
        "decisions": 0,
        "jev_answered": 0,
        "escalated": 0,
        "teacher_calls": 0,
        "teacher_improved": 0,
        "jev_transport_failures": 0,
        "jev_error_rows": 0,
        "jev_failure_rate": 0.0,
        "degraded": False,
        "degraded_episodes": 0,
        "episodes": 0,
        "errors": 0,
    }
    maps_visited: list[str] = []
    missing_all: dict[str, int] = {}
    goal_achieved = False
    start_ep = 1
    elapsed_offset_min = 0.0
    loop_warnings = 0

    # Resume: a restart (code fix, host reboot, crash) must CONTINUE the same
    # run rather than silently resetting the benchmark's cumulative numbers, so
    # a fix mid-run does not cost the run its history.
    if STATUS.exists():
        try:
            prev = json.loads(STATUS.read_text())
        except Exception:
            prev = {}
        if prev.get("run_id") == RUN_ID:
            totals.update(prev.get("totals") or {})
            maps_visited = list(prev.get("maps_visited") or [])
            missing_all = dict(prev.get("top_missing_classes") or {})
            goal_achieved = bool(prev.get("goal_achieved"))
            start_ep = int(prev.get("episodes") or 0) + 1
            elapsed_offset_min = float(prev.get("elapsed_min") or 0)
            log(
                f"RESUMING {RUN_ID} at episode {start_ep} — {totals['episodes']} "
                f"episodes / {elapsed_offset_min:.0f} min already elapsed"
            )

    end = start + max(300.0, DURATION_S - elapsed_offset_min * 60)
    log(
        f"LONG RUN {RUN_ID} — {DURATION_S / 3600:.1f}h, {EPISODE_CYCLES} cycles/episode"
    )
    log(f"goal: {GOAL['id']} — {GOAL['text']}")

    # Resume from the last state that PASSED validation when one exists — a
    # restart continues the run instead of replaying the opening from scratch.
    boot = str(GOOD_STATE) if GOOD_STATE.exists() else str(BOOT)
    consecutive_identical = 0
    last_sig = None

    for ep in range(start_ep, 10000):
        if time.time() >= end:
            log("duration reached — stopping")
            break
        if goal_achieved:
            log(f"GOAL ACHIEVED at episode {ep - 1} — stopping")
            break

        rid = f"{RUN_ID}_ep{ep:03d}"
        runlog = REPO / "cron_logs" / f"run_{rid}.jsonl"
        t0 = time.time()
        log(f"EP{ep}: boot={Path(boot).name} cycles={EPISODE_CYCLES}")

        try:
            proc = subprocess.run(
                [
                    str(REPO / ".venv/bin/python"),
                    "cron_runner.py",
                    "--run-id",
                    rid,
                    "--cycles",
                    str(EPISODE_CYCLES),
                    "--boot-state",
                    boot,
                ],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                timeout=1800,
            )
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc = -9
            log("  episode TIMEOUT (1800s)")
        dur = time.time() - t0

        s = summarise(runlog)
        final_map = tail_maps(runlog)
        totals["episodes"] += 1
        for k in (
            "decisions",
            "jev_answered",
            "escalated",
            "teacher_calls",
            "teacher_improved",
            "jev_transport_failures",
            "jev_error_rows",
        ):
            totals[k] += s[k]
        totals["errors"] += len(s["errors"])
        totals["degraded_episodes"] += 1 if s["degraded"] else 0
        totals["degraded"] = bool(totals["degraded"] or s["degraded"])
        totals["jev_failure_rate"] = (
            round(totals["jev_transport_failures"] / totals["decisions"], 4)
            if totals["decisions"]
            else 0.0
        )
        for m, c in s["missing_classes"].items():
            missing_all[m] = missing_all.get(m, 0) + c
        for m in s["maps"] + ([final_map] if final_map else []):
            if m and m not in maps_visited:
                maps_visited.append(m)

        # ---- anti-poison: prove the state before chaining
        cand = newest_checkpoint(t0)
        verdict = {"ok": False, "map_name": None}
        next_boot = boot
        if cand is not None:
            verdict = probe_state(cand)
            if verdict["ok"]:
                shutil.copy2(cand, GOOD_STATE)
                next_boot = str(GOOD_STATE)
            elif GOOD_STATE.exists():
                next_boot = str(GOOD_STATE)
                log(f"  state rejected ({verdict.get('error')}) — chaining last good")

        goal_hit = bool(final_map and GOAL["marker"] in final_map.lower())
        goal_achieved = (
            goal_achieved
            or goal_hit
            or any(GOAL["marker"] in (m or "").lower() for m in maps_visited)
        )

        sig = (final_map, s["decisions"], s["escalated"], s["teacher_calls"])
        consecutive_identical = consecutive_identical + 1 if sig == last_sig else 0
        last_sig = sig

        row = {
            "at": now(),
            "episode": ep,
            "run_id": rid,
            "exit_code": rc,
            "duration_s": round(dur, 1),
            "decisions": s["decisions"],
            "jev_answered": s["jev_answered"],
            "escalated": s["escalated"],
            "teacher_calls": s["teacher_calls"],
            "teacher_improved": s["teacher_improved"],
            "jev_transport_failures": s["jev_transport_failures"],
            "jev_error_rows": s["jev_error_rows"],
            "jev_failure_rate": s["jev_failure_rate"],
            "degraded": s["degraded"],
            "final_map": final_map,
            "maps_seen": sorted(set(s["maps"])),
            "screens": s["screens"],
            "missing_classes": s["missing_classes"],
            "autonomy": s["autonomy"],
            "actions_sample": s["actions"][:12],
            "state_ok": verdict["ok"],
            "state_map": verdict.get("map_name"),
            "goal_achieved": goal_achieved,
            "errors": s["errors"][:3],
        }
        with EPISODE_LOG.open("a") as fh:
            fh.write(json.dumps(row) + "\n")

        status = {
            "run_id": RUN_ID,
            "updated": now(),
            "goal": GOAL,
            "ladder": LADDER,
            "goal_achieved": goal_achieved,
            "elapsed_min": round(elapsed_offset_min + (time.time() - start) / 60, 1),
            "duration_target_min": round(DURATION_S / 60, 1),
            "episodes": totals["episodes"],
            "totals": totals,
            "degraded": bool(totals["degraded"]),
            "degradation": {
                "component": "jev",
                "transport_failures": totals["jev_transport_failures"],
                "decisions": totals["decisions"],
                "failure_rate": totals["jev_failure_rate"],
                "threshold": JEV_DEGRADED_RATE,
                "min_decisions": JEV_DEGRADED_MIN_DECISIONS,
                "degraded_episodes": totals["degraded_episodes"],
                "last_episode_degraded": s["degraded"],
                "last_episode_errors": s["errors"][:3],
            },
            "maps_visited": maps_visited,
            "top_missing_classes": dict(
                sorted(missing_all.items(), key=lambda kv: -kv[1])[:5]
            ),
            "last_episode": row,
            "episode_log": str(EPISODE_LOG),
            "consecutive_identical": consecutive_identical,
            "loop_warnings": loop_warnings,
        }
        STATUS.write_text(json.dumps(status, indent=1))
        write_findings(status)

        log(
            f"  ep{ep}: rc={rc} {dur:.0f}s map={final_map} dec={s['decisions']} "
            f"esc={s['escalated']} teacher={s['teacher_calls']} "
            f"jev_fail={s['jev_transport_failures']}/{s['decisions']} "
            f"{'DEGRADED ' if s['degraded'] else ''}"
            f"state_ok={verdict['ok']} goal={goal_achieved}"
        )

        if consecutive_identical >= 3:
            # A repeated episode signature is a FINDING, not a reason to stop.
            # The operator asked for hours of play with hourly reports; a stalled
            # game is precisely what those reports exist to surface, so record it
            # and keep playing instead of ending the run.
            loop_warnings += 1
            log(
                f"  LOOP WARNING #{loop_warnings}: {consecutive_identical} consecutive "
                f"identical episodes (sig={sig}) — continuing"
            )
            consecutive_identical = 0
            boot = str(GOOD_STATE) if GOOD_STATE.exists() else boot
        boot = next_boot
        time.sleep(2)

    log(
        f"LONG RUN {RUN_ID} finished: {totals['episodes']} episodes, "
        f"goal_achieved={goal_achieved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
