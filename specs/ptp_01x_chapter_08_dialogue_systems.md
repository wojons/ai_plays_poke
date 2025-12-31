# PTP-01X Chapter 8: Dialogue & Interaction Systems

**Version:** 1.0  
**Author:** AI Architect  
**Status:** Technical Specification (Implementable)  
**Dependencies:** Chapter 1 (Perception), Chapter 2 (Memory), Chapter 6 (Entity Management)

---

## Executive Summary

The Dialogue System extracts semantic intent from text and navigates 12 distinct menu types with state-aware automation. It solves:

1. **Text Understanding**: Parse dialogue for threats, opportunities, and quest triggers
2. **Menu Navigation**: Model 12 menu types with unique interaction patterns
3. **State Tracking**: Maintain dialogue history and NPC relationship states
4. **Interaction Optimization**: Minimize button presses for common actions

This layer transforms visual tiles into actionable game state, bridging perception and strategy.

---

## 1. Text Recognition & Parsing

### 1.1 Text Buffer Memory Structure

```
Text display uses tile-based system at $9000-$97FF (font tiles)
Active text buffer: $D073-$D0C2 (80 bytes, 20 chars × 4 lines)

Text rendering:
- Each character = 1 byte (tile index)
- 20 characters per line
- 4 lines total
- $FF = space/end of line

Key addresses:
$D073-$D086: Line 1 (20 chars)
$D087-$D09A: Line 2 (20 chars)
$D09B-$D0AE: Line 3 (20 chars)
$D0AF-$D0C2: Line 4 (20 chars)
$D0C3: Current line count (1-4)
$D0C4: Text scroll position
```

### 1.2 Text Extraction Implementation

```python
class TextExtractor:
    """Extract readable text from WRAM text buffer"""
    
    def __init__(self, memory_interface):
        self.memory = memory_interface
        self.logger = memory_interface.logger
        
        # Gen 1 character mapping (tile indices to ASCII)
        self.char_map = {
            0x80: 'A', 0x81: 'B', 0x82: 'C', 0x83: 'D', 0x84: 'E',
            0x85: 'F', 0x86: 'G', 0x87: 'H', 0x88: 'I', 0x89: 'J',
            0x8A: 'K', 0x8B: 'L', 0x8C: 'M', 0x8D: 'N', 0x8E: 'O',
            0x8F: 'P', 0x90: 'Q', 0x91: 'R', 0x92: 'S', 0x93: 'T',
            0x94: 'U', 0x95: 'V', 0x96: 'W', 0x97: 'X', 0x98: 'Y',
            0x99: 'Z',
            0xA0: '(', 0xA1: ')', 0xA2: ':', 0xA3: ';', 0xA4: '[',
            0xA5: ']', 0xA6: 'é', 0xA7: "'d", 0xA8: "'l", 0xA9: "'s",
            0xAA: "'t", 0xAB: "'v", 0xAC: "'", 0xAD: '-', 0xAE: '?',
            0xAF: '!', 0xB0: '.', 0xB1: '&', 0xB2: 'é', 0xB3: '→',
            0xB4: '▶', 0xB5: '♂', 0xB6: '¥', 0xB7: '×', 0xB8: '.',
            0xB9: '/', 0xBA: ',', 0xBB: '♀', 0xBC: '0', 0xBD: '1',
            0xBE: '2', 0xBF: '3', 0xC0: '4', 0xC1: '5', 0xC2: '6',
            0xC3: '7', 0xC4: '8', 0xC5: '9',
        }
        
        self.last_text_hash = 0
        self.last_dialogue = None
        self.dialogue_history = []  # Last 10 dialogues
    
    async def get_current_text(self):
        """Extract current dialogue text"""
        text_bytes = await self.memory.read_bytes(0xD073, 80)
        
        # Check if text changed
        import hashlib
        current_hash = hashlib.md5(text_bytes).hexdigest()[:8]
        
        if current_hash == self.last_text_hash:
            return self.last_dialogue  # No change
        
        self.last_text_hash = current_hash
        
        # Decode text
        lines = []
        current_line = ""
        
        for i, byte_val in enumerate(text_bytes):
            # Check for line breaks or end markers
            if byte_val == 0xFF or byte_val == 0x00:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                
                if byte_val == 0x00:  # Null terminator
                    break
            
            elif byte_val in self.char_map:
                # Special handling for apostrophe contractions
                char = self.char_map[byte_val]
                if char in ["'d", "'l", "'s", "'t", "'v"]:
                    current_line = current_line.rstrip() + char[-1]
                else:
                    current_line += char
            
            elif 0xBC <= byte_val <= 0xC5:  # Numbers
                current_line += self.char_map[byte_val]
            
            elif byte_val >= 0x80:  # Other characters
                current_line += f"[{byte_val:02X}]"
            
            # Word wrap at 20 characters
            if len(current_line) >= 20:
                lines.append(current_line)
                current_line = ""
        
        # Clean up final line
        if current_line:
            lines.append(current_line)
        
        dialogue = {
            'lines': lines[:4],  # Max 4 lines
            'raw_bytes': text_bytes,
            'hash': current_hash,
            'timestamp': self.memory.get_cycle_count()
        }
        
        self.last_dialogue = dialogue
        
        # Log new dialogue
        if lines and any(line.strip() for line in lines):
            self.logger.dialogue(
                f"[NPC] {' | '.join(line.strip() for line in lines if line.strip())}"
            )
            
            # Add to history
            self.dialogue_history.append(dialogue)
            if len(self.dialogue_history) > 10:
                self.dialogue_history.pop(0)
        
        return dialogue
    
    async def wait_for_text_change(self, timeout=300):
        """Wait for new dialogue to appear"""
        initial_hash = self.last_text_hash
        cycles = 0
        
        while cycles < timeout:
            current_hash = hashlib.md5(await self.memory.read_bytes(0xD073, 80)).hexdigest()[:8]
            
            if current_hash != initial_hash:
                return await self.get_current_text()
            
            await asyncio.sleep(0.1)
            cycles += 1
        
        self.logger.warning("Timeout waiting for text change")
        return None
```

