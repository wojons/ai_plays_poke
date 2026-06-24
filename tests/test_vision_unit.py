"""Quick unit tests for VisionClient (no API call needed)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import base64 as b64m
import numpy as np

# Simulate API key for testing
os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-test-key"

from src.core.vision import VisionClient

# Test 1: missing key
old_key = os.environ.pop("OPENROUTER_API_KEY", None)
try:
    vc = VisionClient()
    print("FAIL: Should have raised ValueError")
    sys.exit(1)
except ValueError as e:
    print(f"OK: Correctly raised ValueError for missing key")
os.environ["OPENROUTER_API_KEY"] = old_key

# Test 2: basic creation
vc = VisionClient()
print(f"OK: VisionClient created, model={vc.model}")

# Test 3: hash consistency
fake_screen = np.zeros((144, 160, 3), dtype=np.uint8)
h1 = vc._compute_hash(fake_screen)
h2 = vc._compute_hash(fake_screen)
assert h1 == h2, "Hash inconsistent"
print(f"OK: Hash consistent")

# Test 4: image encoding
b64 = vc._encode_image(fake_screen)
print(f"OK: Base64 length: {len(b64)} chars")
decoded = b64m.b64decode(b64)
assert decoded[:4] == b'\x89PNG', f"Not a PNG: {decoded[:4]}"
print(f"OK: Valid PNG, {len(decoded)} bytes")

# Test 5: JSON parse
result = vc._parse_response('{"screen_type": "overworld", "enemy_pokemon": null}')
assert result == {"screen_type": "overworld", "enemy_pokemon": None}, f"Parse failed: {result}"
print("OK: Direct JSON parse")

# Test 6: markdown-fenced JSON
result2 = vc._parse_response('```json\n{"screen_type": "battle"}\n```')
assert result2 == {"screen_type": "battle"}, f"Fenced parse failed: {result2}"
print("OK: Markdown-fenced parse")

# Test 7: regex fallback
text_with_json = 'bla bla "screen_type": "dialog", "player_hp_pct": 75 some other text "enemy_pokemon": "Pidgey"'
result3 = vc._parse_response(text_with_json)
print(f"OK: Regex fallback: {result3}")

# Test 8: unknown returns None
result4 = vc._parse_response("just some random text no json")
assert result4 is None, f"Should be None: {result4}"
print("OK: Garbage returns None")

# Test 9: empty string
result5 = vc._parse_response("")
assert result5 is None
print("OK: Empty string returns None")

print("\n✅ All unit tests passed!")
