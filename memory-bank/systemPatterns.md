# System Patterns: Architecture and Design Patterns

## Core Architectural Pattern: Orchestrated Intelligence Loop (ACTUAL IMPLEMENTATION)

### The Actual Implemented System

The fundamental pattern that differentiates this project is the **Screenshot → AI Analysis → Strategic Decision → Tactical Action** pipeline. This enables real vision-based AI gameplay that actually wins Pokemon battles.

```mermaid
flowchart LR
    ┌─────────────────────────────────────────────────────────────┐
    │                    ACTUAL IMPLEMENTATION                         │
    ├─────────────────────────────────────────────────────────────┤
    │                                                                   │
    │  ┌─────────────────────┐                                        │
    │  │   PYBOY EMULATOR     │  ← Real Game Boy emulation              │
    │  │   (Pokemon ROM)      │     - 160x144 RGB screenshot capture     │
    │  │                     │     - Button input system                │
    │  │  "What screen        │     - Save/Load state functionality      │
    │  │   shows?"            │                                        │
    │  │  └──────────┬───────────┴────────────┬─────────────────┐  │
    │  │             │                        │                         │  │
    │  │  ↓ Screenshot              │ Screen State Analysis   │  │
    │  │  ┌─────────────────────┐             │                         │  │
    │  │  │ PROMPT MANAGER      │ ← Dynamic   │ Game State Detection    │  │
    │  │  │  (5 categories)    │   Selection │                         │  │
    │  │  │                     │             │                         │  │
    │  │  │ "What should        │             ↓ Tactical Analysis       │  │  │
    │  │  │   I interpret       │             │                         │  │
    │  │  │   this?"            │ ┌─────────────────────────────┐        │  │
    │  │  └──────────┬───────────┤   AI CLIENT MANAGER          │        │  │
    │  │             │          │  - OpenRouter API integration │        │  │
    │  │             ↓           │  - Vision + Text models      │        │  │
    │  │  ┌─────────────────────┤                             │        │  │
    │  │  │ ORCHESTRATED        │  "What should I              │        │  │
    │  │  │ INTELLIGENCE LOOP   │   decide based               │        │  │
    │  │  │  1. Screenshot      │                             │        │  │
    │  │  │ 2. State Analysis  │  "What button               │        │  │
    │  │  │ 3. AI Decision     │   should I press?"          │        │  │
    │  │  │ 4. Action Output   │                             │        │  │
    │  │  │                     └─────────┬───────────┬───────┴────────┘  │
    │  │              Command Execution     │           │                  │
    │  │  ┌─────────────────────────────────────────────────────────────┐ │  │
    │  │  │           DATABASE              │        │                  │
    │  │  │     (SQLite Analytics)         │        │                  │
    │  │  │  - Session Tracking             │        │                  │
    │  │  │  - Battle Outcomes             │        │                  │
    │  │  │  - Command History             │        │                  │
    │  │  └─────────────────────────────────────────────────────────────┘ │
    │  └───────────────────────────→ BATTLE VICTORIES!                  ┘
```

### The ACTUAL Implemented Cognitive Architecture

**What We Actually Built:**

**1. Vision Processing (Observer Equivalent)**
```
Screenshot Capture → Vision Model Analysis → Game State Detection
- Real Pokemon Blue ROM gameplay
- 160x144 RGB array capture from PyBoy emulator  
- AI vision analysis to detect battle/menu/dialog states
- Enemy Pokemon identification and HP estimation
```

**2. Strategic Planning (Strategist Equivalent)**
```
Game State Analysis → Prompt Selection → AI Decision Making
- Dynamic prompt system with 5 specialized categories
- Battle prompt: Pokemon analysis and tactical decisions
- Menu prompt: Navigation and selection strategies
- Dialog prompt: Text flow and story progression
- Strategic prompt: Long-term planning and objectives
- Exploration prompt: Pathfinding and navigation
```

