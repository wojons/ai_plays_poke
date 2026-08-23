"""Unit tests for GAP-028: boot-state resolution + lock-rate summary metrics.

Covers cron_runner._resolve_boot_state (default / skip / explicit path)
and _format_summary (per-run lock-rate fraction + distinct-tile count).
"""

from __future__ import annotations

import pytest

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


class TestDryRun:
    """--dry-run precheck (GAP-032): validates setup, exits 0, never boots.

    The precheck runs at import time before the heavy third-party imports,
    so these tests exercise it directly with explicit argv (same pattern as
    TestResolveBootState). A subprocess test is unnecessary: the precheck's
    only side effects are stdout prints and sys.exit.
    """

    def test_dry_run_exits_zero_with_config_summary(self, monkeypatch, capsys, tmp_path) -> None:
        rom = tmp_path / "rom.gb"
        rom.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(rom))
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", tmp_path / "boot.state")
        (tmp_path / "boot.state").write_bytes(b"x")
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "ROM path:" in out and "[OK]" in out
        assert "Boot state:" in out
        assert "Cycles:" in out
        assert "Run ID:" in out
        assert "Model/provider:" in out
        assert "no emulator boot, no LLM/API calls" in out
        assert "📡" not in out  # no API call lines

    def test_dry_run_reflects_cycles_run_id_and_boot_state(self, monkeypatch, capsys, tmp_path) -> None:
        rom = tmp_path / "rom.gb"
        rom.write_bytes(b"x")
        ckpt = tmp_path / "ckpt.state"
        ckpt.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(rom))
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(
                ["--dry-run", "--cycles", "5", "--run-id", "probe", "--boot-state", str(ckpt)]
            )
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "Cycles:         5" in out
        assert "Run ID:         probe" in out
        assert f"{ckpt}  [OK]" in out

    def test_dry_run_boot_state_skip_prints_bypass(self, monkeypatch, capsys, tmp_path) -> None:
        rom = tmp_path / "rom.gb"
        rom.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(rom))
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run", "--boot-state", "skip"])
        assert e.value.code == 0
        assert "skip (legacy intro bypass)" in capsys.readouterr().out

    def test_dry_run_missing_boot_state_still_exits_zero(self, monkeypatch, capsys, tmp_path) -> None:
        rom = tmp_path / "rom.gb"
        rom.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(rom))
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run", "--boot-state", str(tmp_path / "nope.state")])
        assert e.value.code == 0
        assert "fall back to intro bypass" in capsys.readouterr().out

    def test_dry_run_missing_rom_exits_one(self, monkeypatch, capsys, tmp_path) -> None:
        monkeypatch.setattr(cron_runner, "ROM", str(tmp_path / "nope.gb"))
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 1
        assert "ERROR: ROM not found" in capsys.readouterr().out

    def test_no_dry_run_returns_without_exiting(self) -> None:
        assert cron_runner._dry_run_precheck(["--cycles", "3"]) is None

    def test_main_parser_exposes_dry_run_flag(self) -> None:
        # --help must list --dry-run (GAP-032 acceptance); the flag must
        # parse on the real parser main() uses.
        args = cron_runner._main_parser().parse_args(["--dry-run"])
        assert args.dry_run is True
