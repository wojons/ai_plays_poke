"""
Command schemas for AI → Emulator communication

Defines the structure for:
- Commands sent from AI to emulator
- AI thinking process data
- Game state context
"""

from dataclasses import dataclass, asdict
import json
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime


class Button(str, Enum):
    """All Game Boy buttons"""
    A = "A"
    B = "B"
    START = "START"
    SELECT = "SELECT"
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class CommandType(str, Enum):
    """Types of commands the AI can send"""
    PRESS = "press"           # Single button press
    HOLD = "hold"           # Hold button for duration
    RELEASE = "release"      # Release held button
    SEQUENCE = "sequence"    # Sequence of buttons
    BATCH = "batch"          # Batched movement (e.g., walk 10 steps)
    WAIT = "wait"           # Wait for specified time


@dataclass
class AICommand:
    """
    Base command structure from AI to emulator
    
    Example:
    {
        "command_type": "press",
        "button": "A",
        "reasoning": "Press A to select Ember",
        "confidence": 0.85,
        "wait_ticks": 60
    }
    """
    command_type: CommandType
    reasoning: str
    confidence: float
    tick: int
    timestamp: str
    
    # Command-specific fields
    button: Optional[Button] = None
    button_sequence: Optional[List[Button]] = None
    duration_ms: Optional[int] = None
    wait_ticks: int = 60
    batch_direction: Optional[str] = None
    batch_steps: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        d = asdict(self)
        # Convert enums to strings
        if isinstance(d.get("command_type"), CommandType):
            d["command_type"] = d["command_type"].value
        if isinstance(d.get("button"), Button):
            d["button"] = d["button"].value
        if d.get("button_sequence"):
            d["button_sequence"] = [b.value for b in d["button_sequence"]]
        return d
    
    def to_string(self) -> str:
        """Convert to simple string format: 'press:A'"""
        if self.command_type == CommandType.PRESS and self.button:
            return f"press:{self.button.value}"
        elif self.command_type == CommandType.SEQUENCE and self.button_sequence:
            formatted = ",".join(b.value for b in self.button_sequence)
            return f"sequence:{formatted}"
        elif self.command_type == CommandType.BATCH:
            return f"batch:{self.batch_direction}x{self.batch_steps}"
        elif self.command_type == CommandType.WAIT:
            return f"wait:{self.wait_ticks}"
        else:
            return f"{self.command_type.value}:unknown"


@dataclass
class AIThought:
    """
    AI thinking process for logging
    
    Stores the reasoning behind AI decisions
    """
    tick: int
    timestamp: str
    
    # The thought process
    thought_process: str      # High-level what AI is doing
    reasoning: str            # Detailed why AI is doing it
    proposed_action: str      # What action AI wants to take
    
    # Context
    game_state: Dict[str, Any]  # Current game state
    
    # Metadata
    model_used: str           # Which AI model
    confidence: float         # Confidence in decision
    tokens_used: int          # Input + output tokens
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database logging"""
        d = asdict(self)
        d["game_state"] = json.dumps(d.get("game_state", {}))
        return d


@dataclass
class GameState:
    """
    Current game state snapshot
    
    Used to provide context to AI models
    """
    tick: int
    timestamp: str
    
    # Screen state
    screen_type: str         # "battle", "overworld", "menu", "dialog", "transition"
    
    # Battle state (if in battle)
    is_battle: bool          # Are we in a battle?
    is_menu: bool
    has_dialog: bool
    can_move: bool = True
    turn_number: int = 0
    enemy_pokemon: Optional[str] = None
    enemy_hp_percent: Optional[float] = None
    player_hp_percent: Optional[float] = None
    menu_type: Optional[str] = None  # "pokemon", "bag", "main", "options", etc
    cursor_position: Optional[tuple] = None  # (x, y) on menu grid
    dialog_text: Optional[str] = None
    location: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API/logging"""
        return asdict(self)


@dataclass
class BattleState:
    """
    Detailed battle information for Strategist/Tactician
    
    This is what the Vision System should extract and enrich with Pokédex data
    """
    tick: int
    timestamp: str
    enemy_pokemon: str
    enemy_level: int
    enemy_hp_percent: float
    player_pokemon: str
    player_level: int
    player_hp_percent: float
    battle_id: Optional[int] = None
    enemy_types: Optional[List[str]] = None
    enemy_base_stats: Optional[Dict[str, int]] = None
    enemy_weaknesses: Optional[List[str]] = None
    enemy_resistances: Optional[List[str]] = None
    turn_number: int = 0
    available_moves: Optional[List[str]] = None
    
    def get_type_advice(self) -> str:
        """Generate type matchup advice string"""
        if not self.enemy_weaknesses:
            return "No type data available"
        return f"Use {', '.join(self.enemy_weaknesses)} type moves for super-effective damage"


@dataclass
class CommandExecutionResult:
    """
    Result of executing a command
    """
    command: AICommand
    success: bool
    execution_time_ms: float
    error_message: Optional[str] = None
    game_state_after: Optional[GameState] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        d = {
            "tick": self.command.tick,
            "command_type": self.command.command_type.value,
            "command_value": self.command.to_string(),
            "reasoning": self.command.reasoning,
            "confidence": self.command.confidence,
            "success": self.success,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms
        }
        if self.game_state_after:
            d["game_state_after"] = self.game_state_after.to_dict()
        return d


# Helper functions

def create_press_command(button: Button, reasoning: str, 
                        tick: int, confidence: float = 0.8) -> AICommand:
    """Create a simple press button command"""
    return AICommand(
        command_type=CommandType.PRESS,
        button=button,
        reasoning=reasoning,
        confidence=confidence,
        tick=tick,
        timestamp=datetime.now().isoformat()
    )


def create_batch_command(direction: str, steps: int, reasoning: str,
                        tick: int, confidence: float = 0.8) -> AICommand:
    """Create a batch navigation command"""
    return AICommand(
        command_type=CommandType.BATCH,
        batch_direction=direction,
        batch_steps=steps,
        reasoning=reasoning,
        confidence=confidence,
        tick=tick,
        timestamp=datetime.now().isoformat()
    )


def parse_command_string(command_str: str) -> Optional[Dict[str, Any]]:
    """
    Parse command string to components
    
    Examples:
        "press:A" → {"command_type": "press", "button": "A"}
        "batch:UPx10" → {"command_type": "batch", "batch_direction": "UP", "batch_steps": 10}
        "sequence:UP,UP,LEFT,A" → {"command_type": "sequence", "button_sequence": [...]}
    """
    parts = command_str.split(":")
    if len(parts) != 2:
        return None
    
    command_type, params = parts
    result = {"command_type": command_type}
    
    if command_type == "press":
        if params in [b.value for b in Button]:
            result["button"] = params
            return result
    elif command_type == "batch":
        if "x" in params:
            direction, steps = params.split("x")
            result["batch_direction"] = direction
            result["batch_steps"] = int(steps)
            return result
    elif command_type == "sequence":
        buttons = params.split(",")
        if all(b in [btn.value for btn in Button] for b in buttons):
            result["button_sequence"] = buttons
            return result
    
    return None
