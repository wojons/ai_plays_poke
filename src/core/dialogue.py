"""
Dialogue & Interaction System for PTP-01X Pokemon AI

Implements comprehensive dialogue parsing and menu navigation:
- DialogParser: Speaker identification, content extraction, type classification
- TextSpeedController: Optimal text speed for AI vs human readability
- MenuNavigator: Option selection, Yes/No dialogs, multiple choice menus
- NPCInteraction: Trainer battle detection, gift/reward extraction, info extraction

Integration:
- HSM: State machine access for dialog state transitions
- Vision: Text extraction via OCR
- GOAP: Dialog-based goals for planning
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime
import time
import logging
import re


logger = logging.getLogger(__name__)


class DialogType(Enum):
    """Types of dialog content"""
    STORY = auto()
    BATTLE = auto()
    TRAINER = auto()
    ITEM = auto()
    INFORMATION = auto()
    GREETING = auto()
    CHOICE = auto()
    SYSTEM = auto()


class SpeakerType(Enum):
    """Speaker identification types"""
    NPC = auto()
    PLAYER = auto()
    SYSTEM = auto()
    TRAINER = auto()
    RIVAL = auto()
    GYM_LEADER = auto()


class DialogIntent(Enum):
    """Intent classification for dialog"""
    GREETING = auto()
    THREAT = auto()
    REWARD = auto()
    CHOICE = auto()
    SHOP = auto()
    HEAL = auto()
    PROGRESSION = auto()
    QUEST = auto()
    INFORMATION = auto()
    BATTLE_CHALLENGE = auto()
    GIFT = auto()


class MenuType(Enum):
    """Types of menus"""
    MAIN_MENU = auto()
    BATTLE_MENU = auto()
    BAG_MENU = auto()
    POKEMON_MENU = auto()
    SHOP_MENU = auto()
    YES_NO = auto()
    CHOICE = auto()
    SAVE_MENU = auto()
    OPTIONS = auto()
    PC_MENU = auto()


class NavigationButton(Enum):
    """Controller buttons for navigation"""
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    A = auto()
    B = auto()
    START = auto()
    SELECT = auto()


@dataclass
class DialogLine:
    """Parsed dialog line"""
    raw_text: str
    clean_text: str
    speaker: Optional[str]
    speaker_type: Optional[SpeakerType]
    intent: Optional[DialogIntent]
    entities: Dict[str, List[str]] = field(default_factory=dict)
    is_choice: bool = False
    is_important: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class DialogEntry:
    """Complete dialog entry with metadata"""
    lines: List[DialogLine]
    dialog_type: DialogType
    primary_intent: DialogIntent
    secondary_intent: Optional[DialogIntent]
    confidence: float
    key_entities: Dict[str, List[str]] = field(default_factory=dict)
    actions_required: List[str] = field(default_factory=list)
    information_extracted: List[str] = field(default_factory=list)
    quest_triggered: Optional[str] = None
    reward_offered: Optional[Dict[str, Any]] = None
    duration_ms: float = 0.0


@dataclass
class MenuOption:
    """Menu option with position and content"""
    index: int
    text: str
    row: int
    col: int
    is_selected: bool = False


@dataclass
class MenuState:
    """Current menu state"""
    menu_type: MenuType
    options: List[MenuOption]
    current_selection: int
    cursor_position: Tuple[int, int]
    is_active: bool = True


@dataclass
class NPCInfo:
    """Information about an NPC"""
    name: str
    role: str
    location: str
    is_trainer: bool = False
    trainer_class: Optional[str] = None
    badge_requirement: Optional[int] = None
    gift_offered: Optional[str] = None
    information: List[str] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    dialogue_history: List[str] = field(default_factory=list)
    relationship_level: int = 0


@dataclass
class InteractionResult:
    """Result of NPC interaction"""
    success: bool
    npc_info: Optional[NPCInfo]
    dialog_entry: Optional[DialogEntry]
    battle_initiated: bool = False
    gift_received: Optional[str] = None
    information_gained: List[str] = field(default_factory=list)
    quest_started: Optional[str] = None
    action_taken: str = ""
    time_spent_ms: float = 0.0


class DialogParser:
    """
    Parser for dialogue text from Pokemon game screens.
    
    Responsibilities:
    - Extract speaker identification
    - Parse content and extract key information
    - Classify dialog types
    - Identify intents and actions
    """

    def __init__(self):
        self._pokemon_names = self._build_pokemon_database()
        self._location_names = self._build_location_database()
        self._item_names = self._build_item_database()
        self._trainer_classes = self._build_trainer_classes()
        self._keyword_patterns = self._build_keyword_patterns()
        self._speaker_patterns = self._build_speaker_patterns()

    def _build_pokemon_database(self) -> Set[str]:
        """Build set of Pokemon names for entity extraction"""
        return {
            "PIKACHU", "CHARIZARD", "BULBASAUR", "SQUIRTLE", "EEVEE",
            "MEWTWO", "MEW", "GENGAR", "DRAGONITE", "SNORLAX",
            "LAPRAS", "ZUBAT", "GEODUDE", "PIDGEY", "RATTATA",
            "SPEAROW", "NIDORAN", "CLEFAIRY", "VULPIX", "JIGGLYPUFF",
            "ZUBAT", "GOLBAT", "ODDISH", "PARAS", "VENONAT",
            "DIGLETT", "MEOWTH", "PSYDUCK", "MANKEY", "GROWLITHE",
            "POLIWAG", "ABRA", "MACHOP", "BELLSPROUT", "TENTACOOL",
            "GEODUDE", "PONYTA", "SLOWPOKE", "MAGNEMITE", "FARFETCHD",
            "DODUO", "SEEL", "GRIMER", "SHELLDER", "ONIX",
            "DROWZEE", "KRABBY", "VOLTORB", "EXEGGCUTE", "CUBONE",
            "HITMONLEE", "HITMONCHAN", "LICKITUNG", "KOFFING", "RHYHORN",
            "CHANSEY", "TANGELA", "KANGASKHAN", "HORSEA", "GOLDEEN",
            "SEAKING", "STARYU", "MRMIME", "SCYTHER", "JYNX",
            "ELECTABUZZ", "MAGMAR", "PINSIR", "TAUROS", "MAGIKARP",
            "GYARADOS", "DITTO", "EEVEE", "VAPOREON", "JOLTEON",
            "FLAREON", "PORYGON", "OMANYTE", "KABUTO", "AERODACTYL",
            "SNORLAX", "DRATINI", "DRAGONAIR", "DRAGONITE", "MEWTWO", "MEW",
        }

    def _build_location_database(self) -> Set[str]:
        """Build set of location names"""
        return {
            "PALLET TOWN", "VIRIDIAN CITY", "PEWTER CITY", "CERULEAN CITY",
            "VERMILION CITY", "CELADON CITY", "FUCHSIA CITY", "CINNABAR ISLAND",
            "SAFFRON CITY", "ROUTE 1", "ROUTE 2", "ROUTE 3", "ROUTE 4",
            "ROUTE 5", "ROUTE 6", "ROUTE 7", "ROUTE 8", "ROUTE 9",
            "ROUTE 10", "ROUTE 11", "ROUTE 12", "ROUTE 13", "ROUTE 14",
            "ROUTE 15", "ROUTE 16", "ROUTE 17", "ROUTE 18", "ROUTE 19",
            "ROUTE 20", "ROUTE 21", "ROUTE 22", "ROUTE 23", "ROUTE 24",
            "ROUTE 25", "VIRIDIAN FOREST", "MT MOON", "ROCK TUNNEL",
            "POWER PLANT", "ROUTE 10", "LAKE OF RAGE", "MART",
            "POKEMON CENTER", "GYM", "CINNABAR LAB", "SAFARI ZONE",
            "VICTORY ROAD", "INDIGO PLATEAU", "UNION CAVE", "ROCKET HIDEOUT",
            "CERULEAN CAVE",
        }

    def _build_item_database(self) -> Set[str]:
        """Build set of item names"""
        return {
            "POKE BALL", "GREAT BALL", "ULTRA BALL", "MASTER BALL",
            "POTION", "SUPER POTION", "HYPER POTION", "MAX POTION",
            "ANTIDOTE", "BURN HEAL", "ICE HEAL", "AWAKENING",
            "PARALYZE HEAL", "FULL RESTORE", "FULL HEAL", "REVIVE",
            "MAX REVIVE", "ESCAPE ROPE", "REPEL", "SUPER REPEL",
            "MAX REPEL", "SAFARI BALL", "MOON STONE", "THUNDER STONE",
            "FIRE STONE", "WATER STONE", "LEAF STONE", "TIN MUSHROOM",
            "BIG MUSHROOM", "PEARL", "BIG PEARL", "STARDUST", "STAR PIECE",
            "NUGGET", "HEART SCALE", "POKEDEX", "RUNNING SHOES", "BICYCLE",
            "HM01", "HM02", "HM03", "HM04", "HM05", "HM06", "HM07", "HM08",
            "TM01", "TM02", "TM03", "TM04", "TM05", "TM06", "TM07", "TM08",
            "TM09", "TM10", "TM11", "TM12", "TM13", "TM14", "TM15", "TM16",
            "TM17", "TM18", "TM19", "TM20", "TM21", "TM22", "TM23", "TM24",
            "TM25", "TM26", "TM27", "TM28", "TM29", "TM30", "TM31", "TM32",
            "TM33", "TM34", "TM35", "TM36", "TM37", "TM38", "TM39", "TM40",
            "TM41", "TM42", "TM43", "TM44", "TM45", "TM46", "TM47", "TM48",
            "TM49", "TM50", "TM", "TMS", "TECHNICAL MACHINE",
        }

    def _build_trainer_classes(self) -> Dict[str, Dict[str, Any]]:
        """Build trainer class information"""
        return {
            "YOUNGSTER": {"aggression": 0.7, "badge_req": 0},
            "LASS": {"aggression": 0.5, "badge_req": 0},
            "BUG CATCHER": {"aggression": 0.4, "badge_req": 0},
            "HIKER": {"aggression": 0.8, "badge_req": 1},
            "YOUNGSTER": {"aggression": 0.7, "badge_req": 0},
            "RIVAL": {"aggression": 0.85, "badge_req": 0},
            "GYM LEADER": {"aggression": 0.9, "badge_req": 0},
            "CHAMPION": {"aggression": 0.95, "badge_req": 8},
            "ROCKET GRUNT": {"aggression": 0.75, "badge_req": 0},
            "ROCKET EXECUTIVE": {"aggression": 0.85, "badge_req": 4},
        }

    def _build_keyword_patterns(self) -> Dict[DialogIntent, List[str]]:
        """Build keyword patterns for intent classification - order matters, later keywords take priority"""
        return {
            DialogIntent.BATTLE_CHALLENGE: ["let's battle", "wanna battle", "i challenge you", "your pokémon", "battle me", "fight me"],
            DialogIntent.GIFT: ["take this", "here, have", "this is for you", "here's a gift", "present for you"],
            DialogIntent.QUEST: ["help me", "please help", "find my", "search for", "request", "favor", "mission", "quest"],
            DialogIntent.SHOP: ["what would you like to buy", "purchase", "how many", "that will be", "that costs"],
            DialogIntent.REWARD: ["you've earned", "congratulations", "you win", "prize", "reward"],
            DialogIntent.HEAL: ["your pokemon have been healed", "feel better", "all healed"],
            DialogIntent.PROGRESSION: ["the path is now open", "next area", "advance", "progress"],
            DialogIntent.THREAT: ["prepare yourself", "you'll never", "you can't", "i'll defeat", "get ready to lose"],
            DialogIntent.CHOICE: ["what would", "do you want", "which one", "choose", "select", "pick"],
            DialogIntent.INFORMATION: ["did you know", "here's a tip", "interesting fact", "story", "history"],
            DialogIntent.GREETING: ["hello", "hi", "welcome", "hey", "good morning", "good afternoon", "good evening"],
        }

    def _build_speaker_patterns(self) -> Dict[SpeakerType, List[str]]:
        """Build patterns for speaker identification"""
        return {
            SpeakerType.NPC: ["NPC", "TRAINER", "PERSON", "GIRL", "BOY", "MAN", "WOMAN"],
            SpeakerType.TRAINER: ["YOUNGSTER", "LASS", "BUG CATCHER", "HIKER", "SWIMMER", "ROCKET GRUNT"],
            SpeakerType.GYM_LEADER: ["BROCK", "MISTY", "LTSURGE", "ERIKA", "KOGA", "BLAINE", "SABRINA", "GIOVANNI"],
            SpeakerType.RIVAL: ["BLUE", "GARY", "RIVAL"],
            SpeakerType.PLAYER: ["ASH", "RED", "PLAYER", "YOU"],
            SpeakerType.SYSTEM: ["GAME", "SYSTEM", "NARRATOR", ""],
        }

    def parse_dialog(self, raw_text: str, context: Optional[Dict[str, Any]] = None) -> DialogEntry:
        """Parse dialog text and extract structured information"""
        start_time = time.time()
        
        lines = self._split_into_lines(raw_text)
        parsed_lines = []
        
        for line in lines:
            if line.strip():
                parsed_line = self._parse_line(line, context)
                parsed_lines.append(parsed_line)
        
        dialog_type = self._classify_dialog_type(parsed_lines)
        primary_intent, secondary_intent, confidence = self._classify_intent(parsed_lines)
        
        key_entities = self._extract_all_entities(parsed_lines)
        actions_required = self._determine_actions(parsed_lines, primary_intent)
        information_extracted = self._extract_information(parsed_lines)
        
        quest_triggered = self._detect_quest(parsed_lines)
        reward_offered = self._detect_reward(parsed_lines)
        
        entry = DialogEntry(
            lines=parsed_lines,
            dialog_type=dialog_type,
            primary_intent=primary_intent,
            secondary_intent=secondary_intent,
            confidence=confidence,
            key_entities=key_entities,
            actions_required=actions_required,
            information_extracted=information_extracted,
            quest_triggered=quest_triggered,
            reward_offered=reward_offered,
            duration_ms=(time.time() - start_time) * 1000
        )
        
        return entry

    def _split_into_lines(self, raw_text: str) -> List[str]:
        """Split text into individual lines"""
        if not raw_text:
            return []
        
        lines = raw_text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        return [line.strip() for line in lines if line.strip()]

    def _parse_line(self, line: str, context: Optional[Dict[str, Any]] = None) -> DialogLine:
        """Parse a single line of dialog"""
        clean_text = self._clean_text(line)
        speaker, speaker_type = self._identify_speaker(clean_text, context)
        intent = self._identify_intent(clean_text)
        entities = self._extract_entities(clean_text)
        is_choice = self._is_choice_line(clean_text)
        is_important = self._is_important_line(clean_text, intent)
        
        return DialogLine(
            raw_text=line,
            clean_text=clean_text,
            speaker=speaker,
            speaker_type=speaker_type,
            intent=intent,
            entities=entities,
            is_choice=is_choice,
            is_important=is_important
        )

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        text = text.replace('?', '').replace('!', '').replace('.', '')
        text = text.upper()
        return text

    def _identify_speaker(self, text: str, context: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[SpeakerType]]:
        """Identify who is speaking"""
        text_upper = text.upper()
        
        for speaker_type, patterns in self._speaker_patterns.items():
            for pattern in patterns:
                if pattern.upper() in text_upper:
                    return pattern, speaker_type
        
        if context:
            if context.get('is_trainer_battle'):
                return context.get('trainer_name'), SpeakerType.TRAINER
            if context.get('location') == 'POKEMON CENTER':
                return "NURSE JOY", SpeakerType.NPC
            if context.get('location') == 'POKEMART':
                return "MR FUJI", SpeakerType.NPC
        
        return None, None

    def _identify_intent(self, text: str) -> Optional[DialogIntent]:
        """Identify the intent of the dialog line - checks more specific intents first"""
        text_lower = text.lower()
        
        for intent, keywords in self._keyword_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return intent
        
        return None

    def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract entities from text"""
        entities = {
            'pokemon': [],
            'locations': [],
            'items': [],
            'actions': [],
            'trainers': [],
        }
        
        text_upper = text.upper()
        text_lower = text.lower()
        
        words = text.split()
        for word in words:
            clean_word = re.sub(r'[^\w]', '', word).upper()
            if clean_word in self._pokemon_names:
                entities['pokemon'].append(clean_word)
            if clean_word in self._location_names:
                entities['locations'].append(clean_word)
            if clean_word in self._item_names:
                entities['items'].append(clean_word)
        
        if "TM" in text_upper:
            tm_match = re.search(r'TM\s*(\d+)', text_upper)
            if tm_match:
                entities['items'].append(f"TM{tm_match.group(1)}")
            else:
                entities['items'].append("TM")
        
        for location in self._location_names:
            if location in text_upper:
                entities['locations'].append(location)
        
        for item in self._item_names:
            if item in text_upper:
                if item not in entities['items']:
                    entities['items'].append(item)
        
        action_keywords = ['battle', 'fight', 'shop', 'buy', 'sell', 'heal', 'catch', 'trade', 'gift']
        for keyword in action_keywords:
            if keyword in text_lower:
                entities['actions'].append(keyword)
        
        return entities

    def _extract_all_entities(self, lines: List[DialogLine]) -> Dict[str, List[str]]:
        """Extract all entities from parsed lines"""
        combined = {
            'pokemon': [],
            'locations': [],
            'items': [],
            'actions': [],
            'trainers': [],
        }
        
        for line in lines:
            for category, values in line.entities.items():
                for value in values:
                    if value not in combined[category]:
                        combined[category].append(value)
        
        return combined

    def _classify_dialog_type(self, lines: List[DialogLine]) -> DialogType:
        """Classify the overall dialog type"""
        intents = [line.intent for line in lines if line.intent]
        
        if DialogIntent.BATTLE_CHALLENGE in intents or DialogIntent.THREAT in intents:
            return DialogType.BATTLE
        if DialogIntent.QUEST in intents or DialogIntent.PROGRESSION in intents:
            return DialogType.STORY
        if DialogIntent.SHOP in intents:
            return DialogType.ITEM
        if DialogIntent.GIFT in intents or DialogIntent.REWARD in intents:
            return DialogType.ITEM
        
        for line in lines:
            if line.speaker_type == SpeakerType.GYM_LEADER:
                return DialogType.TRAINER
            if line.speaker_type == SpeakerType.RIVAL:
                return DialogType.TRAINER
        
        return DialogType.INFORMATION

    def _classify_intent(self, lines: List[DialogLine]) -> Tuple[DialogIntent, Optional[DialogIntent], float]:
        """Classify primary and secondary intents"""
        intent_counts: Dict[DialogIntent, int] = {}
        
        for line in lines:
            if line.intent:
                intent_counts[line.intent] = intent_counts.get(line.intent, 0) + 1
        
        if not intent_counts:
            return DialogIntent.INFORMATION, None, 0.5
        
        sorted_intents = sorted(intent_counts.items(), key=lambda x: x[1], reverse=True)
        primary_intent = sorted_intents[0][0] if sorted_intents else DialogIntent.INFORMATION
        primary_count = sorted_intents[0][1] if sorted_intents else 0
        total_lines = len(lines)
        
        confidence = min(primary_count / total_lines + 0.3, 0.95)
        
        secondary_intent = sorted_intents[1][0] if len(sorted_intents) > 1 else None
        
        return primary_intent, secondary_intent, confidence

    def _determine_actions(self, lines: List[DialogLine], intent: DialogIntent) -> List[str]:
        """Determine required actions based on intent"""
        actions = []
        
        action_map = {
            DialogIntent.GREETING: ["acknowledge", "continue"],
            DialogIntent.THREAT: ["prepare_for_battle", "accept_challenge"],
            DialogIntent.REWARD: ["accept_reward", "thank"],
            DialogIntent.CHOICE: ["make_choice", "select_option"],
            DialogIntent.SHOP: ["enter_shop", "browse_items"],
            DialogIntent.HEAL: ["accept_healing", "wait"],
            DialogIntent.PROGRESSION: ["advance", "explore_new_area"],
            DialogIntent.QUEST: ["accept_quest", "update_objectives"],
            DialogIntent.INFORMATION: ["remember_info", "continue"],
            DialogIntent.BATTLE_CHALLENGE: ["enter_battle", "prepare_team"],
            DialogIntent.GIFT: ["receive_gift", "thank"],
        }
        
        actions = action_map.get(intent, ["continue"])
        return actions

    def _extract_information(self, lines: List[DialogLine]) -> List[str]:
        """Extract useful information from dialog"""
        info = []
        
        for line in lines:
            if line.intent == DialogIntent.INFORMATION:
                info.append(line.clean_text)
            
            for location in line.entities.get('locations', []):
                info.append(f"Location mentioned: {location}")
            
            for pokemon in line.entities.get('pokemon', []):
                info.append(f"Pokemon mentioned: {pokemon}")
            
            for item in line.entities.get('items', []):
                info.append(f"Item mentioned: {item}")
        
        return info

    def _is_choice_line(self, text: str) -> bool:
        """Check if line presents a choice"""
        choice_patterns = [
            r'\d+\)\s*\w+',
            r'\[YES/NO\]',
            r'YES\s*NO',
            r'CHOOSE',
            r'SELECT',
        ]
        
        return any(re.search(pattern, text.upper()) for pattern in choice_patterns)

    def _is_important_line(self, text: str, intent: Optional[DialogIntent]) -> bool:
        """Check if line contains important information"""
        if intent in [DialogIntent.QUEST, DialogIntent.PROGRESSION, DialogIntent.BATTLE_CHALLENGE]:
            return True
        
        important_keywords = ['BADGE', 'GYM', 'LEADER', 'CHAMPION', 'LEGENDARY', 'SECRET', 'HIDDEN']
        
        return any(keyword in text.upper() for keyword in important_keywords)

    def _detect_quest(self, lines: List[DialogLine]) -> Optional[str]:
        """Detect if a quest is triggered"""
        for line in lines:
            if line.intent == DialogIntent.QUEST:
                return f"Quest from {line.speaker or 'NPC'}"
        
        return None

    def _detect_reward(self, lines: List[DialogLine]) -> Optional[Dict[str, Any]]:
        """Detect if a reward is offered"""
        for line in lines:
            if line.intent == DialogIntent.REWARD or line.intent == DialogIntent.GIFT:
                return {
                    'type': 'item',
                    'item': line.entities.get('items', ['Unknown'])[0] if line.entities.get('items') else 'Unknown',
                    'source': line.speaker
                }
        
        return None


