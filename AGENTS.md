# AI Agents Guide for PTP-01X Pokémon AI

## Project Overview
PTP-01X is a comprehensive autonomous Pokémon AI benchmarking system with ~53,500 lines of specifications covering gameplay AI, CLI infrastructure, mode duration tracking, API integration, and edge case handling.

## Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# For development (includes linting/formatting tools)
pip install -r requirements.txt  # Already includes pytest, black, mypy, flake8
```

## Build & Development Commands

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_vision.py -v

# Run specific test function
pytest tests/test_vision.py::test_screen_classification -v

# Run tests with coverage
pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

# Run tests in parallel (if many tests)
pytest tests/ -n auto -v

# Run tests with verbose output and stop on first failure
pytest tests/ -v -x
```

### Code Formatting & Linting
```bash
# Format code with Black (line length: 88)
black src/ tests/

# Check formatting without changes
black --check src/ tests/

# Run type checking with mypy
mypy src/ --ignore-missing-imports --strict

# Run linting with flake8
flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203,W503

# Run import sorting (if isort is installed)
isort src/ tests/

# Pre-commit hooks (if configured)
pre-commit run --all-files
```

### Running the AI
```bash
# Basic run (when implemented)
python -m src.cli.main --experiment-name "test-run-001" --max-time 3600

# Debug mode with verbose logging
python -m src.cli.main --verbose --log-file debug.log

# Run with specific configuration
python -m src.cli.main --config-file config/experiment.yaml

# Run with parallel workers
python -m src.cli.experiment --parallel-workers 4 --experiment-name "bench-001"
```

## Testing Strategy

### Test Structure
```
tests/
├── test_vision.py          # Vision & OCR tests
├── test_state_machine.py   # Hierarchical state machine tests
├── test_battle.py          # Combat heuristics tests
├── test_navigation.py      # World navigation tests
├── test_inventory.py       # Inventory system tests
├── test_dialogue.py        # Dialogue system tests
├── test_goap.py           # GOAP planner tests
├── test_failsafe.py       # Failsafe protocol tests
└── conftest.py            # Pytest fixtures
```

### Writing Tests
```python
# Use pytest fixtures for common setup
@pytest.fixture
def mock_game_state():
    return {
        "location": "Pallet Town",
        "team": [{"name": "Pikachu", "hp": 35, "max_hp": 35}],
        "badges": 0
    }

# Test naming: test_feature_behavior_expectedOutcome
def test_vision_classifies_battle_screen(mock_screenshot):
    # Arrange
    vision = VisionProcessor()
    
    # Act
    result = vision.classify_screen(mock_screenshot)
    
    # Assert
    assert result.screen_type == "battle"
    assert result.confidence > 0.90

# Use pytest.mark for test categories
@pytest.mark.integration
def test_full_battle_sequence():
    pass

@pytest.mark.slow
def test_long_navigation_path():
    pass
```

### Testing Patterns
1. **Unit tests**: Test individual functions/classes in isolation
2. **Integration tests**: Test component interactions (mark with `@pytest.mark.integration`)
3. **Property-based tests**: Use `hypothesis` for edge case testing
4. **Mock external APIs**: Use `pytest-mock` or `unittest.mock` for LLM calls

## Code Style Guidelines

### Imports
```python
# Standard library imports first
import json
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass

# Third-party imports second
import pytest
import numpy as np
from PIL import Image

# Local imports last (absolute imports)
from src.core.vision import VisionProcessor
from src.core.game_loop import GameLoop
from src.cli.config import CLIConfig
```

### Type Hints
```python
# Always use type hints
from typing import Dict, List, Optional, Union, Any

def process_screenshot(screenshot: Image.Image) -> Dict[str, Any]:
    """Process screenshot and return classification result."""
    pass

# Use Optional for nullable types
def get_context(key: str, default: Optional[str] = None) -> str:
    pass

# Use Union for multiple types
def normalize_value(value: Union[int, float, str]) -> float:
    pass

# Use mypy-compatible generics
T = TypeVar('T')
class Result(Generic[T]):
    value: T
```

### Error Handling
```python
# Custom exceptions for domain-specific errors
class PokemonAIError(Exception):
    """Base exception for Pokemon AI errors."""
    pass

class VisionError(PokemonAIError):
    """Exception for vision/screen classification errors."""
    pass

class GameStateError(PokemonAIError):
    """Exception for invalid game state errors."""
    pass

# Use try-except with specific error types
try:
    screenshot = capture_screenshot()
    state = vision_processor.classify(screenshot)
except VisionError as e:
    log_warning(f"Vision failed, using fallback: {e}")
    state = self._use_fallback_state()
except Exception as e:
    log_error(f"Unexpected error: {e}")
    raise GameStateError(f"Failed to classify game state: {e}") from e

# Use context managers for resources
with open(save_path, 'rb') as f:
    save_data = f.read()
```

