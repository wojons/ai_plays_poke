"""
Inventory & Item Management Module for PTP-01X Pokemon AI

Implements comprehensive inventory management with:
- InventoryState: Item tracking with categories, counts, and TMs
- ShoppingHeuristic: Intelligent shopping based on progress and budget
- PokemonCenterProtocol: Healing triggers and optimal party management
- ItemUsageStrategy: Battle item optimization and waste prevention

Integration Points:
- Vision (Chapter 1): OCR for item reading, visual bag detection
- GOAP (Chapter 9): Shopping goals, healing objectives
- Combat (Chapter 3): Potion usage, status cure decisions
- Navigation (Chapter 4): Mart/Center locations for route planning
- Data (Chapter 5): Inventory persistence, item knowledge base
- HSM (Chapter 2): Shopping/Healing state transitions
- Failsafe (Chapter 10): Low-money triggers, corruption detection

Performance Targets:
- Shopping decision latency: <2 seconds
- Item usage in battle: <0.5 second response
- Pokemon Center cycle: <30 seconds complete
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ItemCategory(Enum):
    """Item category classifications"""
    POTION = auto()
    POKEBALL = auto()
    STATUS_CURE = auto()
    BATTLE_ITEM = auto()
    KEY_ITEM = auto()
    TM_HM = auto()
    BERRY = auto()
    HONEY = auto()
    MAIL = auto()
    MISC = auto()


class ItemType(Enum):
    """All item types in Pokemon Yellow"""
    POTION = "Potion"
    SUPER_POTION = "Super Potion"
    HYPER_POTION = "Hyper Potion"
    MAX_POTION = "Max Potion"
    FULL_RESTORE = "Full Restore"
    POKE_BALL = "Poke Ball"
    GREAT_BALL = "Great Ball"
    ULTRA_BALL = "Ultra Ball"
    MASTER_BALL = "Master Ball"
    SAFARI_BALL = "Safari Ball"
    ANTIDOTE = "Antidote"
    BURN_HEAL = "Burn Heal"
    ICE_HEAL = "Ice Heal"
    AWAKENING = "Awakening"
    PARALYZE_HEAL = "Paralyze Heal"
    FULL_HEAL = "Full Heal"
    REVIVE = "Revive"
    MAX_REVIVE = "Max Revive"
    ETHER = "Ether"
    MAX_ETHER = "Max Ether"
    ELIXIR = "Elixir"
    MAX_ELIXIR = "Max Elixir"
    ESCAPE_ROPE = "Escape Rope"
    REPEL = "Repel"
    SUPER_REPEL = "Super Repel"
    MAX_REPEL = "Max Repel"
    X_ATTACK = "X Attack"
    X_DEFEND = "X Defend"
    X_SPEED = "X Speed"
    X_SPECIAL = "X Special"
    DIRE_HIT = "Dire Hit"
    GUARD_SPEC = "Guard Spec"
    CHARCOAL = "Charcoal"
    MYSTIC_WATER = "Mystic Water"
    MIRACLE_SEED = "Miracle Seed"
    BLACK_BELT = "Black Belt"
    SHARP_BEAK = "Sharp Beak"
    POISON_BARB = "Poison Barb"
    SOFT_SAND = "Soft Sand"
    HARD_STONE = "Hard Stone"
    SILVER_POWDER = "Silver Powder"
    SPELL_TAG = "Spell Tag"
    TWISTED_SPOON = "Twisted Spoon"
    METAL_COAT = "Metal Coat"
    LEAF_STONE = "Leaf Stone"
    FIRE_STONE = "Fire Stone"
    WATER_STONE = "Water Stone"
    THUNDER_STONE = "Thunder Stone"
    MOON_STONE = "Moon Stone"
    SUN_STONE = "Sun Stone"
    BICYCLE = "Bicycle"
    COIN_CASE = "Coin Case"
    ITEMFINDER = "Itemfinder"
    OLD_ROD = "Old Rod"
    GOOD_ROD = "Good Rod"
    SUPER_ROD = "Super Rod"
    POKEDEX = "Pokedex"
    TOWN_MAP = "Town Map"
    VS_SEEKER = "Vs Seeker"
    BASEMENT_KEY = "Basement Key"
    RARE_CANDY = "Rare Candy"
    HM01 = "HM01 Cut"
    HM02 = "HM02 Fly"
    HM03 = "HM03 Surf"
    HM04 = "HM04 Strength"
    HM05 = "HM05 Flash"
    TM01 = "TM01 Mega Punch"
    TM02 = "TM02 Razor Wind"
    TM03 = "TM03 Swords Dance"
    TM04 = "TM04 Whirlwind"
    TM05 = "TM05 Mega Kick"
    TM06 = "TM06 Toxic"
    TM07 = "TM07 Horn Drill"
    TM08 = "TM08 Body Slam"
    TM09 = "TM09 Take Down"
    TM10 = "TM10 Double Edge"
    TM11 = "TM11 Bubble Beam"
    TM12 = "TM12 Water Gun"
    TM13 = "TM13 Ice Punch"
    TM14 = "TM14 Blizzard"
    TM15 = "TM15 Hyper Beam"
    TM16 = "TM16 Pay Day"
    TM17 = "TM17 Submission"
    TM18 = "TM18 Counter"
    TM19 = "TM19 Seismic Toss"
    TM20 = "TM20 Rage"
    TM21 = "TM21 Mega Drain"
    TM22 = "TM22 SolarBeam"
    TM23 = "TM23 Dragon Rage"
    TM24 = "TM24 Thunderbolt"
    TM25 = "TM25 Thunder"
    TM26 = "TM26 Earthquake"
    TM27 = "TM27 Fissure"
    TM28 = "TM28 Dig"
    TM29 = "TM29 Psychic"
    TM30 = "TM30 Teleport"
    TM31 = "TM31 Mimic"
    TM32 = "TM32 Double Team"
    TM33 = "TM33 Reflect"
    TM34 = "TM34 Bide"
    TM35 = "TM35 Metronome"
    TM36 = "TM36 Selfdestruct"
    TM37 = "TM37 Egg Bomb"
    TM38 = "TM38 Fire Blast"
    TM39 = "TM39 Swift"
    TM40 = "TM40 Skull Bash"
    TM41 = "TM41 Softboiled"
    TM42 = "TM42 Dream Eater"
    TM43 = "TM43 Sky Attack"
    TM44 = "TM44 Rest"
    TM45 = "TM45 Thunder Wave"
    TM46 = "TM46 Psywave"
    TM47 = "TM47 Explosion"
    TM48 = "TM48 Rock Slide"
    TM49 = "TM49 Tri Attack"
    TM50 = "TM50 Substitut"


class HealingPriority(Enum):
    """Priority levels for healing decisions"""
    CRITICAL = 95
    HIGH = 70
    MEDIUM = 40
    LOW = 0


class ShoppingPriority(Enum):
    """Priority levels for shopping decisions"""
    CRITICAL = 95
    HIGH = 70
    MEDIUM = 40
    LOW = 0


@dataclass
class ItemData:
    """Static data for an item type"""
    item_type: ItemType
    name: str
    category: ItemCategory
    base_price: int
    healing_power: int = 0
    is_key_item: bool = False
    is_tm: bool = False
    tm_number: Optional[int] = None
    hm_number: Optional[int] = None
    compatible_pokemon: List[str] = field(default_factory=list)


@dataclass
class InventoryItem:
    """An item instance in the inventory"""
    item_type: ItemType
    quantity: int = 1
    max_quantity: int = 99

    @property
    def is_empty(self) -> bool:
        return self.quantity <= 0

    @property
    def is_full(self) -> bool:
        return self.quantity >= self.max_quantity

    def add(self, amount: int = 1) -> int:
        actual_add = min(amount, self.max_quantity - self.quantity)
        self.quantity += actual_add
        return actual_add

    def remove(self, amount: int = 1) -> int:
        actual_remove = min(amount, self.quantity)
        self.quantity -= actual_remove
        return actual_remove

    def consume(self) -> bool:
        """Consume one item (returns True if successful)"""
        if self.quantity > 0:
            self.quantity -= 1
            return True
        return False


@dataclass
class TMData:
    """TM/HM data including compatibility"""
    tm_number: int
    item_type: ItemType
    move_name: str
    move_type: str
    move_power: int
    move_accuracy: int
    compatible_species: List[str]
    is_hm: bool = False
    hm_move_name: Optional[str] = None


@dataclass
class KeyItem:
    """Key item tracking (HM moves, badges, event items)"""
    item_type: ItemType
    name: str
    description: str
    obtained: bool = False
    obtained_time: Optional[datetime] = None
    used: bool = False
    use_location: Optional[str] = None


@dataclass
class PokemonState:
    """State of a Pokemon for item usage decisions"""
    species: str
    level: int
    current_hp: int
    max_hp: int
    status: str
    moves: List[str]
    move_pp: Dict[str, int]
    move_max_pp: Dict[str, int]


@dataclass
class PartyState:
    """Complete party state for healing/item decisions"""
    pokemon: List[PokemonState]
    money: int

    def get_avg_level(self) -> float:
        if not self.pokemon:
            return 0.0
        return sum(p.level for p in self.pokemon) / len(self.pokemon)

    def get_avg_hp_percent(self) -> float:
        if not self.pokemon:
            return 0.0
        total_hp = sum(p.current_hp for p in self.pokemon)
        max_hp = sum(p.max_hp for p in self.pokemon)
        return total_hp / max_hp if max_hp > 0 else 0.0

    def get_lowest_hp_percent(self) -> float:
        if not self.pokemon:
            return 1.0
        return min(
            p.current_hp / p.max_hp if p.max_hp > 0 else 0
            for p in self.pokemon
        )

    def get_fainted_count(self) -> int:
        return sum(1 for p in self.pokemon if p.current_hp == 0)

    def get_status_count(self) -> int:
        return sum(1 for p in self.pokemon if p.status != "NONE")

    def get_healthy_count(self) -> int:
        return sum(
            1 for p in self.pokemon
            if p.current_hp > 0 and p.status == "NONE"
        )

    def get_total_pp_remaining(self) -> int:
        total = 0
        for p in self.pokemon:
            total += sum(p.move_pp.values())
        return total

    def get_total_pp_max(self) -> int:
        total = 0
        for p in self.pokemon:
            total += sum(p.move_max_pp.values())
        return total


@dataclass
class ShoppingListItem:
    """An item to purchase"""
    item_type: ItemType
    quantity: int
    priority: ShoppingPriority
    estimated_cost: int
    reason: str


@dataclass
class ShoppingPlan:
    """Complete shopping plan"""
    items: List[ShoppingListItem]
    total_cost: int
    available_budget: int
    emergency_reserve: int
    estimated_time: int


class InventoryState:
    """
    Tracks all inventory items including categories, counts, key items, and TMs.

    Responsibilities:
    - Item quantity tracking with add/remove/consume methods
    - Category-based organization (Potions, Pokeballs, TMs, etc.)
    - Key items (HM moves, badges, event items) tracking
    - TM and HM compatibility database
    - Bag capacity management
    """

    ITEM_DATABASE: Dict[ItemType, ItemData] = {}
    TM_DATABASE: Dict[int, TMData] = {}

    def __init__(self):
        self._items: Dict[ItemType, InventoryItem] = {}
        self._key_items: Dict[ItemType, KeyItem] = {}
        self._initialize_item_database()
        self._initialize_tm_database()
        self._bag_capacity = 20

    def _initialize_item_database(self) -> None:
        """Initialize the item knowledge base with all Pokemon Yellow items"""
        if InventoryState.ITEM_DATABASE:
            return

        item_db: Dict[ItemType, ItemData] = {}

        healing_items = [
            (ItemType.POTION, "Potion", ItemCategory.POTION, 300, 20),
            (ItemType.SUPER_POTION, "Super Potion", ItemCategory.POTION, 700, 50),
            (ItemType.HYPER_POTION, "Hyper Potion", ItemCategory.POTION, 1200, 200),
            (ItemType.MAX_POTION, "Max Potion", ItemCategory.POTION, 2500, 999),
            (ItemType.FULL_RESTORE, "Full Restore", ItemCategory.POTION, 3000, 999),
        ]

        pokeballs = [
            (ItemType.POKE_BALL, "Poke Ball", ItemCategory.POKEBALL, 200, 0),
            (ItemType.GREAT_BALL, "Great Ball", ItemCategory.POKEBALL, 600, 0),
            (ItemType.ULTRA_BALL, "Ultra Ball", ItemCategory.POKEBALL, 1200, 0),
            (ItemType.MASTER_BALL, "Master Ball", ItemCategory.POKEBALL, 0, 0),
            (ItemType.SAFARI_BALL, "Safari Ball", ItemCategory.POKEBALL, 0, 0),
        ]

        status_cures = [
            (ItemType.ANTIDOTE, "Antidote", ItemCategory.STATUS_CURE, 200, 0),
            (ItemType.BURN_HEAL, "Burn Heal", ItemCategory.STATUS_CURE, 250, 0),
            (ItemType.ICE_HEAL, "Ice Heal", ItemCategory.STATUS_CURE, 250, 0),
            (ItemType.AWAKENING, "Awakening", ItemCategory.STATUS_CURE, 250, 0),
            (ItemType.PARALYZE_HEAL, "Paralyze Heal", ItemCategory.STATUS_CURE, 200, 0),
            (ItemType.FULL_HEAL, "Full Heal", ItemCategory.STATUS_CURE, 600, 0),
            (ItemType.REVIVE, "Revive", ItemCategory.STATUS_CURE, 1500, 0),
            (ItemType.MAX_REVIVE, "Max Revive", ItemCategory.STATUS_CURE, 4000, 0),
        ]

        pp_items = [
            (ItemType.ETHER, "Ether", ItemCategory.MISC, 1200, 0),
            (ItemType.MAX_ETHER, "Max Ether", ItemCategory.MISC, 2000, 0),
            (ItemType.ELIXIR, "Elixir", ItemCategory.MISC, 3000, 0),
            (ItemType.MAX_ELIXIR, "Max Elixir", ItemCategory.MISC, 4500, 0),
        ]

        repel_items = [
            (ItemType.REPEL, "Repel", ItemCategory.MISC, 350, 0),
            (ItemType.SUPER_REPEL, "Super Repel", ItemCategory.MISC, 500, 0),
            (ItemType.MAX_REPEL, "Max Repel", ItemCategory.MISC, 700, 0),
        ]

        x_items = [
            (ItemType.X_ATTACK, "X Attack", ItemCategory.BATTLE_ITEM, 500, 0),
            (ItemType.X_DEFEND, "X Defend", ItemCategory.BATTLE_ITEM, 550, 0),
            (ItemType.X_SPEED, "X Speed", ItemCategory.BATTLE_ITEM, 350, 0),
            (ItemType.X_SPECIAL, "X Special", ItemCategory.BATTLE_ITEM, 350, 0),
            (ItemType.DIRE_HIT, "Dire Hit", ItemCategory.BATTLE_ITEM, 650, 0),
            (ItemType.GUARD_SPEC, "Guard Spec", ItemCategory.BATTLE_ITEM, 700, 0),
        ]

        evolution_stones = [
            (ItemType.LEAF_STONE, "Leaf Stone", ItemCategory.MISC, 0),
            (ItemType.FIRE_STONE, "Fire Stone", ItemCategory.MISC, 0),
            (ItemType.WATER_STONE, "Water Stone", ItemCategory.MISC, 0),
            (ItemType.THUNDER_STONE, "Thunder Stone", ItemCategory.MISC, 0),
            (ItemType.MOON_STONE, "Moon Stone", ItemCategory.MISC, 0),
            (ItemType.SUN_STONE, "Sun Stone", ItemCategory.MISC, 0),
        ]

        key_items = [
            (ItemType.BICYCLE, "Bicycle", ItemCategory.KEY_ITEM, 0),
            (ItemType.COIN_CASE, "Coin Case", ItemCategory.KEY_ITEM, 0),
            (ItemType.ITEMFINDER, "Itemfinder", ItemCategory.KEY_ITEM, 0),
            (ItemType.OLD_ROD, "Old Rod", ItemCategory.KEY_ITEM, 0),
            (ItemType.GOOD_ROD, "Good Rod", ItemCategory.KEY_ITEM, 0),
            (ItemType.SUPER_ROD, "Super Rod", ItemCategory.KEY_ITEM, 0),
            (ItemType.POKEDEX, "Pokedex", ItemCategory.KEY_ITEM, 0),
            (ItemType.TOWN_MAP, "Town Map", ItemCategory.KEY_ITEM, 0),
            (ItemType.VS_SEEKER, "Vs Seeker", ItemCategory.KEY_ITEM, 0),
            (ItemType.BASEMENT_KEY, "Basement Key", ItemCategory.KEY_ITEM, 0),
        ]

        all_items = (
            healing_items + pokeballs + status_cures + pp_items +
            repel_items + x_items + evolution_stones + key_items
        )

        for item_info in all_items:
            if len(item_info) == 5:
                item_type, name, category, price, healing = item_info
            else:
                item_type, name, category, price = item_info
                healing = 0
            item_db[item_type] = ItemData(
                item_type=item_type,
                name=name,
                category=category,
                base_price=price,
                healing_power=healing,
                is_key_item=(category == ItemCategory.KEY_ITEM),
            )

        item_db[ItemType.RARE_CANDY] = ItemData(
            item_type=ItemType.RARE_CANDY,
            name="Rare Candy",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.ESCAPE_ROPE] = ItemData(
            item_type=ItemType.ESCAPE_ROPE,
            name="Escape Rope",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.CHARCOAL] = ItemData(
            item_type=ItemType.CHARCOAL,
            name="Charcoal",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.MYSTIC_WATER] = ItemData(
            item_type=ItemType.MYSTIC_WATER,
            name="Mystic Water",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.MIRACLE_SEED] = ItemData(
            item_type=ItemType.MIRACLE_SEED,
            name="Miracle Seed",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.BLACK_BELT] = ItemData(
            item_type=ItemType.BLACK_BELT,
            name="Black Belt",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.SHARP_BEAK] = ItemData(
            item_type=ItemType.SHARP_BEAK,
            name="Sharp Beak",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.POISON_BARB] = ItemData(
            item_type=ItemType.POISON_BARB,
            name="Poison Barb",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.SOFT_SAND] = ItemData(
            item_type=ItemType.SOFT_SAND,
            name="Soft Sand",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.HARD_STONE] = ItemData(
            item_type=ItemType.HARD_STONE,
            name="Hard Stone",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.SILVER_POWDER] = ItemData(
            item_type=ItemType.SILVER_POWDER,
            name="Silver Powder",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.SPELL_TAG] = ItemData(
            item_type=ItemType.SPELL_TAG,
            name="Spell Tag",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.TWISTED_SPOON] = ItemData(
            item_type=ItemType.TWISTED_SPOON,
            name="Twisted Spoon",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        item_db[ItemType.METAL_COAT] = ItemData(
            item_type=ItemType.METAL_COAT,
            name="Metal Coat",
            category=ItemCategory.MISC,
            base_price= 0,
        )

        InventoryState.ITEM_DATABASE = item_db

    def _initialize_tm_database(self) -> None:
        """Initialize TM compatibility database"""
        if InventoryState.TM_DATABASE:
            return

        tm_db: Dict[int, TMData] = {}

        tm_data_list = [
            (1, ItemType.TM01, "Mega Punch", "Normal", 40, 85, []),
            (2, ItemType.TM02, "Razor Wind", "Normal", 80, 100, []),
            (3, ItemType.TM03, "Swords Dance", "Normal", 0, 100, []),
            (4, ItemType.TM04, "Whirlwind", "Normal", 0, 100, []),
            (5, ItemType.TM05, "Mega Kick", "Normal", 120, 75, []),
            (6, ItemType.TM06, "Toxic", "Poison", 0, 90, []),
            (7, ItemType.TM07, "Horn Drill", "Normal", 0, 30, []),
            (8, ItemType.TM08, "Body Slam", "Normal", 85, 100, []),
            (9, ItemType.TM09, "Take Down", "Normal", 90, 85, []),
            (10, ItemType.TM10, "Double Edge", "Normal", 120, 100, []),
            (11, ItemType.TM11, "Bubble Beam", "Water", 65, 100, []),
            (12, ItemType.TM12, "Water Gun", "Water", 40, 100, []),
            (13, ItemType.TM13, "Ice Punch", "Ice", 75, 100, []),
            (14, ItemType.TM14, "Blizzard", "Ice", 110, 70, []),
            (15, ItemType.TM15, "Hyper Beam", "Normal", 150, 90, []),
            (16, ItemType.TM16, "Pay Day", "Normal", 40, 100, []),
            (17, ItemType.TM17, "Submission", "Fighting", 80, 80, []),
            (18, ItemType.TM18, "Counter", "Fighting", 0, 100, []),
            (19, ItemType.TM19, "Seismic Toss", "Fighting", 0, 100, []),
            (20, ItemType.TM20, "Rage", "Normal", 20, 100, []),
            (21, ItemType.TM21, "Mega Drain", "Grass", 40, 100, []),
            (22, ItemType.TM22, "SolarBeam", "Grass", 120, 100, []),
            (23, ItemType.TM23, "Dragon Rage", "Dragon", 0, 100, []),
            (24, ItemType.TM24, "Thunderbolt", "Electric", 90, 100, []),
            (25, ItemType.TM25, "Thunder", "Electric", 110, 70, []),
            (26, ItemType.TM26, "Earthquake", "Ground", 100, 100, []),
            (27, ItemType.TM27, "Fissure", "Ground", 0, 30, []),
            (28, ItemType.TM28, "Dig", "Ground", 60, 100, []),
            (29, ItemType.TM29, "Psychic", "Psychic", 90, 100, []),
            (30, ItemType.TM30, "Teleport", "Psychic", 0, 100, []),
            (31, ItemType.TM31, "Mimic", "Normal", 0, 100, []),
            (32, ItemType.TM32, "Double Team", "Normal", 0, 100, []),
            (33, ItemType.TM33, "Reflect", "Psychic", 0, 100, []),
            (34, ItemType.TM34, "Bide", "Normal", 0, 100, []),
            (35, ItemType.TM35, "Metronome", "Normal", 0, 100, []),
            (36, ItemType.TM36, "Selfdestruct", "Normal", 200, 100, []),
            (37, ItemType.TM37, "Egg Bomb", "Normal", 100, 75, []),
            (38, ItemType.TM38, "Fire Blast", "Fire", 110, 85, []),
            (39, ItemType.TM39, "Swift", "Normal", 60, 100, []),
            (40, ItemType.TM40, "Skull Bash", "Normal", 130, 100, []),
            (41, ItemType.TM41, "Softboiled", "Normal", 0, 100, []),
            (42, ItemType.TM42, "Dream Eater", "Psychic", 100, 100, []),
            (43, ItemType.TM43, "Sky Attack", "Normal", 140, 90, []),
            (44, ItemType.TM44, "Rest", "Psychic", 0, 100, []),
            (45, ItemType.TM45, "Thunder Wave", "Electric", 0, 100, []),
            (46, ItemType.TM46, "Psywave", "Psychic", 0, 80, []),
            (47, ItemType.TM47, "Explosion", "Normal", 250, 100, []),
            (48, ItemType.TM48, "Rock Slide", "Rock", 75, 90, []),
            (49, ItemType.TM49, "Tri Attack", "Normal", 80, 100, []),
            (50, ItemType.TM50, "Substitute", "Normal", 0, 100, []),
        ]

        for number, item_type, move_name, move_type, power, accuracy, compatible in tm_data_list:
            tm_db[number] = TMData(
                tm_number=number,
                item_type=item_type,
                move_name=move_name,
                move_type=move_type,
                move_power=power,
                move_accuracy=accuracy,
                compatible_species=compatible,
            )

        hm_db = [
            (1, ItemType.HM01, "Cut", "Normal", 50, 95, True),
            (2, ItemType.HM02, "Fly", "Flying", 70, 95, True),
            (3, ItemType.HM03, "Surf", "Water", 90, 100, True),
            (4, ItemType.HM04, "Strength", "Normal", 80, 100, True),
            (5, ItemType.HM05, "Flash", "Normal", 0, 70, True),
        ]

        for number, item_type, move_name, move_type, power, accuracy, _ in hm_db:
            tm_db[number] = TMData(
                tm_number=number,
                item_type=item_type,
                move_name=move_name,
                move_type=move_type,
                move_power=power,
                move_accuracy=accuracy,
                compatible_species=[],
                is_hm=True,
                hm_move_name=move_name,
            )

        InventoryState.TM_DATABASE = tm_db

    def get_item(self, item_type: ItemType) -> Optional[InventoryItem]:
        """Get an item from inventory"""
        return self._items.get(item_type)

    def get_quantity(self, item_type: ItemType) -> int:
        """Get quantity of an item type"""
        item = self.get_item(item_type)
        return item.quantity if item else 0

    def add_item(self, item_type: ItemType, quantity: int = 1) -> int:
        """Add items to inventory, returns actual amount added"""
        if item_type not in self._items:
            self._items[item_type] = InventoryItem(item_type=item_type, quantity=0)
        return self._items[item_type].add(quantity)

    def remove_item(self, item_type: ItemType, quantity: int = 1) -> int:
        """Remove items from inventory, returns actual amount removed"""
        item = self.get_item(item_type)
        if item:
            return item.remove(quantity)
        return 0

    def consume_item(self, item_type: ItemType) -> bool:
        """Consume one item (for battle/potion use)"""
        item = self.get_item(item_type)
        if item:
            return item.consume()
        return False

    def has_item(self, item_type: ItemType, quantity: int = 1) -> bool:
        """Check if inventory has at least quantity of item"""
        return self.get_quantity(item_type) >= quantity

    def get_by_category(self, category: ItemCategory) -> List[InventoryItem]:
        """Get all items in a category"""
        category_items = self._get_category_mapping().get(category, set())
        return [
            item for item in self._items.values()
            if item.item_type in category_items
        ]

    def _get_category_mapping(self) -> Dict[ItemCategory, Set[ItemType]]:
        """Get mapping of categories to item types"""
        return {
            ItemCategory.POTION: {
                ItemType.POTION, ItemType.SUPER_POTION, ItemType.HYPER_POTION,
                ItemType.MAX_POTION, ItemType.FULL_RESTORE,
            },
            ItemCategory.POKEBALL: {
                ItemType.POKE_BALL, ItemType.GREAT_BALL, ItemType.ULTRA_BALL,
                ItemType.MASTER_BALL, ItemType.SAFARI_BALL,
            },
            ItemCategory.STATUS_CURE: {
                ItemType.ANTIDOTE, ItemType.BURN_HEAL, ItemType.ICE_HEAL,
                ItemType.AWAKENING, ItemType.PARALYZE_HEAL, ItemType.FULL_HEAL,
                ItemType.REVIVE, ItemType.MAX_REVIVE,
            },
            ItemCategory.BATTLE_ITEM: {
                ItemType.X_ATTACK, ItemType.X_DEFEND, ItemType.X_SPEED,
                ItemType.X_SPECIAL, ItemType.DIRE_HIT, ItemType.GUARD_SPEC,
            },
            ItemCategory.KEY_ITEM: {
                ItemType.BICYCLE, ItemType.COIN_CASE, ItemType.ITEMFINDER,
                ItemType.OLD_ROD, ItemType.GOOD_ROD, ItemType.SUPER_ROD,
                ItemType.POKEDEX, ItemType.TOWN_MAP, ItemType.VS_SEEKER,
                ItemType.BASEMENT_KEY,
            },
            ItemCategory.TM_HM: set(),
        }

    def get_potions(self) -> Dict[ItemType, int]:
        """Get all healing potions with quantities"""
        potion_types = self._get_category_mapping()[ItemCategory.POTION]
        return {
            item_type: self.get_quantity(item_type)
            for item_type in potion_types
            if self.get_quantity(item_type) > 0
        }

    def get_pokeballs(self) -> Dict[ItemType, int]:
        """Get all capture balls with quantities"""
        ball_types = self._get_category_mapping()[ItemCategory.POKEBALL]
        return {
            item_type: self.get_quantity(item_type)
            for item_type in ball_types
            if self.get_quantity(item_type) > 0
        }

    def get_status_cures(self) -> Dict[ItemType, int]:
        """Get all status cure items with quantities"""
        cure_types = self._get_category_mapping()[ItemCategory.STATUS_CURE]
        return {
            item_type: self.get_quantity(item_type)
            for item_type in cure_types
            if self.get_quantity(item_type) > 0
        }

    def get_tms(self) -> List[TMData]:
        """Get all obtained TMs"""
        tm_types = {data.item_type for data in InventoryState.TM_DATABASE.values()}
        obtained = []
        for tm_number, tm_data in InventoryState.TM_DATABASE.items():
            if self.has_item(tm_data.item_type):
                obtained.append(tm_data)
        return obtained

    def get_tm_count(self) -> int:
        """Count obtained TMs"""
        return len(self.get_tms())

    def get_key_item(self, item_type: ItemType) -> Optional[KeyItem]:
        """Get key item status"""
        return self._key_items.get(item_type)

    def obtain_key_item(self, item_type: ItemType) -> None:
        """Mark a key item as obtained"""
        if item_type not in self._key_items:
            item_data = InventoryState.ITEM_DATABASE.get(item_type)
            if item_data:
                self._key_items[item_type] = KeyItem(
                    item_type=item_type,
                    name=item_data.name,
                    description=f"Key item: {item_data.name}",
                    obtained=True,
                    obtained_time=datetime.now(),
                )
        else:
            self._key_items[item_type].obtained = True
            self._key_items[item_type].obtained_time = datetime.now()

    def use_key_item(self, item_type: ItemType, location: str) -> None:
        """Record key item usage"""
        if item_type in self._key_items:
            self._key_items[item_type].used = True
            self._key_items[item_type].use_location = location

    def get_tm_compatibility(self, tm_number: int) -> Optional[TMData]:
        """Get TM data including compatible Pokemon"""
        return InventoryState.TM_DATABASE.get(tm_number)

    def get_bag_summary(self) -> Dict[str, Any]:
        """Get summary of inventory state"""
        category_summary = {}
        for category in ItemCategory:
            items = self.get_by_category(category)
            if items:
                category_summary[category.name] = sum(i.quantity for i in items)

        return {
            "total_items": len(self._items),
            "total_quantity": sum(i.quantity for i in self._items.values()),
            "by_category": category_summary,
            "key_items_obtained": len([k for k in self._key_items.values() if k.obtained]),
            "tms_obtained": self.get_tm_count(),
            "bag_capacity": self._bag_capacity,
            "bag_used": sum(i.quantity for i in self._items.values()),
        }

    def validate_inventory(self) -> Tuple[bool, List[str]]:
        """Validate inventory for corruption (negative quantities, etc.)"""
        errors = []
        is_valid = True

        for item_type, item in self._items.items():
            if item.quantity < 0:
                errors.append(f"Negative quantity for {item_type.name}")
                is_valid = False
            if item.quantity > 99:
                errors.append(f"Quantity > 99 for {item_type.name}")
                is_valid = False

        total_items = sum(i.quantity for i in self._items.values())
        if total_items > self._bag_capacity:
            errors.append(f"Bag capacity exceeded: {total_items}/{self._bag_capacity}")
            is_valid = False

        return is_valid, errors

    def clear_inventory(self) -> None:
        """Clear all inventory items (for testing)"""
        self._items.clear()
        self._key_items.clear()


class ShoppingHeuristic:
    """
    Intelligent shopping decisions based on progress, routes, and budget.

    Responsibilities:
    - Generate buy lists based on game progress (early vs late game)
    - Price optimization (better shops in different cities)
    - Restock intervals (Pokeballs, Potions based on usage)
    - Budget management (money tracking, spending limits)
    """

    ITEM_COSTS: Dict[ItemType, int] = {}
    HEALING_POWER: Dict[ItemType, int] = {}
    ROUTE_SHOPPING_NEEDS: Dict[str, Dict[str, Any]] = {}
    GYM_SPECIFIC_ITEMS: Dict[str, Dict[ItemType, int]] = {}

    def __init__(self, inventory: InventoryState):
        self._inventory = inventory
        self._initialize_item_costs()
        self._initialize_route_data()
        self._initialize_gym_data()

    def _initialize_item_costs(self) -> None:
        """Initialize item cost database"""
        if ShoppingHeuristic.ITEM_COSTS:
            return

        costs: Dict[ItemType, int] = {}
        healing_power: Dict[ItemType, int] = {}

        items_with_costs = [
            (ItemType.POTION, 300, 20),
            (ItemType.SUPER_POTION, 700, 50),
            (ItemType.HYPER_POTION, 1200, 200),
            (ItemType.MAX_POTION, 2500, 999),
            (ItemType.FULL_RESTORE, 3000, 999),
            (ItemType.POKE_BALL, 200, 0),
            (ItemType.GREAT_BALL, 600, 0),
            (ItemType.ULTRA_BALL, 1200, 0),
            (ItemType.MASTER_BALL, 0, 0),
            (ItemType.SAFARI_BALL, 0, 0),
            (ItemType.ANTIDOTE, 200, 0),
            (ItemType.BURN_HEAL, 250, 0),
            (ItemType.ICE_HEAL, 250, 0),
            (ItemType.AWAKENING, 250, 0),
            (ItemType.PARALYZE_HEAL, 200, 0),
            (ItemType.FULL_HEAL, 600, 0),
            (ItemType.REVIVE, 1500, 0),
            (ItemType.MAX_REVIVE, 4000, 0),
            (ItemType.ETHER, 1200, 0),
            (ItemType.MAX_ETHER, 2000, 0),
            (ItemType.ELIXIR, 3000, 0),
            (ItemType.MAX_ELIXIR, 4500, 0),
            (ItemType.REPEL, 350, 0),
            (ItemType.SUPER_REPEL, 500, 0),
            (ItemType.MAX_REPEL, 700, 0),
            (ItemType.X_ATTACK, 500, 0),
            (ItemType.X_DEFEND, 550, 0),
            (ItemType.X_SPEED, 350, 0),
            (ItemType.X_SPECIAL, 350, 0),
            (ItemType.DIRE_HIT, 650, 0),
            (ItemType.GUARD_SPEC, 700, 0),
        ]

        for item_type, cost, healing in items_with_costs:
            costs[item_type] = cost
            if healing > 0:
                healing_power[item_type] = healing

        ShoppingHeuristic.ITEM_COSTS = costs
        ShoppingHeuristic.HEALING_POWER = healing_power

    def _initialize_route_data(self) -> None:
        """Initialize route shopping needs database"""
        if ShoppingHeuristic.ROUTE_SHOPPING_NEEDS:
            return

        route_data: Dict[str, Dict[str, Any]] = {}

        route_data["ROUTE_1"] = {
            "min_wild_level": 2,
            "max_wild_level": 5,
            "pokemon_types": ["NORMAL", "BUG", "POISON"],
            "status_frequency": 0.1,
            "has_shiny_pokemon": False,
            "recommended_potions": 5,
            "recommended_balls": 10,
        }

        route_data["ROUTE_2"] = {
            "min_wild_level": 4,
            "max_wild_level": 8,
            "pokemon_types": ["BUG", "POISON", "GRASS"],
            "status_frequency": 0.3,
            "has_shiny_pokemon": False,
            "recommended_potions": 8,
            "recommended_balls": 15,
        }

        route_data["ROUTE_3"] = {
            "min_wild_level": 6,
            "max_wild_level": 12,
            "pokemon_types": ["ROCK", "GROUND", "FIGHTING"],
            "status_frequency": 0.1,
            "has_shiny_pokemon": True,
            "recommended_potions": 10,
            "recommended_balls": 20,
        }

        route_data["ROUTE_4"] = {
            "min_wild_level": 8,
            "max_wild_level": 14,
            "pokemon_types": ["WATER", "ELECTRIC"],
            "status_frequency": 0.2,
            "has_shiny_pokemon": False,
            "recommended_potions": 12,
            "recommended_balls": 15,
        }

        route_data["VIRIDIAN_FOREST"] = {
            "min_wild_level": 3,
            "max_wild_level": 6,
            "pokemon_types": ["BUG", "POISON"],
            "status_frequency": 0.5,
            "has_shiny_pokemon": False,
            "recommended_potions": 5,
            "recommended_balls": 10,
        }

        route_data["MT_MOON"] = {
            "min_wild_level": 10,
            "max_wild_level": 16,
            "pokemon_types": ["ROCK", "GROUND", "PSYCHIC"],
            "status_frequency": 0.1,
            "has_shiny_pokemon": True,
            "recommended_potions": 15,
            "recommended_balls": 25,
        }

        route_data["ROUTE_24"] = {
            "min_wild_level": 12,
            "max_wild_level": 18,
            "pokemon_types": ["WATER", "BUG", "GRASS"],
            "status_frequency": 0.2,
            "has_shiny_pokemon": False,
            "recommended_potions": 10,
            "recommended_balls": 15,
        }

        route_data["POWER_PLANT"] = {
            "min_wild_level": 22,
            "max_wild_level": 30,
            "pokemon_types": ["ELECTRIC"],
            "status_frequency": 0.6,
            "has_shiny_pokemon": True,
            "recommended_potions": 20,
            "recommended_balls": 30,
        }

        route_data["ROUTE_10"] = {
            "min_wild_level": 20,
            "max_wild_level": 28,
            "pokemon_types": ["ROCK", "GROUND", "ELECTRIC"],
            "status_frequency": 0.3,
            "has_shiny_pokemon": False,
            "recommended_potions": 15,
            "recommended_balls": 20,
        }

        route_data["VICTORY_ROAD"] = {
            "min_wild_level": 40,
            "max_wild_level": 55,
            "pokemon_types": ["ROCK", "GROUND", "FIGHTING", "PSYCHIC"],
            "status_frequency": 0.2,
            "has_shiny_pokemon": True,
            "recommended_potions": 30,
            "recommended_balls": 50,
        }

        ShoppingHeuristic.ROUTE_SHOPPING_NEEDS = route_data

    def _initialize_gym_data(self) -> None:
        """Initialize gym-specific shopping data"""
        if ShoppingHeuristic.GYM_SPECIFIC_ITEMS:
            return

        gym_items: Dict[str, Dict[ItemType, int]] = {}

        gym_items["BROCK"] = {
            ItemType.POTION: 10,
            ItemType.ANTIDOTE: 3,
        }

        gym_items["MISTY"] = {
            ItemType.SUPER_POTION: 10,
            ItemType.PARALYZE_HEAL: 5,
        }

        gym_items["LT_SURGE"] = {
            ItemType.HYPER_POTION: 10,
            ItemType.PARALYZE_HEAL: 5,
        }

        gym_items["ERIKA"] = {
            ItemType.SUPER_POTION: 15,
            ItemType.ANTIDOTE: 5,
            ItemType.BURN_HEAL: 5,
        }

        gym_items["KOGA"] = {
            ItemType.HYPER_POTION: 15,
            ItemType.ANTIDOTE: 5,
            ItemType.AWAKENING: 5,
        }

        gym_items["BLAINE"] = {
            ItemType.HYPER_POTION: 20,
            ItemType.BURN_HEAL: 10,
        }

        gym_items["SABRINA"] = {
            ItemType.HYPER_POTION: 20,
            ItemType.FULL_HEAL: 5,
        }

        gym_items["GIOVANNI"] = {
            ItemType.HYPER_POTION: 25,
            ItemType.SUPER_POTION: 10,
        }

        ShoppingHeuristic.GYM_SPECIFIC_ITEMS = gym_items

    def generate_shopping_list(
        self,
        party_state: PartyState,
        upcoming_route: Optional[str] = None,
        available_money: int = 0,
    ) -> ShoppingPlan:
        """
        Generate complete shopping plan based on current state and needs.

        Args:
            party_state: Current party status
            upcoming_route: Route ID for route-specific shopping needs
            available_money: Current money for budget calculations

        Returns:
            ShoppingPlan with items, costs, and priorities
        """
        available_budget, emergency_reserve = self.calculate_budget(
            available_money, []
        )

        shopping_needs: Dict[ItemType, int] = {}

        current_potions = sum(self._inventory.get_potions().values())
        current_balls = sum(self._inventory.get_pokeballs().values())
        current_cures = sum(self._inventory.get_status_cures().values())

        if current_potions < 10:
            shopping_needs[ItemType.POTION] = 10 - current_potions
        if current_balls < 15:
            shopping_needs[ItemType.POKE_BALL] = 15 - current_balls
        if current_cures < 3:
            shopping_needs[ItemType.FULL_HEAL] = 3 - current_cures

        if upcoming_route and upcoming_route in ShoppingHeuristic.ROUTE_SHOPPING_NEEDS:
            route_needs = self.analyze_route_needs(
                upcoming_route,
                party_state.get_avg_level()
            )
            for item_type, quantity in route_needs.items():
                if item_type in shopping_needs:
                    shopping_needs[item_type] = max(shopping_needs[item_type], quantity)
                else:
                    shopping_needs[item_type] = quantity

        early_game_essentials = self.get_early_game_essentials()
        for item_type in early_game_essentials:
            if not self._inventory.has_item(item_type):
                shopping_needs[item_type] = shopping_needs.get(item_type, 1)

        selected_items = self.select_items_for_budget(shopping_needs, available_budget)

        total_cost = sum(item.estimated_cost for item in selected_items)
        estimated_time = len(selected_items) * 30

        return ShoppingPlan(
            items=selected_items,
            total_cost=total_cost,
            available_budget=available_budget,
            emergency_reserve=emergency_reserve,
            estimated_time=estimated_time,
        )

    def analyze_route_needs(
        self,
        route_id: str,
        party_level: float,
    ) -> Dict[ItemType, int]:
        """
        Analyze upcoming route to determine shopping needs.

        Returns:
            Dictionary of item types with recommended quantities
        """
        needs: Dict[ItemType, int] = {}

        if route_id not in ShoppingHeuristic.ROUTE_SHOPPING_NEEDS:
            return needs

        route_data = ShoppingHeuristic.ROUTE_SHOPPING_NEEDS[route_id]

        max_wild_level = route_data["max_wild_level"]
        if max_wild_level > party_level + 5:
            potion_qty = 15 + (max_wild_level - int(party_level))
        else:
            potion_qty = 10

        needs[ItemType.POTION] = max(potion_qty, 5)

        encounter_types = route_data.get("pokemon_types", [])

        if "GRASS" in encounter_types or "POISON" in encounter_types:
            needs[ItemType.ANTIDOTE] = needs.get(ItemType.ANTIDOTE, 0) + 5

        if "ELECTRIC" in encounter_types:
            needs[ItemType.PARALYZE_HEAL] = needs.get(ItemType.PARALYZE_HEAL, 0) + 5

        if "FIRE" in encounter_types:
            needs[ItemType.BURN_HEAL] = needs.get(ItemType.BURN_HEAL, 0) + 5

        if route_data.get("status_frequency", 0) > 0.5:
            for status_item in [ItemType.ANTIDOTE, ItemType.PARALYZE_HEAL, ItemType.BURN_HEAL]:
                needs[status_item] = needs.get(status_item, 0) + 3

        if route_data.get("has_shiny_pokemon", False):
            needs[ItemType.POKE_BALL] = 30

        needs[ItemType.POKE_BALL] = max(needs.get(ItemType.POKE_BALL, 0), route_data.get("recommended_balls", 15))

        return needs

    def calculate_quantity_needed(
        self,
        item_type: ItemType,
        party_state: PartyState,
    ) -> int:
        """Calculate how many of an item are needed"""
        current = self._inventory.get_quantity(item_type)

        thresholds: Dict[ItemType, int] = {
            ItemType.POTION: 10,
            ItemType.SUPER_POTION: 5,
            ItemType.HYPER_POTION: 3,
            ItemType.POKE_BALL: 20,
            ItemType.GREAT_BALL: 5,
            ItemType.ANTIDOTE: 3,
            ItemType.PARALYZE_HEAL: 3,
            ItemType.BURN_HEAL: 3,
            ItemType.FULL_HEAL: 5,
            ItemType.REVIVE: 3,
            ItemType.ETHER: 2,
            ItemType.ELIXIR: 2,
            ItemType.REPEL: 3,
            ItemType.SUPER_REPEL: 2,
            ItemType.MAX_REPEL: 2,
        }

        threshold = thresholds.get(item_type, 5)
        return max(0, threshold - current)

    def calculate_budget(
        self,
        current_money: int,
        upcoming_challenges: List[str],
    ) -> Tuple[int, int]:
        """
        Calculate available shopping budget and emergency reserve.

        Returns:
            (available_budget, emergency_reserve)
        """
        emergency_reserve = int(current_money * 0.20)
        available_budget = current_money - emergency_reserve
        return available_budget, emergency_reserve

    def select_items_for_budget(
        self,
        shopping_needs: Dict[ItemType, int],
        available_budget: int,
    ) -> List[ShoppingListItem]:
        """
        Select items based on priority and budget constraints.

        Returns:
            List of ShoppingListItem sorted by priority
        """
        priority_map: Dict[ItemType, ShoppingPriority] = {
            ItemType.POTION: ShoppingPriority.CRITICAL,
            ItemType.SUPER_POTION: ShoppingPriority.HIGH,
            ItemType.HYPER_POTION: ShoppingPriority.HIGH,
            ItemType.POKE_BALL: ShoppingPriority.CRITICAL,
            ItemType.GREAT_BALL: ShoppingPriority.HIGH,
            ItemType.ANTIDOTE: ShoppingPriority.HIGH,
            ItemType.PARALYZE_HEAL: ShoppingPriority.HIGH,
            ItemType.BURN_HEAL: ShoppingPriority.MEDIUM,
            ItemType.ICE_HEAL: ShoppingPriority.MEDIUM,
            ItemType.AWAKENING: ShoppingPriority.MEDIUM,
            ItemType.FULL_HEAL: ShoppingPriority.HIGH,
            ItemType.REVIVE: ShoppingPriority.CRITICAL,
            ItemType.ETHER: ShoppingPriority.MEDIUM,
            ItemType.ELIXIR: ShoppingPriority.MEDIUM,
            ItemType.REPEL: ShoppingPriority.MEDIUM,
            ItemType.SUPER_REPEL: ShoppingPriority.MEDIUM,
            ItemType.MAX_REPEL: ShoppingPriority.LOW,
            ItemType.X_ATTACK: ShoppingPriority.LOW,
            ItemType.X_DEFEND: ShoppingPriority.LOW,
            ItemType.X_SPEED: ShoppingPriority.LOW,
            ItemType.RARE_CANDY: ShoppingPriority.LOW,
        }

        scored_items: List[ShoppingListItem] = []

        for item_type, quantity in shopping_needs.items():
            cost = ShoppingHeuristic.ITEM_COSTS.get(item_type, 0)
            if cost == 0:
                continue

            priority = priority_map.get(item_type, ShoppingPriority.MEDIUM)
            total_cost = cost * quantity
            reason = f"Need {quantity} {item_type.value} (Priority: {priority.name})"

            scored_items.append(ShoppingListItem(
                item_type=item_type,
                quantity=quantity,
                priority=priority,
                estimated_cost=total_cost,
                reason=reason,
            ))

        scored_items.sort(key=lambda x: x.priority.value, reverse=True)

        selected_items: List[ShoppingListItem] = []
        remaining_budget = available_budget

        for item in scored_items:
            if item.estimated_cost <= remaining_budget:
                selected_items.append(item)
                remaining_budget -= item.estimated_cost
            elif item.estimated_cost > remaining_budget and remaining_budget > 0:
                affordable_qty = remaining_budget // ShoppingHeuristic.ITEM_COSTS.get(item.item_type, 1)
                if affordable_qty > 0:
                    new_cost = affordable_qty * ShoppingHeuristic.ITEM_COSTS.get(item.item_type, 1)
                    new_item = ShoppingListItem(
                        item_type=item.item_type,
                        quantity=affordable_qty,
                        priority=item.priority,
                        estimated_cost=new_cost,
                        reason=f"Partial purchase: {affordable_qty} of {item.quantity}",
                    )
                    selected_items.append(new_item)
                    remaining_budget = 0

        return selected_items

    def find_best_shop(self, current_location: str) -> str:
        """Find best shop for current location based on prices"""
        shop_locations: Dict[str, str] = {
            "Pallet Town": "Viridian City PokeMart",
            "Viridian City": "Viridian City PokeMart",
            "Pewter City": "Pewter City PokeMart",
            "Cerulean City": "Cerulean City PokeMart",
            "Lavender Town": "Lavender Town PokeMart",
            "Vermilion City": "Vermilion City PokeMart",
            "Celadon City": "Celadon City PokeMart",
            "Fuchsia City": "Fuchsia City PokeMart",
            "Cinnabar Island": "Cinnabar Island PokeMart",
            "Indigo Plateau": "Indigo Plateau PokeMart",
        }

        return shop_locations.get(current_location, "Viridian City PokeMart")

    def get_restock_threshold(self, item_type: ItemType) -> int:
        """Get restock threshold for an item type"""
        thresholds: Dict[ItemType, int] = {
            ItemType.POTION: 5,
            ItemType.SUPER_POTION: 3,
            ItemType.HYPER_POTION: 2,
            ItemType.POKE_BALL: 10,
            ItemType.GREAT_BALL: 3,
            ItemType.ULTRA_BALL: 2,
            ItemType.FULL_HEAL: 3,
            ItemType.REVIVE: 2,
            ItemType.ETHER: 2,
            ItemType.ELIXIR: 2,
            ItemType.REPEL: 3,
            ItemType.SUPER_REPEL: 2,
            ItemType.MAX_REPEL: 2,
        }

        return thresholds.get(item_type, 5)

    def should_restock(self, item_type: ItemType) -> bool:
        """Check if item should be restocked"""
        current = self._inventory.get_quantity(item_type)
        threshold = self.get_restock_threshold(item_type)
        return current < threshold

    def get_early_game_essentials(self) -> List[ItemType]:
        """Get essential items for early game"""
        return [
            ItemType.POTION,
            ItemType.POKE_BALL,
            ItemType.ANTIDOTE,
        ]

    def get_late_game_essentials(self) -> List[ItemType]:
        """Get essential items for late game"""
        return [
            ItemType.HYPER_POTION,
            ItemType.FULL_HEAL,
            ItemType.REVIVE,
            ItemType.MAX_REPEL,
        ]

    def get_gym_specific_items(self, gym_type: str) -> Dict[ItemType, int]:
        """Get items needed for specific gym battles"""
        return ShoppingHeuristic.GYM_SPECIFIC_ITEMS.get(gym_type, {})


class PokemonCenterProtocol:
    """
    Pokemon Center healing and party management protocol.

    Responsibilities:
    - Heal trigger (low HP party percentage, default: 50%)
    - Optimal healing order (prioritize usable Pokemon)
    - Exit behavior (resume previous goal after healing)
    - Money management for healing costs
    """

    def __init__(self, inventory: InventoryState):
        self._inventory = inventory
        self._heal_threshold_percent: float = 50.0
        self._critical_threshold_percent: float = 20.0
        self._exit_destination: Optional[str] = None
        self._pc_swaps_max = 2

    def set_heal_thresholds(
        self,
        heal_percent: float = 50.0,
        critical_percent: float = 20.0,
    ) -> None:
        """Configure heal trigger thresholds"""
        self._heal_threshold_percent = heal_percent
        self._critical_threshold_percent = critical_percent

    def assess_healing_need(self, party_state: PartyState) -> Tuple[bool, HealingPriority, str]:
        """
        Assess if party needs healing and at what priority.

        Returns:
            (needs_healing, priority_level, reason)
        """
        lowest_hp = party_state.get_lowest_hp_percent()
        fainted = party_state.get_fainted_count()
        status = party_state.get_status_count()
        total_pp = party_state.get_total_pp_remaining()
        max_pp = party_state.get_total_pp_max()
        pp_percent = total_pp / max_pp if max_pp > 0 else 1.0

        if fainted > 0 or lowest_hp < 0.10:
            return True, HealingPriority.CRITICAL, f"{fainted} fainted, lowest HP {lowest_hp:.1%}"
        elif status > 0 or lowest_hp < 0.25:
            return True, HealingPriority.HIGH, f"{status} status, lowest HP {lowest_hp:.1%}"
        elif lowest_hp < 0.50:
            return True, HealingPriority.MEDIUM, f"Lowest HP {lowest_hp:.1%}"
        elif pp_percent < 0.30:
            return True, HealingPriority.MEDIUM, f"PP exhausted ({total_pp}/{max_pp})"
        return False, HealingPriority.LOW, "Party healthy"

    def get_healing_priority(self, party_state: PartyState) -> List[int]:
        """
        Get indices of Pokemon to heal in priority order.

        Returns:
            List of party indices sorted by healing priority
        """
        indices = list(range(len(party_state.pokemon)))
        indices.sort(
            key=lambda i: (
                party_state.pokemon[i].current_hp / party_state.pokemon[i].max_hp
                if party_state.pokemon[i].max_hp > 0 else 1.0
            )
        )
        return indices

    def should_navigate_to_center(self, party_state: PartyState) -> bool:
        """Determine if navigation to Pokemon Center is needed"""
        needs_healing, _, _ = self.assess_healing_need(party_state)
        return needs_healing

    def calculate_healing_cost(self, party_state: PartyState) -> int:
        """Calculate cost for Pokemon Center healing (always free in Gen 1)"""
        return 0

    def get_nearest_center_location(self, current_location: str) -> Optional[str]:
        """Get nearest Pokemon Center location from current position"""
        center_locations: Dict[str, str] = {
            "Pallet Town": "Pallet Town Pokemon Center",
            "Viridian City": "Viridian City Pokemon Center",
            "Pewter City": "Pewter City Pokemon Center",
            "Cerulean City": "Cerulean City Pokemon Center",
            "Route 5": "Cerulean City Pokemon Center",
            "Lavender Town": "Lavender Town Pokemon Center",
            "Route 10": "Lavender Town Pokemon Center",
            "Vermilion City": "Vermilion City Pokemon Center",
            "Celadon City": "Celadon City Pokemon Center",
            "Fuchsia City": "Fuchsia City Pokemon Center",
            "Route 18": "Fuchsia City Pokemon Center",
            "Cinnabar Island": "Cinnabar Island Pokemon Center",
            "Indigo Plateau": "Indigo Plateau Pokemon Center",
        }

        return center_locations.get(current_location)

    def execute_center_protocol(
        self,
        party_state: PartyState,
        pc_box_state: Optional[List[PokemonState]] = None,
        upcoming_challenges: Optional[List[str]] = None,
    ) -> Tuple[bool, PartyState]:
        """
        Execute complete Pokemon Center visit: heal + optional PC.

        Returns:
            (success, updated_party_state)
        """
        needs_healing, priority, reason = self.assess_healing_need(party_state)

        if not needs_healing:
            return True, party_state

        new_party = []
        for pokemon in party_state.pokemon:
            new_state = PokemonState(
                species=pokemon.species,
                level=pokemon.level,
                current_hp=pokemon.max_hp,
                max_hp=pokemon.max_hp,
                status="NONE",
                moves=pokemon.moves,
                move_pp=dict(pokemon.move_max_pp),
                move_max_pp=dict(pokemon.move_max_pp),
            )
            new_party.append(new_state)

        updated_state = PartyState(
            pokemon=new_party,
            money=party_state.money,
        )

        return True, updated_state

    def assess_pc_needs(
        self,
        party_state: PartyState,
        pc_box_state: List[PokemonState],
        upcoming_challenges: List[str],
    ) -> List[Tuple[int, int]]:
        """
        Analyze if PC swaps are needed for optimal party composition.

        Returns:
            List of (deposit_index, withdraw_index) tuples
        """
        swaps: List[Tuple[int, int]] = []

        if not pc_box_state or len(pc_box_state) == 0:
            return swaps

        party_scores = self._calculate_carry_scores(party_state.pokemon)
        box_scores = self._calculate_carry_scores(pc_box_state)

        low_party_indices = [i for i, score in enumerate(party_scores) if score < 50]
        high_box_indices = [i for i, score in enumerate(box_scores) if score >= 50]

        for party_idx in low_party_indices:
            if not high_box_indices:
                break
            box_idx = high_box_indices.pop(0)
            swaps.append((party_idx, box_idx))

        return swaps[:self._pc_swaps_max]

    def _calculate_carry_scores(self, pokemon_list: List[PokemonState]) -> List[int]:
        """Calculate carry scores for Pokemon list"""
        scores = []
        for pokemon in pokemon_list:
            score = 0
            score += pokemon.level * 2
            if pokemon.max_hp > 100:
                score += 20
            if pokemon.status == "NONE" and pokemon.current_hp > 0:
                score += 30
            score += len(pokemon.moves) * 5
            scores.append(score)
        return scores

    def get_exit_destination(self) -> Optional[str]:
        """Get destination to return to after healing"""
        return self._exit_destination

    def set_exit_destination(self, destination: str) -> None:
        """Set destination to resume after healing"""
        self._exit_destination = destination


class ItemUsageStrategy:
    """
    Battle item usage optimization and waste prevention.

    Responsibilities:
    - Potion timing (not too early, not too late)
    - Status item usage (Paralyze Heal, Awakening, etc.)
    - Rare candy optimization (level timing, XP efficiency)
    - No waste scenarios (no overhealing, no unused TMs)
    """

    STATUS_CURE_MAP: Dict[str, ItemType] = {
        "POISONED": ItemType.ANTIDOTE,
        "BURNED": ItemType.BURN_HEAL,
        "PARALYZED": ItemType.PARALYZE_HEAL,
        "FROZEN": ItemType.ICE_HEAL,
        "ASLEEP": ItemType.AWAKENING,
    }

    def __init__(self, inventory: InventoryState):
        self._inventory = inventory

    def select_battle_item(
        self,
        party_state: PartyState,
        active_index: int,
        enemy_info: Optional[Dict[str, Any]] = None,
        is_trainer_battle: bool = False,
    ) -> Tuple[Optional[ItemType], Optional[int]]:
        """
        Select optimal item to use in battle.

        Args:
            party_state: Current party state
            active_index: Index of active Pokemon
            enemy_info: Optional enemy Pokemon information
            is_trainer_battle: Whether this is a trainer battle

        Returns:
            (item_type, target_index) or (None, None) if no item needed
        """
        if active_index < 0 or active_index >= len(party_state.pokemon):
            return None, None

        active_pokemon = party_state.pokemon[active_index]
        hp_percent = active_pokemon.current_hp / active_pokemon.max_hp if active_pokemon.max_hp > 0 else 0
        status = active_pokemon.status

        healthy_count = party_state.get_healthy_count()

        if hp_percent < 0.10:
            if healthy_count > 1:
                if self._inventory.has_item(ItemType.MAX_POTION):
                    return ItemType.MAX_POTION, active_index
                elif self._inventory.has_item(ItemType.HYPER_POTION):
                    return ItemType.HYPER_POTION, active_index
                elif self._inventory.has_item(ItemType.SUPER_POTION):
                    return ItemType.SUPER_POTION, active_index
                elif self._inventory.has_item(ItemType.POTION):
                    return ItemType.POTION, active_index
            else:
                if self._inventory.has_item(ItemType.MAX_POTION):
                    return ItemType.MAX_POTION, active_index
                elif self._inventory.has_item(ItemType.HYPER_POTION):
                    return ItemType.HYPER_POTION, active_index
                elif self._inventory.has_item(ItemType.SUPER_POTION):
                    return ItemType.SUPER_POTION, active_index
                elif self._inventory.has_item(ItemType.POTION):
                    return ItemType.POTION, active_index
                elif self._inventory.has_item(ItemType.FULL_RESTORE):
                    return ItemType.FULL_RESTORE, active_index

        if status in ["PARALYZED", "ASLEEP", "FROZEN"]:
            if status == "PARALYZED" and self._inventory.has_item(ItemType.PARALYZE_HEAL):
                return ItemType.PARALYZE_HEAL, active_index
            elif status == "ASLEEP" and self._inventory.has_item(ItemType.AWAKENING):
                return ItemType.AWAKENING, active_index
            elif status == "FROZEN" and self._inventory.has_item(ItemType.ICE_HEAL):
                return ItemType.ICE_HEAL, active_index

        if hp_percent < 0.50 and hp_percent >= 0.10:
            if self._inventory.has_item(ItemType.MAX_POTION):
                return ItemType.MAX_POTION, active_index
            elif self._inventory.has_item(ItemType.HYPER_POTION):
                return ItemType.HYPER_POTION, active_index
            elif self._inventory.has_item(ItemType.SUPER_POTION):
                return ItemType.SUPER_POTION, active_index
            elif self._inventory.has_item(ItemType.POTION):
                return ItemType.POTION, active_index

        if status in ["POISONED", "BURNED"]:
            if status == "POISONED" and self._inventory.has_item(ItemType.ANTIDOTE):
                return ItemType.ANTIDOTE, active_index
            elif status == "BURNED" and self._inventory.has_item(ItemType.BURN_HEAL):
                return ItemType.BURN_HEAL, active_index

        total_pp = sum(active_pokemon.move_pp.values())
        if total_pp == 0 and self._inventory.has_item(ItemType.ELIXIR):
            return ItemType.ELIXIR, active_index
        elif total_pp == 0 and self._inventory.has_item(ItemType.ETHER):
            return ItemType.ETHER, active_index

        if is_trainer_battle:
            if self._inventory.has_item(ItemType.X_ATTACK):
                return ItemType.X_ATTACK, active_index
            elif self._inventory.has_item(ItemType.X_DEFEND):
                return ItemType.X_DEFEND, active_index
            elif self._inventory.has_item(ItemType.X_SPEED):
                return ItemType.X_SPEED, active_index

        return None, None

    def should_use_potion(
        self,
        pokemon: PokemonState,
        current_hp_percent: float,
        battle_context: Dict[str, Any],
    ) -> bool:
        """Determine if potion should be used"""
        if current_hp_percent < 0.10:
            return True
        if current_hp_percent < 0.50 and battle_context.get("is_trainer_battle", False):
            return True
        return False

    def select_potion_type(
        self,
        pokemon: PokemonState,
        available_potions: Dict[ItemType, int],
    ) -> Optional[ItemType]:
        """Select most efficient potion type for the situation"""
        if not available_potions:
            return None

        hp_percent = pokemon.current_hp / pokemon.max_hp if pokemon.max_hp > 0 else 0
        missing_hp = pokemon.max_hp - pokemon.current_hp

        potion_power: Dict[ItemType, int] = {
            ItemType.HYPER_POTION: 200,
            ItemType.SUPER_POTION: 50,
            ItemType.POTION: 20,
            ItemType.MAX_POTION: 999,
            ItemType.FULL_RESTORE: 999,
        }

        best_potion = None
        best_efficiency = 0

        for potion_type, power in potion_power.items():
            if potion_type in available_potions:
                heal_amount = min(power, missing_hp)
                cost = ShoppingHeuristic.ITEM_COSTS.get(potion_type, 9999)
                if cost > 0:
                    efficiency = heal_amount / cost
                    if efficiency > best_efficiency:
                        best_efficiency = efficiency
                        best_potion = potion_type

        return best_potion

    def should_use_status_cure(
        self,
        pokemon: PokemonState,
        battle_context: Dict[str, Any],
    ) -> bool:
        """Determine if status cure should be used"""
        blocking_statuses = ["PARALYZED", "ASLEEP", "FROZEN"]
        if pokemon.status in blocking_statuses:
            return True
        if pokemon.status in ["POISONED", "BURNED"] and battle_context.get("is_trainer_battle", False):
            return True
        return False

    def select_status_cure(
        self,
        pokemon: PokemonState,
        available_cures: Dict[ItemType, int],
    ) -> Optional[ItemType]:
        """Select appropriate status cure item"""
        if not available_cures or pokemon.status == "NONE":
            return None

        cure_item = ItemUsageStrategy.STATUS_CURE_MAP.get(pokemon.status)
        if cure_item and cure_item in available_cures:
            return cure_item

        if self._inventory.has_item(ItemType.FULL_HEAL):
            return ItemType.FULL_HEAL

        return None

    def calculate_item_value(
        self,
        item_type: ItemType,
        party_state: PartyState,
        battle_context: Dict[str, Any],
    ) -> float:
        """
        Calculate value score for an item based on current situation.
        Higher score = higher priority.
        """
        base_value = 1.0

        lowest_hp = party_state.get_lowest_hp_percent()
        status_count = party_state.get_status_count()

        urgency = 1.0
        if item_type in [ItemType.POTION, ItemType.SUPER_POTION, ItemType.HYPER_POTION]:
            if lowest_hp < 0.20:
                urgency = 3.0
            elif lowest_hp < 0.50:
                urgency = 2.0
            elif lowest_hp < 0.75:
                urgency = 1.5

        if item_type in [ItemType.ANTIDOTE, ItemType.BURN_HEAL, ItemType.ICE_HEAL,
                         ItemType.AWAKENING, ItemType.PARALYZE_HEAL, ItemType.FULL_HEAL]:
            if status_count > 0:
                urgency = 2.5 * status_count

        cost = ShoppingHeuristic.ITEM_COSTS.get(item_type, 0)
        healing_power = ShoppingHeuristic.HEALING_POWER.get(item_type, 0)
        cost_efficiency = 1.0
        if cost > 0 and healing_power > 0:
            cost_efficiency = min(max(healing_power / cost * 10, 0.5), 1.5)

        final_score = base_value * urgency * cost_efficiency
        return final_score

    def calculate_potion_efficiency(
        self,
        potion_type: ItemType,
        current_hp: int,
        max_hp: int,
    ) -> float:
        """Calculate efficiency of using a potion (avoid overhealing)"""
        missing_hp = max_hp - current_hp
        if missing_hp <= 0:
            return 0.0

        power = ShoppingHeuristic.HEALING_POWER.get(potion_type, 0)
        if power == 0:
            return 1.0

        actual_heal = min(power, missing_hp)
        efficiency = actual_heal / power

        return efficiency

    def should_use_rare_candy(
        self,
        pokemon: PokemonState,
        party_state: PartyState,
        upcoming_challenges: List[str],
    ) -> bool:
        """Determine if Rare Candy should be used on this Pokemon"""
        if not self._inventory.has_item(ItemType.RARE_CANDY):
            return False

        if pokemon.level >= 100:
            return False

        avg_level = party_state.get_avg_level()
        if pokemon.level < avg_level - 5:
            return True

        if pokemon.level >= 50 and pokemon.level < 100:
            return True

        return False

    def get_optimal_candy_target(
        self,
        party_state: PartyState,
        upcoming_challenges: List[str],
    ) -> Optional[int]:
        """Get index of best Pokemon to use Rare Candy on"""
        if not self._inventory.has_item(ItemType.RARE_CANDY):
            return None

        best_index = None
        best_score = -1

        for i, pokemon in enumerate(party_state.pokemon):
            if pokemon.level >= 100:
                continue

            score = 0
            score += (100 - pokemon.level) * 2
            score += pokemon.max_hp / 10

            if pokemon.status == "NONE" and pokemon.current_hp > 0:
                score += 50

            avg_level = party_state.get_avg_level()
            if pokemon.level < avg_level - 10:
                score += 30

            if score > best_score:
                best_score = score
                best_index = i

        return best_index

    def should_use_x_item(
        self,
        battle_context: Dict[str, Any],
    ) -> bool:
        """Determine if X items should be used in this battle"""
        if not battle_context.get("is_trainer_battle", False):
            return False

        turn_number = battle_context.get("turn_number", 1)
        if turn_number > 3:
            return False

        return True

    def select_x_item(
        self,
        battle_context: Dict[str, Any],
    ) -> Optional[ItemType]:
        """Select which X item to use"""
        if not self.should_use_x_item(battle_context):
            return None

        enemy_type = battle_context.get("enemy_type", "")

        if enemy_type in ["ROCK", "GROUND", "FIGHTING"]:
            if self._inventory.has_item(ItemType.X_DEFEND):
                return ItemType.X_DEFEND
        elif enemy_type in ["GHOST", "PSYCHIC"]:
            if self._inventory.has_item(ItemType.X_SPEED):
                return ItemType.X_SPEED

        if self._inventory.has_item(ItemType.X_ATTACK):
            return ItemType.X_ATTACK
        elif self._inventory.has_item(ItemType.X_DEFEND):
            return ItemType.X_DEFEND
        elif self._inventory.has_item(ItemType.X_SPEED):
            return ItemType.X_SPEED

        return None

    def evaluate_repel_usage(
        self,
        party_state: PartyState,
        current_location: str,
        upcoming_route: str,
    ) -> Tuple[bool, Optional[ItemType], str]:
        """
        Evaluate if Repel should be used.

        Returns:
            (should_use, repel_type, reason)
        """
        avg_level = party_state.get_avg_level()

        if upcoming_route in ShoppingHeuristic.ROUTE_SHOPPING_NEEDS:
            route_data = ShoppingHeuristic.ROUTE_SHOPPING_NEEDS[upcoming_route]
            max_wild_level = route_data.get("max_wild_level", 99)

            if avg_level > max_wild_level + 10:
                if self._inventory.has_item(ItemType.MAX_REPEL):
                    return True, ItemType.MAX_REPEL, f"Party level {avg_level} >> wild levels"
                elif self._inventory.has_item(ItemType.SUPER_REPEL):
                    return True, ItemType.SUPER_REPEL, f"Party level {avg_level} >> wild levels"
                elif self._inventory.has_item(ItemType.REPEL):
                    return True, ItemType.REPEL, f"Party level {avg_level} >> wild levels"

        route_length = 50
        if upcoming_route in ShoppingHeuristic.ROUTE_SHOPPING_NEEDS:
            route_data = ShoppingHeuristic.ROUTE_SHOPPING_NEEDS[upcoming_route]
            route_length = route_data.get("recommended_potions", 50)

        if route_length > 100:
            if self._inventory.has_item(ItemType.MAX_REPEL):
                return True, ItemType.MAX_REPEL, f"Long route ({route_length} tiles)"
        elif route_length > 50:
            if self._inventory.has_item(ItemType.SUPER_REPEL):
                return True, ItemType.SUPER_REPEL, f"Medium route ({route_length} tiles)"

        return False, None, ""

    def get_no_waste_items(self) -> List[ItemType]:
        """Get list of items that should never be wasted"""
        return [
            ItemType.MASTER_BALL,
            ItemType.RARE_CANDY,
            ItemType.MAX_REVIVE,
        ]

    def check_waste_prevention(
        self,
        item_type: ItemType,
        target_state: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Check if using item would be wasteful.

        Returns:
            (is_wasteful, reason)
        """
        no_waste = self.get_no_waste_items()
        if item_type in no_waste:
            return False, ""

        if item_type in [ItemType.HYPER_POTION, ItemType.MAX_POTION, ItemType.FULL_RESTORE]:
            current_hp = target_state.get("current_hp", 0)
            max_hp = target_state.get("max_hp", 1)
            missing_hp = max_hp - current_hp
            healing_power = ShoppingHeuristic.HEALING_POWER.get(item_type, 0)

            if healing_power > 0 and missing_hp < healing_power * 0.3:
                return True, f"Only {missing_hp} HP missing, {healing_power} would be wasted"

        return False, ""