class TextSpeedController:
    """
    Controller for dialogue text speed optimization.
    
    Optimizes text display speed for AI efficiency while handling:
    - AI vs human readability tradeoffs
    - Skip logic (read first line, skip rest)
    - Text box detection
    """

    def __init__(self):
        self._speed_settings = {
            'instant': {'text_delay': 0.0, 'auto_advance': True, 'skip_threshold': 5},
            'fast': {'text_delay': 0.05, 'auto_advance': True, 'skip_threshold': 3},
            'normal': {'text_delay': 0.15, 'auto_advance': False, 'skip_threshold': 1},
            'slow': {'text_delay': 0.3, 'auto_advance': False, 'skip_threshold': 0},
        }
        self._current_setting = 'fast'
        self._skip_read_first = True
        self._dialog_advance_count = 0
        self._dialog_skip_count = 0

    def get_optimal_speed(self, dialog_entry: DialogEntry) -> Dict[str, Any]:
        """Determine optimal text speed for a dialog entry"""
        line_count = len(dialog_entry.lines)
        important_lines = sum(1 for line in dialog_entry.lines if line.is_important)
        
        if important_lines > 0 and important_lines == line_count:
            return self._speed_settings['normal'].copy()
        
        if line_count > self._speed_settings[self._current_setting]['skip_threshold']:
            if self._skip_read_first and line_count > 1:
                self._dialog_skip_count += 1
                return {
                    **self._speed_settings[self._current_setting],
                    'read_first_line_only': True,
                    'skip_remaining': True,
                }
        
        self._dialog_advance_count += 1
        return self._speed_settings[self._current_setting].copy()

    def calculate_button_presses(self, dialog_entry: DialogEntry) -> List[NavigationButton]:
        """Calculate button presses needed to advance dialog"""
        speed_settings = self.get_optimal_speed(dialog_entry)
        presses = []
        
        if speed_settings.get('read_first_line_only'):
            presses.append(NavigationButton.A)
            remaining = len(dialog_entry.lines) - 1
        else:
            remaining = len(dialog_entry.lines)
        
        if speed_settings.get('auto_advance'):
            presses.extend([NavigationButton.A] * remaining)
        else:
            presses.append(NavigationButton.A)
        
        return presses

    def set_speed_setting(self, setting: str) -> bool:
        """Set text speed setting"""
        if setting in self._speed_settings:
            self._current_setting = setting
            logger.info(f"Text speed set to: {setting}")
            return True
        return False

    def get_speed_stats(self) -> Dict[str, Any]:
        """Get text speed controller statistics"""
        total = self._dialog_advance_count + self._dialog_skip_count
        skip_rate = (self._dialog_skip_count / total * 100) if total > 0 else 0.0
        
        return {
            'current_setting': self._current_setting,
            'total_dialogs': total,
            'advance_count': self._dialog_advance_count,
            'skip_count': self._dialog_skip_count,
            'skip_rate_percent': skip_rate,
        }

    def should_skip_remaining(self, dialog_entry: DialogEntry) -> Tuple[bool, int]:
        """Determine if remaining dialog should be skipped"""
        speed_settings = self.get_optimal_speed(dialog_entry)
        
        if speed_settings.get('skip_remaining', False):
            return True, len(dialog_entry.lines) - 1
        
        return False, 0


