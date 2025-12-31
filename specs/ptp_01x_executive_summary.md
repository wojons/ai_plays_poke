# Pallet Town Protocol: Master Architectural Schema (PTP-01X)

## Executive Summary

The **Pallet Town Protocol (PTP-01X)** defines the comprehensive technical architecture for an Autonomous Artificial Intelligence Agent designed to achieve a deterministic, 100% completion rate of Generation I Game Boy Pokémon titles (Red, Blue, Yellow).

### Core Design Philosophy

This architecture **eschews the fragility of pure computer vision approaches** and **the opacity of end-to-end reinforcement learning** in favor of a **Hybrid Symbolic-Neuro-Visual Model**:

1. **Symbolic Layer**: Direct memory access (DMA) via PyBoy emulation core for ground-truth state retrieval
2. **Neuro Layer**: Vision model (GPT-4o) for visual context, validation, and visual-only cues
3. **Visual Layer**: Pixel buffer processing, OCR, semantic grid classification

### The 10-Chapter Architecture

| Chapter | Name | Purpose |
|---------|------|---------|
| **1** | Perception Layer | Visual Interface & Grid Normalization |
| **2** | Memory Interfacing | State Retrieval (The "Truth" Layer) |
| **3** | Cartographic Intelligence | Spatial Mapping & Global Navigation |
| **4** | Navigation Engine | Pathfinding Algorithms (HPA*) |
| **5** | Battle Mechanics | Combat Heuristics & Type Analysis |
| **6** | Entity Management | Party Optimization & Evolution |
| **7** | Inventory & Logistics | Item Management & Economy |
| **8** | Dialogue Systems | NPC Interaction & Menu Navigation |
| **9** | Decision Core | GOAP Planning & Goal Hierarchy |
| **10** | Failsafe Protocols | System Integration & Recovery |

---

## 1. The Hybrid Symbolic-Neuro-Visual Model

### Why This Architecture Wins

**Pure Vision Approaches Fail Because:**
- Visual ambiguity (similar-looking tiles, animations)
- OCR errors on pixel-font text
- Screen transitions and animations confuse decision timing
- Cannot read hidden stats (EVs, IVs, exact HP numbers)

**Pure Memory Approaches Fail Because:**
- Memory can be delayed or corrupted
- Cannot detect visual-only cues (animation states, screen shakes)
- Cannot verify memory matches rendered reality
- Bypasses the "authentic gameplay" requirement

**PTP-01X Solution: Dual Verification**

```
┌─────────────────────────────────────────────────────────────────────┐
│                    HYBRID ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐ │
│  │   VISION LAYER  │    │  MEMORY LAYER   │    │  DECISION CORE  │ │
│  │   (Chapter 1)   │    │   (Chapter 2)   │    │   (Chapter 9)   │ │
│  │                 │    │                 │    │                 │ │
│  │ - Pixel Buffer  │    │ - WRAM Access   │    │ - GOAP Planning │ │
│  │ - OCR Parsing   │    │ - Event Flags   │    │ - Goal Hierarchy│ │
│  │ - Semantic Grid │    │ - Party Data    │    │ - Task Planning │ │
│  │ - Visual Cues   │    │ - Inventory     │    │ - Strategy      │ │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘ │
│           │                      │                      │          │
│           │     Visual-Memory    │                      │          │
│           │     Reconciliation   │                      │          │
│           └──────────────────────┼──────────────────────┘          │
│                                  │                                   │
│                                  ▼                                   │
│                    ┌─────────────────────────┐                       │
│                    │   CONFLICT RESOLUTION   │                       │
│                    │                         │                       │
│                    │ - State Desync Alert    │                       │
│                    │ - Re-Localization       │                       │
│                    │ - Trust Calibration     │                       │
│                    └─────────────────────────┘                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Key Technical Innovations

### 2.1 Synchronous "Tick-Read-Act" Cycle

The architecture mandates a strict cycle timing:

```
TICK:      Advance emulation by 1 frame (or N frames for training)
           ↓
READ:      Extract frame buffer + Read WRAM state
           ↓
VERIFY:    Compare Vision vs Memory for consistency
           ↓
DECIDE:    Use Decision Core (GOAP) to plan action
           ↓
ACT:       Execute button press
           ↓
REPEAT
```

**Critical Timing Rules:**
- Frame buffer read must happen IMMEDIATELY after tick advancement
- If de-coupled, agent risks "blind inputs" (acting on stale data)
- During high-speed training, use "headless" rendering mode

### 2.2 Color Quantization Pipeline

The Game Boy displays only 4 shades (White, Light Gray, Dark Gray, Black), but modern emulation introduces artifacts through upscaling and color correction.

**Quantization Algorithm:**
```
1. For each pixel in frame buffer:
2. Calculate Euclidean distance to 4 canonical colors:
   - White (255, 255, 255)
   - Light Gray (170, 170, 170)
   - Dark Gray (85, 85, 85)
   - Black (0, 0, 0)