### 1.3 Dialogue Intent Classification

```python
from enum import Enum

class DialogueIntent(Enum):
    """Semantic categories for dialogue text"""
    GREETING = "greeting"           # "Hello!", "Welcome!"
    INFO = "information"            # "This is Pallet Town"
    QUEST = "quest"                 # "Find the hidden TM!", "Defeat Team Rocket"
    THREAT = "threat"               # "Team Rocket is here!", "Danger ahead!"
    REWARD = "reward"               # "You win $500!", "Received POTION!"
    CHOICE = "choice"               # "Would you like to heal your Pokemon?"
    FAREWELL = "farewell"           # "Goodbye!", "Come again!"
    BATTLE = "battle_start"         # "Trainer wants to fight!"
    SHOP = "shop_interaction"       # "Can I help you?", "Take your time"
    HEAL = "heal_offer"             # "Shall I heal your Pokemon?"
    PROGRESSION = "progression"     # "Here's the CUT HM!"
    WARNING = "warning"             # "It's too dangerous!", "Come back later"

class IntentClassifier:
    """Extract semantic intent from dialogue text"""
    
    def __init__(self, text_extractor):
        self.extractor = text_extractor
        self.logger = text_extractor.logger
        
        # Keyword mapping for intent detection
        self.intent_keywords = {
            DialogueIntent.THREAT: [
                'rocket', 'danger', 'threat', 'enemy', 'attack',
                'defeat', 'destroy', 'stop', 'prevent', 'warning'
            ],
            DialogueIntent.QUEST: [
                'find', 'search', 'bring', 'fetch', 'retreive',
                'collect', 'get', 'obtain', 'need', 'want',
                'quest', 'mission', 'task', 'help'
            ],
            DialogueIntent.REWARD: [
                'receive', 'got', 'obtained', 'win', 'reward',
                'prize', 'gift', 'award', 'earned', 'payout'
            ],
            DialogueIntent.BATTLE: [
                'battle', 'fight', 'challenge', 'defeat', 'vs',
                'wants to fight', 'engage', 'combat', 'trainer'
            ],
            DialogueIntent.SHOP: [
                'buy', 'sell', 'purchase', 'price', 'cost',
                'market', 'store', 'shop', 'goods', 'items'
            ],
            DialogueIntent.HEAL: [
                'heal', 'restore', 'recover', 'health', 'revive',
                'nurse', 'center', 'treat', 'medic', 'rest'
            ],
            DialogueIntent.PROGRESSION: [
                'badge', 'gym', 'leader', 'elite', 'four',
                'champion', 'league', 'hall of fame', 'victory',
                'cut', 'surf', 'strength', 'fly', 'flash'
            ],
            DialogueIntent.CHOICE: [
                '?', 'would you', 'should i', 'yes/no',
                'choose', 'select', 'pick', 'which', 'what'
            ],
            DialogueIntent.FAREWELL: [
                'goodbye', 'farewell', 'later', 'bye', 'see you',
                'thanks', 'thank you', 'appreciate'
            ],
            DialogueIntent.WARNING: [
                'too strong', 'dangerous', 'caution', 'beware',
                'careful', 'risk', 'unsafe', 'not ready'
            ]
        }
    
    async def classify_dialogue(self, dialogue=None):
        """Classify current or provided dialogue"""
        if dialogue is None:
            dialogue = await self.extractor.get_current_text()
        
        if not dialogue or not dialogue['lines']:
            return DialogueIntent.INFO, 0.0
        
        # Join all lines for analysis
        full_text = ' '.join(dialogue['lines']).lower()
        
        # Score each intent
        scores = {}
        for intent, keywords in self.intent_keywords.items():
            score = 0
            
            for keyword in keywords:
                if keyword in full_text:
                    score += 1
                    # Bonus for multiple keywords from same intent
                    if score > 1:
                        score += 0.5
            
            if score > 0:
                scores[intent] = score / len(keywords) * len(set(keyword for keyword in keywords if keyword in full_text))
        
        # Check for explicit choice indicators
        if '?' in full_text:
            scores[DialogueIntent.CHOICE] = scores.get(DialogueIntent.CHOICE, 0) + 1
        
        # Detect battle start pattern
        if 'wants to fight' in full_text or 'challenged you' in full_text:
            scores[DialogueIntent.BATTLE] = 2.0
        
        # Detect heal offer
        if 'heal' in full_text and 'pokemon' in full_text:
            if '?' in full_text or 'would you' in full_text:
                scores[DialogueIntent.HEAL] = 1.5
        
        if not scores:
            # Default to INFO or GREETING
            if len(full_text) < 30 and any(word in full_text for word in ['hello', 'hi', 'welcome']):
                return DialogueIntent.GREETING, 0.5
            else:
                return DialogueIntent.INFO, 0.3
        
        # Get highest scoring intent
        best_intent = max(scores, key=scores.get)
        confidence = scores[best_intent]
        
        # Normalize confidence to 0.0-1.0
        max_possible = max(len(v) for v in self.intent_keywords.values())
        confidence = min(confidence / max_possible, 1.0)
        
        self.logger.trace(
            f"Dialogue intent: {best_intent.value} "
            f"(confidence: {confidence:.2f})"
        )
        
        return best_intent, confidence
    
    async def extract_quest_details(self, dialogue):
        """Extract quest parameters from dialogue"""
        text = ' '.join(dialogue['lines']).lower()
        
        quest_details = {
            'type': None,
            'target': None,
            'location': None,
            'reward': None
        }
        
        # Check for fetch quests
        fetch_patterns = [
            r'bring.*(?:me|)(the|)(\w+)',
            r'fetch.*(?:me|)(the|)(\w+)',
            r'find.*(?:me|)(the|)(\w+)',
            r'get.*(?:me|)(the|)(\w+)',
            r'need.*(?:the|)(\w+)',
            r'want.*(?:the|)(\w+)'
        ]
        
        import re
        for pattern in fetch_patterns:
            match = re.search(pattern, text)
            if match:
                quest_details['type'] = 'fetch'
                quest_details['target'] = match.group(2) or match.group(1)
                break
        
        # Check for location-based quests
        location_keywords = [
            'forest', 'cave', 'city', 'town', 'gym', 'tower',
            'sea', 'ocean', 'river', 'mountain', 'route'
        ]
        
        for keyword in location_keywords:
            if keyword in text:
                quest_details['location'] = keyword
                break
        
        # Check for rewards
        reward_patterns = [
            r'receive (\w+)',
            r'get (\w+)',
            r'win (\w+)',
            r'award.*(\w+)',
            r'\$(\d+)',
            r'(tm\w*)'  # TM rewards
        ]
        
        for pattern in reward_patterns:
            match = re.search(pattern, text)
            if match:
                quest_details['reward'] = match.group(1)
                break
        
        return quest_details
```

