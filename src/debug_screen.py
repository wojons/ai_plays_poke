"""
Debug script to check PyBoy screen data
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyboy import PyBoy
from PIL import Image
import numpy as np

def debug_screen(rom_path: str, num_ticks: int = 1000):
    """Debug PyBoy screen data"""
    
    print(f"🎮 Debugging PyBoy screen data")
    print(f"📂 ROM: {rom_path}")
    print(f"🔄 Ticks: {num_ticks}")
    print("=" * 50)
    
    # Check if ROM exists
    if not os.path.exists(rom_path):
        print(f"❌ ROM not found: {rom_path}")
        return False
    
    # Initialize emulator
    print(f"🚀 Loading ROM...")
    pyboy = PyBoy(rom_path)
    
    # Create debug directory
    debug_dir = Path(__file__).parent.parent / "debug"
    debug_dir.mkdir(exist_ok=True)
    print(f"📁 Debug files will be saved to: {debug_dir}")
    
    # Run the test loop
    print(f"\n▶️  Running {num_ticks} ticks...")
    
    for tick in range(num_ticks):
        # Tick the emulator
        pyboy.tick()
        
        # Check screen data every 100 ticks
        if tick % 100 == 0:
            try:
                # Get screen ndarray
                screen_nparr = pyboy.screen.ndarray
                
                if screen_nparr is not None and screen_nparr.size > 0:
                    # Print debug information
                    print(f"  📊 Tick {tick}: Screen data - min: {screen_nparr.min()}, max: {screen_nparr.max()}, mean: {screen_nparr.mean():.2f}")
                    
                    # Check if screen has non-white pixels
                    unique_values = np.unique(screen_nparr)
                    non_white = unique_values[unique_values != 255]
                    
                    if len(non_white) > 0:
                        print(f"  🟢 Found non-white pixels at tick {tick}: {non_white[:5]}...")
                    else:
                        print(f"  🔴 Screen is still all white at tick {tick}")
                        
            except Exception as e:
                print(f"  ❌ Error at tick {tick}: {e}")
    
    # Clean up
    print("\n🛑 Stopping emulator...")
    pyboy.stop()
    
    print("\n" + "=" * 50)
    print("✅ Debug completed!")
    
    return True

if __name__ == "__main__":
    print("🧪 PyBoy Screen Debug Test")
    print("=" * 50)
    
    # Run debug with Pokemon Blue ROM
    success = debug_screen("data/rom/pokemon_blue.gb", num_ticks=1000)
    
    if success:
        print("\n🎉 Debug completed successfully!")
    else:
        print("\n❌ Debug failed. Check the errors above.")