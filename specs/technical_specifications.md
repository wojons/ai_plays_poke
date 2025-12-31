# Technical Specifications: Orchestrated Intelligence Framework

## Purpose
This document provides detailed technical specifications for implementing the AI Plays Pokemon orchestrated intelligence framework. It bridges the architectural patterns defined in the Memory Bank with concrete implementation requirements.

## Audience
- Developers implementing the system
- Researchers designing experiments
- Content creators configuring the AI

## Document Structure
This spec follows a component-first approach, detailing each module's:
- **Interface Contract**: What it provides and requires
- **State Management**: Data structures and lifecycle
- **Error Handling**: Failure modes and recovery
- **Performance Requirements**: Latency, throughput, cost targets
- **Testing Strategy**: How to verify correctness

---

## 1. Core Module: Emulator Interface

### Purpose
Encapsulate PyBoy emulator operations behind a stable, testable interface.

### Interface Contract

```python
# Methods the module provides
class EmulatorInterface:
    def __init__(self, rom_path: str, save_path: Optional[str] = None)
    def start(self) -> None
    def stop(self) -> None
    def reset(self) -> None
    
    # Screen operations
    def capture_screen(self) -> np.ndarray  # 160x144 RGB array
    def get_screen_hash(self) -> str  # SHA256 of current frame
    def wait_for_screen_change(self, timeout_ms: int = 5000) -> bool
    
    # Memory operations (for validation only - not exposed to AI)
    def read_memory(self, address: int, length: int = 1) -> bytes
    def write_memory(self, address: int, data: bytes) -> None  # Test only
    def get_battle_state(self) -> BattleState  # Ground truth from RAM
    
    # Input operations
    def press_button(self, button: Button, duration_ms: int = 100) -> None
    def release_button(self, button: Button) -> None
    def send_input_sequence(self, sequence: List[Tuple[Button, int]]) -> None
    
    # Game state
    def load_state(self, slot: int = 0) -> None
    def save_state(self, slot: int = 0) -> None
    def get_game_time(self) -> int  # In-game time in frames (60fps)
    def is_running(self) -> bool
```

### Data Structures

```python
@dataclass
class BattleState:
    in_battle: bool
    battle_type: Literal["wild", "trainer", "gym", "elite_four"]  # From RAM
    turn: int
    player_pokemon: PokemonState
    enemy_pokemon: PokemonState
    last_action: Optional[str]

@dataclass
class PokemonState:
    species_id: int  # Pokemon species (1-151)
    level: int
    hp_current: int
    hp_max: int
    status: Literal["normal", "paralyzed", "asleep", "poisoned", "burned", "frozen"]
    type_1: str
    type_2: Optional[str]
    moves: List[MoveState]

@dataclass
class MoveState:
    move_id: int  # Move ID (see Pokemon data)
    pp_current: int
    pp_max: int
    type: str
    power: int

class Button(Enum):
    A = "a"
    B = "b"
    START = "start"
    SELECT = "select"
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
```

### Critical Memory Addresses (Pokemon Red)

```python
MEMORY_ADDRESSES = {
    # Battle state
    "battle_mode": 0xD057,      # 0=no battle, 1=wild, 2=trainer, 3=gym, 4=elite4
    "battle_turn": 0xD0C1,      # Current turn counter
    
    # Player Pokemon (current active)
    "player_species": 0xD126,   # Current Pokemon ID
    "player_level": 0xD144,     # Current level
    "player_hp": 0xD16C,        # Two bytes: low/high (big-endian)
    "player_hp_max": 0xD18C,    # Two bytes: low/high (big-endian)
    
    # Enemy Pokemon
    "enemy_species": 0xD124,    # Enemy Pokemon ID
    "enemy_level": 0xD14D,      # Enemy level
    "enemy_hp": 0xD11C,         # Two bytes: low/high (big-endian)
    "enemy_hp_max": 0xD11E,     # Two bytes: low/high (big-endian)
    
    # Party data
    "party_count": 0xD163,      # Number of Pokemon in party (1-6)
    "party_list": 0xD164,       # 6 * 44 bytes per Pokemon
    
    # Menu state
    "menu_state": 0xD0E8,       # Current menu (0=closed, 1=main, 2=fight, 3=bag, etc)
    "cursor_x": 0xD0E9,         # Cursor X position
    "cursor_y": 0xD0EA,         # Cursor Y position
}
```

### Performance Requirements

| Operation | Target Latency | Max Latency | Notes |
|-----------|---------------|-------------|-------|
| Screen capture | <10ms | 20ms | Native PyBoy operation |
| Memory read (1 byte) | <1ms | 5ms | Native PyBoy operation |
| Memory read (100 bytes) | <5ms | 10ms | Native PyBoy operation |
| Button press | <20ms | 50ms | Includes frame advance |
| Screen hash | <5ms | 10ms | SHA256 computation |
| Full battle state read | <50ms | 100ms | Multiple memory reads |

### Error Handling

```python
class EmulatorError(Exception):
    """Base exception for emulator operations"""
    pass

class RomLoadError(EmulatorError):
    """Failed to load ROM file"""
    pass

class MemoryReadError(EmulatorError):
    """Failed to read memory address"""
    pass

class InputError(EmulatorError):
    """Invalid input or timing issue"""
    pass

class StasisError(EmulatorError):
    """Game appears stuck or frozen"""
    pass

# Recovery strategies
RECOVERY_STRATEGIES = {
    "memory_mismatch": "dual_verify",
    "stasis_detected": "random_input",
    "invalid_state": "reset_and_reload",
    "frame_timeout": "skip_frame",
}
```

### Testing Strategy

1. **Unit Tests**: Mock PyBoy, test interface contract
2. **Integration Tests**: Real ROM, basic operations
3. **Memory Accuracy Tests**: Verify known addresses return correct values
4. **Performance Tests**: Ensure latency requirements met
5. **Reliability Tests**: 1000+ operations without failure

---

## 2. Vision Processing Module

### Purpose
Convert raw game frames into structured semantic state using vision models.

### Interface Contract

```python
class VisionProcessor:
    def __init__(self, api_key: str, model: str = "gpt-4-vision")
    
    # Screen classification
    def classify_screen(self, frame: np.ndarray) -> ScreenClassification
    def get_screen_type(self, frame: np.ndarray) -> ScreenType
    
    # Battle state extraction
    def extract_battle_state(self, frame: np.ndarray) -> Optional[ExtractedBattleState]
    def extract_enemy_pokemon(self, frame: np.ndarray) -> Optional[PokemonSpriteID]
    
    # Menu parsing
    def extract_menu_state(self, frame: np.ndarray) -> Optional[MenuState]
    def extract_cursor_position(self, frame: np.ndarray) -> Optional[Tuple[int, int]]
    
    # Stats extraction (hybrid vision + RAM validation)
    def extract_hp(self, frame: np.ndarray, ram_hp: Optional[int] = None) -> HPExtract
    def extract_level(self, frame: np.ndarray, ram_level: Optional[int] = None) -> LevelExtract
    
    # Cost optimization
    def should_process_frame(self, previous_frame: np.ndarray, current_frame: np.ndarray) -> bool
    def differential_rendering(self, frame: np.ndarray, last_processed: np.ndarray) -> ScreenRegionChanges
```

### Data Structures

```python
@dataclass
class ScreenClassification:
    screen_type: ScreenType
    confidence: float  # 0.0 to 1.0
    battle_state: Optional[BattleScreenType] = None
    menu_state: Optional[MenuScreenType] = None

class ScreenType(Enum):
    OVERWORLD = "overworld"
    BATTLE = "battle"
    MENU = "menu"
    DIALOG = "dialog"
    TRANSITION = "transition"

class BattleScreenType(Enum):
    BATTLE_START = "battle_start"
    BATTLE_MAIN = "battle_main"
    MOVE_SELECT = "move_select"
    ITEM_SELECT = "item_select"
    POKEMON_SELECT = "pokemon_select"
    BATTLE_ANIMATION = "battle_animation"
    BATTLE_END = "battle_end"

class MenuScreenType(Enum):
    MAIN_MENU = "main_menu"
    POKEMON_MENU = "pokemon_menu"
    BAG_MENU = "bag_menu"
    SAVE_MENU = "save_menu"
    OPTIONS_MENU = "options_menu"

@dataclass
class ExtractedBattleState:
    enemy_visible: bool
    enemy_sprite_id: int  # Sprite pattern hash
    enemy_hp_visible: bool
    enemy_hp_percentage: Optional[float]  # 0.0 to 1.0
    player_hp_percentage: Optional[float]
    battle_ui_visible: bool
    text_box_content: Optional[str]
```

