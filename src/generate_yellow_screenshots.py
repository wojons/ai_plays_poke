"""
Generate High-Quality Screenshots for Pokemon Yellow
Run for 100,000 ticks with screenshots every 1,000 ticks
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyboy import PyBoy
from PIL import Image

def generate_pokemon_yellow_screenshots(num_ticks=100000, screenshot_interval=1000):
    """Generate high-quality screenshots for Pokemon Yellow"""
    
    print("🎮 Pokemon Yellow Screenshot Generator")
    print("=" * 60)
    print(f"🔄 Total ticks: {num_ticks:,}")
    print(f"📸 Screenshot interval: every {screenshot_interval:,} ticks")
    print(f"📊 Total screenshots: {num_ticks // screenshot_interval}")
    print("=" * 60)
    
    rom_path = "data/rom/pokemon_yellow.gb"
    
    # Check if ROM exists
    if not os.path.exists(rom_path):
        print(f"❌ ROM not found: {rom_path}")
        return False
    
    # Create screenshots directory specifically for Pokemon Yellow
    screenshot_dir = Path(__file__).parent.parent / "screenshots" / "pokemon_yellow_corrected"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Screenshots will be saved to: {screenshot_dir}")
    
    # Initialize emulator
    print(f"\n🚀 Loading Pokemon Yellow ROM...")
    pyboy = PyBoy(rom_path)
    
    # Run the game loop
    print(f"\n▶️  Running {num_ticks:,} ticks...")
    print(f"⏳ This may take several minutes...\n")
    
    screenshot_count = 0
    
    for tick in range(num_ticks):
        # Tick the emulator
        pyboy.tick()
        
        # Save screenshot at interval
        if tick % screenshot_interval == 0:
            try:
                # Use PyBoy's built-in image method - this returns a proper PIL Image
                pil_image = pyboy.screen.image
                
                if pil_image is not None:
                    # Save with high quality
                    filename = f"yellow_{tick:06d}.png"
                    filepath = screenshot_dir / filename
                    pil_image.save(str(filepath), format='PNG', compress_level=1)  # Low compression for quality
                    
                    screenshot_count += 1
                    
                    # Print progress
                    progress = (tick / num_ticks) * 100
                    print(f"  📸 [{progress:5.1f}%] Tick {tick:6d}: Saved {filename}")
                    
            except Exception as e:
                print(f"  ❌ Error at tick {tick}: {e}")
    
    # Clean up
    print(f"\n🛑 Stopping emulator...")
    pyboy.stop()
    
    print("\n" + "=" * 60)
    print("✅ Screenshot generation completed!")
    print(f"📸 Total screenshots saved: {screenshot_count}")
    print(f"📁 Location: {screenshot_dir}")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    # Generate full 100,000 ticks with screenshots every 1,000 ticks
    success = generate_pokemon_yellow_screenshots(
        num_ticks=100000,  # Full generation
        screenshot_interval=1000
    )
    
    if success:
        print("\n🎉 Pokemon Yellow screenshots generated successfully!")
        print("📁 All 100 screenshots saved to screenshots/pokemon_yellow/")
    else:
        print("\n❌ Screenshot generation failed.")