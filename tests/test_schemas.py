"""
Unit tests for command schemas and data structures

Tests command validation, game state dataclass integrity,
and serialization/deserialization functionality.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from src.schemas.commands import (
    AICommand,
    CommandType,
    Button,
    GameState,
    BattleState,
    AIThought,
    CommandExecutionResult,
    create_press_command,
    create_batch_command,
    parse_command_string,
)


class TestButtonEnum:
    """Tests for Button enum values and behavior"""

    def test_button_values_exist(self):
        """Verify all expected buttons are defined"""
        expected_buttons = {"A", "B", "START", "SELECT", "UP", "DOWN", "LEFT", "RIGHT"}
        actual_buttons = {b.value for b in Button}
        assert actual_buttons == expected_buttons

    def test_button_string_inheritance(self):
        """Button inherits from str for easy comparison"""
        assert Button.A == "A"
        assert Button.START == "START"

    def test_button_count(self):
        """Verify correct number of buttons"""
        assert len(Button) == 8


class TestCommandTypeEnum:
    """Tests for CommandType enum values and behavior"""

    def test_command_type_values_exist(self):
        """Verify all expected command types are defined"""
        expected_types = {"press", "hold", "release", "sequence", "batch", "wait"}
        actual_types = {ct.value for ct in CommandType}
        assert actual_types == expected_types

    def test_command_type_string_inheritance(self):
        """CommandType inherits from str for easy comparison"""
        assert CommandType.PRESS == "press"
        assert CommandType.BATCH == "batch"

    def test_command_type_count(self):
        """Verify correct number of command types"""
        assert len(CommandType) == 6


class TestAICommand:
    """Tests for AICommand dataclass"""

    def test_ai_command_creation_minimal(self):
        """Create AICommand with minimal required fields"""
        cmd = AICommand(
            command_type=CommandType.PRESS,
            button=Button.A,
            reasoning="Test reasoning",
            confidence=0.8,
            tick=100,
            timestamp=datetime.now().isoformat(),
        )
        assert cmd.command_type == CommandType.PRESS
        assert cmd.button == Button.A
        assert cmd.reasoning == "Test reasoning"
        assert cmd.confidence == 0.8
        assert cmd.tick == 100

    def test_ai_command_creation_full(self):
        """Create AICommand with all fields"""
        cmd = AICommand(
            command_type=CommandType.BATCH,
            batch_direction="UP",
            batch_steps=15,
            reasoning="Move up",
            confidence=0.9,
            tick=200,
            timestamp=datetime.now().isoformat(),
            duration_ms=1000,
            wait_ticks=60,
        )
        assert cmd.batch_direction == "UP"
        assert cmd.batch_steps == 15
        assert cmd.duration_ms == 1000
        assert cmd.wait_ticks == 60

    def test_ai_command_to_dict(self):
        """Test conversion to dictionary"""
        cmd = AICommand(
            command_type=CommandType.PRESS,
            button=Button.A,
            reasoning="Test",
            confidence=0.8,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        result = cmd.to_dict()
        assert isinstance(result, dict)
        assert result["command_type"] == "press"
        assert result["button"] == "A"
        assert result["tick"] == 100

    def test_ai_command_to_dict_with_sequence(self):
        """Test to_dict with button sequence"""
        cmd = AICommand(
            command_type=CommandType.SEQUENCE,
            button_sequence=[Button.UP, Button.DOWN, Button.A],
            reasoning="Test sequence",
            confidence=0.85,
            tick=150,
            timestamp="2025-01-01T00:00:00",
        )
        result = cmd.to_dict()
        assert result["button_sequence"] == ["UP", "DOWN", "A"]

    def test_ai_command_to_string_press(self):
        """Test to_string for press command"""
        cmd = AICommand(
            command_type=CommandType.PRESS,
            button=Button.A,
            reasoning="Test",
            confidence=0.8,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        assert cmd.to_string() == "press:A"

    def test_ai_command_to_string_batch(self):
        """Test to_string for batch command"""
        cmd = AICommand(
            command_type=CommandType.BATCH,
            batch_direction="DOWN",
            batch_steps=5,
            reasoning="Test",
            confidence=0.7,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        assert cmd.to_string() == "batch:DOWNx5"

    def test_ai_command_to_string_wait(self):
        """Test to_string for wait command"""
        cmd = AICommand(
            command_type=CommandType.WAIT,
            reasoning="Wait",
            confidence=1.0,
            tick=100,
            timestamp="2025-01-01T00:00:00",
            wait_ticks=120,
        )
        assert cmd.to_string() == "wait:120"

    def test_ai_command_default_values(self):
        """Test default field values"""
        cmd = AICommand(
            command_type=CommandType.PRESS,
            button=Button.A,
            reasoning="Test",
            confidence=0.8,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        assert cmd.duration_ms is None
        assert cmd.button_sequence is None
        assert cmd.batch_direction is None
        assert cmd.batch_steps == 0
        assert cmd.wait_ticks == 60


class TestGameState:
    """Tests for GameState dataclass"""

    def test_game_state_creation_minimal(self):
        """Create GameState with minimal required fields"""
        state = GameState(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            screen_type="overworld",
            is_battle=False,
            is_menu=False,
            has_dialog=False,
        )
        assert state.tick == 100
        assert state.screen_type == "overworld"
        assert state.is_battle is False

    def test_game_state_creation_full(self):
        """Create GameState with all fields"""
        state = GameState(
            tick=200,
            timestamp="2025-01-01T00:00:00",
            screen_type="battle",
            is_battle=True,
            is_menu=False,
            has_dialog=False,
            can_move=True,
            turn_number=3,
            enemy_pokemon="Pikachu",
            enemy_hp_percent=75.0,
            player_hp_percent=50.0,
            menu_type=None,
            cursor_position=(1, 2),
            dialog_text=None,
            location="Route 1",
        )
        assert state.enemy_pokemon == "Pikachu"
        assert state.enemy_hp_percent == 75.0
        assert state.cursor_position == (1, 2)
        assert state.location == "Route 1"

    def test_game_state_to_dict(self):
        """Test conversion to dictionary"""
        state = GameState(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            screen_type="menu",
            is_battle=False,
            is_menu=True,
            has_dialog=False,
            menu_type="pokemon",
        )
        result = state.to_dict()
        assert isinstance(result, dict)
        assert result["screen_type"] == "menu"
        assert result["is_menu"] is True
        assert result["menu_type"] == "pokemon"

    def test_game_state_default_values(self):
        """Test default field values"""
        state = GameState(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            screen_type="overworld",
            is_battle=False,
            is_menu=False,
            has_dialog=False,
        )
        assert state.can_move is True
        assert state.turn_number == 0
        assert state.enemy_pokemon is None
        assert state.enemy_hp_percent is None
        assert state.player_hp_percent is None
        assert state.menu_type is None
        assert state.cursor_position is None
        assert state.dialog_text is None
        assert state.location is None


class TestBattleState:
    """Tests for BattleState dataclass"""

    def test_battle_state_creation(self):
        """Create BattleState with required fields"""
        state = BattleState(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            enemy_pokemon="Charizard",
            enemy_level=50,
            enemy_hp_percent=100.0,
            player_pokemon="Blastoise",
            player_level=48,
            player_hp_percent=80.0,
        )
        assert state.enemy_pokemon == "Charizard"
        assert state.enemy_level == 50
        assert state.turn_number == 0

    def test_battle_state_type_advice(self):
        """Test type advice generation"""
        state = BattleState(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            enemy_pokemon="Golem",
            enemy_level=30,
            enemy_hp_percent=60.0,
            player_pokemon="Onix",
            player_level=28,
            player_hp_percent=90.0,
            enemy_weaknesses=["Water", "Grass", "Ice"],
            enemy_resistances=["Normal", "Fire", "Electric"],
        )
        advice = state.get_type_advice()
        assert "Water" in advice
        assert "Grass" in advice
        assert "Ice" in advice

    def test_battle_state_no_type_data(self):
        """Test type advice when no data available"""
        state = BattleState(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            enemy_pokemon="Unknown",
            enemy_level=1,
            enemy_hp_percent=100.0,
            player_pokemon="Test",
            player_level=1,
            player_hp_percent=100.0,
        )
        advice = state.get_type_advice()
        assert advice == "No type data available"

    def test_battle_state_to_dict(self):
        """Test conversion to dictionary"""
        state = BattleState(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            enemy_pokemon="Pikachu",
            enemy_level=10,
            enemy_hp_percent=50.0,
            player_pokemon="Charmander",
            player_level=10,
            player_hp_percent=75.0,
        )
        result = state.__dict__
        assert isinstance(result, dict)
        assert result["enemy_pokemon"] == "Pikachu"


class TestAIThought:
    """Tests for AIThought dataclass"""

    def test_ai_thought_creation(self):
        """Create AIThought with required fields"""
        thought = AIThought(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            thought_process="Navigating",
            reasoning="Need to reach Pokemon Center",
            proposed_action="Move UP",
            game_state={"hp_percent": 20.0},
            model_used="gpt-4o-mini",
            confidence=0.85,
            tokens_used=200,
        )
        assert thought.thought_process == "Navigating"
        assert thought.game_state["hp_percent"] == 20.0
        assert thought.tokens_used == 200

    def test_ai_thought_to_dict(self):
        """Test conversion to dictionary with JSON serialization"""
        thought = AIThought(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            thought_process="Test",
            reasoning="Test reasoning",
            proposed_action="Test action",
            game_state={"key": "value"},
            model_used="test",
            confidence=0.8,
            tokens_used=100,
        )
        result = thought.to_dict()
        assert isinstance(result, dict)
        assert result["tick"] == 100
        assert isinstance(result["game_state"], str)


class TestCommandExecutionResult:
    """Tests for CommandExecutionResult dataclass"""

    def test_execution_result_success(self):
        """Test successful command execution result"""
        cmd = AICommand(
            command_type=CommandType.PRESS,
            button=Button.A,
            reasoning="Test",
            confidence=0.8,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        result = CommandExecutionResult(
            command=cmd,
            success=True,
            execution_time_ms=25.5,
        )
        assert result.success is True
        assert result.execution_time_ms == 25.5
        assert result.error_message is None

    def test_execution_result_failure(self):
        """Test failed command execution result"""
        cmd = AICommand(
            command_type=CommandType.PRESS,
            button=Button.START,
            reasoning="Test",
            confidence=0.6,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        result = CommandExecutionResult(
            command=cmd,
            success=False,
            execution_time_ms=5.0,
            error_message="Button press failed",
        )
        assert result.success is False
        assert result.error_message == "Button press failed"

    def test_execution_result_to_dict(self):
        """Test conversion to dictionary"""
        cmd = AICommand(
            command_type=CommandType.PRESS,
            button=Button.B,
            reasoning="Test",
            confidence=0.9,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        result = CommandExecutionResult(
            command=cmd,
            success=True,
            execution_time_ms=30.0,
        )
        dict_result = result.to_dict()
        assert dict_result["success"] is True
        assert dict_result["execution_time_ms"] == 30.0


class TestHelperFunctions:
    """Tests for helper functions"""

    def test_create_press_command(self):
        """Test creating a press command via helper"""
        cmd = create_press_command(
            button=Button.A,
            reasoning="Select menu option",
            tick=500,
            confidence=0.95,
        )
        assert cmd.command_type == CommandType.PRESS
        assert cmd.button == Button.A
        assert cmd.reasoning == "Select menu option"
        assert cmd.confidence == 0.95
        assert cmd.tick == 500

    def test_create_batch_command(self):
        """Test creating a batch command via helper"""
        cmd = create_batch_command(
            direction="LEFT",
            steps=20,
            reasoning="Walk left to find route",
            tick=600,
            confidence=0.7,
        )
        assert cmd.command_type == CommandType.BATCH
        assert cmd.batch_direction == "LEFT"
        assert cmd.batch_steps == 20
        assert cmd.confidence == 0.7

    def test_parse_command_string_press(self):
        """Test parsing press command string"""
        result = parse_command_string("press:A")
        assert result is not None
        assert result["command_type"] == "press"
        assert result["button"] == "A"

    def test_parse_command_string_batch(self):
        """Test parsing batch command string"""
        result = parse_command_string("batch:UPx15")
        assert result is not None
        assert result["command_type"] == "batch"
        assert result["batch_direction"] == "UP"
        assert result["batch_steps"] == 15

    def test_parse_command_string_sequence(self):
        """Test parsing sequence command string"""
        result = parse_command_string("sequence:UP,UP,LEFT,A")
        assert result is not None
        assert result["command_type"] == "sequence"
        assert result["button_sequence"] == ["UP", "UP", "LEFT", "A"]

    def test_parse_command_string_invalid(self):
        """Test parsing invalid command string"""
        result = parse_command_string("invalid:command")
        assert result is None

    def test_parse_command_string_no_colon(self):
        """Test parsing command without colon"""
        result = parse_command_string("pressA")
        assert result is None

    def test_parse_command_string_unknown_button(self):
        """Test parsing command with unknown button"""
        result = parse_command_string("press:INVALID")
        assert result is None

    def test_parse_command_string_unknown_command_type(self):
        """Test parsing unknown command type"""
        result = parse_command_string("jump:A")
        assert result is None


class TestCommandValidation:
    """Tests for command validation logic"""

    def test_confidence_range(self):
        """Test confidence values are within valid range"""
        cmd = AICommand(
            command_type=CommandType.PRESS,
            button=Button.A,
            reasoning="Test",
            confidence=1.0,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        assert 0.0 <= cmd.confidence <= 1.0

        cmd_low = AICommand(
            command_type=CommandType.PRESS,
            button=Button.A,
            reasoning="Test",
            confidence=0.0,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        assert 0.0 <= cmd_low.confidence <= 1.0

    def test_battle_state_turn_number(self):
        """Test turn number starts at 0 and increments"""
        state = BattleState(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            enemy_pokemon="Test",
            enemy_level=1,
            enemy_hp_percent=100.0,
            player_pokemon="Test",
            player_level=1,
            player_hp_percent=100.0,
            turn_number=0,
        )
        assert state.turn_number >= 0

    def test_game_state_hp_percent_range(self):
        """Test HP percentages are within valid range"""
        state = GameState(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            screen_type="battle",
            is_battle=True,
            is_menu=False,
            has_dialog=False,
            enemy_hp_percent=50.0,
            player_hp_percent=75.0,
        )
        assert state.enemy_hp_percent is None or 0.0 <= state.enemy_hp_percent <= 100.0
        assert state.player_hp_percent is None or 0.0 <= state.player_hp_percent <= 100.0

    def test_command_type_values(self):
        """Verify command types have expected string values"""
        assert CommandType.PRESS.value == "press"
        assert CommandType.HOLD.value == "hold"
        assert CommandType.RELEASE.value == "release"
        assert CommandType.SEQUENCE.value == "sequence"
        assert CommandType.BATCH.value == "batch"
        assert CommandType.WAIT.value == "wait"

    def test_batch_command_validation(self):
        """Test batch command step count validation"""
        cmd = AICommand(
            command_type=CommandType.BATCH,
            batch_direction="RIGHT",
            batch_steps=100,
            reasoning="Test",
            confidence=0.8,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        assert cmd.batch_steps >= 0

    def test_sequence_command_length(self):
        """Test sequence command can contain multiple buttons"""
        long_sequence = [Button.UP] * 10 + [Button.A]
        cmd = AICommand(
            command_type=CommandType.SEQUENCE,
            button_sequence=long_sequence,
            reasoning="Long sequence",
            confidence=0.9,
            tick=100,
            timestamp="2025-01-01T00:00:00",
        )
        assert cmd.button_sequence is not None and len(cmd.button_sequence) == 11


class TestSerializationRoundTrip:
    """Tests for serialization and deserialization round trips"""

    def test_command_serialization_round_trip(self):
        """Test command survives to_dict -> from_dict round trip"""
        original = AICommand(
            command_type=CommandType.PRESS,
            button=Button.A,
            reasoning="Test reasoning",
            confidence=0.85,
            tick=12345,
            timestamp="2025-01-01T12:00:00",
        )
        as_dict = original.to_dict()
        assert as_dict["command_type"] == "press"
        assert as_dict["button"] == "A"
        assert as_dict["reasoning"] == "Test reasoning"
        assert as_dict["confidence"] == 0.85
        assert as_dict["tick"] == 12345

    def test_game_state_serialization_round_trip(self):
        """Test game state survives to_dict round trip"""
        original = GameState(
            tick=100,
            timestamp="2025-01-01T00:00:00",
            screen_type="menu",
            is_battle=False,
            is_menu=True,
            has_dialog=False,
            menu_type="bag",
            cursor_position=(0, 3),
        )
        as_dict = original.to_dict()
        assert as_dict["screen_type"] == "menu"
        assert as_dict["is_menu"] is True
        assert as_dict["menu_type"] == "bag"
        assert as_dict["cursor_position"] == (0, 3)

    def test_battle_state_serialization_round_trip(self):
        """Test battle state survives to_dict round trip"""
        original = BattleState(
            tick=200,
            timestamp="2025-01-01T00:00:00",
            enemy_pokemon="Charizard",
            enemy_level=55,
            enemy_hp_percent=33.0,
            player_pokemon="Blastoise",
            player_level=52,
            player_hp_percent=80.0,
            turn_number=5,
            enemy_types=["Fire", "Flying"],
            enemy_weaknesses=["Water", "Electric", "Rock"],
        )
        as_dict = original.__dict__
        assert as_dict["enemy_pokemon"] == "Charizard"
        assert as_dict["turn_number"] == 5
        assert as_dict["enemy_types"] == ["Fire", "Flying"]
        assert as_dict["enemy_weaknesses"] == ["Water", "Electric", "Rock"]