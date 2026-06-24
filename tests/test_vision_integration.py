"""Integration test: Emulator + VisionClient with real API call."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load API key from Kobayashi-Maru env
api_key = None
env_path = "/home/kara/Kobayashi-Maru/.hermes/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                api_key = line.split("=", 1)[1]
                break

if not api_key:
    print("ERROR: Could not find OPENROUTER_API_KEY")
    sys.exit(1)

os.environ["OPENROUTER_API_KEY"] = api_key
print(f"API key loaded ({len(api_key)} chars)")

from src.core.emulator import Emulator
from src.core.vision import VisionClient
from src.core.rom_detect import detect_platform
import time

ROM_PATH = "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
print(f"ROM: {ROM_PATH}")
print(f"Platform detected: {detect_platform(ROM_PATH)}")

# Boot Blue to the copyright screen
print("Booting emulator...")
e = Emulator(ROM_PATH)
e.wait(180)  # 3 seconds
screen = e.capture()
print(f"Screen captured: shape={screen.shape}, dtype={screen.dtype}")
print(f"Pixel range: {screen.min()}-{screen.max()}")

# Save screenshot for debugging
from PIL import Image
Image.fromarray(screen).save("/tmp/pokemon_blue_capture.png")
print("Saved screenshot to /tmp/pokemon_blue_capture.png")

# Send to vision model
print("Creating VisionClient...")
vc = VisionClient()

print("Sending to vision model (this may take 10-30 seconds)...")
start = time.time()
result = vc.analyze(screen, "gen1")
elapsed = time.time() - start

print(f"\nVision call took {elapsed:.1f}s")
print(f"Vision result:")
for k, v in result.items():
    print(f"  {k}: {v!r}")

# Test cache
print("\nTesting cache (should be instant)...")
start2 = time.time()
result2 = vc.analyze(screen, "gen1")
elapsed2 = time.time() - start2

print(f"Cache call took {elapsed2:.3f}s")
print(f"Cache hit: {elapsed2 < 0.01}")
assert result == result2, "Cache returned different result!"

e.stop()
print("\n✅ Integration test passed!")
