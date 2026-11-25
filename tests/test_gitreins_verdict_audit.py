"""Tests for scripts/gitreins_verdict_audit.py (INT-GATE-2, INT-GATE-004).

Every fixture is a synthetic gitreins tree under ``tmp_path`` -- the live
repo's ``.gitreins/`` state is never read or mutated by this module. The
script is loaded via ``importlib`` from its ``scripts/`` path (no packaging
required) and exercised through ``main(argv)``, whose return value is the
process exit code.

Coverage semantics (INT-GATE-004): a verdict covers a task only when its
graded commit equals the row's recorded commit (tasks.yaml ``commit_hash``,
else the board row's ``commit_hash``), is an ancestor of it, or equals the
shipped tip when the row records no commit. Git-backed fixtures exercise the
real ``git merge-base`` ancestry arm; the hermetic fixtures rely on equality
and the fail-closed behavior of ancestry probes outside a git repo.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "gitreins_verdict_audit.py"

FAKE_SHA_A = "a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4"
FAKE_SHA_B = "b2c3d4e5b2c3d4e5b2c3d4e5b2c3d4e5b2c3d4e5"

requires_git = pytest.mark.skipif(
    shutil.which("git") is None, reason="git executable not available"
)


@pytest.fixture(scope="module")
def audit_mod() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gitreins_verdict_audit", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: the module uses `from __future__ import annotations`
    # with @dataclass, and dataclass processing resolves the string annotations
    # through sys.modules[cls.__module__].
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".gitreins").mkdir(parents=True)
    return root


def _write_tasks(root: Path, body: str) -> None:
    (root / ".gitreins" / "tasks.yaml").write_text(body, encoding="utf-8")


def _task_block(
    task_id: str,
    status: str,
    created_at: str,
    completed_at: str | None = None,
    commit_hash: str | None = None,
) -> str:
    lines = [
        f"- id: {task_id}",
        f"  status: {status}",
        f"  created_at: '{created_at}'",
    ]
    if completed_at is not None:
        lines.append(f"  completed_at: '{completed_at}'")
    if commit_hash is not None:
        lines.append(f"  commit_hash: '{commit_hash}'")
    return "\n".join(lines) + "\n"


def _write_verdict(
    root: Path,
    task_id: str,
    *,
    evaluated_at: str | None = None,
    raw: str | None = None,
    run_id: str = "run0001",
    commit: str | None = None,
) -> None:
    stamp = _utc_now().strftime("%Y-%m-%d")
    run_dir = root / ".gitreins" / "history" / stamp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "verdict.json"
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
        return
    payload: dict[str, Any] = {"task_id": task_id, "passed": True}
    if evaluated_at is not None:
        payload["evaluated_at"] = evaluated_at
    if commit is not None:
        payload["commit"] = commit
    path.write_text(json.dumps(payload), encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _init_git_repo(root: Path) -> str:
    """Turn the synthetic root into a real git repo with one commit; return HEAD."""
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    _git(root, "config", "user.email", "audit-test@example.com")
    _git(root, "config", "user.name", "audit-test")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "seed.txt")
    _git(root, "commit", "-q", "-m", "seed")
    return _git(root, "rev-parse", "HEAD")


def test_clean_repo_passes(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-OK",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
            commit_hash=FAKE_SHA_A,
        ),
    )
    _write_verdict(root, "T-OK", commit=FAKE_SHA_A)
    assert audit_mod.main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "RESULT: OK" in out
    assert "tasks_audited: 1" in out
    assert "verdicts_found: 1" in out


def test_complete_without_verdict_inside_window_fails(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-ORPHAN",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
        ),
    )
    assert audit_mod.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "T-ORPHAN" in out
    assert "ORPHAN-NOVERDICT: T-ORPHAN" in out


def test_exception_file_skips_orphan_with_notice(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-EXC",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
        ),
    )
    exceptions_path = root / ".gitreins" / "verdict_audit_exceptions.yaml"
    exceptions_path.write_text(
        "- id: T-EXC\n  reason: disclosed partial close\n", encoding="utf-8"
    )
    assert audit_mod.main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "exceptions_skipped: 1" in out
    assert "T-EXC: disclosed partial close" in out
    assert "RESULT: OK" in out


def test_stale_in_progress_without_verdict_fails(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block("T-STALE", "in_progress", _iso(now - timedelta(days=20))),
    )
    assert audit_mod.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "ORPHAN-STALE: T-STALE" in out


def test_fresh_in_progress_and_old_complete_not_flagged(
    audit_mod: ModuleType, tmp_path: Path
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block("T-FRESH", "in_progress", _iso(now - timedelta(days=1)))
        + _task_block(
            "T-OLD",
            "complete",
            _iso(now - timedelta(days=50)),
            _iso(now - timedelta(days=45)),
        ),
    )
    assert audit_mod.main([str(root)]) == 0


def test_malformed_verdict_is_counted_and_not_coverage(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-CORRUPT",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
        ),
    )
    _write_verdict(root, "T-CORRUPT", raw="{not valid json!!!")
    assert audit_mod.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "malformed_verdicts_skipped: 1" in out
    assert "ORPHAN-NOVERDICT: T-CORRUPT" in out


def test_malformed_verdict_tolerated_in_clean_repo(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-GOOD",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
            commit_hash=FAKE_SHA_A,
        ),
    )
    _write_verdict(root, "T-GOOD", commit=FAKE_SHA_A)
    _write_verdict(
        root, "T-UNRELATED", raw="<<<binary garbage\\u00ff", run_id="run0002"
    )
    assert audit_mod.main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "malformed_verdicts_skipped: 1" in out
    assert "verdicts_found: 1" in out
    assert "RESULT: OK" in out


def test_cap_hits_counted_and_exit_neutral(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-CAP",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
            commit_hash=FAKE_SHA_A,
        ),
    )
    _write_verdict(root, "T-CAP", commit=FAKE_SHA_A)
    _write_verdict(
        root,
        "T-CAP",
        raw=json.dumps(
            {
                "task_id": "T-CAP",
                "passed": False,
                "summary": "judge stopped: Iteration cap reached (300)",
            }
        ),
        run_id="run0002",
    )
    assert audit_mod.main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "cap_hits (WARN, exit-neutral): 1" in out
    assert "RESULT: OK" in out


def test_out_of_window_cap_hit_not_counted(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(root, "tasks:\n" + _task_block("T-NONE", "in_progress", _iso(now)))
    old_eval = _iso(now - timedelta(days=60))
    _write_verdict(
        root,
        "T-NONE",
        raw=json.dumps({"task_id": "T-NONE", "body": "Iteration cap reached"}),
    )
    stamp = _utc_now().strftime("%Y-%m-%d")
    stale_dir = root / ".gitreins" / "history" / stamp / "run-old"
    stale_dir.mkdir(parents=True, exist_ok=True)
    (stale_dir / "verdict.json").write_text(
        json.dumps(
            {"task_id": "T-NONE", "evaluated_at": old_eval, "body": "Iteration cap"}
        ),
        encoding="utf-8",
    )
    assert audit_mod.main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "cap_hits (WARN, exit-neutral): 1" in out


def test_json_mode_reports_exit_ok(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-J",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
            commit_hash=FAKE_SHA_A,
        ),
    )
    _write_verdict(root, "T-J", commit=FAKE_SHA_A)
    assert audit_mod.main([str(root), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["exit_ok"] is True
    assert report["tasks_audited"] == 1
    assert report["verdicts_found"] == 1
    assert report["window_days"] == audit_mod.DEFAULT_WINDOW_DAYS
    assert report["stale_days"] == audit_mod.DEFAULT_STALE_DAYS

    orphan_root = _make_repo(tmp_path / "orphan")
    _write_tasks(
        orphan_root,
        "tasks:\n"
        + _task_block(
            "T-J2",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
        ),
    )
    assert audit_mod.main([str(orphan_root), "--json"]) == 1
    orphan_report = json.loads(capsys.readouterr().out)
    assert orphan_report["exit_ok"] is False
    assert orphan_report["orphan_noverdict"] == ["T-J2"]


def test_bare_list_tasks_yaml_supported(audit_mod: ModuleType, tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        _task_block(
            "T-LIST",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
        ),
    )
    assert audit_mod.main([str(root)]) == 1


def test_tolerant_date_formats(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    z_date = _iso(now - timedelta(days=20)).replace("+00:00", "Z")
    naive_date = (now - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%S")
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block("T-ZULU", "in_progress", z_date)
        + _task_block("T-NAIVE", "in_progress", naive_date)
        + _task_block("T-BADDATE", "in_progress", "not-a-date")
        + _task_block(
            "T-OK-VERDICTED",
            "complete",
            "not-a-date",
            _iso(now - timedelta(days=1)),
            commit_hash=FAKE_SHA_A,
        ),
    )
    _write_verdict(root, "T-OK-VERDICTED", commit=FAKE_SHA_A)
    assert audit_mod.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "ORPHAN-STALE: T-ZULU, T-NAIVE" in out
    assert "T-BADDATE" not in out.split("ORPHAN-STALE:")[1].splitlines()[0]
    assert "RESULT: FAIL" in out


def test_missing_tasks_yaml_is_usage_error(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    # tasks.yaml intentionally never written -> usage/IO error, exit 2.
    assert audit_mod.main([str(root)]) == 2
    err = capsys.readouterr().err
    assert "ERROR:" in err


def test_missing_history_dir_is_empty_universe(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(root, "tasks:\n" + _task_block("T-NEW", "in_progress", _iso(now)))
    assert audit_mod.main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "verdicts_found: 0" in out
    assert "RESULT: OK" in out


# --- INT-GATE-004: verdict coverage must be commit-attributed ---------------


def test_verdict_on_unmerged_tip_is_not_coverage(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC fixture: one verdict grading an unmerged branch tip must fail the row.

    The graded commit is a real orphan-branch commit in a real git repo: it is
    neither the row's recorded commit, nor an ancestor of it, nor the shipped
    tip. Hermetic to the live tree -- no exceptions file exists in the fixture,
    so the arm stays asserted even if INT-GL-3 is later cleared by a dated
    exception entry.
    """
    root = _make_repo(tmp_path)
    shipped_tip = _init_git_repo(root)
    orphan_commit = _git(root, "commit-tree", "HEAD^{tree}", "-m", "unmerged tip")
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-UNMERGED",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
            commit_hash=shipped_tip,
        ),
    )
    _write_verdict(root, "T-UNMERGED", commit=orphan_commit)
    assert audit_mod.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "ORPHAN-NOVERDICT: T-UNMERGED" in out
    assert "RESULT: FAIL" in out


