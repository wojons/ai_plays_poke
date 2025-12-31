"""
Pytest configuration and fixtures for PTP-01X Pokemon AI tests

Provides reusable mock objects and test utilities for unit and integration tests.
"""

import pytest
import tempfile
import os
from unittest.mock import MagicMock, Mock
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

from src.schemas.commands import (
    AICommand,
    CommandType,
    Button,
    GameState,
    BattleState,
    AIThought,
    CommandExecutionResult,
)


@pytest.fixture
def mock_emulator():
    """Mock PyBoy emulator state"""
    emulator = MagicMock()
    emulator.tick_count = 100
    emulator.is_running = True
    emulator.current_screen = MagicMock()
    emulator.current_screen.ndarray = b"\x00" * (160 * 144 * 3)
    emulator.memory = MagicMock()
    emulator.memory[0xFF40] = 0x10
    emulator.save_state.return_value = b"mock_save_state_data"
    emulator.load_state.return_value = True
    return emulator


@pytest.fixture
def mock_ai_client():
    """Mock AI client responses"""
    client = MagicMock()
    client.generate_decision.return_value = {
        "command": "press:A",
        "reasoning": "Test action",
        "confidence": 0.85,
    }
    client.get_completion.return_value = "Test completion"
    client.get_cost.return_value = 0.001
    client.get_tokens.return_value = {"input": 100, "output": 50}
    return client


@pytest.fixture
def mock_game_state() -> Dict[str, Any]:
    """Mock game state data"""
    return {
        "tick": 100,
        "timestamp": datetime.now().isoformat(),
        "screen_type": "overworld",
        "is_battle": False,
        "is_menu": False,
        "has_dialog": False,
        "can_move": True,
        "turn_number": 0,
        "enemy_pokemon": None,
        "enemy_hp_percent": None,
        "player_hp_percent": None,
        "menu_type": None,
        "cursor_position": None,
        "dialog_text": None,
        "location": "Pallet Town",
    }


@pytest.fixture
def sample_screenshot():
    """Pre-captured screenshot fixture (mock image data)"""
    import numpy as np
    return np.zeros((144, 160, 3), dtype=np.uint8)


@pytest.fixture
def temp_session(tmp_path):
    """Temporary session directory with proper structure"""
    session_dir = tmp_path / "session_001"
    session_dir.mkdir()
    (session_dir / "screenshots").mkdir()
    (session_dir / "logs").mkdir()
    (session_dir / "states").mkdir()
    return session_dir


@pytest.fixture
def sample_ai_command():
    """Sample AI command for testing"""
    return AICommand(
        command_type=CommandType.PRESS,
        button=Button.A,
        reasoning="Press A to select option",
        confidence=0.85,
        tick=100,
        timestamp=datetime.now().isoformat(),
    )


@pytest.fixture
def sample_batch_command():
    """Sample batch command for testing"""
    return AICommand(
        command_type=CommandType.BATCH,
        batch_direction="UP",
        batch_steps=10,
        reasoning="Move up 10 steps",
        confidence=0.75,
        tick=101,
        timestamp=datetime.now().isoformat(),
    )


@pytest.fixture
def sample_sequence_command():
    """Sample sequence command for testing"""
    return AICommand(
        command_type=CommandType.SEQUENCE,
        button_sequence=[Button.UP, Button.UP, Button.LEFT, Button.A],
        reasoning="Navigate menu",
        confidence=0.90,
        tick=102,
        timestamp=datetime.now().isoformat(),
    )


@pytest.fixture
def sample_game_state():
    """Sample game state for testing"""
    return GameState(
        tick=100,
        timestamp=datetime.now().isoformat(),
        screen_type="overworld",
        is_battle=False,
        is_menu=False,
        has_dialog=False,
        can_move=True,
        turn_number=0,
        enemy_pokemon=None,
        enemy_hp_percent=None,
        player_hp_percent=None,
        menu_type=None,
        cursor_position=None,
        dialog_text=None,
        location="Pallet Town",
    )


@pytest.fixture
def sample_battle_state():
    """Sample battle state for testing"""
    return BattleState(
        tick=200,
        timestamp=datetime.now().isoformat(),
        enemy_pokemon="Pikachu",
        enemy_level=15,
        enemy_hp_percent=75.0,
        player_pokemon="Charmander",
        player_level=12,
        player_hp_percent=60.0,
        battle_id=1,
        enemy_types=["Electric"],
        enemy_weaknesses=["Ground"],
        enemy_resistances=["Flying"],
        turn_number=3,
        available_moves=["Scratch", "Ember", "Growl", "Leer"],
    )


@pytest.fixture
def sample_ai_thought():
    """Sample AI thought for testing"""
    return AIThought(
        tick=100,
        timestamp=datetime.now().isoformat(),
        thought_process="Navigating to Pokemon Center",
        reasoning="Player Pokemon health is low, need to heal",
        proposed_action="Move UP 10 steps then press A",
        game_state={"location": "Route 1", "player_hp_percent": 25.0},
        model_used="gpt-4o-mini",
        confidence=0.82,
        tokens_used=150,
    )


@pytest.fixture
def sample_command_execution_result(sample_ai_command, sample_game_state):
    """Sample command execution result for testing"""
    return CommandExecutionResult(
        command=sample_ai_command,
        success=True,
        execution_time_ms=50.0,
        error_message=None,
        game_state_after=sample_game_state,
    )


@pytest.fixture
def mock_db_connection():
    """Mock database connection"""
    db = MagicMock()
    db.execute.return_value = None
    db.commit.return_value = None
    db.fetchone.return_value = None
    db.fetchall.return_value = []
    db.close.return_value = None
    return db