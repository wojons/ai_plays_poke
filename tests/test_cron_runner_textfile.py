"""Tests for the node_exporter textfile record written by the cron lane."""

from __future__ import annotations

import re
from pathlib import Path

import cron_runner


def _autonomy(*, backtrack_rate: float | None = 0.25) -> dict[str, int | float | None]:
    return {
        "decisions_total": 7,
        "map_transitions_observed": 3,
        "decisions_per_map_transition": 7 / 3,
        "backtrack_rate": backtrack_rate,
    }


def _sample_value(text: str, metric: str, *, outcome: str | None = None) -> float:
    suffix = f'{{outcome="{outcome}"}}' if outcome is not None else ""
    match = re.search(rf"^{re.escape(metric + suffix)} ([0-9.]+)$", text, re.MULTILINE)
    assert match is not None
    return float(match.group(1))


def test_first_write_creates_completed_record(tmp_path: Path) -> None:
    result = cron_runner._write_textfile_record(
        tmp_path, "run-a", "completed", 1.5, _autonomy()
    )

    assert result == tmp_path / "aipp_run.prom"
    text = result.read_text(encoding="utf-8")
    assert _sample_value(text, "aipp_run_completed_total", outcome="completed") == 1
    assert _sample_value(text, "aipp_run_last_decisions_total") == 7


def test_second_write_accumulates_and_error_keeps_completed_value(
    tmp_path: Path,
) -> None:
    cron_runner._write_textfile_record(tmp_path, "run-a", "completed", 1.5, _autonomy())
    cron_runner._write_textfile_record(tmp_path, "run-b", "completed", 2.5, _autonomy())
    second_text = (tmp_path / "aipp_run.prom").read_text(encoding="utf-8")
    assert (
        _sample_value(second_text, "aipp_run_completed_total", outcome="completed") == 2
    )

    cron_runner._write_textfile_record(tmp_path, "run-c", "error", 0.5, _autonomy())
    error_text = (tmp_path / "aipp_run.prom").read_text(encoding="utf-8")
    assert (
        _sample_value(error_text, "aipp_run_completed_total", outcome="completed") == 2
    )
    assert _sample_value(error_text, "aipp_run_completed_total", outcome="error") == 1


def test_optional_backtrack_rate_is_omitted_or_emitted(tmp_path: Path) -> None:
    cron_runner._write_textfile_record(
        tmp_path, "run-a", "completed", 1.0, _autonomy(backtrack_rate=None)
    )
    text = (tmp_path / "aipp_run.prom").read_text(encoding="utf-8")
    assert "aipp_run_last_backtrack_rate " not in text

    cron_runner._write_textfile_record(
        tmp_path, "run-b", "completed", 1.0, _autonomy(backtrack_rate=0.375)
    )
    text = (tmp_path / "aipp_run.prom").read_text(encoding="utf-8")
    assert _sample_value(text, "aipp_run_last_backtrack_rate") == 0.375


def test_unwritable_parent_returns_none(tmp_path: Path) -> None:
    parent_file = tmp_path / "afile"
    parent_file.write_text("not a directory", encoding="utf-8")

    result = cron_runner._write_textfile_record(
        parent_file / "x", "run-a", "completed", 1.0, _autonomy()
    )

    assert result is None


def test_parser_accepts_textfile_dir_and_has_expected_default(tmp_path: Path) -> None:
    parser = cron_runner._main_parser()

    assert parser.parse_args([]).textfile_dir == cron_runner.DEFAULT_TEXTFILE_DIR
    assert parser.parse_args(["--textfile-dir", str(tmp_path)]).textfile_dir == tmp_path
