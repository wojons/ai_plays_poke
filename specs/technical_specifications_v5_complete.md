# COMPREHENSIVE SYSTEM SPECIFICATION: AI Plays Pokemon

## 🎯 EXECUTIVE SUMMARY

**Project Status**: Real AI API integration working, but system lacks comprehensive phase handling, logging infrastructure, and memory management.

**Critical Gaps**:
1. Only 5 basic prompts vs 50+ required game phases
2. No file-based logging system (only stdout)
3. No save file validation or corruption handling
4. No memory compression system
5. Limited error recovery
6. No transition state handling

**Success Criteria**: Build production-ready system with complete phase coverage, robust logging, and intelligent memory management.

---

## 🎮 COMPLETE GAME WORKFLOW ANALYSIS

### **WORKFLOW 1: EMULATOR BOOT & INITIALIZATION**

```
Emulator Start → ROM Load → PyBoy Init → Save File Detection → Game State Check
     ↓                                                                              ↓
   [PyBoy API]                                                              [Save Validation]
     ↓                                                                              ↓
Screen Capture → State Analysis → Phase Detection → Prompt Selection → AI Decision
```

**Boot Sequence States**:
1. **pyboy_loading** - Emulator initializing (0-30 ticks)
2. **game_freak_logo** - Logo animation (30-60 ticks)
3. **title_screen** - "PRESS START" visible (60-90 ticks)
4. **menu_screen** - Main menu options (90-120 ticks)
5. **save_check** - Validate save file existence (120-150 ticks)

**Save File States**:
- **save_valid** - Save file exists and is loadable
- **save_corrupted** - Save file exists but corrupted
- **save_missing** - No save file found
- **save_incompatible** - Wrong game version

**Decision Tree**:
```
Save Check
  ├── Valid Save → Load Save → Continue Game
  ├── Corrupted Save → Check Flag → New Game (if flag set) or Error
  ├── Missing Save → New Game Sequence
  └── Incompatible → Error with message
```

---

### **WORKFLOW 2: NEW GAME SEQUENCE**

```
New Game Selected → Story Intro → Starter Selection → Rival Battle → Tutorial Items
     ↓                  ↓              ↓              ↓              ↓
[Dialog Phase]  [Choice Phase] [Battle Phase] [Reward Phase] [Ready Phase]
```

**New Game Phases**:
1. **oak_intro** - Professor Oak dialogue (150-250 ticks)
2. **starter_selection** - Choose Bulbasaur/Charmander/Squirtle (250-350 ticks)
3. **starter_summary** - Pokemon summary screen (350-400 ticks)
4. **rival_encounter** - Rival appears for battle (400-450 ticks)
5. **tutorial_items** - Receive Pokedex, Pokeballs (450-550 ticks)
6. **mom_goodbye** - Dialogue with mom (550-600 ticks)
7. **pallet_town_start** - Standing outside house (600-650 ticks)

**Critical Decision Points**:
- **Starter Selection**: Must choose based on gym strategy
- **Rival Battle**: First combat test of AI
- **Item Collection**: Verify Pokedex and Pokeballs received

---

### **WORKFLOW 3: OVERWORLD EXPLORATION**

```
Overworld Screen → Movement → Encounter Check → Random Battle? → Continue
     ↓              ↓           ↓              ↓
[Path Planning] [Movement] [RNG Check] [Yes→Battle Flow]
```

**Overworld Sub-States**:
1. **navigating** - Normal movement (most common)
2. **grass_encounter_check** - Every step in tall grass
3. **cave_encounter_check** - Every step in caves
4. **city_walking** - Walking in city (no encounters)
5. **route_transition** - Moving between routes
6. **warp_animation** - Using door/ladder (transition)

**Encounter Probability**:
- Tall grass: ~15% per step
- Caves: ~10% per step
- Water (Surf): ~5% per step
- Cities: 0%

---

### **WORKFLOW 4: BATTLE SYSTEM**

```
Battle Start → Pokemon Display → Battle Menu → Move Selection → Attack
     ↓              ↓              ↓              ↓              ↓
[Enemy ID]  [Animation]  [Option Display] [Choose Move] [Damage Calc]
     ↓              ↓              ↓              ↓              ↓
Animation → Result Display → Continue? → Battle Menu → Repeat
```

**Battle Phases**:
1. **battle_entry** - Transition animation into battle (10 ticks)
2. **pokemon_sent_out** - Pokemon appears with cry (20 ticks)
3. **battle_menu_display** - "Fight/Bag/Pokemon/Run" menu (30 ticks)
4. **move_selection** - Choose specific move (40-60 ticks)
5. **attack_animation** - Move execution animation (60-100 ticks)
6. **damage_display** - "It's super effective!" text (100-120 ticks)
7. **hp_bar_animation** - HP bar drops (120-150 ticks)
8. **result_check** - Fainted? Continue? (150-160 ticks)
9. **experience_gain** - EXP bar fill animation if victory (160-200 ticks)
10. **battle_exit** - Return to overworld (200-250 ticks)

**Critical Timing**:
- **Menu navigation**: Must wait for menu to fully render
- **Animation timing**: Pressing buttons during animations can skip
- **Text advancement**: Most text requires A button press
- **State transitions**: Must detect when animation ends

---

### **WORKFLOW 5: CITY SERVICES**

```
Enter City → Pokemon Center → Healing → Shopping → Exit City
     ↓              ↓         ↓         ↓
[Building Entry] [Dialogue] [Animation] [Menu Navigation]
```

**City Service States**:
1. **pokemon_center_entry** - Walking into center (10 ticks)
2. **nurse_joy_dialog** - "Welcome to Pokemon Center!" (20-30 ticks)
3. **healing_animation** - Pokemon restoration animation (40-60 ticks)
4. **healing_complete** - "Your Pokemon are fully healed!" (70-80 ticks)
5. **exit_center** - Leave building (90-100 ticks)
6. **mart_entry** - Enter Pokemon Mart (110-120 ticks)
7. **mart_menu** - Shop interface (130-180 ticks)
8. **purchase_menu** - Item selection (190-240 ticks)
9. **purchase_complete** - "Thank you!" dialog (250-280 ticks)
10. **exit_mart** - Leave shop (290-300 ticks)

**Service Priorities**:
- **Healing**: When any Pokemon HP < 50%
- **Shopping**: When potions < 3, or specific items needed
- **PC Access**: When party full and need to deposit

---

### **WORKFLOW 6: STATE TRANSITIONS**

**Transition Types**:
1. **screen_fade** - Black screen between areas (30-60 ticks)
2. **loading_animation** - "Now loading..." type screens (20-40 ticks)
3. **door_animation** - Entering/exiting buildings (15-25 ticks)
4. **warp_effect** - Using teleporters/pads (10-20 ticks)
5. **cutscene_transition** - Story sequence transitions (50-100 ticks)

**Transition Detection**:
- Screen goes black or mostly black
- No interactive elements visible
- Previous state no longer valid
- Must wait for transition to complete before acting

---

## 📋 COMPLETE PROMPT LIBRARY (50+ TEMPLATES)

### **BOOT SEQUENCE PROMPTS (8)**

**prompts/boot/title_screen.txt**
```
CURRENT STATE: Title Screen
VISUAL: Game Freak logo, "PRESS START" text
AUDIO: Pokemon theme music
AVAILABLE: START button only
ACTION: Press START to enter main menu
```

**prompts/boot/main_menu.txt**
```
CURRENT STATE: Main Menu
OPTIONS: New Game, Options, Continue
SAVE_STATUS: {save_status}
DECISION: Continue (if valid save) → Load Game
         Options → Configure settings
         New Game → Fresh start
```

**prompts/boot/save_check.txt**
```
CURRENT STATE: Save File Validation
SAVE_FILE: {save_path}
STATUS: {valid|corrupted|missing}
ACTION: Load (valid) | New Game (missing/corrupted)
ERROR_HANDLING: If corrupted and flag not set → ERROR
```

**prompts/boot/options_menu.txt**
```
CURRENT STATE: Options Configuration
SETTINGS: Text Speed, Battle Style, Sound
OPTIMAL: Text Speed=FAST, Battle Style=SET, Sound=MONO
ACTION: Configure all settings for AI efficiency
```

**prompts/boot/loading_save.txt**
```
CURRENT STATE: Loading Save File
PROGRESS: {badges}, {playtime}, {location}
VALIDATION: Checksum verified
ACTION: Wait for load completion → Verify game state
```

**prompts/boot/save_corrupted.txt**
```
CURRENT STATE: Save File Corruption Detected
ERROR: {corruption_details}
OPTIONS: New Game (if --new-game-on-corruption flag)
         Exit with error (default)
USER_ACTION: Check logs for corruption details
```

**prompts/boot/new_game_confirm.txt**
```
CURRENT STATE: New Game Confirmation
WARNING: All progress will be lost
CONFIRMATION: {user_override} flag set
ACTION: Start new game sequence
```

**prompts/boot/emulator_error.txt**
```
CURRENT STATE: Emulator Initialization Failed
ERROR: {error_message}
ROM: {rom_path}
CHECK: File exists, format .gb/.gbc, valid ROM
ACTION: Exit with detailed error message
```

---

### **NEW GAME PROMPTS (12)**

**prompts/new_game/oak_intro.txt**
```
CURRENT STATE: Professor Oak Introduction
DIALOGUE: "Welcome to the world of Pokemon!"
ACTION: Press A repeatedly to advance text
TIMING: Wait for text box, press A, wait for next text
OBJECTIVE: Reach starter selection screen
```

**prompts/new_game/starter_selection.txt**
```
CURRENT STATE: Starter Pokemon Selection
CHOICES: Bulbasaur (Grass), Charmander (Fire), Squirtle (Water)
STRATEGY: First gym is Rock type (Brock in Pewter City)
ANALYSIS: Bulbasaur > Squirtle > Charmander for early game
OPTIMAL: Bulbasaur (super-effective against Rock)
ACTION: Navigate to Bulbasaur, press A to select
```

**prompts/new_game/starter_summary.txt**
```
CURRENT STATE: Starter Pokemon Summary
SHOWING: {starter_name} stats, moves, ability
ACTION: Review stats briefly, press A to continue
MEMORY: Record starter Pokemon in team history
```

**prompts/new_game/rival_appears.txt**
```
CURRENT STATE: Rival Encounter
RIVAL: {rival_name} appears
DIALOGUE: "I'll take the Pokemon that's strong against yours!"
ACTION: Note rival's Pokemon selection
PREDICTION: Rival will choose counter to your starter
```

**prompts/new_game/first_battle_prep.txt**
```
CURRENT STATE: First Battle Preparation
ENEMY: Rival with counter starter
PLAYER: Starter at level 5
ANALYSIS: Equal match, type disadvantage for rival
STRATEGY: Use type-effective moves, conserve PP
ACTION: Prepare for battle sequence
```

**prompts/new_game/tutorial_items.txt**
```
CURRENT STATE: Receive Tutorial Items
ITEMS: Pokedex, 5 Pokeballs
ACTION: Accept all items (mission critical)
MEMORY_UPDATE: Inventory [Pokedex:1, Pokeballs:5]
```

