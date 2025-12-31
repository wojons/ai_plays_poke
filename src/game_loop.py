#!/usr/bin/env python3
"""
AI Plays Pokemon - Main CLI Entry Point

Main game loop coordinator that handles:
- CLI argument parsing
- Emulator management
- AI command processing
- Screenshot capture
- Database logging
- performance tracking
"""

import argparse
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np

from db.database import GameDatabase
from core.emulator import EmulatorInterface, EmulatorManager, Button
from core.screenshots import ScreenshotManager, SimpleLiveView
from core.ai_client import GameAIManager, OpenRouterClient
from schemas.commands import (
    AICommand, AIThought, GameState, 
    create_press_command, CommandType
)


class GameLoop:
    """
    Main game loop coordinator
    
    Manages the flow:
    Screenshot → AI Decision → Command → Execute → Log → Repeat
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize game loop with configuration
        
        Args:
            config: Configuration dictionary with settings
        """
        self.config = config
        
        # Initialize components
        rom_path = config["rom_path"]
        
        # Single emulator mode
        if config.get("multi_instance", False):
            count = config.get("instance_count", 3)
            self.emulator_mgr = EmulatorManager(rom_path, count)
            self.current_instance = f"instance_0"
        else:
            self.emulator_mgr = None
            self.emulator = EmulatorInterface(rom_path)
        
        # Database
        db_path = Path(config["save_dir"]) / "game_data.db"
        self.db = GameDatabase(str(db_path))
        
        # Screenshot manager
        screenshot_dir = Path(config["save_dir"]) / "screenshots"
        self.screenshot_mgr = ScreenshotManager(str(screenshot_dir))
        
        # Live view
        self.live_view = SimpleLiveView(self.screenshot_mgr)
        
        # AI Manager (with fallback to stub mode)
        try:
            self.ai_manager = GameAIManager()
            self.use_real_ai = True
            print("✅ AI Manager initialized with OpenRouter API")
        except ValueError:
            # No API key available, use stub mode
            self.ai_manager = None
            self.use_real_ai = False
            print("⚠️  No OpenRouter API key found. Using stub AI mode")
        
        # State tracking
        self.current_tick = 0
        self.last_screenshot_tick = 0
        self.is_running = False
        self.paused = False
        self.session_id = None
        
        # Command pipeline
        self.pending_commands: list = []
        self.command_history: list = []
        
        # Current battle tracking
        self.current_battle_id: Optional[int] = None
        self.battle_turn_count = 0
        
        # Metrics
        self.metrics = {
            "total_ticks": 0,
            "screenshots_taken": 0,
            "commands_sent": 0,
            "ai_decisions": 0,
            "battles_encountered": 0,
            "battles_won": 0,
            "battles_lost": 0,
            "start_time": None
        }
    
    def start(self):
        """Start the game loop"""
        rom_name = Path(self.config["rom_path"]).name
        save_dir = Path(self.config["save_dir"])
        
        print(f"🎮 AI Plays Pokemon - Starting...")
        print(f"📁 ROM: {rom_name}")
        print(f"💾 Save Directory: {save_dir}")
        print(f"📊 Database: {save_dir}/game_data.db")
        print(f"📸 Screenshots: {save_dir}/screenshots/")
        print()
        
        # Start emulator(s)
        if self.emulator_mgr:
            self.emulator_mgr.start_all()
            emulator = self.emulator_mgr.get_instance(self.current_instance)
        else:
            self.emulator.start()
            emulator = self.emulator
        
        # Start database session
        self.session_id = self.db.start_session(
            rom_path=str(self.config["rom_path"]),
            model_name=self.config.get("model_name", "stub_ai")
        )
        
        self.is_running = True
        self.metrics["start_time"] = datetime.now()
        
        print("✅ System initialized. Beginning game loop...")
        print("Press Ctrl+C to stop gracefully")
        print()
    
    def stop(self):
        """Stop the game loop and save all state"""
        if not self.is_running:
            return
        
        print("\n🛑 Stopping game loop gracefully...")
        
        # Save emulator state
        save_path = Path(self.config["save_dir"]) / "emulator_state.state"
        if self.emulator_mgr:
            emulator = self.emulator_mgr.get_instance(self.current_instance)
            emulator.save_state(str(save_path))
        else:
            self.emulator.save_state(str(save_path))
        print(f"💾 Emulator state saved to {save_path}")
        
        # End database session with final metrics
        final_metrics = {
            **self.metrics,
            "final_state": {"final_tick": self.current_tick}
        }
        self.db.end_session(final_metrics)
        
        # Export session data for analysis
        export_path = self.db.export_session_data(self.session_id)
        print(f"📊 Session data exported to {export_path}")
        
        self.is_running = False
        
        # Stop emulator(s)
        if self.emulator_mgr:
            self.emulator_mgr.stop_all()
        else:
            self.emulator.stop()
        
        # Print final stats
        self._print_final_stats()
    
    def _print_final_stats(self):
        """Print final statistics"""
        print()
        print(f"📊 Final Statistics:")
        print(f"   Session ID: {self.session_id}")
        print(f"   Total Ticks: {self.metrics['total_ticks']}")
        print(f"   Screenshots: {self.metrics['screenshots_taken']}")
        print(f"   Commands Sent: {self.metrics['commands_sent']}")
        print(f"   AI Decisions: {self.metrics['ai_decisions']}")
        print(f"   Battles: {self.metrics['battles_encountered']}")
        print(f"   Wins: {self.metrics['battles_won']}")
        print(f"   Losses: {self.metrics['battles_lost']}")
        
        if self.metrics["start_time"]:
            duration = (datetime.now() - self.metrics["start_time"]).total_seconds()
            print(f"   Duration: {duration:.1f} seconds")
    
    def run_single_tick(self):
        """Execute one iteration of the game loop"""
        self.current_tick += 1
        self.metrics["total_ticks"] += 1
        
        # Tick emulator
        if self.emulator_mgr:
            emulator = self.emulator_mgr.get_instance(self.current_instance)
            emulator.tick()
        else:
            self.emulator.tick()
        
        # Check if should take screenshot
        screenshot_interval = self.config.get("screenshot_interval", 60)
        if self.current_tick - self.last_screenshot_tick >= screenshot_interval:
            self._capture_and_process_screenshot()
            self.last_screenshot_tick = self.current_tick
        
        # Execute pending AI commands
        if self.pending_commands:
            self._execute_pending_commands()
        
        # Check for battle state transition
        self._detect_battle_transition()
    
    def _capture_and_process_screenshot(self):
        """Capture screenshot, analyze, and trigger AI if needed"""
        # Get emulator
        if self.emulator_mgr:
            emulator = self.emulator_mgr.get_instance(self.current_instance)
            screenshot = emulator.capture_screen()
        else:
            screenshot = self.emulator.capture_screen()
        
        # Save screenshot
        game_state = self._analyze_game_state()
        
        screenshot_path = self.screenshot_mgr.save_screenshot(
            screenshot,
            "screenshot",
            state_type=game_state.screen_type,
            tick=self.current_tick
        )
        
        self.metrics["screenshots_taken"] += 1
        self.live_view.should_display = True  # For screenshot manager tracking
        self.live_view.current_image = screenshot
        
        # Log to database
        self.db.log_screenshot(
            self.current_tick,
            str(screenshot_path),
            game_state.to_dict()
        )
        
        # Trigger AI decision if game state requires it
        if game_state.is_battle or game_state.is_menu or game_state.has_dialog:
            self._get_ai_decision(game_state)
    
    def _analyze_game_state(self) -> GameState:
        """
        Analyze current game state using vision processing
        
        Uses real AI vision analysis when available, falls back to stub logic
        """
        # Start with default game state
        game_state = GameState(
            tick=self.current_tick,
            timestamp=datetime.now().isoformat(),
            screen_type="overworld",
            is_battle=False,
            is_menu=False,
            has_dialog=False,
            can_move=True,
            turn_number=self.battle_turn_count,
            player_hp_percent=100.0,
            enemy_hp_percent=100.0
        )
        
        # Capture current screenshot for vision analysis
        try:
            # Get screenshot from emulator
            if self.emulator_mgr:
                emulator = self.emulator_mgr.get_instance(self.current_instance)
                screenshot = emulator.capture_screen()
            else:
                screenshot = self.emulator.capture_screen()
            
            # Use real vision analysis if available
            if self.use_real_ai and self.ai_manager and screenshot is not None:
                print(f"👀 Analyzing screenshot with AI vision...")
                vision_result = self.ai_manager.analyze_screenshot(screenshot)
                
                # Extract game state from vision analysis
                game_state.screen_type = vision_result.get("screen_type", "overworld")
                game_state.enemy_pokemon = vision_result.get("enemy_pokemon")
                game_state.player_hp_percent = vision_result.get("player_hp", 100.0)
                game_state.enemy_hp_percent = vision_result.get("enemy_hp", 100.0)
                
                # Set flags based on screen type
                if game_state.screen_type == "battle":
                    game_state.is_battle = True
                elif game_state.screen_type == "menu":
                    game_state.is_menu = True
                elif game_state.screen_type == "dialog":
                    game_state.has_dialog = True
                    
                print(f"✅ Vision analysis: {game_state.screen_type}, "
                      f"HP({game_state.player_hp_percent:.0f}%, {game_state.enemy_hp_percent:.0f}%)")
                
            else:
                # Fallback to stub logic for now
                game_state = self._analyze_game_state_stub(game_state)
                
        except Exception as e:
            print(f"⚠️  Vision analysis failed: {e}, using stub logic")
            game_state = self._analyze_game_state_stub(game_state)
        
        return game_state
    
    def _analyze_game_state_stub(self, game_state: GameState) -> GameState:
        """
        Stub game state analysis (original implementation)
        
        Args:
            game_state: Game state to update
            
        Returns:
            Updated game state with simulated detection
        """
        # Simple state detection based on tick ranges (for testing)
        
        # Simulate battle state at certain tick ranges
        if 100 < self.current_tick < 150:
            game_state.screen_type = "battle"
            game_state.is_battle = True
            game_state.enemy_pokemon = "Pidgey"
            game_state.player_hp_percent = 85.0
            game_state.enemy_hp_percent = 100.0
        
        # Simulate menu state
        elif 200 < self.current_tick < 220:
            game_state.screen_type = "menu"
            game_state.is_menu = True
            game_state.menu_type = "main"
        
        # Simulate dialog
        elif 300 < self.current_tick < 310:
            game_state.screen_type = "dialog"
            game_state.has_dialog = True
            game_state.dialog_text = "Welcome to the world of Pokemon!"
        
        return game_state
    
    def _get_ai_decision(self, game_state: GameState):
        """
        Get AI decision based on game state
        
        Uses real AI (OpenRouter) when available, falls back to stub AI otherwise
        """
        print(f"🤔 AI decision needed at tick {self.current_tick} ({game_state.screen_type})")
        self.metrics["ai_decisions"] += 1
        
        # Check if we should use real AI or stub
        if self.use_real_ai and self.ai_manager:
            command = self._get_real_ai_decision(game_state)
            model_used = "openrouter_ai"
            tokens_used = 0  # TODO: Track actual tokens
        else:
            command = self._get_stub_ai_decision(game_state)
            model_used = "stub_ai"
            tokens_used = 0
        
        # Log AI thought process
        thought = AIThought(
            tick=self.current_tick,
            timestamp=datetime.now().isoformat(),
            thought_process="Processing current game state",
            reasoning=command["reasoning"],
            proposed_action=command["action"],
            game_state=game_state.to_dict(),
            model_used=model_used,
            confidence=command["confidence"],
            tokens_used=tokens_used
        )
        
        self.db.log_ai_thought(thought.to_dict())
        
        # Add to command pipeline
        self.pending_commands.append({
            "tick": self.current_tick,
            "command": command["action"],
            "reasoning": command["reasoning"],
            "confidence": command["confidence"],
            "button": command.get("button")
        })
        
        print(f"✅ AI decision ({model_used}): {command['action']} - {command['reasoning']}")
    
    def _get_real_ai_decision(self, game_state: GameState) -> Dict[str, Any]:
        """
        Get real AI decision using OpenRouter models
        
        Args:
            game_state: Current game state
            
        Returns:
            Command dictionary with action, reasoning, and confidence
        """
        try:
            # For now, use simple AI analysis - this will be enhanced later
            if game_state.is_battle:
                # Use vision model if available
                return self._analyze_battle_with_ai(game_state)
            elif game_state.is_menu:
                return self._analyze_menu_with_ai(game_state)
            elif game_state.has_dialog:
                return self._analyze_dialog_with_ai(game_state)
            else:
                return self._analyze_overworld_with_ai(game_state)
                
        except Exception as e:
            print(f"❌ Real AI decision failed: {e}, falling back to stub")
            return self._get_stub_ai_decision(game_state)
    
    def _get_stub_ai_decision(self, game_state: GameState) -> Dict[str, Any]:
        """
        Get stub AI decision (original simple implementation)
        
        Args:
            game_state: Current game state
            
        Returns:
            Command dictionary with action, reasoning, and confidence
        """
        if game_state.is_battle:
            return self._simple_battle_ai(game_state)
        elif game_state.is_menu:
            return self._simple_menu_ai(game_state)
        elif game_state.has_dialog:
            return self._simple_dialog_ai(game_state)
        else:
            return self._simple_exploration_ai(game_state)
    
    def _analyze_battle_with_ai(self, game_state: GameState) -> Dict[str, Any]:
        """Analyze battle state with AI (placeholder for now)"""
        # TODO: Integrate with AI vision for battle analysis
        return {
            "action": "press:A",
            "button": Button.A,
            "reasoning": "AI battle analysis - default action",
            "confidence": 0.6
        }
    
    def _analyze_menu_with_ai(self, game_state: GameState) -> Dict[str, Any]:
        """Analyze menu state with AI (placeholder for now)"""
        # TODO: Integrate with AI vision for menu analysis
        return {
            "action": "press:DOWN",
            "button": Button.DOWN,
            "reasoning": "AI menu analysis - navigate cursor",
            "confidence": 0.5
        }
    
    def _analyze_dialog_with_ai(self, game_state: GameState) -> Dict[str, Any]:
        """Analyze dialog state with AI (placeholder for now)"""
        # TODO: Integrate with AI vision for dialog analysis
        return {
            "action": "press:A",
            "button": Button.A,
            "reasoning": "AI dialog analysis - advance text",
            "confidence": 0.9
        }
    
    def _analyze_overworld_with_ai(self, game_state: GameState) -> Dict[str, Any]:
        """Analyze overworld state with AI (placeholder for now)"""
        # TODO: Integrate with AI vision for exploration
        return {
            "action": "press:UP",
            "button": Button.UP,
            "reasoning": "AI overworld analysis - explore",
            "confidence": 0.4
        }
    
    def _simple_battle_ai(self, game_state: GameState) -> Dict[str, Any]:
        """Simple battle heuristic (stub)"""
        return {
            "action": "press:A",
            "button": Button.A,
            "reasoning": "In battle, press A to select default move",
            "confidence": 0.6
        }
    
    def _simple_menu_ai(self, game_state: GameState) -> Dict[str, Any]:
        """Simple menu navigation"""
        return {
            "action": "press:DOWN",
            "button": Button.DOWN,
            "reasoning": "In menu, move cursor down",
            "confidence": 0.5
        }
    
    def _simple_dialog_ai(self, game_state: GameState) -> Dict[str, Any]:
        """Simple dialog handling"""
        return {
            "action": "press:A",
            "button": Button.A,
            "reasoning": "Advance dialog text",
            "confidence": 0.9
        }
    
    def _simple_exploration_ai(self, game_state: GameState) -> Dict[str, Any]:
        """Simple exploration"""
        return {
            "action": "press:UP",
            "button": Button.UP,
            "reasoning": "Exploring, move north",
            "confidence": 0.4
        }
    
    def _execute_pending_commands(self):
        """Execute commands waiting in pipeline"""
        if not self.pending_commands:
            return
        
        command = self.pending_commands.pop(0)
        
        try:
            # Parse command (format: "press:A" or similar)
            parsed = self._parse_command(command["command"])
            if not parsed:
                raise ValueError(f"Invalid command format: {command['command']}")
            
            # Get emulator
            if self.emulator_mgr:
                emulator = self.emulator_mgr.get_instance(self.current_instance)
            else:
                emulator = self.emulator
            
            # Execute
            start_time = time.time()
            
            if parsed["type"] == "press" and parsed.get("button"):
                button = parsed["button"]
                emulator.press_button(button)
            else:
                # Handle other command types later
                print(f"⚠️  Command type not implemented: {parsed['type']}")
            
            execution_time = (time.time() - start_time) * 1000  # Convert to ms
            
            # Log executed command
            self.command_history.append({
                **command,
                "executed_at": datetime.now().isoformat(),
                "success": True,
                "execution_time_ms": execution_time
            })
            
            self.metrics["commands_sent"] += 1
            
            self.db.log_command({
                "tick": command["tick"],
                "command_type": parsed.get("type", "unknown"),
                "command_value": command["command"],
                "reasoning": command["reasoning"],
                "confidence": command["confidence"],
                "success": True,
                "execution_time_ms": execution_time
            })
            
            print(f"⏎ Executed: {command['command']}")
            
        except Exception as e:
            print(f"❌ Command execution failed: {e}")
            self.db.log_command({
                "tick": command["tick"],
                "command_type": "error",
                "command_value": command.get("command", "unknown"),
                "reasoning": command.get("reasoning", ""),
                "confidence": command["confidence"],
                "success": False,
                "error_message": str(e),
                "execution_time_ms": 0
            })
    
    def _parse_command(self, command_str: str) -> Optional[Dict[str, Any]]:
        """Parse command string to components"""
        parts = command_str.split(":")
        if len(parts) != 2:
            return None
        
        command_type, params = parts
        
        if command_type == "press":
            button_map = {
                "A": Button.A, "B": Button.B, "START": Button.START,
                "SELECT": Button.SELECT, "UP": Button.UP, "DOWN": Button.DOWN,
                "LEFT": Button.LEFT, "RIGHT": Button.RIGHT
            }
            if params.upper() in button_map:
                return {"type": "press", "button": button_map[params.upper()]}
        
        return None
    
    def _detect_battle_transition(self):
        """Detect when battle starts/ends and log accordingly"""
        # Simple check: if in battle state
        game_state = self._analyze_game_state()
        
        if game_state.is_battle and self.current_battle_id is None:
            # Battle started
            self.current_battle_id = self.db.log_battle_start({
                "tick": self.current_tick,
                "enemy_pokemon": game_state.enemy_pokemon or "Unknown",
                "enemy_level": 5,
                "player_pokemon": "Starter",
                "player_level": 5
            })
            self.metrics["battles_encountered"] += 1
            self.battle_turn_count = 0
            print("⚔️ Battle started!")
            
        elif not game_state.is_battle and self.current_battle_id is not None:
            # Battle ended
            # For now, assume victory if survived
            outcome = "victory" if game_state.player_hp_percent > 0 else "defeat"
            self.db.log_battle_end(self.current_battle_id, outcome, self.battle_turn_count)
            
            if outcome == "victory":
                self.metrics["battles_won"] += 1
            else:
                self.metrics["battles_lost"] += 1
            
            print(f"🏁 Battle ended! Result: {outcome}")
            
            self.current_battle_id = None
            self.battle_turn_count = 0


