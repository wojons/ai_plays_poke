# PTP-01X Database Schema Design Specification

**Version:** 1.0  
**Status:** DRAFT - CRITICAL FOR BENCHMARKING  
**Purpose:** Complete database schema for AI Pokemon gameplay benchmarking system  
**Author:** PTP-01X Architecture Team  
**Date:** December 31, 2025  

---

## 1. DATABASE DESIGN PHILOSOPHY

### 1.1 Why This Database Matters

This is NOT just a logging system. This is a **benchmarking infrastructure** for measuring AI model performance in long-horizon dynamic environments. The database must support:

- **Performance Metrics**: Tick counts, decision latencies, action success rates
- **Comparative Analysis**: Track different AI model runs and compare results
- **Progression Tracking**: Pokemon levels, badge counts, story progression
- **Battle Analytics**: Win/loss records, damage dealt/taken, move effectiveness
- **Error Analysis**: Softlock detection, recovery success rates, failure patterns
- **Resource Efficiency**: Money management, item usage, PP conservation

### 1.2 Database Design Principles

**Principle 1: Comprehensive Tracking**
Every significant event must be logged with sufficient detail for later analysis.

**Principle 2: Time-Series Awareness**
The database must support temporal queries to track performance over time.

**Principle 3: Entity Relationship Clarity**
Clear relationships between sessions, runs, battles, and individual decisions.

**Principle 4: Benchmark-Ready Queries**
Pre-defined queries for common benchmarking scenarios.

**Principle 5: Scalability**
Schema must support 100+ hour gameplay sessions with millions of records.

---

## 2. CORE DATABASE SCHEMA

### 2.1 Entity Relationship Diagram

```mermaid
erDiagram
    SESSIONS ||--o{ RUNS : contains
    SESSIONS {
        string session_id PK
        datetime start_time
        datetime end_time
        string ai_model_version
        string rom_version
        string environment
        json configuration
    }
    
    RUNS ||--o{ SESSIONS : belongs_to
    RUNS {
        string run_id PK
        string session_id FK
        datetime start_time
        datetime end_time
        string initial_state
        string final_state
        string completion_status
        int total_ticks
        int total_battles
        int victories
        int defeats
        int badges_earned
        float final_money
        int pokemon_caught
        int highest_level
        string termination_reason
    }
    
    RUNS ||--o{ POKEMON_PARTY : has
    RUNS ||--o{ BATTLES : contains
    RUNS ||--o{ DECISIONS : generates
    RUNS ||--o{ NAVIGATION_EVENTS : logs
    RUNS ||--o{ INVENTORY_TRANSACTIONS : tracks
    RUNS ||--o{ OBJECTIVES : tracks
    RUNS ||--o{ ERRORS : records
    
    POKEMON_PARTY {
        string pokemon_id PK
        string run_id FK
        string species
        string nickname
        int level
        int current_hp
        int max_hp
        int experience
        string nature
        string ability
        json moves
        json ivs
        json evs
        string status
        datetime caught_time
        string caught_location
        int times_battled
        int victories
        int defeats
        int experience_gained
    }
    
    BATTLES {
        string battle_id PK
        string run_id FK
        datetime start_time
        datetime end_time
        string battle_type
        string opponent_name
        string opponent_species
        int opponent_level
        string battle_outcome
        int turns
        int player_pokemon_fainted
        int opponent_pokemon_fainted
        int damage_dealt
        int damage_taken
        int experience_gained
        int money_gained
        json player_team
        json opponent_team
        json battle_log
    }
    
    BATTLE_TURNS {
        string turn_id PK
        string battle_id FK
        int turn_number
        string player_action
        string player_move
        int player_damage
        string opponent_action
        string opponent_move
        int opponent_damage
        string turn_outcome
        json battle_state
    }
    
    DECISIONS {
        string decision_id PK
        string run_id FK
        datetime timestamp
        string game_state
        string decision_type
        string reasoning
        string action_taken
        float confidence_score
        int decision_latency_ms
        string model_used
        int tokens_consumed
        float api_cost
        string context_summary
        json full_context
        json ai_response
    }
    
    NAVIGATION_EVENTS {
        string nav_event_id PK
        string run_id FK
        datetime timestamp
        string event_type
        string from_location
        string to_location
        int ticks_elapsed
        int distance_tiles
        string path_taken
        boolean encounter_occurred
        string encounter_type
        boolean success
        string failure_reason
    }
    
    INVENTORY_TRANSACTIONS {
        string transaction_id PK
        string run_id FK
        datetime timestamp
        string transaction_type
        string item_name
        int quantity_change
        int new_quantity
        int money_before
        int money_after
        string source
        string reason
    }
    
    OBJECTIVES {
        string objective_id PK
        string run_id FK
        datetime created_time
        string objective_type
        string description
        string status
        datetime completed_time
        int ticks_to_complete
        json requirements
    }
    
    ERRORS {
        string error_id PK
        string run_id FK
        datetime timestamp
        string error_type
        string error_severity
        string error_message
        string error_context
        string recovery_action
        boolean recovery_success
        int recovery_ticks
        json stack_trace
    }
    
    PERFORMANCE_METRICS {
        string metric_id PK
        string run_id FK
        datetime timestamp
        string metric_type
        string metric_name
        float metric_value
        string metric_unit
        json metadata
    }
    
    AI_MODEL_CONFIGURATIONS {
        string config_id PK
        string model_name
        string model_version
        datetime timestamp
        json parameters
        json system_prompt
        json model_settings
    }
```