class MenuNavigator:
    """
    Navigator for game menus.
    
    Handles:
    - Option selection via button presses
    - Yes/No dialog handling
    - Multiple choice menus
    - Menu type detection
    """

    def __init__(self):
        self._menu_coordinate_maps: Dict[MenuType, Dict[str, Tuple[int, int]]] = {}
        self._menu_cache: Dict[str, List[NavigationButton]] = {}
        self._menu_statistics = {
            'total_navigations': 0,
            'successful_navigations': 0,
            'failed_navigations': 0,
        }
        self._setup_default_maps()

    def _setup_default_maps(self) -> None:
        """Setup default menu coordinate mappings"""
        self._menu_coordinate_maps = {
            MenuType.MAIN_MENU: {
                'POKEMON': (0, 0),
                'BAG': (0, 1),
                'FIGHT': (0, 2),
                'RUN': (0, 3),
            },
            MenuType.BATTLE_MENU: {
                'FIGHT': (0, 0),
                'PKMN': (0, 1),
                'ITEM': (0, 2),
                'RUN': (0, 3),
            },
            MenuType.BAG_MENU: {
                'ITEMS': (0, 0),
                'BALLS': (0, 1),
                'KEY_ITEMS': (0, 2),
            },
            MenuType.POKEMON_MENU: {},
            MenuType.SHOP_MENU: {
                'BUY': (0, 0),
                'SELL': (0, 1),
            },
            MenuType.YES_NO: {
                'YES': (0, 0),
                'NO': (0, 1),
            },
            MenuType.SAVE_MENU: {
                'YES': (0, 0),
                'NO': (0, 1),
            },
        }

    def detect_menu_type(self, screen_text: str) -> Optional[MenuType]:
        """Detect menu type from screen text"""
        text_upper = screen_text.upper()
        
        if 'POKEMON' in text_upper and any(word in text_upper for word in ['BAG', 'FIGHT', 'RUN']):
            return MenuType.MAIN_MENU
        
        if 'FIGHT' in text_upper and 'PKMN' in text_upper:
            return MenuType.BATTLE_MENU
        
        if 'ITEMS' in text_upper and 'BALLS' in text_upper:
            return MenuType.BAG_MENU
        
        if 'BUY' in text_upper and 'SELL' in text_upper:
            return MenuType.SHOP_MENU
        
        if 'YES' in text_upper and 'NO' in text_upper:
            return MenuType.YES_NO
        
        if 'SAVE' in text_upper:
            return MenuType.SAVE_MENU
        
        if 'OPTIONS' in text_upper:
            return MenuType.OPTIONS
        
        return None

    def create_menu_state(self, menu_type: MenuType, options: List[str], 
                          current_selection: int = 0) -> MenuState:
        """Create a menu state from detected options"""
        parsed_options = []
        
        for i, option_text in enumerate(options):
            row, col = self._calculate_position(len(options), i)
            
            parsed_options.append(MenuOption(
                index=i,
                text=option_text,
                row=row,
                col=col,
                is_selected=(i == current_selection)
            ))
        
        cursor_pos = self._calculate_position(len(options), current_selection)
        
        return MenuState(
            menu_type=menu_type,
            options=parsed_options,
            current_selection=current_selection,
            cursor_position=cursor_pos,
            is_active=True
        )

    def _calculate_position(self, total_options: int, index: int) -> Tuple[int, int]:
        """Calculate cursor position for option index"""
        row = index % 2
        col = index // 2
        return (row, col)

    def calculate_navigation_path(self, current_pos: Tuple[int, int], 
                                   target_pos: Tuple[int, int]) -> List[NavigationButton]:
        """Calculate button presses needed to navigate to target position"""
        path = []
        current_row, current_col = current_pos
        target_row, target_col = target_pos
        
        while current_row < target_row:
            path.append(NavigationButton.DOWN)
            current_row += 1
        while current_row > target_row:
            path.append(NavigationButton.UP)
            current_row -= 1
        
        while current_col < target_col:
            path.append(NavigationButton.RIGHT)
            current_col += 1
        while current_col > target_col:
            path.append(NavigationButton.LEFT)
            current_col -= 1
        
        return path

    def navigate_to_option(self, menu_state: MenuState, option_text: str) -> Tuple[bool, List[NavigationButton]]:
        """Calculate navigation path to a specific option"""
        self._menu_statistics['total_navigations'] += 1
        
        target_option = None
        for option in menu_state.options:
            if option_text.upper() in option.text.upper():
                target_option = option
                break
        
        if target_option is None:
            self._menu_statistics['failed_navigations'] += 1
            return False, []
        
        current_pos = menu_state.cursor_position
        target_pos = (target_option.row, target_option.col)
        
        path = self.calculate_navigation_path(current_pos, target_pos)
        
        if path:
            self._menu_statistics['successful_navigations'] += 1
        else:
            self._menu_statistics['total_navigations'] -= 1
        
        return len(path) > 0, path

    def select_current_option(self) -> List[NavigationButton]:
        """Get button press to select current option"""
        return [NavigationButton.A]

    def handle_yes_no_dialog(self, response: bool) -> List[NavigationButton]:
        """Handle Yes/No dialog response"""
        if response:
            return [NavigationButton.A]
        else:
            return [NavigationButton.DOWN, NavigationButton.A]

    def handle_multiple_choice(self, choice_index: int, total_options: int) -> List[NavigationButton]:
        """Handle multiple choice menu selection"""
        presses = []
        
        target_row, target_col = self._calculate_position(total_options, choice_index)
        
        if target_row > 0:
            presses.extend([NavigationButton.DOWN] * target_row)
        elif target_row < 0:
            presses.extend([NavigationButton.UP] * abs(target_row))
        
        if target_col > 0:
            presses.extend([NavigationButton.RIGHT] * target_col)
        elif target_col < 0:
            presses.extend([NavigationButton.LEFT] * abs(target_col))
        
        presses.append(NavigationButton.A)
        
        return presses

    def exit_menu(self) -> List[NavigationButton]:
        """Get button presses to exit current menu"""
        return [NavigationButton.B]

    def get_menu_stats(self) -> Dict[str, Any]:
        """Get menu navigation statistics"""
        total = self._menu_statistics['total_navigations']
        success = self._menu_statistics['successful_navigations']
        
        return {
            'total_navigations': total,
            'successful_navigations': success,
            'failed_navigations': self._menu_statistics['failed_navigations'],
            'success_rate_percent': (success / total * 100) if total > 0 else 0.0,
        }

    def clear_cache(self) -> None:
        """Clear menu navigation cache"""
        self._menu_cache.clear()


