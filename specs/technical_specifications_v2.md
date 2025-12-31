# Technical Specifications: AI-Assisted Pokemon Gameplay Framework (v2)

## System Overview (Based on 12/30/2025 Discussion)

This document describes the implementation of a **local AI-driven Pokemon gameplay system** using a relay architecture. Multiple AI instances with varying capabilities will play Pokemon simultaneously, with performance comparison and learning capabilities.

### Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AI COORDINATOR                           │
│  - Manages multiple AI instances (skill levels 1-10)       │
│  - Routes screenshots → AI → Commands → Emulator          │
│  - Tracks performance metrics for comparison               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  AI LVL 1   │  │  AI LVL 5   │  │  AI LVL 10  │        │
│  │ (Basic)     │  │ (Medium)    │  │ (Advanced)  │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                 │
│         └────────────────┴────────────────┘                 │
│                          │                                  │
│  ┌───────────────────────┴───────────────────────────────┐  │
│  │           COMMAND RELAY / PARSER                      │  │
│  │  - Formats AI output → Emulator commands             │  │
│  │  - Validates & sanitizes commands                     │  │
│  │  - Batches operations (e.g., "walk 10 steps")         │  │
│  └───────────────────────┬───────────────────────────────┘  │
└──────────────────────────┼──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│           PYBOY EMULATOR INTERFACE                          │
│  - Runs Pokemon ROM (multiple instances)                   │
│  - Provides screen capture (160x144 RGB)                   │
│  - Accepts button inputs (A,B,START,SELECT + D-pad)       │
│  - Memory access (for validation & state detection)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. AI Coordinator Module

### Purpose
Manages multiple AI instances, coordinates screenshot → command flow, tracks performance metrics, and handles the relay between AI decision-making and emulator execution.

### Interface Contract

```python
class AICoordinator:
    def __init__(self, config_path: str)
    
    # AI Instance Management
    def initialize_ai_instances(self, count: int = 3, skill_levels: List[int]) -> List[AIInstance]
    def start_ai_instance(self, instance_id: str) -> None
    def stop_ai_instance(self, instance_id: str) -> None
    def get_ai_performance(self, instance_id: str) -> AIPerformanceMetrics
    
    # Game Loop Coordination
    def process_game_tick(self, emulator_id: str) -> CommandExecutionResult
    def should_take_screenshot(self, tick_count: int) -> bool
    def get_screenshot_interval(self, game_state: GameState) -> int  # ticks
    
    # Command Routing
    def send_to_ai(self, instance_id: str, screenshot: np.ndarray, game_state: GameState) -> AIResponse
    def route_command_to_emulator(self, command: FormattedCommand) -> ExecutionResult
    
    # Batch Operation Optimization
    def optimize_command_sequence(self, raw_commands: List[str]) -> List[BatchableCommand]
    def estimate_command_duration(self, command: str) -> int  # in ticks
    
    # Performance Tracking & Comparison
    def record_decision(self, instance_id: str, decision: DecisionRecord) -> None
    def get_leaderboard(self) -> List[AIPerformanceMetrics]
    def export_metrics(self, format: str = "json") -> Path
```

### Data Structures

```python
@dataclass
class AIInstance:
    """Represents a single AI player with specific capabilities"""
    instance_id: str
    skill_level: int  # 1-10 scale
    model_path: str  # Path to local model (GGUF format)
    config: AIConfig
    is_running: bool
    memory_manager: MemoryManager  # Per-AI memory
    
    # Performance tracking
    battles_fought: int
    battles_won: int
    badges_earned: List[str]
    total_ticks: int
    
@dataclass  
class AIConfig:
    """Configuration for AI capabilities at each skill level"""
    skill_level: int
    model_size: str  # "7B", "13B", etc.
    context_window: int  # tokens
    supports_tools: bool  # Can use web search, etc.
    reasoning_depth: Literal["basic", "medium", "advanced"]
    
    # Permission flags
    can_batch_commands: bool
    can_search_web: bool
    has_pokemon_knowledge: bool  # Built-in knowledge vs needs to learn
    max_batch_size: int  # How many steps can batch together
    
@dataclass
class GameState:
    """Current game state that AI needs to make decisions"""
    screen_type: Literal["battle", "overworld", "menu", "dialog", "transition"]
    screenshot: np.ndarray  # 160x144 RGB
    current_location: Optional[str]
    in_battle: bool
    battle_state: Optional[BattleState]
    last_command: Optional[str]
    ticks_since_last_screenshot: int
    
@dataclass
class AIResponse:
    """Structured response from AI model"""
    instance_id: str
    raw_response: str  # Raw text from AI
    parsed_commands: List[ParsedCommand]
    reasoning: str  # AI's explanation
    confidence: float  # 0.0 to 1.0
    suggested_wait_ticks: int  # How long to wait before next screenshot
    needs_validation: bool  # Requires human/validator check
    
@dataclass
class ParsedCommand:
    """Validated and structured command ready for execution"""
    command_id: str
    action: Literal["press_button", "hold_button", "sequence", "batch_navigate"]
    button: Optional[Literal["A", "B", "START", "SELECT", "UP", "DOWN", "LEFT", "RIGHT"]]
    duration_ms: Optional[int]  # For hold_button
    sequence: Optional[List[ButtonAction]]  # For complex sequences
    batch: Optional[BatchCommand]  # For batched operations
    estimated_ticks: int
    safety_level: Literal["safe", "caution", "dangerous"]  # For validation
    
@dataclass
class BatchCommand:
    """Batched navigation command for efficiency (e.g., "walk 10 steps up")"""
    command_type: Literal["walk", "run", "menu_navigate"]
    direction: Literal["up", "down", "left", "right"]
    steps: int
    through_grass: bool  # Risk assessment - random encounters
    estimated_duration_ticks: int
```

