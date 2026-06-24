"""Quick smoke test for Phase 4 components."""
import sys
sys.path.insert(0, "/home/kara/ai_plays_poke")

from src.core.memory import GameMemory
m = GameMemory()
m.record_action("pressed A")
m.record_action("pressed up for 20 frames")
m.set_goal("Reach Viridian City")
m.update_party("Squirtle L10 healthy, Pidgey L8 fainted")
snap = m.snapshot()
assert snap["active_goal"] == "Reach Viridian City"
assert len(snap["recent_actions"]) == 2
assert snap["battles_fought"] == 0
print("✓ GameMemory tests passed")
print(f"  snapshot: {snap}")

from src.core.ai_client import OpenRouterClient
assert hasattr(OpenRouterClient, "send_tool_request"), "send_tool_request missing!"
print("✓ send_tool_request method exists on OpenRouterClient")

from src.core.decision import DecisionLoop
print("✓ DecisionLoop import OK")

print("\n=== ALL PHASE 4 COMPONENT TESTS PASSED ===")
