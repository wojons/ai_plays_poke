"""Unit tests for GAP-028: boot-state resolution + lock-rate summary metrics.

Covers cron_runner._resolve_boot_state (default / skip / explicit path)
and _format_summary (per-run lock-rate fraction + distinct-tile count).
"""

from __future__ import annotations

import cron_runner


class TestResolveBootState:
    """--boot-state / data/boot.state resolution (GAP-028)."""

    def test_default_uses_data_boot_state_when_present(self, monkeypatch, tmp_path) -> None:
        ckpt = tmp_path / "boot.state"
        ckpt.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", ckpt)
        assert cron_runner._resolve_boot_state(None) == ckpt

    def test_skip_returns_none(self) -> None:
        assert cron_runner._resolve_boot_state("skip") is None
        assert cron_runner._resolve_boot_state("SKIP") is None

    def test_missing_default_returns_none(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", tmp_path / "nope.state")
        assert cron_runner._resolve_boot_state(None) is None

    def test_explicit_path_used(self, tmp_path) -> None:
        ckpt = tmp_path / "custom.state"
        ckpt.write_bytes(b"x")
        assert cron_runner._resolve_boot_state(str(ckpt)) == ckpt

    def test_explicit_missing_path_returns_none(self, tmp_path) -> None:
        assert cron_runner._resolve_boot_state(str(tmp_path / "missing.state")) is None


class TestFormatSummary:
    """Final summary line: lock-rate fraction + distinct tiles (GAP-028)."""

    def test_includes_lock_rate_and_tiles(self) -> None:
        s = cron_runner._format_summary("run1", 20, {"overworld"}, 5, 20, 3)
        assert "[run1] Done. 20 actions. Screens: {'overworld'}" in s
        assert "lock-rate: 5/20 cycles" in s
        assert "25%" in s
        assert "distinct tiles: 3" in s

    def test_zero_lock_rate(self) -> None:
        s = cron_runner._format_summary("run2", 10, {"overworld"}, 0, 10, 1)
        assert "lock-rate: 0/10 cycles" in s
        assert "0%" in s

    def test_half_lock_rate_rounds_to_50_percent(self) -> None:
        s = cron_runner._format_summary("run3", 10, {"overworld"}, 5, 10, 2)
        assert "50%" in s

    def test_one_hundred_percent_lock_rate(self) -> None:
        s = cron_runner._format_summary("run4", 5, {"overworld"}, 5, 5, 1)
        assert "lock-rate: 5/5 cycles" in s
        assert "100%" in s
