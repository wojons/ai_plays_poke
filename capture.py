#!/usr/bin/env python3
"""Cycle 5: Press A to advance Oak's dialog further."""
import sys
sys.path.insert(0, '/home/kara/ai_plays_poke')
from src.core.emulator import Emulator
from PIL import Image

emu = Emulator('data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb')
emu.fast_forward(1800)  # Boot sequence
emu.press_button('start', frames=30)  # C1: START at title
emu.fast_forward(180)
emu.press_button('a', frames=30)  # C2: select NEW GAME
emu.fast_forward(300)
emu.press_button('a', frames=30)  # C3: advance dialog (Hello there!)
emu.fast_forward(120)
emu.press_button('a', frames=30)  # C4: advance dialog (Welcome...)
emu.fast_forward(120)
emu.press_button('a', frames=30)  # C5: advance dialog (My name is OAK!)
emu.fast_forward(180)
img = emu.capture()
Image.fromarray(img).save('/tmp/poke_screen.png')
emu.stop()
print('[5/5] Pressed A to advance Oak dialog — final cycle')
