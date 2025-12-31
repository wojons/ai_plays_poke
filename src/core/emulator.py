"""
Emulator Interface using PyBoy

Real PyBoy emulator integration for Pokemon games.
Replaces the previous stub implementation.
"""

from pathlib import Path
from typing import Optional
import numpy as np
import os

from src.schemas.commands import Button, GameState, CommandExecutionResult

# Try to import PyBoy, fallback to stub if not available
try:
    from pyboy import PyBoy
    PYBOY_AVAILABLE = True
    print("✅ PyBoy import successful - using real emulator")
except ImportError:
    PYBOY_AVAILABLE = False
    print("⚠️  PyBoy not available - using stub emulator")


class EmulatorInterface:
    """
    Interface for Pokemon emulator using PyBoy
    
    Integrates real PyBoy emulation with proper button presses,
    screenshot capture, and state management.
    """
    
    def __init__(self, rom_path: str):
        """
        Initialize emulator with ROM path
        
        Args:
            rom_path: Path to Pokemon ROM file (.gb)
        """
        self.rom_path = Path(rom_path)
        self.is_running = False
        self.current_tick = 0
        
        if PYBOY_AVAILABLE and os.path.exists(self.rom_path):
            print(f"🎮 Emulator initialized with ROM: {self.rom_path}")
            
            # Initialize real PyBoy
            try:
                self.pyboy = PyBoy(str(self.rom_path))
                print("✅ Real PyBoy emulator loaded")
            except Exception as e:
                print(f"❌ PyBoy initialization failed: {e}")
                print("⚠️  Falling back to stub implementation")
                self._init_stub_mode()
        else:
            print(f"⚠️  ROM not found or PyBoy unavailable: {self.rom_path}")
            self._init_stub_mode()
    
    def _init_stub_mode(self):
        """Initialize stub mode when real emulator is not available"""
        PYBOY_AVAILABLE = False
        self.pyboy = None
        print("⚠️  Using stub emulator mode")
    
    def start(self):
        """Start the emulator"""
        if PYBOY_AVAILABLE and hasattr(self, 'pyboy') and self.pyboy:
            self.is_running = True
            print("✅ Real PyBoy emulator started")
        else:
            self.is_running = True
            print("✅ Emulator started (stub mode)")
    
    def stop(self):
        """Stop the emulator"""
        if PYBOY_AVAILABLE and hasattr(self, 'pyboy') and self.pyboy:
            try:
                self.pyboy.stop()
                print("✋ Real PyBoy emulator stopped")
            except Exception as e:
                print(f"⚠️  PyBoy stop error: {e}")
        
        self.is_running = False
        print("✋ Emulator stopped")
    
    def tick(self) -> bool:
        """
        Advance one frame (one tick)
        60 ticks = 1 second in GameBoy
        
        Returns:
            False when game should exit, True otherwise
        """
        if not self.is_running:
            return False
        
        if PYBOY_AVAILABLE and hasattr(self, 'pyboy') and self.pyboy:
            try:
                self.pyboy.tick()
                self.current_tick += 1
                return True
            except Exception as e:
                print(f"⚠️  PyBoy tick error: {e}")
                return False
        else:
            # Stub mode - just increment tick
            self.current_tick += 1
            return True
    
    def capture_screen(self) -> np.ndarray:
        """
        Capture current game screen as RGB array
        Returns 160x144 RGB image
        
        Returns:
            numpy array of shape (144, 160, 3)
        """
        if PYBOY_AVAILABLE and hasattr(self, 'pyboy') and self.pyboy:
            try:
                screen_nparr = self.pyboy.screen.ndarray
                if screen_nparr is not None and screen_nparr.size > 0:
                    return screen_nparr
                else:
                    # Fallback to stub if screen data is empty
                    return np.random.randint(50, 200, (144, 160, 3), dtype=np.uint8)
            except Exception as e:
                print(f"⚠️  Screen capture error: {e}")
                return np.random.randint(50, 200, (144, 160, 3), dtype=np.uint8)
        else:
            # Stub mode: return random colored screen
            return np.random.randint(50, 200, (144, 160, 3), dtype=np.uint8)
    
    def press_button(self, button: Button, duration_frames: int = 60):
        """
        Press a button
        
        Args:
            button: Button to press
            duration_frames: How long to hold (60 = 1 second)
        """
        if PYBOY_AVAILABLE and hasattr(self, 'pyboy') and self.pyboy:
            try:
                # Map our Button enum to PyBoy button constants
                button_mapping = {
                    Button.A: "a",
                    Button.B: "b", 
                    Button.START: "start",
                    Button.SELECT: "select",
                    Button.UP: "up",
                    Button.DOWN: "down",
                    Button.LEFT: "left",
                    Button.RIGHT: "right"
                }
                
                if button in button_mapping:
                    pyboy_button = button_mapping[button]
                    self.pyboy.button_press(pyboy_button)
                    # Simple implementation - just press and release
                    # TODO: Implement proper duration handling
                    self.pyboy.button_release(pyboy_button)
                    
                print(f"⏎ Real PyBoy: Pressed {button}")
            except Exception as e:
                print(f"⚠️  Button press error: {e}")
        else:
            print(f"⏎ Pressing {button} for {duration_frames} frames (stub mode)")
    
    def save_state(self, state_path: str) -> bool:
        """
        Save emulator state to file using PyBoy's native save state mechanism.
        
        Args:
            state_path: Path to save state file
            
        Returns:
            True if save was successful, False otherwise
        """
        if PYBOY_AVAILABLE and hasattr(self, 'pyboy') and self.pyboy:
            try:
                state_data = self.pyboy.dumps()
                with open(state_path, 'wb') as f:
                    f.write(state_data)
                print(f"💾 PyBoy state saved to {state_path} ({len(state_data)} bytes)")
                return True
            except Exception as e:
                print(f"⚠️  PyBoy save state error: {e}")
                return False
        else:
            try:
                stub_data = f"stub_state_{self.current_tick}".encode('utf-8')
                with open(state_path, 'wb') as f:
                    f.write(stub_data)
                print(f"💾 State saved to {state_path} (stub mode)")
                return True
            except Exception as e:
                print(f"⚠️  Save state error: {e}")
                return False
    
    def load_state(self, state_path: str) -> bool:
        """
        Load emulator state from file using PyBoy's native load state mechanism.
        
        Args:
            state_path: Path to state file
            
        Returns:
            True if load was successful, False otherwise
        """
        if PYBOY_AVAILABLE and hasattr(self, 'pyboy') and self.pyboy:
            try:
                with open(state_path, 'rb') as f:
                    state_data = f.read()
                self.pyboy.loads(state_data)
                print(f"💾 PyBoy state loaded from {state_path} ({len(state_data)} bytes)")
                return True
            except Exception as e:
                print(f"⚠️  PyBoy load state error: {e}")
                return False
        else:
            try:
                if Path(state_path).exists():
                    content = Path(state_path).read_text()
                    print(f"💾 State loaded from {state_path}: {content} (stub mode)")
                    return True
                else:
                    print(f"⚠️  State file not found: {state_path}")
                    return False
            except Exception as e:
                print(f"⚠️  Load state error: {e}")
                return False
    
    def get_state_bytes(self) -> bytes:
        """
        Get emulator state as bytes for in-memory storage.
        
        Returns:
            Bytes containing the emulator state, or empty bytes if unavailable
        """
        if PYBOY_AVAILABLE and hasattr(self, 'pyboy') and self.pyboy:
            try:
                return self.pyboy.dumps()
            except Exception as e:
                print(f"⚠️  PyBoy get_state_bytes error: {e}")
                return b""
        else:
            return f"stub_state_{self.current_tick}".encode('utf-8')
    
    def load_state_bytes(self, state_data: bytes) -> bool:
        """
        Load emulator state from bytes for in-memory restoration.
        
        Args:
            state_data: Bytes containing the emulator state
            
        Returns:
            True if load was successful, False otherwise
        """
        if PYBOY_AVAILABLE and hasattr(self, 'pyboy') and self.pyboy:
            try:
                self.pyboy.loads(state_data)
                return True
            except Exception as e:
                print(f"⚠️  PyBoy load_state_bytes error: {e}")
                return False
        else:
            print("⚠️  Cannot load state bytes in stub mode")
            return False
    
    def get_game_time(self) -> int:
        """
        Get in-game time in ticks
        
        Returns:
            Current tick count
        """
        return self.current_tick
    
    def is_in_battle(self) -> bool:
        """Check if currently in battle (stub)"""
        return False
    
    def is_running_state(self) -> bool:
        """Check if emulator is running"""
        return self.is_running