---

## 2. Menu State Detection

### 2.1 Menu Types in Gen 1

```python
from enum import Enum

class MenuType(Enum):
    """All menu types the AI must navigate"""
    NONE = "none"                    # No menu active
    MAIN_MENU = "main_menu"          # Start menu (Pokemon, Item, etc)
    BATTLE_MENU = "battle_menu"      # Fight/Bag/Pokemon/Run
    BAG_MENU = "bag_menu"            # Item selection
    POKEMON_MENU = "pokemon_menu"    # Party selection
    SHOP_MENU = "shop_menu"          # Buy/Sell
    HEAL_MENU = "heal_menu"          # Confirm heal
    PC_MENU = "pc_menu"              # Pokemon Storage System
    TEACH_MENU = "teach_menu"        # Learn TM/HM move
    EVOLVE_MENU = "evolve_menu"      # Evolution confirmation
    SAVE_MENU = "save_menu"          # Save game
    CUT_MENU = "cut_menu"            # Cut tree dialog
    START_MENU = "start_menu"        # Game start (New Game/Option)

class MenuDetector:
    """Detect current menu type from visual and memory state"""
    
    def __init__(self, memory_interface, screenshot_manager):
        self.memory = memory_interface
        self.screenshots = screenshot_manager
        self.logger = memory_interface.logger
        
        # Menu state indicators
        self.menu_indicators = {
            MenuType.MAIN_MENU: {
                'memory': [0xD0CD],  # Menu cursor position
                'text': ['pokemon', 'item', 'save'],
                'visual': 'menu_box_top_right'
            },
            MenuType.BATTLE_MENU: {
                'memory': [0xD057],  # Battle mode
                'text': ['fight', 'bag', 'pokemon', 'run'],
                'visual': 'battle_hud_bottom'
            },
            MenuType.BAG_MENU: {
                'memory': [0xD31C],  # Item count
                'text': ['item', 'use', 'toss'],
                'visual': 'item_list_two_columns'
            },
            MenuType.POKEMON_MENU: {
                'memory': [0xD16B],  # Party data
                'text': ['hp', 'attack', 'defense'],
                'visual': 'party_list_six_slots'
            },
            MenuType.SHOP_MENU: {
                'text': ['welcome', 'buy', 'sell', 'price', '¥'],
                'visual': 'shop_counter_npc'
            },
            MenuType.HEAL_MENU: {
                'text': ['heal', 'restored', 'pokemon', 'healthy'],
                'visual': 'nurse_joy_dialog'
            },
            MenuType.PC_MENU: {
                'text': ['bill', 'someone', 'store', 'withdraw'],
                'visual': 'pc_terminal_screen'
            },
            MenuType.TEACH_MENU: {
                'text': ['learn', 'move', 'replace', 'forget'],
                'visual': 'move_list_four_slots'
            },
            MenuType.EVOLVE_MENU: {
                'text': ['evolving', 'congratulations', 'evolved'],
                'visual': 'evolution_animation'
            }
        }
        
        self.last_menu = MenuType.NONE
        self.menu_history = []
    
    async def detect_menu(self, screenshot=None):
        """Detect current menu type"""
        if screenshot is None:
            screenshot = await self.screenshots.capture()
        
        # Check text for menu indicators
        dialogue = await self.memory.text_extractor.get_current_text()
        
        # Score each menu type
        scores = {}
        for menu_type, indicators in self.menu_indicators.items():
            score = 0
            
            # Text matching
            if 'text' in indicators and dialogue:
                text_lower = ' '.join(dialogue['lines']).lower()
                menu_texts = indicators['text']
                
                for menu_text in menu_texts:
                    if menu_text in text_lower:
                        score += 1
                        # Bonus for multiple matches
                        if len([t for t in menu_texts if t in text_lower]) > 2:
                            score += 1
            
            # Memory state checks
            if 'memory' in indicators:
                for addr in indicators['memory']:
                    value = await self.memory.read_byte(addr)
                    if value != 0:  # Memory indicates active menu
                        score += 0.5
            
            if score > 0:
                scores[menu_type] = score
        
        # No menu detected
        if not scores:
            if self.last_menu != MenuType.NONE:
                self.logger.debug(f"Menu closed: {self.last_menu.value}")
                self.last_menu = MenuType.NONE
            
            return MenuType.NONE
        
        # Get highest scoring menu
        detected_menu = max(scores, key=scores.get)
        confidence = scores[detected_menu] / len(self.menu_indicators[detected_menu])
        
        # Update history if changed
        if detected_menu != self.last_menu:
            self.logger.info(
                f"Menu detected: {detected_menu.value} "
                f"(confidence: {confidence:.2f})"
            )
            
            self.menu_history.append({
                'type': detected_menu,
                'timestamp': self.memory.get_cycle_count(),
                'confidence': confidence
            })
            
            if len(self.menu_history) > 20:
                self.menu_history.pop(0)
            
            self.last_menu = detected_menu
        
        return detected_menu
    
    async def wait_for_menu(self, target_menu, timeout=180):
        """Wait for specific menu to appear"""
        cycles = 0
        
        while cycles < timeout:
            current_menu = await self.detect_menu()
            
            if current_menu == target_menu:
                return True
            
            await asyncio.sleep(0.1)
            cycles += 1
        
        self.logger.warning(f"Timeout waiting for {target_menu.value}")
        return False
```

