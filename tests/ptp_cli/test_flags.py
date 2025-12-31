#!/usr/bin/env python3
"""
Unit tests for CLI Flag System

Tests for flag parsing, validation, and configuration.
"""

import pytest
import sys
import os
from pathlib import Path

# Add project root and src to path
project_root = Path(__file__).parent.parent.parent
src_root = project_root / "src"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(src_root))

from ptp_cli.flags import (
    CLIFlagParser,
    FullConfig,
    TickRateConfig,
    ScreenshotConfig,
    CommandBufferConfig,
    RunLimitsConfig,
    SnapshotConfig,
    ExperimentConfig,
    SystemConfig,
    LimitAction,
    FailMode,
    BudgetMode,
    ResultsFormat
)


class TestTickRateConfig:
    """Tests for TickRateConfig validation."""

    def test_valid_defaults(self):
        """Test default values are valid."""
        config = TickRateConfig()
        errors = config._validate_config()
        assert len(errors) == 0

    def test_valid_custom_values(self):
        """Test custom values within range."""
        config = TickRateConfig(base=15, battle=3, timeout=60)
        errors = config._validate_config()
        assert len(errors) == 0

    def test_invalid_base_too_low(self):
        """Test base tick rate too low."""
        config = TickRateConfig(base=0)
        errors = config._validate_config()
        assert "tick-rate-base must be >= 1" in errors

    def test_invalid_base_too_high(self):
        """Test base tick rate too high."""
        config = TickRateConfig(base=100)
        errors = config._validate_config()
        assert "tick-rate-base must be <= 60" in errors

    def test_invalid_battle_too_low(self):
        """Test battle tick rate too low."""
        config = TickRateConfig(battle=0)
        errors = config._validate_config()
        assert "tick-rate-battle must be >= 1" in errors

    def test_invalid_timeout_too_low(self):
        """Test timeout too low."""
        config = TickRateConfig(timeout=1)
        errors = config._validate_config()
        assert "tick-rate-timeout must be >= 5" in errors

    def test_adaptive_with_high_base_warning(self):
        """Test adaptive mode warning with high base rate."""
        config = TickRateConfig(base=45, adaptive=True)
        errors = config._validate_config()
        assert any("adaptive mode works best" in e for e in errors)

    def test_budget_mode_without_limit(self):
        """Test budget mode requires limit."""
        config = TickRateConfig(budget_mode="hourly", budget_limit=None)
        errors = config._validate_config()
        assert any("tick-rate-budget-limit required" in e for e in errors)

    def test_budget_limit_negative(self):
        """Test negative budget limit."""
        config = TickRateConfig(budget_limit=-5.0)
        errors = config._validate_config()
        assert "tick-rate-budget-limit must be positive" in errors


class TestScreenshotConfig:
    """Tests for ScreenshotConfig validation."""

    def test_valid_defaults(self):
        """Test default values are valid."""
        config = ScreenshotConfig()
        errors = config._validate_config()
        assert len(errors) == 0

    def test_valid_custom_values(self):
        """Test custom values within range."""
        config = ScreenshotConfig(interval=50, quality=90, max_storage_gb=100.0)
        errors = config._validate_config()
        assert len(errors) == 0

    def test_invalid_interval_too_low(self):
        """Test interval too low."""
        config = ScreenshotConfig(interval=0)
        errors = config._validate_config()
        assert "screenshot-interval must be >= 1" in errors

    def test_invalid_quality_too_low(self):
        """Test quality below range."""
        config = ScreenshotConfig(quality=-1)
        errors = config._validate_config()
        assert "screenshot-quality must be 0-100" in errors

    def test_invalid_quality_too_high(self):
        """Test quality above range."""
        config = ScreenshotConfig(quality=101)
        errors = config._validate_config()
        assert "screenshot-quality must be 0-100" in errors

    def test_invalid_max_storage(self):
        """Test non-positive max storage."""
        config = ScreenshotConfig(max_storage_gb=0)
        errors = config._validate_config()
        assert "screenshot-max-storage must be positive" in errors


class TestCommandBufferConfig:
    """Tests for CommandBufferConfig validation."""

    def test_valid_defaults(self):
        """Test default values are valid."""
        config = CommandBufferConfig()
        errors = config._validate_config()
        assert len(errors) == 0

    def test_invalid_buffer_size_too_low(self):
        """Test buffer size too low."""
        config = CommandBufferConfig(buffer_size=0)
        errors = config._validate_config()
        assert "command-buffer-size must be >= 1" in errors

    def test_invalid_timeout_too_low(self):
        """Test timeout too low."""
        config = CommandBufferConfig(timeout=0)
        errors = config._validate_config()
        assert "command-timeout must be >= 1" in errors

    def test_invalid_rollback_history(self):
        """Test negative rollback history."""
        config = CommandBufferConfig(rollback_history=-1)
        errors = config._validate_config()
        assert "command-rollback-history must be >= 0" in errors

    def test_invalid_stale_threshold(self):
        """Test negative stale threshold."""
        config = CommandBufferConfig(stale_threshold=-1)
        errors = config._validate_config()
        assert "command-stale-threshold must be >= 0" in errors