### AI Skill Level Configuration

```python
AI_SKILL_LEVELS = {
    1: AIConfig(
        skill_level=1,
        model_size="3B",
        context_window=4096,
        supports_tools=False,
        reasoning_depth="basic",
        can_batch_commands=False,
        can_search_web=False,
        has_pokemon_knowledge=False,
        max_batch_size=1
    ),
    5: AIConfig(
        skill_level=5,
        model_size="7B", 
        context_window=8192,
        supports_tools=True,
        reasoning_depth="medium",
        can_batch_commands=True,
        can_search_web=True,
        has_pokemon_knowledge=True,
        max_batch_size=5
    ),
    10: AIConfig(
        skill_level=10,
        model_size="13B",
        context_window=16384,
        supports_tools=True,
        reasoning_depth="advanced",
        can_batch_commands=True,
        can_search_web=True,
        has_pokemon_knowledge=True,
        max_batch_size=20
    )
}
```

### Performance Metrics Tracking

```python
@dataclass
class AIPerformanceMetrics:
    """Comprehensive metrics for comparing AI instances"""
    instance_id: str
    skill_level: int
    
    # Basic stats
    total_ticks: int
    battles_fought: int
    battles_won: int
    badges_collected: List[str]
    badges_count: int
    
    # Efficiency metrics
    win_rate: float
    avg_battle_duration_ticks: float
    avg_damage_ratio: float  # damage_dealt / damage_taken
    
    # Decision quality
    decision_count: int
    avg_confidence: float
    confidence_accuracy: float  # Does high confidence = success?
    
    # Economic metrics
    total_potions_used: int
    total_pp_restored: int
    pokemon_center_visits: int
    
    # Learning metrics
    lessons_learned: int
    mistakes_repeated: int  # How often makes same mistake twice
    improvement_velocity: float  # Positive = improving
    
    # Ranking
    overall_score: float  # Composite score for leaderboard
    rank: int  # Position among all instances
```

### Command Batch Optimization Logic

```python
class CommandOptimizer:
    """Convert individual commands into efficient batches"""
    
    def optimize_sequence(self, commands: List[str], ai_level: int) -> List[BatchableCommand]:
        """
        Convert sequential commands into batches where possible.
        Example: ["UP", "UP", "UP", "UP", "UP"] → BatchCommand(walk, up, 5)
        """
        if ai_level < 3:  # Low-level AIs can't batch
            return [self._convert_to_single_command(cmd) for cmd in commands]
        
        optimized = []
        i = 0
        while i < len(commands):
            # Try to create a batch
            batch = self._try_create_batch(commands[i:])
            if batch:
                optimized.append(batch)
                i += batch.original_command_count
            else:
                # Single command
                optimized.append(self._convert_to_single_command(commands[i]))
                i += 1
        
        return optimized
    
    def _try_create_batch(self, commands: List[str]) -> Optional[BatchCommand]:
        """Look for patterns that can be batched"""
        if len(commands) < 2:
            return None
        
        # Pattern: Same directional command repeated
        if all(cmd == commands[0] for cmd in commands[:5]):
            direction = commands[0].lower()
            if direction in ["up", "down", "left", "right"]:
                return BatchCommand(
                    command_type="walk",
                    direction=direction,
                    steps=min(len(commands), 20),  # Max batch size
                    through_grass=self._is_grass_area(),
                    estimated_duration_ticks=len(commands) * 15  # 15 ticks per step
                )
        
        return None
```

---

## 2. Pokédex Integration & Pokémon Detection Module

### Purpose
When the vision system detects Pokémon on screen, automatically enrich the battle state with expert Pokédex data. This provides factual type information, weaknesses, and resistances without LLM hallucination.

### Installation
```bash
pip install pypokedex
```

### Core Integration

