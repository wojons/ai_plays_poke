# PTP-01X Specification Index

**Last Updated:** December 31, 2025  
**Total Specifications:** 16 documents  
**Total Lines:** ~53,500+

---

## Quick Reference

| Priority | File | Status | Lines | Purpose |
|----------|------|--------|-------|---------|
| 🔴 HIGH | `ptp_01x_cli_control_infrastructure.md` | ✅ COMPLETE | ~10,000 | CLI, observability, aggregation |
| 🔴 HIGH | `ptp_01x_mode_duration_tracking.md` | ✅ NEW | ~1,800 | **Loop detection, mode tracking** |
| 🔴 HIGH | `ptp_01x_api_integration.md` | ✅ NEW | ~1,500 | **API integration & error handling** |
| 🔴 HIGH | `ptp_01x_detailed/chapter_01-10_*.md` | ✅ COMPLETE | ~15,850 | Core gameplay AI |
| 🟡 MED | `ptp_01x_database_schema_design.md` | ✅ COMPLETE | ~3,000 | Database schema |
| 🟡 MED | `ptp_01x_executive_summary.md` | ✅ COMPLETE | ~500 | High-level overview |
| 🟢 REF | `base_design/index.md` | ✅ COMPLETE | ~500 | Architecture integration |

---

## Specification Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    STRATEGIC LAYER                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ptp_01x_executive_summary.md                        │   │
│  │ Executive summary and high-level vision             │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   ARCHITECTURE LAYER                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ base_design/index.md                                │   │
│  │ Architecture integration and design patterns        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   GAMEPLAY LAYER                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ptp_01x_detailed/chapter_01_vision_perception.md    │   │
│  │ ptp_01x_detailed/chapter_02_hierarchical_state_m... │   │
│  │ ... (10 chapters total)                             │   │
│  │ Core AI gameplay systems                            │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 INFRASTRUCTURE LAYER                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ptp_01x_cli_control_infrastructure.md               │   │
│  │ CLI, observability, data aggregation                │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ptp_01x_database_schema_design.md                   │   │
│  │ Database schema design                              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Complete Specification List

### 1. Strategic Specifications

#### 1.1 ptp_01x_executive_summary.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~500 |
| **Focus** | High-level project overview |
| **Use When** | Understanding project scope, explaining to stakeholders |
| **Key Sections** | Project vision, success criteria, architecture overview |

---

### 2. Architecture Specifications

#### 2.1 base_design/index.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~500 |
| **Focus** | Architecture integration |
| **Use When** | Understanding how components fit together |
| **Key Sections** | System architecture, component relationships |

---

### 3. Gameplay Specifications (10 Chapters)

All gameplay chapters follow the **spec-driven format** with:
- Mermaid flowcharts (visual logic)
- Pseudo-code snippets (implementation details)
- LLM reasoning prompts (AI thought process)

#### 3.1 chapter_01_vision_perception.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~1,500 |
| **Focus** | Visual processing pipeline |
| **Components** | Pixel normalization, OCR, sprite recognition, battle menu detection |
| **Dependencies** | None (root system) |

#### 3.2 chapter_02_hierarchical_state_machine.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~1,200 |
| **Focus** | State management |
| **Components** | Bootstrap sequence, navigation loop, combat state machine, interrupts |
| **Dependencies** | Chapter 1 (vision) |

#### 3.3 chapter_03_tactical_combat_heuristics.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~1,300 |
| **Focus** | Combat decision-making |
| **Components** | Damage formulas, type effectiveness, move selection, catch logic |
| **Dependencies** | Chapter 1, Chapter 2 |

#### 3.4 chapter_04_world_navigation.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~1,500 |
| **Focus** | Pathfinding and exploration |
| **Components** | A* pathfinding, HM dependencies, puzzle-solving, route optimization |
| **Dependencies** | Chapter 1, Chapter 2 |

#### 3.5 chapter_05_data_persistence.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~1,400 |
| **Focus** | Memory and knowledge management |
| **Components** | Objective stack, knowledge base, inventory tracking, PC management |
| **Dependencies** | All chapters |

#### 3.6 chapter_06_entity_management.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~1,650 |
| **Focus** | Party optimization |
| **Components** | Carry score, evolution strategy, team composition, experience distribution |
| **Dependencies** | Chapter 1, Chapter 3, Chapter 5 |

#### 3.7 chapter_07_inventory_system.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~1,400 |
| **Focus** | Item logistics |
| **Components** | Shopping heuristics, Pokemon Center protocol, item usage, breeding |
| **Dependencies** | Chapter 1, Chapter 2, Chapter 5 |

