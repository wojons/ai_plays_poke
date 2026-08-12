"""
Debug script to check PyBoy screen data
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

# PyBoy is imported lazily inside debug_screen() so that `--help` exits without
# importing the emulator. The module-level name is kept so tests can continue
# patching debug_screen.PyBoy.
PyBoy: Any = None

ROM_PATH = "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"


def debug_screen(rom_path: str, num_ticks: int = 1000) -> bool:
    """Debug PyBoy screen data"""

    print("🎮 Debugging PyBoy screen data")
    print(f"📂 ROM: {rom_path}")
    print(f"🔄 Ticks: {num_ticks}")
    print("=" * 50)

    # Check if ROM exists
    if not os.path.exists(rom_path):
        print(f"❌ ROM not found: {rom_path}")
        return False
    # Initialize emulator
    print("🚀 Loading ROM...")
    global PyBoy
    if PyBoy is None:
        from pyboy import PyBoy
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
                    print(
                        f"  📊 Tick {tick}: Screen data - min: {screen_nparr.min()}, max: {screen_nparr.max()}, mean: {screen_nparr.mean():.2f}"
                    )

                    # Check if screen has non-white pixels
                    unique_values = np.unique(screen_nparr)
                    non_white = unique_values[unique_values != 255]

                    if len(non_white) > 0:
                        print(
                            f"  🟢 Found non-white pixels at tick {tick}: {non_white[:5]}..."
                        )
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
    parser = argparse.ArgumentParser(
        description="Debug PyBoy screen data by ticking the emulator and inspecting frames."
    )
    parser.add_argument(
        "--rom",
        default=None,
        help=f"Path to the ROM file (default: {ROM_PATH})",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=None,
        help="Number of emulator ticks to run (default: 1000)",
    )
    args = parser.parse_args()

    # Boot the emulator only when the run is explicitly requested (--rom and/or
    # --ticks given). A bare invocation or --help prints usage and exits 0
    # without importing PyBoy.
    if args.rom is None and args.ticks is None:
        parser.print_help()
        sys.exit(0)

    rom = args.rom if args.rom is not None else ROM_PATH
    ticks = args.ticks if args.ticks is not None else 1000

    print("🧪 PyBoy Screen Debug Test")
    print("=" * 50)

    success = debug_screen(rom, num_ticks=ticks)
    if success:
        print("\n🎉 Debug completed successfully!")
    else:
        print("\n❌ Debug failed. Check the errors above.")