def test_verdict_on_unrelated_commit_without_git_is_not_coverage(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Hermetic unmerged-tip arm: unrelated graded commit never covers, and the
    fail-closed ancestry probe outside a git repo cannot rescue it."""
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-MISMATCH",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
            commit_hash=FAKE_SHA_A,
        ),
    )
    _write_verdict(root, "T-MISMATCH", commit=FAKE_SHA_B)
    assert audit_mod.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "ORPHAN-NOVERDICT: T-MISMATCH" in out


def test_row_without_commit_and_verdict_off_shipped_tip_is_not_coverage(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """INT-GL-3 mirror: commit_hash null, verdicts grade a branch tip that is
    not the shipped tree. With no recorded reference the only accepted
    attribution is shipped-tip equality; outside a git repo no tip resolves,
    so the verdict cannot cover and the row is flagged (INT-GATE-004)."""
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-NO-REF",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
        ),
    )
    _write_verdict(root, "T-NO-REF", commit=FAKE_SHA_B)
    assert audit_mod.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "ORPHAN-NOVERDICT: T-NO-REF" in out


def test_board_commit_hash_rescues_matching_verdict(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The tasks.yaml row has no commit_hash; the board row records one and the
    verdict grades exactly that commit -> covered."""
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-BOARD",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
        ),
    )
    board_dir = root / ".coding-hermes" / "board"
    board_dir.mkdir(parents=True)
    (board_dir / "tasks.jsonl").write_text(
        json.dumps({"id": "T-BOARD", "commit_hash": FAKE_SHA_A}) + "\n",
        encoding="utf-8",
    )
    _write_verdict(root, "T-BOARD", commit=FAKE_SHA_A)
    assert audit_mod.main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "RESULT: OK" in out


