# Ultrathink Analysis: Complete Pokemon Gameplay Workflow

## Executive Summary

A comprehensive breakdown of the Pokemon GB gameplay lifecycle, AI decision-making requirements, and prompt strategy for each game phase.

---

## 🎮 Complete Game Lifecycle Analysis

### **Zone 1: Game Boot & Initialization (0-200 ticks)**

**0-30 ticks: Opening Sequence**
- Visual: Game Freak logo animation, title screen fade-in
- Screensaver: Pokemon intro animation
- Audio: Opening theme music
- AI Action: Wait for title screen to load
- Required Data: None (passive phase)

**30-60 ticks: Title Screen**
- Visual: "PRESS START" text, background Pokemon sprites
- Available Actions: Press START, A button
- AI Decision: Press START to begin
- Prompt Type: `boot/title_screen.txt`

**60-120 ticks: Main Menu**
- Visual: Menu options [New Game, Options, Continue]
- Save Check: Detect if valid save file exists
- AI Decision: 
  - If save exists → "Continue" → Load state
  - If no save → "New Game" → Start fresh game
- Prompt Type: `boot/main_menu.txt`

**120-200 ticks: Options (if selected)**
- Visual: Text speed, battle style, sound settings
- AI Action: Configure settings for optimal AI gameplay
- Prompt Type: `configuration/settings.txt`

### **Zone 2: New Game Initialization (200-500 ticks)**

**200-250 ticks: Professor Oak Intro**
- Visual: Oak dialogue "Welcome to the world of Pokemon!"
- AI Action: Press A repeatedly to advance dialogue
- Prompt Type: `story/intro_dialogue.txt`

**250-350 ticks: Starter Pokemon Selection**
- Visual: Three Pokeballs with Bulbasaur, Charmander, Squirtle
- AI Decision: Analyze optimal starter choice
  - Consider early game advantages
  - Type effectiveness against first gym (Rock)
  - Availability of wild Pokemon
- Recommended Choice: Bulbasaur (Rock super-effective)
- Prompt Type: `gameplay/starter_selection.txt`