**prompts/new_game/mom_dialogue.txt**
```
CURRENT STATE: Mom's Goodbye Advice
DIALOGUE: "Be careful on your journey!"
LOCATION_INFO: Route 1 leads to Viridian City
ACTION: Advance dialogue, prepare for Route 1
```

**prompts/new_game/standing_in_pallet.txt**
```
CURRENT STATE: Outside Mom's House in Pallet Town
LOCATION: Pallet Town, Kanto Region
OBJECTIVE: Travel to Viridian City via Route 1
PREPARATION: Heal if needed, check inventory
ACTION: Start walking toward Route 1 (north)
```

**prompts/new_game/route1_entry.txt**
```
CURRENT STATE: Entering Route 1
TERRAIN: Tall grass patches, wild Pokemon area
ENCOUNTER_RATE: ~15% per step in grass
TEAM_STATUS: Starter at level 5-6
STRATEGY: Walk on path to minimize encounters
         Grind if underleveled
ACTION: Navigate through Route 1 to Viridian City
```

**prompts/new_game/first_wild_encounter.txt**
```
CURRENT STATE: First Wild Pokemon Encounter
ENEMY: {pokemon_name} Lv.{level}
EXPERIENCE: First time battling wild Pokemon
STRATEGY: Learn enemy patterns, gain EXP
ACTION: Engage battle or run based on strategy
```

**prompts/new_game/viridian_city_arrival.txt**
```
CURRENT STATE: Arrived at Viridian City
LOCATION: First city with Pokemon services
FACILITIES: Pokemon Center, Pokemon Mart, Gym
ACTION: Heal at Pokemon Center first
PLANNING: Shop for supplies, prepare for Viridian Forest
```

**prompts/new_game/level_up_first.txt**
```
CURRENT STATE: Pokemon Leveled Up
POKEMON: {pokemon_name} reached Lv.{level}
UPDATES: New move learned: {move_name}
ACTION: Review new move, decide to learn/replace
STRATEGY: Keep type-effective moves, replace weak moves
```

---

### **OVERWORLD PROMPTS (8)**

**prompts/overworld/path_planning.txt**
```
CURRENT STATE: Overworld Navigation
LOCATION: {current_location}
DESTINATION: {target_location}
KNOWN_ROUTES: {available_paths}
ENCOUNTER_DATA: {encounter_rates_by_terrain}

PATH_STRATEGY:
1. Shortest distance to destination
2. Minimize grass/cave walking (reduce encounters)
3. Known item locations along route
4. Pokemon Center proximity for healing

CURRENT_STATUS:
- Team HP: {team_hp_summary}
- Potions: {potion_count}
- Last heal: {ticks_since_last_heal}

ACTION: Choose direction (UP/DOWN/LEFT/RIGHT) with reasoning
```

**prompts/overworld/grass_walking.txt**
```
CURRENT STATE: Walking in Tall Grass
ENCOUNTER_RATE: 15% per step
AWARENESS: High encounter risk
READINESS: {team_hp_status}
ITEMS: {escape_rope_count}, {potion_count}

DECISION_RULES:
- If HP < 50%: Exit grass immediately
- If no potions: Avoid grass if possible
- If hunting: Stay in grass for encounters
- If rushing: Run from most encounters

ACTION: Continue walking, prepare for encounter
```

**prompts/overworld/cave_navigation.txt**
```
CURRENT STATE: Cave Navigation
LIGHT_STATUS: Flash needed for some caves
ENCOUNTERS: Rock/Ground types common
ESCAPE_OPTIONS: {escape_rope_available}

CAVE_STRATEGY:
1. Use Flash if available (improved visibility)
2. Watch for Rock-type encounters
3. Save Escape Ropes for emergencies
4. Explore thoroughly for items

ACTION: Navigate carefully, check for items
```

**prompts/overworld/surfing.txt**
```
CURRENT STATE: Surfing on Water
WATER_ENCOUNTERS: Water Pokemon common
AVAILABLE_MOVES: Surf speed and direction

STRATEGY:
- Water Pokemon often good additions to team
- Surf to access hidden areas
- Watch for rare Water Pokemon

ACTION: Surf toward destination, watch for encounters
```

**prompts/overworld/bike_riding.txt**
```
CURRENT STATE: Bicycle Active
SPEED: 2x normal walking speed
ENCOUNTER_RATE: Same as walking
BENEFIT: Faster travel, same encounter risk

USAGE:
- Long distance travel
- Backtracking through explored areas
- Speedrunning objectives

ACTION: Continue to destination at high speed
```

**prompts/overworld/cut_scene.txt**
```
CURRENT STATE: Cutscene Active
VISUAL: Story sequence playing
CONTROL: Limited or no player control
ACTION: Wait for cutscene to complete
POST_SCENE: Note any important information revealed
```

**prompts/overworld/npc_interaction.txt**
```
CURRENT STATE: NPC Interaction
NPC_TYPE: {trainer|citizen|gym_leader|story_character}
DIALOGUE: {dialogue_content}

ANALYSIS:
- Trainers: Battle challenge imminent
- Citizens: Hints, item gifts, or flavor text
- Gym Leaders: Must defeat for badge
- Story: Progress narrative, receive items

ACTION: Advance dialogue, prepare for battle if trainer
MEMORY: Record important information from dialogue
```

**prompts/overworld/item_pickup.txt**
```
CURRENT STATE: Item on Ground
ITEM: {item_name} at {location}
VALUE: {item_rarity_and_usefulness}

PRIORITY_SYSTEM:
- High: Rare Candy, Master Ball, TMs
- Medium: Potions, Pokeballs, Rare items
- Low: Antidote (if already have many)

ACTION: Pick up item (press A)
INVENTORY_UPDATE: Add item to inventory count
```

---

### **BATTLE SYSTEM PROMPTS (15+)**

**prompts/battle/wild_encounter_start.txt**
```
CURRENT STATE: Wild Encounter
ENEMY: {pokemon_name} Lv.{level} ({types})
APPEARANCE: {sprite_details}
HP_BAR: {enemy_hp_percentage}%

PLAYER_POKEMON: {player_name} Lv.{level} ({types})
PLAYER_HP: {player_hp_percentage}%
AVAILABLE_MOVES: {move_list_with_types}

BATTLE_ANALYSIS:
- Type effectiveness: {matchup_analysis}
- Win probability: {estimated_chance}
- EXP reward: {exp_value}
- Catch difficulty: {catch_rate}

STRATEGIC_OPTIONS:
1. FIGHT - Engage battle
2. RUN - Flee (success rate: {run_success_rate})
3. BAG - Use item (Potion, Pokeball, etc)
4. POKEMON - Switch (if available)

DECISION: Choose action with confidence and reasoning
```

**prompts/battle/trainer_battle_start.txt**
```
CURRENT STATE: Trainer Battle
TRAINER_TYPE: {bug_catcher|youngster|hiker|gym_leader}
TRAINER_NAME: {name}
ENEMY_POKEMON: {first_pokemon_name} Lv.{level}

TRAINER_PATTERNS:
- Known for: {common_pokemon_types}
- Difficulty: {estimated_difficulty}
- Cannot run from trainer battles

STRATEGY:
- Must defeat all trainer Pokemon
- Cannot escape
- Gain money and EXP
- Plan for multiple Pokemon

ACTION: Prepare for battle, select first move
```

**prompts/battle/battle_menu_display.txt**
```
CURRENT STATE: Battle Menu
OPTIONS:
- FIGHT: Select move
- BAG: Use item
- RUN: Attempt escape (wild only)
- POKEMON: Switch Pokemon

CURRENT_SITUATION:
- Enemy HP: {enemy_hp_percentage}%
- Player HP: {player_hp_percentage}%
- Last action: {previous_action}

ANALYSIS:
- If enemy low HP: Use strong move to finish
- If player low HP: Consider healing or switching
- If need EXP: Use type-effective moves
- If wild battle unnecessary: Consider running

ACTION: Select menu option
```

**prompts/battle/move_selection_menu.txt**
```
CURRENT STATE: Move Selection Menu
AVAILABLE_MOVES:
{move1}: Type {type1}, Power {power1}, PP {pp1}/{max_pp1}
{move2}: Type {type2}, Power {power2}, PP {pp2}/{max_pp2}
{move3}: Type {type3}, Power {power3}, PP {pp3}/{max_pp3}
{move4}: Type {type4}, Power {power4}, PP {pp4}/{max_pp4}

MOVE_ANALYSIS:
- Type effectiveness: {effectiveness_matrix}
- STAB bonus: {stab_moves}
- PP remaining: {pp_status}
- Critical hit chance: {crit_rates}

OPTIMIZATION:
- Maximize damage: {highest_damage_move}
- Conserve PP: {best_pp_efficiency}
- Type coverage: {type_advantage_moves}

STRATEGY: {current_battle_strategy}

ACTION: Select optimal move
```

**prompts/battle/attack_animation.txt**
```
CURRENT STATE: Attack Animation
ANIMATION_TYPE: {move_animation}
DURATION: ~40-60 ticks

OBSERVATION:
- Visual effects showing move type
- Pokemon sprites animating
- No player input accepted during animation

ACTION: WAIT for animation to complete
DETECTION: Animation ends when HP bar animation starts
```

**prompts/battle/damage_calculation_display.txt**
```
CURRENT STATE: Damage Display
TEXT_SHOWN: {effectiveness_text}
EFFECTIVENESS: {not_very|normal|super_effective}

INTERPRETATION:
- "It's not very effective..." → 0.5x damage
- Normal text → 1x damage
- "It's super effective!" → 2x damage

MEMORY_UPDATE:
- Log type effectiveness for this enemy
- Update matchup knowledge base

ACTION: Wait for HP bar animation
```

**prompts/battle/hp_bar_animation.txt**
```
CURRENT STATE: HP Bar Animation
ANIMATION: HP bar decreasing smoothly
START_HP: {start_percentage}%
END_HP: {end_percentage}%
CHANGE: {damage_dealt} damage

HP_BAR_COLORS:
- Green: >50% HP
- Yellow: 20-50% HP
- Red: <20% HP (danger)

ASSESSMENT:
- If enemy HP critical: Prepare for KO
- If player HP critical: Consider healing or switch
- If enemy HP low: Use finishing move

ACTION: Wait for animation completion
```

**prompts/battle/pokemon_fainted.txt**
```
CURRENT STATE: Pokemon Fainted
FAINTED_TYPE: {player|enemy}_pokemon_fainted

IF_ENEMY_FAINTED:
- Victory if last enemy Pokemon
- Next enemy Pokemon appears if trainer battle
- Exp gain animation incoming

IF_PLAYER_FAINTED:
- Switch to next Pokemon if available
- Black out if last Pokemon (return to Pokemon Center)
- Need healing urgently

ACTION: Wait for faint animation and next sequence
```

**prompts/battle/experience_gain.txt**
```
CURRENT STATE: Experience Gain
POKEMON: {pokemon_name} gained EXP
AMOUNT: {exp_gained} EXP
LEVEL_PROGRESS: {current_exp}/{exp_to_next}

ANIMATION: EXP bar filling
LEVEL_UP: {will_level_up}

IF_LEVEL_UP:
- New level: {new_level}
- STAT_INCREASES: {hp, atk, def, spd, spatk, spdef}
- NEW_MOVE: {move_learned}

DECISION: Learn new move? Which move to replace?
MEMORY: Update Pokemon stats and level

ACTION: Continue through level up sequence
```

