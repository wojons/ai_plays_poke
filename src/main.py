"""
Main AI Pokemon Player Application
Combines screenshot capture, memory reading, and vision processing
"""
import os
import sys
import time
from pathlib import Path
from PIL import Image
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyboy import PyBoy

class PokemonAIAgent:
    """AI Agent that plays Pokemon games"""
    
    def __init__(self, rom_path):
        self.rom_path = rom_path
        self.pyboy = None
        self.screenshot_dir = Path(__file__).parent.parent / "screenshots"
        self.screenshot_dir.mkdir(exist_ok=True)
        
    def start(self):
        """Start the Pokemon game"""
        print(f"🎮 Starting Pokemon AI Agent")
        print(f"📂 ROM: {self.rom_path}")
        
        # Check if ROM exists
        if not os.path.exists(self.rom_path):
            print(f"❌ ROM not found: {self.rom_path}")
            return False
        
        # Initialize emulator
        print("🚀 Loading ROM...")
        self.pyboy = PyBoy(self.rom_path)
        
        print("✅ Pokemon game started successfully!")
        return True
    
    def run_ticks(self, num_ticks=100):
        """Run the game for specified number of ticks"""
        print(f"▶️  Running {num_ticks} ticks...")
        for _ in range(num_ticks):
            self.pyboy.tick()
    
    def capture_screenshot(self, tick):
        """Capture screenshot at current game state"""
        try:
            # Get screen ndarray
            screen_nparr = self.pyboy.screen.ndarray
            
            if screen_nparr is not None and screen_nparr.size > 0:
                # Convert to PIL Image
                pil_image = Image.fromarray(screen_nparr, mode='RGB')
                filename = f"screenshot_{tick:04d}.png"
                filepath = self.screenshot_dir / filename
                pil_image.save(str(filepath))
                print(f"  📸 Tick {tick}: Saved {filename}")
                return True
        except Exception as e:
            print(f"  ❌ Error capturing screenshot: {e}")
            return False
    
    def read_memory_data(self):
        """Read Pokemon game data from memory"""
        if not self.pyboy:
            return None
        
        memory = self.pyboy.memory
        stats = {}
        
        try:
            # Player's Pokemon data (example addresses - needs verification)
            stats['player_hp'] = memory[0xD158]  # Current HP
            stats['player_max_hp'] = memory[0xD159]  # Max HP
            stats['player_level'] = memory[0xD16A]  # Level
            stats['player_status'] = memory[0xD15E]  # Status effects
            
            # Enemy Pokemon data (example addresses - needs verification)
            stats['enemy_hp'] = memory[0xCFD8]  # Current HP
            stats['enemy_max_hp'] = memory[0xCFD9]  # Max HP
            stats['enemy_level'] = memory[0xCFE2]  # Level
            
            return stats
            
        except Exception as e:
            print(f"❌ Error reading memory: {e}")
            return None
    
    def get_game_state(self, tick):
        """Get current game state including screenshot and memory data"""
        # Capture screenshot
        self.capture_screenshot(tick)
        
        # Read memory data
        memory_data = self.read_memory_data()
        
        return {
            'tick': tick,
            'screenshot': f"screenshots/screenshot_{tick:04d}.png",
            'memory_data': memory_data
        }
    
    def stop(self):
        """Stop the game"""
        if self.pyboy:
            print("🛑 Stopping emulator...")
            self.pyboy.stop()
            self.pyboy = None
            print("✅ Game stopped successfully!")

def main():
    """Main function to run the AI Pokemon player"""
    
    print("🤖 AI Pokemon Player - Main Application")
    print("=" * 50)
    
    # ROM configuration
    rom_path = "data/rom/pokemon_blue.gb"
    
    # Create AI agent
    agent = PokemonAIAgent(rom_path)
    
    # Start the game
    if not agent.start():
        return
    
    try:
        # Run game for some ticks to initialize
        print("\n🔄 Initializing game...")
        agent.run_ticks(500)
        
        # Get initial game state
        print("\n📊 Getting initial game state...")
        game_state = agent.get_game_state(0)
        print(f"  🎮 Game state at tick 0: {game_state['memory_data']}")
        
        # Run more ticks and capture states
        print("\n🔄 Running game and capturing states...")
        for tick in range(100, 501, 100):
            agent.run_ticks(100)
            game_state = agent.get_game_state(tick)
            print(f"  🎮 Game state at tick {tick}: {game_state['memory_data']}")
        
        print("\n🎉 AI Pokemon player completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error running AI player: {e}")
        
    finally:
        # Clean up
        agent.stop()

if __name__ == "__main__":
    main()