"""Unit tests for demo_runner.py — DemoRunner init/cleanup + demo_summary.

Tests the pure-function and mockable parts of DemoRunner. The run() and
run_headless() methods require an emulator + ROM — tested separately in
test_gameplay_demo.py (ROM-gated) and test_vision_headless.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.demo_runner import DemoRunner, demo_summary


class TestDemoRunnerInit:
    """DemoRunner.__init__ — stores config, validates nothing eagerly."""

    def test_init_default(self) -> None:
        runner = DemoRunner("data/rom/test.gba")
        assert str(runner._rom_path).endswith("test.gba")
        assert runner._generation == "gen3"
        assert runner._thinking_model == "openrouter/owl-alpha"
        assert runner._vision_model == "google/gemma-3-12b-it"
        assert runner.emulator is None
        assert runner.loop is None
        assert runner.results == []

    def test_init_path_resolved(self) -> None:
        runner = DemoRunner("data/rom/pokemon_red.gb")
        assert Path(runner._rom_path).is_absolute()

    def test_init_custom_models(self) -> None:
        runner = DemoRunner(
            "data/rom/test.gba",
            generation="gen1",
            thinking_model="deepseek/deepseek-v4-flash",
            vision_model="openai/gpt-4o",
        )
        assert runner._generation == "gen1"
        assert runner._thinking_model == "deepseek/deepseek-v4-flash"
        assert runner._vision_model == "openai/gpt-4o"

    def test_init_path_string(self) -> None:
        runner = DemoRunner("data/rom/test.gba")
        assert isinstance(runner._rom_path, Path)


class TestDemoRunnerCleanup:
    """DemoRunner.cleanup() — stops emulator and resets state."""

    def test_cleanup_with_none(self) -> None:
        runner = DemoRunner("data/rom/test.gba")
        runner.cleanup()  # should not raise
        assert runner.emulator is None
        assert runner.loop is None
        assert runner.results == []

    def test_cleanup_twice(self) -> None:
        runner = DemoRunner("data/rom/test.gba")
        runner.cleanup()
        runner.cleanup()  # idempotent
        assert runner.emulator is None


class TestDemoSummary:
    """demo_summary() — pure function, no dependencies."""

    def test_summary_empty(self) -> None:
        result: dict = {}
        s = demo_summary(result)
        assert "ROM: ?" in s
        assert "0 / 0" in s

    def test_summary_minimal(self) -> None:
        result = {
            "rom_path": "/path/to/rom.gba",
            "cycles_requested": 10,
            "cycles_completed": 8,
            "success_rate": 0.75,
            "screen_types_seen": ["overworld", "battle"],
            "tool_calls_made": 42,
            "elapsed_s": 123.456,
        }
        s = demo_summary(result)
        assert "rom.gba" in s
        assert "8 / 10" in s
        assert "75.0%" in s
        assert "overworld" in s
        assert "battle" in s
        assert "42" in s
        assert "123.5s" in s

    def test_summary_zero_rates(self) -> None:
        result = {
            "rom_path": "test",
            "cycles_requested": 20,
            "cycles_completed": 0,
            "success_rate": 0.0,
            "screen_types_seen": [],
            "tool_calls_made": 0,
            "elapsed_s": 0.0,
        }
        s = demo_summary(result)
        assert "0 / 20" in s
        assert "0.0%" in s
        assert "0.0s" in s
        assert "[]" in s

    def test_summary_partial_types(self) -> None:
        """Missing optional keys should be handled gracefully."""
        result = {
            "rom_path": "test.gba",
            "cycles_requested": 5,
            "cycles_completed": 3,
            "success_rate": 0.6,
            "elapsed_s": 30.0,
        }
        s = demo_summary(result)
        assert "test.gba" in s
        assert "3 / 5" in s

    def test_summary_missing_keys(self) -> None:
        """Keys that default to 0/? should not crash."""
        result: dict = {}
        s = demo_summary(result)
        assert s  # non-empty string


class TestDemoRunnerRunError:
    """DemoRunner.run() with non-existent ROM raises FileNotFoundError."""

    def test_run_missing_rom(self) -> None:
        runner = DemoRunner("/tmp/nonexistent_rom_abcdef.gba")
        with pytest.raises(FileNotFoundError):
            runner.run(max_cycles=1, skip_intro=False)

    def test_run_headless_missing_rom(self) -> None:
        runner = DemoRunner("/tmp/nonexistent_rom_abcdef.gba")
        with pytest.raises(FileNotFoundError):
            runner.run_headless(max_cycles=1)
