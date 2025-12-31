#!/usr/bin/env python3
"""
PTP-01X CLI Flag System

Complete argparse configuration for all CLI flags including:
- Tick Rate Control
- Screenshot Control
- Command Buffer Control
- Run Limits
- Snapshot Management
- Experiment Orchestration
- System Flags

Version: 2.0
Date: December 31, 2025
"""

import argparse
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from enum import Enum


class LimitAction(Enum):
    """Action to take when a limit is reached."""
    SAVE_AND_EXIT = "save-and-exit"
    SAVE_ONLY = "save-only"
    ABORT = "abort"


class FailMode(Enum):
    """Behavior when experiment runs fail."""
    CONTINUE = "continue"
    FAST_FAIL = "fast-fail"
    RETRY = "retry"


class BudgetMode(Enum):
    """Budget period mode for cost limiting."""
    HOURLY = "hourly"
    DAILY = "daily"
    RUN = "run"


class ResultsFormat(Enum):
    """Output format for experiment results."""
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"


@dataclass
class TickRateConfig:
    """Tick rate configuration."""
    base: int = 10
    battle: int = 2
    timeout: int = 30
    adaptive: bool = False
    budget_mode: Optional[str] = None
    budget_limit: Optional[float] = None

    def _validate_config(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if self.base < 1:
            errors.append("tick-rate-base must be >= 1")
        if self.base > 60:
            errors.append("tick-rate-base must be <= 60")
        if self.battle < 1:
            errors.append("tick-rate-battle must be >= 1")
        if self.battle > 30:
            errors.append("tick-rate-battle must be <= 30")
        if self.timeout < 5:
            errors.append("tick-rate-timeout must be >= 5")
        if self.adaptive and self.base > 30:
            errors.append("adaptive mode works best with tick-rate-base <= 30")
        if self.budget_mode and self.budget_limit is None:
            errors.append("tick-rate-budget-limit required when tick-rate-budget is set")
        if self.budget_limit and self.budget_limit <= 0:
            errors.append("tick-rate-budget-limit must be positive")
        return errors


@dataclass
class ScreenshotConfig:
    """Screenshot configuration."""
    interval: int = 100
    battle_turn: int = 1
    on_error: int = 1
    on_change: bool = False
    quality: int = 85
    max_storage_gb: float = 50.0
    async_capture: bool = False
    compress: bool = False

    def _validate_config(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if self.interval < 1:
            errors.append("screenshot-interval must be >= 1")
        if self.quality < 0 or self.quality > 100:
            errors.append("screenshot-quality must be 0-100")
        if self.max_storage_gb <= 0:
            errors.append("screenshot-max-storage must be positive")
        return errors


@dataclass
class CommandBufferConfig:
    """Command buffer configuration."""
    buffer_size: int = 10
    timeout: int = 5
    validation_enabled: bool = False
    rollback_history: int = 100
    interrupt_battle: bool = True
    stale_threshold: int = 2

    def _validate_config(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if self.buffer_size < 1:
            errors.append("command-buffer-size must be >= 1")
        if self.timeout < 1:
            errors.append("command-timeout must be >= 1")
        if self.rollback_history < 0:
            errors.append("command-rollback-history must be >= 0")
        if self.stale_threshold < 0:
            errors.append("command-stale-threshold must be >= 0")
        return errors


@dataclass
class RunLimitsConfig:
    """Run limits configuration."""
    max_time_seconds: Optional[int] = None
    max_ticks: Optional[int] = None
    max_cost: Optional[float] = None
    max_pokemon_caught: Optional[int] = None
    max_badges: Optional[int] = None
    max_level: Optional[int] = None
    on_limit: str = "save-and-exit"
    grace_period: int = 30

    def _validate_config(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if self.max_time_seconds is not None and self.max_time_seconds <= 0:
            errors.append("max-time must be positive")
        if self.max_ticks is not None and self.max_ticks <= 0:
            errors.append("max-ticks must be positive")
        if self.max_cost is not None and self.max_cost <= 0:
            errors.append("max-cost must be positive")
        if self.max_pokemon_caught is not None and self.max_pokemon_caught <= 0:
            errors.append("max-pokemon-caught must be positive")
        if self.max_badges is not None and (self.max_badges < 0 or self.max_badges > 16):
            errors.append("max-badges must be 0-16")
        if self.max_level is not None and (self.max_level < 1 or self.max_level > 100):
            errors.append("max-level must be 1-100")
        if self.grace_period < 0:
            errors.append("limit-grace-period must be >= 0")
        return errors


@dataclass
class SnapshotConfig:
    """Snapshot management configuration."""
    memory_count: int = 10
    disk_interval: int = 1000
    on_event: List[str] = field(default_factory=list)
    max_disk_gb: float = 20.0
    compress: bool = False
    validation_enabled: bool = False
    rollback_on_error: bool = False
    rollback_grace: int = 3
    allow_share: bool = False
    name: Optional[str] = None

    def _validate_config(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        valid_events = {"catch", "battle", "badge", "death"}
        for event in self.on_event:
            if event not in valid_events:
                errors.append(f"invalid snapshot-on-event: {event}")
        if self.memory_count < 0:
            errors.append("snapshot-memory must be >= 0")
        if self.disk_interval < 100:
            errors.append("snapshot-disk must be >= 100")
        if self.max_disk_gb <= 0:
            errors.append("snapshot-max-disk must be positive")
        if self.rollback_grace < 0:
            errors.append("rollback-grace must be >= 0")
        return errors


@dataclass
class SaveStateConfig:
    """Save state management configuration."""
    interval_ticks: int = 1000
    max_snapshots: int = 10
    on_event: List[str] = field(default_factory=lambda: ["battle", "level_up", "badge"])
    emergency_count: int = 3
    validate_on_save: bool = False
    compress_old: bool = False

    def _validate_config(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        valid_events = {"battle", "level_up", "badge", "catch", "location_change", "event"}
        for event in self.on_event:
            if event not in valid_events:
                errors.append(f"invalid save-on-event: {event}")
        if self.interval_ticks < 100:
            errors.append("save-interval-ticks must be >= 100")
        if self.max_snapshots < 1:
            errors.append("save-max-snapshots must be >= 1")
        if self.emergency_count < 1:
            errors.append("emergency-snapshot-count must be >= 1")
        return errors


@dataclass
class ExperimentConfig:
    """Experiment orchestration configuration."""
    name: str = "default"
    parallel_workers: int = 1
    sequential_retry: int = 3
    memory_limit_gb: float = 8.0
    api_rate_limit: int = 100
    aggregate_stats: bool = False
    fail_mode: str = "continue"
    checkpoint_frequency: int = 10000
    resume_from: Optional[str] = None
    config_file: Optional[str] = None
    export_results: bool = False
    results_format: str = "json"

    def _validate_config(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if self.parallel_workers < 1:
            errors.append("parallel-workers must be >= 1")
        if self.sequential_retry < 0:
            errors.append("sequential-retry must be >= 0")
        if self.memory_limit_gb <= 0:
            errors.append("parallel-memory-limit must be positive")
        if self.api_rate_limit < 1:
            errors.append("parallel-api-rate-limit must be >= 1")
        if self.checkpoint_frequency < 0:
            errors.append("checkpoint-frequency must be >= 0")
        return errors


@dataclass
class SystemConfig:
    """System-level configuration."""
    verbose: bool = False
    quiet: bool = False
    log_file: Optional[str] = None
    config_file: Optional[str] = None
    random_seed: Optional[int] = None
    help_flag: bool = False
    version: bool = False


@dataclass
class FullConfig:
    """Complete configuration combining all flag categories."""
    rom_path: str = ""
    save_dir: str = "./game_saves"

    tick_rate: TickRateConfig = field(default_factory=TickRateConfig)
    screenshot: ScreenshotConfig = field(default_factory=ScreenshotConfig)
    command_buffer: CommandBufferConfig = field(default_factory=CommandBufferConfig)
    limits: RunLimitsConfig = field(default_factory=RunLimitsConfig)
    snapshot: SnapshotConfig = field(default_factory=SnapshotConfig)
    save_state: SaveStateConfig = field(default_factory=SaveStateConfig)
    experiment: ExperimentConfig = field(default_factory=ExperimentConfig)
    system: SystemConfig = field(default_factory=SystemConfig)

    def validate(self) -> List[str]:
        """Validate entire configuration."""
        errors = []
        if not self.rom_path:
            errors.append("rom path is required")
        else:
            rom_path = Path(self.rom_path)
            if not rom_path.exists():
                errors.append(f"ROM file not found: {rom_path}")
        errors.extend(self.tick_rate._validate_config())
        errors.extend(self.screenshot._validate_config())
        errors.extend(self.command_buffer._validate_config())
        errors.extend(self.limits._validate_config())
        errors.extend(self.snapshot._validate_config())
        errors.extend(self.save_state._validate_config())
        errors.extend(self.experiment._validate_config())
        return errors

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "rom_path": self.rom_path,
            "save_dir": self.save_dir,
            "tick_rate": {
                "base": self.tick_rate.base,
                "battle": self.tick_rate.battle,
                "timeout": self.tick_rate.timeout,
                "adaptive": self.tick_rate.adaptive,
                "budget_mode": self.tick_rate.budget_mode,
                "budget_limit": self.tick_rate.budget_limit
            },
            "screenshot": {
                "interval": self.screenshot.interval,
                "battle_turn": self.screenshot.battle_turn,
                "on_error": self.screenshot.on_error,
                "on_change": self.screenshot.on_change,
                "quality": self.screenshot.quality,
                "max_storage_gb": self.screenshot.max_storage_gb,
                "async_capture": self.screenshot.async_capture,
                "compress": self.screenshot.compress
            },
            "command_buffer": {
                "buffer_size": self.command_buffer.buffer_size,
                "timeout": self.command_buffer.timeout,
                "validation_enabled": self.command_buffer.validation_enabled,
                "rollback_history": self.command_buffer.rollback_history,
                "interrupt_battle": self.command_buffer.interrupt_battle,
                "stale_threshold": self.command_buffer.stale_threshold
            },
            "limits": {
                "max_time_seconds": self.limits.max_time_seconds,
                "max_ticks": self.limits.max_ticks,
                "max_cost": self.limits.max_cost,
                "max_pokemon_caught": self.limits.max_pokemon_caught,
                "max_badges": self.limits.max_badges,
                "max_level": self.limits.max_level,
                "on_limit": self.limits.on_limit,
                "grace_period": self.limits.grace_period
            },
            "snapshot": {
                "memory_count": self.snapshot.memory_count,
                "disk_interval": self.snapshot.disk_interval,
                "on_event": self.snapshot.on_event,
                "max_disk_gb": self.snapshot.max_disk_gb,
                "compress": self.snapshot.compress,
                "validation_enabled": self.snapshot.validation_enabled,
                "rollback_on_error": self.snapshot.rollback_on_error,
                "rollback_grace": self.snapshot.rollback_grace,
                "allow_share": self.snapshot.allow_share,
                "name": self.snapshot.name
            },
            "save_state": {
                "interval_ticks": self.save_state.interval_ticks,
                "max_snapshots": self.save_state.max_snapshots,
                "on_event": self.save_state.on_event,
                "emergency_count": self.save_state.emergency_count,
                "validate_on_save": self.save_state.validate_on_save,
                "compress_old": self.save_state.compress_old
            },
            "experiment": {
                "name": self.experiment.name,
                "parallel_workers": self.experiment.parallel_workers,
                "sequential_retry": self.experiment.sequential_retry,
                "memory_limit_gb": self.experiment.memory_limit_gb,
                "api_rate_limit": self.experiment.api_rate_limit,
                "aggregate_stats": self.experiment.aggregate_stats,
                "fail_mode": self.experiment.fail_mode,
                "checkpoint_frequency": self.experiment.checkpoint_frequency,
                "resume_from": self.experiment.resume_from,
                "config_file": self.experiment.config_file,
                "export_results": self.experiment.export_results,
                "results_format": self.experiment.results_format
            },
            "system": {
                "verbose": self.system.verbose,
                "quiet": self.system.quiet,
                "log_file": self.system.log_file,
                "config_file": self.system.config_file,
                "random_seed": self.system.random_seed
            }
        }


class CLIFlagParser:
    """
    Complete CLI flag parser for PTP-01X.

    Implements all flags from ptp_01x_cli_control_infrastructure.md
    """

    def __init__(self):
        self.parser = argparse.ArgumentParser(
            description="PTP-01X Autonomous Pokemon AI System",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Basic run
  python src/game_loop.py --rom pokemon_red.gb --save-dir ./my_run

  # Fast exploration with adaptive tick rate
  python src/game_loop.py --rom pokemon_blue.gb --tick-rate-base 15 --tick-rate-adaptive

  # Debug session with frequent screenshots
  python src/game_loop.py --rom pokemon_red.gb --screenshot-interval 10 --screenshot-on-change

  # Budget-constrained run ($5 max)
  python src/game_loop.py --rom pokemon_blue.gb --max-cost 5.00 --on-limit save-and-exit

  # Long-running experiment with snapshots
  python src/game_loop.py --rom pokemon_red.gb --snapshot-disk 5000 --snapshot-on-event catch,badge

  # Multi-run experiment with parallel workers
  python src/game_loop.py --experiment-name benchmark --parallel-workers 4 --max-ticks 10000

For more information, see: specs/ptp_01x_cli_control_infrastructure.md
            """
        )
        self._setup_flag_groups()

    def _add_tick_rate_flags(self):
        """Add tick rate control flags."""
        group = self.parser.add_argument_group(
            "Tick Rate Control",
            "Control game loop execution speed and adaptive behavior"
        )

        group.add_argument(
            "--tick-rate-base",
            type=int,
            default=10,
            help="Base tick rate for overworld exploration (ticks/second, default: 10)"
        )

        group.add_argument(
            "--tick-rate-battle",
            type=int,
            default=2,
            help="Tick rate during battle sequences (ticks/second, default: 2)"
        )

        group.add_argument(
            "--tick-rate-timeout",
            type=int,
            default=30,
            help="Maximum seconds without state change before timeout (default: 30)"
        )

        group.add_argument(
            "--tick-rate-adaptive",
            action="store_true",
            default=False,
            help="Auto-adjust rate based on decision latency"
        )

        group.add_argument(
            "--tick-rate-budget",
            type=str,
            choices=["hourly", "daily", "run"],
            default=None,
            help="Cost budget mode: hourly, daily, or run"
        )

        group.add_argument(
            "--tick-rate-budget-limit",
            type=float,
            default=None,
            help="Maximum budget in dollars per period (required with --tick-rate-budget)"
        )

    def _add_screenshot_flags(self):
        """Add screenshot control flags."""
        group = self.parser.add_argument_group(
            "Screenshot Control",
            "Configure screenshot capture, quality, and storage"
        )

        group.add_argument(
            "--screenshot-interval",
            type=int,
            default=100,
            help="Base screenshot interval in ticks (default: 100)"
        )

        group.add_argument(
            "--screenshot-battle-turn",
            type=int,
            default=1,
            help="Screenshots captured per battle turn (default: 1)"
        )

        group.add_argument(
            "--screenshot-on-error",
            type=int,
            default=1,
            help="Screenshots captured per error tick (default: 1)"
        )

        group.add_argument(
            "--screenshot-on-change",
            action="store_true",
            default=False,
            help="Capture screenshot on any state transition"
        )

        group.add_argument(
            "--screenshot-quality",
            type=int,
            default=85,
            choices=range(0, 101),
            metavar="[0-100]",
            help="JPEG quality 0-100 (default: 85)"
        )

        group.add_argument(
            "--screenshot-max-storage",
            type=float,
            default=50.0,
            help="Maximum storage in GB for screenshots (default: 50.0)"
        )

        group.add_argument(
            "--screenshot-async",
            action="store_true",
            default=False,
            help="Enable non-blocking (async) screenshot capture"
        )

        group.add_argument(
            "--screenshot-compress",
            action="store_true",
            default=False,
            help="Compress old screenshots to save storage"
        )

    def _add_command_buffer_flags(self):
        """Add command buffer control flags."""
        group = self.parser.add_argument_group(
            "Command Buffer Control",
            "Configure command queuing, execution, and rollback"
        )

        group.add_argument(
            "--command-buffer-size",
            type=int,
            default=10,
            help="Maximum number of queued commands (default: 10)"
        )

        group.add_argument(
            "--command-timeout",
            type=int,
            default=5,
            help="Maximum seconds a command can wait in buffer (default: 5)"
        )

        group.add_argument(
            "--command-validate",
            action="store_true",
            default=False,
            help="Validate commands against current game state before execution"
        )

        group.add_argument(
            "--command-rollback-history",
            type=int,
            default=100,
            help="Number of commands stored for potential rollback (default: 100)"
        )

        group.add_argument(
            "--command-interrupt-battle",
            action="store_true",
            default=True,
            help="Clear command buffer when random battle starts (default: True)"
        )

        group.add_argument(
            "--command-stale-threshold",
            type=int,
            default=2,
            help="Seconds before command is considered stale (default: 2)"
        )

    def _add_limit_flags(self):
        """Add run limit flags."""
        group = self.parser.add_argument_group(
            "Run Limits",
            "Configure stopping conditions and limit behavior"
        )

        group.add_argument(
            "--max-time",
            type=int,
            default=None,
            help="Maximum real time in seconds (default: unlimited)"
        )

        group.add_argument(
            "--max-ticks",
            type=int,
            default=None,
            help="Maximum game ticks to execute (default: unlimited)"
        )

        group.add_argument(
            "--max-cost",
            type=float,
            default=None,
            help="Maximum cost in USD (default: unlimited)"
        )

        group.add_argument(
            "--max-pokemon-caught",
            type=int,
            default=None,
            help="Stop after catching N Pokemon (default: unlimited)"
        )

        group.add_argument(
            "--max-badges",
            type=int,
            default=None,
            help="Stop after earning N badges (0-16, default: unlimited)"
        )

        group.add_argument(
            "--max-level",
            type=int,
            default=None,
            help="Stop when Pokemon reaches level N (1-100, default: unlimited)"
        )

        group.add_argument(
            "--on-limit",
            type=str,
            choices=["save-and-exit", "save-only", "abort"],
            default="save-and-exit",
            help="Action when limit is reached (default: save-and-exit)"
        )

        group.add_argument(
            "--limit-grace-period",
            type=int,
            default=30,
            help="Seconds to finish current decision before stopping (default: 30)"
        )

    def _add_snapshot_flags(self):
        """Add snapshot management flags."""
        group = self.parser.add_argument_group(
            "Snapshot Management",
            "Configure save states, rollback, and recovery"
        )

        group.add_argument(
            "--snapshot-memory",
            type=int,
            default=10,
            help="Number of RAM snapshots for instant restore (default: 10)"
        )

        group.add_argument(
            "--snapshot-disk",
            type=int,
            default=1000,
            help="Interval in ticks for disk snapshots (default: 1000)"
        )

        group.add_argument(
            "--snapshot-on-event",
            type=str,
            default="",
            help="Event triggers for snapshots: catch,battle,badge,death (comma-separated)"
        )

        group.add_argument(
            "--snapshot-max-disk",
            type=float,
            default=20.0,
            help="Maximum storage in GB for snapshots (default: 20.0)"
        )

        group.add_argument(
            "--snapshot-compress",
            action="store_true",
            default=False,
            help="Compress disk snapshots to save storage"
        )

        group.add_argument(
            "--snapshot-validate",
            action="store_true",
            default=False,
            help="Validate snapshots can be restored after saving"
        )

        group.add_argument(
            "--rollback-on-error",
            action="store_true",
            default=False,
            help="Automatically rollback to last good snapshot on error"
        )

        group.add_argument(
            "--rollback-grace",
            type=int,
            default=3,
            help="Maximum rollback depth (default: 3)"
        )

        group.add_argument(
            "--snapshot-share",
            action="store_true",
            default=False,
            help="Allow sharing snapshots via network"
        )

        group.add_argument(
            "--snapshot-name",
            type=str,
            default=None,
            help="Name for creating a named snapshot"
        )

    def _add_save_state_flags(self):
        """Add save state control flags."""
        group = self.parser.add_argument_group(
            "Save State Control",
            "Configure save state intervals, rotation, and event triggers"
        )

        group.add_argument(
            "--save-interval-ticks",
            type=int,
            default=1000,
            help="Snapshot interval in ticks (default: 1000)"
        )

        group.add_argument(
            "--save-max-snapshots",
            type=int,
            default=10,
            help="Maximum number of snapshots to keep (default: 10)"
        )

        group.add_argument(
            "--save-on-event",
            type=str,
            default="",
            help="Event triggers for snapshots: battle,level_up,badge,catch,location_change (comma-separated)"
        )

        group.add_argument(
            "--emergency-snapshot-count",
            type=int,
            default=3,
            help="Number of emergency snapshots to preserve on crash (default: 3)"
        )

        group.add_argument(
            "--save-state-validate",
            action="store_true",
            default=False,
            help="Validate save states can be restored after saving"
        )

        group.add_argument(
            "--save-state-compress",
            action="store_true",
            default=False,
            help="Compress old save states to save storage"
        )

    def _add_experiment_flags(self):
        """Add experiment orchestration flags."""
        group = self.parser.add_argument_group(
            "Experiment Orchestration",
            "Configure multi-run experiments and parallel execution"
        )

        group.add_argument(
            "--experiment-name",
            type=str,
            default="default",
            help="Experiment identifier for grouping results (default: default)"
        )

        group.add_argument(
            "--parallel-workers",
            type=int,
            default=1,
            help="Maximum concurrent game instances (default: 1)"
        )

        group.add_argument(
            "--sequential-retry",
            type=int,
            default=3,
            help="Number of retries on failure (default: 3)"
        )

        group.add_argument(
            "--parallel-memory-limit",
            type=float,
            default=8.0,
            help="Per-worker memory limit in GB (default: 8.0)"
        )

        group.add_argument(
            "--parallel-api-rate-limit",
            type=int,
            default=100,
            help="Maximum API calls per minute across all workers (default: 100)"
        )

        group.add_argument(
            "--aggregate-stats",
            action="store_true",
            default=False,
            help="Calculate mean and standard deviation for parallel runs"
        )

        group.add_argument(
            "--fail-mode",
            type=str,
            choices=["continue", "fast-fail", "retry"],
            default="continue",
            help="Behavior on failure: continue, fast-fail, or retry (default: continue)"
        )

        group.add_argument(
            "--checkpoint-frequency",
            type=int,
            default=10000,
            help="Save checkpoint after N sequential runs (default: 10000)"
        )

        group.add_argument(
            "--resume-from",
            type=str,
            default=None,
            help="Resume experiment from checkpoint directory"
        )

        group.add_argument(
            "--experiment-config",
            type=str,
            default=None,
            help="Load experiment settings from YAML config file"
        )

        group.add_argument(
            "--export-results",
            action="store_true",
            default=False,
            help="Export aggregated results after experiment completes"
        )

        group.add_argument(
            "--results-format",
            type=str,
            choices=["json", "csv", "parquet"],
            default="json",
            help="Output format for exported results (default: json)"
        )

    def _add_system_flags(self):
        """Add system-level flags."""
        group = self.parser.add_argument_group(
            "System Flags",
            "General system configuration and utilities"
        )

        group.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            default=False,
            help="Enable verbose output"
        )

        group.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            default=False,
            help="Suppress all output except errors"
        )

        group.add_argument(
            "--log-file",
            type=str,
            default=None,
            help="Write logs to specified file"
        )

        group.add_argument(
            "--config-file",
            type=str,
            default=None,
            help="Load additional configuration from YAML file"
        )

        group.add_argument(
            "--random-seed",
            type=int,
            default=None,
            help="Random seed for reproducibility"
        )

    def _add_required_flags(self):
        """Add required positional/optional arguments."""
        self.parser.add_argument(
            "--rom",
            type=str,
            required=True,
            help="Path to Pokemon ROM file (.gb or .gbc)"
        )

        self.parser.add_argument(
            "--save-dir",
            type=str,
            default="./game_saves",
            help="Directory for saves, database, and screenshots (default: ./game_saves)"
        )

    def _setup_flag_groups(self):
        """Setup all flag groups."""
        self._add_required_flags()
        self._add_tick_rate_flags()
        self._add_screenshot_flags()
        self._add_command_buffer_flags()
        self._add_limit_flags()
        self._add_snapshot_flags()
        self._add_save_state_flags()
        self._add_experiment_flags()
        self._add_system_flags()

    def parse_args(self, args: Optional[List[str]] = None) -> FullConfig:
        """
        Parse command line arguments and return FullConfig.

        Args:
            args: Optional list of arguments (uses sys.argv if None)

        Returns:
            FullConfig with all parsed values
        """
        parsed = self.parser.parse_args(args)

        snapshot_events = []
        if parsed.snapshot_on_event:
            snapshot_events = [e.strip() for e in parsed.snapshot_on_event.split(",")]

        save_state_events = []
        if parsed.save_on_event:
            save_state_events = [e.strip() for e in parsed.save_on_event.split(",")]

        return FullConfig(
            rom_path=parsed.rom,
            save_dir=parsed.save_dir,
            tick_rate=TickRateConfig(
                base=parsed.tick_rate_base,
                battle=parsed.tick_rate_battle,
                timeout=parsed.tick_rate_timeout,
                adaptive=parsed.tick_rate_adaptive,
                budget_mode=parsed.tick_rate_budget,
                budget_limit=parsed.tick_rate_budget_limit
            ),
            screenshot=ScreenshotConfig(
                interval=parsed.screenshot_interval,
                battle_turn=parsed.screenshot_battle_turn,
                on_error=parsed.screenshot_on_error,
                on_change=parsed.screenshot_on_change,
                quality=parsed.screenshot_quality,
                max_storage_gb=parsed.screenshot_max_storage,
                async_capture=parsed.screenshot_async,
                compress=parsed.screenshot_compress
            ),
            command_buffer=CommandBufferConfig(
                buffer_size=parsed.command_buffer_size,
                timeout=parsed.command_timeout,
                validation_enabled=parsed.command_validate,
                rollback_history=parsed.command_rollback_history,
                interrupt_battle=parsed.command_interrupt_battle,
                stale_threshold=parsed.command_stale_threshold
            ),
            limits=RunLimitsConfig(
                max_time_seconds=parsed.max_time,
                max_ticks=parsed.max_ticks,
                max_cost=parsed.max_cost,
                max_pokemon_caught=parsed.max_pokemon_caught,
                max_badges=parsed.max_badges,
                max_level=parsed.max_level,
                on_limit=parsed.on_limit,
                grace_period=parsed.limit_grace_period
            ),
            snapshot=SnapshotConfig(
                memory_count=parsed.snapshot_memory,
                disk_interval=parsed.snapshot_disk,
                on_event=snapshot_events,
                max_disk_gb=parsed.snapshot_max_disk,
                compress=parsed.snapshot_compress,
                validation_enabled=parsed.snapshot_validate,
                rollback_on_error=parsed.rollback_on_error,
                rollback_grace=parsed.rollback_grace,
                allow_share=parsed.snapshot_share,
                name=parsed.snapshot_name
            ),
            save_state=SaveStateConfig(
                interval_ticks=parsed.save_interval_ticks,
                max_snapshots=parsed.save_max_snapshots,
                on_event=save_state_events,
                emergency_count=parsed.emergency_snapshot_count,
                validate_on_save=parsed.save_state_validate,
                compress_old=parsed.save_state_compress
            ),
            experiment=ExperimentConfig(
                name=parsed.experiment_name,
                parallel_workers=parsed.parallel_workers,
                sequential_retry=parsed.sequential_retry,
                memory_limit_gb=parsed.parallel_memory_limit,
                api_rate_limit=parsed.parallel_api_rate_limit,
                aggregate_stats=parsed.aggregate_stats,
                fail_mode=parsed.fail_mode,
                checkpoint_frequency=parsed.checkpoint_frequency,
                resume_from=parsed.resume_from,
                config_file=parsed.experiment_config,
                export_results=parsed.export_results,
                results_format=parsed.results_format
            ),
            system=SystemConfig(
                verbose=parsed.verbose,
                quiet=parsed.quiet,
                log_file=parsed.log_file,
                config_file=parsed.config_file,
                random_seed=parsed.random_seed
            )
        )

    def validate_config(self, config: FullConfig) -> List[str]:
        """
        Validate a FullConfig and return list of errors.

        Args:
            config: Configuration to validate

        Returns:
            List of error messages (empty if valid)
        """
        errors = config.validate()

        if config.system.verbose and config.system.quiet:
            errors.append("Cannot use both --verbose and --quiet")

        if config.experiment.parallel_workers > 1 and config.experiment.resume_from:
            if not Path(config.experiment.resume_from).exists():
                errors.append(f"Resume directory not found: {config.experiment.resume_from}")

        return errors

    def parse_and_validate(self, args: Optional[List[str]] = None) -> tuple[FullConfig, List[str]]:
        """
        Parse arguments and validate configuration.

        Returns:
            Tuple of (FullConfig, error_list)
        """
        config = self.parse_args(args)
        errors = self.validate_config(config)
        return config, errors


def create_config_from_args(args: Optional[List[str]] = None) -> FullConfig:
    """
    Convenience function to create FullConfig from CLI arguments.

    Args:
        args: Optional list of arguments (uses sys.argv if None)

    Returns:
        FullConfig with all parsed values
    """
    parser = CLIFlagParser()
    config, errors = parser.parse_and_validate(args)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        parser.parser.print_help()
        exit(1)

    return config


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        parser = CLIFlagParser()
        parser.parser.print_help()
        sys.exit(0)

    config = create_config_from_args()

    print("Parsed Configuration:")
    print("=" * 60)

    config_dict = config.to_dict()
    for section, values in config_dict.items():
        print(f"\n{section}:")
        if isinstance(values, dict):
            for key, value in values.items():
                print(f"  {key}: {value}")
        else:
            print(f"  {values}")

    print("\n" + "=" * 60)
    print("Configuration validated successfully!")