class InventoryManager:
    """
    Main inventory management class integrating all components.

    Integration point for:
    - Vision system for item reading
    - GOAP for shopping/healing goals
    - Combat for battle item usage
    - Navigation for Mart/Center locations
    """

    def __init__(self):
        self._inventory = InventoryState()
        self._shopping = ShoppingHeuristic(self._inventory)
        self._center = PokemonCenterProtocol(self._inventory)
        self._item_usage = ItemUsageStrategy(self._inventory)

    @property
    def inventory(self) -> InventoryState:
        return self._inventory

    @property
    def shopping(self) -> ShoppingHeuristic:
        return self._shopping

    @property
    def center(self) -> PokemonCenterProtocol:
        return self._center

    @property
    def item_usage(self) -> ItemUsageStrategy:
        return self._item_usage

    def process_vision_update(self, vision_data: Dict[str, Any]) -> None:
        """Process vision system update for inventory changes"""
        item_readings = vision_data.get("item_readings", [])
        for reading in item_readings:
            item_type_str = reading.get("item_type", "")
            quantity = reading.get("quantity", 0)

            try:
                item_type = ItemType(item_type_str)
                if quantity > 0:
                    self._inventory.add_item(item_type, quantity)
                else:
                    self._inventory.remove_item(item_type, abs(quantity))
            except ValueError:
                logger.warning(f"Unknown item type from vision: {item_type_str}")

    def get_shopping_goal(self, party_state: PartyState, money: int) -> Optional[ShoppingPlan]:
        """Generate shopping goal for GOAP planner"""
        return self._shopping.generate_shopping_list(party_state, None, money)

    def get_healing_goal(self, party_state: PartyState) -> Optional[Tuple[bool, HealingPriority, str]]:
        """Generate healing goal for GOAP planner"""
        return self._center.assess_healing_need(party_state)

    def get_battle_item_decision(
        self,
        party_state: PartyState,
        active_index: int,
        battle_context: Dict[str, Any],
    ) -> Tuple[Optional[ItemType], Optional[int]]:
        """Get item decision for combat module"""
        return self._item_usage.select_battle_item(
            party_state, active_index, None, battle_context.get("is_trainer_battle", False)
        )

    def record_item_usage(self, item_type: ItemType, context: Dict[str, Any]) -> None:
        """Record item usage for learning/optimization"""
        self._inventory.consume_item(item_type)

    def get_inventory_report(self) -> Dict[str, Any]:
        """Get comprehensive inventory report"""
        return {
            "inventory_summary": self._inventory.get_bag_summary(),
            "shopping_needs": [],
            "healing_status": {},
            "item_usage_stats": {},
        }