#### 3.8 chapter_08_dialogue_systems.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~1,600 |
| **Focus** | Text and menu processing |
| **Components** | Text recognition, menu navigation, intent classification, knowledge integration |
| **Dependencies** | Chapter 1, Chapter 5 |

#### 3.9 chapter_09_goap_decision_core.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~1,800 |
| **Focus** | Goal planning and execution |
| **Components** | GOAP planner, hierarchical layers, goal prioritization, action execution |
| **Dependencies** | All chapters (central coordinator) |

#### 3.10 chapter_10_failsafe_protocols.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~1,500 |
| **Focus** | System integrity |
| **Components** | Confidence scoring, softlock detection, emergency recovery, death spiral prevention |
| **Dependencies** | All chapters |

**Gameplay Total:** ~15,850 lines

---

### 4. Infrastructure Specifications

#### 4.1 ptp_01x_cli_control_infrastructure.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~10,000 |
| **Focus** | Operational control plane |
| **Components** | CLI flags, observability dashboard, data aggregation, version management |
| **Sub-components** | Tick rate control, screenshot management, command buffering, snapshots, parallel execution |
| **Use When** | Implementing run control, monitoring, data analysis |

**Key Sections:**
1. Executive Summary
2. CLI Flag Specifications (40+ flags)
3. Observability & Diagnostics (API endpoints)
4. Data Aggregation Architecture (SQLite + PostgreSQL)
5. Schema & Config Evolution (version management)
6. Failure Modes & Recovery (error handling)
7. Implementation Roadmap (4-week plan)

#### 4.2 ptp_01x_database_schema_design.md
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COMPLETE |
| **Lines** | ~3,000 |
| **Focus** | Database schema design |
| **Components** | Per-run SQLite schema, central PostgreSQL schema, aggregation queries |
| **Tables** | 12 per-run tables, 6 central tables, 3 materialized views |
| **Use When** | Implementing data storage, analytics, benchmarking |

**Database Schema Summary:**
- **Per-Run (SQLite):** sessions, runs, pokemon_party, battles, battle_turns, decisions, navigation_events, inventory_transactions, objectives, errors, performance_metrics, ai_model_configurations, screenshots
- **Central (PostgreSQL):** aggregated_runs, aggregated_decisions, aggregated_battles, model_performance
- **Views:** model_comparison, battle_analysis, cost_analysis

#### 4.3 ptp_01x_mode_duration_tracking.md ⭐ NEW
| Attribute | Value |
|-----------|-------|
| **Status** | ✅ NEW (CRITICAL GAP FILLED) |
| **Lines** | ~1,800 |
| **Focus** | Loop detection, mode duration tracking, adaptive break-out |
| **Components** | Mode classifier, duration tracker, profile learner, anomaly detector, break-out manager, escalation engine |
| **Key Innovation** | Learns normal duration for each mode (e.g., wild battles normally 30-120s) and triggers break-out when exceeding statistical thresholds |
| **Use When** | Preventing infinite loops, detecting stuck states, implementing adaptive timeouts |

**Problem Solved:**
- **Before:** Fixed 30-second battle stall detection couldn't distinguish normal 5-minute battles from abnormal loops
- **After:** Learns that gym battles normally take 10-30 minutes, triggers break-out only when exceeding p95/p99 thresholds

**Key Sections:**
1. System Architecture
2. Mode Classification (20+ mode/sub-mode combinations)
3. Duration Tracking Engine (real-time + cumulative)
4. Learned Duration Profiles (EWMA learning)
5. Statistical Anomaly Detection (z-score, percentiles)
6. Adaptive Break-out Mechanisms (success rate tracking)
7. Escalation Protocols (integrates with Chapter 10)
8. Integration Points (HSM, Failsafe, CLI)
9. Implementation Roadmap (5 weeks)

---

## Integration Matrix

### Data Flow Between Gameplay Systems

```
Chapter 1 (Vision) → All chapters (provides visual input)
Chapter 2 (HSM) ←→ Chapter 9 (GOAP) (state management)
Chapter 3 (Combat) → Chapter 6 (Entity), Chapter 7 (Inventory)
Chapter 4 (Navigation) → Chapter 7 (Shopping), Chapter 10 (Failsafe)
Chapter 5 (Data) ←→ Chapter 8 (Dialogue) (knowledge base)
Chapter 6 (Entity) → Chapter 9 (GOAP) (party optimization)
Chapter 7 (Inventory) → Chapter 8 (Dialogue) (shopping triggers)
Chapter 8 (Dialogue) → Chapter 5 (Data), Chapter 9 (GOAP) (quests)
Chapter 9 (GOAP) → All chapters (action execution)
Chapter 10 (Failsafe) → All chapters (emergency recovery)
```