### Prompt Templates

```python
BATTLE_STATE_PROMPT = """
Analyze this Pokemon battle screenshot and extract:
1. Is a battle currently happening? (yes/no)
2. Can you see the enemy Pokemon sprite? (yes/no)
3. What does the enemy Pokemon sprite look like? (describe key features)
4. Can you see HP bars? (yes/no)
5. Estimate enemy HP percentage (0-100)
6. Estimate player HP percentage (0-100)
7. Is there text in the dialog box? What does it say?

Respond in JSON:
{
  "in_battle": bool,
  "enemy_visible": bool,
  "enemy_sprite_description": string,
  "hp_bars_visible": bool,
  "enemy_hp_percent": float (0-100),
  "player_hp_percent": float (0-100),
  "dialog_text": string (or null)
}
"""

POKEMON_IDENTIFICATION_PROMPT = """
Identify the Pokemon in this sprite. Describe:
1. Main color/s
2. Shape and posture
3. Distinguishing features
4. Best guess at Pokemon name

Compare to Pokemon generation 1 sprites only.

Respond in JSON:
{
  "sprite_hash": string,
  "pokemon_guess": string,
  "confidence": float (0-1)
}
"""
```

### Performance Requirements

| Operation | Target Latency | Max Latency | Cost per Call | Rate Limit |
|-----------|---------------|-------------|---------------|------------|
| Screen classification | 500ms | 2000ms | $0.001-0.003 | 60/min |
| Battle state extraction | 1000ms | 3000ms | $0.003-0.01 | 60/min |
| Menu parsing | 800ms | 2500ms | $0.002-0.008 | 60/min |
| HP extraction | 500ms | 2000ms | $0.001-0.003 | 60/min |

### Cost Optimization Rules

1. **Differential Rendering**: Don't process frames identical to last processed
2. **State-Based Gate**: Only run vision when game state actually changes
3. **Confidence Thresholding**: Skip re-processing if confidence > 0.95
4. **Cache Validated Results**: Cache vision results for 100 frames if validated by RAM

```python
def should_process_frame(prev_frame: np.ndarray, curr_frame: np.ndarray) -> bool:
    """Return True if current frame is meaningfully different"""
    if prev_frame is None:
        return True
    
    # Quick hash comparison
    prev_hash = hashlib.sha256(prev_frame.tobytes()).hexdigest()
    curr_hash = hashlib.sha256(curr_frame.tobytes()).hexdigest() 
    
    if prev_hash == curr_hash:
        return False  # Identical frames
    
    # Check for semantic differences (text appearing, cursor moving)
    diff_percentage = np.mean(prev_frame != curr_frame)
    return diff_percentage > 0.01  # More than 1% different
```

### Error Handling

```python
class VisionError(Exception):
    """Base exception for vision operations"""
    pass

class APIError(VisionError):
    """API call failed (network, rate limit, etc.)"""
    pass

class ClassificationError(VisionError):
    """Failed to classify screen"""
    pass

class ExtractionError(VisionError):
    """Failed to extract information"""
    pass

class ConfidenceTooLowError(VisionError):
    """Model confidence below threshold"""
    def __init__(self, confidence: float, threshold: float):
        self.confidence = confidence
        self.threshold = threshold
```

### Testing Strategy

1. **Unit Tests**: Mock API responses, test prompt formatting
2. **Accuracy Tests**: 100+ screenshots with ground truth labels
3. **Cost Tests**: Verify differential rendering reduces API calls by >50%
4. **Validation Tests**: Compare vision results to RAM data
5. **Robustness Tests**: Test with blurry, partial, or unusual frames

### Ground Truth Dataset

```python
test_screenshots = [
    {
        "filename": "battle_charmander_vs_geodude.png",
        "ground_truth": {
            "screen_type": "battle",
            "battle_type": "battle_main",
            "enemy_pokemon": "geodude",
            "enemy_hp_percent": 100,
            "player_hp_percent": 85
        },
        "ram_truth": {
            "enemy_species": 74,  # Geodude
            "enemy_hp": 40,
            "player_species": 4,  # Charmander
            "player_hp": 38
        }
    }
    # ... 100+ test cases
]
```

---

## 3. Memory Management Module

### Purpose
Implement the Tri-Tier memory architecture for hierarchical state management.

### Interface Contract

```python
class MemoryManager:
    def __init__(self, memory_path: Path)
    
    # Observer (long-term) operations
    def load_observer_memory(self) -> ObserverMemory
    def save_observer_memory(self, memory: ObserverMemory) -> None
    def update_observer(self, event: GameEvent) -> None
    def get_journey_summary(self, max_length: int = 1000) -> str
    
    # Strategist (mid-term) operations
    def load_strategist_memory(self) -> StrategistMemory
    def save_strategist_memory(self, memory: StrategistMemory) -> None
    def get_relevant_lessons(self, context: BattleContext) -> List[Lesson]
    def add_lesson(self, lesson: Lesson, confidence: float) -> None
    def decay_memories(self) -> None  # Called periodically
    
    # Tactician (immediate) operations
    def get_tactician_context(self) -> TacticianBuffer
    def update_tactician(self, battle_state: BattleState) -> None  # Per turn
    def flush_tactician(self) -> None  # When battle ends
    
    # Memory utilities
    def backup_memory(self) -> str  # Returns backup path
    def restore_memory(self, backup_path: str) -> None
    def get_memory_stats(self) -> MemoryStats
```

### Data Structures: Observer Memory

```python
@dataclass
class ObserverMemory:
    """Persistent long-term memory spanning multiple sessions"""
    created_at: datetime
    last_updated: datetime
    
    # Journey narrative
    journey_narrative: List[JourneyEntry]  # Chronological major events
    
    # Team history
    team_history: List[TeamSnapshot]  # Major team changes
    
    # Progress tracking
    badges_earned: List[str]  # Badge names in order
    hms_unlocked: List[str]   # HM moves obtained
    important_locations: List[LocationMemory]
    
    # High-level statistics
    total_battles: int
    battles_won: int
    pokemon_caught: int
    pokedex_completion: int  # 0-151
    
    # Strategic achievements
    elite_four_attempts: int
    elite_four_wins: int
    champion_defeats: int

@dataclass
class JourneyEntry:
    """Significant event in the adventure"""
    timestamp: datetime
    event_type: Literal["gym_battle", "elite_four", "catch_pokemon", "learn_move", "story_event"]
    description: str
    context: Dict[str, Any]  # Game-specific details
    importance_score: float  # 0.0 to 1.0

@dataclass
class TeamSnapshot:
    """Team composition at a point in time"""
    timestamp: datetime
    location: str
    pokemon: List[PokemonSummary]
    avg_level: float

@dataclass
class PokemonSummary:
    species: str
    level: int
    types: List[str]
    move_count: int
```

### Data Structures: Strategist Memory