**prompts/battle/level_up_move.txt**
```
CURRENT STATE: Level Up Move Learning
POKEMON: {pokemon_name} reached Lv.{level}
NEW_MOVE: {move_name} (Type: {type}, Power: {power})

CURRENT_MOVES:
{current_move_list_with_details}

MOVE_ANALYSIS:
- New move power: {power}
- Type effectiveness: {coverage}
- PP: {pp}
- Accuracy: {accuracy}

REPLACEMENT_STRATEGY:
- Drop weakest move (lowest power)
- Maintain type coverage
- Keep STAB moves when possible
- Preserve status moves if useful

ACTION: Choose move to replace or decline learning
```

**prompts/battle/victory_screen.txt**
```
CURRENT STATE: Battle Victory
VICTORY_TYPE: {wild|trainer}_victory
REWARDS:
- EXP: {exp_gained}
- Money: ${money_gained} (trainer only)
- Items: {items_dropped}

POST_BATTLE_STATUS:
- Player HP: {team_hp_summary}
- PP used: {pp_consumed}
- Items used: {items_consumed}

NEXT_ACTIONS:
1. Check team HP status
2. Use healing items if needed
3. Continue to destination
4. Heal at Pokemon Center if critical

ACTION: Plan next moves based on post-battle status
MEMORY: Log battle outcome, update win rate
```

**prompts/battle/defeat_screen.txt**
```
CURRENT STATE: Battle Defeat
DEFEAT_TYPE: {all_pokemon_fainted|critical_hp}
CONSEQUENCE: Black out → Return to Pokemon Center

LOSS_ANALYSIS:
- Enemy too strong: {level_difference}
- Type disadvantage: {bad_matchup}
- Resource exhaustion: {no_items_pp}
- Strategic error: {mistake_analysis}

RECOVERY_PLAN:
- Heal all Pokemon at nearest center
- Rethink strategy for this enemy type
- Level up before re-attempt
- Consider catching different Pokemon

MEMORY: Log failure, update strategy knowledge
ACTION: Accept defeat, heal, replan
```

**prompts/battle/catching_phase.txt**
```
CURRENT STATE: Attempting to Catch Pokemon
TARGET: {pokemon_name} Lv.{level} ({types})
HP: {current_hp_percentage}% (lower = easier catch)
STATUS: {status_condition} (burn/sleep/paralyze = easier)

CATCH_RATE_BASE: {base_catch_rate}
POKEBALL_TYPE: {pokeball|greatball|ultraball}

SUCCESS_ESTIMATE: {catch_probability}

STRATEGY:
- Weaken to <20% HP (don't KO)
- Apply status condition if possible
- Use appropriate ball type
- Consider rarity (legendary = use best ball)

ACTION: Use Pokeball from bag menu
MEMORY: Log catch attempt, success rate
```

**prompts/battle/run_attempt.txt**
```
CURRENT STATE: Attempting to Run
ESCAPE_ATTEMPT: Current speed comparison
ENEMY_SPEED: {enemy_speed}
PLAYER_SPEED: {player_speed}

SUCCESS_RATE: {escape_probability}

IF_SUCCESS: Return to overworld
IF_FAIL: Enemy gets free attack
BACKUP_PLAN: If fail repeatedly, consider fighting

ACTION: Select RUN from battle menu
NOTE: Cannot run from trainer battles
```

**prompts/battle/switch_pokemon.txt**
```
CURRENT STATE: Switching Pokemon
CURRENT_POKEMON: {current_name} (HP: {hp}%)
AVAILABLE_SWITCHES: {other_pokemon_list}

SWITCH_REASON:
- Type advantage needed: {better_matchup}
- Current Pokemon low HP: {risk_of_faint}
- Strategic counter: {counter_enemy_type}
- EXP distribution: {balance_levels}

SWITCH_COST: Enemy gets free attack turn

SWITCH_TARGET: {recommended_pokemon} (reason: {explanation})

ACTION: Select POKEMON from battle menu, choose switch target
```

**prompts/battle/trainer_multiple_pokemon.txt**
```
CURRENT STATE: Trainer Battle - Multiple Pokemon
TRAINER: {trainer_type} {trainer_name}
CURRENT_ENEMY: {current_pokemon} (HP: {hp}%)
REMAINING_ENEMIES: {remaining_count} more Pokemon

STRATEGY_ADJUSTMENT:
- Conserve PP across all battles
- Preserve HP for multiple fights
- Don't use best moves on weak first Pokemon
- Plan for type variety in trainer's team

RESOURCE_MANAGEMENT:
- PP remaining: {pp_status_all_moves}
- Item usage: {potion_priority}
- Pokemon health: {team_status_summary}

ACTION: Select moves balancing current fight and future fights
```

**prompts/battle/status_condition_active.txt**
```
CURRENT STATE: Status Condition Active
AFFECTED_POKEMON: {pokemon_name}
CONDITION: {burn|poison|paralyze|sleep|freeze|confusion}
EFFECT: {condition_effect_description}

DAMAGE_PER_TURN:
- Burn: -1/16 max HP per turn
- Poison: -1/8 max HP per turn
- Badly Poisoned: Increases each turn

IMMEDIATE_ACTION:
- Use Antidote for poison
- Use Burn Heal for burn
- Use Paralyze Heal for paralysis
- Wait out sleep (2-5 turns usually)
- Switch for confusion/freeze

ITEM_INVENTORY: {healing_item_count}

DECISION: Use healing item or switch Pokemon?
```

---

### **CITY SERVICE PROMPTS (8)**

**prompts/services/pokemon_center_entry.txt**
```
CURRENT STATE: Entering Pokemon Center
BUILDING_TYPE: Healing facility, free service
LOCATION: {city_name} Pokemon Center
VISUAL: Counter with Nurse Joy

HEALING_PRIORITY:
- If any Pokemon HP < 50%: HIGH PRIORITY
- If team fully healed: LOW PRIORITY
- Before gym challenge: MANDATORY

ACTION: Approach counter, press A to talk to Nurse Joy
```

**prompts/services/nurse_joy_dialogue.txt**
```
CURRENT STATE: Nurse Joy Dialogue
WELCOME_TEXT: "Welcome to the Pokemon Center!"
OPTIONS: Heal Pokemon, Use PC, Exit

HEALING_COST: FREE
HEALING_TIME: 2-3 seconds animation

ACTION: Select "Heal Pokemon" option
LOGIC: Free healing is always beneficial
```

**prompts/services/healing_animation.txt**
```
CURRENT STATE: Healing Animation
VISUAL: Pokemon balls on healing machine
ANIMATION_DURATION: ~60 ticks

OBSERVED: Pokemon being healed one by one
RESULT: All Pokemon restored to full HP/PP

ACTION: Wait for animation to complete
DETECTION: "Your Pokemon are fully healed!" text appears
```

**prompts/services/healing_complete.txt**
```
CURRENT STATE: Healing Complete
RESULT: All Pokemon restored to full HP/PP
POST_HEALING_STATUS:
  - HP: All Pokemon at 100%
  - PP: All moves at max PP
  - Status: All conditions healed

BENEFIT: Free full team recovery
COST: ~5 seconds of real time

ACTION: Exit Pokemon Center, continue journey
```

**prompts/services/pc_storage_access.txt**
```
CURRENT STATE: PC Storage Access
PURPOSE: Deposit/withdraw Pokemon from storage
BOX_SYSTEM: {current_box_number} - {pokemon_count} Pokemon stored

USE_CASES:
- Party full, caught new Pokemon → Deposit one
- Need different type for gym → Withdraw counter
- Level grinding → Deposit high levels

CURRENT_PARTY: {party_summary}
STORAGE_POKEMON: {storage_summary}

ACTION: Access PC if party management needed
```

**prompts/services/pokemon_mart_entry.txt**
```
CURRENT STATE: Entering Pokemon Mart
STORE_TYPE: Item shop
LOCATION: {city_name} Pokemon Mart
CLERK: Shopkeeper at counter

AVAILABLE_FUNDS: ${current_money}
SHOPPING_PRIORITIES:
1. Potion (300) if <5 in inventory
2. Antidote (100) if <3 in inventory
3. Pokeball (200) if <10 in inventory
4. Escape Rope (550) if none in inventory
5. Repel (350) if planning cave/grass traversal

ACTION: Approach counter, press A to shop
```

**prompts/services/mart_menu_navigation.txt**
```
CURRENT STATE: Mart Menu
CATEGORY: {healing|pokeballs|battle_items|vitamins}
INVENTORY_BEFORE: {current_item_counts}

ITEM_ANALYSIS:
- Potion: Heals 20 HP, essential
- Antidote: Cures poison, situational
- Pokeball: Catch Pokemon, always useful
- Escape Rope: Flee caves, emergency use
- Repel: Avoid encounters, strategic use

SHOPPING_BUDGET: {spending_limit}
PRIORITY_ORDER: {item_priority_based_on_need}

ACTION: Navigate to needed item category
```

**prompts/services/purchase_confirmation.txt**
```
CURRENT STATE: Purchase Confirmation
ITEM: {item_name}
PRICE: ${item_price}
CURRENT_MONEY: ${current_money}
AFTER_PURCHASE: ${remaining_money}

AFFORDABLE: {yes|no}
NEED_LEVEL: {critical|high|medium|low}

PURCHASE_DECISION:
- Critical need + affordable → BUY
- High need + affordable → BUY
- Medium need + affordable → CONSIDER
- Low need OR not affordable → SKIP

ACTION: Confirm purchase (A) or cancel (B)
MEMORY: Update inventory count after purchase
```

---

### **DIALOGUE PROMPTS (5)**

**prompts/dialogue/story_progression.txt**
```
CURRENT STATE: Story Dialogue
CHARACTER: {character_name}
DIALOGUE: {dialogue_text}

STORY_IMPORTANCE: {critical_important_flavor}
INFORMATION_GAINED: {key_story_details}

IF_CRITICAL:
- Note important locations mentioned
- Record character objectives
- Remember item locations
- Note future objectives

ACTION: Press A to advance text
MEMORY: Record important story information
```

**prompts/dialogue/npc_helpful.txt**
```
CURRENT STATE: Helpful NPC Dialogue
NPC_TYPE: Citizen, researcher, gym guide
INFORMATION: {helpful_hints}

TYPICAL_INFO:
- "The Gym Leader uses Rock-type Pokemon"
- "The item is hidden in the northeast corner"
- "You'll need CUT to get through this forest"

MEMORY_PRIORITY: HIGH - Affects strategy
ACTION: Pay attention, record hints
FOLLOW_UP: May need to return to this NPC later
```

**prompts/dialogue/npc_challenge.txt**
```
CURRENT STATE: Trainer Challenge
TRAINER_TYPE: {bug_catcher|camper|fisher|other}
CHALLENGE_TEXT: "I challenge you to a battle!"

LOCK_IN: Cannot avoid trainer battle
PREPARATION: Last chance to check team HP
ACTION: Accept challenge (automatic)
TRANSITION: Battle start in 20-30 ticks
```

