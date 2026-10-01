#!/usr/bin/env python3
"""E2E-002: run and score the 80-cycle narrative L2 acceptance gate.

The evaluator is deliberately evidence-first. A process exit code alone cannot pass:
JSONL, DuckBrain, resource, key-liveness, review, and replay evidence must all agree.
A single complete run is an L2 candidate; two distinct passing run ids are required
before the emitted ladder score can claim L2.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import resource
import secrets
import subprocess
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core import duckbrain_client  # noqa: E402

INSTRUMENT = "E2E-002"
MODE = "e2e-l2-80-cycle-narrative"
EXPECTED_CYCLES = 80
EXPECTED_BOOT_STATE = "data/boot.state"
MEMORY_CAP_BYTES = 4 * 1024**3
MEMORY_CAP_MB = MEMORY_CAP_BYTES / 1024**2
MEMORY_EVENTS = frozenset({"memory_note", "memory_goal"})
API_FAILURE_EVENTS = frozenset(
    {"api_failure", "api_error", "llm_api_failure", "transport_failure"}
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a run log strictly; malformed/non-object rows invalidate evidence."""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: malformed JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: row is not a JSON object")
            rows.append(row)
    return rows


def _nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _checkpoint_artifact(row: dict[str, Any]) -> bool:
    """Return whether a top-level battle-looking row declares checkpoint origin."""
    provenance = " ".join(
        str(row.get(name, ""))
        for name in ("source", "origin", "artifact", "boot_state", "checkpoint")
    ).lower()
    return "checkpoint" in provenance