```python
@dataclass
class StrategistMemory:
    """Session-long memory of learned lessons"""
    type_lessons: List[TypeLesson]  # Type effectiveness learnings
    opponent_patterns: List[OpponentPattern]  # How specific opponents behave
    move_insights: List[MoveInsight]  # Move effectiveness data
    resource_strategies: List[ResourceStrategy]  # PP/item management
    failure_memories: List[FailureMemory]  # What went wrong
    
    # Memory metadata
    last_decay: datetime
    total_lessons: int
    avg_confidence: float

@dataclass
class TypeLesson:
    """Learned type effectiveness relationship"""
    attacker_type: str
    defender_type: str
    confidence: float  # 0.0 to 1.0
    evidence_count: int
    avg_damage_observed: float
    success_rate: float  # % of times this worked
    last_used: datetime
    priority: int  # Higher = more important

@dataclass
class OpponentPattern:
    """Pattern observed in opponent behavior"""
    opponent_id: str  # Trainer ID or Pokemon+level
    observed_behaviors: List[BehaviorObservation]
    aggression_score: float  # 0.0 to 1.0
    common_moves: List[Tuple[str, float]]  # Move + frequency
    difficulty_rating: float  # Estimated difficulty
    times_faced: int

@dataclass 
class MoveInsight:
    """Characteristics of a move observed"""
    move_name: str
    avg_damage: float
    accuracy_observed: float
    times_used: int
    effectiveness_notes: List[str]  # "Super effective on Rock types"

@dataclass
class FailureMemory:
    """What went wrong and what to avoid"""
    failure_type: Literal["type_mismatch", "underleveled", "pp_depletion", "bad_sequence"]
    context: BattleContext
    root_cause: str
    proposed_solution: str
    confidence: float
    times_repeated: int
```

### Data Structures: Tactician Buffer

```python
@dataclass
class TacticianBuffer:
    """Immediate context for current decision"""
    current_battle: Optional[BattleContext]
    last_actions: List[ActionTaken]  # Last 5 turns
    available_actions: List[ActionOption]
    strategic_override: Optional[str]  # From Strategist
    
    # Derived from battle state
    turn_number: int
    battle_has_started: bool
    last_damage_taken: int
    last_damage_dealt: int

@dataclass
class BattleContext:
    """Current battle parameters"""
    turn: int
    location: str
    enemy_pokemon: PokemonInBattle
    player_pokemon: PokemonInBattle
    battle_type: Literal["wild", "trainer", "gym", "elite_four"]
    start_time: datetime

@dataclass
class PokemonInBattle:
    species: str
    level: int
    hp_current: int
    hp_max: int
    hp_percent: float  # 0.0 to 1.0
    status: str
    moves: List[MoveInBattle]
    
@dataclass
class MoveInBattle:
    name: str
    type: str
    pp_current: int
    pp_max: int
    "effectiveness": Optional[Literal["super", "normal", "not_very", "none", "unknown"]]
    based_on: Literal["text", "ram", "pokedex"]
```

### Memory Filtering Logic

```python
def get_relevant_lessons(
    strategist_memory: StrategistMemory,
    battle_context: BattleContext
) -> List[Lesson]:
    """Retrieve lessons most relevant to current battle"""
    
    scored_lessons = []
    
    for lesson in strategist_memory.type_lessons:
        # Score based on type match
        score = 0.0
        
        # Does enemy have this type?
        if battle_context.enemy_pokemon.type_1 == lesson.defender_type or \
           battle_context.enemy_pokemon.type_2 == lesson.defender_type:
            score += lesson.confidence * 0.5
        
        # Recency bonus
        hours_since_last = (datetime.now() - lesson.last_used).total_seconds() / 3600
        recency_bonus = 1.0 / (1.0 + hours_since_last / 24)  # 24-hour half-life
        score += recency_bonus * 0.3
        
        # Experience bonus
        exp_bonus = min(lesson.evidence_count / 10.0, 1.0)  # Max at 10 uses
        score += exp_bonus * 0.2
        
        if score > 0.3:  # Threshold
            scored_lessons.append((lesson, score))
    
    # Sort by score and take top N
    scored_lessons.sort(key=lambda x: x[1], reverse=True)
    return [lesson for lesson, _ in scored_lessons[:5]]  # Top 5
```

### Memory Decay and Consolidation

```python
def decay_memories(strategist_memory: StrategistMemory):
    """Apply temporal decay to all memories"""
    now = datetime.now()
    hours_elapsed = (now - strategist_memory.last_decay).total_seconds() / 3600
    
    decay_rate = 0.01  # 1% per hour halves confidence in ~3 days
    decay_factor = 1.0 / (1.0 + decay_rate * hours_elapsed)
    
    # Apply decay
    for lesson in strategist_memory.type_lessons:
        lesson.confidence *= decay_factor
    
    # Consolidate low-confidence memories
    strategist_memory.type_lessons = [
        lesson for lesson in strategist_memory.type_lessons
        if lesson.confidence > 0.2
    ]
    
    strategist_memory.last_decay = now
```

### Memory Persistence

```python
def save_observer_memory(memory: ObserverMemory, path: Path):
    """Save with versioning and compression"""
    
    # Create backup of current
    if path.exists():
        backup_path = path.with_suffix(f".backup.{datetime.now():%Y%m%d%H%M%S}")
        path.rename(backup_path)
    
    # Save compressed version
    data = {
        "version": "1.0",
        "created_at": memory.created_at.isoformat(),
        "last_updated": memory.last_updated.isoformat(),
        "journey_narrative": [entry.__dict__ for entry in memory.journey_narrative],
        "team_history": [snap.__dict__ for snap in memory.team_history],
        # ... rest of fields
    }
    
    # Pickle for speed
    with open(path, 'wb') as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    # Also save JSON backup for manual inspection
    json_path = path.with_suffix('.json')
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
```

### Performance Requirements

| Operation | Target Latency | Max Latency | Memory Usage |
|-----------|---------------|-------------|--------------|
| Load observer memory | <100ms | 500ms | <10MB |
| Load strategist memory | <50ms | 200ms | <5MB |
| Get tactician context | <5ms | 20ms | <1MB |
| Update tactician | <1ms | 5ms | <1MB |
| Retrieve relevant lessons | <20ms | 100ms | N/A |
| Save memory | <200ms | 1000ms | N/A |

### Error Handling

```python
class MemoryError(Exception):
    """Base exception for memory operations"""
    pass

class MemoryCorruptionError(MemoryError):
    """Memory file is corrupted or invalid"""
    pass

class MemoryVersionError(MemoryError):
    """Memory file version mismatch"""
    def __init__(self, file_version: str, expected_version: str):
        self.file_version = file_version
        self.expected_version = expected_version

class MemoryOverflowError(MemoryError):
    """Memory exceeds maximum size"""
    pass

# Recovery strategies
RECOVERY_STRATEGIES = {
    "corruption": "restore_from_backup",
    "version_mismatch": "attempt_migration",
    "overflow": "consolidate_memories",
    "validation_failure": "rollback_last_update",
}
```

### Testing Strategy

1. **Unit Tests**: Test memory operations, filtering logic
2. **Persistence Tests**: Save/load with various data sizes
3. **Version Tests**: Upgrade/downgrade between versions
4. **Performance Tests**: Load 10MB+ memory files
5. **Decay Tests**: Verify temporal decay math
6. **Robustness Tests**: Corrupt files, test recovery

---

## 4. Model Orchestration Module

### Purpose
Manage multiple LLM models for different cognitive tasks with adaptive selection.

### Interface Contract

```python
class ModelOrchestrator:
    def __init__(self, config: ModelConfig)
    
    # Strategic reasoning (Thinking Model)
    def strategize(
        self,
        observer_memory: ObserverMemory,
        current_context: BattleContext,
        task_complexity: TaskComplexity
    ) -> StrategicDirective
    
    # Tactical execution (Acting Model)
    def act(
        self,
        tactician_buffer: TacticianBuffer,
        strategic_directive: StrategicDirective,
        available_actions: List[ActionOption]
    ) -> ActionDecision
    
    # Learning/analytics (Thinking Model)
    def reflect(
        self,
        battle_log: BattleLog,
        failure_analysis: Optional[FailureDetails]
    ) -> List[Insight]
    
    # Model selection
    def select_model_for_task(self, task: Task) -> ModelSelection
    def estimate_cost(self, task: Task) -> CostEstimate
    def get_model_stats(self) -> ModelUsageStats
    
    # Context building helpers
    def build_strategic_context(
        self,
        observer_memory: ObserverMemory,
        current_context: BattleContext
    ) -> str
    
    def build_tactical_context(
        self,
        tactician_buffer: TacticianBuffer
    ) -> str
```