```python
import pypokedex
from typing import Optional, Dict, Any, List

class PokemonEnricher:
    """Enriches vision detections with Pokédex data for AI context"""
    
    def __init__(self):
        self.cache: Dict[str, pypokedex.pokemon.Pokemon] = {}
        self.type_cache: Dict[str, List[str]] = {}
    
    def get_pokemon_data(self, name: str) -> Optional[Dict[str, Any]]:
        """Fetch Pokédex data for a detected Pokemon with error handling"""
        try:
            normalized_name = self._normalize_name(name)
            
            if normalized_name in self.cache:
                pokemon = self.cache[normalized_name]
            else:
                pokemon = pypokedex.get(name=normalized_name)
                self.cache[normalized_name] = pokemon
            
            return {
                "name": pokemon.name,
                "dex": pokemon.dex,
                "types": pokemon.types,
                "base_stats": {
                    "hp": pokemon.base_stats.hp,
                    "attack": pokemon.base_stats.attack,
                    "defense": pokemon.base_stats.defense,
                    "sp_atk": pokemon.base_stats.sp_atk,
                    "sp_def": pokemon.base_stats.sp_def,
                    "speed": pokemon.base_stats.speed
                },
                "abilities": [ability.name for ability in pokemon.abilities],
                "weaknesses": self._calculate_type_matchups(pokemon.types)["weak"],
                "resistances": self._calculate_type_matchups(pokemon.types)["resist"]
            }
        except Exception as e:
            print(f"⚠️ Pokédex lookup failed for '{name}': {e}")
            return None
    
    def _normalize_name(self, raw_name: str) -> str:
        """Handle common vision OCR errors and normalizations"""
        corrections = {
            "GEODUDE": "geodude", "GEODUD3": "geodude", "g3odude": "geodude",
            "CHARMANDER": "charmander", "CHARMAND3R": "charmander",
            "SQUIRTLE": "squirtle", "SQURTLE": "squirtle",
            "BULBASAUR": "bulbasaur", "BULBASAAR": "bulbasaur",
            "PIKACHU": "pikachu", "PIKACU": "pikachu", "PIKACH": "pikachu",
            "PIDGEY": "pidgey", "PIDGY": "pidgey", "Pidgey": "pidgey"
        }
        return corrections.get(raw_name.upper(), raw_name.lower())
    
    def _calculate_type_matchups(self, types: List[str]) -> Dict[str, List[str]]:
        """Calculate type effectiveness using Gen 1 type chart"""
        # Gen 1 type effectiveness chart (attacker → defender)
        type_chart = {
            "normal": {"rock": 0.5, "ghost": 0},
            "fire": {"fire": 0.5, "water": 0.5, "rock": 0.5, "grass": 2, "ice": 2, "bug": 2},
            "water": {"fire": 2, "water": 0.5, "grass": 0.5, "ground": 2, "rock": 2},
            "electric": {"water": 2, "electric": 0.5, "grass": 0.5, "ground": 0},
            "grass": {"fire": 0.5, "water": 2, "grass": 0.5, "poison": 0.5, "ground": 2, "rock": 2, "flying": 0.5},
            "ice": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 0.5, "ground": 2, "flying": 2},
            "fighting": {"normal": 2, "ice": 2, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "rock": 2, "ghost": 0},
            "poison": {"grass": 2, "poison": 0.5, "ground": 0.5, "bug": 2, "rock": 0.5, "ghost": 0.5},
            "ground": {"fire": 2, "electric": 2, "grass": 0.5, "poison": 2, "flying": 0, "bug": 0.5, "rock": 2},
            "flying": {"electric": 0.5, "grass": 2, "fighting": 2, "bug": 2, "rock": 0.5},
            "psychic": {"fighting": 2, "poison": 2, "psychic": 0.5},
            "bug": {"fire": 0.5, "grass": 2, "fighting": 0.5, "poison": 2, "flying": 0.5, "psychic": 2, "ghost": 0.5},
            "rock": {"fire": 2, "ice": 2, "fighting": 0.5, "ground": 0.5, "flying": 2, "bug": 2},
            "ghost": {"normal": 0, "psychic": 0, "ghost": 2}
        }
        
        weaknesses = []
        resistances = []
        
        for attack_type in type_chart.keys():
            multiplier = 1.0
            for defense_type in types:
                if defense_type == "":
                    continue
                multiplier *= type_chart.get(attack_type, {}).get(defense_type, 1.0)
            
            if multiplier >= 2.0:
                weaknesses.append(attack_type)
            elif multiplier <= 0.5:
                resistances.append(attack_type)
        
        return {"weak": weaknesses, "resist": resistances}

class EnrichedBattleState:
    """Battle state enhanced with Pokédex data"""
    
    def __init__(self, vision_state: Dict[str, Any], enricher: PokemonEnricher):
        self.enemy_visible = vision_state.get("enemy_visible", False)
        self.enemy_pokemon = vision_state.get("enemy_pokemon")
        self.enemy_hp_percentage = vision_state.get("enemy_hp_percentage")
        self.player_hp_percentage = vision_state.get("player_hp_percentage")
        self.battle_ui_visible = vision_state.get("battle_ui_visible", False)
        self.text_box_content = vision_state.get("text_box_content")
        
        # Enriched data
        self.enemy_data = enricher.get_pokemon_data(self.enemy_pokemon) if self.enemy_pokemon else None
    
    @property
    def enemy_types(self) -> Optional[List[str]]:
        return self.enemy_data["types"] if self.enemy_data else None
    
    @property
    def enemy_weaknesses(self) -> Optional[List[str]]:
        return self.enemy_data["weaknesses"] if self.enemy_data else None
    
    @property
    def enemy_resistances(self) -> Optional[List[str]]:
        return self.enemy_data["resistances"] if self.enemy_data else None
    
    @property
    def enemy_base_stats(self) -> Optional[Dict[str, int]]:
        return self.enemy_data["base_stats"] if self.enemy_data else None
    
    def get_type_advice(self) -> str:
        """Generate type matchup advice for AI context"""
        if not self.enemy_weaknesses:
            return "No type data available"
        
        return f"Use {', or '.join(self.enemy_weaknesses)} type moves for super-effective damage"
    
    def get_defense_advice(self) -> str:
        """Generate defensive advice"""
        if not self.enemy_resistances:
            return "No resistance data available"
        
        return f"Avoid {', and '.join(self.enemy_resistances)} type moves (resisted)"

# Integration Pattern

class VisionProcessor:
    def __init__(self, api_key: str, provider: str = "openai"):
        # ... existing initialization ...
        self.pokemon_enricher = PokemonEnricher()
    
    def extract_battle_state(self, frame: np.ndarray) -> Optional[EnrichedBattleState]:
        """Extract battle state with Pokédex enrichment"""
        # Step 1: Extract visual information
        screen_type = self.classify_screen(frame)
        if screen_type.screen_type != "battle":
            return None
        
        # Step 2: Detect Pokemon (from vision model)
        enemy_detection = self.detect_enemy_pokemon(frame)
        if not enemy_detection:
            return None
        
        # Step 3: Extract HP from visual HP bars
        enemy_hp = self.extract_hp_from_bar(frame, is_enemy=True)
        player_hp = self.extract_hp_from_bar(frame, is_enemy=False)
        
        # Step 4: Create enriched battle state
        vision_state = {
            "enemy_visible": True,
            "enemy_pokemon": enemy_detection.name,
            "enemy_hp_percentage": enemy_hp,
            "player_hp_percentage": player_hp,
            "battle_ui_visible": True,
            "text_box_content": self.extract_dialog_text(frame)
        }
        
        return EnrichedBattleState(vision_state, self.pokemon_enricher)

# Enhanced Prompt Template for AI

POKEMON_DETECTION_PROMPT = """
Analyze this Pokemon battle screenshot.

For the ENEMY Pokemon:
1. Identify the Pokemon species (if visible)
2. Estimate HP percentage (0-100%) from HP bar
3. Extract any visible level
4. Note the Pokemon's pose/animation state

For the PLAYER Pokemon:
1. Identify the Pokemon species (if visible in party UI)
2. Estimate HP percentage
3. Extract current move menu if visible

IMPORTANT: Only identify Pokemon you are confident about. 
If uncertain, respond "UNKNOWN" with 0% confidence.

Response format:
{
  "enemy_pokemon": "Charmander" or "UNKNOWN",
  "enemy_confidence": 0.85,
  "enemy_hp_percent": 75,
  "player_pokemon": "Squirtle" or "UNKNOWN", 
  "player_hp_percent": 45,
  "battle_state": "active|menu|animation|victory|defeat",
  "reasoning": "Brief identification rationale"
}
"""
```

