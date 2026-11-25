#!/usr/bin/env python3
"""Standing verdict-coverage audit for the gitreins lifecycle state (INT-GATE-2,
coverage semantics tightened by INT-GATE-004).

The defect class this guard detects is "complete-without-verdict": a task flips
to ``status: complete`` (or sits ``in_progress`` forever) while no verdict that
actually graded the row's shipped state exists under ``.gitreins/history/``.
Live historical instances that motivated the guard: DF-AIPP-13-R3 (completed
2026-11-21, judge never delivered; disclosed partial close), DF-AIPP-11 (stale
``in_progress`` since 2026-10-20, work landed separately), and INT-GL-3
(completed 2026-11-20 whose only verdicts graded the branch tip ``f4750e9``,
not the merged tree ``c5eb28d`` that actually shipped -- the original
existence-only predicate counted those as coverage; INT-GATE-004).

Coverage predicate (INT-GATE-004): a parsed verdict counts as coverage for a
task ONLY when its graded commit (``verdict.json`` ``commit`` field) is

* equal to the row's recorded commit (the task's ``commit_hash`` -- taken from
  the gitreins task row itself, else from the board row with the same id in
  ``.coding-hermes/board/tasks.jsonl`` when the task row carries none), or
* an ancestor of that recorded commit (a verdict grading the pre-merge branch
  tip that produced the row's shipped commit), or
* equal to the shipped tip (``git rev-parse HEAD`` at the audit root) when the
  row records no commit at all.

A verdict that graded only some other tip -- an unmerged branch tip, a
worktree tip unrelated to the row's recorded commit, or a row whose
``commit_hash`` is null and whose verdicts grade anything but the shipped tip
-- must not count. Verdicts without a parseable ``commit`` field do not count
as coverage either: an unattributed verdict cannot prove the shipped state was
graded.

FAIL rules (any hit => exit 1, offending ids listed):

* ``ORPHAN-STALE`` -- ``status: in_progress`` whose ``created_at`` is older
  than ``--stale-days`` (default 14) with no commit-attributed coverage.
* ``ORPHAN-NOVERDICT`` -- ``status: complete`` whose ``completed_at`` falls
  inside the last ``--window-days`` (default 30) with no commit-attributed
  coverage and no entry in ``.gitreins/verdict_audit_exceptions.yaml``.

Tolerance contract: malformed/unreadable verdict files are counted and
skipped, never fatal; unparseable task dates are treated as "unknown age" and
never produce a failure by themselves; a missing exceptions file simply means
no exceptions; a missing board file or a non-git audit root degrade the
reference-commit resolution (rows then need the tasks.yaml ``commit_hash``
field or the shipped-tip equality arm to count coverage). A corrupt verdict
does NOT count as verdict coverage for its task. Git ancestry probes
(``git merge-base --is-ancestor``) fail closed: an unresolvable or ambiguous
commit never grants coverage. ``cap_hits`` counts in-window verdict bodies
containing the substring ``Iteration cap`` (the judge-iteration-cap starvation
signature); it is WARN-only and exit-neutral. Verdicts whose ``evaluated_at``
is missing or unparseable are treated as in-window for that count (an unknown
date cannot prove itself stale).

Usage:
    python3 scripts/gitreins_verdict_audit.py [repo_root] [--window-days N]
        [--stale-days N] [--json]

Exit codes: 0 clean, 1 any orphan found, 2 usage/IO error (missing
tasks.yaml, unparsable YAML, unusable shape).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
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
BOARD_DIRNAME = ".coding-hermes"
BOARD_SUBDIR = "board"
BOARD_FILENAME = "tasks.jsonl"
GIT_TIMEOUT_SECONDS = 10


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
    graded_commits: dict[str, tuple[str, ...]] = field(default_factory=dict)
    files_found: int = 0
    files_parsed: int = 0
    malformed: int = 0
    cap_hits: int = 0


def scan_verdicts(history_dir: Path, window_cutoff: datetime) -> VerdictScan:
    """Collect the verdict universe and in-window cap hits.

    Every ``verdict.json`` under ``history_dir`` (recursive) contributes its
    ``task_id`` and -- when present -- its graded ``commit`` to the per-task
    graded-commit index. Malformed or unreadable files are counted in
    ``malformed`` and skipped. ``cap_hits`` counts parsed verdict bodies
    containing ``CAP_SUBSTRING`` whose ``evaluated_at`` falls on/after
    ``window_cutoff`` (missing/unparseable ``evaluated_at`` counts as
    in-window; see module docstring).
    """
    paths = sorted(history_dir.rglob(VERDICT_FILENAME)) if history_dir.is_dir() else []
    task_ids: set[str] = set()
    graded: dict[str, list[str]] = {}
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
        if not isinstance(payload, dict):
            malformed += 1
            continue
        task_id = payload.get("task_id")
        if isinstance(task_id, str) and task_id:
            task_ids.add(task_id)
            commit = payload.get("commit")
            if isinstance(commit, str) and commit.strip():
                graded.setdefault(task_id, []).append(commit.strip())
        evaluated_at = parse_iso_datetime(payload.get("evaluated_at"))
        in_window = evaluated_at is None or evaluated_at >= window_cutoff
        if in_window and CAP_SUBSTRING in raw:
            cap_hits += 1
    return VerdictScan(
        task_ids=frozenset(task_ids),
        graded_commits={tid: tuple(commits) for tid, commits in graded.items()},
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


def load_board_commit_hashes(root: Path) -> dict[str, str]:
    """Read per-row ``commit_hash`` from ``.coding-hermes/board/tasks.jsonl``.

    The board is the authoritative place the close flow records the shipped
    commit (the gitreins ``tasks.yaml`` rows in this repo carry no commit
    field). Tolerant: a missing board file, broken lines, or rows without an
    id/``commit_hash`` simply contribute nothing. When an id appears more than
    once, the last occurrence wins (board updates are appended).
    """
    board_path = root / BOARD_DIRNAME / BOARD_SUBDIR / BOARD_FILENAME
    if not board_path.is_file():
        return {}
    try:
        text = board_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    refs: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        commit_hash = row.get("commit_hash")
        if (
            isinstance(row_id, str)
            and row_id
            and isinstance(commit_hash, str)
            and commit_hash.strip()
        ):
            refs[row_id] = commit_hash.strip()
    return refs


def _run_git(
    args: Sequence[str], root: Path
) -> subprocess.CompletedProcess[bytes] | None:
    """Run a git plumbing command at ``root``; ``None`` on any failure."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def resolve_shipped_tip(root: Path) -> str | None:
    """The audit root's HEAD commit (the shipped tip); ``None`` if not a repo."""
    proc = _run_git(["rev-parse", "HEAD"], root)
    if proc is None or proc.returncode != 0:
        return None
    out = proc.stdout.decode("utf-8", "replace").strip()
    return out or None


