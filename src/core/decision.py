"""
Decision Loop — connects vision output → prompt assembly → thinking model →
tool call → emulator execution for AI Plays Pokémon.
"""

from __future__ import annotations

import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from src.core.emulator import Emulator
from src.core.vision import VisionClient
from src.core.prompt_assembler import PromptStack
from src.core.memory import GameMemory
from src.core.ai_client import OpenRouterClient
from src.core.tools import TOOL_SCHEMA, parse_tool_call, execute_tool_call


class DecisionLoop:
    """Orchestrates one full decision cycle every *screenshot_interval* frames.

    Each cycle: capture → vision → prompt assembly → thinking → tool execution.
    """

    def __init__(
        self,
        emulator: Emulator,
        generation: str = "gen1",
        thinking_model: str = "openrouter/owl-alpha",
        vision_model: str = "google/gemma-3-12b-it",
    ) -> None:
        self.emulator = emulator
        self.generation = generation
        self.thinking_model = thinking_model

        # Wire up components
        self.vision = VisionClient(model=vision_model)
        self.prompt_stack = PromptStack()
        self.memory = GameMemory()
        self.client = OpenRouterClient()

        # Screenshots directory — saved for Bane to review
        self._run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._screenshots_dir = Path("screenshots") / f"run_{self._run_id}"
        self._screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._step_count = 0

        # Fallback state — persisted across cycles
        self._last_vision: dict[str, Any] = {"screen_type": "unknown"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(self) -> dict[str, Any]:
        """One full decision cycle.

        Returns a dictionary with keys:
            vision, screen_type, prompt, raw_response, tool_call, action, success,
            screenshot, run_dir
        """
        self._step_count += 1

        # 1. Capture screenshot
        screenshot = self.emulator.capture()

        # Save screenshot for review
        ss_path = self._screenshots_dir / f"step_{self._step_count:04d}.png"
        Image.fromarray(screenshot).save(str(ss_path))

        result: dict[str, Any] = {
            "vision": None,
            "screen_type": "unknown",
            "prompt": "",
            "raw_response": "",
            "tool_call": None,
            "action": "",
            "success": False,
            "screenshot": str(ss_path),
            "run_dir": str(self._screenshots_dir),
        }

        # 2. Vision: analyse screenshot
        try:
            vision_output = self.vision.analyze(screenshot, game=self.generation)
            self._last_vision = vision_output
        except Exception:
            print("[FALLBACK] Vision failed — using previous/unknown screen type")
            vision_output = self._last_vision

        result["vision"] = vision_output
        screen_type = vision_output.get("screen_type", "unknown")
        result["screen_type"] = screen_type

        # 3. Select & assemble prompt
        try:
            assembled_prompt = self.prompt_stack.assemble(
                generation=self.generation,
                screen_type=screen_type,
                vision_output=vision_output,
                memory_context=self.memory.snapshot(),
            )
        except Exception:
            # If the screen_type is unrecognised (no YAML), fall back to 'overworld'
            print(f"[FALLBACK] Prompt assembly failed for screen_type={screen_type!r} → falling back to overworld")
            assembled_prompt = self.prompt_stack.assemble(
                generation=self.generation,
                screen_type="overworld",
                vision_output=vision_output,
                memory_context=self.memory.snapshot(),
            )

        result["prompt"] = assembled_prompt

        # 4. Thinking: call owl-alpha with prompt + TOOL_SCHEMA
        try:
            raw_response = self.client.send_tool_request(
                prompt=assembled_prompt,
                tools=TOOL_SCHEMA,
                model=self.thinking_model,
                max_tokens=200,
                temperature=0.3,
            )
        except Exception:
            print("[FALLBACK] Thinking model failed — using default action (press A)")
            raw_response = ""

        result["raw_response"] = raw_response

        # 5. Parse tool call
        tool_call = None
        if raw_response:
            tool_call = parse_tool_call(raw_response)
        if tool_call is None:
            print("[FALLBACK] Tool-call parse failed — using default action (press A)")
            tool_call = {"name": "press_button", "arguments": {"button": "a", "duration": 5}}

        result["tool_call"] = tool_call

        # 6. Execute tool call on emulator
        action_result = execute_tool_call(
            self.emulator,
            tool_name=tool_call["name"],
            arguments=tool_call.get("arguments", {}),
        )
        result["action"] = action_result
        result["success"] = not action_result.startswith("Error")

        # 7. Record action in memory
        self.memory.record_action(action_result)

        return result

    def run(
        self,
        max_steps: int = 1000,
        screenshot_interval: int = 60,
    ) -> list[dict[str, Any]]:
        """Run the game loop for *max_steps* cycles.

        Each cycle advances the emulator by *screenshot_interval* frames,
        then calls :meth:`step`.

        Returns:
            List of step result dicts.
        """
        results: list[dict[str, Any]] = []

        for i in range(max_steps):
            # Advance emulator between decisions
            self.emulator.wait(screenshot_interval)

            try:
                step_result = self.step()
            except Exception:
                traceback.print_exc()
                step_result = {
                    "vision": self._last_vision,
                    "screen_type": "unknown",
                    "prompt": "",
                    "raw_response": "",
                    "tool_call": None,
                    "action": f"[ERROR step {i}]",
                    "success": False,
                }

            results.append(step_result)

        return results