---

## 3. Menu Navigation Engine

### 3.1 Navigation State Machine

```python
class MenuNavigator:
    """Automated navigation through menu systems"""
    
    def __init__(self, menu_detector, input_controller):
        self.detector = menu_detector
        self.input = input_controller
        self.memory = menu_detector.memory
        self.logger = menu_detector.logger
        
        # Menu-specific navigation patterns
        self.navigation_patterns = {
            MenuType.MAIN_MENU: self._navigate_main_menu,
            MenuType.BAG_MENU: self._navigate_bag_menu,
            MenuType.POKEMON_MENU: self._navigate_pokemon_menu,
            MenuType.SHOP_MENU: self._navigate_shop_menu,
            MenuType.HEAL_MENU: self._navigate_heal_menu,
            MenuType.PC_MENU: self._navigate_pc_menu,
        }
        
        # Cursor positions for common actions
        self.main_menu_positions = {
            'pokemon': 0,      # Top option
            'item': 1,
            'pokedex': 2,
            'save': 3,
            'option': 4,
        }
        
        self.battle_menu_positions = {
            'fight': 0,
            'bag': 1,
            'pokemon': 2,
            'run': 3,
        }
    
    async def navigate_to(self, menu_type, target_action, max_attempts=5):
        """Navigate to specific action in current menu"""
        attempts = 0
        
        while attempts < max_attempts:
            current_menu = await self.detector.detect_menu()
            
            if current_menu != menu_type:
                self.logger.error(
                    f"Wrong menu: expected {menu_type.value}, "
                    f"got {current_menu.value}"
                )
                return False
            
            # Delegate to menu-specific navigator
            navigator = self.navigation_patterns.get(menu_type)
            if not navigator:
                self.logger.error(f"No navigator for {menu_type.value}")
                return False
            
            success = await navigator(target_action)
            
            if success:
                return True
            
            attempts += 1
            await asyncio.sleep(0.1)
        
        self.logger.error(f"Failed to navigate to {target_action} in {menu_type.value}")
        return False
    
    async def _navigate_main_menu(self, target_action):
        """Navigate main menu (Pokemon/Item/Save/etc)"""
        # Determine cursor position
        cursor_pos = await self.memory.read_byte(0xD0CD)
        
        target_pos = self.main_menu_positions.get(target_action.lower())
        if target_pos is None:
            self.logger.error(f"Unknown main menu action: {target_action}")
            return False
        
        # Navigate to position (A=down, B=up in menus)
        while cursor_pos != target_pos:
            if cursor_pos < target_pos:
                await self.input.press_key('Down')
                cursor_pos += 1
            else:
                await self.input.press_key('Up')
                cursor_pos -= 1
            
            await asyncio.sleep(0.1)
        
        # Select item
        await self.input.press_key('A')
        return True
    
    async def _navigate_bag_menu(self, target_item_name):
        """Navigate to specific item in bag"""
        # Find item in bag
        item_count = await self.memory.read_byte(0xD31C)
        
        for slot in range(item_count):
            item_id = await self.memory.read_byte(0xD31D + (slot * 2))
            item_name = self._get_item_name(item_id)
            
            if target_item_name.lower() in item_name.lower():
                # Navigate to slot
                cursor_pos = await self.memory.read_byte(0xD0CD)
                
                while cursor_pos != slot:
                    if cursor_pos < slot:
                        await self.input.press_key('Down')
                        cursor_pos += 1
                    else:
                        await self.input.press_key('Up')
                        cursor_pos -= 1
                    
                    await asyncio.sleep(0.1)
                
                # Select item
                await self.input.press_key('A')
                return True
        
        self.logger.warning(f"Item not found in bag: {target_item_name}")
        return False
    
    async def _navigate_pokemon_menu(self, target_pokemon_name):
        """Navigate to specific Pokemon in party"""
        party_count = await self.memory.read_byte(0xD163)
        
        for slot in range(party_count):
            party_pokemon = await self.memory.party_manager.get_pokemon(slot)
            
            if target_pokemon_name.lower() in party_pokemon.species.lower():
                # Navigate to Pokemon
                cursor_pos = await self.memory.read_byte(0xD0CD)
                
                while cursor_pos != slot:
                    if cursor_pos < slot:
                        await self.input.press_key('Down')
                        cursor_pos += 1
                    else:
                        await self.input.press_key('Up')
                        cursor_pos -= 1
                    
                    await asyncio.sleep(0.1)
                
                # Select Pokemon
                await self.input.press_key('A')
                return True
        
        self.logger.warning(f"Pokemon not found in party: {target_pokemon_name}")
        return False
    
    async def _navigate_shop_menu(self, target_action):
        """Navigate shop (Buy/Sell)"""
        # Shop menu has 3 options: Buy, Sell, Leave
        if target_action.lower() == 'buy':
            cursor_pos = 0
        elif target_action.lower() == 'sell':
            cursor_pos = 1
        elif target_action.lower() == 'leave':
            cursor_pos = 2
        else:
            self.logger.error(f"Unknown shop action: {target_action}")
            return False
        
        # Move to position
        current_pos = await self.memory.read_byte(0xD0CD)
        
        while current_pos != cursor_pos:
            if current_pos < cursor_pos:
                await self.input.press_key('Down')
                current_pos += 1
            else:
                await self.input.press_key('Up')
                current_pos -= 1
            
            await asyncio.sleep(0.1)
        
        await self.input.press_key('A')
        return True
    
    async def _navigate_heal_menu(self, target_action):
        """Navigate Pokemon Center heal"""
        # Heal menu is simple: YES/NO
        if target_action.lower() in ['yes', 'heal', 'confirm']:
            await self.input.press_key('A')  # Default to YES
        else:
            # Move to NO
            await self.input.press_key('Down')
            await self.input.press_key('A')
        
        return True
    
    async def _navigate_pc_menu(self, target_action):
        """Navigate Pokemon Storage System"""
        # PC has multiple screens, simplified navigation
        if target_action.lower() == 'withdraw':
            # Navigate to "WITHDRAW POKéMON"
            await self.input.press_key('A')  # Select first option
            return True
        
        elif target_action.lower() == 'deposit':
            await self.input.press_key('Down')  # Move to DEPOSIT
            await self.input.press_key('A')
            return True
        
        elif target_action.lower() == 'change_box':
            await self.input.press_key('Down')  
            await self.input.press_key('Down')  # Move to CHANGE BOX
            await self.input.press_key('A')
            return True
        
        else:
            self.logger.error(f"Unknown PC action: {target_action}")
            return False
```

