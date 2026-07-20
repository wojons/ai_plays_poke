"""Extended unit tests for demo_runner.py — mock-based coverage of run() and run_headless().

Adds mock-based tests for run()/run_headless() happy paths and cleanup() with
non-None emulator. The ROM-dependent paths are tested via integration tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import numpy as np
import pytest

from src.core.demo_runner import DemoRunner, demo_summary


# ── Helpers ────────────────────────────────────────────────────────────────

def _mock_emulator() -> MagicMock:
    """Create a mock Emulator that passes skip_intro, capture, stop."""
    emu = MagicMock()
    emu.capture.return_value = np.zeros((160, 240, 3), dtype=np.uint8)
    emu.skip_intro.return_value = None
    emu.stop.return_value = None
    emu.wait.return_value = None
    return emu


def _mock_decision_loop(results: list | None = None) -> MagicMock:
    """Create a mock DecisionLoop with configurable results."""
    loop = MagicMock()
    if results is None:
        results = [
            {"success": True, "screen_type": "overworld", "tool_call": {"name": "press_button", "args": {"button": "A"}}},
            {"success": True, "screen_type": "overworld", "tool_call": {"name": "press_button", "args": {"button": "UP"}}},
            {"success": False, "screen_type": "battle", "tool_call": None},
        ]
    loop.run.return_value = results
    return loop


# ── run() with mocks ──────────────────────────────────────────────────────

class TestDemoRunnerRunMocked:
    """DemoRunner.run() happy path with mocked Emulator + DecisionLoop."""

    @patch("src.core.demo_runner.Emulator")
    @patch("src.core.demo_runner.DecisionLoop")
    def test_run_happy_path(self, mock_dl_cls, mock_emu_cls, tmp_path):
        """Full run() with mocked emulator and decision loop returns summary."""
        mock_emu = _mock_emulator()
        mock_loop = _mock_decision_loop()
        mock_emu_cls.return_value = mock_emu
        mock_dl_cls.return_value = mock_loop

        # Create a real file so is_file() passes
        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        result = runner.run(max_cycles=5, skip_intro=True)

        assert result["rom_path"] == str(rom)
        assert result["cycles_requested"] == 5
        assert result["cycles_completed"] == 3  # 3 results in mock
        assert isinstance(result["success_rate"], float)
        assert "overworld" in result["screen_types_seen"]
        assert "battle" in result["screen_types_seen"]
        assert result["tool_calls_made"] == 2  # only 2 have tool_call
        assert "elapsed_s" in result
        assert mock_emu.skip_intro.called
        assert mock_loop.run.called

    @patch("src.core.demo_runner.Emulator")
    @patch("src.core.demo_runner.DecisionLoop")
    def test_run_skip_intro_false(self, mock_dl_cls, mock_emu_cls, tmp_path):
        """run() with skip_intro=False should NOT call skip_intro."""
        mock_emu = _mock_emulator()
        mock_loop = _mock_decision_loop([])
        mock_emu_cls.return_value = mock_emu
        mock_dl_cls.return_value = mock_loop

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        result = runner.run(max_cycles=1, skip_intro=False)

        assert not mock_emu.skip_intro.called
        assert result["cycles_completed"] == 0

    @patch("src.core.demo_runner.Emulator")
    @patch("src.core.demo_runner.DecisionLoop")
    def test_run_passes_intro_params(self, mock_dl_cls, mock_emu_cls, tmp_path):
        """run() forwards intro parameters to emulator.skip_intro."""
        mock_emu = _mock_emulator()
        mock_loop = _mock_decision_loop()
        mock_emu_cls.return_value = mock_emu
        mock_dl_cls.return_value = mock_loop

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        runner.run(max_cycles=2, skip_intro=True,
                   intro_press_frames=42, intro_wait_frames=99,
                   intro_repetitions=7)

        mock_emu.skip_intro.assert_called_once_with(
            press_frames=42, wait_frames=99, repetitions=7,
        )

    @patch("src.core.demo_runner.Emulator")
    @patch("src.core.demo_runner.DecisionLoop")
    def test_run_passes_models_to_decision_loop(self, mock_dl_cls, mock_emu_cls, tmp_path):
        """DecisionLoop receives generation + model params from DemoRunner."""
        mock_emu = _mock_emulator()
        mock_loop = _mock_decision_loop()
        mock_emu_cls.return_value = mock_emu
        mock_dl_cls.return_value = mock_loop

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom), generation="gen1",
                            thinking_model="test/think", vision_model="test/see")
        runner.run(max_cycles=1)

        mock_dl_cls.assert_called_once_with(
            emulator=mock_emu, generation="gen1",
            thinking_model="test/think", vision_model="test/see",
        )

    @patch("src.core.demo_runner.Emulator")
    @patch("src.core.demo_runner.DecisionLoop")
    def test_run_screenshot_interval_forwarded(self, mock_dl_cls, mock_emu_cls, tmp_path):
        """run() forwards screenshot_interval to DecisionLoop.run."""
        mock_emu = _mock_emulator()
        mock_loop = _mock_decision_loop()
        mock_emu_cls.return_value = mock_emu
        mock_dl_cls.return_value = mock_loop

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        runner.run(max_cycles=3, screenshot_interval=15)

        mock_loop.run.assert_called_once_with(max_steps=3, screenshot_interval=15)

    @patch("src.core.demo_runner.Emulator")
    @patch("src.core.demo_runner.DecisionLoop")
    def test_run_zero_success_rate(self, mock_dl_cls, mock_emu_cls, tmp_path):
        """run() with all-failure results → success_rate 0.0."""
        mock_emu = _mock_emulator()
        mock_loop = _mock_decision_loop([
            {"success": False, "screen_type": "overworld", "tool_call": None},
            {"success": False, "screen_type": "overworld", "tool_call": None},
        ])
        mock_emu_cls.return_value = mock_emu
        mock_dl_cls.return_value = mock_loop

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        result = runner.run(max_cycles=2)
        assert result["success_rate"] == 0.0
        assert result["tool_calls_made"] == 0

    @patch("src.core.demo_runner.Emulator")
    @patch("src.core.demo_runner.DecisionLoop")
    def test_run_empty_results(self, mock_dl_cls, mock_emu_cls, tmp_path):
        """run() with empty results → success_rate 0.0 (protected by max(1))."""
        mock_emu = _mock_emulator()
        mock_loop = _mock_decision_loop([])
        mock_emu_cls.return_value = mock_emu
        mock_dl_cls.return_value = mock_loop

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        result = runner.run(max_cycles=1)
        assert result["success_rate"] == 0.0
        assert result["screen_types_seen"] == []

    @patch("src.core.demo_runner.Emulator")
    @patch("src.core.demo_runner.DecisionLoop")
    def test_run_null_screen_type(self, mock_dl_cls, mock_emu_cls, tmp_path):
        """run() with None screen_type → not added to set (falsy check)."""
        mock_emu = _mock_emulator()
        mock_loop = _mock_decision_loop([
            {"success": True, "screen_type": None, "tool_call": None},
            {"success": True, "screen_type": "", "tool_call": None},
        ])
        mock_emu_cls.return_value = mock_emu
        mock_dl_cls.return_value = mock_loop

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        result = runner.run(max_cycles=2)
        assert result["screen_types_seen"] == []

    @patch("src.core.demo_runner.Emulator")
    @patch("src.core.demo_runner.DecisionLoop")
    def test_run_duplicate_screen_types(self, mock_dl_cls, mock_emu_cls, tmp_path):
        """run() deduplicates screen types via set."""
        mock_emu = _mock_emulator()
        mock_loop = _mock_decision_loop([
            {"success": True, "screen_type": "overworld", "tool_call": None},
            {"success": True, "screen_type": "overworld", "tool_call": None},
            {"success": True, "screen_type": "overworld", "tool_call": None},
        ])
        mock_emu_cls.return_value = mock_emu
        mock_dl_cls.return_value = mock_loop

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        result = runner.run(max_cycles=3)
        assert result["screen_types_seen"] == ["overworld"]


# ── run_headless() with mocks ─────────────────────────────────────────────

class TestDemoRunnerRunHeadlessMocked:
    """DemoRunner.run_headless() happy path with mocked Emulator."""

    @patch("src.core.demo_runner.Emulator")
    def test_run_headless_happy_path(self, mock_emu_cls, tmp_path):
        """run_headless() captures screenshots and returns summary."""
        mock_emu = _mock_emulator()
        mock_emu_cls.return_value = mock_emu

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        result = runner.run_headless(max_cycles=3, screenshot_interval=10)

        assert result["mode"] == "headless"
        assert result["cycles_completed"] == 3
        assert "elapsed_s" in result
        assert len(result["captures"]) == 3
        assert result["captures"][0]["cycle"] == 1
        assert result["captures"][0]["height"] == 160
        assert result["captures"][0]["width"] == 240
        assert mock_emu.skip_intro.called
        assert mock_emu.wait.call_count == 3
        assert mock_emu.capture.call_count == 3

    @patch("src.core.demo_runner.Emulator")
    def test_run_headless_zero_cycles(self, mock_emu_cls, tmp_path):
        """run_headless() with 0 cycles → no captures."""
        mock_emu = _mock_emulator()
        mock_emu_cls.return_value = mock_emu

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        result = runner.run_headless(max_cycles=0)

        assert result["captures"] == []
        assert mock_emu.wait.call_count == 0

    @patch("src.core.demo_runner.Emulator")
    def test_run_headless_default_params(self, mock_emu_cls, tmp_path):
        """run_headless() defaults to max_cycles=5, screenshot_interval=30."""
        mock_emu = _mock_emulator()
        mock_emu_cls.return_value = mock_emu

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        result = runner.run_headless()

        assert result["cycles_completed"] == 5
        assert mock_emu.wait.call_count == 5

    @patch("src.core.demo_runner.Emulator")
    def test_run_headless_capture_shape(self, mock_emu_cls, tmp_path):
        """run_headless() captures include cycle, height, width."""
        mock_emu = _mock_emulator()
        mock_emu_cls.return_value = mock_emu

        rom = tmp_path / "test.gba"
        rom.write_bytes(b"\x00" * 4096)

        runner = DemoRunner(str(rom))
        result = runner.run_headless(max_cycles=2)

        for cap in result["captures"]:
            assert "cycle" in cap
            assert "height" in cap
            assert "width" in cap
            assert cap["height"] == 160
            assert cap["width"] == 240


# ── cleanup() with non-None emulator ──────────────────────────────────────

class TestDemoRunnerCleanupExtended:
    """DemoRunner.cleanup() with non-None emulator."""

    def test_cleanup_with_emulator(self):
        """cleanup() calls emulator.stop() and sets to None."""
        runner = DemoRunner("/tmp/fake.gba")
        runner.emulator = MagicMock()
        emu_ref = runner.emulator  # keep reference before cleanup nulls it
        runner.loop = MagicMock()
        runner.results = [{"test": 1}]

        runner.cleanup()

        emu_ref.stop.assert_called_once()
        assert runner.emulator is None
        assert runner.loop is None
        assert runner.results == []
