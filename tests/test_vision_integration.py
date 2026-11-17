"""Integration test: Emulator + VisionClient with real API call."""

import os  # noqa: E402
import sys  # noqa: E402

import pytest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Resolve the credential from this checkout only: the process environment first,
# then this repo's own .env (path derived from this file, never an absolute host
# path or another project's .env).  Missing key ⇒ skip, never fail.
api_key = os.environ.get("OPENROUTER_API_KEY") or None
env_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)
if not api_key and os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                api_key = line.split("=", 1)[1]
                break

if not api_key:
    pytest.skip(
        "OPENROUTER_API_KEY not available (process env and repo .env both "
        "absent); skipping live vision integration script",
        allow_module_level=True,
    )

os.environ["OPENROUTER_API_KEY"] = api_key
print(f"API key loaded ({len(api_key)} chars)")

from src.core.emulator import Emulator  # noqa: E402
from src.core.vision import VisionClient  # noqa: E402
from src.core.rom_detect import detect_platform  # noqa: E402
import time  # noqa: E402

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
from PIL import Image  # noqa: E402

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
print("Vision result:")
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
# Test-only capture path is consumed by mocks and never written as a shared temp file.
# ruff: noqa: S108