**350-450 ticks: Rival Selection**
- Visual: Rival chooses Pokemon (counter to player's)
- AI Action: Note rival's Pokemon for future planning
- Prompt Type: `gameplay/rival_selection.txt`

**450-500 ticks: Naming Sequence**
- Visual: Player name input screen
- AI Action: Generate or use default name
- Prompt Type: `configuration/naming.txt`

### **Zone 3: Pallet Town Tutorial (500-800 ticks)**

**500-600 ticks: Get Pokedex**
- Visual: Oak gives player Pokedex
- AI Action: Accept Pokedex (mission critical item)
- Memory Update: Inventory: Pokedex acquired
- Prompt Type: `gameplay/item_acquisition.txt`

**600-700 ticks: Get Pokeballs**
- Visual: Oak gives 5 Pokeballs
- AI Action: Accept Pokeballs (essential for catching)
- Memory Update: Inventory: Pokeballs x5
- Prompt Type: `gameplay/item_acquisition.txt`

**700-750 ticks: Mom Dialogue**
- Visual: Mom gives advice, mentions Route 1
- AI Action: Listen to advice, prepare for Route 1
- Prompt Type: `story/m Guidance.txt`

**750-800 ticks: Leave House**
- Visual: Standing outside mom's house in Pallet Town
- AI Action: Plan route to Viridian City
- Prompt Type: `navigation/path_planning.txt`

### **Zone 4: Route 1 Wild Zone (800-1500 ticks)**

**Navigation Phase: Walking to Viridian City**
- Visual: Overworld screen, grass patches
- Player HP: Full health
- Inventory: Potion x1, Antidote x1 from early areas
- Wild Enemies: Pidgey (Normal/Flying), Rattata (Normal)

**Random Encounter Detection (every 15 ticks in grass)**
- Visual: Battle transition animation wild Pokemon appears
- Enemy: Pidgey Lv2-5, Rattata Lv2-4
- AI Decision: Fight or run based on health and strategy

**Battle Sequence (per encounter):**

**Step 1: Battle Start (10-20 ticks)**
- Visual: Wild Pokemon sprite appears, battle UI loads
- Enemy identified from vision: Pidgey Lv3
- Player Pokemon: Starter (Lv5)
- AI Decision: Determine strategy
- Prompt Type: `battle/wild_encounter_start.txt`

**Step 2: Move Selection (20-60 ticks)**
- Visual: Battle menu [Fight, Bag, Pokemon, Run]
- Available moves: Tackle (normal), Growl (status), type move
- AI Decision: Select optimal move
  - Check enemy type (Pidgey = Normal/Flying)
  - Choose damage vs status move
  - Consider EXP gain potential
- Prompt Type: `battle/move_selection.txt`

**Step 3: Attack Animation (60-100 ticks)**
- Visual: Pokemon attack animation, damage calculation
- AI Action: Wait for animation completion
- Prompt Type: None (passive wait)

**Step 4: Enemy Turn (100-140 ticks)**
- Visual: Enemy attacks, player HP changes
- AI Action: Analyze damage taken
- Memory Update: Enemy attack patterns, move effectiveness
- Prompt Type: `battle/defense_analysis.txt`

**Phase Decision Points:**

**Run Conditions (when to flee):**
- Player HP < 30% and no healing items
- EXP not useful (already leveled)
- Low catch rate Pokemon encountered

**Fight Conditions:**
- Good EXP opportunity
- Wanted for future team
- Type disadvantage manageable

### **Zone 5: Viridian City Services (1500-2500 ticks)**

**Pokemon Center Entry**
- Visual: Nurse Joy at counter, "WE HOPE YOU SEE YOUR POKEMON AGAIN!"
- AI Action: Approach counter, heal Pokemon
- Prompt Type: `services/pokemon_center.txt`

**Pokemon Mart Shopping**
- Visual: Shop interface with items and prices
- Inventory: P$1000+ from early game
- Priority Items:
  - Potion (Potion heals 20 HP - $300)
  - Antidote (Cures poison - $100) 
  - Poke Ball (Catching - $200)
  - Escape Rope (Instant flee - $550)
- AI Decision: Optimize purchases based on money and immediate needs
- Prompt Type: `services/shopping.txt`

**Gym Leader Challenges (Future phases)**
- Viridian Gym: Rock-type trainers
- Pewter Gym: Brock (Rock)
- And 6 more gyms progressively

### **Zone 6: Advanced Gameplay Patterns (Ongoing)**

**Dialog Handling Pattern:**
- Visual: Text box at bottom of screen
- AI Action: Press A repeatedly until dialog completes
- Memory Update: Story information received, NPC locations learned
- Prompt Type: `dialog/advance_text.txt`

**Menu Navigation Pattern:**
- Visual: Inventory grid, Pokemon party list
- AI Action: Navigate to desired item/Pokemon
- Prompt Type: `menu/navigation.txt`

**State Transitions:**
- Overworld → Battle (random encounter)
- Battle → Overworld (victory/defeat/run)
- Overworld → Menu (button press)
- Menu → Overworld (back/selection complete)
- Overworld → Dialog (NPC interaction)
- Dialog → Overworld (conversation complete)
- Any → Transition (map loading, cutscene)

---

## 🤖 AI Decision-Making Architecture

### **Memory Hierarchy Requirements**

**TIER 1: Persistent Observer Memory (Long-term)**
```json
{
  "journey_summary": {
    "playtime_hours": 4.5,
    "badges_obtained": [],
    "gyms_defeated": [],
    "pokemon_caught": {
      "pidgey": 3,
      "rattata": 2
    },
    "total_exp_gained": 12450,
    "money_earned": 8500,
    "key_locations_visited": [
      "Pallet Town",
      "Route 1 Wild",
      "Viridian City"
    ]
  },
  "team_history": {
    "starter_pokemon": "bulbasaur",
    "current_team": [
      {
        "species": "bulbasaur",
        "current_level": 8,
        "moves": ["Tackle", "Growl", "Vine Whip", "Poison Powder"],
        "nature": "calm",
        "ability": "Overgrow"
      }
    ]
  }
}
```

**TIER 2: Strategic Memory (Session-long)**
```json
{
  "battle_lessons": {
    "pidgey_weakness": {
      "effective": ["electric", "ice", "rock"],
      "resistance": ["grass", "bug", "fighting"],
      "confidence": 0.8,
      "encounters": 5
    },
    "rattata_strategy": {
      "fast_kill": "Tackle 2x",
      "efficiency": "95%",
      "recommended_level": "5+"
    }
  },
  "resource_strategy": {
    "money_management": "Save for Potions > Pokeballs",
    "healing_priority": "HP < 50% use Potion",
    "item_usage": "Use Antidote immediately on poison"
  },
  "failure_analysis": {
    "recent_defeats": [],
    "mistakes_made": [],
    "lessons_learned": []
  }
}
```

**TIER 3: Tactical Memory (Immediate context)**
```json
{
  "current_situation": {
    "game_screen": "overworld",
    "player_location": "Route 1 (tall grass)",
    "player_hp_percentage": 85,
    "active_party": ["bulbasaur Lv8"],
    "last_n_actions": ["walked 5 steps north", "encountered Pidgey"],
    "available_moves": ["Tackle", "Growl", "Vine Whip", "Poison Powder"]
  },
  "battle_context": {
    "active_battle": false,
    "enemy_pokemon": null,
    "enemy_hp": null,
    "turn_number": 0
  },
  "immediate_objective": {
    "primary_goal": "Reach Pewter City Gym",
    "current_task": "Grind Route 1 for EXP",
    "healing_threshold": "HP < 50% heal at Pokemon Center"
  }
}
```

### **Memory Compression Strategy**

**Compression Algorithm:**
1. **Level-based pruning**: Keep only recent 20% of low-importance events
2. **Summarization**: Replace repetitive events with aggregate stats
3. **Priority filtering**: Always preserve: badges, gym victories, Pokemon caught, major items
4. **Context relevance**: Keep data that affects current decisions

**Example Compression:**
```json
{
  "before": {
    "encounters": [
      {"pokemon": "Rattata", "lv3", "result": "defeated", "turns": 3},
      {"pokemon": "Rattata", "lv3", "result": "defeated", "turns": 3}, 
      {"pokemon": "Rattata", "lv2", "result": "defeated", "turns": 2},
      // ... 20 more Rattata encounters
    ]
  },
  "after": {
    "combat_stats": {
      "species": "Rattata",
      "encounters": 23,
      "win_rate": "95.7%",
      "avg_turns": 2.8,
      "exp_per_encounter": 24,
      "pattern": "Always use Tackle"
    }
  }
}
```

---

## 📝 Comprehensive Prompt Library

### **BOOT SEQUENCE PROMPTS**

`boot/title_screen.txt`
```
You are an AI playing Pokemon Red/Blue/Yellow.

CURRENT STATE: Title Screen
VISUAL: "PRESS START" visible, Pokemon sprites in background

OBJECTIVE: Initialize the game

AVAILABLE ACTIONS:
- Press START button

STRATEGY:
1. Press START to access main menu
2. Wait for menu to load

DECISION: What button should I press?
```

`boot/main_menu.txt`
```
You are an AI playing Pokemon. Analyzing the main menu.

CURRENT STATE: Main Menu
VISIBLE OPTIONS:
- New Game: Start fresh adventure
- Options: Game settings
- Continue: Load existing save

SAVE STATUS: {save_exists}

CONTEXT:
- If save_exists: Check save validity
- If no save: Must select New Game

OBJECTIVE: Choose optimal starting option

DECISION MAKING:
- Continue (if valid save exists)
- New Game (if no save or preferred fresh start)

DECISION: Which menu option should be selected?
```

`configuration/settings.txt`
```
You are an AI configuring Pokemon game settings.

CURRENT STATE: Options Menu
VISIBLE SETTINGS:
- Text Speed: [Slow/Mid/Fast]
- Battle Style: [Shift/Set]
- Sound: [Mono/Stereo]

OBJECTIVE: Configure optimal AI settings

AI PREFERENCES:
- Text Speed: FAST (faster dialogue advancement)
- Battle Style: SET (preserved battle animations for analysis)
- Sound: MONO (no audio preference)

DECISION: Configure settings for optimal AI performance
```

### **GAMEPLAY PROMPTS**

`gameplay/starter_selection.txt`
```
You are an AI selecting a starter Pokemon.

CURRENT STATE: Starter Pokemon Selection
VISIBLE STARTERS:
- Bulbasaur: Grass/Poison
- Charmander: Fire  
- Squirtle: Water

CONTEXT:
- First gym is Brock (Rock type) in Pewter City
- Early wild Pokemon: Pidgey (Normal/Flying), Rattata (Normal)
- Need strong early game Pokemon

STRATEGY ANALYSIS:
- Bulbasaur: Super-effective against Brock, strong against early grass Pokemon
- Charmander: Weak to Brock, weak to early route Pokemon
- Squirtle: Strong against Brock, decent early game

OPTIMAL CHOICE:
- Primary: Bulbasaur (easiest path)
- Secondary: Squirtle (solid alternative)
- Avoid: Charmander (most challenging start)

DECISION: Which starter should be chosen and why?
```

`navigation/path_planning.txt`
```
You are an AI Pokemon trainer navigating the world.

CURRENT STATE: Overworld Navigation
PLAYER LOCATION: {current_location}
OBJECTIVE: {current_objective}

AVAILABLE MOVEMENT OPTIONS:
- UP, DOWN, LEFT, RIGHT (d-pad)
- A button (interact/advance)
- B button (back/menu)

KNOWLEDGE:
- Next destination: {next_destination}
- Known routes: {known_routes}
- Pokemon Center location: {pokemon_center_location}
- Inventory: {inventory_summary}

NAVIGATION STRATEGY:
1. Take shortest path to objective
2. Avoid unnecessary tall grass (random encounters)
3. Visit Pokemon Center when HP < 50%
4. Collect useful items in route

CONTEXT MEMORY:
- Recent battles: {recent_battle_summary}
- HP status: {current_hp_percentage}
- Level progress: {player_pokemon_levels}

DECISION: What direction should I move and why?
```

### **BATTLE PROMPTS**

`battle/wild_encounter_start.txt`
```
You are an AI in a Pokemon battle.

CURRENT STATE: Wild Encounter Start
ENEMY POKEMON: {enemy_name} Lv.{enemy_level}
ENEMY TYPE: {enemy_types}
PLAYER POKEMON: {player_name} Lv.{player_level}
PLAYER HP: {player hp_percentage}%

VISUAL OBSERVATIONS:
- Enemy sprite: {pokemon_sprite_description}
- Enemy HP bar: {enemy_hp_bar_percentage}
- Available actions: Fight, Bag, Pokemon, Run

STRATEGY ASSESSMENT:
1. Combat viability: {win_probability}
2. EXP value: {exp_gained}
3. Escape feasibility: {can_safely_run}
4. Type advantage: {type_matchup}

DECISION OPTIONS:
- FIGHT: Engage in battle
- RUN: Flee encounter
- ITEM: Use Potion (if available and needed)
- SWITCH: Change Pokemon (if available)

DECISION: What should I do and why? Format as JSON:
{
  "action": "FIGHT|RUN|ITEM|SWITCH",
  "confidence": 0.0-1.0,
  "reasoning": "strategic explanation",
  "move": "recommended move or item"
}
```

`battle/move_selection.txt`
```
You are an AI choosing a battle move.

BATTLE CONTEXT:
Turn: {turn_number}
Enemy: {enemy_name} Lv.{enemy_level} ({enemy_types}) - HP: {enemy_hp}%
Player: {player_name} Lv.{player_level} - HP: {player_hp}%

AVAILABLE MOVES:
{list_moves_with_types_and_power}

MOVE ANALYSIS:
- {move1}: Type {type1}, Power {power1}, Accuracy {acc1}, PP {pp1}
- {move2}: Type {type2}, Power {power2}, Accuracy {acc2}, PP {pp2}
{move3_details}
{move4_details}

OPTIMAL MOVE CALCULATION:
1. Type effectiveness against enemy: {type_effectiveness}
2. Damage estimation: {estimated_damage_range}
3. KO probability: {ko_chance}
4. Risk assessment: {risk_level}

STRATEGIC CONSIDERATIONS:
- HP remaining = {player_hp}
- Enemy likely KO in {estimated_turns} turns
- PP conservation needed? {pp_conservation_status}
- Type advantage opportunity: {type_advantage_available}

DECISION: Which move should I use? Format as JSON:
{
  "move": "{move_name}",
  "confidence": 0.0-1.0,
  "estimated_damage": "{damage_range}",
  "reasoning": "why this move is optimal"
}
```

`battle/defense_analysis.txt`
```
Analyze enemy attack patterns.

BATTLE CONTEXT:
Enemy just used: {enemy_move_used}
Damage taken: {damage_amount}
Current HP: {current_hp}
Remaining HP: {remaining_hp_percentage}

ENEMY PATTERN ANALYSIS:
{enemy_attack_history}

PATTERN RECOGNITION:
- Enemy favorite move: {favorite_move}
- Attack frequency: {attack_frequency}
- Predicted next attacks: {predicted_next_moves}

DEFENSIVE STRATEGY:
- Counter move: {counter_move_suggestion}
- Healing needed: {healing_decision}
- Risk assessment: {risk_level}

MEMORY UPDATE TO ADD:
{
  "enemy_pokemon": "{enemy_name}",
  "battle_timestamp": "{timestamp}",
  "attack_pattern": {
    {enemy_move_name}: {
      "damage_range": "{min}-{max}",
      "frequency": "{uses out of {total}}",
      "effectiveness": "{high/medium/low}"
    }
  }
}
```

### **DIALOG PROMPTS**

`story/intro_dialogue.txt`
```
You are an AI experiencing Pokemon story.

CURRENT STATE: Dialog with Professor Oak
DIALOGUE TEXT: "{dialogue_content}"

CONTEXT:
- Stage: {story_stage_id}
- Active Character: {current_character}
- Dialogue Purpose: {dialog_purpose}

AI ACTION:
- Press A to advance dialog when text box appears
- Wait for text to complete before next action

STORY PROGRESS TRACKING:
- Information received: {key_information}
- Next objective: {next_objective}

DECISION: Wait or advance dialog?
```

### **SERVICE PROMPTS**

`services/pokemon_center.txt`
```
You are an AI using Pokemon Center.

CURRENT STATE: Pokemon Center
LOCATION: {city_name} Pokemon Center
AVAILABLE SERVICES:
- Heal Pokemon (FREE)
- PC Storage (access party box)

TEAM STATUS:
{current_party_status}

DECISION:
1. Approach counter
2. Select healing service
3. Confirm healing
4. Wait for healing animation
5. Exit Pokemon Center

HEALING STRATEGY:
- Heal when any Pokemon HP < 50%
- Fully heal before major battles
- Use free service strategically

DECISION: Should I heal or leave and why?
```

`services/shopping.txt`
```
You are an AI shopping at Pokemon Mart.

CURRENT STATE: Shopping
AVAILABLE FUNDS: ${current_money}

ITEMS FOR SALE:
{item_list_with_prices}

CURRENT INVENTORY:
{current_inventory}

SHOPPING STRATEGY:
1. Essential items: Potions, Antidotes, Pokeballs, Escape Ropes
2. Budget allocation:
   - Healing: {budget_allocation}%
   - Catching: {budget_allocation}%
   - Utility: {budget_allocation}%
3. Priority purchases: {priority_items}

PURCHASE OPTIMIZATION:
- Buy most needed items first
- Maintain 5+ potions in inventory
- Buy pokeballs when encountering rare Pokemon
- Stock Antidotes when in poison-prone areas

DECISION: What items should I buy? Format as shopping list.
```

### **STATE DETECTION PROMPTS**

`vision/screen_analysis.txt`
```
You are an AI vision system analyzing Pokemon game screenshots.

IMAGE: {screenshot_data}

ANALYSIS REQUIRED:
1. Screen Type Classification:
   - TITLE
   - MAIN_MENU
   - DIALOG
   - OVERWORLD
   - BATTLE
   - BATTLE_MENU
   - MENU
   - TRANSITION

2. Battle Detection (if applicable):
   - Enemy Pokemon: {species and level}
   - Player Pokemon: {species and HP}
   - Battle Phase: {start/menu/animation/result/end}

3. Game Element Detection:
   - Text presence: {is_text_visible}
   - Buttons/Icons visible: {list_interactive_elements}
   - Health bars: {hp_values_and_percentages}
   - Menu options: {available_choices}

4. Context Clues:
   - Location indicators: {city/route_markers}
   - Characters on screen: {npc_dialogue}
   - Item pickups visible: {items_in_environment}

RESPONSE FORMAT:
{
  "screen_type": "battles",
  "battle_phase": "menu",
  "enemy_pokemon": "Pidgey",
  "enemy_level": 3,
  "enemy_hp_percentage": 100,
  "player_hp_percentage": 85,
  "available_actions": ["Fight", "Bag", "Pokemon", "Run"],
  "recommended_action": "Fight",
  "confidence": 0.9
}
```

---

## 🚨 ERROR RECOVERY STATEMENTS

### **Unsupported Screenshot Types**

`error/unknown_screen.txt`
```
You are an AI encountering an unexpected Pokemon game state.

CURRENT STATE: Unknown/Error State
VISUAL DESCRIPTION: {screenshot_description}

POSSIBLE ISSUES:
- Corrupted save file
- Glitch/bug in game
- Unusual sequence triggered
- Loading screen between zones

RECOVERY STRATEGY:
1. Take screenshot of unknown state
2. Wait 30-60 ticks to see if state resolves
3. If still unknown: Try pressing B to back out
4. If still stuck: Press random direction
5. Log unknown event for future analysis

DECISION: What recovery action should I attempt?
```

`error/save_corruption.txt`
```
You are an AI handling save file corruption.

SAVE STATUS: {corruption_status}
ERROR: {error_message}

RECOVERY OPTIONS:
- Click "NEW GAME" to start fresh
- User override flag: {user_new_game_flag}

DECISION: How should I proceed with corrupted save?
```

---

## 📊 LOGGING SYSTEM ARCHITECTURE

### **Log File Structure**

```
logs/
├── pokemon_ai_{timestamp}.log    # Main log file
├── decisions_{timestamp}.log      # AI decision log
├── battles_{timestamp}.log       # Battle analytics
├── errors_{timestamp}.log         # Error tracking
└── performance_{timestamp}.log   # Performance metrics
```

### **Log Format Standards**

**Standard Log Entry:**
```
[2025-12-31 01:45:32.123] [INFO] [GAME_LOOP] Tick 0120 - Captured screenshot
[2025-12-31 01:45:32.156] [AI_DECISION] [BATTLE] Selected move: Tackle - Type effectiveness: Neutral
[2025-12-31 01:45:32.189] [EXECUTE] [COMMAND] Button A pressed (duration: 5 ticks)
[2025-12-31 01:45:32.222] [RESULT] [BATTLE] Enemy Rattata took 8 damage (HP: 92% -> 84%)
```

**Log Levels:**
- **DEBUG**: Detailed technical information
- **INFO**: Game state changes, decisions made
- **WARNING**: Unexpected situations, minor errors
- **ERROR**: Failures requiring intervention
- **CRITICAL**: System failures requiring shutdown

---

## 🎯 MEMORY MANAGEMENT COMPRESSION

### **Compression Triggers**

**Automatic Compression:**
1. When context window reaches 80% capacity
2. Every 10 minutes of gameplay
3. Before entering major story event

**Compression Algorithm:**
```python
def compress_memory(memory_data, current_context):
    """
    Compress memory based on current game phase and relevance
    """
    # Identify current phase importance
    phase_importance = get_phase_importance(current_context)
    
    # Keep high-importance data
    kept_data = {
        "badges": memory_data["badges"],
        "key_locations": memory_data["key_locations"],
        "story_progression": memory_data["story_progression"]
    }
    
    # Compress low-importance data
    phase_data = memory_data["recent_encounters"]
    if len(phase_data) > 50:
        # Keep only best 20% encounters
        phase_data = phase_data[:10]
        # Add summary stats
        kept_data["recent_encounters_summary"] = generate_summary(phase_data)
    else:
        kept_data["recent_encounters"] = phase_data
    
    # Add compressed metadata
    kept_data["compression_metadata"] = {
        "original_size": len(json.dumps(memory_data)),
        "compressed_size": len(json.dumps(kept_data)),
        "compression_ratio": calculate_compression_ratio(memory_data, kept_data),
        "compression_timestamp": datetime.now().isoformat()
    }
    
    return kept_data
```

---

## 🔄 COMPLEX STATEMACHINE WORKFLOW

```mermaid
graph TD
    A[Game Boot] --> B{Title Screen}
    B --> C{Main Menu}
    C --> D[Save Exists?]
    
    D -->|Yes| E[Load Save State]
    D -->|No| F[New Game Sequence]
    
    F --> G[Starter Selection]
    E --> H[Resume Gameplay]
    
    G --> H
    H --> I{Current Phase}
    
    I -->|Overworld| J[Navigate]
    I -->|Battle| K{Battle Phase}
    I -->|Dialog| L[Advance Story]
    I -->|Menu| M[Manage Game]
    
    J -->|Random Enc| K
    J -->|City Reached| N[City Services]
    
    K -->|Victory| O{Battle Result}
    K -->|Defeat| P[Healing Required]
    
    O --> I
    P --> N
    
    L --> I
    M --> I
    
    N -->{HP Status}
    N -->|HP>50%| J
    N -->|HP<50%| Q[Pokemon Center]
    
    Q --> J
    
    I -->|Transition| R[Wait/Continue]
    R --> I
```

---

## 🚀 PHASE-BASED PROMPT STRATEGY

**Prompt Selection Logic:**
```python
def select_prompt(game_state, memory):
    """
    Select optimal prompt based on current game phase and context
    """
    # Determine current phase
    phase = determine_game_phase(game_state, memory)
    
    # Get phase-specific prompt
    prompt_map = {
        "game_boot": "boot/title_screen.txt",
        "main_menu": "boot/main_menu.txt",
        "starter_selection": "gameplay/starter_selection.txt",
        "new_game_intro": "story/intro_dialogue.txt",
        "overworld": "navigation/path_planning.txt",
        "battle_start": "battle/wild_encounter_start.txt",
        "battle_menu": "battle/move_selection.txt",
        "battle_animation": None,  # Passive wait
        "battle_end": None,  # Automatic progression
        "dialog": "story/intro_dialogue.txt",
        "pokemon_center": "services/pokemon_center.txt",
        "shopping": "services/shopping.txt",
        "menu": "menu/navigation.txt",
        "transition": "error/unknown_screen.txt"
    }
    
    return prompt_map.get(phase, "vision/screen_analysis.txt")
```

---

## 🎯 NEXT STEPS FOR IMPLEMENTATION

1. **Create Prompt Library**: Fill prompts/ directory with above templates
2. **Implement Logging System**: Create logs/ directory and file writing logic  
3. **Build State Machine**: Implement phase detection and prompt routing
4. **Memory Compression**: Implement the compression algorithm
5. **Error Recovery**: Add proper error handling for unsupported states
6. **Save Management**: Implement save validation and corruption handling

This comprehensive analysis provides the foundation for building a sophisticated AI Pokemon player that truly understands every phase of the game.