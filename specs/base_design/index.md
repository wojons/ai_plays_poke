# Pallet Town Protocol: Master Architectural Schema

This is the **"Pallet Town Protocol: Master Architectural Schema" (PTP-01X)**. This document serves as the exhaustive technical foundation for an autonomous agent capable of 100% completion of any Pokémon-style title.

---

## PTP-01X Document Hierarchy

```
specs/
├── ptp_01x_executive_summary.md           ← Start here: Overview of all 10 chapters
├── ptp_01x_chapter_02_memory_layer.md     ← Memory addresses (WRAM hooks)
├── ptp_01x_chapter_05_combat_system.md    ← Gen 1 damage formula & type chart
├── technical_specifications_v5_complete.md ← Legacy comprehensive spec
└── base_design/
    └── index.md                           ← This file
```

---

## Quick Reference: Key PTP-01X Chapters

| Chapter | Document | Purpose | Key Data |
|---------|----------|---------|----------|
| **1** | (Perception) | Visual Interface & Grid Normalization | Pixel buffer, OCR, Semantic Grid |
| **2** | `ptp_01x_chapter_02_memory_layer.md` | WRAM Memory Hooks | $D362 (X), $D361 (Y), $D35E (Map), $D057 (Battle) |
| **3** | (Cartography) | Spatial Mapping | Map stitching, Collision Matrix |
| **4** | (Navigation) | HPA* Pathfinding | Ledge diodes, Warp handling |
| **5** | `ptp_01x_chapter_05_combat_system.md` | Battle Mechanics | Gen 1 damage formula, Type effectiveness |
| **6** | (Entity) | Party Optimization | Evolution, HM assignment |
| **7** | (Inventory) | Item Management | Bag slots, Shopping heuristics |
| **8** | (Dialogue) | Menu Navigation | State machine, OCR |
| **9** | (GOAP) | Goal Planning | Hierarchical goals, Quest graph |
| **10** | (Failsafe) | Error Recovery | Watchdog, Black box logging |

---

## Critical Memory Hooks (Chapter 2)

```python
# From ptp_01x_chapter_02_memory_layer.md
MEMORY_ADDRESSES = {
    'player_x': 0xD362,        # Player X block coordinate
    'player_y': 0xD361,        # Player Y block coordinate
    'map_id': 0xD35E,          # Current Map ID
    'battle_status': 0xD057,   # 0=Overworld, 1=Battle
    'party_count': 0xD163,     # Pokemon in party
    'menu_cursor': 0xCC26,     # Menu selection
    'enemy_hp_low': 0xCFE6,    # Enemy current HP (high byte)
    'enemy_hp_high': 0xCFE7,   # Enemy current HP (low byte)
    'money_1': 0xD3C7,         # Money (3 bytes big-endian)
    'joypad_sim': 0xCC38,      # Input simulation
}
```

---

## Gen 1 Damage Formula (Chapter 5)

```python
# From ptp_01x_chapter_05_combat_system.md
def calculate_damage_gen1(level, base_power, attack, defense, 
                         type_eff, is_stab, is_critical):
    """
    Damage = ((((2 × Level / 5 + 2) × BasePower × A/D) / 50) + 2) × Modifier
    
    Where Modifier = TypeEffectiveness × STAB × Critical × Random(0.85-1.0)
    """
    base = (2 * level / 5 + 2)
    intermediate = base * base_power * (attack / defense)
    divided = intermediate / 50
    added = divided + 2
    
    modifier = type_eff
    if is_stab:
        modifier *= 1.5
    if is_critical:
        modifier *= 1.5
    
    min_damage = int(added * modifier * 0.85)
    max_damage = int(added * modifier * 1.0)
    return (min_damage, max_damage)
```

---

## Gen 1 Type Effectiveness (Chapter 5)

```python
# Gen 1 specific quirks:
# - Bug/Poison: 2× (super effective) [Changed to ½× in Gen 2]
# - Ghost/Psychic: 0× (no effect) [Changed to 2× in Gen 2]
# - Ice/Fire: 1× (neutral) [Changed to ½× in Gen 2]
# - No Dark, Steel, or Fairy types in Gen 1

GEN1_TYPE_CHART = {
    ('Fire', 'Grass'): 2.0, ('Water', 'Fire'): 2.0,
    ('Electric', 'Water'): 2.0, ('Grass', 'Water'): 2.0,
    # ... complete chart in ptp_01x_chapter_05_combat_system.md
}
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PTP-01X ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   PERCEPTION LAYER (Ch1)                 │   │
│  │  Screen → Quantization → Semantic Grid → OCR → Fusion   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   MEMORY LAYER (Ch2)                     │   │
│  │  PyBoy.memory[] → WRAM Hooks → Party Data → Validation  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                 CARTOGRAPHY LAYER (Ch3)                  │   │
│  │  Map ID → Collision Matrix → HM Dependencies → Warps    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                 NAVIGATION LAYER (Ch4)                   │   │
│  │  HPA* Pathfinding → Ledge Diodes → Warp Transitions     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   BATTLE LAYER (Ch5)                     │   │
│  │  Type Matrix → Damage Calc → Kill Thresholds → Switch   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   DECISION CORE (Ch9)                    │   │
│  │  GOAP Planner → Goal Hierarchy → Action Planning        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Next Steps for Implementation

1. **Read `ptp_01x_executive_summary.md`** for complete architecture overview
2. **Reference `ptp_01x_chapter_02_memory_layer.md`** for memory addresses
3. **Reference `ptp_01x_chapter_05_combat_system.md`** for battle mechanics
4. **Check Data Crystal** for any additional memory addresses: https://datacrystal.tcrf.net/wiki/Pok%C3%A9mon_Red_and_Blue/RAM_map

---

**Document Version:** 2.0  
**Last Updated:** December 31, 2025  
**Protocol:** PTP-01X - Base Design Index  
**Status:** PTP-01X specs integrated