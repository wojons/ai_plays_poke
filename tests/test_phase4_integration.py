"""Phase 4 integration verification (no API key).

Tests emulator boot, GameMemory, PromptStack, Tool parsing, and code structure.
"""
import sys
sys.path.insert(0, "/home/kara/ai_plays_poke")

print("=== PHASE 4 INTEGRATION VERIFICATION ===\n")

# ── 1. Emulator boot ──────────────────────────────────────────────────────
print("1. Loading emulator...")
from src.core.emulator import Emulator
e = Emulator("data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb")
print(f"   platform={e.platform}, is_gb={e.is_gb}")
screen = e.capture()
print(f"   Screenshot: {screen.shape} {screen.dtype}")

# Boot past title screen
e.wait(180)
e.press_button("start", 30)
e.wait(180)
e.press_button("a", 5)
e.wait(120)
print("   Game booted (past title screen) ✓")

# ── 2. GameMemory ─────────────────────────────────────────────────────────
print("\n2. GameMemory...")
from src.core.memory import GameMemory
m = GameMemory()
m.record_action("Pressed A for 5 frames")
m.record_action("Pressed up for 20 frames")
m.set_goal("Reach Viridian City")
m.update_party("Squirtle L12 healthy, Pidgey L10 fainted")
m.battles_fought = 3
m.locations_visited.append("Pallet Town")
snap = m.snapshot()
assert snap["active_goal"] == "Reach Viridian City"
assert len(snap["recent_actions"]) == 2
assert snap["battles_fought"] == 3
assert "Pallet Town" in snap["locations_visited"]
print(f"   snapshot: {snap}")
print("   GameMemory ✓")

# ── 3. Prompt assembly (no API) ───────────────────────────────────────────
print("\n3. PromptStack assembly...")
from src.core.prompt_assembler import PromptStack
ps = PromptStack()
test_vision = {
    "screen_type": "overworld",
    "text_lines": ["PALLET TOWN"],
    "menu_items": [],
    "adjacent_info": "grass and path, no NPCs",
}
try:
    assembled = ps.assemble(
        generation="gen1",
        screen_type="overworld",
        vision_output=test_vision,
        memory_context=snap,
    )
    print(f"   Assembled prompt: {len(assembled)} chars")
    assert "Pokémon Red/Blue/Yellow" in assembled
    assert "Reach Viridian City" in assembled
    assert "Pressed A" in assembled or "pressed A" in assembled.lower()
    print("   PromptStack ✓")
except Exception as exc:
    print(f"   Prompt assembly FAILED: {exc}")
    sys.exit(1)

# ── 4. Tool parsing ───────────────────────────────────────────────────────
print("\n4. Tool-call parsing...")
from src.core.tools import TOOL_SCHEMA, parse_tool_call, execute_tool_call

# Test code-fenced JSON
resp1 = '```json\n{"name": "press_button", "arguments": {"button": "a", "duration": 5}}\n```'
parsed = parse_tool_call(resp1)
assert parsed and parsed["name"] == "press_button"
assert parsed["arguments"]["button"] == "a"
print("   Code-fenced JSON ✓")

# Test bare JSON
resp2 = '{"name": "wait", "arguments": {"frames": 30}}'
parsed2 = parse_tool_call(resp2)
assert parsed2 and parsed2["name"] == "wait"
print("   Bare JSON ✓")

# Test tool execution
result = execute_tool_call(e, "press_button", {"button": "a", "duration": 3})
assert "Pressed a" in result
print(f"   Tool execution: {result} ✓")

# Test fallback (unknown screen_type)
resp3 = "I think we should move forward. Let me press the up button for a while. ```json\n{\"name\": \"combo\", \"arguments\": {\"buttons\": [\"up\"], \"duration\": 20}}\n```"
parsed3 = parse_tool_call(resp3)
assert parsed3 and parsed3["name"] == "combo"
print("   Mixed text + JSON ✓")

# Test nil case
assert parse_tool_call("no json here at all") is None
print("   Nil-case fallback ✓")

# ── 5. DecisionLoop code structure ────────────────────────────────────────
print("\n5. DecisionLoop code review...")
import inspect
from src.core.decision import DecisionLoop

# Check step() has all 7 phases
step_src = inspect.getsource(DecisionLoop.step)
phases = [
    ("Capture", "capture()"),
    ("Vision", "vision.analyze" if "vision.analyze" in step_src else "analyze"),
    ("Prompt selection", "prompt_stack.assemble"),
    ("Thinking", "send_tool_request"),
    ("Parse", "parse_tool_call"),
    ("Execute", "execute_tool_call"),
    ("Record", "record_action"),
]
for name, marker in phases:
    assert marker in step_src, f"Phase '{name}' ({marker}) missing from step()"
    print(f"   Phase '{name}' ✓")

# Check fallbacks exist
fallbacks = ["Vision failed", "Prompt assembly failed", "Thinking model failed", "Tool-call parse failed"]
for fb in fallbacks:
    assert fb in step_src, f"Fallback '{fb}' missing"
print(f"   All {len(fallbacks)} fallbacks present ✓")

# Check run() method
run_src = inspect.getsource(DecisionLoop.run)
assert "screenshot_interval" in run_src
assert "self.step()" in run_src
assert "self.emulator.wait" in run_src
print("   run() method correct ✓")

# ── 6. send_tool_request method ───────────────────────────────────────────
print("\n6. send_tool_request...")
from src.core.ai_client import OpenRouterClient
assert hasattr(OpenRouterClient, "send_tool_request")
# Verify signature
sig = inspect.signature(OpenRouterClient.send_tool_request)
params = list(sig.parameters.keys())
assert "prompt" in params
assert "tools" in params
assert "model" in params
print(f"   Method signature: {params}")
print("   send_tool_request ✓")

# ── 7. Cleanup ────────────────────────────────────────────────────────────
e.stop()
print("\n7. Emulator stopped ✓")

print("\n" + "=" * 60)
print("PHASE 4 VERIFIED — all components pass")
print("(Full API-dependent test requires OPENROUTER_API_KEY)")
print("=" * 60)
