"""Verification script for the stacked prompt config system."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.core.prompt_assembler import PromptStack

ps = PromptStack("configs/prompts")

# Test load_stack
stack = ps.load_stack("gen1", "battle")
print("System:", stack["system"][:80])
print("Tools:", stack["tools"][:80])
print("Layers:", list(stack.keys()))
assert list(stack.keys()) == ["system", "tools", "observation", "memory", "examples"]

# Test assemble
prompt = ps.assemble(
    "gen1",
    "battle",
    {
        "screen_type": "battle",
        "enemy_pokemon": "Pidgey",
        "player_hp_pct": 85,
        "enemy_hp_pct": 34,
        "text_lines": ["What will PIDGEY do?", "FIGHT BAG", "POKéMON RUN"],
        "menu_items": ["FIGHT", "BAG", "POKéMON", "RUN"],
    },
    {
        "recent_actions": ["press_start(30)", "wait(120)", "press_a(5)"],
        "party_status": "SQUIRTLE Lv8 HP:45/45",
        "active_goal": "Get to Viridian City",
    },
)
print("Assembled prompt length:", len(prompt))
print("Contains Pidgey:", "Pidgey" in prompt)
print("Contains Squirtle:", "SQUIRTLE" in prompt)
assert "Pidgey" in prompt
assert "SQUIRTLE" in prompt

# Test all stacks load
for gen in ["gen1", "gen3"]:
    for st in ["battle", "overworld", "menu", "dialog"]:
        s = ps.load_stack(gen, st)
        assert list(s.keys()) == ["system", "tools", "observation", "memory", "examples"]
        print(f"  ✓ {gen}/{st}")

# Test available_stacks
stacks = ps.available_stacks()
print("Available stacks:", stacks)
assert len(stacks) == 8

# Test missing placeholder handling
prompt2 = ps.assemble(
    "gen3",
    "overworld",
    {"screen_type": "overworld"},
    {"recent_actions": [], "party_status": "", "active_goal": ""},
)
assert len(prompt2) > 0
assert "FireRed" in prompt2
print("Missing-placeholder test passed")

# Test gen3 battle
prompt3 = ps.assemble(
    "gen3",
    "battle",
    {
        "screen_type": "battle",
        "enemy_pokemon": "Charmeleon",
        "player_hp_pct": 15,
        "enemy_hp_pct": 60,
        "text_lines": ["What will CHARMELEON do?"],
        "menu_items": ["FIGHT", "BAG", "POKéMON", "RUN"],
    },
    {
        "recent_actions": ["press_a(5)"],
        "party_status": "CHARIZARD Lv36 HP:15/120",
        "active_goal": "Defeat rival on Nugget Bridge",
    },
)
assert "Charmeleon" in prompt3
assert "CHARIZARD" in prompt3
assert "FireRed" in prompt3
assert "15%" in prompt3
print("Gen 3 battle test passed")

print("\n✅ ALL TESTS PASSED")
