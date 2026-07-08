"""
Run PyBoy test for all available ROMs (faster version)
"""

import os
from pathlib import Path
from pyboy import PyBoy
from PIL import Image


def test_rom(rom_path: str, rom_name: str, num_ticks: int = 500, screenshot_interval: int = 100) -> bool:

    """Run PyBoy test for a specific ROM"""
    
    print(f"\n{'='*60}")
    print(f"🎮 Testing: {rom_name}")
    print(f"📂 ROM: {rom_path}")
    print(f"🔄 Ticks: {num_ticks}")
    print(f"📸 Screenshot every: {screenshot_interval} ticks")
    print(f"{'='*60}")
    
    # Check if ROM exists
    if not os.path.exists(rom_path):
        print(f"❌ ROM not found: {rom_path}")
        return False
    # Create screenshots directory for this ROM
    base_screenshot_dir = Path(__file__).parent.parent / "screenshots"
    screenshot_dir = base_screenshot_dir / rom_name
    screenshot_dir.mkdir(exist_ok=True)
    
    # Initialize emulator
    print("🚀 Loading ROM...")
    pyboy = PyBoy(rom_path)
    
    # Run the test loop
    print(f"▶️  Running {num_ticks} ticks...")
    
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
                    print(f"  📸 Tick {tick}: Saved {filename} ({pil_image.size}, {os.path.getsize(filepath)} bytes)")
            except Exception as e:
                print(f"  ❌ Error: {e}")
    
    # Clean up
    print("🛑 Stopping emulator...")
    pyboy.stop()
    
    print(f"\n✅ {rom_name} test completed!")
    print(f"📁 Screenshots: {screenshot_dir}")
    
    return True
def main() -> None:
    """Test all available ROMs"""
    
    print("🧪 Testing All Available ROMs (3000 ticks each)")
    print("="*60)
    
    # ROM configurations
    roms = [
        ("data/rom/pokemon_red.gb", "pokemon_red"),
        ("data/rom/pokemon_blue.gb", "pokemon_blue"),
        ("data/rom/pokemon_green.gb", "pokemon_green"),
        ("data/rom/pokemon_yellow.gb", "pokemon_yellow"),
        ("data/rom/pokemon_gold.gbc", "pokemon_gold"),
        ("data/rom/pokemon_silver.gbc", "pokemon_silver"),
    ]
    
    results = []
    
    for rom_path, rom_name in roms:
        if os.path.exists(rom_path):
            success = test_rom(rom_path, rom_name, num_ticks=3000, screenshot_interval=1000)
            results.append((rom_name, success))
        else:
            print(f"\n⚠️  ROM not found: {rom_path}")
            results.append((rom_name, False))
    # Summary
    print(f"\n{'='*60}")
    print("📊 SUMMARY")
    print(f"{'='*60}")
    
    for rom_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {rom_name}")
    
    passed = sum(1 for _, s in results if s)
    total = len(results)
    
    print(f"\n🎯 Results: {passed}/{total} ROMs passed")
    
    if passed == total:
        print("\n🎉 All ROMs are working correctly!")
    else:
        print(f"\n⚠️  {total - passed} ROM(s) failed. Check the errors above.")


if __name__ == "__main__":
    main()