### Data Structures

```python
@dataclass
class ModelConfig:
    """Configuration for all model endpoints"""
    thinking_model: ModelEndpoint
    acting_model: ModelEndpoint
    vision_model: ModelEndpoint
    
    default_temperature: float = 0.2
    max_retries: int = 3
    timeout_seconds: int = 30

@dataclass
class ModelEndpoint:
    provider: Literal["openai", "anthropic"] 
    model_name: str
    api_key: str
    max_tokens: int
    temperature: float
    cost_per_1k_input: float
    cost_per_1k_output: float

@dataclass
class TaskComplexity:
    """How complex is the current task?"""
    battle_type: Literal["wild", "trainer", "gym", "elite_four"]
    enemy_level: int
    player_level: int
    pokemon_remaining: int
    difficulty_modifier: float  # Derived from other factors
    
    def is_grind_battle(self) -> bool:
        """Routine wild Pokemon battle"""
        return self.battle_type == "wild" and \
               self.enemy_level < self.player_level - 5
    
    def is_boss_battle(self) -> bool:
        """Gym leader, Elite Four, or high-level trainer"""
        return self.battle_type in ["gym", "elite_four"] or \
               abs(self.enemy_level - self.player_level) > 10

@dataclass
class StrategicDirective:
    """Output from Thinking Model"""
    primary_objective: str  # "Defeat Brock's team"
    tactical_goals: List[str]  # ["Use Water moves on Geodude", "Preserve HP for Onix"]
    risk_assessment: str  # "High risk: Onix has high defense"
    suggested_approach: str  # "Lead with Water Pokemon, switch if needed"
    expected_difficulty: float  # 0.0 to 1.0
    confidence: float  # Model confidence in plan

@dataclass 
class ActionDecision:
    """Output from Acting Model"""
    action: Literal["PRESS_A", "PRESS_B", "UP", "DOWN", "LEFT", "RIGHT"]
    reasoning: str  # "Using Ember because it's super effective vs Geodude"
    confidence: float
    alternatives_considered: List[str]
    expected_outcome: str

@dataclass
class ModelSelection:
    selected_model: ModelEndpoint
    reasoning: str
    estimated_cost: float
    estimated_latency: float
    alternatives: List[Tuple[ModelEndpoint, float]]  # Alternative + cost difference
```

### Prompt Templates

```python
STRATEGIC_PLANNING_PROMPT = """
You are the Strategist - a Pokemon expert analyzing the current situation.

OBSERVER MEMORY (Journey Summary):
{observer_summary}

CURRENT CONTEXT:
- Location: {current_location}
- Situation: {battle_context}
- Goal: {primary_objective}

RELEVANT PAST EXPERIENCES:
{relevant_lessons}

POKÉDEX DATA:
{expert_knowledge}

TASK: Develop a strategic plan for this battle/challenge.

Respond in this format:
OBJECTIVE: [Primary goal in 1 sentence]
TACTICAL GOALS: [2-4 specific things to accomplish]
RISK ASSESSMENT: [What could go wrong]
APPROACH: [How to execute the strategy]
CONFIDENCE: [0.0-1.0]
"""

TACTICAL_DECISION_PROMPT = """
You are the Tactician - executing strategy moment-by-moment.

MISSION: {primary_objective}

STRATEGIC DIRECTIVE:
{tactical_goals}

CURRENT BATTLE STATE:
Our Pokemon: {player_pokemon} (HP: {player_hp}%)
Enemy: {enemy_pokemon} (HP: {enemy_hp}%)
Turn: {turn_number}

AVAILABLE ACTIONS: {available_actions}

RECENT HISTORY (Last 3 turns):
{recent_actions}

EXPERT KNOWLEDGE: {type_info}

TASK: Choose the next button press (A, B, UP, DOWN, LEFT, RIGHT).

EXPLAIN your reasoning in 1-2 sentences, then state your action.

Response format:
REASONING: [Your reasoning]
ACTION: [A/B/UP/DOWN/LEFT/RIGHT]
CONFIDENCE: [0.0-1.0]
"""
```

### Adaptive Model Selection Logic

```python
def select_model_for_task(self, task: Task) -> ModelSelection:
    """Choose the right model based on task complexity"""
    
    if task.type == "strategic_planning":
        if task.complexity.is_boss_battle():
            # Always use thinking model for boss battles
            selected = self.config.thinking_model
            reason = "Boss battle requires strategic planning"
            cost = self._estimate_cost(selected, task="strategic", context="full")
        else:
            # For routine battles, skip strategic planning sometimes
            selected = self.config.acting_model
            reason = "Routine battle - using tactical model only"
            cost = self._estimate_cost(selected, task="tactical", context="minimal")
    
    elif task.type == "tactical_decision":
        if task.complexity.is_grind_battle():
            # Fast model for grind battles
            selected = self.config.acting_model
            reason = "Grind battle - using fast acting model"
            cost = self._estimate_cost(selected, task="simple")
        else:
            # Regular model for important battles
            selected = self.config.acting_model
            reason = "Standard battle tactics"
            cost = self._estimate_cost(selected, task="complex")
    
    elif task.type == "reflection":
        # Always use thinking model for reflection
        selected = self.config.thinking_model
        reason = "Learning requires deep reasoning"
        cost = self._estimate_cost(selected, task="reflection", depth="deep")
    
    return ModelSelection(
        selected_model=selected,
        reasoning=reason,
        estimated_cost=cost,
        estimated_latency=self._estimate_latency(selected, task)
    )

# Cost optimization:
# - Grind battles: Acting model only (~$0.002/decision)
# - Regular battles: Strategic planning + acting (~$0.05/decision)
# - Boss battles: Full thinking model (~$0.06/decision)
# - Reflection after battle: ~$0.10/battle (amortized over many decisions)
```

### Token Budget Management

```python
def build_strategic_context(
    self,
    observer_memory: ObserverMemory,
    current_context: BattleContext
) -> str:
    """Build context respecting token limits"""
    
    context_parts = []
    remaining_tokens = self.config.thinking_model.max_tokens * 0.5  # Reserve 50% for response
    
    # Add journey summary (token budget: 500)
    journey = observer_memory.get_journey_summary(max_tokens=300)
    context_parts.append(f"JOURNEY:\n{journey}")
    
    # Add relevant lessons (token budget: 400)
    lessons = self._get_relevant_lessons(current_context, max_lessons=3)
    context_parts.append(f"LESSONS:\n{lessons}")
    
    # Add current context (token budget: 200)
    context_parts.append(f"CURRENT:\n{current_context}")
    
    # Add Pokedex data (token budget: depends on what's relevant)
    pokedex = self._get_relevant_pokedex_info(current_context, max_tokens=200)
    context_parts.append(f"EXPERT:\n{pokedex}")
    
    return "\n\n".join(context_parts)
```

### Performance Requirements

| Operation | Target Latency | Max Latency | Target Cost | Max Cost |
|-----------|---------------|-------------|-------------|----------|
| Strategic planning (thinking model) | 2000ms | 5000ms | $0.04 | $0.08 |
| Tactical decision (acting model) | 300ms | 800ms | $0.002 | $0.005 |
| Reflection (thinking model, amortized) | 3000ms | 8000ms | $0.05 | $0.10 |
| Context building | 50ms | 200ms | $0 | $0 |

### Error Handling

```python
class ModelError(Exception):
    """Base exception for model operations"""
    pass

class APIError(ModelError):
    """API call failed"""
    pass

class TimeoutError(ModelError):
    """Model response timeout"""
    pass

class ResponseFormatError(ModelError):
    """Model returned invalid format"""
    pass

class TokenLimitError(ModelError):
    """Context exceeds token limit"""
    pass

# Retry logic for API calls
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # Exponential backoff
```

### Testing Strategy

1. **Unit Tests**: Mock API responses, test context building
2. **Integration Tests**: Real API calls (limited scope)
3. **Cost Tests**: Verify cost estimation accuracy
4. **Model Selection Tests**: Test task classification and model choice
5. **Prompt Tests**: Validate prompt formatting produces valid responses

### A/B Testing Framework