### Data Structures

```python
@dataclass
class PokemonDetection:
    """Result from AI vision model"""
    name: str
    confidence: float
    bbox: Optional[Tuple[int, int, int, int]]  # x, y, w, h
    sprite_hash: Optional[str]

@dataclass 
class EnrichedBattleContext:
    """Complete battle context for Strategist/Tactician"""
    enemy_detection: PokemonDetection
    enemy_pokedex: Optional[Dict[str, Any]]
    player_hp: int
    enemy_hp: int
    turn_number: int
    available_moves: List[str]
    
    def get_strategic_summary(self) -> str:
        """Generate AI-ready summary with Pokédex data"""
        if not self.enemy_pokedex:
            return f"Unknown enemy Pokemon, HP: {self.enemy_hp}%, Use basic attacks"
        
        pkm = self.enemy_pokedex
        return f"""
Enemy: {pkm['name']} (Types: {', '.join(pkm['types'])})
HP: {self.enemy_hp}%
Weaknesses: {', '.join(pkm['weaknesses']) if pkm['weaknesses'] else 'None'}
Resistances: {', '.join(pkm['resistances']) if pkm['resistances'] else 'None'}
""".strip()
```

### Usage in AI Decision Loop

```python
def make_battle_decision(enemy_pokemon: str, battle_context: EnrichedBattleContext) -> str:
    """
    AI uses Pokédex-enriched context to make decisions
    """
    if not battle_context.enemy_pokedex:
        # Fallback: cautious approach
        return "Use neutral moves, preserve PP"
    
    # Get type advantage info
    weaknesses = battle_context.enemy_pokedex["weaknesses"]
    
    # AI reasoning with expert data
    if weaknesses:
        # Prioritize super-effective moves
        return f"Use {weaknesses[0]} type moves for maximum damage"
    else:
        # No clear weaknesses, use strongest neutral move
        return "Use highest power available move"

# Example workflow:
# 1. Vision detects "Geodude" with 85% confidence
# 2. pypokedex.get(name="geodude") returns Rock/Ground types
# 3. Type chart lookup: Weak to Water, Grass, Ice, Fighting, Ground, Steel
# 4. AI context: "Enemy: Geodude (Types: Rock, Ground). Weaknesses: Water, Grass, Ice..."
# 5. AI decision: "Use Water Gun (Water type, super-effective)"
# 6. Result: 2x damage, AI learns that type matching works
```

### Benefits of This Approach

1. **Expert Knowledge**: Provides factual type data without LLM hallucination
2. **Cost Efficiency**: Pokédex lookup is free and instant vs LLM API calls
3. **Learning Foundation**: AI can verify that Water > Fire actually works
4. **Error Recovery**: If vision misidentifies, Pokédex validates types
5. **Authentic Content**: AI makes decisions based on game knowledge, not memory hacks

---

## 2. AI Model Integration Module

### Purpose
Manages local AI model loading, inference, and response parsing. Each AI instance runs a separate model process.

### Interface Contract

```python
class AIModelInterface:
    def __init__(self, model_path: str, config: AIConfig)
    
    # Core inference
    def generate_response(
        self,
        prompt: str,
        screenshot: Optional[np.ndarray] = None,
        max_tokens: int = 500,
        temperature: float = 0.3
    ) -> AIModelResponse
    
    def parse_ai_commands(self, raw_response: str) -> List[ParsedCommand]
    
    # Context management
    def add_to_context(self, message: str) -> None
    def get_context_window_info(self) -> ContextInfo
    def clear_context(self) -> None
    
    # Tool use
    def has_tool_capability(self) -> bool
    def request_tool_use(self, tool_name: str, parameters: Dict) -> ToolResponse
    
    # Performance
    def get_inference_stats(self) -> InferenceStats
    def unload_model(self) -> None
```

### Model Configuration

```python
@dataclass
class AIModelConfig:
    """Configuration for a local AI model"""
    model_path: str  # Path to GGUF file
    model_type: Literal["llama", "mistral", "custom"]
    context_length: int
    gpu_layers: int  # Layers to offload to GPU
    thread_count: int  # CPU threads
    
    # Generation parameters
    default_temperature: float = 0.3
    default_top_p: float = 0.95
    default_top_k: int = 40
    repeat_penalty: float = 1.1
    
    # Capabilities
    supports_vision: bool = False  # Can process screenshots
    supports_tools: bool = False   # Can use web search, etc.
    
@dataclass  
class AIModelResponse:
    """Response from AI model inference"""
    text: str  # Raw response
    tokens_used: int
    generation_time_ms: float
    finish_reason: Literal["stop", "length", "error"]
    tool_calls: Optional[List[ToolCall]]
    
@dataclass
class ToolCall:
    """Tool invocation requested by AI"""
    tool_name: str  # "web_search", "calculator", etc.
    parameters: Dict[str, Any]
    id: str
```

### Prompt Templates