### Naming Conventions
- **Functions/Methods**: `snake_case`, descriptive verbs: `classify_screen()`, `calculate_move_damage()`
- **Classes**: `PascalCase`, descriptive nouns: `VisionProcessor`, `BattleHeuristics`
- **Variables**: `snake_case`: `current_hp`, `enemy_pokemon`
- **Constants**: `UPPER_SNAKE_CASE`: `MAX_LEVEL = 100`, `SCREEN_WIDTH = 160`
- **Private members**: Leading underscore: `_internal_cache`, `_private_method()`
- **Type variables**: `PascalCase` with `T` suffix: `PokemonT`, `GameStateT`

### Code Organization
```python
# Keep functions pure when possible
def calculate_damage(
    attacker: PokemonStats,
    defender: PokemonStats,
    move: Move,
    is_critical: bool = False
) -> int:
    """Pure function - no side effects."""
    base_damage = (2 * attacker.level / 5 + 2) * move.power * attacker.attack / defender.defense
    return int(base_damage / 50) + 2

# Use classes for stateful operations
class BattleManager:
    def __init__(self, game_state: GameState):
        self.state = game_state
        self.turn_count = 0
    
    def execute_turn(self, action: BattleAction) -> TurnResult:
        """Stateful method - modifies internal state."""
        # Implementation
        pass
```

### Documentation
```python
def catch_pokemon(
    wild_pokemon: Pokemon,
    ball_type: str,
    status_condition: Optional[str] = None
) -> CatchResult:
    """
    Attempt to catch a wild Pokémon.
    
    Args:
        wild_pokemon: The wild Pokémon to catch
        ball_type: Type of Poké Ball (e.g., "Poke Ball", "Great Ball", "Ultra Ball")
        status_condition: Status condition affecting catch rate (e.g., "sleep", "paralyze")
    
    Returns:
        CatchResult with success/failure and number of shakes
    
    Raises:
        ValueError: If ball_type is not a valid Poké Ball
        GameStateError: If not in a wild encounter
    
    Note:
        Implements Generation I catch rate formula:
        - Base catch rate varies by Pokémon species
        - Status conditions increase catch rate
        - HP remaining affects catch rate
    """
    # Implementation
    pass
```

## Project-Specific Guidelines

### Memory Bank Updates
```python
# When making significant changes, update memory bank:
from memory_bank import MemoryBankManager

async def update_memory_bank(change: str, impact: str):
    """Update memory bank with implementation changes."""
    manager = MemoryBankManager()
    await manager.record_implementation(
        change_type="enhancement",
        description=change,
        impact=impact,
        update_active_context=True,
        update_progress=True
    )
```

### Specification Compliance
- Always reference `specs/ptp_01x_detailed/` for implementation details
- Update `specs/SPEC_INDEX.md` when adding new specifications
- Follow spec-driven format: Mermaid diagrams + pseudo-code + LLM prompts

### Error Recovery
```python
# Implement graceful degradation
async def classify_screenshot(screenshot: Image.Image) -> ScreenClassification:
    try:
        # Primary method: model-based classification
        return await self._classify_with_model(screenshot)
    except VisionError:
        try:
            # Fallback: rule-based classification
            return self._classify_with_heuristics(screenshot)
        except Exception as e:
            # Last resort: return unknown state
            log_error(f"All classification methods failed: {e}")
            return ScreenClassification(
                type="unknown",
                confidence=0.0,
                reason="classification_failed"
            )
```

### LLM Integration Best Practices
```python
# Always use structured prompts
async def make_decision_with_llm(game_state: GameState, active_goals: list) -> Decision:
    prompt = {
        "system_prompt": "You are a Pokemon AI assistant...",
        "game_state": game_state.to_dict(),
        "active_goals": [g.to_dict() for g in active_goals],
        "last_action_result": self.last_result,
        "temperature": 0.7,
        "json_mode": True
    }
    
    try:
        response = await api_client.generate(prompt)
        return Decision.from_json(response.content)
    except APIError as e:
        log_warning(f"LLM call failed, using heuristic: {e}")
        return self._use_heuristic_decision(game_state, active_goals)
```

## Debugging Tips

### Verbose Logging
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python -m src.cli.main --verbose

# Log to file
python -m src.cli.main --log-file session.log
```

### Performance Profiling
```bash
# Profile CPU usage
py-spy record -o profile.svg -- python -m src.cli.main

# Monitor memory
mprof run python -m src.cli.main
mprof plot
```

### Interactive Debugging
```python
# Use pdb for debugging
import pdb; pdb.set_trace()

# Use ipdb for better debugging (install: pip install ipdb)
import ipdb; ipdb.set_trace()

# Use streamlit for runtime visualization (if available)
streamlit run src/dashboard/run.py
```

## Performance Guidelines

### Optimization Targets
- Vision/OCR: <1 second per screen
- Decision making: <500ms per action
- API calls: <2 seconds (with retry logic)
- Database operations: <100ms per query
- State transitions: <100ms

### Profiling Benchmarks
```bash
# Benchmark vision system
pytest benchmarks/test_vision_benchmark.py --benchmark-only

# Profile memory usage during long runs
pytest tests/ -k "test_100_hour_session" --memray
```

---

**Last Updated:** December 31, 2025  
**Agent Version:** PTP-01X Implementation Assistant