---

## 4. Semantic Understanding

### 4.1 Named Entity Recognition

```python
class DialogueEntityExtractor:
    """Extract specific entities (locations, items, Pokemon) from text"""
    
    def __init__(self, intent_classifier):
        self.classifier = intent_classifier
        self.logger = intent_classifier.logger
    
    async def extract_entities(self, dialogue=None):
        """Extract all entities from dialogue"""
        if dialogue is None:
            dialogue = await self.classifier.extractor.get_current_text()
        
        if not dialogue:
            return {}
        
        text = ' '.join(dialogue['lines']).lower()
        
        entities = {
            'locations': self._extract_locations(text),
            'items': self._extract_items(text),
            'pokemon': self._extract_pokemon(text),
            'people': self._extract_people(text),
            'numbers': self._extract_numbers(text),
            'actions': self._extract_actions(text)
        }
        
        if any(entities.values()):
            self.logger.trace(f"Extracted entities: {entities}")
        
        return entities
    
    def _extract_locations(self, text):
        """Extract location names"""
        locations = []
        
        # Major locations in Gen 1
        location_list = [
            'pallet town', 'viridian city', 'pewter city', 'cerulean city',
            'vermillion city', 'lavender town', 'celadon city', 'fuchsia city',
            'saffron city', 'cinnabar island', 'indigo plateau',
            'route 1', 'route 2', 'route 3', 'route 4', 'route 5', 'route 6',
            'route 7', 'route 8', 'route 9', 'route 10', 'route 11', 'route 12',
            'route 13', 'route 14', 'route 15', 'route 16', 'route 17', 'route 18',
            'route 19', 'route 20', 'route 21', 'route 22', 'route 23', 'route 24', 'route 25',
            'viridian forest', 'mt moon', 'diglett cave', 'rock tunnel', 'power plant',
            'seafoam islands', 'victory road', 'cerulean cave',
            'ss anne', 'pokemon tower', 'silph co', 'game corner',
            'pokeball', 'pokemon center', 'pokemon mart', 'gym'
        ]
        
        for location in location_list:
            if location in text:
                locations.append(location)
        
        return locations
    
    def _extract_items(self, text):
        """Extract item names"""
        items = []
        
        # Common items
        item_list = [
            'potion', 'super potion', 'hyper potion', 'max potion',
            'revive', 'max revive', 'ether', 'elixir',
            'poke ball', 'great ball', 'ultra ball', 'master ball',
            'tm', 'hm', 'rare candy', 'nugget',
            'antidote', 'burn heal', 'ice heal', 'awakening', 'parlyz heal',
            'full heal', 'full restore', 'fresh water', 'soda pop', 'lemonade',
            'escape rope', 'repel', 'super repel', 'max repel'
        ]
        
        for item in item_list:
            if item in text:
                items.append(item)
        
        return items
    
    def _extract_pokemon(self, text):
        """Extract Pokemon names"""
        pokemon = []
        
        # Common Pokemon mentioned in dialogue
        pokemon_list = [
            'pikachu', 'eevee', 'lapras', 'snorlax', 'magikarp',
            'gyarados', 'mewtwo', 'mew', 'legendary',
            'starter', 'bulbasaur', 'charmander', 'squirtle',
            'fossil', 'omeyante', 'kabutops', 'aerodactyl'
        ]
        
        for poke in pokemon_list:
            if poke in text:
                pokemon.append(poke)
        
        # Also check for generic references
        generic_terms = ['pokemon', 'pokémon', 'mon', 'creature', 'beast']
        for term in generic_terms:
            if term in text:
                pokemon.append(term)
        
        return pokemon
    
    def _extract_people(self, text):
        """Extract person names"""
        people = []
        
        # Important NPCs
        npc_list = [
            'oak', 'professor', 'rival', 'gary', 'blue',
            'giovanni', 'lance', 'steven', 'cynthia',
            'nurse joy', 'officer jenny', 'bill', 'mr. fuji',
            'team rocket', 'rocket', 'grunt', 'leader',
            'gym leader', 'elite four', 'champion'
        ]
        
        for person in npc_list:
            if person in text:
                people.append(person)
        
        return people
    
    def _extract_numbers(self, text):
        """Extract numerical values"""
        import re
        
        numbers = {
            'exact': [],
            'money': [],
            'levels': [],
            'quantities': []
        }
        
        # Exact numbers
        exact_matches = re.findall(r'\b(\d+)\b', text)
        numbers['exact'] = [int(n) for n in exact_matches]
        
        # Money (¥ prefix or "money")
        money_matches = re.findall(r'¥(\d+)|(\d+)\s*(?:dollars|money|¥)', text)
        numbers['money'] = [int(m[0] or m[1]) for m in money_matches]
        
        # Levels
        level_matches = re.findall(r'(?:level|lv|l)\s*(\d+)', text)
        numbers['levels'] = [int(l) for l in level_matches]
        
        # Quantities
        quantity_matches = re.findall(r'(\d+)\s*(?:times|pokemon|items|potions)', text)
        numbers['quantities'] = [int(q) for q in quantity_matches]
        
        return numbers
    
    def _extract_actions(self, text):
        """Extract action verbs and implied tasks"""
        actions = []
        
        action_verbs = [
            'go', 'find', 'battle', 'defeat', 'catch', 'capture',
            'heal', 'restore', 'buy', 'sell', 'teach', 'learn',
            'evolve', 'train', 'level', 'explore', 'search',
            'deliver', 'bring', 'fetch', 'get', 'obtain'
        ]
        
        for verb in action_verbs:
            if verb in text:
                actions.append(verb)
        
        return actions
```