```python
class ABTestFramework:
    """Compare different model/config combinations"""
    
    def __init__(self, test_name: str, variants: List[Variant]):
        self.test_name = test_name
        self.variants = variants
        self.results = []
    
    def run_test(self, scenarios: List[TestScenario]):
        """Run multiple scenarios against all variants"""
        for scenario in scenarios:
            for variant in self.variants:
                result = self._run_scenario_with_variant(scenario, variant)
                self.results.append(result)
    
    def get_results(self) -> TestResults:
        """Compare variant performance"""
        metrics = ["win_rate", "avg_cost", "avg_latency", "token_efficiency"]
        return statistical_comparison(self.results, metrics)

@dataclass
class Variant:
    """One configuration to test"""
    name: str
    thinking_model: ModelEndpoint
    acting_model: ModelEndpoint
    prompt_version: str
    context_strategy: str
```

---

## 5. Learning and Reflection Module

### Purpose  
Implement the 5-phase reflection engine that enables learning from both victories and defeats.

### Interface Contract

```python
class ReflectionEngine:
    def __init__(self, model_orchestrator: ModelOrchestrator)
    
    # Main reflection workflow
    def process_battle_outcome(self, battle_log: BattleLog) -> ReflectionResult
    
    # Individual phase methods
    def detect_failure(self, battle_log: BattleLog) -> FailureDetection
    def perform_forensic_analysis(self, battle_log: BattleLog) -> ForensicAnalysis
    def synthesize_insights(self, analysis: ForensicAnalysis) -> List[Insight]
    def integrate_into_memory(self, insights: List[Insight]) -> List[MemoryUpdate]
    def validate_updates(self, updates: List[MemoryUpdate]) -> ValidatedUpdates
    
    # Utilities
    def classify_battle_difficulty(self, battle_log: BattleLog) -> DifficultyRating
    def calculate_learning_velocity(self, window: int = 10) -> LearningVelocity
    def generate_battle_summary(self, battle_log: BattleLog) -> str
```

### Data Structures

```python
@dataclass
class BattleLog:
    """Complete record of a battle"""
    battle_id: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    outcome: Literal["victory", "defeat", "flee", "draw"]
    
    # Battle context
    location: str
    battle_type: Literal["wild", "trainer", "gym", "elite_four"]
    enemy_trainer: Optional[str]
    enemy_team: List[EnemyPokemonLog]
    
    # Turn-by-turn log
    turns: List[TurnLog]
    
    # Team state
    player_team_start: List[PokemonState]
    player_team_end: List[PokemonState]
    
    # Metrics
    decisions_made: int
    tokens_consumed: int
    total_damage_dealt: int
    total_damage_taken: int
    pp_consumed: int

@dataclass
class TurnLog:
    """Single turn record"""
    turn_number: int
    timestamp: datetime
    
    # State snapshots
    player_state: PokemonInBattle
    enemy_state: PokemonInBattle
    
    # Decision made
    decision: ActionDecision
    reasoning: str
    model_used: str
    
    # Outcome
    player_action_effect: str
    enemy_action: str
    damage_dealt: int
    damage_taken: int
    
    # State changes
    pp_consumed: int
    item_used: Optional[str]
    pokemon_switched: Optional[str]

@dataclass
class FailureDetection:
    """Phase 1: Did we lose?"""
    is_failure: bool
    failure_type: Literal["defeat", "suboptimal", "pyrrhic_victory"]
    severity: Literal["low", "medium", "high", "critical"]
    repeat_count: int  # How many times has this pattern failed?
    estimated_progress_lost: float  # Time, resources, etc.
    
@dataclass
class ForensicAnalysis:
    """Phase 2: What happened?"""
    battle_summary: str
    decision_quality: Dict[str, float]  # Model -> quality score
    
    # Analysis results
    type_effectiveness_analysis: List[TypeAnalysis]
    move_effectiveness_analysis: List[MoveAnalysis]
    sequencing_issues: List[SequenceIssue]
    resource_management_score: float
    
    # Key moments
    turning_points: List[TurnLog]  # Decisive moments
    mistakes: List[Mistake]  # Clear errors
    missed_opportunities: List[Opportunity]  # Could have done better

@dataclass
class Insight:
    """Phase 3: What did we learn?"""
    insight_type: Literal["type", "move", "sequence", "resource", "opponent"]
    insight_text: str  # Natural language conclusion
    evidence: List[str]  # Supporting evidence
    confidence: float  # 0.0 to 1.0
    priority: Literal["low", "medium", "high"]
    actionability: Literal["immediate", "future", "strategic"]
    memory_target: str  # Where to store this insight

@dataclass
class MemoryUpdate:
    """Phase 4: How to save the learning"""
    memory_type: Literal["observer", "strategist"]
    update_type: Literal["add", "modify", "remove"]
    target_key: str
    data: Any
    confidence: float
    source_battle: str  # Track provenance
    
@dataclass
class ValidatedUpdates:
    """Phase 5: Sanity-checked updates"""
    accepted: List[MemoryUpdate]
    rejected: List[Tuple[MemoryUpdate, str]]  # Update + reason
    flagged_for_review: List[MemoryUpdate]  # Needs human verification
```

### The 5-Phase Reflection Process

```python
def process_battle_outcome(self, battle_log: BattleLog) -> ReflectionResult:
    """
    The complete reflection workflow.
    Only runs after battles where learning is possible.
    """
    
    # Phase 1: Failure Detection
    failure_detection = self.detect_failure(battle_log)
    
    # Don't reflect on trivial victories (e.g., wild Pokemon with no challenge)
    if failure_detection.failure_type == "suboptimal" and \
       battle_log.battle_type == "wild" and \
       battle_log.duration_seconds < 30:
        return ReflectionResult(skipped=True, reason="Trivial battle")
    
    # Phase 2: Forensic Analysis
    analysis = self.perform_forensic_analysis(battle_log)
    
    # Phase 3: Insight Synthesis
    insights = self.synthesize_insights(analysis)
    
    if not insights:
        return ReflectionResult(skipped=True, reason="No actionable insights")
    
    # Phase 4: Memory Integration
    proposed_updates = self.integrate_into_memory(insights)
    
    # Phase 5: Validation
    validated = self.validate_updates(proposed_updates)
    
    return ReflectionResult(
        failure_detection=failure_detection,
        analysis=analysis,
        insights=insights,
        updates=validated,
        tokens_consumed=self._calculate_tokens(processing)
    )
```

### Phase 1: Failure Detection

```python
def detect_failure(self, battle_log: BattleLog) -> FailureDetection:
    """
    Determine if the battle outcome represents a learning opportunity.
    """
    
    is_failure = battle_log.outcome != "victory"
    
    if is_failure:
        # Categorize the failure
        failure_type = "defeat"
        
        # Check for repeated failures
        repeat_count = self._count_similar_failures(battle_log)
        
        # Calculate severity
        if battle_log.battle_type in ["gym", "elite_four"]:
            severity = "high"
        elif repeat_count > 3:
            severity = "critical"
        elif battle_log.total_damage_taken > battle_log.total_damage_dealt * 2:
            severity = "high"
        else:
            severity = "medium"
            
        return FailureDetection(
            is_failure=True,
            failure_type=failure_type,
            severity=severity,
            repeat_count=repeat_count,
            estimated_progress_lost=self._estimate_loss(battle_log)
        )
    
    # Even victories can be learning opportunities
    elif self._is_pyrrhic_victory(battle_log):
        return FailureDetection(
            is_failure=True,
            failure_type="pyrrhic_victory",
            severity="medium",
            repeat_count=0,
            estimated_progress_lost=self._calculate_resource_loss(battle_log)
        )
    
    # Suboptimal performance (took too long, wasted resources)
    elif self._is_suboptimal(battle_log):
        return FailureDetection(
            is_failure=True,
            failure_type="suboptimal",
            severity="low",
            repeat_count=0,
            estimated_progress_lost=0.1  # Wasted time/resources
        )
    
    # Clean victory - minimal learning
    return FailureDetection(
        is_failure=False,
        failure_type="none",
        severity="low",
        repeat_count=0,
        estimated_progress_lost=0
    )
```