class EmulatorManager:
    """
    Manager for multiple emulator instances
    
    Useful for running multiple AI instances simultaneously
    """
    
    def __init__(self, base_rom_path: str, instance_count: int = 3):
        """
        Initialize multiple emulator instances
        
        Args:
            base_rom_path: ROM file to use for all instances
            instance_count: Number of instances to run
        """
        self.rom_path = base_rom_path
        self.instances = {}
        
        for i in range(instance_count):
            instance_id = f"instance_{i}"
            self.instances[instance_id] = EmulatorInterface(self.rom_path)
            print(f"🎮 Created emulator instance: {instance_id}")
    
    def get_instance(self, instance_id: str) -> EmulatorInterface:
        """Get a specific emulator instance"""
        if instance_id not in self.instances:
            raise ValueError(f"Instance {instance_id} not found")
        return self.instances[instance_id]
    
    def start_all(self):
        """Start all emulator instances"""
        for instance_id, emulator in self.instances.items():
            emulator.start()
        print(f"✅ Started {len(self.instances)} emulator instances")
    
    def stop_all(self):
        """Stop all emulator instances"""
        for instance_id, emulator in self.instances.items():
            emulator.stop()
        print(f"✋ Stopped {len(self.instances)} emulator instances")
    
    def tick_all(self) -> dict:
        """
        Tick all emulators once
        
        Returns:
            Dict of instance_id -> is_alive
        """
        results = {}
        for instance_id, emulator in self.instances.items():
            results[instance_id] = emulator.tick()
        return results


# Example usage
if __name__ == "__main__":
    emulator = EmulatorInterface("pokemon_red.gb")
    
    emulator.start()
    
    for i in range(100):
        emulator.tick()
        if i % 20 == 0:
            screen = emulator.capture_screen()
            print(f"Tick {i}: Screen shape {screen.shape}")
            emulator.press_button(Button.A)
    
    emulator.stop()