### Infrastructure Dependencies

```
CLI Control → All Gameplay Chapters (provides execution framework)
Observability → All Gameplay Chapters (provides monitoring)
Data Aggregation → All Gameplay Chapters (provides persistence)
Version Management → All Systems (provides evolution support)
Mode Duration Tracking → Chapter 2 (HSM), Chapter 10 (Failsafe), Chapter 9 (GOAP)
```

---

## Implementation Order

### Recommended: Infrastructure First

**Phase 0.5: Infrastructure (4 weeks)**
1. CLI Flag System (Week 1)
2. Data Aggregation (Week 2)
3. Observability Dashboard (Week 3)
4. Version Management (Week 4)

**Phase 0.6: Mode Duration Tracking (4 weeks) ⭐ NEW**
1. Core Duration Tracking (Week 1)
2. Profile Learning (Week 2)
3. Anomaly Detection (Week 3)
4. Escalation Integration (Week 4)

**Then: Gameplay Implementation**

**Phase 1: Foundation (2 chapters)**
- Chapter 1: Vision & Perception
- Chapter 2: Hierarchical State Machine

**Phase 2: Core Gameplay (4 chapters)**
- Chapter 3: Tactical Combat
- Chapter 4: World Navigation
- Chapter 5: Data Persistence
- Chapter 6: Entity Management

**Phase 3: Advanced Features (4 chapters)**
- Chapter 7: Inventory System
- Chapter 8: Dialogue Systems
- Chapter 9: GOAP Decision Core
- Chapter 10: Failsafe Protocols

**Phase 4: Integration & Testing**
- Connect all subsystems
- End-to-end testing
- Performance optimization

---

## File Locations

```
/config/workspace/ai_plays_poke/specs/
├── ptp_01x_cli_control_infrastructure.md    ← PRIMARY (Infrastructure)
├── ptp_01x_mode_duration_tracking.md        ← PRIMARY (Loop Detection) ⭐ NEW
├── ptp_01x_database_schema_design.md        ← PRIMARY (Data)
├── ptp_01x_executive_summary.md             ← STRATEGIC
├── base_design/
│   └── index.md                             ← ARCHITECTURE
├── ptp_01x_detailed/
│   ├── chapter_01_vision_perception.md      ← GAMEPLAY
│   ├── chapter_02_hierarchical_state_m...   ← GAMEPLAY
│   ├── chapter_03_tactical_combat_heur...   ← GAMEPLAY
│   ├── chapter_04_world_navigation.md       ← GAMEPLAY
│   ├── chapter_05_data_persistence.md       ← GAMEPLAY
│   ├── chapter_06_entity_management.md      ← GAMEPLAY
│   ├── chapter_07_inventory_system.md       ← GAMEPLAY
│   ├── chapter_08_dialogue_systems.md       ← GAMEPLAY
│   ├── chapter_09_goap_decision_core.md     ← GAMEPLAY
│   ├── chapter_10_failsafe_protocols.md     ← GAMEPLAY
│   └── SPECIFICATION_COMPLETE.md            ← SUMMARY
├── ptp_01x_chapter_01_perception_layer.md   ← LEGACY (ignore)
├── ptp_01x_chapter_02_memory_layer.md       ← LEGACY (ignore)
├── ... (other legacy files)
└── SPEC_INDEX.md                            ← THIS FILE
```

---

## Legacy Files (Do Not Use)

The following files are from earlier design phases and are superseded by the current specifications:

| File | Reason for Deprecation |
|------|------------------------|
| `ptp_01x_chapter_01-10_*.md` | Replaced by `ptp_01x_detailed/chapter_*.md` |
| `technical_specifications*.md` | Replaced by detailed chapter specs |
| `ptp_01x_chapter_*.md` | Replaced by detailed chapter specs |

**Always use files from `ptp_01x_detailed/` for gameplay specs.**

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-29 | v1.0 | Initial spec files created |
| 2025-12-31 | v2.0 | All 10 chapters completed |
| 2025-12-31 | v3.0 | CLI infrastructure spec added |
| 2025-12-31 | v3.1 | Spec index created |
| 2025-12-31 | v3.2 | **Mode duration tracking spec added (CRITICAL GAP FILLED)** |

---

*This index is automatically maintained during specification updates.*
*Last update: December 31, 2025*