---

## 3. DETAILED SCHEMA DEFINITIONS

### 3.1 SESSIONS Table

**Purpose:** Track AI benchmarking sessions across multiple model versions

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    ai_model_version TEXT NOT NULL,
    rom_version TEXT NOT NULL,
    environment TEXT NOT NULL,
    configuration JSON,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sessions_model ON sessions(ai_model_version);
CREATE INDEX IF NOT EXISTS idx_sessions_time ON sessions(start_time);
```

**Sample Data:**
```json
{
    "session_id": "sess_20251231_060000_a1b2c3d4",
    "start_time": "2025-12-31T06:00:00Z",
    "end_time": null,
    "ai_model_version": "gpt-4o-2024-12-01",
    "rom_version": "Pokemon Red (UE) [SGB Enabled] [Original]",
    "environment": "linux_x64_pyboy_2.6.1",
    "configuration": {
        "max_ticks": 1000000,
        "screenshot_interval": 60,
        "enable_logging": true,
        "log_level": "DEBUG"
    },
    "notes": "Long-duration benchmark test for GPT-4o performance"
}
```

### 3.2 RUNS Table

**Purpose:** Individual AI gameplay runs within a session

```sql
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    initial_state JSON NOT NULL,
    final_state JSON,
    completion_status TEXT NOT NULL,
    total_ticks INTEGER DEFAULT 0,
    total_battles INTEGER DEFAULT 0,
    victories INTEGER DEFAULT 0,
    defeats INTEGER DEFAULT 0,
    badges_earned INTEGER DEFAULT 0,
    final_money INTEGER DEFAULT 0,
    pokemon_caught INTEGER DEFAULT 0,
    highest_level INTEGER DEFAULT 0,
    termination_reason TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