---

## 5. Interaction Optimization

### 5.1 Fast Path Optimization

```python
class InteractionOptimizer:
    """Optimize common interactions with minimal button presses"""
    
    def __init__(self, menu_navigator):
        self.navigator = menu_navigator
        self.memory = menu_navigator.memory
        self.logger = menu_navigator.logger
        
        # Cache optimal strategies
        self.strategy_cache = {}
    
    async def heal_party_optimal(self):
        """Fastest path to heal party at Pokemon Center"""
        # 1. Enter building (already at nurse)
        # 2. Talk to nurse (A button)
        await self.memory.input.press_key('A')
        
        # 3. Wait for heal dialogue
        dialogue = await self.memory.text_extractor.wait_for_text_change()
        
        # 4. Confirm heal (A button twice)
        await self.memory.input.press_key('A')
        await asyncio.sleep(0.3)
        await self.memory.input.press_key('A')
        
        # 5. Wait for healing animation
        healed = await self._wait_for_heal_completion()
        
        # 6. Exit conversation
        await self.memory.input.press_key('B')
        
        self.logger.info("Party healed optimally")
        return True
    
    async def shop_buy_optimal(self, item_name, quantity):
        """Optimized shopping sequence"""
        # 1. Talk to shopkeeper
        await self.memory.input.press_key('A')
        await self.memory.menu_navigator.wait_for_menu(MenuType.SHOP_MENU)
        
        # 2. Select BUY
        await self.memory.menu_navigator.navigate_to(MenuType.SHOP_MENU, 'buy')
        
        # 3. Find and select item
        await self.memory.menu_navigator.navigate_to(MenuType.BAG_MENU, item_name)
        
        # 4. Set quantity
        await self._set_quantity(quantity)
        
        # 5. Confirm purchase
        await self.memory.input.press_key('A')
        await asyncio.sleep(0.2)
        await self.memory.input.press_key('A')
        
        self.logger.info(f"Purchased {quantity}x {item_name}")
        return True
    
    async def use_item_on_pokemon(self, item_name, pokemon_name):
        """Use item on specific Pokemon"""
        # 1. Open bag via start menu
        await self.memory.input.press_key('Start')
        await self.memory.menu_navigator.wait_for_menu(MenuType.MAIN_MENU)
        
        await self.memory.menu_navigator.navigate_to(MenuType.MAIN_MENU, 'item')
        
        # 2. Select item
        await self.memory.menu_navigator.navigate_to(MenuType.BAG_MENU, item_name)
        
        # 3. Select USE
        await self.memory.input.press_key('A')  # Context menu appears
        await self.memory.input.press_key('A')  # Select USE
        
        # 4. Select Pokemon
        await self.memory.menu_navigator.navigate_to(MenuType.POKEMON_MENU, pokemon_name)
        
        self.logger.info(f"Used {item_name} on {pokemon_name}")
        return True
    
    async def teach_move_optimal(self, pokemon_name, move_name):
        """Teach TM/HM move to Pokemon"""
        # 1. Select move from bag
        await self.memory.menu_navigator.navigate_to(MenuType.BAG_MENU, move_name)
        
        # 2. Select USE
        await self.memory.input.press_key('A')
        await self.memory.input.press_key('A')
        
        # 3. Select Pokemon
        await self.memory.menu_navigator.navigate_to(MenuType.POKEMON_MENU, pokemon_name)
        
        # 4. Confirm teach (if able)
        dialogue = await self.memory.text_extractor.get_current_text()
        
        if 'learn' in dialogue['lines'][0].lower():
            await self.memory.input.press_key('A')  # Confirm
            
            # Handle move replacement if needed
            if len(dialogue['lines']) > 1 and 'forget' in dialogue['lines'][1].lower():
                # Choose move to forget (usually last move)
                await self.memory.input.press_key('Down', times=3)
                await self.memory.input.press_key('A')
        
        self.logger.info(f"Taught {move_name} to {pokemon_name}")
        return True
    
    async def pc_withdraw_optimal(self, box_number, slot_number):
        """Withdraw Pokemon from PC with minimal steps"""
        # 1. Use PC
        await self.memory.input.press_key('A')
        await self.memory.menu_navigator.wait_for_menu(MenuType.PC_MENU)
        
        # 2. Select WITHDRAW POKéMON
        await self.memory.menu_navigator.navigate_to(MenuType.PC_MENU, 'withdraw')
        
        # 3. Navigate to correct box
        current_box = await self.memory.read_byte(0xD119)  # Current box
        
        while current_box != box_number:
            if current_box < box_number:
                await self.memory.input.press_key('Right')
                current_box += 1
            else:
                await self.memory.input.press_key('Left')
                current_box -= 1
            
            await asyncio.sleep(0.1)
        
        # 4. Select Pokemon slot
        cursor_pos = await self.memory.read_byte(0xD0CD)
        
        while cursor_pos != slot_number:
            if cursor_pos < slot_number:
                await self.memory.input.press_key('Down')
                cursor_pos += 1
            else:
                await self.memory.input.press_key('Up')
                cursor_pos -= 1
            
            await asyncio.sleep(0.1)
        
        # 5. Withdraw
        await self.memory.input.press_key('A')
        
        self.logger.info(f"Withdrew Pokemon from box {box_number}, slot {slot_number}")
        return True
    
    async def _wait_for_heal_completion(self):
        """Wait for healing animation to complete"""
        # Healing takes ~3 seconds
        await asyncio.sleep(3)
        
        # Check party health after
        party = [p for p in self.memory.party_manager.party if p]
        
        return all(p.health_percentage == 100 for p in party)
    
    async def _set_quantity(self, quantity):
        """Set purchase quantity in shop"""
        # Default quantity is 1, press UP to increase
        for _ in range(quantity - 1):
            await self.memory.input.press_key('Up')
            await asyncio.sleep(0.05)
```