class NPCInteraction:
    """
    Handler for NPC interactions.
    
    Responsibilities:
    - Trainer battle initiation detection
    - Gift/reward extraction
    - Information and hint extraction
    - NPC relationship tracking
    """

    def __init__(self, dialog_parser: Optional[DialogParser] = None):
        self._dialog_parser = dialog_parser or DialogParser()
        self._npc_database: Dict[str, NPCInfo] = {}
        self._interaction_history: List[InteractionResult] = []
        self._setup_default_npcs()

    def _setup_default_npcs(self) -> None:
        """Setup default NPC database"""
        default_npcs = [
            NPCInfo(name="PROFESSOR OAK", role="Professor", location="PALLET TOWN", is_trainer=False),
            NPCInfo(name="NURSE JOY", role="Nurse", location="POKEMON CENTER", is_trainer=False),
            NPCInfo(name="MR FUJI", role="Shopkeeper", location="POKEMART", is_trainer=False),
            NPCInfo(name="BROCK", role="Gym Leader", location="PEWTER CITY", is_trainer=True, trainer_class="GYM LEADER"),
            NPCInfo(name="MISTY", role="Gym Leader", location="CERULEAN CITY", is_trainer=True, trainer_class="GYM LEADER"),
            NPCInfo(name="LTSURGE", role="Gym Leader", location="VERMILION CITY", is_trainer=True, trainer_class="GYM LEADER"),
            NPCInfo(name="ERIKA", role="Gym Leader", location="CELADON CITY", is_trainer=True, trainer_class="GYM LEADER"),
            NPCInfo(name="KOGA", role="Gym Leader", location="FUCHSIA CITY", is_trainer=True, trainer_class="GYM LEADER"),
            NPCInfo(name="BLAINE", role="Gym Leader", location="CINNABAR ISLAND", is_trainer=True, trainer_class="GYM LEADER"),
            NPCInfo(name="SABRINA", role="Gym Leader", location="SAFFRON CITY", is_trainer=True, trainer_class="GYM LEADER"),
            NPCInfo(name="GIOVANNI", role="Gym Leader", location="VIRIDIAN CITY", is_trainer=True, trainer_class="GYM LEADER"),
            NPCInfo(name="BLUE", role="Rival", location="Various", is_trainer=True, trainer_class="RIVAL"),
        ]
        
        for npc in default_npcs:
            self._npc_database[npc.name] = npc

    def interact_with_npc(self, npc_name: str, dialog_text: str, 
                          context: Optional[Dict[str, Any]] = None) -> InteractionResult:
        """Process interaction with an NPC"""
        start_time = time.time()
        
        npc_info = self._get_or_create_npc(npc_name, context)
        
        dialog_entry = self._dialog_parser.parse_dialog(dialog_text, context)
        
        battle_initiated = self._detect_battle_initiation(dialog_entry)
        gift_received = self._extract_gift(dialog_entry)
        information_gained = dialog_entry.information_extracted
        quest_started = dialog_entry.quest_triggered
        
        npc_info.dialogue_history.append(dialog_text[:100])
        
        result = InteractionResult(
            success=True,
            npc_info=npc_info,
            dialog_entry=dialog_entry,
            battle_initiated=battle_initiated,
            gift_received=gift_received,
            information_gained=information_gained,
            quest_started=quest_started,
            action_taken=self._determine_action(dialog_entry),
            time_spent_ms=(time.time() - start_time) * 1000
        )
        
        self._interaction_history.append(result)
        
        return result

    def _get_or_create_npc(self, name: str, context: Optional[Dict[str, Any]] = None) -> NPCInfo:
        """Get existing NPC or create new one"""
        name_upper = name.upper()
        
        if name_upper in self._npc_database:
            return self._npc_database[name_upper]
        
        is_trainer = context.get('is_trainer', False) if context else False
        
        npc = NPCInfo(
            name=name,
            role="NPC",
            location=context.get('location', 'Unknown') if context else 'Unknown',
            is_trainer=is_trainer
        )
        
        self._npc_database[name_upper] = npc
        return npc

    def _detect_battle_initiation(self, dialog_entry: DialogEntry) -> bool:
        """Detect if a battle was initiated"""
        if dialog_entry.primary_intent in [DialogIntent.BATTLE_CHALLENGE, DialogIntent.THREAT]:
            return True
        
        for line in dialog_entry.lines:
            if line.intent == DialogIntent.BATTLE_CHALLENGE:
                return True
        
        return False

    def _extract_gift(self, dialog_entry: DialogEntry) -> Optional[str]:
        """Extract gift/reward information"""
        if dialog_entry.reward_offered:
            return dialog_entry.reward_offered.get('item')
        
        for line in dialog_entry.lines:
            if line.intent == DialogIntent.GIFT:
                items = line.entities.get('items', [])
                if items:
                    return items[0]
        
        return None

    def _determine_action(self, dialog_entry: DialogEntry) -> str:
        """Determine what action to take based on dialog"""
        action_map = {
            DialogIntent.GREETING: "acknowledge",
            DialogIntent.THREAT: "prepare_battle",
            DialogIntent.REWARD: "accept",
            DialogIntent.CHOICE: "choose",
            DialogIntent.SHOP: "enter_shop",
            DialogIntent.HEAL: "accept_heal",
            DialogIntent.PROGRESSION: "advance",
            DialogIntent.QUEST: "accept_quest",
            DialogIntent.INFORMATION: "remember",
            DialogIntent.BATTLE_CHALLENGE: "enter_battle",
            DialogIntent.GIFT: "receive",
        }
        
        return action_map.get(dialog_entry.primary_intent, "continue")

    def extract_information(self, dialog_text: str) -> List[str]:
        """Extract useful information from dialog"""
        dialog_entry = self._dialog_parser.parse_dialog(dialog_text)
        return dialog_entry.information_extracted

    def extract_hints(self, dialog_text: str) -> List[str]:
        """Extract hints from dialog"""
        hints = []
        
        hint_keywords = ['tip', 'hint', 'secret', 'hidden', 'warning', 'danger', 'rare']
        
        lines = dialog_text.split('\n')
        for line in lines:
            line_lower = line.lower()
            for keyword in hint_keywords:
                if keyword in line_lower:
                    hints.append(line.strip())
                    break
        
        return hints

    def get_npc_info(self, npc_name: str) -> Optional[NPCInfo]:
        """Get information about an NPC"""
        return self._npc_database.get(npc_name.upper())

    def get_interaction_history(self) -> List[InteractionResult]:
        """Get history of all interactions"""
        return self._interaction_history.copy()

    def get_interaction_stats(self) -> Dict[str, Any]:
        """Get interaction statistics"""
        total = len(self._interaction_history)
        
        battles = sum(1 for r in self._interaction_history if r.battle_initiated)
        gifts = sum(1 for r in self._interaction_history if r.gift_received)
        quests = sum(1 for r in self._interaction_history if r.quest_started)
        
        return {
            'total_interactions': total,
            'battles_initiated': battles,
            'gifts_received': gifts,
            'quests_started': quests,
            'avg_time_ms': sum(r.time_spent_ms for r in self._interaction_history) / total if total > 0 else 0.0,
        }