**prompts/dialogue/hint_recording.txt**
```
CURRENT STATE: Receiving Hint or Secret
HINT_CATEGORY: {location|item|strategy}
HINT_CONTENT: {hint_text}

VERIFICATION:
- Location hint: Check map
- Item hint: Search specified area
- Strategy hint: Apply to future battles

MEMORY_UPDATE:
{
  "hints_received": {
    "location": "CERULEAN_CAVE",
    "item": "MASTER_BALL",
    "strategy": "USE_ICE_ON_DRAGONITE"
  }
}

ACTION: Record hint for future use
```

**prompts/dialogue/story_cutscene.txt**
```
CURRENT STATE: Story Cutscene
CUTSCENE_TYPE: {legendary_encounter|gym_announcement|team_rocket}

CONTROL: Limited input, mostly passive
OBSERVATION: Watch for important information
PATIENCE: Cutscenes can last 100-500 ticks

ACTION: Advance text when prompted, otherwise wait
MEMORY: Note story progression, legendary sightings
```

---

### **MENU SYSTEM PROMPTS (6)**

**prompts/menu/pause_menu.txt**
```
CURRENT STATE: Pause Menu
OPTIONS:
- POKEMON: View party
- BAG: Inventory management
- SAVE: Save game
- OPTION: Settings
- EXIT: Close menu

PURPOSE: Current need
- Check team status → POKEMON
- Use item → BAG
- Save progress → SAVE
- Change settings → OPTION

ACTION: Select appropriate menu option
```

**prompts/menu/pokemon_party.txt**
```
CURRENT STATE: Pokemon Party View
PARTY_LIST:
{detailed_party_info_with_hp_pp_moves}

ANALYSIS:
- HP status: {hp_percentage_each}
- PP remaining: {pp_all_moves}
- Status conditions: {burn_poison_sleep_etc}
- Level distribution: {balance_summary}

NEEDS_ASSESSMENT:
- Healing needed: {which_pokemon}
- PP restoration: {moves_low_pp}
- Status healing: {conditions_to_cure}

POST_VIEW_ACTION: Use items or plan healing
```

**prompts/menu/bag_inventory.txt**
```
CURRENT STATE: Bag Inventory
CATEGORY: {healing|pokeballs|tms|battle_items|berries}

ITEM_COUNTS:
Potion: {count}
Antidote: {count}
Pokeball: {count}
Escape Rope: {count}
{other_items}

USAGE_ANALYSIS:
- Healing items: {sufficiency_for_current_hp_needs}
- Pokeballs: {adequacy_for_catching_plans}
- Utility items: {emergency_readiness}

SHOPPING_NEEDS: {items_to_buy_next_mart}
ACTION: Select item to use, or note shortages
```

**prompts/menu/save_game.txt**
```
CURRENT STATE: Save Game Confirmation
CONFIRMATION_TEXT: "There is already a save file. OK to overwrite?"

SAVE_FREQUENCY:
- Before major battles: ALWAYS
- After rare catches: ALWAYS
- After gym badges: ALWAYS
- Every 15-30 minutes: RECOMMENDED

SAVE_LOCATION: {save_slot}
BACKUP: Consider multiple saves for safety

ACTION: Confirm save (A) or cancel (B)
POST_SAVE: Verify save successful, log in database
```

**prompts/menu/option_settings.txt**
```
CURRENT STATE: Options Menu
CURRENT_SETTINGS:
- Text Speed: {slow/mid/fast}
- Battle Style: {shift/set}
- Sound: {mono/stereo}

AI_OPTIMAL_SETTINGS:
- Text Speed: FAST (faster gameplay)
- Battle Style: SET (conservative animations)
- Sound: MONO (no audio processing needed)

ANALYSIS: Current settings {match|differ} from optimal
ACTION: Adjust settings if not optimal
```

**prompts/menu/item_use.txt**
```
CURRENT STATE: Item Use Menu
ITEM: {item_name}
TARGET: {which_pokemon}

VALIDATION:
- Item type: {healing/status/battle}
- Target HP: {current_hp}
- Expected effect: {heal_amount_or_effect}

OPTIMIZATION:
- Potion on Pokemon with <50% HP
- Full Restore on Pokemon with <20% HP or status
- Revive on fainted Pokemon
- PP restore on moves with <5 PP

ACTION: Confirm use on target Pokemon
UPDATE: Track item consumption in inventory
```

---

### **TRANSITION STATE PROMPTS (8)**

**prompts/transition/screen_fade_black.txt**
```
CURRENT STATE: Screen Fade to Black
TRANSITION_TYPE: Between areas, loading screen
DURATION: 30-60 ticks

STATE_BEFORE: {previous_screen_type}
EXPECTED_STATE_AFTER: {next_screen_type}

CHARACTERISTICS:
- Screen gradually goes black
- No interactive elements
- Audio may change
- Next area loading

ACTION: WAIT for transition to complete
DETECTION: Screen returns to normal, new area visible
```

**prompts/transition/loading_screen.txt**
```
CURRENT STATE: Loading Screen
LOADING_TYPE: {map_load|battle_entry|menu_open}
DURATION: 20-50 ticks

VISUAL_INDICATORS:
- "Now loading..." text (newer games)
- Black screen with audio continuing
- Screen flicker or flash
- Brief pause in gameplay

ACTION: WAIT without input
RUSHING: Do not press buttons during loading
```

**prompts/transition/door_animation.txt**
```
CURRENT STATE: Door Animation
ANIMATION_TYPE: {entering|exiting} building
DURATION: 15-25 ticks

VISUAL: Character sprite disappears, door opens/closes
LOCATION_CHANGE: {building_name}
ENVIRONMENT_CHANGE: {indoor|outdoor}

ACTION: WAIT for animation completion
NEXT: Screen fades in to new location
```

**prompts/transition/warp_pad.txt**
```
CURRENT STATE: Warp Pad/Portal Animation
EFFECT_TYPE: {teleport|warp_pad|portal}
DURATION: 10-20 ticks

VISUAL: Character flashes and disappears
DESTINATION: {target_location}
DISTANCE: Can be cross-map warp

ACTION: WAIT without input
POST_WARP: Map and coordinates may change drastically
```

**prompts/transition/cutscene_transition.txt**
```
CURRENT STATE: Cutscene Transition
STORY_IMPORTANCE: {minor|major|legendary}
DURATION: 50-200 ticks

CONTROL: Limited or no control
OBSERVATION: Story events unfolding

CONTENT_TYPE:
- Character movements
- Dialogue sequences
- Special animations
- Camera pan effects

ACTION: Advance text when prompted, otherwise observe
MEMORY: Record story events and information
```

**prompts/transition/evolution_animation.txt**
```
CURRENT STATE: Pokemon Evolution
POKEMON: {pokemon_name} evolving to {next_form}
DURATION: 100-200 ticks

ANIMATION_SEQUENCE:
1. Pokemon flashes white
2. Evolution animation plays
3. New form revealed
4. Stats increase shown
5. "Congratulations!" message

NO_CANCEL: Cannot stop evolution
RESULT: Permanent form and stat change

ACTION: WAIT through entire animation
MEMORY: Record evolution, update Pokedex
```

**prompts/transition/ability_activation.txt**
```
CURRENT STATE: Ability Activation
ABILITY: {ability_name}
ACTOR: {pokemon_name}

ABILITY_TYPES:
- Intimidate: Opponent Attack drops on entry
- Overgrow: Grass moves boost at low HP
- Blaze: Fire moves boost at low HP
- Torrent: Water moves boost at low HP
- Static: Contact may cause paralysis

ANIMATION: Brief flash or effect
DURATION: 20-40 ticks
IMPACT: Battle state change

ACTION: Note ability effect, adjust strategy
MEMORY: Log ability for this Pokemon species
```

**prompts/transition/status_condition_start.txt**
```
CURRENT STATE: Status Condition Applied
CONDITION: {burn|poison|paralyze|sleep|freeze|confusion}
TARGET: {pokemon_name}
SOURCE: {move_name|ability}

ANIMATION: Visual effect showing condition
DURATION: 30-50 ticks

IMMEDIATE_EFFECT:
- Burn/Poison: Immediate damage tick
- Sleep: Pokemon falls asleep
- Paralyze: "Pokemon is paralyzed!"
- Freeze: Pokemon frozen solid
- Confusion: "Pokemon is confused!"

ACTION: Wait for condition to be established
STRATEGY: Plan healing or switch based on condition
```

---

### **ERROR & RECOVERY PROMPTS (8)**

**prompts/error/unknown_screen.txt**
```
CURRENT STATE: Unknown Screen Detected
SCREEN_TYPE: Unrecognized game state
VISUAL: {screenshot_description}

POSSIBLE_CAUSES:
1. Glitch or corruption
2. Emulator error
3. ROM compatibility issue
4. New unexplored game area
5. Animation frame not in training data

DIAGNOSTIC_STEPS:
1. Wait 60 ticks for state to resolve
2. Press B to go back if possible
3. Try directional buttons
4. Take screenshot for analysis
5. Log unknown state details

RECOVERY_ATTEMPTS: {attempt_count}/3
ACTION: Attempt recovery or exit gracefully
```

**prompts/error/corrupted_save.txt**
```
CURRENT STATE: Save File Corruption
SAVE_FILE: {save_file_path}
ERROR: {corruption_error}

CORRUPTION_TYPES:
- Checksum mismatch: Data integrity compromised
- Incomplete save: Save interrupted during write
- Version mismatch: Wrong game version
- File missing: Save file not found

OPTIONS:
1. Try backup save (if exists)
2. Start new game (if --new-game-on-corruption)
3. Exit with error (safe default)
4. Attempt repair (advanced, risky)

USER_OVERRIDE: {new_game_flag_status}
ACTION: Handle based on flags and backup availability
```

**prompts/error/emulator_crash.txt**
```
CURRENT STATE: Emulator Crash
PYBOY_STATE: {pyboy_status}
ERROR_TYPE: {segfault|memory_error|rom_error}

LAST_ACTIONS: {last_10_actions}
LAST_SCREENSHOT: {screenshot_path}

RECOVERY:
1. Save crash dump
2. Log last actions
3. Save screenshot
4. Restart emulator
5. Load last known good state

PREVENTION: Avoid repeating last action sequence
ACTION: Log error, attempt restart recovery
```

**prompts/error/rom_not_found.txt**
```
CURRENT STATE: ROM File Not Found
ROM_PATH: {rom_file_path}
STATUS: File does not exist

CHECKS:
- Path correct? {path_check}
- File extension .gb/.gbc? {extension_check}
- File readable? {permissions_check}
- Valid Pokemon ROM? {validation_check}

SOLUTIONS:
1. Verify ROM path in config
2. Check file permissions
3. Verify ROM file integrity
4. Ensure valid Pokemon Gen 1 ROM

ACTION: Exit with detailed file not found error
```