class TestRunLimitsConfig:
    """Tests for RunLimitsConfig validation."""

    def test_valid_defaults(self):
        """Test default values are valid."""
        config = RunLimitsConfig()
        errors = config._validate_config()
        assert len(errors) == 0

    def test_invalid_max_time(self):
        """Test non-positive max time."""
        config = RunLimitsConfig(max_time_seconds=0)
        errors = config._validate_config()
        assert "max-time must be positive" in errors

    def test_invalid_max_ticks(self):
        """Test non-positive max ticks."""
        config = RunLimitsConfig(max_ticks=-1)
        errors = config._validate_config()
        assert "max-ticks must be positive" in errors

    def test_invalid_max_cost(self):
        """Test non-positive max cost."""
        config = RunLimitsConfig(max_cost=0)
        errors = config._validate_config()
        assert "max-cost must be positive" in errors

    def test_invalid_max_pokemon_caught(self):
        """Test non-positive max Pokemon caught."""
        config = RunLimitsConfig(max_pokemon_caught=0)
        errors = config._validate_config()
        assert "max-pokemon-caught must be positive" in errors

    def test_invalid_max_badges_too_low(self):
        """Test max badges below range."""
        config = RunLimitsConfig(max_badges=-1)
        errors = config._validate_config()
        assert "max-badges must be 0-16" in errors

    def test_invalid_max_badges_too_high(self):
        """Test max badges above range."""
        config = RunLimitsConfig(max_badges=20)
        errors = config._validate_config()
        assert "max-badges must be 0-16" in errors

    def test_invalid_max_level_too_low(self):
        """Test max level below range."""
        config = RunLimitsConfig(max_level=0)
        errors = config._validate_config()
        assert "max-level must be 1-100" in errors

    def test_invalid_max_level_too_high(self):
        """Test max level above range."""
        config = RunLimitsConfig(max_level=150)
        errors = config._validate_config()
        assert "max-level must be 1-100" in errors

    def test_invalid_grace_period(self):
        """Test negative grace period."""
        config = RunLimitsConfig(grace_period=-1)
        errors = config._validate_config()
        assert "limit-grace-period must be >= 0" in errors


class TestSnapshotConfig:
    """Tests for SnapshotConfig validation."""

    def test_valid_defaults(self):
        """Test default values are valid."""
        config = SnapshotConfig()
        errors = config._validate_config()
        assert len(errors) == 0

    def test_valid_custom_values(self):
        """Test custom values within range."""
        config = SnapshotConfig(
            memory_count=20,
            disk_interval=500,
            on_event=["catch", "battle"]
        )
        errors = config._validate_config()
        assert len(errors) == 0

    def test_invalid_memory_count(self):
        """Test negative memory count."""
        config = SnapshotConfig(memory_count=-1)
        errors = config._validate_config()
        assert "snapshot-memory must be >= 0" in errors

    def test_invalid_disk_interval(self):
        """Test disk interval too low."""
        config = SnapshotConfig(disk_interval=50)
        errors = config._validate_config()
        assert "snapshot-disk must be >= 100" in errors

    def test_invalid_event(self):
        """Test invalid event in on_event."""
        config = SnapshotConfig(on_event=["invalid_event"])
        errors = config._validate_config()
        assert "invalid snapshot-on-event" in errors[0]

    def test_invalid_max_disk(self):
        """Test non-positive max disk."""
        config = SnapshotConfig(max_disk_gb=0)
        errors = config._validate_config()
        assert "snapshot-max-disk must be positive" in errors

    def test_invalid_rollback_grace(self):
        """Test negative rollback grace."""
        config = SnapshotConfig(rollback_grace=-1)
        errors = config._validate_config()
        assert "rollback-grace must be >= 0" in errors


