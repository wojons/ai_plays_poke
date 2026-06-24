#!/usr/bin/env python3
"""Boot and wait for title screen without pressing anything."""
import sys
sys.path.insert(0, '/home/kara/ai_plays_poke')
from src.core.emulator import Emulator
from PIL import Image

emu = Emulator('data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb')
emu.fast_forward(600)  # Boot + wait for copyright to pass + title screen
img = emu.capture()
Image.fromarray(img).save('/tmp/poke_screen.png')
emu.stop()
print('fast_forward(600) — screenshot saved')