**prompts/error/vision_api_failure.txt**
```
CURRENT STATE: Vision API Call Failed
API: {openrouter|claude|stub}
ERROR: {api_error_message}
ATTEMPT: {retry_count}/3

FAILURE_TYPES:
- Network error: Timeout, connection failed
- API error: Invalid key, rate limit
- Image error: Encoding, format, size
- Response error: Malformed, timeout

FALLBACK:
1. Retry with exponential backoff
2. Use stub mode (if enabled)
3. Default to safe action (press A)
4. Log error and continue

ACTION: Retry or fallback to stub mode
```

**prompts/error/state_detection_failure.txt**
```
CURRENT STATE: State Detection Failed
SCREEN_CLASSIFICATION: Unable to determine state
CONFIDENCE: <50%

POSSIBLE_CAUSES:
- Transition state between screens
- Unrecognized menu or interface
- New game area not in training
- Emulator rendering issue
- Screenshot capture timing issue

SAFE_ACTIONS:
1. Wait 30 ticks, try detection again
2. Press A (safe default)
3. Take high-res screenshot for training
4. Log unknown state for analysis

ACTION: Use safe default and log for training data
```

**prompts/error/command_execution_failed.txt**
```
CURRENT STATE: Command Execution Failed
COMMAND: {command_string}
ERROR: {execution_error}

FAILURE_TYPES:
- Invalid button mapping
- Emulator not responding
- Command timing issue
- State changed before execution

RECOVERY:
1. Verify emulator state
2. Retry command
3. Try alternative command
4. Log failure and continue

ACTION: Retry or skip and log error
```

**prompts/error/memory_full.txt**
```
CURRENT STATE: Memory Storage Full
MEMORY_TIER: {tactician|strategist|observer}
USAGE: {current_usage}/{max_capacity}
GROWTH_RATE: {growth_rate_per_hour}

COMPRESSION_TRIGGERED: True
COMPRESSION_TARGET: Reduce to 60% capacity

ACTIONS_TAKEN:
1. Compress older memories
2. Prune low-relevance data
3. Archive to disk if necessary

IMPACT: May lose some historical detail
PREVENTION: Compress more frequently

ACTION: Continue with compressed memory
```

---

## 🚀 LOGGING SYSTEM ARCHITECTURE

### **Log Directory Structure**

```
logs/
├── main/
│   ├── pokemon_ai_20251231_120000.log      # Primary application log
│   ├── pokemon_ai_20251231_120000.log.1    # Rotated log
│   └── ...
├── decisions/
│   ├── decisions_20251231_120000.log       # AI decision log
│   └── ...
├── battles/
│   ├── battles_20251231_120000.log         # Battle analytics
│   └── ...
├── errors/
│   ├── errors_20251231_120000.log          # Error tracking
│   └── ...
└── performance/
    ├── performance_20251231_120000.log     # Performance metrics
    └── ...
```

### **Log Format Specification**

**Standard Log Entry Format**:
```
[timestamp] [LEVEL] [CATEGORY] [SUBCATEGORY] message_key=value [metadata]
```

**Timestamp Format**: `2025-12-31 14:30:45.123456` (microsecond precision)

**Log Levels**:
- `DEBUG` - Detailed diagnostic information
- `INFO` - Normal operational messages
- `WARNING` - Unexpected situations, non-critical errors
- `ERROR` - Failures requiring intervention
- `CRITICAL` - System failures, cannot continue

**Log Categories**:
- `EMULATOR` - PyBoy emulator events
- `AI` - AI decision making
- `VISION` - Screen analysis and vision API
- `MEMORY` - Memory management operations
- `BATTLE` - Battle system events
- `STATE` - Game state detection
- `COMMAND` - Button press execution
- `ERROR` - Error and exception handling

### **Log Entry Examples**

**Emulator Log**:
```
[2025-12-31 14:30:45.123456] [INFO] [EMULATOR] [START] rom_path=/roms/pokemon_blue.gb
[2025-12-31 14:30:45.234567] [INFO] [EMULATOR] [TICK] tick_count=100 fps=60.0
[2025-12-31 14:30:46.345678] [INFO] [EMULATOR] [SCREENSHOT] saved_to=./screenshots/overworld/tick_000100.png
[2025-12-31 14:30:47.456789] [WARNING] [EMULATOR] [LOW_MEMORY] available_ram=512MB
```

**AI Decision Log**:
```
[2025-12-31 14:30:48.123456] [INFO] [AI] [DECISION_START] tick=125 screen_type=battle
[2025-12-31 14:30:48.987654] [INFO] [AI] [PROMPT_SELECTED] prompt=battle/move_selection.txt
[2025-12-31 14:30:50.234567] [INFO] [AI] [API_CALL] model=gpt-4o input_tokens=523 output_tokens=87
[2025-12-31 14:30:50.345678] [INFO] [AI] [DECISION_MADE] action=press:A confidence=0.92 reasoning="Use super-effective move"
```

**Battle Log**:
```
[2025-12-31 14:30:52.123456] [INFO] [BATTLE] [START] enemy=Pidgey_Lv3 location=Route1
[2025-12-31 14:30:54.234567] [INFO] [BATTLE] [TURN] turn=1 player_move=Tackle enemy_hp=92%
[2025-12-31 14:30:55.345678] [INFO] [BATTLE] [TURN] turn=2 player_move=Tackle enemy_hp=84%
[2025-12-31 14:30:56.456789] [INFO] [BATTLE] [VICTORY] exp_gained=45 money_gained=0 duration_ticks=180
```

**Error Log**:
```
[2025-12-31 14:30:58.123456] [ERROR] [EMULATOR] [ROM_ERROR] message="Invalid ROM file format" rom_path=./roms/bad_file.txt
[2025-12-31 14:30:58.234567] [ERROR] [AI] [API_FAILURE] model=gpt-4o error="timeout" retry=1/3
[2025-12-31 14:30:59.345678] [CRITICAL] [STATE] [UNKNOWN_SCREEN] confidence=0.23 screenshot=./logs/errors/unknown_20251231_143059.png
[2025-12-31 14:31:00.456789] [WARNING] [MEMORY] [COMPRESSION] tier=STRATEGIST compressed_from=85k_to=42k
```

### **Log Rotation Configuration**

**Rotation Policy**:
- Max file size: 10 MB per log file
- Max files: 10 rotated files per category
- Age limit: Delete logs older than 30 days

**Rotation Naming**:
```
pokemon_ai_20251231_120000.log (current)
pokemon_ai_20251231_120000.log.1 (previous)
pokemon_ai_20251231_120000.log.2 (older)
...
pokemon_ai_20251231_120000.log.9 (oldest)
```

**Automatic Rotation Trigger**:
- File size > 10 MB → Create new file
- Date change at midnight → New file per day
- Manual reset signal → Create fresh log

### **Event Logging Schema**

**Structured Event Format** (JSON for easy parsing):
```json
{
  "timestamp": "2025-12-31T14:30:45.123456",
  "level": "INFO",
  "category": "BATTLE",
  "subcategory": "START",
  "event_id": "evt_00123",
  "session_id": "sess_abcde",
  "tick": 1250,
  "data": {
    "enemy": "Pidgey",
    "level": 3,
    "location": "Route1",
    "player_hp": 85
  },
  "metadata": {
    "screenshot": "./screenshots/battles/tick_001250.png",
    "confidence": 0.95
  }
}
```

### **Real-Time Log Viewing**

**Log Tailing Command**:
```bash
tail -f logs/main/pokemon_ai_$(date +%Y%m%d).log
```

**Filter by Category**:
```bash
grep "\[BATTLE\]" logs/main/*.log
```

**Filter by Level**:
```bash
grep "\[ERROR\]\|\[CRITICAL\]" logs/main/*.log
```

**Performance Metrics Extraction**:
```bash
grep "\[PERFORMANCE\]" logs/performance/*.log | jq -r '.data.fps'
```

---

## 🧠 MEMORY COMPRESSION SYSTEM

### **Three-Tier Memory Architecture**

#### **TIER 1: OBSERVER MEMORY (Persistent)**

**Purpose**: Long-term journey narrative, never pruned

**Structure**:
```json
{
  "observer": {
    "journey": {
      "game_id": "pokemon_blue_run_001",
      "start_time": "2025-12-31T12:00:00",
      "total_playtime": "04:23:15",
      "current_location": "Viridian City",
      "game_progress": 0.15
    },
    "badges": {
      "boulder": false,
      "cascade": false,
      "thunder": false,
      "rainbow": false,
      "soul": false,
      "marsh": false,
      "volcano": false,
      "earth": false
    },
    "major_events": [
      {
        "timestamp": "2025-12-31T12:15:30",
        "event": "starter_selected",
        "details": {"pokemon": "bulbasaur"}
      },
      {
        "timestamp": "2025-12-31T12:45:22",
        "event": "first_battle_won",
        "details": {"enemy": "pidgey"}
      }
    ],
    "pokedex": {
      "caught": {"bulbasaur": 1, "pidgey": 3, "rattata": 2},
      "seen": {"squirtle": 1, "charmander": 1},
      "completion": 0.03
    },
    "team_evolution": {
      "starter_pokemon": "bulbasaur",
      "evolved": {},
      "released": {},
      "current_party": ["bulbasaur"]
    }
  }
}
```

**Update Frequency**: After every major event (gym, badge, story milestone)

**Storage**: Persistent JSON file, loaded at startup

**Size**: ~10-50 KB (grows slowly)

**Pruning**: NEVER - Complete history preserved

---

#### **TIER 2: STRATEGIST MEMORY (Session)**

**Purpose**: Mid-term heuristics, learning from battles

**Structure**:
```json
{
  "strategist": {
    "type_matchups_learned": {
      "pidgey": {
        "types": ["normal", "flying"],
        "weaknesses": ["electric", "ice", "rock"],
        "resistances": ["grass", "bug", "fighting"],
        "immunities": ["ground"],
        "confidence": 0.92,
        "encounters": 23,
        "wins": 22,
        "best_moves": ["thundershock", "rock_throw", "ice_beam"]
      }
    },
    "resource_management": {
      "item_efficiency": {
        "potion_value": 20,  // HP per use
        "potion_efficiency": 0.067,  // HP per dollar
        "optimal_use_threshold": 0.5  // Use at 50% HP
      },
      "money_balance": {
        "spent": 4500,
        "earned": 6800,
        "current": 2300,
        "expenses_breakdown": {
          "potions": 2100,
          "pokeballs": 1200,
          "repels": 800,
          "escape_ropes": 400
        }
      }
    },
    "battle_patterns": {
      "bug_catcher_pokemon": ["caterpie", "weedle", "metapod", "kakuna"],
      "bug_catcher_strategy": "Low level, evolve soon",
      "youngster_pokemon": ["rattata", "spearow", "ekans"],
      "lass_pokemon": ["jigglypuff", "clefairy"]
    },
    "encounter_rates": {
      "route1_grass": {
        "pidgey": 0.45,
        "rattata": 0.40,
        "other": 0.15,
        "sample_size": 89
      }
    },
    "failure_analysis": [
      {
        "timestamp": "2025-12-31T13:15:22",
        "battle": {
          "enemy": "geodude",
          "level": 10,
          "types": ["rock", "ground"]
        },
        "mistake": "used_fire_moves",
        "correct_strategy": "use_water_grass_moves",
        "lesson": "Rock/Ground weak to Water and Grass",
        "confidence": 0.87
      }
    ]
  }
}
```

