"""Tests for scripts/gitreins_verdict_audit.py (INT-GATE-2).

Every fixture is a synthetic gitreins tree under ``tmp_path`` -- the live
repo's ``.gitreins/`` state is never read or mutated by this module. The
script is loaded via ``importlib`` from its ``scripts/`` path (no packaging
required) and exercised through ``main(argv)``, whose return value is the
process exit code.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "gitreins_verdict_audit.py"


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
) -> str:
    lines = [
        f"- id: {task_id}",
        f"  status: {status}",
        f"  created_at: '{created_at}'",
    ]
    if completed_at is not None:
        lines.append(f"  completed_at: '{completed_at}'")
    return "\n".join(lines) + "\n"


def _write_verdict(
    root: Path,
    task_id: str,
    *,
    evaluated_at: str | None = None,
    raw: str | None = None,
    run_id: str = "run0001",
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
    path.write_text(json.dumps(payload), encoding="utf-8")


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
        ),
    )
    _write_verdict(root, "T-OK")
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
        ),
    )
    _write_verdict(root, "T-GOOD")
    _write_verdict(root, "T-UNRELATED", raw="<<<binary garbage\u00ff", run_id="run0002")
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
        ),
    )
    _write_verdict(root, "T-CAP")
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
        ),
    )
    _write_verdict(root, "T-J")
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
        ),
    )
    _write_verdict(root, "T-OK-VERDICTED")
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