### Phase 2: Forensic Analysis

```python
def perform_forensic_analysis(self, battle_log: BattleLog) -> ForensicAnalysis:
    """
    Deep dive into what happened turn by turn.
    """
    
    analysis = ForensicAnalysis(
        battle_summary=self.generate_battle_summary(battle_log),
        decision_quality={},
        type_effectiveness_analysis=[],
        move_effectiveness_analysis=[],
        sequencing_issues=[],
        resource_management_score=0.0,
        turning_points=[],
        mistakes=[],
        missed_opportunities=[]
    )
    
    # Analyze each turn
    for i, turn in enumerate(battle_log.turns):
        # Quality of decision
        decision_quality = self._evaluate_decision_quality(turn)
        analysis.decision_quality[turn.decision.model_used] = decision_quality
        
        # Type effectiveness check
        type_analysis = self._analyze_type_effectiveness(turn)
        if type_analysis:
            analysis.type_effectiveness_analysis.append(type_analysis)
        
        # Move effectiveness
        move_analysis = self._analyze_move_effectiveness(turn)
        if move_analysis:
            analysis.move_effectiveness_analysis.append(move_analysis)
        
        # Resource management
        resource_score = self._evaluate_resource_use(turn)
        analysis.resource_management_score += resource_score
        
        # Key moments
        if self._is_turning_point(turn, battle_log.turns):
            analysis.turning_points.append(turn)
        
        # Mistakes
        if self._is_clear_mistake(turn):
            analysis.mistakes.append(self._identify_mistake(turn))
    
    # Calculate averages
    analysis.resource_management_score /= len(battle_log.turns)
    
    return analysis
```

### Phase 3: Insight Synthesis

```python
def synthesize_insights(self, analysis: ForensicAnalysis) -> List[Insight]:
    """
    Generate actionable insights from forensic analysis.
    Only generate insights with high confidence.
    """
    
    insights = []
    
    # Type effectiveness insights
    for type_analysis in analysis.type_effectiveness_analysis:
        if type_analysis.times_tested >= 2:  # Need multiple data points
            insight = Insight(
                insight_type="type",
                insight_text=f"{type_analysis.attacker_type} moves are {type_analysis.effectiveness} against {type_analysis.defender_type} types",
                evidence=[
                    f"Used {type_analysis.attacker_type} move {type_analysis.times_tested} times",
                    f"Average damage multiplier: {type_analysis.avg_effectiveness:.2f}x"
                ],
                confidence=type_analysis.confidence,
                priority=self._determine_priority(type_analysis),
                actionability="immediate",
                memory_target="strategist.type_lessons"
            )
            insights.append(insight)
    
    # Move sequencing insights
    if analysis.sequencing_issues:
        for sequence_issue in analysis.sequencing_issues:
            if sequence_issue.impacts_battle_outcome:
                insights.append(Insight(
                    insight_type="sequence",
                    insight_text=f"{sequence_issue.description}",
                    evidence=sequence_issue.evidence,
                    confidence=sequence_issue.confidence,
                    priority="high",
                    actionability="future",
                    memory_target="strategist.failure_modes"
                ))
    
    # Resource management insights
    if analysis.resource_management_score < 0.6:
        insights.append(Insight(
            insight_type="resource",
            insight_text="Need to improve PP/item management",
            evidence=[f"Resource score: {analysis.resource_management_score:.2f}"],
            confidence=0.7,
            priority="medium",
            actionability="strategic",
            memory_target="strategist.resource_strategies"
        ))
    
    return [insight for insight in insights if insight.confidence > 0.6]
```

### Performance Requirements

| Phase | Target | Max | Notes |
|-------|--------|-----|-------|
| Failure Detection | <100ms | 500ms | Simple heuristics |
| Forensic Analysis | <1000ms | 3000ms | Turns × operations |
| Insight Synthesis | <2000ms | 5000ms | Calls thinking model |
| Memory Integration | <500ms | 2000ms | Local operations |
| Validation | <500ms | 2000ms | Local operations |
| **Total Reflection** | **<4s** | **<10s** | After each battle |

### Error Handling

```python
class ReflectionError(Exception):
    """Base exception for reflection operations"""
    pass

class InsufficientDataError(ReflectionError):
    """Not enough battle history to reflect"""
    pass

class InsightGenerationError(ReflectionError):
    """Failed to generate meaningful insights"""
    pass

class MemoryIntegrationError(ReflectionError):
    """Failed to integrate insights into memory"""
    pass

# Recovery: If reflection fails, log and continue (don't block gameplay)
```

### Testing Strategy

1. **Mock Battles**: Create synthetic battle logs with known issues
2. **Regression Testing**: Test that specific failure patterns generate correct insights
3. **Edge Cases**: Edge cases: Zero-turn battles, disconnections, corrupted data
4. **Learning Verification**: Test that insights actually improve future performance
5. **Statistics**: Track insight quality scores

---

## 6. Analytics and Dashboard Module

### Purpose
Track all decisions, calculate metrics, and provide real-time visualization.

### Interface Contract

```python
class DecisionLogger:
    def __init__(self, log_path: Path)
    
    # Core logging
    def log_decision(self, decision: DecisionLogEntry) -> None
    def log_battle_start(self, battle_info: BattleInfo) -> None
    def log_battle_end(self, battle_info: BattleInfo) -> None
    def log_reflection(self, reflection: ReflectionLog) -> None
    def log_error(self, error: ErrorLogEntry) -> None
    
    # Retrieval
    def get_decisions(self, 
                     since: datetime = None,
                     battle_id: str = None,
                     model_used: str = None) -> List[DecisionLogEntry]
    
    def export_logs(self, format: Literal["json", "csv", "parquet"]) -> Path
    
class MetricsAggregator:
    def __init__(self, decision_logger: DecisionLogger)
    
    # Session metrics
    def get_session_metrics(self, hours: int = 1) -> SessionMetrics
    def get_progress_over_time(self) -> ProgressTimeline
    def get_cost_breakdown(self) -> CostBreakdown
    
    # Battle analytics
    def get_win_rate(self, filter_by: Filter = None) -> float
    def get_avg_battle_duration(self, filter_by: Filter = None) -> float
    def get_learning_velocity(self, window: int = 10) -> LearningVelocity
    
    # Model comparison
    def compare_models(self, start_time: datetime, end_time: datetime) -> ModelComparison
    def get_efficiency_ratios(self) -> EfficiencyRatios
    
    # Token usage
    def analyze_token_usage(self) -> TokenAnalysis
    def get_context_compression_ratio(self) -> float
```

### Data Structures

```python
@dataclass
class DecisionLogEntry:
    """Complete log of one decision"""
    decision_id: str
    timestamp: datetime
    session_id: str
    
    # Context
    frame_hash: str
    game_state: GameState
    battle_context: BattleContext
    
    # Decision trace
    context_used: ContextUsed
    reasoning_trace: ReasoningTrace
    action_taken: ActionTaken
    
    # Outcome
    success: bool
    tokens_consumed: int
    latency_ms: float
    cost_usd: float
    
    # Battle metrics
    hp_preserved: int
    pp_conserved: int
    damage_dealt: int
    damage_taken: int
    
    @property
    def token_efficiency(self) -> float:
        """Progress per token"""
        return (self.hp_preserved + self.damage_dealt) / max(self.tokens_consumed, 1)

@dataclass
class SessionMetrics:
    """Aggregate metrics for a session"""
    start_time: datetime
    end_time: datetime
    duration_hours: float
    
    # Decision metrics
    total_decisions: int
    decisions_per_minute: float
    avg_latency_ms: float
    
    # Cost metrics
    total_cost_usd: float
    cost_per_hour: float
    cost_per_battle: float
    
    # Performance metrics
    avg_token_efficiency: float
    win_rate: float
    progress_made: Dict[str, Any]  # Badges, levels, etc.
    
    # Model usage
    model_usage_stats: Dict[str, ModelUsage]

@dataclass
class LearningVelocity:
    """Rate of improvement over time"""
    time_window: timedelta
    battles_tracked: int
    
    # Improvement metrics
    win_rate_improvement: float  # Percentage points
    token_efficiency_improvement: float  # Absolute improvement
    avg_damage_ratio_improvement: float  # (dealt/taken) ratio improvement
    
    # Trend direction
    improving: bool
    velocity_stable: bool  # Is improvement rate stable?
    
    # Confidence intervals
    confidence_level: float
```