class TestExperimentConfig:
    """Tests for ExperimentConfig validation."""

    def test_valid_defaults(self):
        """Test default values are valid."""
        config = ExperimentConfig()
        errors = config._validate_config()
        assert len(errors) == 0

    def test_invalid_parallel_workers(self):
        """Test workers below 1."""
        config = ExperimentConfig(parallel_workers=0)
        errors = config._validate_config()
        assert "parallel-workers must be >= 1" in errors

    def test_invalid_sequential_retry(self):
        """Test negative retry count."""
        config = ExperimentConfig(sequential_retry=-1)
        errors = config._validate_config()
        assert "sequential-retry must be >= 0" in errors

    def test_invalid_memory_limit(self):
        """Test non-positive memory limit."""
        config = ExperimentConfig(memory_limit_gb=0)
        errors = config._validate_config()
        assert "parallel-memory-limit must be positive" in errors

    def test_invalid_api_rate_limit(self):
        """Test API rate limit below 1."""
        config = ExperimentConfig(api_rate_limit=0)
        errors = config._validate_config()
        assert "parallel-api-rate-limit must be >= 1" in errors

    def test_invalid_checkpoint_frequency(self):
        """Test negative checkpoint frequency."""
        config = ExperimentConfig(checkpoint_frequency=-1)
        errors = config._validate_config()
        assert "checkpoint-frequency must be >= 0" in errors


class TestCLIFlagParser:
    """Tests for CLIFlagParser."""

    def test_parse_basic_args(self):
        """Test parsing basic required arguments."""
        parser = CLIFlagParser()
        args = ["--rom", "test.gb"]
        config = parser.parse_args(args)

        assert config.rom_path == "test.gb"
        assert config.save_dir == "./game_saves"

    def test_parse_all_defaults(self):
        """Test parsing with all defaults."""
        parser = CLIFlagParser()
        args = ["--rom", "/tmp/test_pokemon.gb"]
        config = parser.parse_args(args)

        assert config.tick_rate.base == 10
        assert config.screenshot.interval == 100
        assert config.command_buffer.buffer_size == 10
        assert config.limits.on_limit == "save-and-exit"
        assert config.snapshot.memory_count == 10
        assert config.experiment.name == "default"

    def test_parse_tick_rate_flags(self):
        """Test parsing tick rate flags."""
        parser = CLIFlagParser()
        args = [
            "--rom", "/tmp/test_pokemon.gb",
            "--tick-rate-base", "20",
            "--tick-rate-battle", "5",
            "--tick-rate-timeout", "60",
            "--tick-rate-adaptive"
        ]
        config = parser.parse_args(args)

        assert config.tick_rate.base == 20
        assert config.tick_rate.battle == 5
        assert config.tick_rate.timeout == 60
        assert config.tick_rate.adaptive is True

    def test_parse_screenshot_flags(self):
        """Test parsing screenshot flags."""
        parser = CLIFlagParser()
        args = [
            "--rom", "/tmp/test_pokemon.gb",
            "--screenshot-interval", "50",
            "--screenshot-quality", "90",
            "--screenshot-on-change",
            "--screenshot-async"
        ]
        config = parser.parse_args(args)

        assert config.screenshot.interval == 50
        assert config.screenshot.quality == 90
        assert config.screenshot.on_change is True
        assert config.screenshot.async_capture is True

    def test_parse_limit_flags(self):
        """Test parsing limit flags."""
        parser = CLIFlagParser()
        args = [
            "--rom", "/tmp/test_pokemon.gb",
            "--max-time", "3600",
            "--max-ticks", "100000",
            "--max-cost", "10.00",
            "--max-badges", "8",
            "--on-limit", "save-only"
        ]
        config = parser.parse_args(args)

        assert config.limits.max_time_seconds == 3600
        assert config.limits.max_ticks == 100000
        assert config.limits.max_cost == 10.00
        assert config.limits.max_badges == 8
        assert config.limits.on_limit == "save-only"

    def test_parse_snapshot_flags(self):
        """Test parsing snapshot flags."""
        parser = CLIFlagParser()
        args = [
            "--rom", "/tmp/test_pokemon.gb",
            "--snapshot-memory", "50",
            "--snapshot-disk", "5000",
            "--snapshot-on-event", "catch,battle,badge",
            "--snapshot-compress"
        ]
        config = parser.parse_args(args)

        assert config.snapshot.memory_count == 50
        assert config.snapshot.disk_interval == 5000
        assert config.snapshot.on_event == ["catch", "battle", "badge"]
        assert config.snapshot.compress is True

    def test_parse_experiment_flags(self):
        """Test parsing experiment flags."""
        parser = CLIFlagParser()
        args = [
            "--rom", "/tmp/test_pokemon.gb",
            "--experiment-name", "benchmark-001",
            "--parallel-workers", "4",
            "--aggregate-stats",
            "--export-results",
            "--results-format", "parquet"
        ]
        config = parser.parse_args(args)

        assert config.experiment.name == "benchmark-001"
        assert config.experiment.parallel_workers == 4
        assert config.experiment.aggregate_stats is True
        assert config.experiment.export_results is True
        assert config.experiment.results_format == "parquet"

    def test_parse_system_flags(self):
        """Test parsing system flags."""
        parser = CLIFlagParser()
        args = [
            "--rom", "/tmp/test_pokemon.gb",
            "--verbose",
            "--log-file", "output.log",
            "--random-seed", "42"
        ]
        config = parser.parse_args(args)

        assert config.system.verbose is True
        assert config.system.log_file == "output.log"
        assert config.system.random_seed == 42

    def test_parse_invalid_quality_range(self):
        """Test invalid quality range."""
        parser = CLIFlagParser()
        args = [
            "--rom", "/tmp/test_pokemon.gb",
            "--screenshot-quality", "150"
        ]
        with pytest.raises(SystemExit):
            parser.parse_args(args)

    def test_validate_valid_config(self):
        """Test validation of valid configuration."""
        parser = CLIFlagParser()
        args = ["--rom", "/tmp/test_pokemon.gb"]
        config = parser.parse_args(args)
        errors = parser.validate_config(config)

        assert len(errors) == 0

    def test_validate_verbose_quiet_conflict(self):
        """Test validation catches verbose/quiet conflict."""
        parser = CLIFlagParser()
        args = [
            "--rom", "/tmp/test_pokemon.gb",
            "--verbose",
            "--quiet"
        ]
        config = parser.parse_args(args)
        errors = parser.validate_config(config)

        assert any("Cannot use both --verbose and --quiet" in e for e in errors)

    def test_parse_and_validate_success(self):
        """Test parse_and_validate returns valid config."""
        parser = CLIFlagParser()
        args = ["--rom", "/tmp/test_pokemon.gb"]
        config, errors = parser.parse_and_validate(args)

        assert len(errors) == 0
        assert isinstance(config, FullConfig)

    def test_parse_and_validate_error(self):
        """Test parse_and_validate returns errors for invalid config."""
        parser = CLIFlagParser()
        args = [
            "--rom", "/tmp/test_pokemon.gb",
            "--verbose",
            "--quiet"
        ]
        config, errors = parser.parse_and_validate(args)

        assert len(errors) > 0


