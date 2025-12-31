"""
Basic PyBoy Test - Verify emulator and screenshot functionality
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyboy import PyBoy
from PIL import Image
import yaml


def get_rom_path():
    """Load ROM path from config"""
    config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config['rom']['path']


def run_test(num_ticks: int = 1000, screenshot_interval: int = 100):
    """Run basic PyBoy test with screenshots"""
    
    rom_path = get_rom_path()
    print(f"🎮 Starting PyBoy test")
    print(f"📂 ROM: {rom_path}")
    print(f"🔄 Ticks: {num_ticks}")
    print(f"📸 Screenshot every: {screenshot_interval} ticks")
    print("=" * 50)
    
    # Check if ROM exists
    if not os.path.exists(rom_path):
        print(f"❌ ROM not found: {rom_path}")
        return False
    
    # Initialize emulator
    print(f"🚀 Loading ROM...")
    pyboy = PyBoy(rom_path)
    
    # Create screenshots directory
    screenshot_dir = Path(__file__).parent.parent / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)
    print(f"📁 Screenshots will be saved to: {screenshot_dir}")
    
    # Run the test loop
    print(f"\n▶️  Running {num_ticks} ticks...")
    
    for tick in range(num_ticks):
        # Tick the emulator
        pyboy.tick()
        
        # Save screenshot at interval
        if tick % screenshot_interval == 0:
            # Try to get screen data and save using PyBoy's built-in method
            try:
                # Use PyBoy's screen ndarray directly
                screen_nparr = pyboy.screen.ndarray
                if screen_nparr is not None and screen_nparr.size > 0:
                    # Print debug information about screen data
                    print(f"  📊 Tick {tick}: Screen data - min: {screen_nparr.min()}, max: {screen_nparr.max()}, mean: {screen_nparr.mean():.2f}")
                    
                    # Convert numpy array to PIL Image
                    pil_image = Image.fromarray(screen_nparr, mode='RGB')
                    filename = f"screenshot_{tick:04d}.png"
                    filepath = screenshot_dir / filename
                    pil_image.save(str(filepath))
                    print(f"  📸 Tick {tick}: Saved {filename} ({pil_image.size})")
            except Exception as e:
                print(f"  ❌ Error: {e}")
    
    # Clean up
    print("\n🛑 Stopping emulator...")
    pyboy.stop()
    
    print("\n" + "=" * 50)
    print("✅ Test completed successfully!")
    print(f"📁 Screenshots: {screenshot_dir}")
    print(f"💡 Check the screenshots to verify the game is running")
    
    return True


if __name__ == "__main__":
    print("🧪 PyBoy Basic Functionality Test")
    print("=" * 50)
    
    # Run the test with 100 ticks, screenshot every 10
    success = run_test(num_ticks=100, screenshot_interval=10)
    
    if success:
        print("\n🎉 All systems go! PyBoy is working correctly.")
    else:
        print("\n❌ Test failed. Check the errors above.")
        sys.exit(1)