### Logging Schema

```python
# Log files are rotated daily and written in JSON Lines format
# Example log entry:

{
  "timestamp": "2025-12-30T15:23:45.123Z",
  "decision_id": "dec_9f3b2e1a",
  "version": "1.0",
  
  // Game state
  "game_state": {
    "battle_active": true,
    "battle_type": "trainer",
    "location": "Route 3",
    "turn": 12
  },
  
  // Battle context
  "battle_context": {
    "player_pokemon": "Charmander",
    "player_level": 15,
    "player_hp_percent": 65,
    "enemy_pokemon": "Geodude",
    "enemy_level": 14,
    "enemy_hp_percent": 20
  },
  
  // Decision trace
  "reasoning_trace": {
    "model": "gpt-4o-mini",
    "prompt_tokens": 342,
    "completion_tokens": 45,
    "latency_ms": 283
  },
  
  // Action taken
  "action_taken": {
    "button_pressed": "A",
    "reasoning": "Use Ember - guaranteed to finish the weakened Geodude"
  },
  
  // Outcome
  "outcome": {
    "success": true,
    "hp_preserved": 35,
    "damage_dealt": 20,
    "battle_ended": true,
    "victory": true
  },
  
  // Cost
  "cost": {
    "total_usd": 0.0012,
    "per_decision": 0.0012
  }
}
```

### Real-Time Metrics Calculation

```python
def get_session_metrics(self, hours: int = 1) -> SessionMetrics:
    """Calculate rolling metrics for recent activity"""
    
    since_time = datetime.now() - timedelta(hours=hours)
    recent_decisions = self.logger.get_decisions(since=since_time)
    
    if not recent_decisions:
        return SessionMetrics()  # Empty metrics
    
    # Calculate aggregates
    total_cost = sum(d.cost_usd for d in recent_decisions)
    total_tokens = sum(d.tokens_consumed for d in recent_decisions)
    total_latency = sum(d.latency_ms for d in recent_decisions)
    total_damage_dealt = sum(d.damage_dealt for d in recent_decisions)
    total_damage_taken = sum(d.damage_taken for d in recent_decisions)
    
    battles = self._get_battles_in_period(since_time)
    battles_won = sum(1 for b in battles if b.outcome == "victory")
    
    return SessionMetrics(
        start_time=since_time,
        end_time=datetime.now(),
        duration_hours=hours,
        total_decisions=len(recent_decisions),
        decisions_per_minute=len(recent_decisions) / (hours * 60),
        avg_latency_ms=total_latency / len(recent_decisions),
        total_cost_usd=total_cost,
        cost_per_hour=total_cost / hours,
        avg_token_efficiency=total_damage_dealt / max(total_tokens, 1),
        win_rate=battles_won / max(len(battles), 1),
        progress_made=self._calculate_progress(battles)
    )
```

### Performance Requirements

| Operation | Target Latency | Max Latency | Notes |
|-----------|---------------|-------------|-------|
| Log decision | <10ms | 50ms | Async preferred |
| Retrieve recent decisions | <100ms | 500ms | Indexed by time |
| Calculate session metrics | <500ms | 2000ms | Hourly interval |
| Export day of logs | <5000ms | 15000ms | For data analysis |
| Dashboard refresh | <1000ms | 3000ms | User-facing |

### Error Handling

```python
class LoggingError(Exception):
    """Failed to write log"""
    pass

class MetricsCalculationError(Exception):
    """Failed to calculate metrics"""
    pass

class DataIntegrityError(Exception):
    """Log data is corrupted or incomplete"""
    pass

# Log recovery: If write fails, buffer in memory and retry
# Metrics: If calculation fails, return cached values
```

### Testing Strategy

1. **Unit Tests**: Mock logger, test metrics calculation
2. **Integration Tests**: Real logging to files, retrieval
3. **Performance Tests**: Log 10,000+ decisions, query performance
4. **Data Integrity**: Corrupt log files, test recovery
5. **Analytics Tests**: Verify metrics match manual calculation

---

## 7. Error Recovery and Resilience

### Purpose
The system must gracefully handle failures at all levels without losing progress or learning.

### Resilience Patterns

#### Pattern: Circuit Breaker
```python
class CircuitBreaker:
    """Prevent cascading failures in external services"""
    
    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 60):
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
    
    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenError()
        
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise e
    
    def _record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"
    
    def _record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
```

#### Pattern: Graceful Degradation
```python
class ResilientVisionProcessor:
    """If vision API fails, fall back to less accurate methods"""
    
    def extract_battle_state(self, frame: np.ndarray) -> BattleState:
        try:
            # Primary: Vision API
            state = self.vision_api.classify_battle(frame)
            return state
        except APIError as e:
            # Fallback 1: Try different model
            try:
                state = self.backup_vision_model.classify_battle(frame)
                return state
            except Exception:
                pass
            
            # Fallback 2: Use RAM data (if available)
            if self.emulator.is_connected():
                state = self._from_ram_data()
                return state
            
            # Fallback 3: Last known state (may be stale)
            return self.last_known_state
```

#### Pattern: Checkpoint and Resume
```python
class CheckpointManager:
    """Save game state periodically for recovery"""
    
    def __init__(self, save_interval_seconds: int = 300):
        self.save_interval = save_interval_seconds
        self.last_checkpoint = None
    
    def should_checkpoint(self) -> bool:
        """Check if it's time to save state"""
        if not self.last_checkpoint:
            return True
        elapsed = time.time() - self.last_checkpoint
        return elapsed > self.save_interval
    
    def checkpoint(self, emulator: EmulatorInterface) -> Checkpoint:
        """Create a checkpoint"""
        slot = self._get_next_available_slot()
        emulator.save_state(slot)
        
        checkpoint = Checkpoint(
            timestamp=datetime.now(),
            save_slot=slot,
            game_time=emulator.get_game_time(),
            memory_snapshot=self._save_memory_state()
        )
        
        self.last_checkpoint = time.time()
        return checkpoint
    
    def restore_from_checkpoint(self, checkpoint: Checkpoint, emulator: EmulatorInterface):
        """Restore to checkpoint"""
        emulator.load_state(checkpoint.save_slot)
        self._restore_memory_state(checkpoint.memory_snapshot)
```

---

## 8. Configuration Management

### Purpose
All system parameters must be configurable without code changes.

### Configuration Schema

