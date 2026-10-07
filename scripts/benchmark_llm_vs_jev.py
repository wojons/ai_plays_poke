#!/usr/bin/env python3
"""BENCH-1: the LLM-core benchmark — llm head-to-head with jev, one command.

One command runs BOTH arms of the CTRL-WIN question from the SAME boot state
and the SAME cycle budget, then regenerates a side-by-side comparison table
from the arm logs alone:

    .venv/bin/python scripts/benchmark_llm_vs_jev.py run
    .venv/bin/python scripts/benchmark_llm_vs_jev.py report \
        cron_logs/bench1_<stamp>_episodes.jsonl

Conditions are identical by construction (same discipline as
scripts/run_base1_baseline.py and scripts/dist1_episodes.py):

  - same boot state (data/boot.state — the S0/CTRL-WIN conditions; override
    with --boot-state / BENCH1_BOOT_STATE, stamped per episode)
  - same episode length (--cycles) for BOTH arms
  - arms interleaved episode-by-episode (llm ep1, jev ep1, llm ep2, ...) so a
    code or host change between arms cannot masquerade as a mode effect
  - distinct --run-id per episode: bench1_<mode>_ep<N>_<date>
  - SRAM restore before every episode (same snapshot discipline as BASE-1)

Fail-closed contract (the load-bearing rule): a benchmark-labelled run whose
``llm`` arm contains ANY decision row with ``jev_answered=True`` is rejected —
the battery aborts (rc 3), the episode row carries the guard stamp, and
``report`` refuses to write a comparison artifact from it. A contaminated arm
is not a measurement. The same guard rejects an arm whose logs stamp a
different decision_mode than the arm that was requested. It also rejects a run
whose run-level tool-surface stamp disagrees with its per-decision rows.

Every figure in the artifact is derived from cron_logs/run_<id>.jsonl (and the
per-run stdout log for the runner's own lock-rate) — nothing is hand-entered.
A measurement the logs cannot support is ``null`` with an explicit reason.

Usage (from the repo root, with .venv on PATH or via --python):

    .venv/bin/python scripts/benchmark_llm_vs_jev.py run
    .venv/bin/python scripts/benchmark_llm_vs_jev.py report \
        cron_logs/bench1_20260928T..._episodes.jsonl

``run`` executes the interleaved battery and appends one JSON row per episode
to cron_logs/bench1_<stamp>_episodes.jsonl; ``report`` aggregates that log
into data/baselines/bench1_headtohead_<date>.json. Resume-safe: an episode
whose runner already printed its run_autonomy row is skipped on re-run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

RUNNER = REPO / "cron_runner.py"
DEFAULT_BOOT_STATE = REPO / "data" / "boot.state"
ROM_PATH = (
    REPO / "data" / "rom" / "Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
)
# SRAM twin of the ROM: snapshot once, restore before EVERY episode so
# battery-side save-file drift can never differentiate episode N from
# episode 1 (same discipline as run_base1_baseline.py / dist1_episodes.py).
RAM_PATH = ROM_PATH.parent / (ROM_PATH.name + ".ram")
RAM_SNAPSHOT = REPO / "long_run" / "bench1_ram.ram"

MODES = ("llm", "jev")  # benchmark arm first; interleaved per episode
BENCHMARK_ARM = "llm"  # the pure-LLM arm the purity guard protects
EPISODES_PER_ARM = int(os.environ.get("BENCH1_EPISODES", 5))
EPISODE_CYCLES = int(os.environ.get("BENCH1_CYCLES", 5))
RUN_ID_TAG = os.environ.get("BENCH1_RUN_ID_TAG", "bench1")
EPISODE_TIMEOUT_S = 1800  # same guard as run_base1_baseline.py / long_run.py

# cron_runner's own decision-row population: the main loop stamps `intent` on
# every controller/JEV plan entry and on nothing else (event rows, errors and
# per-button execution rows never set it). _autonomy_counters counts exactly
# these rows, so the benchmark reads the log's own authority instead of a
# parallel population — and avoids run_base1_baseline.py's escalation-only
# undercount that recorded `decisions: 0` beside autonomy `decisions_total:
# 12` in the committed ctrlwin llm artifact.
DECISION_ROW_KEY = "intent"
# Mirror of cron_runner.FALLBACK_INTENTS (importing cron_runner here would
# pull the emulator/API stack into a stdlib-only driver).
FALLBACK_INTENTS = frozenset({"parse_fallback", "parse_failure_fallback"})

LOCK_RATE_RE = re.compile(
    r"lock-rate:\s*(\d+)/(\d+)\s+cycles with direction-lock warnings"
)

GUARD_EVENT = "benchmark_purity_guard"
REJECT_JEV_IN_PURE_LLM = "JEV_ANSWERED_IN_PURE_LLM_ARM"
REJECT_MODE_MISMATCH = "MODE_MISMATCH_IN_ARM"
REJECT_SURFACE_STAMP_MISMATCH = "SURFACE_STAMP_MISMATCH_IN_ARM"


class BenchmarkGuardError(RuntimeError):
    """A benchmark arm failed its purity guard (fail closed, never scored)."""

    def __init__(self, code: str, reasons: list[str]) -> None:
        self.code = code
        self.reasons = reasons
        super().__init__(f"{code}: {'; '.join(reasons)}")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def output_path() -> str:
    """Artifact path at CALL time (the run_base1_baseline.py date-freeze fix)."""
    return os.environ.get(
        "BENCH1_OUTPUT_PATH", f"data/baselines/bench1_headtohead_{today()}.json"
    )


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

    cron_runner's own dotenv loader is CWD-relative, so a run from a worktree
    checkout would export with an unset OPENROUTER_API_KEY and silently
    produce a zero-decision episode. Only key NAMES are handled here; values
    move env-var style and are never printed.
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
def _sum_cost_usd(row: Any, _depth: int = 0) -> float:
    """Recursively sum every numeric ``cost_usd`` in a log row.

    Same definition as scripts/dist1_episodes.py: teacher patches, jev asks
    and controller calls all contribute — an honest lower bound of LLM spend.
    """
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
    """The runner's own per-run lock-rate from its stdout log (dist1 shape)."""
    match = LOCK_RATE_RE.search(stdout_text or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _episode_skeleton() -> dict[str, Any]:
    """One arm-episode row. Every metric the logs may not support is None/[]"""
    return {
        "cycles": 0,
        "decisions": 0,
        "real_decisions": 0,
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
        "cost_usd_observed": 0.0,
        "tiles_visited_distinct": 0,
        "map_sequence": [],
        "maps_seen": [],
        "map_transitions": [],
        "first_map_transition_cycle": None,
        "final_map": None,
        "recovery_events": 0,
        "lock_warn_cycles": None,
        "lock_total_cycles": None,
        "lock_rate": None,
        "autonomy": None,
        "decision_mode": None,
        "decision_mode_log": None,
        "decision_mode_family": None,
        "agentic_tools_enabled": None,
        "agentic_tool_calls": 0,
        "pipeline": None,
        "pipeline_counts": {},
        "surface_stamp_mismatches": [],
        "run_completed": False,
        "errors": [],
    }


def episode_metrics_from_log(log_path: Path, stdout_path: Path | None = None) -> dict:
    """Per-episode benchmark metrics from one cron_runner JSONL log.

    Decision rows are cron_runner's own population (rows carrying ``intent``),
    so the counts here are comparable to the log's own run_autonomy totals in
    BOTH modes — including the pure-LLM arm, where jev_answered is False on
    every row by design. The guard inputs are counted from the same rows: any
    ``jev_answered=True`` row in the llm arm is collected (with cycle + map)
    for the fail-closed gate.
    """
    m = _episode_skeleton()
    if not log_path.exists():
        m["errors"].append("log missing")
        return m
    tile_set: set[tuple[Any, Any]] = set()
    decision_modes: set[str] = set()
    decision_mode_families: set[str] = set()
    tool_enabled_values: set[bool] = set()
    pipeline_counts: dict[str, int] = {}
    agentic_tool_calls = 0
    summary_surface: dict[str, Any] = {}
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
            summary_surface = {
                "decision_mode": r.get("decision_mode"),
                "decision_mode_family": r.get("decision_mode_family"),
                "agentic_tools_enabled": r.get("agentic_tools_enabled"),
                "agentic_tool_calls": r.get("agentic_tool_calls"),
                "pipeline": r.get("pipeline"),
                "pipeline_counts": r.get("pipeline_counts"),
            }
            m["run_completed"] = True
            teacher = r.get("teacher_escalations") or {}
            m["teacher_calls"] = max(m["teacher_calls"], teacher.get("count", 0) or 0)
            m["teacher_improved"] = max(
                m["teacher_improved"], teacher.get("improved", 0) or 0
            )
        elif ev in ("recovery", "recovery_exhausted"):
            m["recovery_events"] += 1
            if ev == "recovery_exhausted":
                m["errors"].append(str(r)[:200])
        elif DECISION_ROW_KEY in r:
            cycle = int(r.get("cycle") or 0)
            map_name = r.get("map_name")
            m["decisions"] += 1
            m["cycles"] = max(m["cycles"], cycle)
            intent = r.get(DECISION_ROW_KEY)
            mode = r.get("decision_mode")
            if isinstance(mode, str):
                decision_modes.add(mode)
            family = r.get("decision_mode_family")
            if isinstance(family, str):
                decision_mode_families.add(family)
            tools_enabled = r.get("agentic_tools_enabled")
            if isinstance(tools_enabled, bool):
                tool_enabled_values.add(tools_enabled)
            row_tool_calls = r.get("agentic_tool_calls")
            if isinstance(row_tool_calls, int) and not isinstance(row_tool_calls, bool):
                agentic_tool_calls += max(0, row_tool_calls)
            pipeline = r.get("pipeline")
            if isinstance(pipeline, str) and pipeline:
                pipeline_counts[pipeline] = pipeline_counts.get(pipeline, 0) + 1
            if isinstance(intent, str) and intent in FALLBACK_INTENTS:
                m["fallback_decisions"] += 1
            else:
                m["real_decisions"] += 1
            if r.get("jev_answered") is True:
                m["jev_answered"] += 1
                m["jev_answered_true_rows"].append(
                    {"cycle": cycle, "map": map_name, "intent": intent}
                )
            m["escalated"] += 1 if r.get("escalated") else 0
            m["jev_transport_failures"] += 1 if r.get("jev_ok") is False else 0
            m["jev_error_rows"] += 1 if "jev_error" in r else 0
            mc = r.get("missing_class")
            if isinstance(mc, str):
                m["missing_classes"][mc] = m["missing_classes"].get(mc, 0) + 1
            px, py = r.get("player_tile_x"), r.get("player_tile_y")
            if px is not None and py is not None:
                tile_set.add((px, py))
            if map_name:
                prev = m["map_sequence"][-1]["map"] if m["map_sequence"] else None
                m["map_sequence"].append({"cycle": cycle, "map": map_name})
                if map_name not in m["maps_seen"]:
                    m["maps_seen"].append(map_name)
                if prev and map_name != prev:
                    m["map_transitions"].append(
                        {"cycle": cycle, "from_map": prev, "to_map": map_name}
                    )
                    if m["first_map_transition_cycle"] is None:
                        m["first_map_transition_cycle"] = cycle
        elif "error" in r:
            # Traceback rows carry an `error` field and NO event key (the
            # runner writes err_entry = {"cycle": N, "error": "..."}), so an
            # ev == "error" check would silently drop every crash.
            m["errors"].append(str(r)[:200])
        m["cost_usd_observed"] += _sum_cost_usd(r)
    m["cost_usd_observed"] = round(m["cost_usd_observed"], 6)
    m["tiles_visited_distinct"] = len(tile_set)
    m["decision_mode"] = (
        next(iter(decision_modes))
        if len(decision_modes) == 1
        else summary_surface.get("decision_mode")
    )
    m["decision_mode_family"] = (
        next(iter(decision_mode_families))
        if len(decision_mode_families) == 1
        else summary_surface.get("decision_mode_family")
    )
    m["agentic_tools_enabled"] = (
        next(iter(tool_enabled_values))
        if len(tool_enabled_values) == 1
        else summary_surface.get("agentic_tools_enabled")
    )
    m["agentic_tool_calls"] = agentic_tool_calls
    m["pipeline_counts"] = pipeline_counts
    pipelines = list(pipeline_counts)
    m["pipeline"] = (
        pipelines[0] if len(pipelines) == 1 else ("mixed" if pipelines else None)
    )

    decision_surface = {
        "decision_mode": m["decision_mode"],
        "decision_mode_family": m["decision_mode_family"],
        "agentic_tools_enabled": m["agentic_tools_enabled"],
        "agentic_tool_calls": m["agentic_tool_calls"],
        "pipeline": m["pipeline"],
        "pipeline_counts": m["pipeline_counts"],
    }
    for field, values in (
        ("decision_mode", decision_modes),
        ("decision_mode_family", decision_mode_families),
        ("agentic_tools_enabled", tool_enabled_values),
    ):
        if len(values) > 1:
            m["surface_stamp_mismatches"].append(
                {
                    "field": field,
                    "decision_rows": sorted(values, key=str),
                    "run_autonomy": summary_surface.get(field),
                }
            )
    for field, summary_value in summary_surface.items():
        # Older logs legitimately lack the S7 stamps. Compare only fields the
        # summary actually supplied; new logs must agree field-for-field.
        if summary_value is not None and summary_value != decision_surface[field]:
            m["surface_stamp_mismatches"].append(
                {
                    "field": field,
                    "decision_rows": decision_surface[field],
                    "run_autonomy": summary_value,
                }
            )
    if m["map_sequence"]:
        m["final_map"] = m["map_sequence"][-1]["map"]
    if stdout_path is not None and stdout_path.exists():
        parsed = parse_lock_rate(stdout_path.read_text(errors="replace"))
        if parsed:
            warned, total = parsed
            m["lock_warn_cycles"] = warned
            m["lock_total_cycles"] = total
            m["lock_rate"] = round(warned / total, 4) if total else None
    return m


# -------------------------------------------------------------------- guard
def arm_is_benchmark(mode: str | None) -> bool:
    """Whether a mode is the pure-LLM arm the purity guard protects."""
    return mode == BENCHMARK_ARM


def guard_benchmark_row(row: dict[str, Any]) -> tuple[str | None, list[str]]:
    """The fail-closed benchmark purity gate. Returns (code, reasons).

    Rejects a benchmark-labelled episode row when:
      REJECT_JEV_IN_PURE_LLM — any decision row in the ``llm`` arm carries
        ``jev_answered=True`` (the fast tier influenced the arm; the
        measurement is contaminated no matter how small the leak), or
      REJECT_MODE_MISMATCH — the log's own run_autonomy row stamps a decision
        mode other than the arm that was requested (the argv and the run
        disagree; the row cannot be attributed to either arm), or
      REJECT_SURFACE_STAMP_MISMATCH — the per-decision tool-surface fields and
        the run-level summary disagree, so the arm is not comparable.

    The returned code is None exactly when the row is scorable; the guard
    stamp is written into the row either way so the artifact carries its own
    provenance.
    """
    reasons: list[str] = []
    code: str | None = None
    leak_rows = row.get("jev_answered_true_rows") or []
    if arm_is_benchmark(row.get("arm")) and leak_rows:
        sample = leak_rows[0]
        reasons.append(
            f"{len(leak_rows)} decision row(s) with jev_answered=True in the "
            f"pure-LLM arm (first at cycle {sample.get('cycle')}, "
            f"map {sample.get('map')!r}, intent {sample.get('intent')!r})"
        )
        code = code or REJECT_JEV_IN_PURE_LLM
    seen = row.get("decision_mode_log")
    if seen is not None and seen != row.get("arm"):
        reasons.append(
            f"run_autonomy stamps decision_mode={seen!r} but the episode was "
            f"run as arm={row.get('arm')!r}"
        )
        code = code or REJECT_MODE_MISMATCH
    surface_mismatches = row.get("surface_stamp_mismatches") or []
    if surface_mismatches:
        reasons.append(
            "run_autonomy tool-surface stamp disagrees with decision rows: "
            + ", ".join(str(item.get("field")) for item in surface_mismatches)
        )
        code = code or REJECT_SURFACE_STAMP_MISMATCH
    row["guard"] = {
        "event": GUARD_EVENT,
        "status": "rejected" if code else "clean",
        "code": code,
        "reasons": reasons,
    }
    return code, reasons


def _episode_argv(
    mode: str, run_id: str, cycles: int, boot_state: Path, python: str
) -> list[str]:
    """The cron_runner subprocess argv for one episode, arm stamped explicitly."""
    return [
        python,
        str(RUNNER),
        "--run-id",
        run_id,
        "--cycles",
        str(cycles),
        "--boot-state",
        str(boot_state),
        "--decision-mode",
        mode,
    ]


def plan_runs(
    modes: tuple[str, ...], episodes_per_arm: int, tag: str, date: str
) -> list[tuple[str, int, str]]:
    """The interleaved battery plan: (mode, episode, run_id), no duplicate ids.

    Interleaving (mode A ep1, mode B ep1, mode A ep2, ...) is the point: a
    code or host change landing mid-battery hits BOTH arms instead of
    confounding one whole arm.
    """
    plan: list[tuple[str, int, str]] = []
    seen_ids: set[str] = set()
    for ep in range(1, episodes_per_arm + 1):
        for mode in modes:
            run_id = f"{tag}_{mode}_ep{ep}_{date}"
            if run_id in seen_ids:
                raise ValueError(f"duplicate run id in battery plan: {run_id}")
            seen_ids.add(run_id)
            plan.append((mode, ep, run_id))
    return plan


def already_done(run_id: str) -> bool:
    """Resume support: the run_autonomy summary row landed for this run id."""
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
    mode: str,
    ep: int,
    run_id: str,
    cycles: int,
    boot_state: Path,
    python: str = str(REPO / ".venv" / "bin" / "python"),
) -> dict[str, Any]:
    """Run ONE episode of one arm; return its benchmark row (fail-closed)."""
    runlog = REPO / "cron_logs" / f"run_{run_id}.jsonl"
    stdout_log = REPO / "cron_logs" / f"run_{run_id}.stdout.log"

    ram_md5_before = _restore_ram()
    t0 = time.time()
    log(f"EP {run_id}: arm={mode} cycles={cycles} boot={boot_state.name}")
    try:
        proc = subprocess.run(  # noqa: S603
            _episode_argv(mode, run_id, cycles, boot_state, python),
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

    metrics = episode_metrics_from_log(runlog, stdout_log)
    row: dict[str, Any] = {
        "at": now(),
        "run_id": run_id,
        "arm": mode,
        "episode": ep,
        "exit_code": rc,
        "wall_time_s": wall_time_s,
        "cycles_requested": cycles,
        "boot_state": str(boot_state.relative_to(REPO)),
        "boot_sha256": sha256_of(boot_state),
        "ram_md5_before_episode": ram_md5_before,
        **metrics,
    }
    code, reasons = guard_benchmark_row(row)
    if code:
        log(f"  GUARD REJECTED {run_id}: {code}")
        for reason in reasons:
            log(f"    - {reason}")
    return row


# ---------------------------------------------------------------------- run
def cmd_run(episodes_per_arm: int, cycles: int, boot_state: Path) -> int:
    for name in ("OPENROUTER_API_KEY",):
        load_env_abs(Path("/home/kara/ai_plays_poke/.env"), (name,))
    if not os.environ.get("OPENROUTER_API_KEY"):
        log(
            "ABORT: OPENROUTER_API_KEY not resolvable — refusing to burn a "
            "head-to-head battery on zero-decision arms"
        )
        return 2
    if not ROM_PATH.is_file():
        log(f"ABORT: ROM missing at {ROM_PATH} — a run would crash at boot")
        return 2
    if not boot_state.is_file():
        log(f"ABORT: boot state missing at {boot_state}")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    episode_log = REPO / "cron_logs" / f"{RUN_ID_TAG}_{stamp}_episodes.jsonl"
    log(f"BENCH-1 head-to-head battery -> {episode_log.name}")
    log(f"  {episodes_per_arm} episodes x {cycles} cycles per arm, arms={list(MODES)}")
    for mode, ep, run_id in plan_runs(MODES, episodes_per_arm, RUN_ID_TAG, today()):
        if already_done(run_id):
            log(f"  {run_id}: already complete — skipping (resume)")
            continue
        row = run_episode(mode, ep, run_id, cycles, boot_state)
        with episode_log.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        log(
            f"  {run_id}: rc={row['exit_code']} {row['wall_time_s']:.0f}s "
            f"dec={row['decisions']} (real={row['real_decisions']} "
            f"fb={row['fallback_decisions']}) jev_ans={row['jev_answered']} "
            f"cost=${row['cost_usd_observed']} tiles={row['tiles_visited_distinct']} "
            f"maps={len(row['maps_seen'])} guard={row['guard']['status']}"
        )
        # Fail closed: a rejected arm ends the battery — later episodes of a
        # contaminated arm are waste and could bury the leak in averages.
        if row["guard"]["status"] == "rejected":
            log(
                "ABORT: benchmark purity guard rejected this battery — "
                f"{row['guard']['code']}. No comparison artifact may be "
                "written from this run (report will refuse it)."
            )
            return 3
        time.sleep(2)
    log("battery complete; now run the report subcommand to write the artifact")
    return 0


# ------------------------------------------------------------------- report
def _arm_aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """One comparison-table row per arm, derived ONLY from episode rows."""
    decisions = sum(int(r.get("decisions") or 0) for r in rows)
    real = sum(int(r.get("real_decisions") or 0) for r in rows)
    fallback = sum(int(r.get("fallback_decisions") or 0) for r in rows)
    jev_answered = sum(int(r.get("jev_answered") or 0) for r in rows)
    escalated = sum(int(r.get("escalated") or 0) for r in rows)
    teacher_calls = sum(int(r.get("teacher_calls") or 0) for r in rows)
    teacher_improved = sum(int(r.get("teacher_improved") or 0) for r in rows)
    cost_usd = round(sum(float(r.get("cost_usd_observed") or 0.0) for r in rows), 6)
    lock_warn = sum(
        int(r.get("lock_warn_cycles") or 0)
        for r in rows
        if r.get("lock_warn_cycles") is not None
    )
    lock_total = sum(
        int(r.get("lock_total_cycles") or 0)
        for r in rows
        if r.get("lock_total_cycles") is not None
    )
    first_transitions = [
        int(r["first_map_transition_cycle"])
        for r in rows
        if r.get("first_map_transition_cycle") is not None
    ]
    maps_reached = sorted({m for r in rows for m in (r.get("maps_seen") or [])})
    errors = sum(len(r.get("errors") or []) for r in rows)
    completed = sum(1 for r in rows if r.get("run_completed"))
    mode_families = {r.get("decision_mode_family") for r in rows}
    tools_enabled = {r.get("agentic_tools_enabled") for r in rows}
    pipelines = {r.get("pipeline") for r in rows}
    pipeline_counts: dict[str, int] = {}
    for row in rows:
        for pipeline, count in (row.get("pipeline_counts") or {}).items():
            name = str(pipeline)
            pipeline_counts[name] = pipeline_counts.get(name, 0) + int(count or 0)
    arm_row: dict[str, Any] = {
        "mode": rows[0].get("arm") if rows else None,
        "decision_mode_family": (
            next(iter(mode_families)) if len(mode_families) == 1 else "mixed"
        ),
        "agentic_tools_enabled": (
            next(iter(tools_enabled)) if len(tools_enabled) == 1 else None
        ),
        "agentic_tool_calls": sum(int(r.get("agentic_tool_calls") or 0) for r in rows),
        "pipeline": next(iter(pipelines)) if len(pipelines) == 1 else "mixed",
        "pipeline_counts": pipeline_counts,
        "episodes": len(rows),
        "episodes_completed": completed,
        "decisions": decisions,
        "real_decisions": real,
        "fallback_decisions": fallback,
        "jev_answered": jev_answered,
        "escalations": escalated,
        "teacher_calls": teacher_calls,
        "teacher_improved": teacher_improved,
        "cost_usd_observed": cost_usd,
        "tiles_visited_distinct": sum(
            int(r.get("tiles_visited_distinct") or 0) for r in rows
        ),
        "maps_reached": maps_reached,
        "first_map_transition_cycle": min(first_transitions)
        if first_transitions
        else None,
        "lock_rate": {
            "warned": lock_warn,
            "of": lock_total,
            "rate": round(lock_warn / lock_total, 4) if lock_total else None,
        },
        "errors": errors,
        "run_ids": [r.get("run_id") for r in rows],
    }
    if not first_transitions:
        arm_row["first_map_transition_cycle_reason"] = (
            "no episode left its start map inside the cycle window; the log "
            "shows no map transition, so there is no first-transition cycle"
        )
    if not lock_total:
        arm_row["lock_rate_reason"] = (
            "runner stdout carried no lock-rate line (no completed summary); "
            "rate is null, not zero"
        )
    return arm_row


def _comparability_notes(arms: dict[str, list[dict[str, Any]]]) -> list[str]:
    notes: list[str] = []
    boot_hashes = {r.get("boot_sha256") for rows in arms.values() for r in rows}
    if len(boot_hashes) > 1:
        notes.append(
            "episodes booted DIFFERENT boot states (distinct boot_sha256 "
            "values in the log) — the arms are not comparing like for like"
        )
    cycles_seen = {r.get("cycles_requested") for rows in arms.values() for r in rows}
    if len(cycles_seen) > 1:
        notes.append(
            "episodes requested different cycle budgets "
            f"({sorted(cycles_seen, key=str)}) — arms are not budget-matched"
        )
    for mode, rows in sorted(arms.items()):
        if rows and not any(r.get("run_completed") for r in rows):
            notes.append(
                f"arm {mode}: no episode reached its run_autonomy summary row "
                "(all incomplete) — the aggregate is over partial runs"
            )
        if rows and not any(int(r.get("decisions") or 0) for r in rows):
            notes.append(
                f"arm {mode}: zero decision rows in every episode — a "
                "zero-vs-zero comparison is indeterminate, not a win"
            )
    return notes


def cmd_report(episode_log: Path) -> int:
    episode_log = episode_log.resolve()
    rows = [
        json.loads(line)
        for line in episode_log.read_text(errors="replace").splitlines()
        if line.strip()
    ]
    if not rows:
        log(f"ABORT: {episode_log.name} has no episode rows")
        return 2

    # Re-run the guard over every row read back from the log — the report
    # fails closed even for a log written before the guard existed.
    for row in rows:
        code, reasons = guard_benchmark_row(row)
        if code:
            log(
                f"ABORT: {row.get('run_id')} fails the benchmark purity guard "
                f"({code}) — no comparison artifact is written"
            )
            for reason in reasons:
                log(f"  - {reason}")
            return 3

    arms: dict[str, list[dict[str, Any]]] = {
        mode: [r for r in rows if r.get("arm") == mode] for mode in MODES
    }
    missing = [mode for mode, r in arms.items() if not r]
    if missing:
        log(
            f"ABORT: arm(s) {missing} absent from {episode_log.name} — a "
            "head-to-head artifact needs both arms"
        )
        return 2

    table = [_arm_aggregate(arms[mode]) for mode in MODES]
    by_mode = {row["mode"]: row for row in table}
    llm_row, jev_row = by_mode.get(MODES[0], {}), by_mode.get(MODES[1], {})
    deltas: dict[str, Any] = {
        "decisions_jev_minus_llm": (
            (jev_row.get("decisions") or 0) - (llm_row.get("decisions") or 0)
        ),
        "cost_usd_jev_minus_llm": round(
            (jev_row.get("cost_usd_observed") or 0.0)
            - (llm_row.get("cost_usd_observed") or 0.0),
            6,
        ),
        "fallback_decisions_jev_minus_llm": (
            (jev_row.get("fallback_decisions") or 0)
            - (llm_row.get("fallback_decisions") or 0)
        ),
        "errors_jev_minus_llm": (
            (jev_row.get("errors") or 0) - (llm_row.get("errors") or 0)
        ),
        "note": "differences are jev arm minus llm arm, computed from the table above",
    }

    # Decision-row parity vs the log's own autonomy self-report (same
    # population by construction; a mismatch is listed, never smoothed over).
    parity: list[dict[str, Any]] = []
    for row in rows:
        autonomy = row.get("autonomy") or {}
        logged = autonomy.get("decisions_total")
        counted = int(row.get("decisions") or 0)
        if logged is not None and int(logged) != counted:
            parity.append(
                {
                    "run_id": row.get("run_id"),
                    "decision_rows_counted": counted,
                    "autonomy_decisions_total": logged,
                }
            )
    notes = _comparability_notes(arms)

    log(f"BENCH-1 comparison ({episode_log.name}):")
    header = f"{'metric':<28} {MODES[0]:>14} {MODES[1]:>14}"
    log(header)
    fields = (
        "episodes",
        "episodes_completed",
        "decisions",
        "real_decisions",
        "fallback_decisions",
        "jev_answered",
        "escalations",
        "teacher_calls",
        "cost_usd_observed",
        "tiles_visited_distinct",
        "first_map_transition_cycle",
        "errors",
    )
    for field in fields:
        l_v, j_v = llm_row.get(field), jev_row.get(field)
        log(f"{field:<28} {str(l_v):>14} {str(j_v):>14}")
    log(
        f"{'lock_rate (warned/of)':<28} "
        f"{str(llm_row.get('lock_rate', {}).get('rate')):>14} "
        f"{str(jev_row.get('lock_rate', {}).get('rate')):>14}"
    )
    log(f"  maps_reached llm:   {llm_row.get('maps_reached')}")
    log(f"  maps_reached jev:   {jev_row.get('maps_reached')}")
    for note in notes:
        log(f"  NOTE: {note}")

    artifact = {
        "benchmark_id": "BENCH-1",
        "role": (
            "LLM-core benchmark: the pure-LLM arm vs the fast-tier hybrid arm "
            "at identical boot state and cycle budget, compared from run logs "
            "alone"
        ),
        "recorded_at": now(),
        "guard": {
            "event": GUARD_EVENT,
            "contract": (
                "a benchmark-labelled artifact fails closed if any decision "
                "row in the llm arm carries jev_answered=True, if an "
                "episode's logs stamp a different decision_mode than its arm, "
                "or if run-level and per-decision tool-surface stamps disagree"
            ),
            "rejected_rows": [
                r.get("run_id") for r in rows if (r.get("guard") or {}).get("code")
            ],
        },
        "conditions": {
            "modes": list(MODES),
            "interleaved": "episode-by-episode (llm ep1, jev ep1, llm ep2, ...)",
            "cycles_per_episode": rows[0].get("cycles_requested"),
            "boot_state": rows[0].get("boot_state"),
            "boot_state_sha256": sorted(
                {r.get("boot_sha256") for r in rows if r.get("boot_sha256")}
            ),
            "ram_restore_distinct_md5": sorted(
                {
                    r.get("ram_md5_before_episode")
                    for r in rows
                    if r.get("ram_md5_before_episode")
                },
                key=str,
            ),
            "episode_run_ids": {
                mode: [r.get("run_id") for r in arms[mode]] for mode in MODES
            },
        },
        "summary": {
            "episodes_total": len(rows),
            "decision_row_parity_mismatches": parity,
        },
        "comparison": {
            "table": table,
            "deltas": deltas,
            "comparability_notes": notes,
        },
        "episodes": rows,
        "episode_log": str(episode_log.relative_to(REPO)),
    }
    out = REPO / output_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2) + "\n")
    try:
        rendered = str(out.relative_to(REPO))
    except ValueError:
        # BENCH1_OUTPUT_PATH may legitimately point outside the repo; the
        # artifact is still the one that was written.
        rendered = str(out)
    log(f"artifact -> {rendered}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="execute the interleaved two-arm battery")
    run_p.add_argument("--episodes", type=int, default=EPISODES_PER_ARM)
    run_p.add_argument("--cycles", type=int, default=EPISODE_CYCLES)
    run_p.add_argument(
        "--boot-state",
        type=Path,
        default=Path(os.environ.get("BENCH1_BOOT_STATE", str(DEFAULT_BOOT_STATE))),
    )
    report_p = sub.add_parser(
        "report", help="aggregate an episode log into the comparison artifact"
    )
    report_p.add_argument("episode_log", type=Path)
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args.episodes, args.cycles, args.boot_state)
    return cmd_report(args.episode_log)


if __name__ == "__main__":
    raise SystemExit(main())