```python
class PromptManager:
    """Manages prompt templates for different game states"""
    
    def get_system_prompt(self, ai_level: int) -> str:
        """Base system prompt with AI capabilities"""
        return f"""You are an AI playing Pokemon, skill level {ai_level}/10.

CAPABILITIES:
- You can see the game screen and analyze what's happening
- You can press buttons: A, B, START, SELECT, UP, DOWN, LEFT, RIGHT
- To press a button, output: [BUTTON:A] or [BUTTON:UP] etc.
- You can batch commands for efficiency
- You understand Pokemon types, moves, and strategy{' (you can search web if needed)' if ai_level >= 5 else ''}

YOUR GOAL: Become the Pokemon Champion by defeating all Gym Leaders and the Elite Four.

RESPONSE FORMAT:
REASONING: <your analysis and strategy>
COMMAND: [BUTTON:<button>]
CONFIDENCE: <0.0-1.0>
WAIT_TICKS: <how many ticks to wait before next screenshot>
"""
    
    def get_battle_prompt(self, game_state: GameState, memory: MemoryManager) -> str:
        """Prompt for when in battle"""
        return f"""CURRENT SITUATION - BATTLE MODE:

{self.get_health_status(game_state)}

{memory.get_relevant_lessons(game_state)}

What button should you press (A, B, UP, DOWN, LEFT, RIGHT)?"""
    
    def get_exploration_prompt(self, game_state: GameState, memory: MemoryManager) -> str:
        """Prompt for overworld exploration"""
        current_goal = memory.get_current_objective()
        return f"""CURRENT SITUATION - OVERWORLD:

Location: {game_state.current_location or 'Unknown'}
Current Goal: {current_goal}

Where should you go? What button should you press?"""
```

---

## 3. Command Relay & Parser Module

### Purpose
Converts AI text responses into validated emulator commands. Handles the relay between AI decision-making and game execution.

### Interface Contract

```python
class CommandRelay:
    def __init__(self, validator: CommandValidator)
    
    # Parsing and validation
    def parse_ai_response(self, ai_response: AIModelResponse) -> CommandParseResult
    def validate_command(self, command: ParsedCommand) -> ValidationResult
    
    # Command execution
    def execute_command(self, command: ParsedCommand, emulator: EmulatorInterface) -> ExecutionResult
    def execute_batch(self, batch: BatchCommand, emulator: EmulatorInterface) -> BatchExecutionResult
    
    # Safety and limits
    def check_command_safety(self, command: ParsedCommand) -> SafetyRating
    def enforce_rate_limits(self, commands: List[ParsedCommand]) -> RateLimitResult
    
    # Error handling
    def handle_execution_error(self, error: ExecutionError) -> RecoveryCommand
```

### Response Parsing

```python
@dataclass
class CommandParseResult:
    """Result of parsing AI text response"""
    success: bool
    commands: List[ParsedCommand]
    parse_errors: List[str]
    confidence_adjusted: bool  # Did confidence get modified based on parsing?
    
@dataclass  
class ParsedCommand:
    """Structured command extracted from AI response"""
    action: Literal["press", "hold", "sequence", "batch"]
    button: Optional[Literal["A", "B", "START", "SELECT", "UP", "DOWN", "LEFT", "RIGHT"]]
    duration_ms: Optional[int] = None
    sequence: Optional[List[ButtonAction]] = None
    batch: Optional[BatchCommand] = None
    wait_ticks: int = 60  # Default: wait 60 ticks (1 second)
    
@dataclass
class ButtonAction:
    """Single button action in a sequence"""
    button: str
    duration_ms: int
    pause_ms: int  # Pause after this action
```

### Response Format Enforcement

```python
class ResponseParser:
    """Parse AI text output into structured commands"""
    
    COMMAND_PATTERN = r'\[BUTTON:([A-Z]+)\]'
    REASONING_PATTERN = r'REASONING:\s*(.+)'
    CONFIDENCE_PATTERN = r'CONFIDENCE:\s*([0-9.]+)'
    WAIT_TICKS_PATTERN = r'WAIT_TICKS:\s*(\d+)'
    
    def parse_response(self, raw_text: str) -> CommandParseResult:
        """Extract structured data from AI response"""
        
        commands = []
        errors = []
        
        # Extract reasoning
        reasoning_match = re.search(self.REASONING_PATTERN, raw_text, re.IGNORECASE)
        reasoning = reasoning_match.group(1).strip() if reasoning_match else "No reasoning provided"
        
        # Extract confidence
        confidence_match = re.search(self.CONFIDENCE_PATTERN, raw_text, re.IGNORECASE)
        confidence = float(confidence_match.group(1)) if confidence_match else 0.5
        
        # Extract wait ticks
        wait_match = re.search(self.WAIT_TICKS_PATTERN, raw_text, re.IGNORECASE)
        wait_ticks = int(wait_match.group(1)) if wait_match else 60
        
        # Extract button commands
        button_matches = re.findall(self.COMMAND_PATTERN, raw_text, re.IGNORECASE)
        
        if not button_matches:
            errors.append("No valid button commands found in response")
            return CommandParseResult(
                success=False,
                commands=[],
                parse_errors=errors,
                confidence_adjusted=False
            )
        
        # Convert to parsed commands
        for button in button_matches:
            button = button.upper()
            if button in ["A", "B", "START", "SELECT", "UP", "DOWN", "LEFT", "RIGHT"]:
                commands.append(ParsedCommand(
                    action="press",
                    button=button,
                    wait_ticks=wait_ticks,
                    reasoning=reasoning,
                    confidence=confidence
                ))
            else:
                errors.append(f"Invalid button: {button}")
        
        return CommandParseResult(
            success=len(commands) > 0,
            commands=commands,
            parse_errors=errors,
            confidence_adjusted=bool(errors)
        )
```

### Command Batching Examples

