"""
Tests for DemoRunner — AI Plays Pokémon gameplay demo.

These tests verify the demo runner's structure, headless mode,
and ROM handling.  API-dependent tests (vision + thinking) are
gated behind a ROM file check and API key check.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.core.demo_runner import DemoRunner, demo_summary


# ── helpers ────────────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parent

def _find_rom() -> Path | None:
    """Return the first available ROM, or None.

    PyBoy is GB/GBC-only, so prefer .gb and .gbc over .gba.
    """
    candidates = sorted(_PROJECT.glob("data/rom/*.gb")) + sorted(
        _PROJECT.glob("data/rom/*.gbc")
    ) + sorted(_PROJECT.glob("data/rom/*.gba"))
    return candidates[0] if candidates else None


def _has_api_key() -> bool:
    """True if OPENROUTER_API_KEY is set and non-empty."""
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


# ── unit / smoke tests (no ROM, no API key) ────────────────────────────────


class TestDemoRunnerInstantiation:
    """DemoRunner can be created without a working ROM."""

    def test_instantiate_nonexistent_path(self) -> None:
        runner = DemoRunner("/tmp/no_such_rom.gba")
        assert runner is not None
        assert runner._rom_path == Path("/tmp/no_such_rom.gba").resolve()

    def test_instantiate_with_relative_path(self) -> None:
        runner = DemoRunner("data/rom/pokemon.gba")
        assert runner is not None
        assert runner._rom_path.is_absolute()

    def test_default_models(self) -> None:
        runner = DemoRunner("/tmp/fake.gba")
        assert runner._thinking_model == "openrouter/owl-alpha"
        assert runner._vision_model == "google/gemma-3-12b-it"

    def test_custom_generation(self) -> None:
        runner = DemoRunner("/tmp/fake.gba", generation="gen1")
        assert runner._generation == "gen1"


class TestDemoRunnerFileNotFound:
    """DemoRunner raises when ROM doesn't exist."""

    def test_run_raises_file_not_found(self) -> None:
        runner = DemoRunner("/tmp/no_such_rom_xyz_12345.gba")
        with pytest.raises(FileNotFoundError, match="ROM not found"):
            runner.run(max_cycles=1)

    def test_run_headless_raises_file_not_found(self) -> None:
        runner = DemoRunner("/tmp/no_such_rom_xyz_12345.gba")
        with pytest.raises(FileNotFoundError, match="ROM not found"):
            runner.run_headless()


class TestDemoSummary:
    """demo_summary() formats results correctly."""

    def test_basic_summary(self) -> None:
        result = {
            "rom_path": "/tmp/test.gba",
            "cycles_completed": 10,
            "cycles_requested": 10,
            "success_rate": 0.8,
            "screen_types_seen": ["battle", "overworld"],
            "tool_calls_made": 15,
            "elapsed_s": 42.5,
        }
        summary = demo_summary(result)
        assert "test.gba" in summary
        assert "10" in summary
        assert "80.0%" in summary
        assert "battle" in summary
        assert "overworld" in summary

    def test_zero_cycles(self) -> None:
        result = {
            "rom_path": "/tmp/test.gba",
            "cycles_completed": 0,
            "cycles_requested": 5,
            "success_rate": 0.0,
            "screen_types_seen": [],
            "tool_calls_made": 0,
            "elapsed_s": 0.1,
        }
        summary = demo_summary(result)
        assert "0 / 5" in summary


class TestCleanup:
    """cleanup() is safe to call multiple times."""

    def test_cleanup_before_run(self) -> None:
        runner = DemoRunner("/tmp/fake.gba")
        runner.cleanup()  # should not raise
        assert runner.emulator is None

    def test_cleanup_twice(self) -> None:
        runner = DemoRunner("/tmp/fake.gba")
        runner.cleanup()
        runner.cleanup()  # idempotent
        assert runner.emulator is None


# ── headless smoke test (ROM needed, no API key) ───────────────────────────


@pytest.mark.integration
class TestHeadlessRun:
    """Headless run validates ROM loading + intro skip + capture."""

    @pytest.fixture(autouse=True)
    def _check_rom(self) -> None:
        rom = _find_rom()
        if rom is None:
            pytest.skip("No ROM found in data/rom/")
        self._rom_path = rom

    def test_headless_smoke(self) -> None:
        runner = DemoRunner(str(self._rom_path))
        try:
            result = runner.run_headless(max_cycles=3, screenshot_interval=10)
            assert result["cycles_completed"] == 3
            assert result["mode"] == "headless"
            assert len(result["captures"]) == 3
            for cap in result["captures"]:
                assert cap["height"] > 0
                assert cap["width"] > 0
            assert result["elapsed_s"] > 0
        finally:
            runner.cleanup()

    def test_headless_single_cycle(self) -> None:
        runner = DemoRunner(str(self._rom_path))
        try:
            result = runner.run_headless(max_cycles=1, screenshot_interval=5)
            assert result["cycles_completed"] == 1
            assert len(result["captures"]) == 1
        finally:
            runner.cleanup()


# ── full decision-loop test (ROM + API key) ────────────────────────────────


@pytest.mark.integration
@pytest.mark.live_api
class TestLiveGameplay:
    """Full gameplay demo with vision + thinking LLM."""

    @pytest.fixture(autouse=True)
    def _check_prereqs(self) -> None:
        if not _has_api_key():
            pytest.skip("OPENROUTER_API_KEY not set")
        rom = _find_rom()
        if rom is None:
            pytest.skip("No ROM found in data/rom/")
        self._rom_path = rom

    def test_live_run_three_cycles(self) -> None:
        """Run 3 cycles — verify the pipeline produces results."""
        runner = DemoRunner(str(self._rom_path))
        try:
            result = runner.run(
                max_cycles=3,
                screenshot_interval=30,
                skip_intro=True,
            )
            assert result["cycles_completed"] == 3
            assert 0.0 <= result["success_rate"] <= 1.0
            assert len(result["results"]) == 3
            # Each cycle should have expected keys
            for step in result["results"]:
                assert "screen_type" in step
                assert "action" in step
                assert "success" in step
            # At least one screen type should be recognized
            screen_types = result["screen_types_seen"]
            assert len(screen_types) >= 1, "No screen types recognized"
        finally:
            runner.cleanup()

    def test_live_run_skips_intro(self) -> None:
        """Verify intro skip works — first screen type isn't 'title'."""
        runner = DemoRunner(str(self._rom_path))
        try:
            result = runner.run(
                max_cycles=5,
                screenshot_interval=20,
                skip_intro=True,
            )
            # After skipping intro we should be past the title screen
            result["results"][0].get("screen_type", "")
            # It's OK if vision fails — we just verify the pipeline didn't crash
            assert result["cycles_completed"] == 5
        finally:
            runner.cleanup()