def is_ancestor(
    candidate: str, target: str, root: Path, cache: dict[tuple[str, str], bool]
) -> bool:
    """``candidate`` is an ancestor of ``target``; fails closed on any git error.

    An unresolvable or ambiguous commit can never grant coverage: the probe
    returns ``False`` rather than guessing.
    """
    key = (candidate, target)
    if key not in cache:
        proc = _run_git(["merge-base", "--is-ancestor", candidate, target], root)
        cache[key] = proc is not None and proc.returncode == 0
    return cache[key]


def verdict_covers(
    graded_commits: tuple[str, ...],
    ref_commit: str | None,
    shipped_tip: str | None,
    root: Path,
    ancestry_cache: dict[tuple[str, str], bool],
) -> bool:
    """INT-GATE-004 coverage predicate (see module docstring).

    A graded commit counts when it equals the shipped tip, equals the row's
    recorded commit, or is an ancestor of that recorded commit. Anything else
    -- in particular a verdict that graded only an unmerged branch tip -- does
    not count.
    """
    for commit in graded_commits:
        if shipped_tip is not None and commit == shipped_tip:
            return True
        if ref_commit is not None and (
            commit == ref_commit
            or is_ancestor(commit, ref_commit, root, ancestry_cache)
        ):
            return True
    return False


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
    board_refs = load_board_commit_hashes(root)
    shipped_tip = resolve_shipped_tip(root)
    ancestry_cache: dict[tuple[str, str], bool] = {}
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
        if not isinstance(status, str):
            continue
        row_commit = task.get("commit_hash")
        ref_commit = (
            row_commit.strip()
            if isinstance(row_commit, str) and row_commit.strip()
            else board_refs.get(tid)
        )
        graded_commits = scan.graded_commits.get(tid, ())
        if graded_commits and verdict_covers(
            graded_commits, ref_commit, shipped_tip, root, ancestry_cache
        ):
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
            "and stale in_progress orphans (INT-GATE-2, commit-attributed "
            "coverage per INT-GATE-004)."
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