3. Assign pixel to nearest color (0-3 index)
```

**Benefits:**
- State space reduction: 256³ RGB values → 4 integers
- Noise invariance: immune to emulator palette swaps
- Deterministic: RGB(240,240,240) = RGB(255,255,255) always

### 2.3 Semantic Grid Classification

The 160×144 pixel screen (20×18 tiles of 8×8 pixels) is mapped to a **10×9 semantic grid** of 16×16 pixel blocks.

**Tile Classification Output:**
```
┌─────────────────────────────────────┐
│ WALKABLE │ WALL    │ WARP    │     │
│ LEDGE↓   │ WATER   │ GRASS   │ ... │
│ NPC      │ TRAINER │ ITEM    │     │
└─────────────────────────────────────┘
```

**Classification Method:**
- **Primary**: Hash-Matching against pre-computed TileDatabase
- **Fallback**: CNN classifier for unknown tiles (glitches, animations)

### 2.4 Hierarchical Pathfinding (HPA*)

Standard A* on the entire Kanto map is computationally expensive. PTP-01X uses **Hierarchical Pathfinding A***:

```
┌─────────────────────────────────────────────────────────────────┐
│                     HPA* TWO-LEVEL SEARCH                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LEVEL 1: MACRO-PATHING                                          │
│  ─────────────────────                                           │
│  Query Global Adjacency Graph to find:                           │
│  Pallet Town → Route 1 → Viridian City → Route 2 → Pewter City  │
│                                                                  │
│  LEVEL 2: MICRO-PATHING                                          │
│  ─────────────────────                                           │
│  Within current map, use A* on local Collision Matrix:           │
│  Current Position (5, 3) → Target Warp (12, 2)                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.5 The "Diode Node" Concept for Ledges

Ledges are **unidirectional** (can only go down). Topologically, they function as "diodes" in the navigation graph:

```
Normal Edge:    A ↔ B  (bidirectional, cost 1)
Diode Node:     A ──► B  (only down, cost 1)
                │       ^
                │       │ (blocked)
                ▼       │
                C ──► D  (separate diode)
```

**Pathfinding Implication:**
- A* heuristic is modified to respect Diode Nodes
- Prevents infinite loops from trying to climb ledges
- Agent never attempts invalid movements

---

## 3. Memory Architecture: The "Truth" Layer

### 3.1 WRAM Address Map (Critical Hooks)

The Game Boy's 8KB WRAM ($C000-$DFFF) contains all game state. PTP-01X uses **Hard-Linked Hooks** (static addresses from ROM decompilation) for O(1) access.

| Address | Size | Purpose |
|---------|------|---------|
| $D362 | 1 byte | Player X Block Coordinate |
| $D361 | 1 byte | Player Y Block Coordinate |
| $D35E | 1 byte | Current Map ID |
| $D057 | 1 byte | Battle Status (0=Overworld, 1=Battle) |
| $CFE6-$CFE7 | 2 bytes | Enemy Current HP |
| $CFF4+ | 2 bytes | Enemy Defense Stat |
| $D163 | 1 byte | Party Count |
| $CC26 | 1 byte | Menu Cursor Position |

### 3.2 Event Flag Bitfield

World state is tracked via a contiguous bitfield in WRAM. Each bit = specific event:

```
Example Flags (approximate):
Bit 0: Oak Parcel Delivered
Bit 1: Received Pokedex
Bit 2: Defeated Brock
Bit 3: Obtained Boulder Badge
...
```

**Bitwise Diff Engine:**
- Compare bitfield at time t vs t-1
- Detect exactly which bit flipped
- Query EventDatabase to identify completed event
- Maintain 100% accurate Quest Log

---

## 4. Combat Heuristics: The Math Layer

### 4.1 Damage Formula (Gen I)

```
Damage = (((2 × Level / 5 + 2) × BasePower × A/D) / 50 + 2) × Modifiers
```