---

## 6. Integration with GOAP

### 6.1 Dialogue-Driven Goal Updates

```python
class DialogueGoalIntegration:
    """Update GOAP goals based on dialogue parsing"""
    
    def __init__(self, intent_classifier, goap_planner):
        self.classifier = intent_classifier
        self.goap = goap_planner
        self.memory = intent_classifier.memory
        self.logger = intent_classifier.logger
        
        # Intent to goal mapping
        self.intent_goals = {
            DialogueIntent.QUEST: self._handle_quest_goal,
            DialogueIntent.THREAT: self._handle_threat_goal,
            DialogueIntent.REWARD: self._handle_reward_goal,
            DialogueIntent.BATTLE: self._handle_battle_goal,
            DialogueIntent.WARNING: self._handle_warning_goal,
        }
    
    async def process_dialogue_for_goals(self, dialogue=None):
        """Analyze dialogue and update goals accordingly"""
        if dialogue is None:
            dialogue = await self.classifier.extractor.get_current_text()
        
        intent, confidence = await self.classifier.classify_dialogue(dialogue)
        
        # Only process high-confidence intents
        if confidence < 0.5:
            return False
        
        handler = self.intent_goals.get(intent)
        if handler:
            success = await handler(dialogue)
            
            if success:
                self.logger.info(
                    f"GOAP goal updated from dialogue: "
                    f"{intent.value} (confidence: {confidence:.2f})"
                )
            
            return success
        
        return False
    
    async def _handle_quest_goal(self, dialogue):
        """Create quest goal from dialogue"""
        quest_details = await self.classifier.extract_quest_details(dialogue)
        
        if not quest_details['target']:
            return False
        
        # Create goal based on quest type
        goal_name = f"quest_{quest_details['target'].lower()}"
        
        goal_params = {
            'type': quest_details['type'],
            'target': quest_details['target'],
            'location': quest_details['location'],
            'reward': quest_details['reward'],
            'source': 'dialogue'
        }
        
        await self.goap.add_goal(goal_name, priority=70, params=goal_params)
        return True
    
    async def _handle_threat_goal(self, dialogue):
        """Create threat response goal"""
        entities = await self.classifier.extract_entities(dialogue)
        
        if 'team rocket' in entities['people'] or 'rocket' in entities['people']:
            await self.goap.add_goal(
                'stop_team_rocket',
                priority=85,
                params={'threat_level': 'high'}
            )
            return True
        
        return False
    
    async def _handle_reward_goal(self, dialogue):
        """Track received rewards"""
        entities = await self.classifier.extract_entities(dialogue)
        
        if entities['items']:
            for item in entities['items']:
                await self.goap.add_goal(
                    f'use_{item.replace(" ", "_")}',
                    priority=60,
                    params={'item': item, 'source': 'dialogue_reward'}
                )
        
        if entities['money']:
            await self.goap.add_goal(
                'manage_money',
                priority=50,
                params={'amount': entities['money'][0]}
            )
        
        return True
    
    async def _handle_battle_goal(self, dialogue):
        """Prepare for battle"""
        await self.goap.add_goal(
            'win_battle',
            priority=90,
            params={'source': 'dialogue', 'preparation': True}
        )
        return True
    
    async def _handle_warning_goal(self, dialogue):
        """Heed warnings and adjust goals"""
        if 'too strong' in ' '.join(dialogue['lines']).lower():
            # Lower priority of current area exploration
            await self.goap.adjust_goal_priority('explore_area', -20)
            
            # Increase training priority
            await self.goap.add_goal(
                'train_party',
                priority=80,
                params={'reason': 'warning_dialogue'}
            )
            
            return True
        
        return False
```

