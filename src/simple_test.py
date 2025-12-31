"""
Simple test to verify PyBoy screenshot functionality
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyboy import PyBoy
from PIL import Image

def simple_test():
    """Simple test with Pokemon Blue ROM"""
    
    print("🧪 Simple PyBoy Screenshot Test")
    print("=" * 50)
    
    rom_path = "data/rom/pokemon_blue.gb"
    print(f"📂 ROM: {rom_path}")
    
    # Check if ROM exists
    if not os.path.exists(rom_path):
        print(f"❌ ROM not found: {rom_path}")
        return False
    
    # Initialize emulator
    print("🚀 Loading ROM...")
    pyboy = PyBoy(rom_path)
    
    # Create screenshots directory
    screenshot_dir = Path(__file__).parent.parent / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)
    print(f"📁 Screenshots will be saved to: {screenshot_dir}")
    
    # Run for 500 ticks
    print("\n▶️  Running 500 ticks...")
    
    for tick in range(500):
        # Tick the emulator
        pyboy.tick()
        
        # Save screenshot at intervals
        if tick % 100 == 0:
            try:
                # Get screen ndarray
                screen_nparr = pyboy.screen.ndarray
                
                if screen_nparr is not None and screen_nparr.size > 0:
                    # Print debug info
                    print(f"  📊 Tick {tick}: min={screen_nparr.min()}, max={screen_nparr.max()}, mean={screen_nparr.mean():.2f}")
                    
                    # Convert to PIL Image
                    pil_image = Image.fromarray(screen_nparr, mode='RGB')
                    filename = f"screenshot_{tick:04d}.png"
                    filepath = screenshot_dir / filename
                    pil_image.save(str(filepath))
                    print(f"  📸 Saved {filename}")
                    
            except Exception as e:
                print(f"  ❌ Error at tick {tick}: {e}")
    
    # Clean up
    print("\n🛑 Stopping emulator...")
    pyboy.stop()
    
    print("\n" + "=" * 50)
    print("✅ Test completed!")
    
    return True

if __name__ == "__main__":
    success = simple_test()
    if success:
        print("\n🎉 All systems go! PyBoy screenshots are working.")
    else:
        print("\n❌ Test failed.")