**3. Tactical Execution (Tactician Equivalent)**
```
AI Decision → Command Parsing → Button Press → Victory!
- Button mapping: A, B, START, SELECT, UP, DOWN, LEFT, RIGHT
- Real PyBoy button input execution
- Battle outcome tracking and victory logging
- Performance metrics and analytics
```

### Key Pattern: Hierarchical Memory Filtering

Every piece of information flows through a filtering hierarchy:

**Level 1 - Raw Input:** Screen pixels, memory values, button states
**Level 2 - Semantic State:** `{"battle": true, "enemy": "Geodude", "my_hp": 45}`
**Level 3 - Contextualized State:** `{"battle": true, "enemy": "Geodude", "my_hp": 45, "type_weakness": "Water/Grass"}`
**Level 4 - Strategically Relevant:** `{"battle": true, "enemy": "Geodude", "strategy": "Use Water moves", "my_hp": 45}`
**Level 5 - Tactically Urgent:** `{"BUTTON_A": true, "reason": "Water Gun available and super effective"}`

### Pattern: The Decision Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
    │                      THE DECISION PIPELINE                          │
    ├─────────────────────────────────────────────────────────────┤
    │                                                                      │
    │   INPUT LAYER                                                        │
    │   ├── Vision Model: Raw pixels → Semantic state                      │
    │   ├── Emulator API: Memory values → Ground truth                     │
    │   └── Pokédex API: Pokemon ID → Type/weakness data                   │
    │                                                                      │
    │   CONTEXT LAYER                                                      │
    │   ├── Observer Memory: Journey narrative (filtered by recency)       │
    │   ├── Strategist Memory: Lessons learned (filtered by relevance)    │
    │   └── Tactician Buffer: Current state (always included)              │
    │                                                                      │
    │   REASONING LAYER                                                   │
    │   ├── Strategic Model: "What should I accomplish?" (expensive)       │
    │   ├── Tactical Model: "How do I accomplish it?" (cheap)              │
    │   └── Validation Model: "Is this legal?" (fast)                      │
    │                                                                      │
    │   EXECUTION LAYER                                                     │
    │   ├── Action Translation: Decision → Button press                    │
    │   ├── Emulator Control: Button press → Game input                    │
    │   └── Result Capture: New screen → Loop back to INPUT                │
    │                                                                      │
    │   LEARNING LAYER                                                      │
    │   ├── Battle Log: All decisions + outcomes                           │
    │   ├── Forensic Analysis: What went wrong?                            │
    │   ├── Insight Synthesis: What did I learn?                           │
    │   └── Memory Update: Strategist memory updated                       │
    │                                                                      │
    └─────────────────────────────────────────────────────────────────────┘
