"""
Live end-to-end gameplay tests — AI Plays Pokémon.

These tests require:
  - A ROM file in data/rom/ (GB or GBA)
  - OPENROUTER_API_KEY set in the environment

Tests verify that the full vision→thinking→tool-execution pipeline works
with real API calls, producing valid tool calls, correct screenshot
dimensions, and complete demo summaries.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from src.core.demo_runner import DemoRunner, demo_summary
from src.core.emulator import Emulator
from src.core.tools import TOOL_SCHEMA

# ── helpers ────────────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parent


def _find_rom() -> Path | None:
    """Return the first available ROM, or None."""
    candidates = sorted(_PROJECT.glob("data/rom/*.gba")) + sorted(
        _PROJECT.glob("data/rom/*.gb")
    ) + sorted(_PROJECT.glob("data/rom/*.gbc"))
    return candidates[0] if candidates else None


def _has_api_key() -> bool:
    """True if OPENROUTER_API_KEY is set and non-empty."""
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


# ── prerequisite check fixture ─────────────────────────────────────────────

@pytest.fixture(scope="session")
def _require_live() -> Path:
    """Skip all live-demo tests if ROM or API key missing."""
    if not _has_api_key():
        pytest.skip("OPENROUTER_API_KEY not set")
    rom = _find_rom()
    if rom is None:
        pytest.skip("No ROM found in data/rom/")
    return rom


# ── AC-010: DemoRunner.run() completes ≥1 cycle ────────────────────────────

@pytest.mark.integration
@pytest.mark.live_api
def test_live_completes_one_cycle(_require_live: Path):
    """AC-010: DemoRunner.run() with real ROM + owl-alpha completes ≥1 cycle."""
    rom_path = _require_live
    runner = DemoRunner(str(rom_path))
    try:
        result = runner.run(max_cycles=1, screenshot_interval=30, skip_intro=True)
        assert result["cycles_completed"] >= 1, "Should complete at least 1 cycle"
        assert result["cycles_requested"] == 1
        assert len(result["results"]) == 1
        step = result["results"][0]
        assert "screen_type" in step
        assert "action" in step
        assert "success" in step
        print(f"  AC-010 PASS: 1 cycle, screen_type={step['screen_type']}, "
              f"success={step['success']}, action={step['action'][:80]}")
    finally:
        runner.cleanup()


# ── AC-011: Decision loop produces valid tool calls ─────────────────────────

@pytest.mark.integration
@pytest.mark.live_api
def test_tool_calls_are_valid(_require_live: Path):
    """AC-011: Decision loop produces valid tool calls (press_button, wait) from AI response."""
    rom_path = _require_live
    runner = DemoRunner(str(rom_path))
    try:
        result = runner.run(max_cycles=5, screenshot_interval=30, skip_intro=True)
        valid_tool_present = False
        for step in result["results"]:
            tc = step.get("tool_call")
            if tc is None:
                # Fallback tool calls may be None on error paths
                continue
            # Must have name + arguments keys
            assert "name" in tc, f"tool_call missing 'name': {tc}"
            assert "arguments" in tc, f"tool_call missing 'arguments': {tc}"

            # Tool name must be one of the defined tools
            valid_names = {t["function"]["name"] for t in TOOL_SCHEMA}
            assert tc["name"] in valid_names, (
                f"Unknown tool name: {tc['name']!r}. Valid: {sorted(valid_names)}"
            )
            valid_tool_present = True

            # Verify arguments are usable
            name = tc["name"]
            args = tc.get("arguments", {})
            if name == "press_button":
                assert "button" in args, f"press_button missing 'button': {args}"
            elif name == "wait":
                assert "frames" in args, f"wait missing 'frames': {args}"
            elif name == "combo":
                assert "buttons" in args, f"combo missing 'buttons': {args}"

        assert valid_tool_present, (
            f"No valid tool calls found in {len(result['results'])} cycles. "
            f"Results: {[r.get('tool_call') for r in result['results']]}"
        )
        print(f"  AC-011 PASS: {sum(1 for r in result['results'] if r.get('tool_call'))}/{len(result['results'])} "
              f"cycles produced valid tool calls")
    finally:
        runner.cleanup()


# ── AC-012: Screenshots are valid numpy arrays ──────────────────────────────

@pytest.mark.integration
@pytest.mark.live_api
def test_screenshots_valid_numpy_arrays(_require_live: Path):
    """AC-012: Screenshots captured at each interval are valid numpy arrays.

    GB:  (144, 160, 3)   — SGB border cropped
    GBA: (160, 240, 3)   — full GBA frame
    """
    rom_path = _require_live
    # Determine expected dimensions from the ROM platform
    emu = Emulator(str(rom_path))
    try:
        expected_shape = (144, 160, 3) if emu.is_gb else (160, 240, 3)
        is_gb = emu.is_gb
    finally:
        emu.stop()

    runner = DemoRunner(str(rom_path))
    try:
        runner.emulator = Emulator(str(rom_path))
        runner.emulator.skip_intro()

        # Capture screenshots at intervals, like the real loop does
        screenshots: list[np.ndarray] = []
        for i in range(5):
            runner.emulator.wait(30)
            screenshot = runner.emulator.capture()
            screenshots.append(screenshot)

        assert len(screenshots) == 5, f"Expected 5 screenshots, got {len(screenshots)}"

        for idx, shot in enumerate(screenshots):
            assert isinstance(shot, np.ndarray), (
                f"Screenshot {idx}: expected np.ndarray, got {type(shot)}"
            )
            assert shot.ndim == 3, (
                f"Screenshot {idx}: expected 3 dims, got {shot.ndim}"
            )
            assert shot.shape == expected_shape, (
                f"Screenshot {idx}: expected shape {expected_shape} ({'GB' if is_gb else 'GBA'}), "
                f"got {shot.shape}"
            )
            assert shot.dtype == np.uint8, (
                f"Screenshot {idx}: expected uint8, got {shot.dtype}"
            )
            # Verify pixel values are in RGB range
            assert 0 <= shot.min() <= shot.max() <= 255, (
                f"Screenshot {idx}: pixel values out of range [{shot.min()}, {shot.max()}]"
            )

        print(f"  AC-012 PASS: 5 screenshots validated — shape={expected_shape}, "
              f"dtype=uint8, {'GB' if is_gb else 'GBA'} platform")
    finally:
        runner.cleanup()


# ── AC-013: Demo summary fields ──────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.live_api
def test_demo_summary_fields(_require_live: Path):
    """AC-013: Demo summary includes screen_types_seen, success_rate, elapsed_s."""
    rom_path = _require_live
    runner = DemoRunner(str(rom_path))
    try:
        result = runner.run(max_cycles=3, screenshot_interval=30, skip_intro=True)

        # Required fields
        assert "screen_types_seen" in result, "Missing screen_types_seen"
        assert "success_rate" in result, "Missing success_rate"
        assert "elapsed_s" in result, "Missing elapsed_s"

        # Field types and ranges
        assert isinstance(result["screen_types_seen"], list)
        assert isinstance(result["success_rate"], float)
        assert 0.0 <= result["success_rate"] <= 1.0
        assert isinstance(result["elapsed_s"], (int, float))
        assert result["elapsed_s"] > 0

        # Also verify rom_path and cycles fields
        assert "rom_path" in result
        assert "cycles_completed" in result
        assert "cycles_requested" in result
        assert "tool_calls_made" in result

        # demo_summary() should format these fields correctly
        summary = demo_summary(result)
        assert str(result["cycles_completed"]) in summary
        assert "Success rate:" in summary or f"{result['success_rate']:.0%}" in summary
        assert "Screen types:" in summary or "screen_types" in summary.lower()
        assert "Elapsed:" in summary

        print(f"  AC-013 PASS: screen_types_seen={result['screen_types_seen']}, "
              f"success_rate={result['success_rate']:.2f}, "
              f"elapsed_s={result['elapsed_s']:.1f}")
    finally:
        runner.cleanup()