def organic_battle_pairs(rows: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Pair ordered, top-level organic battle_start/battle_end rows.

    Nested ``battle_events`` are intentionally ignored: they duplicate StateWindow
    transitions and are also the shape used by checkpoint fixture artifacts.
    """
    open_starts: list[int] = []
    pairs: list[tuple[int, int]] = []
    for index, row in enumerate(rows):
        event = row.get("event")
        if event == "battle_start" and not _checkpoint_artifact(row):
            open_starts.append(index)
        elif event == "battle_end" and not _checkpoint_artifact(row) and open_starts:
            pairs.append((open_starts.pop(0), index))
    return pairs


def _map_40_to_11_after_pair(
    rows: list[dict[str, Any]], pairs: Iterable[tuple[int, int]]
) -> tuple[bool, dict[str, Any] | None]:
    for start_index, end_index in pairs:
        map_40_index = next(
            (
                index
                for index in range(start_index, -1, -1)
                if rows[index].get("map_id") == 40
            ),
            None,
        )
        map_11_index = next(
            (
                index
                for index in range(end_index + 1, len(rows))
                if rows[index].get("map_id") == 11
            ),
            None,
        )
        if map_40_index is not None and map_11_index is not None:
            return True, {
                "map_40_cycle": rows[map_40_index].get("cycle"),
                "battle_start_cycle": rows[start_index].get("cycle"),
                "battle_end_cycle": rows[end_index].get("cycle"),
                "map_11_cycle": rows[map_11_index].get("cycle"),
            }
    return False, None


def _api_failure_details(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Count explicit top-level API/transport failure evidence without text guessing."""
    failures: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        reasons: list[str] = []
        event = row.get("event")
        if event in API_FAILURE_EVENTS:
            reasons.append(f"event={event}")
        if row.get("jev_ok") is False:
            reasons.append("jev_ok=false")
        if row.get("api_ok") is False:
            reasons.append("api_ok=false")
        if row.get("api_failure") is True:
            reasons.append("api_failure=true")
        if row.get("error") not in (None, ""):
            reasons.append("error field")
        explicit_count = row.get("api_failures")
        if isinstance(explicit_count, int) and explicit_count > 0:
            reasons.append(f"api_failures={explicit_count}")
        if reasons:
            count = (
                explicit_count
                if isinstance(explicit_count, int) and explicit_count > 0
                else 1
            )
            failures.append(
                {
                    "row": index + 1,
                    "cycle": row.get("cycle"),
                    "count": count,
                    "reasons": reasons,
                }
            )
    return failures


def _duckbrain_memory_types(
    summary: dict[str, Any] | None, expected_key: str
) -> set[str]:
    if not isinstance(summary, dict):
        return set()
    if summary.get("key") != expected_key:
        return set()
    attributes = summary.get("attributes")
    if not isinstance(attributes, dict):
        return set()
    events = attributes.get("events")
    if not isinstance(events, dict):
        return set()
    return {
        event
        for event in MEMORY_EVENTS
        if isinstance(events.get(event), int) and events[event] > 0
    }


def _eligible_previous_run_ids(
    previous_results: Iterable[dict[str, Any]], current_run_id: str
) -> set[str]:
    eligible: set[str] = set()
    for result in previous_results:
        run_id = result.get("run_id")
        key_check = result.get("checks", {}).get("key_liveness", {})
        if (
            isinstance(run_id, str)
            and run_id
            and run_id != current_run_id
            and result.get("instrument") == INSTRUMENT
            and result.get("mode") == MODE
            and result.get("single_run_pass") is True
            and isinstance(key_check, dict)
            and key_check.get("passed") is True
        ):
            eligible.add(run_id)
    return eligible


def _command_arg(command: Any, name: str) -> str | None:
    if not isinstance(command, list):
        return None
    try:
        index = command.index(name)
    except ValueError:
        return None
    if index + 1 >= len(command):
        return None
    return str(command[index + 1])


def evaluate_evidence(
    *,
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    duckbrain_summary: dict[str, Any] | None,
    review_path: Path,
    replay_path: Path,
    previous_results: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Evaluate one run plus explicit prior-run evidence into an L0-L4 score."""
    run_id = str(manifest.get("run_id") or "")
    command = manifest.get("command")
    mode_ok = (
        manifest.get("instrument") == INSTRUMENT
        and manifest.get("mode") == MODE
        and manifest.get("cycles") == EXPECTED_CYCLES
        and manifest.get("boot_state") == EXPECTED_BOOT_STATE
        and manifest.get("fresh_run_id") is True
        and re.fullmatch(r"e2e002_\d{8}_\d{6}_[0-9a-f]{4}", run_id) is not None
        and _command_arg(command, "--run-id") == run_id
        and _command_arg(command, "--boot-state") == EXPECTED_BOOT_STATE
        and _command_arg(command, "--cycles") == str(EXPECTED_CYCLES)
    )
    key_state = manifest.get("key_preflight")
    key_ok = (
        isinstance(key_state, dict)
        and key_state.get("passed") is True
        and key_state.get("skipped") is False
        and isinstance(key_state.get("live_key_names"), list)
        and bool(key_state["live_key_names"])
    )
    process_ok = manifest.get("process_exit_code") == 0
    completed_cycle = max(
        (row["cycle"] for row in rows if isinstance(row.get("cycle"), int)),
        default=0,
    )
    cycles_ok = completed_cycle >= EXPECTED_CYCLES
    stamped_run_ids = {
        str(row["run_id"])
        for row in rows
        if isinstance(row.get("run_id"), str) and row["run_id"]
    }
    run_identity_ok = stamped_run_ids == {run_id}

    jsonl_memory = {
        str(row["event"])
        for row in rows
        if row.get("event") in MEMORY_EVENTS
    }
    duckbrain_key = f"/game/runs/{run_id}/summary"
    duckbrain_memory = _duckbrain_memory_types(duckbrain_summary, duckbrain_key)
    shared_memory = sorted(jsonl_memory & duckbrain_memory)
    memory_ok = bool(shared_memory)

    pairs = organic_battle_pairs(rows)
    battle_ok = bool(pairs)
    map_ok, map_observation = _map_40_to_11_after_pair(rows, pairs)
    starter_ok = any(row.get("event") == "starter_picked" for row in rows)

    failures = _api_failure_details(rows)
    structured_failure_count = sum(int(item.get("count", 1)) for item in failures)
    runner_failure_count = manifest.get("runner_api_failure_count")
    runner_failure_count_ok = (
        isinstance(runner_failure_count, int) and runner_failure_count >= 0
    )
    runner_failure_count_value = (
        runner_failure_count if runner_failure_count_ok else None
    )
    total_api_failures = (
        structured_failure_count + runner_failure_count_value
        if runner_failure_count_value is not None
        else None
    )
    api_ok = runner_failure_count_ok and total_api_failures == 0

    peak_rss_kb = manifest.get("peak_rss_kb")
    peak_rss_mb = (
        float(peak_rss_kb) / 1024
        if isinstance(peak_rss_kb, (int, float)) and peak_rss_kb >= 0
        else None
    )
    cap_ok = (
        manifest.get("memory_cap_bytes") == MEMORY_CAP_BYTES
        and manifest.get("memory_cap_enforced") is True
        and peak_rss_mb is not None
        and peak_rss_mb <= MEMORY_CAP_MB
    )

    review_ok = _nonempty_file(review_path)
    replay_ok = _nonempty_file(replay_path)
    artifacts_ok = review_ok and replay_ok

    checks: dict[str, dict[str, Any]] = {
        "instrument_shape": {
            "passed": mode_ok,
            "expected": {
                "mode": MODE,
                "cycles": EXPECTED_CYCLES,
                "boot_state": EXPECTED_BOOT_STATE,
                "fresh_run_id": True,
            },
            "observed": {
                "mode": manifest.get("mode"),
                "cycles": manifest.get("cycles"),
                "boot_state": manifest.get("boot_state"),
                "fresh_run_id": manifest.get("fresh_run_id"),
            },
        },
        "run_identity": {
            "passed": run_identity_ok,
            "expected": run_id,
            "observed": sorted(stamped_run_ids),
        },
        "key_liveness": {
            "passed": key_ok,
            "skipped": key_state.get("skipped") if isinstance(key_state, dict) else None,
            "live_key_names": (
                key_state.get("live_key_names", []) if isinstance(key_state, dict) else []
            ),
        },
        "process_exit": {
            "passed": process_ok,
            "observed": manifest.get("process_exit_code"),
        },
        "completed_80_cycles": {
            "passed": cycles_ok,
            "observed_max_cycle": completed_cycle,
        },
        "memory_both_surfaces": {
            "passed": memory_ok,
            "jsonl_event_types": sorted(jsonl_memory),
            "duckbrain_event_types": sorted(duckbrain_memory),
            "event_types": shared_memory,
            "duckbrain_key": duckbrain_key,
        },
        "starter_picked": {"passed": starter_ok},
        "organic_battle_pair": {
            "passed": battle_ok,
            "observed_pairs": len(pairs),
            "pair_cycles": [
                [rows[start].get("cycle"), rows[end].get("cycle")]
                for start, end in pairs
            ],
            "nested_battle_events_ignored": True,
        },
        "map_40_to_11_post_battle": {
            "passed": map_ok,
            "observed": map_observation,
        },
        "api_failures": {
            "passed": api_ok,
            "observed": total_api_failures,
            "jsonl_count": structured_failure_count,
            "runner_log_count": runner_failure_count,
            "jsonl_failures": failures,
        },
        "peak_rss": {
            "passed": cap_ok,
            "observed_kb": peak_rss_kb,
            "observed_mb": peak_rss_mb,
            "cap_mb": MEMORY_CAP_MB,
            "cap_enforced": manifest.get("memory_cap_enforced"),
        },
        "review_and_replay": {
            "passed": artifacts_ok,
            "review": {"path": str(review_path), "present": review_ok},
            "replay": {"path": str(replay_path), "present": replay_ok},
        },
    }

    l0 = all(
        checks[name]["passed"]
        for name in (
            "instrument_shape",
            "run_identity",
            "key_liveness",
            "process_exit",
            "completed_80_cycles",
            "api_failures",
            "peak_rss",
        )
    )
    l1 = l0 and starter_ok and battle_ok
    single_run_pass = l1 and memory_ok and map_ok and artifacts_ok

    passing_ids = _eligible_previous_run_ids(previous_results, run_id)
    if single_run_pass and run_id:
        passing_ids.add(run_id)
    independent_ids = sorted(passing_ids)
    l2 = single_run_pass and len(independent_ids) >= 2

    if l2:
        level = "L2"
    elif l1:
        level = "L1"
    else:
        level = "L0"

    levels = {
        "L0": {
            "passed": l0,
            "reason": "80-cycle live-key pipeline/resource gate" if l0 else "pipeline gate incomplete",
        },
        "L1": {
            "passed": l1,
            "reason": "starter plus organic paired battle events" if l1 else "starter/battle gate incomplete",
        },
        "L2": {
            "passed": l2,
            "reason": (
                "two distinct complete E2E-002 runs"
                if l2
                else f"requires two distinct passing run ids; observed {len(independent_ids)}"
            ),
        },
        "L3": {
            "passed": False,
            "reason": "not evaluated by E2E-002 (requires Brock and cross-run goal continuity)",
        },
        "L4": {
            "passed": False,
            "reason": "not evaluated by E2E-002 (requires Hall of Fame at low hint level)",
        },
    }

    return {
        "schema_version": 1,
        "instrument": INSTRUMENT,
        "mode": MODE,
        "run_id": run_id,
        "evaluated_at": _utc_now(),
        "smoke_only": manifest.get("cycles") != EXPECTED_CYCLES,
        "single_run_pass": single_run_pass,
        "gate_pass": l2,
        "independent_passing_run_ids": independent_ids,
        "score": {"level": level, "value": int(level[1]), "levels": levels},
        "checks": checks,
    }


def publish_ladder_score(
    result: dict[str, Any], existing_summary: dict[str, Any] | None
) -> str:
    """Append the scored summary to DuckBrain under the canonical run key."""
    run_id = str(result["run_id"])
    existing_attributes = (
        existing_summary.get("attributes", {})
        if isinstance(existing_summary, dict)
        and isinstance(existing_summary.get("attributes"), dict)
        else {}
    )
    attributes = dict(existing_attributes)
    attributes["e2e_acceptance"] = {
        "instrument": INSTRUMENT,
        "mode": MODE,
        "run_id": run_id,
        "ladder_score": result["score"]["level"],
        "ladder_value": result["score"]["value"],
        "levels": result["score"]["levels"],
        "single_run_pass": result["single_run_pass"],
        "gate_pass": result["gate_pass"],
        "independent_passing_run_ids": result["independent_passing_run_ids"],
        "checks": result["checks"],
        "evaluated_at": result.get("evaluated_at"),
    }
    return duckbrain_client.remember(
        key=f"/game/runs/{run_id}/summary",
        domain="game/runs",
        attributes=attributes,
        embedding_text=(
            f"Run {run_id} E2E-002 score {result['score']['level']}; "
            f"gate_pass={result['gate_pass']}"
        ),
        namespace="pokemon-global",
    )


def render_review(result: dict[str, Any], path: Path, replay_path: Path) -> None:
    """Write a self-contained evidence review page; it never changes the verdict."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, check in result.get("checks", {}).items():
        passed = bool(check.get("passed"))
        rows.append(
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td class={'pass' if passed else 'fail'}>{'PASS' if passed else 'FAIL'}</td>"
            f"<td><code>{html.escape(json.dumps(check, sort_keys=True, default=str))}</code></td>"
            "</tr>"
        )
    replay_link = os.path.relpath(replay_path, path.parent)
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(str(result.get('run_id')))} E2E-002 review</title>
<style>body{{font:15px system-ui;background:#10131a;color:#e8edf5;margin:2rem;max-width:1200px}}h1{{margin-bottom:.2rem}}.pass{{color:#62d68b}}.fail{{color:#ff6b6b}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #374151;padding:.6rem;vertical-align:top}}code{{white-space:pre-wrap;overflow-wrap:anywhere}}a{{color:#7dd3fc}}</style></head><body>
<h1>E2E-002 — {html.escape(str(result.get('score', {}).get('level', 'L0')))}</h1>
<p>Run <code>{html.escape(str(result.get('run_id')))}</code> · mode <code>{MODE}</code></p>
<p>Single-run pass: <strong>{result.get('single_run_pass')}</strong> · two-pass L2 gate: <strong>{result.get('gate_pass')}</strong></p>
<p>Independent passing runs: <code>{html.escape(json.dumps(result.get('independent_passing_run_ids', [])))}</code></p>
<p><a href="{html.escape(replay_link)}">Replay video</a></p>
<table><thead><tr><th>Check</th><th>Verdict</th><th>Evidence</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</body></html>"""
    path.write_text(document, encoding="utf-8")


def _load_previous(paths: Iterable[Path]) -> list[dict[str, Any]]:
    return [_read_json(path) for path in paths]


def _evaluate_manifest(
    manifest_path: Path,
    previous_paths: list[Path],
    replay_override: Path | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    manifest = _read_json(manifest_path)
    run_id = str(manifest.get("run_id") or "")
    artifact_dir = manifest_path.parent
    review_path = artifact_dir / "review.html"
    replay_path = replay_override or ROOT / "videos" / f"{run_id}.mp4"
    log_path = Path(str(manifest.get("log_path") or ""))
    if not log_path.is_absolute():
        log_path = ROOT / log_path
    try:
        rows = read_jsonl(log_path)
        log_error = None
    except (OSError, ValueError) as exc:
        rows = []
        log_error = str(exc)

    summary = duckbrain_client.get(
        key=f"/game/runs/{run_id}/summary", namespace="pokemon-global"
    )
    (artifact_dir / "duckbrain-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    placeholder = {
        "run_id": run_id,
        "score": {"level": "L0"},
        "checks": {},
        "single_run_pass": False,
        "gate_pass": False,
        "independent_passing_run_ids": [],
    }
    render_review(placeholder, review_path, replay_path)
    result = evaluate_evidence(
        manifest=manifest,
        rows=rows,
        duckbrain_summary=summary,
        review_path=review_path,
        replay_path=replay_path,
        previous_results=_load_previous(previous_paths),
    )
    if log_error:
        result["evidence_error"] = log_error
        result["single_run_pass"] = False
        result["gate_pass"] = False
        result["score"]["level"] = "L0"
        result["score"]["value"] = 0
        result["score"]["levels"]["L0"] = {
            "passed": False,
            "reason": "run JSONL unavailable or malformed",
        }
    result_path = artifact_dir / "result.json"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    render_review(result, review_path, replay_path)
    publish_ladder_score(result, summary)
    return result, result_path, review_path


def _fresh_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"e2e002_{stamp}_{secrets.token_hex(2)}"


def _limit_child_memory() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_CAP_BYTES, MEMORY_CAP_BYTES))


def _run_instrument(args: argparse.Namespace) -> int:
    run_id = _fresh_run_id()
    artifact_dir = ROOT / "artifacts" / "e2e" / run_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    log_path = ROOT / "cron_logs" / f"run_{run_id}.jsonl"
    if log_path.exists():
        raise RuntimeError(f"fresh run id collision: {log_path}")

    python = Path(args.python)
    command = [
        str(python),
        "cron_runner.py",
        "--run-id",
        run_id,
        "--boot-state",
        EXPECTED_BOOT_STATE,
        "--cycles",
        str(EXPECTED_CYCLES),
    ]
    if args.rom:
        command.extend(["--rom", args.rom])

    preflight = [*command, "--dry-run"]
    preflight_result = subprocess.run(
        preflight,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    preflight_log = artifact_dir / "preflight.log"
    preflight_log.write_text(preflight_result.stdout, encoding="utf-8")
    live_key_names = sorted(
        set(re.findall(r"Key liveness:\s+([A-Z0-9_]+) live", preflight_result.stdout))
    )
    key_passed = preflight_result.returncode == 0 and bool(live_key_names)

    started_at = _utc_now()
    runner_log = artifact_dir / "runner.log"
    exit_code: int | None = None
    peak_rss_kb: int | None = None
    if key_passed:
        with runner_log.open("w", encoding="utf-8") as output:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
                preexec_fn=_limit_child_memory,
            )
        exit_code = completed.returncode
        peak_rss_kb = int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    else:
        runner_log.write_text(
            "Run withheld: key preflight did not prove at least one configured live key.\n",
            encoding="utf-8",
        )

    replay_path = ROOT / "videos" / f"{run_id}.mp4"
    replay_log = artifact_dir / "replay.log"
    if exit_code == 0:
        replay_result = subprocess.run(
            [str(python), "make_run_video.py", run_id],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        replay_log.write_text(replay_result.stdout, encoding="utf-8")
    else:
        replay_log.write_text("Replay withheld: runner did not exit 0.\n", encoding="utf-8")

    runner_text = runner_log.read_text(encoding="utf-8", errors="replace")
    runner_api_failure_count = len(
        re.findall(
            r"^\s*(?:\[API\] (?:Request failed|Rate limited|Server error)|OpenRouter API error)",
            runner_text,
            flags=re.MULTILINE,
        )
    )

    manifest = {
        "schema_version": 1,
        "instrument": INSTRUMENT,
        "mode": MODE,
        "run_id": run_id,
        "cycles": EXPECTED_CYCLES,
        "boot_state": EXPECTED_BOOT_STATE,
        "fresh_run_id": True,
        "command": command,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "key_preflight": {
            "passed": key_passed,
            "skipped": False,
            "live_key_names": live_key_names,
            "return_code": preflight_result.returncode,
            "evidence_path": str(preflight_log.relative_to(ROOT)),
        },
        "memory_cap_bytes": MEMORY_CAP_BYTES,
        "memory_cap_enforced": True,
        "peak_rss_kb": peak_rss_kb,
        "process_exit_code": exit_code,
        "runner_api_failure_count": runner_api_failure_count,
        "log_path": str(log_path.relative_to(ROOT)),
        "runner_log_path": str(runner_log.relative_to(ROOT)),
        "replay_path": str(replay_path.relative_to(ROOT)),
    }
    manifest_path = artifact_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result, result_path, review_path = _evaluate_manifest(
        manifest_path, args.previous_result, replay_path
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"Result: {result_path}")
    print(f"Review: {review_path}")
    return 0 if result["gate_pass"] else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="launch a fresh capped 80-cycle run, then score it")
    run.add_argument("--python", default=sys.executable, help="project-venv Python executable")
    run.add_argument("--rom", help="untracked owned ROM path passed to cron_runner")
    run.add_argument(
        "--previous-result",
        action="append",
        type=Path,
        default=[],
        help="result.json from a distinct prior passing E2E-002 run",
    )

    evaluate = subparsers.add_parser("evaluate", help="score an existing instrument manifest")
    evaluate.add_argument("--manifest", type=Path, required=True)
    evaluate.add_argument("--replay", type=Path)
    evaluate.add_argument(
        "--previous-result", action="append", type=Path, default=[]
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "run":
        return _run_instrument(args)
    result, result_path, review_path = _evaluate_manifest(
        args.manifest, args.previous_result, args.replay
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"Result: {result_path}")
    print(f"Review: {review_path}")
    return 0 if result["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