```

### Pattern: Memory Management Patterns

**Observer Memory (Long-term Archive):**
```
Structure:
{
  "journey_narrative": "String summary of major events",
  "team_history": [{"pokemon": "Charizard", "levels_gained": 12, "battles_won": 8}],
  "badge_progress": ["Boulder", "Cascade"],
  "hm_progress": ["Cut", "Flash"],
  "important_locations": [{"name": "Pewter City", "purpose": "Before Gym 2"}]
}
Update Frequency: After major events (gym battles, story moments)
Access Pattern: Always loaded at session start
Pruning: Never pruned (only grows)
```

**Strategist Memory (Mid-term Heuristics):**
```
Structure:
{
  "type_lessons": {"Fire_vs_Rock": {"confidence": 0.85, "uses": 3, "success": True}},
  "opponent_patterns": {"Brock": {"aggression": 0.9, "common_moves": ["Tackle", "Harden"]}},
  "move_effectiveness": {"Flamethrower": {"avg_damage": 45, "hit_rate": 0.95}},
  "resource_strategies": {"PP_conservation": {"confidence": 0.7, "priority": 3}},
  "failure_modes": {"Geodude_defeat": {"reason": "Type mismatch", "solution": "Switch to Water"}}
}
Update Frequency: After every battle
Access Pattern: Retrieved based on current battle context
Pruning: Aged out after 1000 turns without access
```

**Tactician Memory (Operational Buffer):**
```
Structure:
{
  "current_battle": {
    "turn": 2,
    "enemy_pokemon": "Geodude",
    "enemy_hp": 60,
    "enemy_type": ["Rock", "Ground"],
    "my_pokemon": "Charmander",
    "my_hp": 45,
    "my_moves": [
      {"name": "Ember", "type": "Fire", "pp": 25, "effectiveness": "not_very"},
      {"name": "Scratch", "type": "Normal", "pp": 35, "effectiveness": "neutral"},
      {"name": "Growl", "type": "Normal", "pp": 40, "effectiveness": "status"}
    ]
  },
  "last_actions": ["Used Ember", "Enemy used Tackle"]
}
Update Frequency: Every turn
Access Pattern: Always included in tactical decisions
Pruning: Flushed when battle ends
```

### Pattern: Context Injection Protocol

The Tactician never sees raw pixels or memory dumps. It receives structured context:

```
PROMPT_TEMPLATE = """
MISSION OBJECTIVE: {observer_narrative_recent}

STRATEGIC INTELLIGENCE: {strategist_memories_relevant}

EXPERT SYSTEM DATA: {pokedex_lookup}

CURRENT BATTLE STATE: {tactician_buffer}

INSTRUCTION: Determine the next button press (A, B, UP, DOWN, LEFT, RIGHT).

Explain your reasoning in 1-2 sentences.
"""
```

### Pattern: Memory Decay and Consolidation

**Temporal Decay:**
```
decay_factor = 1.0 / (1.0 + decay_rate * time_elapsed / 3600)

# Example: decay_rate = 0.01
# After 1 hour: decay = 1.0 / 1.01 = 0.99
# After 24 hours: decay = 1.0 / 1.24 = 0.81
# After 7 days: decay = 1.0 / (1 + 0.01*168) = 0.37
```

**Consolidation Protocol:**
1. When memory is accessed, increment access_count
2. When memory is updated, blend old and new confidence
3. When memory is not accessed for 1000 turns, mark for review
4. When memory confidence drops below 0.2, delete
```

### Pattern: The Reflection Engine

```
REFLECTION_PHASES = [
  "failure_detection",      # Did we lose? How bad?
  "forensic_analysis",      # What happened turn by turn?
  "insight_synthesis",      # What lessons can we extract?
  "memory_integration",     # Update strategist memory
  "validation_override"     # Sanity check updates
]
```

### Pattern: Failure Classification

```
FAILURE_TYPES = {
  "execution_failure": {    # Right idea, wrong button
    "severity": "low",
    "reflection_depth": "brief",
    "memory_update": "low_priority"
  },
  "strategic_failure": {    # Wrong approach for opponent
    "severity": "high",
    "reflection_depth": "deep",
    "memory_update": "high_priority"
  },
  "information_failure": {    # Didn't know crucial data
    "severity": "medium",
    "reflection_depth": "medium",
    "memory_update": "add_fact"
  },
  "resource_failure": {    # Exhausted PP/items
    "severity": "medium",
    "reflection_depth": "medium",
    "memory_update": "resource_strategy"
  },
  "compounding_failure": {    # Small mistakes accumulated
    "severity": "high",
    "reflection_depth": "deep",
    "memory_update": "sequence_optimization"
  }
}
```

### Pattern: Insight Confidence Scoring

```
CONFIDENCE_CALCULATION = {
  "evidence_count": "number of supporting battles",
  "recency_weight": "how recent was the evidence",
  "contradiction_check": "does this match existing memories",
  "specificity_weight": "is this too specific or generalizable"
}

# Bayesian-style update:
new_confidence = (new_evidence * 0.6 + old_confidence * 0.4) * decay_factor
```

---

## Document History

- **v1.0 (2025-12-29):** Initial system patterns documented during ULTRATHINK session with core team
- **v2.0 (2025-12-31):** Updated with PTP-01X specification completion
- **Current Version:** Updated during PTP-01X specification completion session

---

*Document updated during PTP-01X specification completion on December 31, 2025*
