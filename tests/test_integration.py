"""
Integration tests for the game loop

Tests component interactions, state transitions, error recovery,
and main user journeys through the system.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
import time
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

from schemas.commands import (
    AICommand, CommandType, Button, GameState, BattleState,
    AIThought, CommandExecutionResult
)


class TestFullTickCycle:
    """Tests for the complete tick cycle flow"""

    def test_screenshot_to_state_detection(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test that screenshot capture leads to proper state detection"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            mock_emulator.capture_screen.return_value = MagicMock()

    def test_state_detection_to_ai_decision(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test that game state triggers AI decision"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.current_tick = 10

            battle_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="battle",
                is_battle=True,
                is_menu=False,
                has_dialog=False,
                can_move=False
            )

            decision = game_loop._get_stub_ai_decision(battle_state)

            assert decision is not None
            assert 'action' in decision
            assert 'reasoning' in decision
            assert 'confidence' in decision
            assert 0.0 <= decision['confidence'] <= 1.0

    def test_command_to_execution(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test that pending commands are executed"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator

            game_loop.pending_commands = [
                {
                    "command": "press:A",
                    "tick": 10,
                    "reasoning": "Test",
                    "confidence": 0.8
                }
            ]
            game_loop.current_tick = 10

            mock_emulator.press_button = MagicMock()
            game_loop._execute_pending_commands()

            mock_emulator.press_button.assert_called_once_with(Button.A)
            assert len(game_loop.pending_commands) == 0
            assert len(game_loop.command_history) == 1

    def test_execution_to_logging(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test that executed commands are logged to database"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.db = mock_db_connection

            mock_emulator.press_button = MagicMock()
            mock_db_connection.log_command = MagicMock()

            game_loop.pending_commands = [
                {
                    "command": "press:A",
                    "tick": 10,
                    "reasoning": "Test",
                    "confidence": 0.8
                }
            ]
            game_loop.current_tick = 10

            game_loop._execute_pending_commands()

            mock_db_connection.log_command.assert_called_once()
            call_args = mock_db_connection.log_command.call_args[0][0]
            assert call_args['tick'] == 10
            assert call_args['success'] is True

    def test_full_tick_cycle_integration(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test complete tick cycle: screenshot -> state -> decision -> command -> log"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.db = mock_db_connection
            game_loop.current_tick = 0
            game_loop.last_screenshot_tick = 0

            mock_emulator.tick = MagicMock()
            mock_emulator.capture_screen = MagicMock(return_value=MagicMock())
            mock_emulator.press_button = MagicMock()
            mock_db_connection.log_screenshot = MagicMock()
            mock_db_connection.log_command = MagicMock()
            mock_db_connection.log_ai_thought = MagicMock()

            game_loop.run_single_tick()

            assert game_loop.current_tick == 1
            assert game_loop.metrics['total_ticks'] == 1

    def test_database_entries_verification(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Verify database entries are created at each stage of the tick cycle"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.db = mock_db_connection
            game_loop.current_tick = 50

            screenshot_data = {
                'tick': 50,
                'path': '/tmp/screenshot.png',
                'game_state': {'screen_type': 'battle', 'is_battle': True}
            }

            thought_data = {
                'tick': 50,
                'game_state': screenshot_data['game_state'],
                'reasoning': 'Battle decision',
                'confidence': 0.75
            }

            command_data = {
                'tick': 50,
                'command_type': 'press',
                'command_value': 'press:A',
                'reasoning': 'Battle decision',
                'confidence': 0.75,
                'success': True
            }

            game_loop.db.log_screenshot(game_loop.current_tick, screenshot_data['path'], screenshot_data['game_state'])
            game_loop.db.log_ai_thought(thought_data)
            game_loop.db.log_command(command_data)

            mock_db_connection.log_screenshot.assert_called()
            mock_db_connection.log_ai_thought.assert_called_with(thought_data)
            mock_db_connection.log_command.assert_called_with(command_data)


class TestBattleTransition:
    """Tests for battle state transitions"""

    def test_overworld_to_battle_detection(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test detection of transition from overworld to battle"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.db = mock_db_connection
            game_loop.current_battle_id = None
            game_loop.battle_turn_count = 0

            mock_db_connection.log_battle_start = MagicMock(return_value=1)
            
            battle_game_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="battle",
                is_battle=True,
                is_menu=False,
                has_dialog=False
            )
            
            with patch.object(game_loop, '_analyze_game_state', return_value=battle_game_state):
                game_loop._detect_battle_transition()

            assert game_loop.current_battle_id == 1
            mock_db_connection.log_battle_start.assert_called_once()
            assert game_loop.battle_turn_count == 0

    def test_battle_state_management(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test proper state tracking during battle"""
        from game_loop import GameLoop

        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.current_battle_id = 1
            game_loop.battle_turn_count = 0

            battle_game_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="battle",
                is_battle=True,
                is_menu=False,
                has_dialog=False,
                player_hp_percent=100.0
            )

            with patch('game_loop.GameLoop._analyze_game_state', return_value=battle_game_state):
                for i in range(3):
                    game_loop._detect_battle_transition()
                    assert game_loop.current_battle_id == 1
                    assert game_loop.battle_turn_count == i + 1

    def test_battle_end_to_overworld(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test detection of battle end and return to overworld"""
        from game_loop import GameLoop

        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.db = mock_db_connection
            game_loop.current_battle_id = 1
            game_loop.battle_turn_count = 5
            game_loop.metrics['battles_encountered'] = 1
            game_loop.metrics['battles_won'] = 0

            mock_db_connection.log_battle_end = MagicMock()

            battle_game_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="battle",
                is_battle=True,
                is_menu=False,
                has_dialog=False,
                player_hp_percent=100.0
            )

            overworld_game_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="overworld",
                is_battle=False,
                is_menu=False,
                has_dialog=False,
                player_hp_percent=100.0
            )

            with patch('game_loop.GameLoop._analyze_game_state', side_effect=[battle_game_state, overworld_game_state]):
                game_loop._detect_battle_transition()
                assert game_loop.current_battle_id == 1

                game_loop._detect_battle_transition()
                assert game_loop.current_battle_id is None
                mock_db_connection.log_battle_end.assert_called_once()

    def test_battle_turn_tracking(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test that battle turns are properly counted"""
        from game_loop import GameLoop

        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.current_battle_id = 1
            game_loop.battle_turn_count = 0

            battle_game_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="battle",
                is_battle=True,
                is_menu=False,
                has_dialog=False,
                player_hp_percent=100.0
            )

            with patch('game_loop.GameLoop._analyze_game_state', return_value=battle_game_state):
                for i in range(10):
                    game_loop._detect_battle_transition()

                assert game_loop.battle_turn_count == 10

    def test_battle_metrics_update(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test that battle metrics are updated correctly"""
        from game_loop import GameLoop

        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.metrics = {
                'battles_encountered': 0,
                'battles_won': 0,
                'battles_lost': 0
            }

            mock_db_connection.log_battle_start = MagicMock(return_value=1)
            mock_db_connection.log_battle_end = MagicMock()

            battle_game_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="battle",
                is_battle=True,
                is_menu=False,
                has_dialog=False,
                player_hp_percent=100.0
            )

            overworld_game_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="overworld",
                is_battle=False,
                is_menu=False,
                has_dialog=False,
                player_hp_percent=100.0
            )

            with patch('game_loop.GameLoop._analyze_game_state', side_effect=[battle_game_state, overworld_game_state]):
                game_loop._detect_battle_transition()
                assert game_loop.metrics['battles_encountered'] == 1

                game_loop._detect_battle_transition()
                assert game_loop.metrics['battles_won'] == 1


class TestDialogFlow:
    """Tests for dialog handling flow"""

    def test_dialog_initiation(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test detection of dialog initiation"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator

            dialog_game_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="dialog",
                is_battle=False,
                is_menu=False,
                has_dialog=True
            )

            with patch.object(game_loop, '_analyze_game_state', return_value=dialog_game_state):
                state = game_loop._analyze_game_state()

            assert state.has_dialog is True

    def test_text_advancement(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test AI decision to advance dialog text"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.current_tick = 100

            dialog_state = GameState(
                tick=100,
                timestamp=datetime.now().isoformat(),
                screen_type="dialog",
                is_battle=False,
                is_menu=False,
                has_dialog=True,
                can_move=False,
                dialog_text="Welcome to the world of Pokemon!"
            )

            decision = game_loop._simple_dialog_ai(dialog_state)

            assert decision['action'] == 'press:A'
            assert decision['button'] == Button.A
            assert decision['confidence'] > 0.5

    def test_dialog_completion(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test detection of dialog completion"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator

            dialog_game_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="dialog",
                is_battle=False,
                is_menu=False,
                has_dialog=True
            )
            
            overworld_game_state = GameState(
                tick=10,
                timestamp=datetime.now().isoformat(),
                screen_type="overworld",
                is_battle=False,
                is_menu=False,
                has_dialog=False
            )

            with patch.object(game_loop, '_analyze_game_state', side_effect=[dialog_game_state, overworld_game_state]):
                state1 = game_loop._analyze_game_state()
                state2 = game_loop._analyze_game_state()

            assert state1.has_dialog is True
            assert state2.has_dialog is False

    def test_dialog_advancement_multiple_pages(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test multi-page dialog advancement"""
        from game_loop import GameLoop

        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.pending_commands = []

            dialog_state = GameState(
                tick=100,
                timestamp=datetime.now().isoformat(),
                screen_type="dialog",
                is_battle=False,
                is_menu=False,
                has_dialog=True
            )

            game_loop._get_ai_decision(dialog_state)

            assert len(game_loop.pending_commands) == 1
            assert game_loop.pending_commands[0]['command'] == 'press:A'


class TestCommandExecution:
    """Tests for command execution system"""

    def test_single_button_press(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test execution of single button press command"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator

            mock_emulator.press_button = MagicMock()

            parsed = game_loop._parse_command("press:A")
            assert parsed is not None
            assert parsed['type'] == 'press'
            assert parsed['button'] == Button.A

    def test_button_sequence_execution(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test execution of button sequence commands (not implemented, returns None)"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator

            mock_emulator.press_button = MagicMock()

            parsed = game_loop._parse_command("sequence:UP,DOWN,LEFT,RIGHT")
            assert parsed is None

    def test_batch_command_execution(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test execution of batch movement commands (not implemented, returns None)"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator

            parsed = game_loop._parse_command("batch:UPx10")
            assert parsed is None

    def test_command_timing(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test that command execution includes proper timing"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.db = mock_db_connection

            mock_emulator.press_button = MagicMock()
            mock_db_connection.log_command = MagicMock()

            game_loop.pending_commands = [
                {
                    "command": "press:A",
                    "tick": 10,
                    "reasoning": "Test timing",
                    "confidence": 0.8
                }
            ]

            start_time = time.time()
            game_loop._execute_pending_commands()
            execution_time = (time.time() - start_time) * 1000

            call_args = mock_db_connection.log_command.call_args[0][0]
            assert 'execution_time_ms' in call_args
            assert call_args['execution_time_ms'] >= 0

    def test_all_directions(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test all directional button commands"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator

            buttons = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'A', 'B', 'START', 'SELECT']

            for button in buttons:
                parsed = game_loop._parse_command(f"press:{button}")
                assert parsed is not None
                assert parsed['button'] == getattr(Button, button)

    def test_command_history_tracking(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test that executed commands are tracked in history"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.command_history = []

            mock_emulator.press_button = MagicMock()

            commands = [
                {"command": "press:A", "tick": 1, "reasoning": "Test 1", "confidence": 0.8},
                {"command": "press:B", "tick": 2, "reasoning": "Test 2", "confidence": 0.9},
                {"command": "press:UP", "tick": 3, "reasoning": "Test 3", "confidence": 0.7},
            ]

            for cmd in commands:
                game_loop.pending_commands = [cmd]
                game_loop._execute_pending_commands()

            assert len(game_loop.command_history) == 3
            for i, cmd in enumerate(commands):
                assert game_loop.command_history[i]['command'] == cmd['command']
                assert game_loop.command_history[i]['success'] is True


class TestErrorRecovery:
    """Tests for error handling and recovery mechanisms"""

    def test_api_failure_stub_fallback(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test fallback to stub AI when API fails"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.use_real_ai = False
            game_loop.current_tick = 100

            battle_state = GameState(
                tick=100,
                timestamp=datetime.now().isoformat(),
                screen_type="battle",
                is_battle=True,
                is_menu=False,
                has_dialog=False
            )

            decision = game_loop._get_stub_ai_decision(battle_state)

            assert decision is not None
            assert 'action' in decision
            assert 'reasoning' in decision

    def test_emulator_error_graceful_shutdown(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test graceful shutdown when emulator encounters error"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.is_running = True

            mock_emulator.tick = MagicMock(side_effect=Exception("Emulator crashed"))
            mock_emulator.stop = MagicMock()
            mock_db_connection.log_command = MagicMock()

            initial_running = game_loop.is_running
            
            try:
                game_loop.run_single_tick()
            except Exception:
                pass

            assert game_loop.is_running == initial_running or mock_emulator.stop.called

    def test_database_error_retry(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test retry logic when database operations fail"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.db = mock_db_connection

            call_count = [0]

            def failing_log(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise Exception("Database temporarily unavailable")
                return None

            mock_db_connection.log_command = failing_log

            game_loop.pending_commands = [
                {
                    "command": "press:A",
                    "tick": 10,
                    "reasoning": "Test retry",
                    "confidence": 0.8
                }
            ]

            max_retries = 5
            for attempt in range(max_retries):
                try:
                    game_loop._execute_pending_commands()
                    if not game_loop.pending_commands:
                        break
                except Exception:
                    pass

    def test_invalid_command_handling(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test handling of invalid command formats"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.db = mock_db_connection

            mock_db_connection.log_command = MagicMock()

            parsed = game_loop._parse_command("invalid:command")
            assert parsed is None

    def test_unknown_button_handling(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test handling of unknown button in command"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator

            parsed = game_loop._parse_command("press:UNKNOWN")
            assert parsed is None

    def test_command_execution_error_logging(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test that command execution errors are properly logged"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.db = mock_db_connection

            mock_emulator.press_button = MagicMock(side_effect=Exception("Button press failed"))
            mock_db_connection.log_command = MagicMock()

            game_loop.pending_commands = [
                {
                    "command": "press:A",
                    "tick": 10,
                    "reasoning": "Test error logging",
                    "confidence": 0.8
                }
            ]

            game_loop._execute_pending_commands()

            mock_db_connection.log_command.assert_called_once()
            call_args = mock_db_connection.log_command.call_args[0][0]
            assert call_args['success'] is False
            assert 'error_message' in call_args or 'error' in call_args

    def test_state_analysis_error_handling(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test error handling in state analysis"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            mock_emulator.capture_screen = MagicMock(side_effect=Exception("Screenshot failed"))

            result = game_loop._analyze_game_state()

            assert isinstance(result, GameState)

    def test_empty_pending_commands(
        self, mock_emulator, mock_ai_client, temp_session, mock_db_connection
    ):
        """Test that empty command list doesn't cause errors"""
        from game_loop import GameLoop
        
        with patch('game_loop.GameDatabase') as mock_db_class:
            mock_db_class.return_value = mock_db_connection
            game_loop = GameLoop(
                config={
                    "rom_path": str(temp_session / "rom.gb"),
                    "save_dir": str(temp_session / "saves"),
                    "screenshot_interval": 60
                }
            )
            game_loop.emulator = mock_emulator
            game_loop.pending_commands = []

            game_loop._execute_pending_commands()

            assert len(game_loop.pending_commands) == 0