**Update Frequency**: After every battle or significant event

**Storage**: In-memory + periodic JSON snapshot

**Size**: ~100-500 KB (grows during session)

**Pruning**: Compress after 1000 turns without access

---

#### **TIER 3: TACTICIAN MEMORY (Immediate)**

**Purpose**: Current battle state, immediate context

**Structure**:
```json
{
  "tactician": {
    "current_battle": {
      "active": true,
      "enemy": {
        "name": "pidgey",
        "level": 3,
       "types": ["normal", "flying"],
 "hp_percentage": 65,
        "max_hp": 38,
        "current_hp": 25,
        "last_move": "tackle",
        "attack_pattern": ["tackle", "tackle", "gust"],
        "stats": {
          "attack": 18,
          "defense": 16,
          "speed": 20
        }
      },
      "player": {
        "active_pokemon": "bulbasaur",
        "level": 6,
        "hp_percentage": 82,
        "current_hp": 29,
        "max_hp": 35,
        "moves": [
          {
            "name": "tackle",
            "type": "normal",
            "power": 40,
            "pp": 23,
            "max_pp": 35,
            "accuracy": 100
          },
          {
            "name": "growl",
            "type": "normal",
            "power": 0,
            "pp": 38,
            "max_pp": 40,
            "accuracy": 100
          },
          {
            "name": "vine_whip",
            "type": "grass",
            "power": 35,
            "pp": 8,
            "max_pp": 10,
            "accuracy": 100
          }
        ]
      },
      "turn_number": 3,
      "last_action": "player_used_tackle",
      "battle_start_tick": 1250,
      "battle_type": "wild_encounter"
    },
    "recent_actions": [
      {
        "tick": 1200,
        "action": "navigate_north",
        "location": "route1"
      },
      {
        "tick": 1250,
        "action": "battle_start",
        "enemy": "pidgey"
      },
      {
        "tick": 1260,
        "action": "battle_command",
        "command": "press:A",
        "menu_choice": "tackle"
      }
    ],
    "immediate_objectives": {
      "primary": "Defeat current enemy",
      "secondary": "Conserve PP and HP",
      "tertiary": "Gain EXP efficiently"
    },
    "environmental_factors": {
      "weather": null,
      "terrain": "normal",
      "field_effects": []
    }
  }
}
```

**Update Frequency**: Every tick during battle

**Storage**: In-memory only

**Size**: ~10-50 KB (constant size, flushed after battle)

**Pruning**: Cleared after each battle

---

### **Memory Compression Algorithm**

#### **Compression Trigger Conditions**

```python
def should_compress_memory(memory_data, current_context):
    """
    Determine if memory compression is needed
    """
    triggers = []

    # Size-based triggers
    if memory_data['observer_size'] > 50000:  # 50KB
        triggers.append('observer_oversize')

    if memory_data['strategist_size'] > 300000:  # 300KB
        triggers.append('strategist_oversize')

    if memory_data['tactician_size'] > 50000:  # 50KB
        triggers.append('tactician_oversize')

    # Time-based triggers
    if current_context['time_since_last_compression'] > 600:  # 10 minutes
        triggers.append('time_threshold')

    # Event-based triggers
    if current_context['major_event_occurred']:
        triggers.append('post_major_event')

    # Context window triggers
    if current_context['context_window_usage'] > 0.8:  # 80% full
        triggers.append('context_near_limit')

    return triggers
```

#### **Observer Memory Compression (Minimal)**

```python
def compress_observer_memory(observer_data, current_tier2):
    """
    Minimal compression - mostly preserve, slight summarization
    """
    compressed = observer_data.copy()

    # Keep all major events, but summarize minor ones
    minor_events = [e for e in compressed['major_events'] if e['importance'] == 'minor']
    if len(minor_events) > 100:
        # Keep most recent 20 minor events
        compressed['major_events'] = [
            e for e in compressed['major_events'] if e['importance'] != 'minor'
        ] + minor_events[-20:]

   # Summarize repetitive encounter data
    for species, data in compressed['pokedex']['caught'].items():
  if data['count'] > 50:
      data['summary'] = f"Caught {data['count']} total, first at {data['first_catch']}"
  if len(data['detailed_times']) > 10:
            data['detailed_times'] = data['detailed_times'][-10:]  # Keep last 10

    return compressed
```

#### **Strategist Memory Compression (Moderate)**

```python
def compress_strategist_memory(strategist_data, current_context):
    """
    Moderate compression - merge similar learnings
    """
    compressed = strategist_data.copy()

    # Merge type matchups by confidence
    for species, matchup in compressed['type_matchups_learned'].items():
        if matchup['encounters'] > 20:
 # High confidence, keep summary
         matchup['confidence'] = min(1.0, matchup['confidence'])
       matchup['detailed_encounters'] = matchup['encounters']  # Store count
       if len(matchup['specific_instances']) > 10:
    matchup['specific_instances'] = matchup['specific_instances'][-5:]

    # Age out old failure analysis
    current_time = datetime.now()
    compressed['failure_analysis'] = [
        f for f in compressed['failure_analysis']
  if (current_time - f['timestamp']).days < 7  # Keep last 7 days
    ]

    # Summarize encounter rates if large sample
    for location, rates in compressed['encounter_rates'].items():
  if rates['sample_size'] > 200:
      # Keep as is but remove raw timestamps
      if 'timestamps' in rates:
    del rates['timestamps']

    return compressed
```

#### **Tactician Memory Compression (Aggressive)**

```python
def compress_tactician_memory(tactician_data):
    """
    Aggressive compression - summarize battle history
  """
    compressed = tactician_data.copy()

    if 'current_battle' in compressed and compressed['current_battle']['active']:
        # In battle - preserve critical info
        battle = compressed['current_battle']

        # Summarize turn history
        if len(battle.get('turn_history', [])) > 20:
            recent_turns = battle['turn_history'][-5:]
            summary = {
                'total_turns': len(battle['turn_history']),
                'recent_turns': recent_turns,
                'player_damage_dealt': sum(t.get('player_damage', 0) for t in battle['turn_history']),
         'enemy_damage_dealt': sum(t.get('enemy_damage', 0) for t in battle['turn_history'])
            }
    battle['turn_history'] = summary

    # Compress recent actions, keep only last 10
    if len(compressed.get('recent_actions', [])) > 50:
        compressed['recent_actions'] = compressed['recent_actions'][-10:]

    return compressed
```

#### **Compression Metrics and Monitoring**

```python
def log_compression_metrics(before, after, tier):
    """
    Log compression effectiveness
    """
    original_size = len(json.dumps(before))
    compressed_size = len(json.dumps(after))
    compression_ratio = compressed_size / original_size

    logger.info(
        f"[MEMORY] [COMPRESSION] tier={tier} "
        f"original={original_size}b compressed={compressed_size}b "
        f"ratio={compression_ratio:.2f} saved={original_size-compressed_size}b"
    )

    # Warn if compression too aggressive
    if compression_ratio < 0.3:  # Lost >70% of data
  logger.warning(
      f"[MEMORY] [AGGRESSIVE_COMPRESSION] tier={tier} "
   f"ratio={compression_ratio:.2f} - May have lost important data"
    )

    return {
        'timestamp': datetime.now().isoformat(),
        'tier': tier,
        'original_size': original_size,
  'compressed_size': compressed_size,
        'compression_ratio': compression_ratio
    }
```

### **Memory Storage Implementation**

**File-Based Persistence**:
```
memory/
├── observer/
│   ├── observer_current.json              # Current observer memory
│   ├── observer_archive_20251231_1200.json # Hourly snapshots
│   └── observer_archive_20251230_1200.json
├── strategist/
│   ├── strategist_current.json
│   └── strategist_archive_*.json
└── tactician/
    └── tactician_current.json (volatile, frequent updates)
```

**Writing Strategy**:
- Observer: Write on major events + hourly
- Strategist: Write after each battle + every 10 minutes
- Tactician: Write every tick (in-memory only, periodic disk sync)

**Loading Strategy**:
- Load observer at startup (complete history)
- Load strategist at startup (session learning)
- Initialize tactician fresh (immediate context)

---

## 🚨 ERROR HANDLING & RECOVERY

### **Error Hierarchy**

```python
ERROR_SEVERITY = {
    "LOW": {
        "examples": ["minor_vision_confidence", "non_critical_api_timeout"],
        "action": "log_and_continue",
        "retry": True
    },
    "MEDIUM": {
        "examples": ["state_detection_failed", "command_retry_exceeded"],
        "action": "retry_with_fallback",
    "retry": True,
        "max_attempts": 3
    },
    "HIGH": {
        "examples": ["save_corruption", "emulator_crash"],
        "action": "safe_recovery_mode",
        "retry": False,
        "requires_user": True
    },
    "CRITICAL": {
  "examples": ["rom_not_found", "unrecoverable_state"],
        "action": "immediate_shutdown",
     "save_state": "emergency_save",
        "requires_user": True
    }
}
```

### **Recovery Strategies**

**1. Safe Default Recovery**:
```python
def safe_default_recovery(error_context):
    """
    When state unknown, use safe default actions
    """
    logger.warning(f"[RECOVERY] Using safe default, error={error_context}")

    # Press A is safest in most situations
    safe_action = "press:A"

    # Wait longer than usual
    time.sleep(1.0)

    # Try detection again
    return safe_action
```

**2. State Rollback Recovery**:
```python
def rollback_recovery(desired_state, max_rollback=100):
    """
    Roll back emulator state to known good point
  """
    logger.critical(f"[RECOVERY] Rolling back to state {desired_state}")

    # Load previous save state
    emulator.load_state(f"checkpoint_{desired_state}.state")

    # Clear recent memory that might be corrupted
    memory.tactician.clear()

    return True
```

**3. Stub Mode Fallback**:
```python
def stub_mode_fallback():
    """
    Switch to stub AI mode when vision API fails
    """
    logger.warning("[RECOVERY] Switching to stub AI mode")

    # Disable API calls
    config.USE_VISION_API = False
    config.USE_STUB_MODE = True

    # Use simple heuristics
    ai.decision_function = simple_battle_heuristic

    return True
```

**4. Restart Recovery**:
```python
def restart_emulator_recovery():
    """
    Restart emulator when unrecoverable
    """
    logger.critical("[RECOVERY] Restarting emulator")

    # Save emergency state
    emulator.save_state("emergency_recovery.state")

    # Stop emulator
    emulator.stop()

    # Wait and restart
    time.sleep(2.0)
    emulator.start()

    # Load emergency state
    emulator.load_state("emergency_recovery.state")

    return True
```

### **Error Recovery Workflow**