```python
class CommandBatcher:
    """Optimize command sequences for efficiency"""
    
    def batch_directional_commands(self, commands: List[ParsedCommand]) -> List[ParsedCommand]:
        """Convert repeated directional inputs into batch commands"""
        optimized = []
        i = 0
        
        while i < len(commands):
            if commands[i].action == "press" and commands[i].button in ["UP", "DOWN", "LEFT", "RIGHT"]:
                # Count consecutive same-direction commands
                direction = commands[i].button
                count = 1
                
                while (i + count < len(commands) and 
                       commands[i + count].action == "press" and 
                       commands[i + count].button == direction):
                    count += 1
                
                if count >= 3:  # Only batch if 3+ consecutive
                    # Create batch command
                    batch = BatchCommand(
                        command_type="walk",
                        direction=direction.lower(),
                        steps=count,
                        through_grass=False,  # Will be determined by location
                        estimated_duration_ticks=count * 15
                    )
                    
                    optimized.append(ParsedCommand(
                        action="batch",
                        button=None,
                        batch=batch,
                        wait_ticks=batch.estimated_duration_ticks
                    ))
                    
                    i += count
                else:
                    optimized.append(commands[i])
                    i += 1
            else:
                optimized.append(commands[i])
                i += 1
        
        return optimized
```

---

## 4. Tick-Based Timing Module

### Purpose
Manages game timing in "ticks" (game frames) to control screenshot frequency and command execution timing.

### Interface Contract

```python
class TickManager:
    def __init__(self, ticks_per_second: int = 60)  # Game Boy runs at ~60fps
    
    # Timing control
    def get_current_tick(self) -> int
    def wait_ticks(self, tick_count: int) -> None
    def get_ticks_since_last_screenshot(self) -> int
    
    # Adaptive timing
    def calculate_screenshot_interval(self, game_state: GameState) -> int
    def should_process_frame(self) -> bool  # Based on tick counter
    
    # Animation handling
    def detect_animation_in_progress(self, frame_history: List[np.ndarray]) -> bool
    def estimate_animation_duration(self, animation_type: str) -> int
```

### Timing Configuration

```python
SCREENSHOT_INTERVALS = {
    "battle": 60,      # 1 second during battle
    "overworld": 90,   # 1.5 seconds while exploring
    "dialog": 30,      # 0.5 seconds during text (rapid)
    "menu": 60,        # 1 second in menus
    "animation": 150,  # 2.5 seconds during animations
}

COMMAND_DURATION_TICKS = {
    "press_button": 15,     # 0.25 seconds
    "menu_select": 30,      # 0.5 seconds
    "walk_step": 15,        # 0.25 seconds per step
    "battle_animation": 120, # 2 seconds
    "text_scroll": 30,      # 0.5 seconds
}
```

### Adaptive Timing Logic

```python
def calculate_screenshot_interval(game_state: GameState) -> int:
    """Dynamically adjust screenshot frequency based on game state"""
    
    base_interval = SCREENSHOT_INTERVALS.get(game_state.screen_type, 60)
    
    # Adjust based on recent activity
    if game_state.last_command:
        if "battle" in game_state.last_command.lower():
            # More frequent during battle animations
            base_interval = SCREENSHOT_INTERVALS["animation"]
    
    # Check for stable frames (no changes = can wait longer)
    if game_state.ticks_since_last_change > 180:  # 3 seconds stable
        base_interval *= 2  # Double the wait time
    
    # Cap at reasonable maximum
    return min(base_interval, 300)  # Max 5 seconds between screenshots
```

---

## 5. Memory Management for Multiple AI Instances

### Purpose
Each AI instance maintains its own memory system tracking objectives, learned lessons, and game progress.

### Per-AI Memory Structure

```python
class MemoryManager:
    def __init__(self, ai_instance_id: str, persistence_path: Path)
    
    # Long-term objectives
    def set_main_goal(self, goal: str) -> None  # "Become Champion"
    def add_sub_goal(self, goal: Objective) -> None  # "Defeat Brock", "Get Boulder Badge"
    def mark_goal_complete(self, goal_id: str) -> None
    def get_current_objectives(self) -> List[Objective]
    
    # Location & navigation
    def record_location(self, location: str, purpose: str) -> None
    def get_path_to(self, destination: str) -> Optional[List[Direction]]
    def note_blocked_path(self, location: str, obstacle: str) -> None
    
    # Learned lessons
    def add_lesson(self, lesson: LearnedLesson) -> None
    def get_relevant_lessons(self, context: GameState) -> List[LearnedLesson]
    def update_lesson_confidence(self, lesson_id: str, success: bool) -> None
```

### Objective Tracking

```python
@dataclass
class Objective:
    """A specific goal the AI is trying to accomplish"""
    objective_id: str
    description: str
    priority: int  # 1-10
    status: Literal["not_started", "in_progress", "completed", "blocked"]
    
    # Context
    location_required: Optional[str]
    prerequisites: List[str]  # Other objectives that must be completed first
    expected_difficulty: float  # 0.0 to 1.0
    
    # AI-specific
    attempts: int
    learned_from_failure: bool
    alternate_strategies: List[str]

class ObjectiveManager:
    """Manages hierarchical objectives for AI"""
    
    def __init__(self):
        self.main_goal = "Become Pokemon Champion"
        self.objectives = self._initialize_default_objectives()
    
    def _initialize_default_objectives(self) -> List[Objective]:
        """Set up standard Pokemon progression objectives"""
        return [
            Objective(
                objective_id="starter",
                description="Choose a starter Pokemon",
                priority=10,
                location_required="Pallet Town",
                prerequisites=[],
                expected_difficulty=0.1
            ),
            Objective(
                objective_id="brock", 
                description="Defeat Gym Leader Brock and get Boulder Badge",
                priority=9,
                location_required="Pewter City Gym",
                prerequisites=["starter"],
                expected_difficulty=0.3
            ),
            Objective(
                objective_id="misty",
                description="Defeat Gym Leader Misty and get Cascade Badge", 
                priority=9,
                location_required="Cerulean City Gym",
                prerequisites=["brock"],
                expected_difficulty=0.4
            ),
            # ... etc up to Champion
        ]
    
    def get_next_objective(self) -> Optional[Objective]:
        """Get the highest priority objective that's ready"""
        ready = [
            obj for obj in self.objectives
            if obj.status == "not_started" and 
               all(prereq in [o.objective_id for o in self.objectives 
                            if o.status == "completed"] for prereq in obj.prerequisites)
        ]
        return max(ready, key=lambda o: o.priority) if ready else None
```