def create_config(args) -> Dict[str, Any]:
    """Create configuration from CLI arguments"""
    return {
        "rom_path": args.rom,
        "save_dir": args.save_dir,
        "screenshot_interval": args.screenshot_interval,
        "load_state": args.load_state,
        "max_ticks": args.max_ticks,
        "model_name": "stub_ai",  # Will be replaced with real AI
        "multi_instance": args.multi_instance,
        "instance_count": args.instances
    }


def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(
        description="AI Plays Pokemon - Orchestrated Intelligence Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic run
  python game_loop.py --rom pokemon_red.gb --save-dir ./my_run
  
  # Fast screenshots (every 30 ticks = 0.5 seconds)
  python game_loop.py --rom pokemon_red.gb --screenshot-interval 30
  
  # High frequency AI analysis (every 10 ticks)
  python game_loop.py --rom pokemon_blue.gb --screenshot-interval 10
  
  # Load from existing state
  python game_loop.py --rom pokemon_red.gb --load-state checkpoint.state
  
  # Multiple AI instances (for comparison)
  python game_loop.py --rom pokemon_red.gb --multi-instance --instances 3
  
  # Long gameplay session with analysis
  python game_loop.py --rom pokemon_blue.gb --save-dir ./battle_session --max-ticks 1800
        """
    )
    
    # Required arguments
    parser.add_argument(
        "--rom",
        type=str,
        required=True,
        help="Path to Pokemon ROM file (.gb)"
    )
    
    parser.add_argument(
        "--save-dir",
        type=str,
        default="./game_saves",
        help="Directory for saves, DB, and screenshots (default: ./game_saves)"
    )
    
    # Optional arguments
    parser.add_argument(
        "--screenshot-interval",
        type=int,
        default=60,
        help="Ticks between screenshots (default: 60 = 1 second at 60fps). Lower values = more frequent AI analysis."
    )
    
    parser.add_argument(
        "--load-state",
        type=str,
        help="Load existing emulator state file"
    )
    
    parser.add_argument(
        "--max-ticks",
        type=int,
        help="Maximum ticks to run before stopping (optional)"
    )
    
    parser.add_argument(
        "--multi-instance",
        action="store_true",
        help="Run multiple emulator instances simultaneously"
    )
    
    parser.add_argument(
        "--instances",
        type=int,
        default=3,
        help="Number of instances for multi-instance mode (default: 3)"
    )
    
    args = parser.parse_args()
    
    # Validate ROM exists
    rom_path = Path(args.rom)
    if not rom_path.exists():
        print(f"❌ ROM file not found: {rom_path}")
        return 1
    
    # Create configuration
    config = create_config(args)
    
    # Initialize game loop
    game_loop = GameLoop(config)
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\n🤷 Signal received, stopping gracefully...")
        game_loop.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Start
        game_loop.start()
        
        # Main loop
        while game_loop.is_running:
            if args.max_ticks and game_loop.current_tick >= args.max_ticks:
                print(f"\n⏱️ Reached max ticks ({args.max_ticks}), stopping...")
                break
            
            game_loop.run_single_tick()
            
            # Small delay to prevent CPU spinning
            time.sleep(0.001)
            
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        game_loop.stop()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