```yaml
# config/settings.yaml

project:
  name: "AI Plays Pokemon"
  version: "1.0.0"
  game_version: "Pokemon Red (English)"

# Emulator settings
emulator:
  rom_path: "data/roms/pokemon_red.gb"
  boot_rom: null  # Optional
  save_path: "memory/game_states/"
  frame_skip: 0  # 0 = no skip, runs at full speed
  
  # Memory addresses (overridable per game version)
  memory_addresses:
    battle_mode: 0xD057
    player_hp: 0xD16C
    enemy_hp: 0xD11C
    # ... etc

# Model settings
models:
  thinking:
    provider: "anthropic"
    model: "claude-3-opus-20240229"
    api_key: "${ANTHROPIC_API_KEY}"  # From environment
    max_tokens: 4000
    temperature: 0.2
    cost_per_1k_input: 0.015
    cost_per_1k_output: 0.075
    
  acting:
    provider: "anthropic" 
    model: "claude-3-haiku-20240307"
    api_key: "${ANTHROPIC_API_KEY}"
    max_tokens: 1000
    temperature: 0.1
    cost_per_1k_input: 0.00025
    cost_per_1k_output: 0.00125
    
  vision:
    provider: "openai"
    model: "gpt-4-vision-preview"
    api_key: "${OPENAI_API_KEY}"
    max_tokens: 2000
    temperature: 0.1
    cost_per_1k_input: 0.01
    detail: "auto"  # auto, low, high

# Memory settings
memory:
  persistence_path: "memory/strategist_memory.pkl"
  backup_count: 5
  
  decay:
    enabled: true
    rate_per_hour: 0.01  # 1% per hour
    
  filtering:
    relevant_lessons_limit: 5
    max_tokens_per_context: 3000
    
  tactician:
    turn_history_limit: 5  # How many past turns to keep
    
# Learning settings
learning:
  reflection:
    enabled: true
    min_battle_duration_seconds: 30
    skip_trivial_victories: true
    
  failure_detection:
    repeat_threshold: 3  # How many repeats before critical
    
  insight_generation:
    min_confidence: 0.6
    min_evidence_count: 2
    
  memory_integration:
    validation_mode: "automatic"  # automatic, manual, disabled

# Vision settings
vision:
  differential_rendering:
    enabled: true
    similarity_threshold: 0.99
    
  cost_optimization:
    skip_static_frames: true
    cache_validated_results: true
    cache_ttl_frames: 100
    
  accuracy_requirements:
    battle_state_confidence: 0.9
    pokemon_identification_confidence: 0.85
    hp_extraction_error_tolerance: 5  # HP points

# Cost settings
cost:
  optimization:
    enabled: true
    target_cost_per_hour: 1.0  # USD
    
  alerts:
    hourly_budget: 2.0
    daily_budget: 10.0
    
  model_switching:
    use_thinking_model_for: ["gym", "elite_four", "learning_moment"]
    use_fast_model_for: ["overworld", "grinding"]

# Performance settings
performance:
  latency_targets:
    tactical_decision_ms: 500
    strategic_planning_ms: 2000
    vision_processing_ms: 1000
    
  monitoring:
    log_slow_operations: true
    slow_threshold_ms: 2000

# Analytics
analytics:
  logging:
    enabled: true
    log_path: "logs/decisions/"
    rotation: "daily"  # daily, hourly, size_based
    
  metrics:
    calculate_session_metrics: true
    session_window_hours: 1
    
  dashboard:
    enabled: true
    port: 8501
    refresh_seconds: 30

# Error handling
error_handling:
  circuit_breaker:
    enabled: true
    failure_threshold: 5
    reset_timeout_seconds: 60
    
  graceful_degradation:
    enabled: true
    fallbacks:
      - "backup_model"
      - "ram_data" 
      - "cached_state"
      
  checkpoints:
    enabled: true
    interval_seconds: 300  # 5 minutes
    max_checkpoints: 10

# Testing
testing:
  # When enabled, various test parameters apply
  enabled: false
  
  mock_apis: false
  
  overrides:
    # Force specific behaviors for testing
    force_model_selection: null  # Override adaptive selection
    force_vision_failure: false  # Test fallback paths
    force_memory_error: false    # Test recovery
```

### Environment Variables

```bash
# Required
export POKEMON_ROM_PATH="/path/to/pokemon_red.gb"
export OPENAI_API_KEY="sk-..."           # If using OpenAI models
export ANTHROPIC_API_KEY="ant-..."       # If using Anthropic models

# Optional
export MEMORY_STORAGE_PATH="~/.ai_plays_poke/memory"
export LOG_PATH="~/.ai_plays_poke/logs"
export ANALYTICS_DB="~/.ai_plays_poke/analytics.db"
```

---

## 9. Integration Testing Strategy

### End-to-End Test Scenarios

```python
def test_full_battle_flow():
    """Test complete battle from start to finish"""
    
    # Setup
    config = load_config("test_config.yaml")
    emulator = EmulatorInterface(config.emulator.rom_path)
    vision = VisionProcessor(config.models.vision.api_key)
    memory = MemoryManager(config.memory.persistence_path)
    orchestrator = ModelOrchestrator(config.models)
    
    # Start battle (use save state with pre-positioned character)
    emulator.load_state("test_battle_ready")
    
    # Verify initial state
    assert emulator.is_running()
    assert vision.classify_screen(emulator.capture_screen()).screen_type == "battle"
    
    # Run battle loop
    battle_log = BattleLog(battle_id="test_1")
    
    turn_count = 0
    max_turns = 50  # Prevent infinite loops
    
    while turn_count < max_turns:
        # Get current state
        frame = emulator.capture_screen()
        battle_state = vision.extract_battle_state(frame)
        
        # Make decision
        tactician_context = memory.get_tactician_context()
        decision = orchestrator.act(
            tactician_context,
            battle_state,
            available_actions
        )
        
        # Execute action
        emulator.press_button(decision.action)
        
        # Log
        battle_log.add_turn(
            TurnLog(
                turn_number=turn_count,
                decision=decision,
                game_state=battle_state
            )
        )
        
        # Check if battle ended
        if vision.classify_screen(emulator.capture_screen()).screen_type != "battle":
            break
        
        turn_count += 1
        sleep(0.5)  # Give game time to process
    
    # Reflect
    reflector = ReflectionEngine(orchestrator)
    reflection = reflector.process_battle_outcome(battle_log)
    
    # Verify learning occurred
    assert len(reflection.insights) > 0
    assert reflection.failure_detection is not None
    
    # Cleanup
    emulator.stop()
```

### Integration Test Categories

1. **Flow Tests**: Complete user journeys (battle, explore, menu navigation)
2. **Failure Recovery Tests**: API failures, emulator crashes, memory corruption
3. **Performance Tests**: Measure latency under various conditions
4. **Accuracy Tests**: Compare system decisions to optimal play
5. **Cost Tests**: Verify cost optimization reduces expenses
6. **Learning Tests**: Verify system improves over time

---

## 10. Deployment Considerations

### Local Development
```bash
# Install
pip install -r requirements.txt

# Set environment
export POKEMON_ROM_PATH="/path/to/rom.gb"
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="ant-..."

# Run
python src/main.py --config config/settings.yaml

# View dashboard
streamlit run src/ui/dashboard.py
```

### Production-Like Deployment (Docker)

```dockerfile# For a production-like deployment
FROM python:3.11-slim

WORKDIR /ai_plays_poke

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user
RUN useradd --create-home --shell /bin/bash ai_player
USER ai_player

# Expose dashboard port
EXPOSE 8501

CMD ["python", "src/main.py"]
```

### Scaling Considerations

- **Single instance**: Current design targets one AI playing one game
- **Multiple instances**: Possible with multiple ROMs/accounts
- **Horizontal scaling**: Each AI instance is independent
- **GPU requirements**: None (vision models are API-based)

---

## Appendix: Code Examples

### Minimal Working Example

```python
from src.core.emulator import EmulatorInterface
from src.cognition.vision import VisionProcessor
from src.cognition.memory import MemoryManager
from src.cognition.orchestrator import ModelOrchestrator
from src.cognition.reflection import ReflectionEngine
from config.settings import load_config
import time

def main():
    # Load configuration
    config = load_config("config/settings.yaml")
    
    # Initialize components
    emulator = EmulatorInterface(config.emulator.rom_path)
    vision = VisionProcessor(config.models.vision.api_key)
    memory = MemoryManager(config.memory.persistence_path)
    orchestrator = ModelOrchestrator(config.models)
    
    try:
        # Start game
        emulator.start()
        
        # Main game loop
        while True:
            # Get current game state
            frame = emulator.capture_screen()
            screen_state = vision.classify_screen(frame)
            
            if screen_state.screen_type == "battle":
                # Battle logic
                battle_state = vision.extract_battle_state(frame)
                tactician = memory.get_tactician_context()
                decision = orchestrator.act(tactician, battle_state)
                emulator.press_button(decision.action)
                
            elif screen_state.screen_type == "overworld":
                # Exploration logic
                # ... handle overworld navigation
                pass
                
            # Log decision
            logger.log_decision(decision)
            
            # Prevent rapid looping
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("Shutting down...")
        emulator.stop()

if __name__ == "__main__":
    main()
```

---

## Document History

- **v1.0 (2025-12-30)**: Initial technical specifications covering all modules