### Hierarchical Memory Example

```python
# Main Goal
"Become Pokemon Champion"
└─── Objective 1: "Get Boulder Badge from Brock"
     ├─── Sub-goal: "Travel to Pewter City"
     │    ├─── Remember: "Need to go north through Route 1"
     │    └─── Lesson: "Wild Pokemon appear in tall grass"
     ├─── Sub-goal: "Defeat Brock's Geodude and Onix"  
     │    ├─── Strategy: "Use Water or Grass moves"
     │    ├─── Lesson: "Geodude uses Defense Curl on turn 1"
     │    └─── Pokemon needed: "Water type Pokemon"
     └─── Sub-goal: "Enter the gym battle"
          └─── Location: "Pewter City Gym coordinates"
```

---

## 6. Multi-AI Comparison and Ranking System

### Purpose
Tracks performance of multiple AI instances and creates leaderboards for comparison.

### Performance Scoring Algorithm

```python
class PerformanceScorer:
    """Calculate composite scores for AI comparison"""
    
    def calculate_overall_score(self, metrics: AIPerformanceMetrics) -> float:
        """Weighted composite score"""
        
        # Base score components (0-100 each)
        win_rate_score = metrics.win_rate * 100
        
        # Efficiency (damage ratio)
        efficiency_score = min(metrics.avg_damage_ratio * 50, 100)
        
        # Progress (badges)
        progress_score = (metrics.badges_count / 8) * 100  # 8 badges in Gen 1
        
        # Learning velocity (improvement over time)
        learning_score = (metrics.improvement_velocity + 1) * 50  # -1 to 1 → 0 to 100
        learning_score = max(0, min(100, learning_score))
        
        # Resource management (less potions = better play)
        resource_score = max(0, 100 - (metrics.total_potions_used / 10))
        
        # Composite (weighted average)
        weights = {
            'win_rate': 0.25,
            'efficiency': 0.20,
            'progress': 0.30,  # Most important
            'learning': 0.15,
            'resource': 0.10
        }
        
        overall = (
            win_rate_score * weights['win_rate'] +
            efficiency_score * weights['efficiency'] +  
            progress_score * weights['progress'] +
            learning_score * weights['learning'] +
            resource_score * weights['resource']
        )
        
        # Skill level bonus (encourages higher skill AIs to be creative)
        skill_bonus = metrics.skill_level * 2  # Up to 20 point bonus
        
        return min(100, overall + skill_bonus)
```

### Leaderboard Generation

```python
class LeaderboardGenerator:
    """Generate real-time leaderboard"""
    
    def __init__(self):
        self.ai_instances: Dict[str, AIInstance] = {}
        self.snapshots: List[LeaderboardSnapshot] = []
    
    def update_leaderboard(self) -> LeaderboardSnapshot:
        """Current rankings"""
        metrics = []
        
        for instance_id, instance in self.ai_instances.items():
            if instance.is_running:
                metrics.append({
                    'instance': instance,
                    'metrics': instance.get_performance_metrics(),
                    'score': self.calculate_overall_score(instance)
                })
        
        # Sort by score
        sorted_rankings = sorted(metrics, key=lambda m: m['score'], reverse=True)
        
        # Add ranks
        for rank, entry in enumerate(sorted_rankings, 1):
            entry['metrics'].rank = rank
        
        snapshot = LeaderboardSnapshot(
            timestamp=datetime.now(),
            rankings=sorted_rankings
        )
        
        self.snapshots.append(snapshot)
        return snapshot
    
    def get_trending_improvement(self, hours: int = 1) -> List[AIInstance]:
        """Which AIs are improving fastest"""
        recent = self.snapshots[-12:]  # Last hour (5-min snapshots)
        
        improvements = []
        for instance_id in self.ai_instances.keys():
            scores = [s.get_score(instance_id) for s in recent if s.has_instance(instance_id)]
            if len(scores) >= 2:
                improvement = scores[-1] - scores[0]
                improvements.append((instance_id, improvement))
        
        return sorted(improvements, key=lambda x: x[1], reverse=True)
```

---

## 7. Error Recovery and Resilience

### Error Types and Recovery Strategies

```python
ERROR_HANDLING = {
    "stasis_error": {
        "detection": "screen_unchanged_for_50_ticks",
        "recovery": "random_button_press",
        "retry_count": 3,
        "escalation": "reset_to_last_checkpoint"
    },
    "ai_hallucination": {
        "detection": "invalid_button_command",
        "recovery": "reprompt_with_correction",
        "retry_count": 2,
        "escalation": "fallback_to_safe_action"
    },
    "vision_parsing_failure": {
        "detection": "cannot_parse_game_state",
        "recovery": "wait_and_retry",
        "retry_count": 5,
        "escalation": "use_ram_data_fallback"
    },
    "animation_timing": {
        "detection": "command_during_animation",
        "recovery": "wait_for_animation_end",
        "retry_count": 10,
        "escalation": "force_command_after_timeout"
    }
}
```

### Watchdog Timer System