class TestFullConfig:
    """Tests for FullConfig."""

    def test_to_dict(self):
        """Test to_dict conversion."""
        config = FullConfig(
            rom_path="pokemon.gb",
            save_dir="./saves"
        )

        result = config.to_dict()

        assert result["rom_path"] == "pokemon.gb"
        assert result["save_dir"] == "./saves"
        assert result["tick_rate"]["base"] == 10
        assert result["screenshot"]["interval"] == 100

    def test_validate_missing_rom(self):
        """Test validation fails for missing ROM."""
        config = FullConfig(rom_path="")
        errors = config.validate()

        assert len(errors) > 0
        assert any("rom path is required" in e for e in errors)

    def test_validate_nonexistent_rom(self):
        """Test validation fails for non-existent ROM."""
        config = FullConfig(rom_path="/nonexistent/pokemon.gb")
        errors = config.validate()

        assert len(errors) > 0
        assert any("ROM file not found" in e for e in errors)

    def test_validate_valid_rom(self):
        """Test validation passes for valid ROM path."""
        rom_path = Path("/tmp/test_rom.gb")
        rom_path.touch()
        try:
            config = FullConfig(rom_path=str(rom_path))
            errors = config.validate()

            assert len(errors) == 0
        finally:
            rom_path.unlink()


class TestEnums:
    """Tests for enum types."""

    def test_limit_action_values(self):
        """Test LimitAction enum values."""
        assert LimitAction.SAVE_AND_EXIT.value == "save-and-exit"
        assert LimitAction.SAVE_ONLY.value == "save-only"
        assert LimitAction.ABORT.value == "abort"

    def test_fail_mode_values(self):
        """Test FailMode enum values."""
        assert FailMode.CONTINUE.value == "continue"
        assert FailMode.FAST_FAIL.value == "fast-fail"
        assert FailMode.RETRY.value == "retry"

    def test_budget_mode_values(self):
        """Test BudgetMode enum values."""
        assert BudgetMode.HOURLY.value == "hourly"
        assert BudgetMode.DAILY.value == "daily"
        assert BudgetMode.RUN.value == "run"

    def test_results_format_values(self):
        """Test ResultsFormat enum values."""
        assert ResultsFormat.JSON.value == "json"
        assert ResultsFormat.CSV.value == "csv"
        assert ResultsFormat.PARQUET.value == "parquet"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])