```
Error Detected
     ↓
Classify Severity (LOW/MEDIUM/HIGH/CRITICAL)
     ↓
Choose Recovery Strategy
     ↓
┌─────────────────┬──────────────┬─────────────┬──────────────┐
│ LOW             │ MEDIUM       │ HIGH        │ CRITICAL     │
│ log_and_continue│ retry_3x     │ safe_mode   │ emergency_   │
│                 │ fallback_    │ user_       │ shutdown     │
│                 │ stub         │ notification│ save_        │
│                 │              │ rollback    │ screenshot   │
└─────────────────┴──────────────┴─────────────┴──────────────┘
     ↓
Execute Recovery
     ↓
Log Recovery Attempt
     ↓
Verify Recovery Success
     ↓
Return to Normal Operation or Escalate
```

---

## 🎯 STATE MACHINE IMPLEMENTATION

### **Phase Detection Algorithm**

```python
def detect_game_phase(screenshot, memory_context, tick):
    """
    Determine current game phase from screenshot and context

    Returns:
        {
            'phase': str,
            'confidence': float,
            'substate': str,
            'transitions_from': [str],
            'transitions_to': [str],
            'required_action': str
        }
    """
    # Multi-modal detection
    visual_features = extract_visual_features(screenshot)
    text_content = extract_visible_text(screenshot)
    color_profile = analyze_color_distribution(screenshot)
    layout_features = detect_layout_regions(screenshot)

    # Phase classification
    phase_scores = {}

    # Check for battle indicators
    if (visual_features['hp_bars_detected'] > 0 and
        visual_features['battle_sprites_visible'] and
     layout_features['bottom_menu_present']):
        phase_scores['battle'] = 0.9

    # Check for overworld
    if (color_profile['green_ratio'] > 0.3 and
      visual_features['character_sprite_visible'] and
   not visual_features['dialog_box_present']):
        phase_scores['overworld'] = 0.85

    # Check for dialog
    if (text_content and
    layout_features['text_box_bottom'] and
        visual_features['dialog_box_present']):
        phase_scores['dialog'] = 0.95

    # Check for menu
    if (layout_features['grid_pattern'] and
       visual_features['cursor_indicator'] and
        color_profile['menu_colors']):
        phase_scores['menu'] = 0.9

    # Check for transition/black screen
    if (color_profile['black_ratio'] > 0.9 or
  visual_features['brightness_avg'] < 20):
        phase_scores['transition'] = 0.95

    # Find highest confidence phase
    if phase_scores:
        best_phase = max(phase_scores.items(), key=lambda x: x[1])

        # Determine substate
        substate = determine_substate(
   best_phase[0], visual_features, text_content, memory_context
  )

        return {
     'phase': best_phase[0],
            'confidence': best_phase[1],
   'substate': substate,
        'transitions_from': get_possible_transitions_from(substate),
      'transitions_to': get_possible_transitions_to(substate),
 'required_action': get_required_action(substate)
        }

    # Fallback - unknown state
    return {
 'phase': 'unknown',
        'confidence': 0.0,
        'substate': 'unknown_screen',
        'transitions_from': [],
        'transitions_to': [],
        'required_action': 'safe_default'
    }
```

### **Substate Determination**

```python
def determine_substate(phase, visual_features, text_content, context):
    """
    Get specific substate within main phase
    """
    if phase == 'battle':
        if 'FIGHT/BAG/POKéMON/RUN' in text_content:
            return 'battle_menu'
        elif 'wild' in text_content.lower():
     return 'wild_encounter_start'
        elif visual_features['hp_bars_animating']:
      return 'battle_animation'
        elif 'Gained' in text_content and 'EXP' in text_content:
            return 'experience_gain'
        elif 'fainted' in text_content.lower():
            return 'pokemon_fainted'
     elif visual_features['pokemon_stats_visible']:
      return 'battle_stats_display'
        else:
    return 'battle_active'

    elif phase == 'overworld':
        if visual_features['grass_tiles_visible']:
       return 'overworld_grass'
        elif visual_features['cave_tiles_visible']:
     return 'overworld_cave'
        elif visual_features['water_tiles_visible']:
        return 'overworld_water'
        elif visual_features['building_entrance']:
      return 'overworld_near_building'
        else:
            return 'overworld_path'

    elif phase == 'menu':
        if 'POKéMON' in text_content:
            return 'menu_pokemon'
        elif 'BAG' in text_content:
  return 'menu_bag'
      elif 'SAVE' in text_content:
       return 'menu_save'
        elif 'OPTION' in text_content:
  return 'menu_options'
        else:
      return 'menu_main'

    elif phase == 'dialog':
        if 'Healing' in text_content and 'Pokemon' in text_content:
            return 'dialog_pokemon_center'
        elif 'Mart' in text_content or 'Welcome' in text_content:
            return 'dialog_shop'
     elif 'Welcome' in text_content and 'WORLD' in text_content.upper():
      return 'dialog_oak_intro'
        elif '!' in text_content or '?' in text_content:
    return 'dialog_story'
        else:
          return 'dialog_npc'

    return f"{phase}_generic"
```

### **State Transition Matrix**

```python
STATE_TRANSITIONS = {
    # Menu states
    'menu_main': {
        'transitions_from': ['overworld', 'dialog', 'battle', 'transition'],
        'transitions_to': ['menu_pokemon', 'menu_bag', 'menu_save', 'menu_options', 'overworld'],
        'required_actions': ['menu_navigation', 'button_press']
    },

    # Battle states
    'battle_menu': {
        'transitions_from': ['battle_animation', 'battle_start', 'battle_turn'],
        'transitions_to': ['move_selection', 'bag_menu', 'pokemon_switch', 'run_attempt', 'battle_animation'],
        'required_actions': ['battle_decision']
    },

    # Overworld states
    'overworld_grass': {
        'transitions_from': ['overworld_path', 'battle_victory', 'pokemon_center_exit'],
        'transitions_to': ['battle_wild_encounter', 'overworld_path', 'grass_encounter_check'],
        'required_actions': ['navigation', 'encounter_check']
    },

    # Dialog states
    'dialog_pokemon_center': {
        'transitions_from': ['overworld_near_building', 'transition_door'],
        'transitions_to': ['menu_pc_heal', 'dialog_continue', 'pokemon_center_exit'],
  'required_actions': ['dialog_advance', 'healing_decision']
    },

    # Transition states
    'transition_door': {
        'transitions_from': ['overworld_near_building', 'menu_exit'],
        'transitions_to': ['dialog_shop', 'dialog_pokemon_center', 'overworld'],
        'required_actions': ['wait_for_animation']
    },

    # Error states
    'unknown_screen': {
        'transitions_from': ['any'],
        'transitions_to': ['safe_default', 'previous_known', 'emergency_exit'],
        'required_actions': ['safe_recovery', 'error_logging']
    }
}
```

---

## 📊 IMPLEMENTATION ROADMAP

### **Phase 1: Foundation (Days 1-2)**

**Priority 1: Comprehensive Logging System**
- [ ] Create logger.py with file-based logging
- [ ] Implement log rotation and archiving
- [ ] Add structured JSON logging for events
- [ ] Create log directory structure
- [ ] Add log level filtering
- [ ] Implement real-time log viewing tools

**Priority 2: Expand Prompt Library**
- [ ] Create all 50+ prompt templates
- [ ] Organize prompts in directory structure
- [ ] Add prompt validation and testing
- [ ] Implement dynamic prompt selection
- [ ] Add prompt versioning

**Priority 3: Save File Management**
- [ ] Implement save file validation
- [ ] Add save corruption detection
- [ ] Create backup save system
- [ ] Add save state management
- [ ] Implement new game flow

### **Phase 2: Intelligence Core (Days 3-4)**

**Priority 4: Memory Compression System**
- [ ] Implement 3-tier memory architecture
- [ ] Add memory compression algorithms
- [ ] Create memory persistence layer
- [ ] Implement memory retrieval and filtering
- [ ] Add memory analytics and monitoring

**Priority 5: State Machine Enhancement**
- [ ] Improve phase detection accuracy
- [ ] Add substate recognition
- [ ] Implement transition tracking
- [ ] Add state confidence scoring
- [ ] Create state recovery mechanisms

**Priority 6: Prompt Routing**
- [ ] Implement phase-based prompt selection
- [ ] Add context-aware routing
- [ ] Create prompt fallback system
- [ ] Add prompt effectiveness tracking

### **Phase 3: Robustness (Days 5-6)**

**Priority 7: Error Recovery**
- [ ] Implement error classification
- [ ] Add recovery strategies
- [ ] Create safe mode fallback
- [ ] Add emergency save system
- [ ] Implement user notification system

**Priority 8: Vision API Fix**
- [ ] Debug image encoding issue
- [ ] Test with real screenshots
- [ ] Add image quality validation
- [ ] Implement fallback to stub
- [ ] Add API error handling

**Priority 9: Testing & Validation**
- [ ] Test all game phases
- [ ] Validate prompt effectiveness
- [ ] Test error recovery
- [ ] Performance profiling
- [ ] User acceptance testing

### **Phase 4: Polish (Day 7)**

**Priority 10: Analytics Dashboard**
- [ ] Create real-time metrics display
- [ ] Add performance visualization
- [ ] Implement decision playback
- [ ] Add memory usage charts

**Priority 11: Documentation**
- [ ] Complete API documentation
- [ ] Add user guide
- [ ] Create troubleshooting guide
- [ ] Document all prompts

**Priority 12: Deployment**
- [ ] Package for distribution
- [ ] Create startup scripts
- [ ] Add configuration management
- [ ] Production monitoring setup

---

## 🎯 SUCCESS METRICS

### **Functional Metrics**

- **Phase Coverage**: 50+ game phases supported (target: 100%)
- **Prompt Library**: 50+ prompt templates (target: 100%)
- **State Detection Accuracy**: >95% correct phase detection
- **Battle Win Rate**: >70% win rate against wild Pokemon
- **Error Recovery**: >90% errors recovered automatically

### **Performance Metrics**

- **Decision Latency**: <1000ms per decision (target: <500ms)
- **API Cost**: <$0.10 per hour of gameplay
- **Memory Usage**: <1GB RAM total
- **Log File Size**: <100MB per day maximum
- **Startup Time**: <10 seconds

### **Quality Metrics**

- **Code Coverage**: >80% test coverage
- **Type Hints**: 100% public functions typed
- **Documentation**: 100% modules documented
- **Error Rate**: <1% unhandled errors
- **User Satisfaction**: Can complete Viridian Forest

---

## 🔧 TECHNICAL IMPLEMENTATION DETAILS

### **Core Components**