class DialogueManager:
    """
    Main dialogue system coordinating all components.
    
    Integrates:
    - DialogParser for text analysis
    - TextSpeedController for display optimization
    - MenuNavigator for menu interactions
    - NPCInteraction for NPC management
    """

    def __init__(self):
        self.dialog_parser = DialogParser()
        self.text_speed = TextSpeedController()
        self.menu_navigator = MenuNavigator()
        self.npc_interaction = NPCInteraction(self.dialog_parser)
        
        self._dialog_history: List[DialogEntry] = []
        self._system_stats = {
            'total_dialogs_processed': 0,
            'avg_processing_time_ms': 0.0,
            'intent_accuracy': 0.0,
        }

    def process_dialog(self, raw_text: str, context: Optional[Dict[str, Any]] = None) -> DialogEntry:
        """Process dialog text and return structured entry"""
        entry = self.dialog_parser.parse_dialog(raw_text, context)
        
        self._dialog_history.append(entry)
        
        self._system_stats['total_dialogs_processed'] += 1
        
        total_time = sum(d.duration_ms for d in self._dialog_history)
        count = len(self._dialog_history)
        self._system_stats['avg_processing_time_ms'] = total_time / count if count > 0 else 0.0
        
        return entry

    def advance_dialog(self, dialog_entry: DialogEntry) -> List[NavigationButton]:
        """Get button presses to advance through dialog"""
        return self.text_speed.calculate_button_presses(dialog_entry)

    def handle_npc_interaction(self, npc_name: str, dialog_text: str, 
                                context: Optional[Dict[str, Any]] = None) -> InteractionResult:
        """Handle interaction with an NPC"""
        return self.npc_interaction.interact_with_npc(npc_name, dialog_text, context)

    def navigate_menu(self, menu_text: str, target_option: str) -> Tuple[bool, List[NavigationButton]]:
        """Navigate to a specific menu option"""
        menu_type = self.menu_navigator.detect_menu_type(menu_text)
        
        if menu_type is None:
            return False, []
        
        options = self._extract_menu_options(menu_text)
        menu_state = self.menu_navigator.create_menu_state(menu_type, options)
        
        return self.menu_navigator.navigate_to_option(menu_state, target_option)

    def _extract_menu_options(self, menu_text: str) -> List[str]:
        """Extract menu options from text"""
        options = []
        
        lines = menu_text.split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) > 0:
                options.append(line)
        
        return options

    def get_system_stats(self) -> Dict[str, Any]:
        """Get dialogue system statistics"""
        dialog_stats = self.text_speed.get_speed_stats()
        menu_stats = self.menu_navigator.get_menu_stats()
        npc_stats = self.npc_interaction.get_interaction_stats()
        
        return {
            **self._system_stats,
            'text_speed': dialog_stats,
            'menu_navigation': menu_stats,
            'npc_interactions': npc_stats,
        }

    def get_dialog_history(self) -> List[DialogEntry]:
        """Get history of processed dialogs"""
        return self._dialog_history.copy()

    def reset(self) -> None:
        """Reset dialogue system state"""
        self._dialog_history.clear()
        self._system_stats = {
            'total_dialogs_processed': 0,
            'avg_processing_time_ms': 0.0,
            'intent_accuracy': 0.0,
        }
        self.text_speed = TextSpeedController()
        self.menu_navigator.clear_cache()


def create_dialogue_system() -> DialogueManager:
    """Factory function to create a fully configured dialogue system"""
    return DialogueManager()


def create_dialog_parser() -> DialogParser:
    """Factory function to create a dialog parser"""
    return DialogParser()


def create_text_speed_controller() -> TextSpeedController:
    """Factory function to create a text speed controller"""
    return TextSpeedController()


def create_menu_navigator() -> MenuNavigator:
    """Factory function to create a menu navigator"""
    return MenuNavigator()


def create_npc_interaction() -> NPCInteraction:
    """Factory function to create an NPC interaction handler"""
    return NPCInteraction()