CREATE INDEX IF NOT EXISTS idx_runs_completion ON runs(completion_status);
CREATE INDEX IF NOT EXISTS idx_runs_ticks ON runs(total_ticks);
```

**Completion Status Values:**
- `IN_PROGRESS` - Run still active
- `COMPLETED_CHAMPION` - Defeated Elite Four and became champion
- `COMPLETED_STORY` - Finished main story (optional completion)
- `TERMINATED_TIMEOUT` - Exceeded max tick limit
- `TERMINATED_ERROR` - Critical error occurred
- `TERMINATED_MANUAL` - User manually stopped
- `TERMINATED_SOFTLOCK` - Stuck in impossible situation
- `TERMINATED_DEATH_SPIRAL` - Unrecoverable resource depletion

**Sample Data:**
```json
{
    "run_id": "run_20251231_060001_e5f6g7h8",
    "session_id": "sess_20251231_060000_a1b2c3d4",
    "start_time": "2025-12-31T06:00:01Z",
    "end_time": "2025-12-31T18:45:23Z",
    "initial_state": {
        "location": "Pallet Town",
        "money": 3000,
        "badges": 0,
        "party": [{"species": "Pikachu", "level": 5}]
    },
    "final_state": {
        "location": "Victory Road",
        "money": 45000,
        "badges": 7,
        "party": [
            {"species": "Charizard", "level": 67},
            {"species": "Blastoise", "level": 65},
            {"species": "Pikachu", "level": 58}
        ]
    },
    "completion_status": "TERMINATED_TIMEOUT",
    "total_ticks": 458923,
    "total_battles": 1247,
    "victories": 1189,
    "defeats": 58,
    "badges_earned": 7,
    "final_money": 45000,
    "pokemon_caught": 12,
    "highest_level": 67,
    "termination_reason": "Reached max tick limit (500000)"
}
```

### 3.3 POKEMON_PARTY Table

**Purpose:** Track Pokemon caught, trained, and released during a run

```sql
CREATE TABLE IF NOT EXISTS pokemon_party (
    pokemon_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    species TEXT NOT NULL,
    nickname TEXT,
    level INTEGER DEFAULT 5,
    current_hp INTEGER,
    max_hp INTEGER,
    experience INTEGER DEFAULT 0,
    nature TEXT,
    ability TEXT,
    moves JSON,
    ivs JSON,
    evs JSON,
    status TEXT DEFAULT 'HEALTHY',
    caught_time DATETIME,
    caught_location TEXT,
    times_battled INTEGER DEFAULT 0,
    victories INTEGER DEFAULT 0,
    defeats INTEGER DEFAULT 0,
    experience_gained INTEGER DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_pokemon_run ON pokemon_party(run_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_species ON pokemon_party(species);
CREATE INDEX IF NOT EXISTS idx_pokemon_level ON pokemon_party(level);
```

**Sample Data:**
```json
{
    "pokemon_id": "poke_001_a1b2c3d4",
    "run_id": "run_20251231_060001_e5f6g7h8",
    "species": "Charizard",
    "nickname": "Char",
    "level": 67,
    "current_hp": 180,
    "max_hp": 180,
    "experience": 250000,
    "nature": "Adamant",
    "ability": "Blaze",
    "moves": [
        {"name": "Flamethrower", "pp": 25, "type": "Fire"},
        {"name": "Slash", "pp": 30, "type": "Normal"},
        {"name": "Dragon Claw", "pp": 15, "type": "Dragon"},
        {"name": "Fire Blast", "pp": 5, "type": "Fire"}
    ],
    "ivs": {"hp": 31, "attack": 31, "defense": 30, "speed": 31, "sp_atk": 25, "sp_def": 28},
    "evs": {"attack": 252, "speed": 252, "hp": 6},
    "status": "HEALTHY",
    "caught_time": "2025-12-31T08:30:00Z",
    "caught_location": "Route 16",
    "times_battled": 156,
    "victories": 142,
    "defeates": 14,
    "experience_gained": 125000
}
```

### 3.4 BATTLES Table

**Purpose:** Track all battles during a run

```sql
CREATE TABLE IF NOT EXISTS battles (
    battle_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    battle_type TEXT NOT NULL,
    opponent_name TEXT,
    opponent_species TEXT NOT NULL,
    opponent_level INTEGER NOT NULL,
    battle_outcome TEXT NOT NULL,
    turns INTEGER DEFAULT 0,
    player_pokemon_fainted INTEGER DEFAULT 0,
    opponent_pokemon_fainted INTEGER DEFAULT 0,
    damage_dealt INTEGER DEFAULT 0,
    damage_taken INTEGER DEFAULT 0,
    experience_gained INTEGER DEFAULT 0,
    money_gained INTEGER DEFAULT 0,
    player_team JSON,
    opponent_team JSON,
    battle_log JSON,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_battles_run ON battles(run_id);
CREATE INDEX IF NOT EXISTS idx_battles_type ON battles(battle_type);
CREATE INDEX IF NOT EXISTS idx_battles_outcome ON battles(battle_outcome);
```

**Battle Type Values:**
- `WILD_POKEMON` - Random encounter
- `TRAINER_BATTLE` - Named trainer
- `GYM_LEADER` - Gym battle
- `ELITE_FOUR` - Elite Four member
- `CHAMPION` - Final champion battle
- `RIVAL_BATTLE` - Rival encounters
- `TEAM_ROCKET` - Team Rocket grunt battles

**Battle Outcome Values:**
- `VICTORY` - Won the battle
- `DEFEAT` - Lost the battle
- `DRAW` - No winner (both fainted last Pokemon)
- `RUN_AWAY` - Successfully escaped
- `FORFEIT` - Could not continue (no PP, no items)

**Sample Data:**
```json
{
    "battle_id": "bat_001_123456789",
    "run_id": "run_20251231_060001_e5f6g7h8",
    "start_time": "2025-12-31T12:30:00Z",
    "end_time": "2025-12-31T12:32:45Z",
    "battle_type": "GYM_LEADER",
    "opponent_name": "Misty",
    "opponent_species": "Starmie",
    "opponent_level": 54,
    "battle_outcome": "VICTORY",
    "turns": 8,
    "player_pokemon_fainted": 0,
    "opponent_pokemon_fainted": 3,
    "damage_dealt": 450,
    "damage_taken": 120,
    "experience_gained": 2500,
    "money_gained": 2700,
    "player_team": [
        {"species": "Charizard", "level": 58, "hp_after": 180, "moves_used": ["Flamethrower", "Slash"]}
    ],
    "opponent_team": [
        {"species": "Starmie", "level": 54, "fainted": true},
        {"species": "Horsea", "level": 51, "fainted": true},
        {"species": "Goldeen", "level": 49, "fainted": true}
    ],
    "battle_log": [
        {"turn": 1, "player_action": "Flamethrower", "damage": 85, "effectiveness": "SUPER"},
        {"turn": 1, "opponent_action": "Hydro Pump", "damage": 45, "hit": true},
        {"turn": 2, "player_action": "Slash", "damage": 72, "effectiveness": "NORMAL"}
    ]
}
```

### 3.5 BATTLE_TURNS Table

**Purpose:** Granular turn-by-turn battle analysis

```sql
CREATE TABLE IF NOT EXISTS battle_turns (
    turn_id TEXT PRIMARY KEY,
    battle_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    player_action TEXT,
    player_move TEXT,
    player_damage INTEGER,
    opponent_action TEXT,
    opponent_move TEXT,
    opponent_damage INTEGER,
    turn_outcome TEXT,
    battle_state JSON,
    FOREIGN KEY (battle_id) REFERENCES battles(battle_id)
);

CREATE INDEX IF NOT EXISTS idx_turns_battle ON battle_turns(battle_id);
```

### 3.6 DECISIONS Table

**Purpose:** Track every AI decision with context and performance metrics

```sql
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    game_state TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    reasoning TEXT,
    action_taken TEXT NOT NULL,
    confidence_score REAL,
    decision_latency_ms REAL,
    model_used TEXT,
    tokens_consumed INTEGER,
    api_cost REAL,
    context_summary TEXT,
    full_context JSON,
    ai_response JSON,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_decisions_run ON decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_decisions_type ON decisions(decision_type);
CREATE INDEX IF NOT EXISTS idx_decisions_latency ON decisions(decision_latency_ms);
CREATE INDEX IF NOT EXISTS idx_decisions_time ON decisions(timestamp);
```

**Decision Type Values:**
- `BATTLE_MOVE` - Selected a battle move
- `BATTLE_SWITCH` - Switched Pokemon
- `BATTLE_ITEM` - Used an item
- `BATTLE_RUN` - Attempted to run
- `NAVIGATION_MOVE` - Movement direction
- `MENU_SELECT` - Menu option selected
- `DIALOG_ADVANCE` - Advanced dialogue
- `DIALOG_CHOICE` - Made a dialogue choice
- `INTERACTION` - Interacted with NPC/object
- `HEALING` - Used Pokemon Center/item to heal
- `SHOPPING_BUY` - Purchased item
- `SHOPPING_SOLD` - Sold item
- `OBJECTIVE_UPDATE` - Updated quest objective
- `EMERGENCY_RESPONSE` - Emergency recovery action

**Sample Data:**
```json
{
    "decision_id": "dec_001_abcdef12",
    "run_id": "run_20251231_060001_e5f6g7h8",
    "timestamp": "2025-12-31T12:30:05Z",
    "game_state": "BATTLE_GYM_MISTY",
    "decision_type": "BATTLE_MOVE",
    "reasoning": "Starmie is Water-type, Fire-type move will be super effective. Flamethrower has 85% accuracy and deals 85 damage on average. Opponent at 65% HP, this could knock out.",
    "action_taken": "FLAMETHROWER",
    "confidence_score": 0.87,
    "decision_latency_ms": 2450,
    "model_used": "gpt-4o",
    "tokens_consumed": 2847,
    "api_cost": 0.0152,
    "context_summary": "Turn 1 vs Misty's Starmie (Lv54, 65% HP). Charizard at full HP. Opponent team: Starmie, Horsea, Goldeen.",
    "full_context": {
        "player_pokemon": {"species": "Charizard", "level": 58, "hp": 180, "moves": [...]},
        "opponent_pokemon": {"species": "Starmie", "level": 54, "hp": 117, "moves": [...]},
        "battle_history": [],
        "party_status": [...],
        "inventory_status": {...}
    },
    "ai_response": {
        "reasoning": "Analyzing move options for Charizard against Starmie...",
        "action": "Flamethrower",
        "confidence": 0.87
    }
}
```

### 3.7 NAVIGATION_EVENTS Table

**Purpose:** Track all movement and exploration events

```sql
CREATE TABLE IF NOT EXISTS navigation_events (
    nav_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    event_type TEXT NOT NULL,
    from_location TEXT,
    to_location TEXT,
    ticks_elapsed INTEGER,
    distance_tiles INTEGER,
    path_taken JSON,
    encounter_occurred BOOLEAN,
    encounter_type TEXT,
    success BOOLEAN,
    failure_reason TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_nav_run ON navigation_events(run_id);
CREATE INDEX IF NOT EXISTS idx_nav_type ON navigation_events(event_type);
CREATE INDEX IF NOT EXISTS idx_nav_encounter ON navigation_events(encounter_occurred);
```

**Event Type Values:**
- `MOVE_NORTH` - Moved north
- `MOVE_SOUTH` - Moved south
- `MOVE_EAST` - Moved east
- `MOVE_WEST` - Moved west
- `WARP` - Used warp (stairs, cave entrance, etc.)
- `LEDGE_JUMP` - Jumped down ledge
- `SURF_MOVE` - Used Surf to move on water
- `WATER_ENTRY` - Entered water
- `WATER_EXIT` - Exited water
- `TRIGGER_INTERACTION` - Triggered NPC/object interaction

### 3.8 INVENTORY_TRANSACTIONS Table

**Purpose:** Track all item acquisitions and usage

```sql
CREATE TABLE IF NOT EXISTS inventory_transactions (
    transaction_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    transaction_type TEXT NOT NULL,
    item_name TEXT NOT NULL,
    quantity_change INTEGER NOT NULL,
    new_quantity INTEGER,
    money_before INTEGER,
    money_after INTEGER,
    source TEXT,
    reason TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_inventory_run ON inventory_transactions(run_id);
CREATE INDEX IF NOT EXISTS idx_inventory_type ON inventory_transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_inventory_item ON inventory_transactions(item_name);
```

**Transaction Type Values:**
- `PURCHASE` - Bought from shop
- `SELL` - Sold to shop
- `USE_ITEM` - Used item in battle
- `USE_ITEM_OUTSIDE` - Used item outside battle
- `RECEIVE_ITEM` - Received from NPC/gift
- `FIND_ITEM` - Found on ground
- `DROP_ITEM` - Dropped item
- `TRANSFER_PC` - Transferred to/from PC

### 3.9 OBJECTIVES Table

**Purpose:** Track quest and story objectives

```sql
CREATE TABLE IF NOT EXISTS objectives (
    objective_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    created_time DATETIME NOT NULL,
    objective_type TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    completed_time DATETIME,
    ticks_to_complete INTEGER,
    requirements JSON,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_objectives_run ON objectives(run_id);
CREATE INDEX IF NOT EXISTS idx_objectives_type ON objectives(objective_type);
CREATE INDEX IF NOT EXISTS idx_objectives_status ON objectives(status);
```

**Objective Type Values:**
- `STORY_MILESTONE` - Major story progression
- `GYM_BADGE` - Gym badge acquisition
- `CAPTURE_POKEMON` - Catch specific Pokemon
- `LEVEL_TARGET` - Reach specific level
- `HM_OBTAIN` - Obtain HM
- `ITEM_ACQUISITION` - Get specific item
- `NPC_INTERACTION` - Talk to specific NPC
- `LOCATION_REACH` - Reach specific location

### 3.10 ERRORS Table

**Purpose:** Track all errors and recovery actions

```sql
CREATE TABLE IF NOT EXISTS errors (
    error_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    error_type TEXT NOT NULL,
    error_severity TEXT NOT NULL,
    error_message TEXT,
    error_context TEXT,
    recovery_action TEXT,
    recovery_success BOOLEAN,
    recovery_ticks INTEGER,
    stack_trace JSON,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_errors_run ON errors(run_id);
CREATE INDEX IF NOT EXISTS idx_errors_type ON errors(error_type);
CREATE INDEX IF NOT EXISTS idx_errors_severity ON errors(error_severity);
```

**Error Type Values:**
- `SOFTLOCK_DETECTED` - System detected softlock
- `VISION_FAILURE` - OCR/vision system failed
- `API_ERROR` - OpenRouter API error
- `NAVIGATION_FAILURE` - Could not reach destination
- `BATTLE_LOSS` - Lost important battle
- `ITEM_DEPLETED` - Critical item ran out
- `PP_EXHAUSTED` - All PP depleted
- `STATE_CORRUPTION` - Invalid game state detected
- `RECOVERY_FAILED` - Recovery attempt failed
- `UNKNOWN_ERROR` - Unclassified error

**Error Severity Values:**
- `INFO` - Minor issue, no action needed
- `WARNING` - Potential problem, monitor closely
- `ERROR` - Significant issue, recovery triggered
- `CRITICAL` - System at risk, immediate intervention needed

### 3.11 PERFORMANCE_METRICS Table

**Purpose:** Track performance metrics over time

```sql
CREATE TABLE IF NOT EXISTS performance_metrics (
    metric_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    metric_type TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT,
    metadata JSON,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_metrics_run ON performance_metrics(run_id);
CREATE INDEX IF NOT EXISTS idx_metrics_type ON performance_metrics(metric_type);
CREATE INDEX IF NOT EXISTS idx_metrics_time ON performance_metrics(timestamp);
```

**Metric Type Values:**
- `LATENCY` - Response time metrics
- `THROUGHPUT` - Operations per second
- `RESOURCE_USAGE` - CPU, memory, disk usage
- `API_COST` - Cost metrics
- `TOKEN_USAGE` - LLM token consumption
- `DECISION_RATE` - Decisions per second
- `BATTLE_WIN_RATE` - Win percentage
- `NAVIGATION_EFFICIENCY` - Pathfinding success rate
- `ERROR_RATE` - Errors per thousand ticks

### 3.12 AI_MODEL_CONFIGURATIONS Table

**Purpose:** Track AI model configurations for benchmarking comparison

```sql
CREATE TABLE IF NOT EXISTS ai_model_configurations (
    config_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    parameters JSON NOT NULL,
    system_prompt JSON,
    model_settings JSON,
    FOREIGN KEY (config_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_config_model ON ai_model_configurations(model_name);
```

---

## 4. BENCHMARK QUERIES

### 4.1 Performance Comparison Queries

```sql
-- Compare total ticks to champion across models
SELECT 
    s.ai_model_version,
    COUNT(r.run_id) as total_runs,
    AVG(r.total_ticks) as avg_ticks_to_complete,
    MIN(r.total_ticks) as best_time,
    MAX(r.total_ticks) as worst_time,
    AVG(r.victories * 100.0 / NULLIF(r.total_battles, 0)) as avg_win_rate,
    AVG(r.badges_earned) as avg_badges,
    SUM(r.final_money) / COUNT(r.run_id) as avg_money_earned
FROM sessions s
JOIN runs r ON s.session_id = r.session_id
WHERE r.completion_status IN ('COMPLETED_CHAMPION', 'COMPLETED_STORY')
GROUP BY s.ai_model_version
ORDER BY avg_ticks_to_complete ASC;
```

```sql
-- Analyze decision quality by model
SELECT 
    s.ai_model_version,
    AVG(d.confidence_score) as avg_confidence,
    AVG(d.decision_latency_ms) as avg_latency,
    COUNT(d.decision_id) as total_decisions,
    SUM(d.api_cost) as total_cost,
    AVG(d.tokens_consumed) as avg_tokens,
    COUNT(CASE WHEN d.decision_type = 'BATTLE_MOVE' THEN 1 END) as battle_decisions,
    COUNT(CASE WHEN d.decision_type = 'NAVIGATION_MOVE' THEN 1 END) as navigation_decisions
FROM sessions s
JOIN decisions d ON s.session_id = d.session_id
GROUP BY s.ai_model_version;
```

### 4.2 Battle Analysis Queries

```sql
-- Battle win rate by Pokemon species
SELECT 
    p.species,
    COUNT(b.battle_id) as total_battles,
    SUM(CASE WHEN b.battle_outcome = 'VICTORY' THEN 1 ELSE 0 END) as victories,
    AVG(b.turns) as avg_turns,
    AVG(b.damage_dealt) as avg_damage_dealt,
    AVG(b.damage_taken) as avg_damage_taken,
    AVG(CASE WHEN b.battle_type = 'GYM_LEADER' THEN 
        CASE WHEN b.battle_outcome = 'VICTORY' THEN 1 ELSE 0 END 
    END) as gym_win_rate
FROM pokemon_party p
JOIN battles b ON p.run_id = b.run_id
WHERE p.run_id = 'specific_run_id'
GROUP BY p.species;
```

### 4.3 Error Analysis Queries

```sql
-- Error frequency by type and severity
SELECT 
    e.error_type,
    e.error_severity,
    COUNT(e.error_id) as error_count,
    AVG(CASE WHEN e.recovery_success = 1 THEN 1 ELSE 0 END) as recovery_rate,
    AVG(e.recovery_ticks) as avg_recovery_time
FROM errors e
GROUP BY e.error_type, e.error_severity
ORDER BY error_count DESC;
```

### 4.4 Progression Tracking Queries

```sql
-- Level progression over time
SELECT 
    p.species,
    p.level,
    MIN(d.timestamp) as first_reached_time,
    r.total_ticks as ticks_to_reach,
    p.experience_gained as total_xp
FROM pokemon_party p
JOIN runs r ON p.run_id = r.run_id
JOIN decisions d ON r.run_id = d.run_id
WHERE d.decision_type = 'BATTLE_MOVE'
GROUP BY p.species, p.level
ORDER BY p.species, p.level;
```

---

## 5. DATA RETENTION AND ARCHIVAL

### 5.1 Retention Policy

| Data Type | Retention Period | Archival Format |
|-----------|------------------|-----------------|
| Sessions | 2 years | Compressed JSON |
| Runs | 1 year | Compressed JSON |
| Battle Details | 6 months | Compressed JSON |
| Decision Logs | 3 months | Partitioned by month |
| Error Logs | 1 year | Compressed JSON |
| Performance Metrics | 3 months | Time-series database |

### 5.2 Archival Strategy

- **Hot Storage**: Recent data (< 1 month) in main database
- **Warm Storage**: Recent data (1-6 months) in compressed format
- **Cold Storage**: Historical data (> 6 months) in S3/compatible storage

---

## 6. PERFORMANCE CONSIDERATIONS

### 6.1 Indexing Strategy

**Primary Indexes:**
- session_id, run_id (foreign keys)
- timestamp (time-range queries)
- decision_type, game_state (filtering)

**Composite Indexes:**
- (run_id, timestamp) for decision history
- (session_id, ai_model_version) for model comparison
- (battle_type, battle_outcome) for battle analysis

### 6.2 Partitioning

**Decision Logs:** Partition by date (daily partitions)
**Navigation Events:** Partition by run_id
**Performance Metrics:** Time-series partitioning

### 6.3 Query Optimization

- Pre-aggregate common metrics (hourly/daily summaries)
- Use materialized views for frequently accessed data
- Implement query timeouts to prevent expensive queries

---

## 7. IMPLEMENTATION ROADMAP

### Phase 1: Core Schema (Week 1)
- [ ] Create all tables with constraints
- [ ] Implement primary indexes
- [ ] Create migration scripts
- [ ] Set up test database with sample data

### Phase 2: Query Library (Week 2)
- [ ] Implement benchmark queries
- [ ] Create stored procedures for complex calculations
- [ ] Build performance dashboard queries
- [ ] Set up automated report generation

### Phase 3: Performance Optimization (Week 3)
- [ ] Implement partitioning strategy
- [ ] Optimize slow queries
- [ ] Set up query caching
- [ ] Implement connection pooling

### Phase 4: Integration (Week 4)
- [ ] Integrate with game loop
- [ ] Set up real-time data ingestion
- [ ] Implement error tracking integration
- [ ] Build monitoring dashboards

---

## 8. SAMPLE BENCHMARK RESULTS

### 8.1 Model Performance Comparison

| Model | Avg Ticks to Champion | Win Rate | Avg Cost/Run | Decision Latency |
|-------|----------------------|----------|---------------|------------------|
| gpt-4o | 342,156 | 94.2% | $12.45 | 2,450ms |
| gpt-4o-mini | 287,423 | 91.8% | $3.21 | 890ms |
| claude-3-opus | 298,765 | 93.5% | $18.67 | 3,120ms |
| claude-3-haiku | 312,891 | 89.2% | $4.89 | 1,340ms |

### 8.2 Battle Statistics

| Metric | Value |
|--------|-------|
| Total Battles | 1,247 |
| Victories | 1,189 (95.4%) |
| Defeats | 58 (4.6%) |
| Average Turns/Battle | 4.2 |
| Most Used Move | Flamethrower (234 uses) |
| Highest Damage Turn | 127 (Charizard vs Brock) |

---

## 9. CONCLUSION

This database schema provides a comprehensive foundation for AI Pokemon gameplay benchmarking. Key features include:

✅ **Complete Event Tracking**: Every decision, battle, and navigation event logged  
✅ **Benchmark-Ready Queries**: Pre-defined queries for common comparisons  
✅ **Performance Metrics**: Latency, cost, and efficiency tracking  
✅ **Error Analysis**: Comprehensive error and recovery tracking  
✅ **Scalability**: Partitioning and retention strategies for long-term use  
✅ **Research Quality**: Data suitable for academic benchmarking and analysis  

The schema supports the core benchmarking requirements:
1. **Comparative Analysis**: Compare different AI models
2. **Performance Tracking**: Measure efficiency over time
3. **Error Analysis**: Identify failure patterns
4. **Progression Tracking**: Monitor Pokemon and badge acquisition
5. **Cost Analysis**: Track API costs per run

**Next Steps:**
1. Implement database schema in code
2. Create migration scripts for version updates
3. Set up test database with sample data
4. Build benchmarking query library
5. Integrate with game loop for real-time logging

---

**Document Status:** ✅ **READY FOR IMPLEMENTATION**

This specification provides the complete database design needed for AI Pokemon gameplay benchmarking. The schema is production-ready and includes all necessary components for comprehensive performance tracking and analysis.