**1. Enhanced Logger** (`src/core/logger.py`):
```python
import logging
import logging.handlers
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

class PokemonLogger:
    """
    Structured logging for AI Pokemon system
    """

    def __init__(self, log_dir: str = "./logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create loggers for each category
        self.loggers = {}
        for category in ['main', 'decisions', 'battles', 'errors', 'performance']:
   self._setup_logger(category)

    def _setup_logger(self, category: str):
        """Set up individual logger for category"""
        logger = logging.getLogger(f"pokemon_{category}")
 logger.setLevel(logging.DEBUG)

        # Create log directory for category
        cat_dir = self.log_dir / category
        cat_dir.mkdir(exist_ok=True)

        # File handler with rotation
        log_file = cat_dir / f"{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        handler = logging.handlers.RotatingFileHandler(
            log_file,
      maxBytes=10*1024*1024,  # 10MB
     backupCount=10
        )

        # JSON formatter for structured logging
        formatter = JSONFormatter()
 handler.setFormatter(formatter)

        logger.addHandler(handler)
     self.loggers[category] = logger

    def log(self, level: str, category: str, subcategory: str,
 message: str, data: Dict[str, Any] = None):
        """Log structured event"""
        logger = self.loggers.get(category)
        if not logger:
            raise ValueError(f"Unknown log category: {category}")

        log_data = {
     'timestamp': datetime.now().isoformat(),
            'level': level,
     'category': category,
            'subcategory': subcategory,
            'message': message,
            'data': data or {}
        }

        log_method = getattr(logger, level.lower())
        log_method(json.dumps(log_data))

 class JSONFormatter(logging.Formatter):
    """JSON log formatter"""

    def format(self, record):
        try:
            # Parse JSON if message is already JSON
   log_data = json.loads(record.getMessage())
        except json.JSONDecodeError:
            # Otherwise create basic JSON structure
      log_data = {
         'timestamp': datetime.now().isoformat(),
            'message': record.getMessage()
            }

        return json.dumps(log_data)
```

**2. State Detector** (`src/core/state_detector.py`):
```python
import cv2
import numpy as np
from typing import Dict, Any, Tuple
from pathlib import Path

class GameStateDetector:
    """
    Detect current game state from screenshots
    """

    def __init__(self, model_path: str = None):
        self.model_path = model_path
        self.phase_templates = self._load_phase_templates()

    def detect_state(self, screenshot: np.ndarray, context: Dict) -> Dict[str, Any]:
        """Detect current game phase with confidence"""

        # Extract features
        features = self._extract_features(screenshot)
        text = self._extract_text(screenshot)

        # Compare against known phase templates
        phase_scores = {}
        for phase_name, template in self.phase_templates.items():
            score = self._compare_to_template(features, text, template)
  phase_scores[phase_name] = score

        # Select best match
        best_phase = max(phase_scores.items(), key=lambda x: x[1])

        return {
   'phase': best_phase[0],
            'confidence': best_phase[1],
     'features': features,
            'detected_text': text,
     'substate': self._determine_substate(best_phase[0], features, text)
        }

    def _extract_features(self, screenshot: np.ndarray) -> Dict[str, Any]:
        """Extract visual features from screenshot"""
        features = {}

        # HP bar detection
        features['hp_bars'] = self._detect_hp_bars(screenshot)
   features['hp_bar_count'] = len(features['hp_bars'])

        # Color analysis
        features['color_histogram'] = self._analyze_colors(screenshot)

  # Edge detection for sprites
        features['sprite_edges'] = self._detect_sprites(screenshot)

        # Text region detection
        features['text_boxes'] = self._detect_text_regions(screenshot)

     # UI element detection
        features['menu_grid'] = self._detect_menu_grid(screenshot)
        features['dialog_box'] = self._detect_dialog_box(screenshot)

        return features

    def _compare_to_template(self, features: Dict, text: str, template: Dict) -> float:
        """Compare features to phase template"""
        score = 0.0
        total_checks = 0

        # Check required features
   for feature, required in template.get('required_features', {}).items():
       if feature in features:
    actual = features[feature]
         if actual == required:
         score += 1.0
         total_checks += 1

        # Check text patterns
        for pattern in template.get('text_patterns', []):
            if pattern in text:
          score += 1.0
         total_checks += 1

        # Check color patterns
        for color, ratio in template.get('color_ratios', {}).items():
     actual_ratio = features['color_histogram'].get(color, 0)
       if abs(actual_ratio - ratio) < 0.1:  # Within 10%
   score += 1.0
      total_checks += 1

   return score / max(total_checks, 1)  # Normalize to 0-1

    def _determine_substate(self, phase: str, features: Dict, text: str) -> str:
   """Determine substate within phase"""
        substate_detectors = {
            'battle': self._get_battle_substate,
            'overworld': self._get_overworld_substate,
            'dialog': self._get_dialog_substate,
   'menu': self._get_menu_substate
        }

        detector = substate_detectors.get(phase)
        if detector:
     return detector(features, text)
        return f"{phase}_generic"

    def _get_battle_substate(self, features: Dict, text: str) -> str:
        """Get battle-specific substate"""
   if 'FIGHT/BAG/POKéMON/RUN' in text:
    return 'menu'
        elif 'Gained' in text and 'EXP' in text:
            return 'experience'
        elif any(word in text for word in ['wild', 'appeared', 'Go']):
    return 'start'
     elif 'fainted' in text.lower():
       return 'faint'
        elif features.get('hp_bars_animating'):
   return 'animation'
        else:
     return 'active'

   def _get_overworld_substate(self, features: Dict, text: str) -> str:
        """Get overworld-specific substate"""
        if features.get('grass_tiles'):
            return 'grass'
        elif features.get('cave_tiles'):
     return 'cave'
        elif features.get('building_entrance'):
      return 'near_building'
        elif features.get('npc_nearby'):
     return 'near_npc'
        else:
            return 'path'

    def _detect_hp_bars(self, screenshot: np.ndarray) -> list:
     """Detect HP bars in screenshot"""
  hsv = cv2.cvtColor(screenshot, cv2.COLOR_RGB2HSV)

        # Red HP bars (low health)
     red_lower = np.array([0, 100, 100])
        red_upper = np.array([10, 255, 255])
        red_mask = cv2.inRange(hsv, red_lower, red_upper)

        # Yellow HP bars (medium health)
   yellow_lower = np.array([20, 100, 100])
        yellow_upper = np.array([40, 255, 255])
        yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)

        # Green HP bars (high health)
        green_lower = np.array([40, 100, 100])
        green_upper = np.array([80, 255, 255])
    green_mask = cv2.inRange(hsv, green_lower, green_upper)

        # Find contours
        combined_mask = red_mask | yellow_mask | green_mask
        contours, _ = cv2.findContours(
            combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        hp_bars = []
        for contour in contours:
       x, y, w, h = cv2.boundingRect(contour)
          if w > 10 and h > 2:  # Reasonable HP bar size
    hp_bars.append({
                    'x': x, 'y': y, 'width': w, 'height': h,
              'color': self._get_dominant_color(screenshot, x, y, w, h)
     })

   return hp_bars
```

**3. Prompt Router** (`src/core/prompt_router.py`):
```python
from pathlib import Path
from typing import Dict, Any, Optional
import json

class PromptRouter:
    """
    Route to appropriate prompt based on game state
    """

    def __init__(self, prompts_dir: str = "./prompts"):
        self.prompts_dir = Path(prompts_dir)
        self.prompt_cache = {}
        self.load_all_prompts()

    def load_all_prompts(self):
        """Load all prompt templates"""
        prompt_files = list(self.prompts_dir.rglob("*.txt"))
        print(f"📜 Loading {len(prompt_files)} prompt templates")

    self.prompts = {}
        for prompt_file in prompt_files:
            # Get relative path without extension
   category = prompt_file.parent.name
 name = prompt_file.stem

            # Read prompt content
            with open(prompt_file, 'r') as f:
   content = f.read()

    # Store in nested dict
            if category not in self.prompts:
        self.prompts[category] = {}
        self.prompts[category][name] = {
        'content': content,
   'path': str(prompt_file),
     'metadata': self._extract_metadata(content)
      }

     print(f"✅ Loaded {len(self.prompts)} prompt categories")

    def get_prompt(self, game_state: Dict, memory: Dict) -> str:
        """Get appropriate prompt for current state"""
        phase = game_state.get('phase', 'unknown')
     substate = game_state.get('substate', 'generic')

        # Build prompt lookup path
   prompt_candidates = self._get_prompt_candidates(phase, substate, memory)

        # Score candidates based on relevance
  scored = []
      for candidate in prompt_candidates:
   score = self._score_prompt(candidate, game_state, memory)
     scored.append((candidate, score))

        # Return best prompt
  scored.sort(key=lambda x: x[1], reverse=True)
        best_prompt = scored[0][0]

        # Fill template with context
    filled_prompt = self._fill_template(best_prompt, game_state, memory)

     return filled_prompt

    def _get_prompt_candidates(self, phase: str, substate: str, memory: Dict) -> list:
   """Get candidate prompts for phase/substate"""
        candidates = []

   # Specific prompt for exact match
    if phase in self.prompts and substate in self.prompts[phase]:
     candidates.append(self.prompts[phase][substate])

        # Generic prompt for phase
        if phase in self.prompts and 'generic' in self.prompts[phase]:
   candidates.append(self.prompts[phase]['generic'])

        # Fallback to error/unknown
        if 'error' in self.prompts and 'unknown_screen' in self.prompts['error']:
  candidates.append(self.prompts['error']['unknown_screen'])

        return candidates

  def _score_prompt(self, prompt: Dict, game_state: Dict, memory: Dict) -> float:
        """Score prompt relevance to current state"""
    score = 0.5  # Base score

        # Check if prompt has required placeholders filled
    placeholders = self._extract_placeholders(prompt['content'])
   for placeholder in placeholders:
      if self._can_fill_placeholder(placeholder, game_state, memory):
      score += 0.1

        # Check if prompt category matches current phase
        if game_state.get('phase') in prompt['path']:
            score += 0.3

        return min(score, 1.0)  # Cap at 1.0

    def _fill_template(self, prompt_template: Dict, game_state: Dict, memory: Dict) -> str:
        """Fill prompt template with contextual data"""
        template = prompt_template['content']

        # Extract placeholders like {player_hp}
        placeholders = self._extract_placeholders(template)

     # Fill each placeholder
        for placeholder in placeholders:
       value = self._get_contextual_value(placeholder, game_state, memory)
         if value is not None:
  template = template.replace(f"{{{placeholder}}}", str(value))
            else:
      # Keep placeholder if can't fill
                pass

        return template

    def _extract_placeholders(self, template: str) -> list:
 """Extract all {placeholder} names from template"""
        import re
        return re.findall(r'\{([^}]+)\}', template)

    def _get_contextual_value(self, placeholder: str, game_state: Dict, memory: Dict) -> Optional[str]:
        """Get value for placeholder from game state or memory"""
        # Try game_state first
  if placeholder in game_state:
       return str(game_state[placeholder])

   # Try memory tiers
        for tier in ['tactician', 'strategist', 'observer']:
   if tier in memory and placeholder in memory[tier]:
       return str(memory[tier][placeholder])

        # Try nested paths (e.g., "player.hp")
        if '.' in placeholder:
            parts = placeholder.split('.')
       value = self._get_nested_value(parts, game_state) or \
         self._get_nested_value(parts, memory)
     if value is not None:
    return str(value)

        # Default placeholders
    defaults = {
        'current_location': 'Unknown',
            'tick': '0',
            'timestamp': 'Unknown',
     'player_name': 'Red'
 }
        return defaults.get(placeholder)

    def _get_nested_value(self, path: list, data: Dict):
        """Get nested dict value by path like ['player', 'hp']"""
 value = data
        for key in path:
       if isinstance(value, dict) and key in value:
        value = value[key]
            else:
        return None
        return value
```

---

This comprehensive specification provides the foundation for building a production-ready AI Pokemon system with complete phase coverage, robust logging, and intelligent memory management.