Where:
- Level = Pokemon level
- BasePower = Move's base power
- A = Attack (attacker) or Special (Gen I doesn't separate)
- D = Defense (defender) or Special
- Modifiers = Type Effectiveness × STAB × Critical Hit × Random (0.85-1.0)

### 4.2 Expected Damage Calculation

The agent prioritizes moves with highest **Expected Damage**:

```
ExpectedDamage = BasePower × TypeEffectiveness × STAB × Accuracy × 0.925
```

(0.925 accounts for average random roll)

### 4.3 Kill Threshold Logic

- **Guaranteed KO**: MinDamage > EnemyHP → Priority 1
- **2HKO Possible**: MaxDamage > EnemyHP → Priority 2
- **Survival Check**: If EnemyMaxDamage < MyHP × 0.25 → Safe to attack
- **Switch Required**: If EnemyMaxDamage > MyHP → Consider switching

---

## 5. Goal Oriented Action Planning (GOAP)

### 5.1 The Goal Hierarchy

```
Root Goal: GAME_COMPLETION
  │
  ├── Sub-Goal: OBTAIN_BOULDER_BADGE
  │   ├── Navigate to Pewter City
  │   ├── Enter Gym
  │   ├── Defeat Trainers
  │   └── Defeat Brock
  │
  ├── Sub-Goal: OBTAIN_CASCADE_BADGE
  │   └── (similar structure)
  │
  └── ... (all 8 badges + Elite Four)
```

### 5.2 Quest Dependency Graph

```
Critical Path Analysis:
┌─────────────────────────────────────────────────────────────────┐
│                    QUEST DEPENDENCY GRAPH                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Cut] requires [Boulder Badge]                                  │
│  [Surf] requires [Soul Badge] AND [Safari Zone Entry]           │
│  [Fly] requires [Cascade Badge]                                  │
│                                                                  │
│  The agent calculates the SHORTEST path to Credits Roll          │
│  Ignores side quests unless Run_Category = "100%"                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. System Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        PTP-01X SYSTEM ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    PERCEPTION LAYER (Chapter 1)                 │    │
│  │  Pixel Buffer → Quantization → Semantic Grid → OCR → Fusion     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                   MEMORY LAYER (Chapter 2)                      │    │
│  │  WRAM Hooks → Event Flags → Party Data → Inventory → Validation │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                 CARTOGRAPHIC LAYER (Chapter 3)                  │    │
│  │  Map Stitching → Collision Matrix → HM Dependencies → Warps     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                 NAVIGATION ENGINE (Chapter 4)                   │    │
│  │  HPA* Pathfinding → Ledge Diode Handling → Warp Transitions     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                   BATTLE SYSTEM (Chapter 5)                     │    │
│  │  Type Matrix → Damage Calc → Kill Thresholds → Switch Logic    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                 ENTITY MANAGEMENT (Chapter 6)                   │    │
│  │  Party Optimization → Evolution Management → HM Assignment      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                 INVENTORY SYSTEM (Chapter 7)                    │    │
│  │  Bag Management → Shopping Heuristics → Item Efficiency         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                 DIALOGUE SYSTEMS (Chapter 8)                    │    │
│  │  Menu State Machine → NPC Interaction → Yes/No Decisions        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                 DECISION CORE (Chapter 9)                       │    │
│  │  GOAP Planner → Goal Hierarchy → Quest Graph → Action Planning  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                 FAILSAFE PROTOCOLS (Chapter 10)                 │    │
│  │  Watchdog Timer → Black Box Logging → Error Recovery → Config   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. File Structure

```
specs/
├── ptp_01x_executive_summary.md           ← This file
├── ptp_01x_perception_layer.md            ← Chapter 1
├── ptp_01x_memory_layer.md                ← Chapter 2
├── ptp_01x_cartography_layer.md           ← Chapter 3
├── ptp_01x_navigation_engine.md           ← Chapter 4
├── ptp_01x_combat_system.md               ← Chapter 5
├── ptp_01x_entity_management.md           ← Chapter 6
├── ptp_01x_inventory_system.md            ← Chapter 7
├── ptp_01x_dialogue_systems.md            ← Chapter 8
├── ptp_01x_goap_planner.md                ← Chapter 9
├── ptp_01x_failsafe_protocols.md          ← Chapter 10
├── technical_specifications_v5_complete.md
└── base_design/
    └── index.md
```

---

## 8. Implementation Status

| Chapter | Status | Implementation File |
|---------|--------|---------------------|
| 1. Perception | Partial | `src/core/screenshots.py`, vision debug tools |
| 2. Memory | Not Started | Need WRAM hooks implementation |
| 3. Cartography | Not Started | Need map database and stitching |
| 4. Navigation | Not Started | Need HPA* pathfinding |
| 5. Combat | Partial | Basic battle detection, need full heuristics |
| 6. Entity | Not Started | Need party management |
| 7. Inventory | Not Started | Need item system |
| 8. Dialogue | Partial | Basic dialog flow |
| 9. GOAP | Not Started | Need full planning system |
| 10. Failsafe | Partial | New logger, need watchdog |

---

## 9. Conclusion

The PTP-01X architecture provides a **rigorous engineering blueprint** for solving Pokémon. By combining:

1. **Visual perception** (for context and validation)
2. **Memory access** (for ground truth)
3. **Symbolic planning** (GOAP for strategy)
4. **Heuristic optimization** (damage calc, pathfinding)

The agent achieves **superhuman precision** in a deterministic, debuggable system.

This is not "AI playing a game" — this is **mathematically solving the environment**.

---

**Document Version:** 1.0  
**Last Updated:** December 31, 2025  
**Protocol:** PTP-01X - Master Architectural Schema