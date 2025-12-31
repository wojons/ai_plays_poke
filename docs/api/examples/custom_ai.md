# Custom AI Integration Example

This example demonstrates how to integrate a custom AI model with PTP-01X.

## Custom AI Manager

Create a custom AI manager that extends or replaces the default behavior:

```python
from typing import Dict, Any, Optional
import numpy as np
from src.core.ai_client import GameAIManager
from src.schemas.commands import GameState, AICommand, Button, CommandType


class CustomAIManager:
    """
    Custom AI manager for specialized decision making
    """

    def __init__(self, model_path: str):
        """
        Initialize with custom model

        Args:
            model_path: Path to custom model
        """
        self.model = self._load_model(model_path)
        self.decision_history = []

    def _load_model(self, model_path: str):
        """Load custom model"""
        # Implement your model loading here
        return {"type": "custom", "path": model_path}

    def analyze_game_state(
        self,
        screenshot: np.ndarray,
        game_state: GameState
    ) -> AICommand:
        """
        Analyze game state and generate command

        Args:
            screenshot: Current game screenshot
            game_state: Current game state

        Returns:
            AICommand to execute
        """
        # Your custom AI logic here
        decision = self._model_inference(screenshot, game_state)

        cmd = AICommand(
            command_type=CommandType.PRESS,
            button=decision["button"],
            reasoning=decision["reasoning"],
            confidence=decision["confidence"],
            tick=game_state.tick,
            timestamp=datetime.now().isoformat()
        )

        self.decision_history.append(cmd)
        return cmd

    def _model_inference(
        self,
        screenshot: np.ndarray,
        game_state: GameState
    ) -> Dict[str, Any]:
        """Run model inference"""
        # Your inference logic here
        return {
            "button": Button.A,
            "reasoning": "Default action",
            "confidence": 0.8
        }


# Usage
custom_ai = CustomAIManager("models/custom_pokemon_ai.pt")
```

## Integration with GameLoop

Modify the game loop to use your custom AI:

```python
from pathlib import Path
from src.core.game_loop import GameLoop
from src.core.emulator_interface import EmulatorInterface
from src.core.screenshot_manager import ScreenshotManager
from custom_ai import CustomAIManager
from src.schemas.commands import GameState


class CustomGameLoop:
    """Game loop with custom AI integration"""

    def __init__(
        self,
        rom_path: Path,
        save_dir: Path,
        ai_manager: CustomAIManager
    ):
        self.rom_path = rom_path
        self.save_dir = save_dir
        self.ai_manager = ai_manager

        # Initialize components
        self.emulator = EmulatorInterface(str(rom_path))
        self.screenshot_manager = ScreenshotManager(str(save_dir / "screenshots"))

        # State
        self.current_tick = 0
        self.is_running = False

    def start(self):
        """Start the game loop"""
        self.emulator.start()
        self.is_running = True

    def stop(self):
        """Stop the game loop"""
        self.emulator.stop()
        self.is_running = False

    def run_single_tick(self):
        """Execute one tick with custom AI"""
        # Advance emulator
        self.emulator.tick()
        self.current_tick += 1

        # Capture screenshot
        screenshot = self.emulator.capture_screen()

        # Analyze game state
        game_state = self._analyze_state(screenshot)

        # Get AI decision
        command = self.ai_manager.analyze_game_state(screenshot, game_state)

        # Execute command
        self.emulator.press_button(command.button)

    def _analyze_state(self, screenshot: np.ndarray) -> GameState:
        """Analyze screenshot to determine game state"""
        # Your state analysis logic
        return GameState(
            tick=self.current_tick,
            timestamp=datetime.now().isoformat(),
            screen_type="overworld",
            is_battle=False,
            is_menu=False,
            has_dialog=False
        )


# Usage
ai = CustomAIManager("models/custom.pt")
loop = CustomGameLoop(
    rom_path=Path("pokemon_red.gb"),
    save_dir=Path("./saves"),
    ai_manager=ai
)

loop.start()
for _ in range(1000):
    loop.run_single_tick()
loop.stop()
```

## Hook-Based Integration

Extend the existing `GameAIManager` with custom hooks:

```python
from src.core.ai_client import GameAIManager
from src.schemas.commands import GameState
import numpy as np


class HookedAIManager(GameAIManager):
    """GameAIManager with custom hooks for extensibility"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hooks = []

    def add_hook(self, hook_fn):
        """Add custom hook"""
        self.hooks.append(hook_fn)

    def analyze_screenshot(self, screenshot: np.ndarray) -> Dict[str, Any]:
        """Override with hook support"""
        # Run custom hooks before
        for hook in self.hooks:
            screenshot = hook.pre_process(screenshot)

        # Call parent method
        result = super().analyze_screenshot(screenshot)

        # Run custom hooks after
        for hook in self.hooks:
            result = hook.post_process(result)

        return result


class CustomHook:
    """Example hook for custom processing"""

    def pre_process(self, screenshot: np.ndarray) -> np.ndarray:
        """Pre-process screenshot"""
        # Your preprocessing
        return screenshot

    def post_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process result"""
        # Your postprocessing
        result["custom_field"] = "custom_value"
        return result


# Usage
ai = HookedAIManager()
ai.add_hook(CustomHook())
```

## Next Steps

- [Data Export](data_export.md) - Export session data
- [API Reference](../index.md) - Full API documentation
- [GameState](../game_state.md) - State structure