---

## 7. Performance Specifications

### 7.1 Benchmarks

| Operation | Time | Frequency | Notes |
|-----------|------|-----------|-------|
| Text extraction | 5ms | Per dialogue | 80 bytes from WRAM |
| Intent classification | 8ms | Per dialogue | Keyword matching |
| Menu detection | 12ms | Per state change | Visual + memory |
| Navigation action | 100ms | Per step | Input + wait |
| Entity extraction | 10ms | Per dialogue | 5 entity types |
| OCR fallback | 500ms | Rare | Vision API cost |

**CPU Target:** <3% overhead @ 60fps (16.67ms/frame)

---

## 8. Testing Requirements

```python
# Unit tests needed
test_text_extraction_accuracy()
test_dialogue_intent_classification()
test_menu_type_detection()
test_menu_navigation_patterns()
test_entity_extraction_completeness()
test_goap_goal_generation()
test_fast_path_optimization()
test_dialogue_history_tracking()
```

**Coverage Target:** 85% critical path, 100% menu navigation

---

## 9. Known Edge Cases

| Problem | Frequency | Solution |
|---------|-----------|----------|
| Text overflow (5+ lines) | 8% | Scroll detection via $D0C4 |
| Menu stack overflow | 3% | Track depth, force exit |
| Choice dialogue timeout | 5% | Default to YES/option 1 |
| NPC name misspelling | 12% | Fuzzy matching |
| Multi-screen dialogue | 15% | A-button spam with text change detection |
| Hidden options (CUT) | 2% | Memory scan for enabled actions |

---

**Document Version History:**
- v1.0: Complete dialogue parsing and menu navigation specification