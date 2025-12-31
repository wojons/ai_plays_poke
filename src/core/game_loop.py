#!/usr/bin/env python3
"""
Core Game Loop Manager for AI Plays Pokemon Framework

Handles the main coordination between emulator, AI decisions, command execution,
and database logging. Provides CLI interface for running experiments.
"""

import argparse
import asyncio
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import json
import signal
import sys

import cv2
import numpy as np
from PIL import Image

from .emulator_interface import EmulatorInterface, Button
from .database import GameDatabase
from .screenshot_manager import ScreenshotManager


class GameLoop:
    """
    Main game loop coordinator. Manages the flow:
    Screenshot → AI Decision → Command → Execution → Log → Repeat
    """
    
    def __init__(self, 
                 rom_path: Path,
                 save_dir: Path,
                 screenshot_interval: float = 1.0,
                 ai_response_delay: float = 0.5):
        """
        Initialize game loop
        
        Args:
            rom_path: Path to Pokemon ROM file
            save_dir: Directory for saves, DB, and screenshots
            screenshot_interval: Seconds between screenshots
            ai_response_delay: Seconds to wait for AI processing
        """
        self.rom_path = rom_path
        self.save_dir = Path(save_dir)
        self.screenshot_interval = screenshot_interval
        self.ai_response_delay = ai_response_delay
        
        # Ensure save directory exists
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.emulator = EmulatorInterface(str(self.rom_path))
        self.db = GameDatabase(str(self.save_dir / "game_data.db"))
        self.screenshot_manager = ScreenshotManager(str(self.save_dir / "screenshots"))
        
        # State tracking
        self.current_tick = 0
        self.last_screenshot_time = 0
        self.is_running = False
        self.paused = False
        
        # Command pipeline
        self.pending_commands: List[Dict[str, Any]] = []
        self.command_history: List[Dict[str, Any]] = []
        
        # Performance tracking
        self.metrics = {
            "total_ticks": 0,
            "screenshots_taken": 0,
            "commands_sent": 0,
            "battles_encountered": 0,
            "start_time": None
        }
        
    def start(self):
        """Start the game loop"""
        print(f"🎮 Starting AI Plays Pokemon")
        print(f"📁 ROM: {self.rom_path}")
        print(f"💾 Save Directory: {self.save_dir}")
        
        self.emulator.start()
        self.is_running = True
        self.metrics["start_time"] = datetime.now()
        
        print("✅ Emulator started. Beginning game loop...")
        print("Press Ctrl+C to stop gracefully (saves progress)")
        
    def stop(self):
        """Stop the game loop and save state"""
        if not self.is_running:
            return
            
        print("\n🛑 Stopping game loop...")
        
        # Save emulator state
        save_path = self.save_dir / "emulator_state.state"
        self.emulator.save_state(str(save_path))
        print(f"💾 Emulator state saved to {save_path}")
        
        # Log final metrics
        self.db.log_session_metrics({
            **self.metrics,
            "end_time": datetime.now(),
            "duration": (datetime.now() - self.metrics["start_time"]).total_seconds() 
            if self.metrics["start_time"] else 0
        })
        
        self.is_running = False
        self.emulator.stop()
        
        print(f"📊 Final Stats:")
        print(f"   Ticks: {self.metrics['total_ticks']}")
        print(f"   Screenshots: {self.metrics['screenshots_taken']}")
        print(f"   Commands: {self.metrics['commands_sent']}")
        print(f"   Battles: {self.metrics['battles_encountered']}")
        
    def run_single_tick(self):
        """Execute one iteration of the game loop"""
        # Advance emulator
        self.emulator.tick()
        self.current_tick += 1
        self.metrics["total_ticks"] += 1
        
        # Take screenshot if interval elapsed
        current_time = time.time()
        if current_time - self.last_screenshot_time >= self.screenshot_interval:
            self._capture_and_process_screenshot()
            self.last_screenshot_time = current_time
        
        # Process any pending AI decisions
        if self.pending_commands:
            self._execute_pending_commands()
        
        # Check for battle state changes
        self._detect_battle_transition()
        
    def _capture_and_process_screenshot(self):
        """Capture screenshot, save it, and analyze game state"""
        screenshot = self.emulator.capture_screen()
        
        # Save screenshot with timestamp
        timestamp = datetime.now().isoformat()
        screenshot_path = self.screenshot_manager.save_screenshot(
            screenshot, 
            f"tick_{self.current_tick}_{timestamp}"
        )
        
        self.metrics["screenshots_taken"] += 1
        
        # Detect game state from screenshot
        game_state = self._analyze_screenshot(screenshot)
        
        # Log to database
        self.db.log_screenshot_event({
            "tick": self.current_tick,
            "timestamp": timestamp,
            "path": str(screenshot_path),
            "game_state": game_state
        })
        
        # Trigger AI decision if needed based on state
        if game_state.get("requires_ai_decision", False):
            asyncio.create_task(self._get_ai_decision(game_state))
        
    def _analyze_screenshot(self, screenshot: np.ndarray) -> Dict[str, Any]:
        """
        Analyze screenshot to determine game state
        This is a placeholder for actual vision processing
        """
        # Simple state detection based on screen regions
        height, width, _ = screenshot.shape
        
        # Check for battle UI (HP bars in corners)
        top_left = screenshot[0:20, 0:50]
        top_right = screenshot[0:20, width-50:width]
        
        is_battle = self._detect_hp_bars(top_left) or self._detect_hp_bars(top_right)
        
        # Check for dialog box (text at bottom)
        bottom_region = screenshot[height-40:height, 0:width]
        has_dialog = self._detect_text(bottom_region)
        
        # Check for menu (grid pattern)
        center_region = screenshot[height//3:2*height//3, width//3:2*width//3]
        is_menu = self._detect_menu_pattern(center_region)
        
        game_state = {
            "is_battle": is_battle,
            "has_dialog": has_dialog,
            "is_menu": is_menu,
            "requires_ai_decision": is_battle or has_dialog or is_menu
        }
        
        return game_state
    
    def _detect_hp_bars(self, region: np.ndarray) -> bool:
        """Detect HP bar colors (red/yellow/green)"""
        # Convert to HSV for color detection
        hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
        
        # Red HP bar (low health)
        red_lower = np.array([0, 100, 100])
        red_upper = np.array([10, 255, 255])
        red_mask = cv2.inRange(hsv, red_lower, red_upper)
        
        # Green HP bar (high health)
        green_lower = np.array([40, 100, 100])
        green_upper = np.array([80, 255, 255])
        green_mask = cv2.inRange(hsv, green_lower, green_upper)
        
        # If significant red or green detected, likely HP bar
        red_pixels = np.sum(red_mask > 0)
        green_pixels = np.sum(green_mask > 0)
        
        return (red_pixels + green_pixels) > 50  # Threshold
    
    def _detect_text(self, region: np.ndarray) -> bool:
        """Detect if region contains text (dialog box)"""
        # Convert to grayscale
        gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        
        # Check for high contrast (text characteristics)
        std_dev = np.std(gray)
        return std_dev > 30  # Text regions have higher contrast
    
    def _detect_menu_pattern(self, region: np.ndarray) -> bool:
        """Detect menu grid patterns"""
        # Convert to grayscale
        gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        
        # Apply edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Count horizontal/vertical lines (grid pattern)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 50, minLineLength=20, maxLineGap=5)
        
        return lines is not None and len(lines) > 5
    
    async def _get_ai_decision(self, game_state: Dict[str, Any]):
        """
        Get AI decision based on game state
        This is a placeholder for actual AI integration
        """
        print(f"🤔 AI decision needed at tick {self.current_tick}")
        
        # Simple decision logic for now
        if game_state["is_battle"]:
            command = self._simple_battle_ai()
        elif game_state["is_menu"]:
            command = self._simple_menu_ai()
        else:
            command = self._simple_exploration_ai()
        
        # Record AI thought process
        thought_record = {
            "tick": self.current_tick,
            "timestamp": datetime.now().isoformat(),
            "game_state": game_state,
            "reasoning": command["reasoning"],
            "confidence": command["confidence"],
            "model_used": "simple_heuristic"
        }
        
        self.db.log_ai_thought(thought_record)
        
        # Add to command pipeline
        self.pending_commands.append({
            "command": command["action"],
            "tick": self.current_tick,
            "reasoning": command["reasoning"],
            "confidence": command["confidence"]
        })
        
        print(f"✅ AI decision made: {command['action']}")
    
    def _simple_battle_ai(self) -> Dict[str, Any]:
        """Simple battle heuristic (placeholder)"""
        return {
            "action": "press:A",
            "reasoning": "In battle, press A to select default move",
            "confidence": 0.6
        }
    
    def _simple_menu_ai(self) -> Dict[str, Any]:
        """Simple menu navigation"""
        return {
            "action": "press:DOWN", 
            "reasoning": "In menu, move cursor down",
            "confidence": 0.5
        }
    
    def _simple_exploration_ai(self) -> Dict[str, Any]:
        """Simple exploration"""
        return {
            "action": "press:UP",
            "reasoning": "Exploring, move north",
            "confidence": 0.4
        }
    
    def _execute_pending_commands(self):
        """Execute commands waiting in pipeline"""
        if not self.pending_commands:
            return
        
        command = self.pending_commands.pop(0)
        
        try:
            # Parse command (format: "press:A" or "sequence:UP,UP,LEFT")
            action, params = command["command"].split(":", 1)
            
            if action == "press":
                button = params.upper()
                if hasattr(Button, button):
                    self.emulator.press_button(getattr(Button, button))
                    execution_time = time.time()
                    
                    # Log executed command
                    self.command_history.append({
                        **command,
                        "executed_at": execution_time,
                        "success": True
                    })
                    
                    self.metrics["commands_sent"] += 1
                    self.db.log_command_execution({
                        "tick": self.current_tick,
                        "command": command["command"],
                        "reasoning": command["reasoning"],
                        "confidence": command["confidence"],
                        "success": True
                    })
                    
                    print(f"⏎ Executed: {command['command']}")
                else:
                    raise ValueError(f"Unknown button: {button}")
                    
            elif action == "sequence":
                # Handle sequences (future feature)
                buttons = params.split(",")
                print(f"⏭️ Sequence: {buttons} (not yet implemented)")
                
            elif action == "batch":
                # Handle batch commands (future feature)
                print(f"⏭ Batch: {params} (not yet implemented)")
                
        except Exception as e:
            print(f"❌ Command execution failed: {e}")
            self.db.log_command_execution({
                "tick": self.current_tick,
                "command": command.get("command", "unknown"),
                "reasoning": command.get("reasoning", ""),
                "confidence": command.get("confidence", 0),
                "success": False,
                "error": str(e)
            })
    
    def _detect_battle_transition(self):
        """Detect when battle starts/ends"""
        # Simple check: if screenshot shows battle UI vs previous state
        # This is a placeholder for more sophisticated detection
        if self.current_tick % 60 == 0:  # Check every second
            is_currently_battling = self._analyze_screenshot(
                self.emulator.capture_screen()
            )["is_battle"]
            
            if is_currently_battling and not hasattr(self, '_was_battling'):
                # Battle just started
                print("⚔️ Battle started!")
                self.metrics["battles_encountered"] += 1
                self.db.log_battle_start({
                    "tick": self.current_tick,
                    "timestamp": datetime.now().isoformat()
                })
                self._was_battling = True
                
            elif not is_currently_battling and hasattr(self, '_was_battling'):
                # Battle just ended
                print("🏁 Battle ended!")
                self.db.log_battle_end({
                    "tick": self.current_tick,
                    "timestamp": datetime.now().isoformat()
                })
                delattr(self, '_was_battling')

def main():
    """Main entry point for CLI"""
    parser = argparse.ArgumentParser(
        description="AI Plays Pokemon - Framework for AI-driven Pokemon gameplay",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic run with default settings
  python game_loop.py --rom "pokemon_red.gb" --save-dir "./saves/run1"
  
  # Fast screenshots (500ms interval)
  python game_loop.py --rom "pokemon_red.gb" --screenshot-interval 0.5
  
  # Start from existing save state
  python game_loop.py --rom "pokemon_red.gb" --load-state "checkpoint.state"
        """
    )
    
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
    
    parser.add_argument(
        "--screenshot-interval",
        type=float,
        default=1.0,
        help="Seconds between screenshots (default: 1.0)"
    )
    
    parser.add_argument(
        "--load-state",
        type=str,
        help="Load existing emulator state file (.state)"
    )
    
    parser.add_argument(
        "--ai-delay",
        type=float,
        default=0.5,
        help="Seconds to wait for AI processing (default: 0.5)"
    )
    
    parser.add_argument(
        "--max-ticks",
        type=int,
        help="Maximum ticks to run before stopping (optional)"
    )
    
    args = parser.parse_args()
    
    # Validate ROM exists
    rom_path = Path(args.rom)
    if not rom_path.exists():
        print(f"❌ ROM file not found: {rom_path}")
        return 1
    
    # Initialize game loop
    game_loop = GameLoop(
        rom_path=rom_path,
        save_dir=args.save_dir,
        screenshot_interval=args.screenshot_interval,
        ai_response_delay=args.ai_delay
    )
    
    # Load state if provided
    if args.load_state:
        state_path = Path(args.load_state)
        if state_path.exists():
            print(f"📂 Loading state from {state_path}")
            game_loop.emulator.load_state(str(state_path))
        else:
            print(f"⚠️ State file not found: {state_path}, starting fresh")
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\n🤷 Ctrl+C detected, stopping gracefully...")
        game_loop.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Start game loop
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
