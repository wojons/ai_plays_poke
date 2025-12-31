# GameAIManager

Manages AI models for Pokemon gameplay decisions.

## Overview

The `GameAIManager` class coordinates between vision models (for reading screens) and text models (for strategic/thinking/reasoning). It integrates with the Vision & Perception Engine for local screen analysis and supports multiple AI providers (OpenRouter, Anthropic Claude).

## Class Signature

```python
class GameAIManager:
    def __init__(
        self,
        api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        enable_prompt_manager: bool = True,
        model_priority: str = "balanced"
    )
```

## Constructor

### `__init__(self, api_key: Optional[str] = None, anthropic_api_key: Optional[str] = None, enable_prompt_manager: bool = True, model_priority: str = "balanced")`

Initialize the AI manager.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | `Optional[str]` | `None` | OpenRouter API key (loads from env if None) |
| `anthropic_api_key` | `Optional[str]` | `None` | Anthropic API key (loads from env if None) |
| `enable_prompt_manager` | `bool` | `True` | Whether to enable PromptManager |
| `model_priority` | `str` | `"balanced"` | Model selection priority (speed/cost/quality/balanced) |

**Example:**

```python
from src.core.ai_client import GameAIManager

# With explicit API keys
ai_manager = GameAIManager(
    api_key="sk-or-v1-...",
    anthropic_api_key="sk-ant-...",
    model_priority="balanced"
)

# Using environment variables
ai_manager = GameAIManager()
```

## Methods

### `analyze_screenshot(self, screenshot: np.ndarray) -> Dict[str, Any]`

Analyze screenshot using vision model.

```python
screenshot = emulator.capture_screen()
result = ai_manager.analyze_screenshot(screenshot)

print(result)
# {
#     "screen_type": "battle",
#     "enemy_pokemon": "Pidgey",
#     "player_hp": 85,
#     "enemy_hp": 100,
#     "recommended_action": "press:A",
#     "reasoning": "Wild Pidgey appeared"
# }
```

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `screen_type` | `str` | Type of screen (battle, overworld, menu, dialog) |
| `enemy_pokemon` | `Optional[str]` | Enemy Pokemon name if in battle |
| `player_hp` | `int` | Player HP percentage (0-100) |
| `enemy_hp` | `int` | Enemy HP percentage (0-100) |
| `recommended_action` | `str` | Recommended action (e.g., "press:A") |
| `reasoning` | `str` | Explanation for the recommendation |

---

### `make_strategic_decision(self, journey_summary: str, battle_state: str, objective: str, past_failures: str, model: Optional[str] = None) -> Dict[str, Any]`

Make strategic planning decision using thinking model.

```python
result = ai_manager.make_strategic_decision(
    journey_summary="Just received Pokedex from Professor Oak",
    battle_state="No active battle",
    objective="Catch Pokemon and defeat Brock",
    past_failures="Lost to Geodude - need grass type"
)

print(result)
# {
#     "objective": "Defeat Brock",
#     "key_tactics": ["Catch Bulbasaur", "Train to level 10+"],
#     "risks": "Early game weak team",
#     "confidence": 0.75
# }
```

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `objective` | `str` | High-level objective |
| `key_tactics` | `List[str]` | 2-3 specific actions |
| `risks` | `str` | Potential risks |
| `confidence` | `float` | Confidence level (0.0-1.0) |

---

### `make_tactical_decision(self, player_pokemon: str, player_hp: float, enemy_pokemon: str, enemy_hp: float, enemy_type: str, moves: List[str], weaknesses: List[str], recent_actions: str, strategy: str, turn: int, model: Optional[str] = None) -> Dict[str, Any]`

Make immediate tactical decision for battle.

```python
result = ai_manager.make_tactical_decision(
    player_pokemon="Charmander",
    player_hp=75.0,
    enemy_pokemon="Bulbasaur",
    enemy_hp=50.0,
    enemy_type="Grass",
    moves=["Ember", "Scratch", "Growl", "Leer"],
    weaknesses=["Water", "Ground"],
    recent_actions="Turn 1: Used Ember",
    strategy="Use fire moves for type advantage",
    turn=2
)

print(result)
# {
#     "reasoning": "Ember is super-effective against Grass type",
#     "action": "press:A"
# }
```

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `reasoning` | `str` | Explanation for the decision |
| `action` | `str` | Button press action (e.g., "press:A") |

---

### `get_session_stats(self) -> Dict[str, Any]`

Get session statistics including token usage and costs.

```python
stats = ai_manager.get_session_stats()
print(stats)
# {
#     "total_calls": 150,
#     "total_input_tokens": 45000,
#     "total_output_tokens": 12000,
#     "total_cost": 0.045,
#     "json_parse_success_rate": 0.95
# }
```

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `total_calls` | `int` | Number of API calls |
| `total_input_tokens` | `int` | Total input tokens used |
| `total_output_tokens` | `int` | Total output tokens generated |
| `total_cost` | `float` | Total cost in USD |
| `json_parse_success_rate` | `float` | JSON parsing success rate |

---

### `reset_session_stats(self)`

Reset session statistics for a new session.

```python
ai_manager.reset_session_stats()
```

## Internal Components

### Model Selection

The AI manager uses a `ModelRouter` to select appropriate models based on task type:

| Task Type | Balanced Priority | Speed Priority | Quality Priority |
|-----------|-------------------|----------------|------------------|
| Vision | openai/gpt-4o | openai/gpt-4o-mini | anthropic/claude-3-sonnet |
| Thinking | openai/gpt-4o-mini | openai/gpt-4o-mini | anthropic/claude-3-sonnet |
| Acting | openai/gpt-4o-mini | openai/gpt-4o-mini | anthropic/claude-3-haiku |

### Rate Limiting

The `RateLimiter` prevents API rate limit errors:

- Maximum: 50 requests per 60 seconds
- Exponential backoff on retries
- Configurable via constructor

### Circuit Breaker

The `CircuitBreaker` pattern prevents cascade failures:
- Opens after 5 consecutive failures
- Recovery time: 60 seconds
- Half-open state for testing recovery

## Usage Example

```python
import numpy as np
from src.core.ai_client import GameAIManager
from src.core.emulator_interface import EmulatorInterface

# Initialize
ai_manager = GameAIManager(model_priority="balanced")
emulator = EmulatorInterface("pokemon_red.gb")
emulator.start()

# Analyze screenshot
screenshot = emulator.capture_screen()
analysis = ai_manager.analyze_screenshot(screenshot)

# Make tactical decision in battle
if analysis["screen_type"] == "battle":
    decision = ai_manager.make_tactical_decision(
        player_pokemon="Pikachu",
        player_hp=100.0,
        enemy_pokemon=analysis["enemy_pokemon"],
        enemy_hp=analysis["enemy_hp"],
        enemy_type="Normal",
        moves=["ThunderShock", "Quick Attack", "Growl", "Tail Whip"],
        weaknesses=["Ground"],
        recent_actions="Battle started",
        strategy="Use ThunderShock for type advantage",
        turn=1
    )
    print(f"Action: {decision['action']}")
    print(f"Reasoning: {decision['reasoning']}")

# Check costs
stats = ai_manager.get_session_stats()
print(f"Session cost: ${stats['total_cost']:.3f}")
```

## See Also

- [AICommand](../ai_command.md) - Command structure
- [GameState](../game_state.md) - Game state context
- [BattleState](../battle_state.md) - Battle information