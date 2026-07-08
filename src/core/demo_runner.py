"""
Demo Runner — end-to-end gameplay test for AI Plays Pokémon.

Loads a ROM, skips the intro sequence, then runs the decision loop for
a configurable number of cycles, collecting structured results for analysis.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from src.core.emulator import Emulator
from src.core.decision import DecisionLoop


class DemoRunner:
    """Loads ROM → skips intro → runs decision cycles → reports."""

    def __init__(
        self,
        rom_path: str | Path,
        *,
        generation: str = "gen3",
        thinking_model: str = "openrouter/owl-alpha",
        vision_model: str = "google/gemma-3-12b-it",
    ) -> None:
        self._rom_path = Path(rom_path).resolve()
        self._generation = generation
        self._thinking_model = thinking_model
        self._vision_model = vision_model

        self.emulator: Emulator | None = None
        self.loop: DecisionLoop | None = None
        self.results: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        max_cycles: int = 10,
        screenshot_interval: int = 60,
        skip_intro: bool = True,
        intro_press_frames: int = 30,
        intro_wait_frames: int = 60,
        intro_repetitions: int = 16,
    ) -> dict[str, Any]:
        """Execute the gameplay demo.

        Returns a summary dictionary with keys:
            rom_path, cycles_requested, cycles_completed, success_rate,
            screen_types_seen, tool_calls_made, elapsed_s, results.
        """
        t0 = time.monotonic()

        if not self._rom_path.is_file():
            raise FileNotFoundError(f"ROM not found: {self._rom_path}")

        # 1. Load ROM
        self.emulator = Emulator(str(self._rom_path))

        # 2. Skip intro
        if skip_intro:
            self.emulator.skip_intro(
                press_frames=intro_press_frames,
                wait_frames=intro_wait_frames,
                repetitions=intro_repetitions,
            )

        # 3. Wire up decision loop
        self.loop = DecisionLoop(
            emulator=self.emulator,
            generation=self._generation,
            thinking_model=self._thinking_model,
            vision_model=self._vision_model,
        )

        # 4. Run
        self.results = self.loop.run(
            max_steps=max_cycles,
            screenshot_interval=screenshot_interval,
        )

        # 5. Summarize
        elapsed = time.monotonic() - t0
        cycles_completed = len(self.results)
        successes = sum(1 for r in self.results if r.get("success"))

        screen_types: set[str] = set()
        tool_calls: list[dict[str, Any]] = []
        for r in self.results:
            st = r.get("screen_type", "unknown")
            if st:
                screen_types.add(st)
            tc = r.get("tool_call")
            if tc:
                tool_calls.append(tc)

        return {
            "rom_path": str(self._rom_path),
            "cycles_requested": max_cycles,
            "cycles_completed": cycles_completed,
            "success_rate": successes / max(cycles_completed, 1),
            "screen_types_seen": sorted(screen_types),
            "tool_calls_made": len(tool_calls),
            "elapsed_s": round(elapsed, 3),
            "results": self.results,
        }

    def run_headless(
        self,
        *,
        max_cycles: int = 5,
        screenshot_interval: int = 30,
    ) -> dict[str, Any]:
        """Run demo without vision/deep-thinking (headless smoke test).

        Advances the emulator and captures screenshots at each interval,
        but skips the vision + LLM pipeline.  Useful for verifying that
        the emulator ROM loading + intro skip work end-to-end without
        needing an API key.
        """
        t0 = time.monotonic()

        if not self._rom_path.is_file():
            raise FileNotFoundError(f"ROM not found: {self._rom_path}")

        self.emulator = Emulator(str(self._rom_path))

        # Skip intro
        self.emulator.skip_intro()

        caps: list[dict[str, Any]] = []
        for i in range(max_cycles):
            self.emulator.wait(screenshot_interval)
            screen = self.emulator.capture()
            caps.append({
                "cycle": i + 1,
                "height": screen.shape[0],
                "width": screen.shape[1],
            })

        elapsed = time.monotonic() - t0
        return {
            "rom_path": str(self._rom_path),
            "mode": "headless",
            "cycles_completed": max_cycles,
            "elapsed_s": round(elapsed, 3),
            "captures": caps,
        }

    def cleanup(self) -> None:
        """Stop the emulator and release resources."""
        if self.emulator is not None:
            self.emulator.stop()
            self.emulator = None
        self.loop = None
        self.results = []


def demo_summary(result: dict[str, Any]) -> str:
    """Pretty-print a demo run summary as a single string."""
    lines: list[str] = []
    lines.append(f"ROM: {result.get('rom_path', '?')}")
    lines.append(f"Cycles: {result.get('cycles_completed', 0)} / {result.get('cycles_requested', 0)}")
    lines.append(f"Success rate: {result.get('success_rate', 0):.1%}")
    lines.append(f"Screen types: {result.get('screen_types_seen', [])}")
    lines.append(f"Tool calls: {result.get('tool_calls_made', 0)}")
    lines.append(f"Elapsed: {result.get('elapsed_s', 0):.1f}s")
    return "\n".join(lines)