```python
class WatchdogTimer:
    """Detects if AI or game is stuck"""
    
    def __init__(self, timeout_ticks: int = 300):  # 5 seconds default
        self.timeout = timeout_ticks
        self.last_progress_tick = 0
        self.stuck_count = 0
    
    def record_progress(self, current_tick: int):
        """Call when meaningful progress is made"""
        self.last_progress_tick = current_tick
        self.stuck_count = 0
    
    def check_stuck(self, current_tick: int) -> Optional[str]:
        """Return error type if stuck"""
        ticks_since_progress = current_tick - self.last_progress_tick
        
        if ticks_since_progress > self.timeout:
            self.stuck_count += 1
            
            if self.stuck_count > 3:
                return "critical_stasis"
            return "potential_stuck"
        
        return None
    
    def get_recovery_command(self, error_type: str) -> ParsedCommand:
        """Generate appropriate recovery action"""
        if error_type == "critical_stasis":
            # Random button press to try to unstick
            buttons = ["A", "B", "UP", "DOWN", "LEFT", "RIGHT"]
            return ParsedCommand(
                action="press",
                button=random.choice(buttons),
                reasoning="Stuck recovery: random button press",
                confidence=0.3
            )
        
        # Default: press B (usually backs out of menus)
        return ParsedCommand(
            action="press",
            button="B",
            reasoning="Stuck recovery: try backing out",
            confidence=0.4
        )
```

---

## 8. Configuration System

### config/settings.yaml

```yaml
# AI Configuration
ai:
  instances:
    - id: "ai_level_1"
      skill_level: 1
      model_path: "models/llama-3B.gguf"
      enable_batching: false
      enable_tools: false
    
    - id: "ai_level_5"
      skill_level: 5
      model_path: "models/mistral-7B.gguf"
      enable_batching: true
      enable_tools: true
      web_search_endpoint: "http://localhost:8000/search"
    
    - id: "ai_level_10"
      skill_level: 10
      model_path: "models/llama-13B.gguf"
      enable_batching: true
      enable_tools: true
      max_batch_size: 20

# Emulator
emulator:
  rom_path: "roms/Pokemon_Red.gb"
  initial_state: "saves/pallet_town_start.state"
  instance_count: 3  # One per AI
  ticks_per_second: 60

# Timing
timing:
  screenshot_intervals:
    battle: 60        # 1 second
    overworld: 90     # 1.5 seconds
    dialog: 45        # 0.75 seconds
    animation: 120    # 2 seconds
  command_durations:
    press_button: 15
    walk_step: 15
    menu_select: 30
    animation_buffer: 60

# Performance Tracking
performance:
  metrics_interval: 300  # Calculate every 5 minutes
  leaderboard_history: 1000  # Keep last 1000 snapshots
  scoring_weights:
    win_rate: 0.25
    progress: 0.30
    efficiency: 0.20
    learning: 0.15
    resource: 0.10

# Error Recovery
error_handling:
  stasis_timeout: 180  # 3 seconds without progress
  max_retries: 3
  enable_auto_recovery: true
  save_checkpoints: true
  checkpoint_interval: 1800  # Every 30 minutes

# Logging
logging:
  decision_log_path: "logs/decisions/"
  metrics_log_path: "logs/metrics/"
  log_level: "INFO"
  console_output: true
  
  # Log rotation
  max_log_size_mb: 100
  keep_logs_for_days: 7
```

---

## 9. Implementation Priorities

### Phase 1: Foundation (Week 1)
- [ ] Set up PyBoy emulator (single instance working)
- [ ] Screenshot capture and display
- [ ] Basic button input system
- [ ] One AI model running locally (simple 3B model)
- [ ] Command relay system (text → button press)

### Phase 2: Multi-AI (Week 2)
- [ ] Run multiple AI instances simultaneously
- [ ] Basic performance tracking and logging
- [ ] Command parsing and validation
- [ ] Simple memory system (current objective tracking)

### Phase 3: Intelligence (Week 3)
- [ ] Implement Tri-Tier memory (Observer/Strategist/Tactician)
- [ ] Reflection engine (learning from mistakes)
- [ ] Tool use (web search when stuck)
- [ ] Command batching optimization

### Phase 4: Comparison & Analytics (Week 4)
- [ ] Leaderboard system
- [ ] Real-time dashboard
- [ ] Competition logic (10-12 AIs simultaneously)
- [ ] Performance metrics and scoring

### Phase 5: Polish (Week 5)
- [ ] Error recovery systems
- [ ] Adaptive timing
- [ ] Animation detection
- [ ] Testing and bug fixes

---

## 10. Key Metrics to Track

### Per-AI Metrics
- Win rate per badge/battle type
- Decision success rate
- Command confidence accuracy
- Learning velocity (improvement over time)
- Resource efficiency (potions/PP used)
- Total playtime and progress

### System Metrics  
- Screenshot processing latency
- AI inference time
- Total ticks elapsed
- Commands per minute
- Error recovery count
- Cost per model (if API-based in future)

### Comparison Metrics
- Which skill level performs best
- Learning rate by model size
- Optimal command batch sizes
- Effectiveness of web search/tools

---

## Summary of Key Differences from Original v1 Specs

1. **Local AI models** instead of API-based (Claude/GPT-4)
2. **Relay architecture** with separate AI → command → execution flow
3. **Multiple AI instances** running simultaneously for comparison
4. **Command batching** for efficiency (walk 10 steps vs 10 screenshots)
5. **Tick-based timing** instead of wall-clock timing
6. **Skill-based AI levels** with different model sizes/capabilities
7. **Tool use/web search** built into higher-skill AIs
8. **Hierarchical objective tracking** for navigation
9. **No API cost optimization** (local models), but still optimize for speed
10. **Competition/leaderboard** focus comparing AI strategies

This architecture is designed to run **locally with multiple AI instances simultaneously**, comparing different approaches to playing Pokemon, with the AI learning and improving over time through the Reflection Engine.