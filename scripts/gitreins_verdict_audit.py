#!/usr/bin/env python3
"""Standing verdict-coverage audit for the gitreins lifecycle state (INT-GATE-2).

The defect class this guard detects is "complete-without-verdict": a task flips
to ``status: complete`` (or sits ``in_progress`` forever) while no
``verdict.json`` naming that ``task_id`` exists under ``.gitreins/history/``.
Live historical instances that motivated the guard: DF-AIPP-13-R3 (completed
2026-11-21, judge never delivered; disclosed partial close) and DF-AIPP-11
(stale ``in_progress`` since 2026-10-20, work landed separately).

FAIL rules (any hit => exit 1, offending ids listed):

* ``ORPHAN-STALE`` -- ``status: in_progress`` whose ``created_at`` is older
  than ``--stale-days`` (default 14) with no verdict naming the id.
* ``ORPHAN-NOVERDICT`` -- ``status: complete`` whose ``completed_at`` falls
  inside the last ``--window-days`` (default 30) with no verdict naming the id
  and no entry in ``.gitreins/verdict_audit_exceptions.yaml``.

Tolerance contract: malformed/unreadable verdict files are counted and
skipped, never fatal; unparseable task dates are treated as "unknown age" and
never produce a failure by themselves; a missing exceptions file simply means
no exceptions. A corrupt verdict does NOT count as verdict coverage for its
task. ``cap_hits`` counts in-window verdict bodies containing the substring
``Iteration cap`` (the judge-iteration-cap starvation signature); it is
WARN-only and exit-neutral. Verdicts whose ``evaluated_at`` is missing or
unparseable are treated as in-window for that count (an unknown date cannot
prove itself stale).

Usage:
    python3 scripts/gitreins_verdict_audit.py [repo_root] [--window-days N]
        [--stale-days N] [--json]

Exit codes: 0 clean, 1 any orphan found, 2 usage/IO error (missing
tasks.yaml, unparsable YAML, unusable shape).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

CAP_SUBSTRING = "Iteration cap"
DEFAULT_WINDOW_DAYS = 30
DEFAULT_STALE_DAYS = 14
GITREINS_DIRNAME = ".gitreins"
TASKS_FILENAME = "tasks.yaml"
HISTORY_DIRNAME = "history"
VERDICT_FILENAME = "verdict.json"
EXCEPTIONS_FILENAME = "verdict_audit_exceptions.yaml"


class AuditIOError(Exception):
    """A tasks.yaml (or its shape) is missing or unusable -> exit 2."""


def parse_iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp tolerantly; ``None`` when unparseable.

    Accepts offsets or none (naive values are assumed UTC) and a trailing
    ``Z``. Any other input -- wrong type, empty, malformed -- yields ``None``
    and callers treat the age as unknown rather than failing.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass(frozen=True)
class VerdictScan:
    """Result of scanning ``.gitreins/history/**/verdict.json``."""

    task_ids: frozenset[str]
    files_found: int
    files_parsed: int
    malformed: int
    cap_hits: int


def scan_verdicts(history_dir: Path, window_cutoff: datetime) -> VerdictScan:
    """Collect the verdict universe and in-window cap hits.

    Every ``verdict.json`` under ``history_dir`` (recursive) contributes its
    ``task_id`` when the file parses. Malformed or unreadable files are
    counted in ``malformed`` and skipped. ``cap_hits`` counts parsed verdict
    bodies containing ``CAP_SUBSTRING`` whose ``evaluated_at`` falls on/after
    ``window_cutoff`` (missing/unparseable ``evaluated_at`` counts as
    in-window; see module docstring).
    """
    paths = sorted(history_dir.rglob(VERDICT_FILENAME)) if history_dir.is_dir() else []
    task_ids: set[str] = set()
    malformed = 0
    cap_hits = 0
    for path in paths:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            malformed += 1
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            malformed += 1
            continue
        task_id = payload.get("task_id") if isinstance(payload, dict) else None
        if isinstance(task_id, str) and task_id:
            task_ids.add(task_id)
        evaluated_at = (
            parse_iso_datetime(payload.get("evaluated_at"))
            if isinstance(payload, dict)
            else None
        )
        in_window = evaluated_at is None or evaluated_at >= window_cutoff
        if in_window and CAP_SUBSTRING in raw:
            cap_hits += 1
    return VerdictScan(
        task_ids=frozenset(task_ids),
        files_found=len(paths),
        files_parsed=len(paths) - malformed,
        malformed=malformed,
        cap_hits=cap_hits,
    )


def load_tasks(tasks_path: Path) -> list[dict[str, Any]]:
    """Read tasks.yaml: a top-level ``{'tasks': [...]}`` mapping or bare list."""
    try:
        text = tasks_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AuditIOError(f"cannot read {tasks_path}: {exc}") from exc
    try:
        payload: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise AuditIOError(f"cannot parse {tasks_path}: {exc}") from exc
    if isinstance(payload, dict):
        raw_tasks: Any = payload.get("tasks", [])
    elif isinstance(payload, list):
        raw_tasks = payload
    else:
        raise AuditIOError(
            f"{tasks_path}: expected a mapping with a 'tasks' key or a bare list"
        )
    if not isinstance(raw_tasks, list):
        raise AuditIOError(f"{tasks_path}: 'tasks' is not a list")
    return [entry for entry in raw_tasks if isinstance(entry, dict)]


def load_exceptions(exceptions_path: Path) -> dict[str, str]:
    """Read the exceptions file: a list of ``{id, reason}`` mappings.

    A missing file means no exceptions (normal). A present-but-broken file
    degrades to no exceptions with a warning rather than failing the audit.
    """
    try:
        text = exceptions_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        print(
            f"WARNING: cannot read exceptions file {exceptions_path}: {exc}",
            file=sys.stderr,
        )
        return {}
    try:
        payload: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        print(
            f"WARNING: cannot parse exceptions file {exceptions_path}: {exc}",
            file=sys.stderr,
        )
        return {}
    exceptions: dict[str, str] = {}
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("id") is not None:
                reason = item.get("reason", "")
                exceptions[str(item["id"])] = (
                    reason if isinstance(reason, str) else str(reason)
                )
            elif isinstance(item, str):
                exceptions[item] = ""
    elif payload is not None:
        print(
            f"WARNING: {exceptions_path}: expected a list; ignoring exceptions",
            file=sys.stderr,
        )
    return exceptions


@dataclass(frozen=True)
class AuditResult:
    """Everything the human and JSON summaries report."""

    root: Path
    window_days: int
    stale_days: int
    tasks_audited: int
    scan: VerdictScan
    exceptions_skipped: list[tuple[str, str]]
    orphan_stale: list[str]
    orphan_noverdict: list[str]

    @property
    def exit_ok(self) -> bool:
        return not self.orphan_stale and not self.orphan_noverdict


def audit_repo(
    root: Path,
    window_days: int = DEFAULT_WINDOW_DAYS,
    stale_days: int = DEFAULT_STALE_DAYS,
    now: datetime | None = None,
) -> AuditResult:
    """Run the verdict-coverage audit against ``root``.

    ``now`` is injectable for deterministic tests; production callers use the
    real UTC clock. Tasks whose dates cannot be parsed are never failed for
    age ("unknown age" contract). Exception ids are skipped from both orphan
    rules with a printed notice carrying their reason.
    """
    current = now if now is not None else datetime.now(timezone.utc)
    gitreins = root / GITREINS_DIRNAME
    tasks = load_tasks(gitreins / TASKS_FILENAME)
    exceptions = load_exceptions(gitreins / EXCEPTIONS_FILENAME)
    scan = scan_verdicts(
        gitreins / HISTORY_DIRNAME, current - timedelta(days=window_days)
    )
    exceptions_skipped: list[tuple[str, str]] = []
    orphan_stale: list[str] = []
    orphan_noverdict: list[str] = []
    tasks_audited = 0
    for task in tasks:
        task_id = task.get("id")
        if task_id is None:
            continue
        tasks_audited += 1
        tid = str(task_id)
        status = task.get("status")
        if isinstance(status, str) and tid in exceptions:
            exceptions_skipped.append((tid, exceptions[tid]))
            continue
        if not isinstance(status, str) or tid in scan.task_ids:
            continue
        if status == "in_progress":
            created_at = parse_iso_datetime(task.get("created_at"))
            if created_at is not None and current - created_at > timedelta(
                days=stale_days
            ):
                orphan_stale.append(tid)
        elif status == "complete":
            completed_at = parse_iso_datetime(task.get("completed_at"))
            if completed_at is not None and completed_at >= current - timedelta(
                days=window_days
            ):
                orphan_noverdict.append(tid)
    return AuditResult(
        root=root,
        window_days=window_days,
        stale_days=stale_days,
        tasks_audited=tasks_audited,
        scan=scan,
        exceptions_skipped=exceptions_skipped,
        orphan_stale=orphan_stale,
        orphan_noverdict=orphan_noverdict,
    )


def _print_human(result: AuditResult) -> None:
    print(f"=== gitreins verdict audit (root: {result.root}) ===")
    print(f"window_days: {result.window_days}")
    print(f"stale_days: {result.stale_days}")
    print(f"tasks_audited: {result.tasks_audited}")
    print(f"verdicts_found: {result.scan.files_parsed}")
    print(f"malformed_verdicts_skipped: {result.scan.malformed}")
    print(f"exceptions_skipped: {len(result.exceptions_skipped)}")
    for tid, reason in result.exceptions_skipped:
        print(f"  - {tid}: {reason} (skipped)")
    print(f"cap_hits (WARN, exit-neutral): {result.scan.cap_hits}")
    print(f"ORPHAN-STALE: {', '.join(result.orphan_stale) or '(none)'}")
    print(f"ORPHAN-NOVERDICT: {', '.join(result.orphan_noverdict) or '(none)'}")
    if result.exit_ok:
        print("RESULT: OK")
    else:
        orphans = result.orphan_stale + result.orphan_noverdict
        print(f"RESULT: FAIL (orphan tasks: {', '.join(orphans)})")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit gitreins task lifecycle state for complete-without-verdict "
            "and stale in_progress orphans (INT-GATE-2)."
        )
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        help="repository root containing .gitreins/ (default: cwd)",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help="audit window for completed_at (default: %(default)s)",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=DEFAULT_STALE_DAYS,
        help="in_progress age threshold (default: %(default)s)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print a machine-readable report instead of the human block",
    )
    args = parser.parse_args(argv)
    root = Path(args.repo_root)
    try:
        result = audit_repo(root, args.window_days, args.stale_days)
    except AuditIOError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        report = {
            "root": str(result.root),
            "window_days": result.window_days,
            "stale_days": result.stale_days,
            "tasks_audited": result.tasks_audited,
            "verdicts_found": result.scan.files_parsed,
            "verdict_files_found": result.scan.files_found,
            "malformed_verdicts_skipped": result.scan.malformed,
            "cap_hits": result.scan.cap_hits,
            "exceptions_skipped": [
                {"id": tid, "reason": reason}
                for tid, reason in result.exceptions_skipped
            ],
            "orphan_stale": result.orphan_stale,
            "orphan_noverdict": result.orphan_noverdict,
            "exit_ok": result.exit_ok,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(result)
    return 0 if result.exit_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