def test_board_commit_hash_mismatch_still_fails(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Board records one commit, the only verdict graded a different one."""
    root = _make_repo(tmp_path)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-BOARD-X",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
        ),
    )
    board_dir = root / ".coding-hermes" / "board"
    board_dir.mkdir(parents=True)
    (board_dir / "tasks.jsonl").write_text(
        json.dumps({"id": "T-BOARD-X", "commit_hash": FAKE_SHA_A}) + "\n",
        encoding="utf-8",
    )
    _write_verdict(root, "T-BOARD-X", commit=FAKE_SHA_B)
    assert audit_mod.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "ORPHAN-NOVERDICT: T-BOARD-X" in out


@requires_git
def test_verdict_on_shipped_tip_covers_row_without_recorded_commit(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Shipped-tip arm: row records no commit; the verdict graded HEAD -> OK."""
    root = _make_repo(tmp_path)
    shipped_tip = _init_git_repo(root)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-TIP",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
        ),
    )
    _write_verdict(root, "T-TIP", commit=shipped_tip)
    assert audit_mod.main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "RESULT: OK" in out


@requires_git
def test_verdict_on_ancestor_of_row_commit_covers(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ancestor arm: the verdict graded the pre-merge branch tip that the row's
    recorded commit was built on -> covered."""
    root = _make_repo(tmp_path)
    _init_git_repo(root)
    (root / "second.txt").write_text("second\n", encoding="utf-8")
    _git(root, "add", "second.txt")
    _git(root, "commit", "-q", "-m", "second")
    row_commit = _git(root, "rev-parse", "HEAD")
    base_commit = _git(root, "rev-parse", "HEAD~1")
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-ANC",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
            commit_hash=row_commit,
        ),
    )
    _write_verdict(root, "T-ANC", commit=base_commit)
    assert audit_mod.main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "RESULT: OK" in out


@requires_git
def test_verdict_graded_at_worktree_tip_above_row_commit_is_not_coverage(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The INT-GL-3 class with a recorded row commit: the judge graded a tip
    built ON TOP of the row's commit that never landed (descendant, not
    ancestor) -- the one-directional predicate must not count it."""
    root = _make_repo(tmp_path)
    row_commit = _init_git_repo(root)
    base_branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    # An unmerged descendant: a commit on a side branch above the row commit.
    _git(root, "checkout", "-q", "-b", "side")
    (root / "side.txt").write_text("side\n", encoding="utf-8")
    _git(root, "add", "side.txt")
    _git(root, "commit", "-q", "-m", "unmerged work")
    side_tip = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", base_branch)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-WT-TIP",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
            commit_hash=row_commit,
        ),
    )
    _write_verdict(root, "T-WT-TIP", commit=side_tip)
    assert audit_mod.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "ORPHAN-NOVERDICT: T-WT-TIP" in out


@requires_git
def test_verdict_without_commit_field_is_not_coverage(
    audit_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unattributed verdict (no commit field) cannot prove the shipped state
    was graded -- existence alone no longer covers (INT-GATE-004)."""
    root = _make_repo(tmp_path)
    _init_git_repo(root)
    now = _utc_now()
    _write_tasks(
        root,
        "tasks:\n"
        + _task_block(
            "T-NOCOMMIT",
            "complete",
            _iso(now - timedelta(days=2)),
            _iso(now - timedelta(days=1)),
            commit_hash=FAKE_SHA_A,
        ),
    )
    _write_verdict(root, "T-NOCOMMIT")
    assert audit_mod.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "ORPHAN-NOVERDICT: T-NOCOMMIT" in out
