"""
Unit Tests for Inventory & Item Management System

Tests cover:
- InventoryState: Item tracking, categories, add/remove/consume methods
- ShoppingHeuristic: Shopping list generation, budget management
- PokemonCenterProtocol: Healing assessment, center protocol
- ItemUsageStrategy: Battle item selection, potion efficiency
- InventoryManager: Integration layer
"""

import pytest
from datetime import datetime
from src.core.inventory import (
    ItemCategory,
    ItemType,
    HealingPriority,
    ShoppingPriority,
    ItemData,
    InventoryItem,
    TMData,
    KeyItem,
    PokemonState,
    PartyState,
    ShoppingListItem,
    ShoppingPlan,
    InventoryState,
    ShoppingHeuristic,
    PokemonCenterProtocol,
    ItemUsageStrategy,
    InventoryManager,
)


class TestInventoryItem:
    """Tests for InventoryItem class"""

    def test_item_creation_with_defaults(self):
        item = InventoryItem(item_type=ItemType.POTION)
        assert item.quantity == 1
        assert item.max_quantity == 99
        assert not item.is_empty
        assert not item.is_full

    def test_item_add_within_capacity(self):
        item = InventoryItem(item_type=ItemType.POTION, quantity=5)
        added = item.add(10)
        assert added == 10
        assert item.quantity == 15

    def test_item_add_exceeds_capacity(self):
        item = InventoryItem(item_type=ItemType.POTION, quantity=95)
        added = item.add(10)
        assert added == 4
        assert item.quantity == 99

    def test_item_remove_within_quantity(self):
        item = InventoryItem(item_type=ItemType.POTION, quantity=10)
        removed = item.remove(3)
        assert removed == 3
        assert item.quantity == 7

    def test_item_remove_exceeds_quantity(self):
        item = InventoryItem(item_type=ItemType.POTION, quantity=5)
        removed = item.remove(10)
        assert removed == 5
        assert item.quantity == 0

    def test_item_consume_success(self):
        item = InventoryItem(item_type=ItemType.POTION, quantity=3)
        result = item.consume()
        assert result is True
        assert item.quantity == 2

    def test_item_consume_failure(self):
        item = InventoryItem(item_type=ItemType.POTION, quantity=0)
        result = item.consume()
        assert result is False

    def test_is_empty_property(self):
        item = InventoryItem(item_type=ItemType.POTION, quantity=0)
        assert item.is_empty is True
        item.quantity = 1
        assert item.is_empty is False

    def test_is_full_property(self):
        item = InventoryItem(item_type=ItemType.POTION, quantity=99)
        assert item.is_full is True
        item.quantity = 98
        assert item.is_full is False


class TestPokemonState:
    """Tests for PokemonState dataclass"""

    def test_pokemon_state_creation(self):
        pokemon = PokemonState(
            species="Pikachu",
            level=25,
            current_hp=50,
            max_hp=80,
            status="NONE",
            moves=["Thunderbolt", "Quick Attack"],
            move_pp={"Thunderbolt": 15, "Quick Attack": 30},
            move_max_pp={"Thunderbolt": 30, "Quick Attack": 30},
        )
        assert pokemon.species == "Pikachu"
        assert pokemon.level == 25
        assert pokemon.current_hp == 50


class TestPartyState:
    """Tests for PartyState dataclass"""

    @pytest.fixture
    def sample_party(self):
        return PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=50,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
                PokemonState(
                    species="Charizard",
                    level=30,
                    current_hp=100,
                    max_hp=120,
                    status="NONE",
                    moves=["Flamethrower"],
                    move_pp={"Flamethrower": 10},
                    move_max_pp={"Flamethrower": 15},
                ),
                PokemonState(
                    species="Squirtle",
                    level=20,
                    current_hp=0,
                    max_hp=60,
                    status="NONE",
                    moves=["Water Gun"],
                    move_pp={"Water Gun": 20},
                    move_max_pp={"Water Gun": 30},
                ),
            ],
            money=5000,
        )

    def test_get_avg_level(self, sample_party):
        avg = sample_party.get_avg_level()
        assert avg == pytest.approx(25.0, rel=0.01)

    def test_get_avg_hp_percent(self, sample_party):
        avg = sample_party.get_avg_hp_percent()
        total_hp = 50 + 100 + 0
        max_hp = 80 + 120 + 60
        expected = total_hp / max_hp
        assert avg == pytest.approx(expected, rel=0.01)

    def test_get_lowest_hp_percent(self, sample_party):
        lowest = sample_party.get_lowest_hp_percent()
        assert lowest == pytest.approx(0.0, rel=0.01)

    def test_get_fainted_count(self, sample_party):
        assert sample_party.get_fainted_count() == 1

    def test_get_status_count(self, sample_party):
        assert sample_party.get_status_count() == 0

    def test_get_healthy_count(self, sample_party):
        assert sample_party.get_healthy_count() == 2

    def test_empty_party_returns_defaults(self):
        empty_party = PartyState(pokemon=[], money=0)
        assert empty_party.get_avg_level() == 0.0
        assert empty_party.get_avg_hp_percent() == 0.0
        assert empty_party.get_lowest_hp_percent() == 1.0


class TestInventoryState:
    """Tests for InventoryState class - using unique items to avoid test interference"""

    def test_initial_state_empty(self):
        inv = InventoryState()
        inv.clear_inventory()
        summary = inv.get_bag_summary()
        assert summary["total_items"] == 0
        assert summary["total_quantity"] == 0

    def test_add_item_potions(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.HYPER_POTION, 5)
        assert inv.get_quantity(ItemType.HYPER_POTION) == 5

    def test_add_item_creates_new(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.MAX_POTION, 3)
        item = inv.get_item(ItemType.MAX_POTION)
        assert item is not None
        assert item.quantity == 3

    def test_remove_item_pokeballs(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.ULTRA_BALL, 10)
        removed = inv.remove_item(ItemType.ULTRA_BALL, 3)
        assert removed == 3
        assert inv.get_quantity(ItemType.ULTRA_BALL) == 7

    def test_remove_item_nonexistent(self):
        inv = InventoryState()
        inv.clear_inventory()
        removed = inv.remove_item(ItemType.MASTER_BALL, 1)
        assert removed == 0

    def test_consume_item_status_cure(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.FULL_HEAL, 2)
        result = inv.consume_item(ItemType.FULL_HEAL)
        assert result is True
        assert inv.get_quantity(ItemType.FULL_HEAL) == 1

    def test_consume_item_empty(self):
        inv = InventoryState()
        inv.clear_inventory()
        result = inv.consume_item(ItemType.ANTIDOTE)
        assert result is False

    def test_has_item_balls(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.GREAT_BALL, 10)
        assert inv.has_item(ItemType.GREAT_BALL) is True
        assert inv.has_item(ItemType.GREAT_BALL, 15) is False

    def test_get_by_category(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.SUPER_POTION, 5)
        inv.add_item(ItemType.HYPER_POTION, 3)
        inv.add_item(ItemType.GREAT_BALL, 10)

        potions = inv.get_by_category(ItemCategory.POTION)
        assert len(potions) == 2

        balls = inv.get_by_category(ItemCategory.POKEBALL)
        assert len(balls) == 1

    def test_get_potions(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.MAX_POTION, 5)
        inv.add_item(ItemType.FULL_RESTORE, 3)
        inv.add_item(ItemType.BURN_HEAL, 2)

        potions = inv.get_potions()
        assert ItemType.MAX_POTION in potions
        assert ItemType.FULL_RESTORE in potions
        assert ItemType.BURN_HEAL not in potions

    def test_get_pokeballs(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.SAFARI_BALL, 10)
        inv.add_item(ItemType.MASTER_BALL, 5)

        balls = inv.get_pokeballs()
        assert ItemType.SAFARI_BALL in balls
        assert ItemType.MASTER_BALL in balls

    def test_get_status_cures(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.AWAKENING, 3)
        inv.add_item(ItemType.PARALYZE_HEAL, 2)

        cures = inv.get_status_cures()
        assert ItemType.AWAKENING in cures
        assert ItemType.PARALYZE_HEAL in cures

    def test_get_tm_count_empty(self):
        inv = InventoryState()
        inv.clear_inventory()
        assert inv.get_tm_count() == 0

    def test_obtain_key_item(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.obtain_key_item(ItemType.ITEMFINDER)
        key_item = inv.get_key_item(ItemType.ITEMFINDER)
        assert key_item is not None
        assert key_item.obtained is True
        assert key_item.obtained_time is not None

    def test_use_key_item(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.obtain_key_item(ItemType.OLD_ROD)
        inv.use_key_item(ItemType.OLD_ROD, "Route 25")
        key_item = inv.get_key_item(ItemType.OLD_ROD)
        assert key_item.used is True
        assert key_item.use_location == "Route 25"

    def test_get_bag_summary(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.HYPER_POTION, 5)
        inv.add_item(ItemType.ULTRA_BALL, 10)

        summary = inv.get_bag_summary()
        assert summary["total_items"] == 2
        assert summary["total_quantity"] == 15

    def test_validate_inventory_valid(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.MAX_POTION, 15)
        is_valid, errors = inv.validate_inventory()
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_inventory_negative_quantity(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.FULL_HEAL, 5)
        item = inv.get_item(ItemType.FULL_HEAL)
        item.quantity = -1

        is_valid, errors = inv.validate_inventory()
        assert is_valid is False
        assert len(errors) > 0

    def test_validate_inventory_overflow(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.FULL_RESTORE, 95)
        item = inv.get_item(ItemType.FULL_RESTORE)
        item.quantity = 100

        is_valid, errors = inv.validate_inventory()
        assert is_valid is False

    def test_item_database_initialized(self):
        assert len(InventoryState.ITEM_DATABASE) > 0
        assert ItemType.POTION in InventoryState.ITEM_DATABASE

    def test_tm_database_initialized(self):
        assert len(InventoryState.TM_DATABASE) > 0
        assert 1 in InventoryState.TM_DATABASE
        tm = InventoryState.TM_DATABASE[1]
        assert tm.move_name == "Cut"

    def test_tm_database_tm01(self):
        assert 1 in InventoryState.TM_DATABASE
        tm01 = InventoryState.TM_DATABASE[1]
        assert tm01.is_hm is True
        tm02 = InventoryState.TM_DATABASE[2]
        assert tm02.is_hm is True


class TestShoppingHeuristic:
    """Tests for ShoppingHeuristic class"""

    def test_calculate_budget(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        available, reserve = shopping.calculate_budget(5000, [])
        assert available == 4000
        assert reserve == 1000

    def test_calculate_budget_low_money(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        available, reserve = shopping.calculate_budget(100, [])
        assert available == 80
        assert reserve == 20

    def test_analyze_route_needs_basic(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        needs = shopping.analyze_route_needs("ROUTE_1", 10)
        assert ItemType.POTION in needs
        assert ItemType.POKE_BALL in needs

    def test_analyze_route_needs_high_level_party(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        needs = shopping.analyze_route_needs("ROUTE_3", 50)
        assert ItemType.POTION in needs

    def test_analyze_route_needs_unknown_route(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        needs = shopping.analyze_route_needs("UNKNOWN_ROUTE", 10)
        assert len(needs) == 0

    def test_calculate_quantity_needed(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.HYPER_POTION, 3)
        shopping = ShoppingHeuristic(inv)
        party = PartyState(pokemon=[], money=0)
        needed = shopping.calculate_quantity_needed(ItemType.HYPER_POTION, party)
        assert needed == 0

    def test_get_restock_threshold(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        assert shopping.get_restock_threshold(ItemType.SUPER_POTION) == 3
        assert shopping.get_restock_threshold(ItemType.GREAT_BALL) == 3
        assert shopping.get_restock_threshold(ItemType.RARE_CANDY) == 5

    def test_should_restock_true(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.SUPER_POTION, 2)
        shopping = ShoppingHeuristic(inv)
        assert shopping.should_restock(ItemType.SUPER_POTION) is True

    def test_should_restock_false(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.SUPER_POTION, 10)
        shopping = ShoppingHeuristic(inv)
        assert shopping.should_restock(ItemType.SUPER_POTION) is False

    def test_select_items_for_budget(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        needs = {
            ItemType.HYPER_POTION: 10,
            ItemType.ULTRA_BALL: 20,
        }
        items = shopping.select_items_for_budget(needs, 2000)
        assert len(items) > 0

    def test_find_best_shop(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        shop = shopping.find_best_shop("Pewter City")
        assert "Pewter City" in shop

    def test_find_best_shop_unknown(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        shop = shopping.find_best_shop("Unknown Location")
        assert "Viridian City" in shop

    def test_get_early_game_essentials(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        essentials = shopping.get_early_game_essentials()
        assert ItemType.POTION in essentials
        assert ItemType.POKE_BALL in essentials

    def test_get_late_game_essentials(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        essentials = shopping.get_late_game_essentials()
        assert ItemType.HYPER_POTION in essentials

    def test_get_gym_specific_items(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        items = shopping.get_gym_specific_items("BROCK")
        assert items is not None
        assert ItemType.POTION in items

    def test_get_gym_specific_items_unknown(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        items = shopping.get_gym_specific_items("UNKNOWN_GYM")
        assert items == {}

    def test_generate_shopping_list(self):
        inv = InventoryState()
        inv.clear_inventory()
        shopping = ShoppingHeuristic(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=50,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
                PokemonState(
                    species="Charizard",
                    level=30,
                    current_hp=100,
                    max_hp=120,
                    status="NONE",
                    moves=["Flamethrower"],
                    move_pp={"Flamethrower": 10},
                    move_max_pp={"Flamethrower": 15},
                ),
            ],
            money=5000,
        )
        plan = shopping.generate_shopping_list(party, None, 5000)
        assert isinstance(plan, ShoppingPlan)
        assert plan.total_cost >= 0
        assert plan.available_budget > 0


class TestPokemonCenterProtocol:
    """Tests for PokemonCenterProtocol class"""

    def test_assess_healing_need_healthy(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=80,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
                PokemonState(
                    species="Charizard",
                    level=30,
                    current_hp=120,
                    max_hp=120,
                    status="NONE",
                    moves=["Flamethrower"],
                    move_pp={"Flamethrower": 10},
                    move_max_pp={"Flamethrower": 15},
                ),
            ],
            money=5000,
        )
        needs, priority, reason = center.assess_healing_need(party)
        assert needs is False
        assert priority == HealingPriority.LOW

    def test_assess_healing_need_critical(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=5,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
                PokemonState(
                    species="Charizard",
                    level=30,
                    current_hp=0,
                    max_hp=120,
                    status="NONE",
                    moves=["Flamethrower"],
                    move_pp={"Flamethrower": 10},
                    move_max_pp={"Flamethrower": 15},
                ),
            ],
            money=5000,
        )
        needs, priority, reason = center.assess_healing_need(party)
        assert needs is True
        assert priority == HealingPriority.CRITICAL

    def test_assess_healing_need_status(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=50,
                    max_hp=80,
                    status="PARALYZED",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        needs, priority, reason = center.assess_healing_need(party)
        assert needs is True
        assert priority == HealingPriority.HIGH

    def test_get_healing_priority(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=5,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
                PokemonState(
                    species="Charizard",
                    level=30,
                    current_hp=0,
                    max_hp=120,
                    status="NONE",
                    moves=["Flamethrower"],
                    move_pp={"Flamethrower": 10},
                    move_max_pp={"Flamethrower": 15},
                ),
            ],
            money=5000,
        )
        indices = center.get_healing_priority(party)
        assert indices[0] == 1
        assert indices[1] == 0

    def test_should_navigate_to_center_healthy(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=80,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        assert center.should_navigate_to_center(party) is False

    def test_should_navigate_to_center_critical(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=5,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        assert center.should_navigate_to_center(party) is True

    def test_calculate_healing_cost_free(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=80,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        cost = center.calculate_healing_cost(party)
        assert cost == 0

    def test_get_nearest_center_location(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        location = center.get_nearest_center_location("Pewter City")
        assert location is not None
        assert "Pokemon Center" in location

    def test_get_nearest_center_location_unknown(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        location = center.get_nearest_center_location("Unknown")
        assert location is None

    def test_execute_center_protocol_no_healing_needed(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=80,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        success, updated = center.execute_center_protocol(party)
        assert success is True
        assert updated.pokemon[0].current_hp == 80

    def test_execute_center_protocol_heals_party(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=5,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
                PokemonState(
                    species="Charizard",
                    level=30,
                    current_hp=0,
                    max_hp=120,
                    status="NONE",
                    moves=["Flamethrower"],
                    move_pp={"Flamethrower": 10},
                    move_max_pp={"Flamethrower": 15},
                ),
            ],
            money=5000,
        )
        success, updated = center.execute_center_protocol(party)
        assert success is True
        assert updated.pokemon[0].current_hp == updated.pokemon[0].max_hp
        assert updated.pokemon[1].current_hp == updated.pokemon[1].max_hp

    def test_set_heal_thresholds(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        center.set_heal_thresholds(heal_percent=60.0, critical_percent=25.0)
        assert center._heal_threshold_percent == 60.0
        assert center._critical_threshold_percent == 25.0

    def test_set_exit_destination(self):
        inv = InventoryState()
        inv.clear_inventory()
        center = PokemonCenterProtocol(inv)
        center.set_exit_destination("Route 5")
        assert center.get_exit_destination() == "Route 5"


class TestItemUsageStrategy:
    """Tests for ItemUsageStrategy class"""

    def test_select_battle_item_critical_hp(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.MAX_POTION, 10)
        inv.add_item(ItemType.FULL_RESTORE, 5)
        inv.add_item(ItemType.FULL_HEAL, 3)
        strategy = ItemUsageStrategy(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=5,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
                PokemonState(
                    species="Charizard",
                    level=30,
                    current_hp=100,
                    max_hp=120,
                    status="NONE",
                    moves=["Flamethrower"],
                    move_pp={"Flamethrower": 10},
                    move_max_pp={"Flamethrower": 15},
                ),
            ],
            money=5000,
        )
        item, target = strategy.select_battle_item(party, 0)
        assert item in [ItemType.MAX_POTION, ItemType.FULL_RESTORE]
        assert target == 0

    def test_select_battle_item_status_paralyzed(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.PARALYZE_HEAL, 3)
        strategy = ItemUsageStrategy(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=50,
                    max_hp=80,
                    status="PARALYZED",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        item, target = strategy.select_battle_item(party, 0)
        assert item == ItemType.PARALYZE_HEAL

    def test_select_battle_item_no_need(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.MAX_POTION, 10)
        strategy = ItemUsageStrategy(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=50,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        item, target = strategy.select_battle_item(party, 0)
        assert item is None
        assert target is None

    def test_should_use_potion_critical(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        pokemon = PokemonState(
            species="Pikachu",
            level=25,
            current_hp=5,
            max_hp=80,
            status="NONE",
            moves=["Thunderbolt"],
            move_pp={"Thunderbolt": 15},
            move_max_pp={"Thunderbolt": 30},
        )
        result = strategy.should_use_potion(pokemon, 0.05, {"is_trainer_battle": False})
        assert result is True

    def test_should_use_potion_trainer_battle(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        pokemon = PokemonState(
            species="Pikachu",
            level=25,
            current_hp=50,
            max_hp=80,
            status="NONE",
            moves=["Thunderbolt"],
            move_pp={"Thunderbolt": 15},
            move_max_pp={"Thunderbolt": 30},
        )
        result = strategy.should_use_potion(pokemon, 0.40, {"is_trainer_battle": True})
        assert result is True

    def test_should_use_potion_wild_battle(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        pokemon = PokemonState(
            species="Pikachu",
            level=25,
            current_hp=50,
            max_hp=80,
            status="NONE",
            moves=["Thunderbolt"],
            move_pp={"Thunderbolt": 15},
            move_max_pp={"Thunderbolt": 30},
        )
        result = strategy.should_use_potion(pokemon, 0.40, {"is_trainer_battle": False})
        assert result is False

    def test_select_potion_type(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        pokemon = PokemonState(
            species="Pikachu",
            level=25,
            current_hp=50,
            max_hp=80,
            status="NONE",
            moves=["Thunderbolt"],
            move_pp={"Thunderbolt": 15},
            move_max_pp={"Thunderbolt": 30},
        )
        available = {
            ItemType.MAX_POTION: 3,
            ItemType.FULL_RESTORE: 5,
            ItemType.HYPER_POTION: 10,
        }
        potion = strategy.select_potion_type(pokemon, available)
        assert potion is not None

    def test_should_use_status_cure_blocking(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        pokemon = PokemonState(
            species="Pikachu",
            level=25,
            current_hp=50,
            max_hp=80,
            status="PARALYZED",
            moves=["Thunderbolt"],
            move_pp={"Thunderbolt": 15},
            move_max_pp={"Thunderbolt": 30},
        )
        result = strategy.should_use_status_cure(pokemon, {})
        assert result is True

    def test_should_use_status_cure_none(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        pokemon = PokemonState(
            species="Pikachu",
            level=25,
            current_hp=50,
            max_hp=80,
            status="NONE",
            moves=["Thunderbolt"],
            move_pp={"Thunderbolt": 15},
            move_max_pp={"Thunderbolt": 30},
        )
        result = strategy.should_use_status_cure(pokemon, {})
        assert result is False

    def test_select_status_cure(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        pokemon = PokemonState(
            species="Pikachu",
            level=25,
            current_hp=50,
            max_hp=80,
            status="POISONED",
            moves=["Thunderbolt"],
            move_pp={"Thunderbolt": 15},
            move_max_pp={"Thunderbolt": 30},
        )
        available = {ItemType.BURN_HEAL: 5}
        cure = strategy.select_status_cure(pokemon, available)
        assert cure is None

    def test_calculate_item_value(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=50,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        value = strategy.calculate_item_value(
            ItemType.HYPER_POTION,
            party,
            {"is_trainer_battle": False}
        )
        assert value >= 1.0

    def test_calculate_potion_efficiency(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        efficiency = strategy.calculate_potion_efficiency(
            ItemType.MAX_POTION,
            50,
            80
        )
        assert 0 < efficiency <= 1.0

    def test_calculate_potion_efficiency_no_heal_needed(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        efficiency = strategy.calculate_potion_efficiency(
            ItemType.MAX_POTION,
            80,
            80
        )
        assert efficiency == 0.0

    def test_should_use_rare_candy(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.RARE_CANDY, 5)
        strategy = ItemUsageStrategy(inv)
        pokemon = PokemonState(
            species="Pikachu",
            level=55,
            current_hp=80,
            max_hp=80,
            status="NONE",
            moves=["Thunderbolt"],
            move_pp={"Thunderbolt": 15},
            move_max_pp={"Thunderbolt": 30},
        )
        party = PartyState(
            pokemon=[pokemon],
            money=5000,
        )
        result = strategy.should_use_rare_candy(pokemon, party, [])
        assert result is True

    def test_should_use_rare_candy_max_level(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.RARE_CANDY, 5)
        strategy = ItemUsageStrategy(inv)
        pokemon = PokemonState(
            species="Pikachu",
            level=100,
            current_hp=80,
            max_hp=80,
            status="NONE",
            moves=["Thunderbolt"],
            move_pp={"Thunderbolt": 15},
            move_max_pp={"Thunderbolt": 30},
        )
        party = PartyState(
            pokemon=[pokemon],
            money=5000,
        )
        result = strategy.should_use_rare_candy(pokemon, party, [])
        assert result is False

    def test_get_optimal_candy_target(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.RARE_CANDY, 5)
        strategy = ItemUsageStrategy(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=20,
                    current_hp=80,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
                PokemonState(
                    species="Charizard",
                    level=40,
                    current_hp=120,
                    max_hp=120,
                    status="NONE",
                    moves=["Flamethrower"],
                    move_pp={"Flamethrower": 10},
                    move_max_pp={"Flamethrower": 15},
                ),
            ],
            money=5000,
        )
        target = strategy.get_optimal_candy_target(party, [])
        assert target is not None

    def test_should_use_x_item_trainer_battle(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        result = strategy.should_use_x_item({"is_trainer_battle": True, "turn_number": 1})
        assert result is True

    def test_should_use_x_item_wild_battle(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        result = strategy.should_use_x_item({"is_trainer_battle": False, "turn_number": 1})
        assert result is False

    def test_should_use_x_item_late_battle(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        result = strategy.should_use_x_item({"is_trainer_battle": True, "turn_number": 5})
        assert result is False

    def test_select_x_item(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.X_SPEED, 5)
        inv.add_item(ItemType.X_SPECIAL, 5)
        strategy = ItemUsageStrategy(inv)
        item = strategy.select_x_item({"is_trainer_battle": True, "turn_number": 1})
        assert item is not None

    def test_evaluate_repel_usage(self):
        inv = InventoryState()
        inv.clear_inventory()
        inv.add_item(ItemType.SUPER_REPEL, 5)
        strategy = ItemUsageStrategy(inv)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=80,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        should_use, repel_type, reason = strategy.evaluate_repel_usage(
            party,
            "Cerulean City",
            "VICTORY_ROAD"
        )
        assert isinstance(should_use, bool)

    def test_get_no_waste_items(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        items = strategy.get_no_waste_items()
        assert ItemType.MASTER_BALL in items
        assert ItemType.RARE_CANDY in items

    def test_check_waste_prevention_no_waste(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        is_wasteful, reason = strategy.check_waste_prevention(
            ItemType.HYPER_POTION,
            {"current_hp": 50, "max_hp": 80}
        )
        assert is_wasteful is False

    def test_check_waste_prevention_would_be_wasteful(self):
        inv = InventoryState()
        inv.clear_inventory()
        strategy = ItemUsageStrategy(inv)
        is_wasteful, reason = strategy.check_waste_prevention(
            ItemType.MAX_POTION,
            {"current_hp": 79, "max_hp": 80}
        )
        assert is_wasteful is True


class TestInventoryManager:
    """Tests for InventoryManager class"""

    def test_manager_has_all_components(self):
        manager = InventoryManager()
        manager.inventory.clear_inventory()
        assert manager.inventory is not None
        assert manager.shopping is not None
        assert manager.center is not None
        assert manager.item_usage is not None

    def test_process_vision_update(self):
        manager = InventoryManager()
        manager.inventory.clear_inventory()
        vision_data = {
            "item_readings": [
                {"item_type": "Hyper Potion", "quantity": 5},
                {"item_type": "Ultra Ball", "quantity": 10},
            ]
        }
        manager.process_vision_update(vision_data)
        assert manager.inventory.has_item(ItemType.HYPER_POTION)
        assert manager.inventory.has_item(ItemType.ULTRA_BALL)

    def test_get_shopping_goal(self):
        manager = InventoryManager()
        manager.inventory.clear_inventory()
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=50,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        goal = manager.get_shopping_goal(party, 5000)
        assert goal is not None
        assert isinstance(goal, ShoppingPlan)

    def test_get_healing_goal(self):
        manager = InventoryManager()
        manager.inventory.clear_inventory()
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=80,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        goal = manager.get_healing_goal(party)
        assert goal is not None

    def test_get_battle_item_decision(self):
        manager = InventoryManager()
        manager.inventory.clear_inventory()
        manager.inventory.add_item(ItemType.MAX_POTION, 10)
        party = PartyState(
            pokemon=[
                PokemonState(
                    species="Pikachu",
                    level=25,
                    current_hp=5,
                    max_hp=80,
                    status="NONE",
                    moves=["Thunderbolt"],
                    move_pp={"Thunderbolt": 15},
                    move_max_pp={"Thunderbolt": 30},
                ),
            ],
            money=5000,
        )
        item, target = manager.get_battle_item_decision(party, 0, {"is_trainer_battle": False})
        assert item is not None

    def test_record_item_usage(self):
        manager = InventoryManager()
        manager.inventory.clear_inventory()
        manager.inventory.add_item(ItemType.MAX_POTION, 5)
        manager.record_item_usage(ItemType.MAX_POTION, {"context": "battle"})
        assert manager.inventory.get_quantity(ItemType.MAX_POTION) == 4

    def test_get_inventory_report(self):
        manager = InventoryManager()
        manager.inventory.clear_inventory()
        report = manager.get_inventory_report()
        assert "inventory_summary" in report
        assert "shopping_needs" in report
        assert "healing_status" in report


class TestShoppingPlan:
    """Tests for ShoppingPlan dataclass"""

    def test_shopping_plan_creation(self):
        items = [
            ShoppingListItem(
                item_type=ItemType.HYPER_POTION,
                quantity=10,
                priority=ShoppingPriority.CRITICAL,
                estimated_cost=3000,
                reason="Need potions",
            )
        ]
        plan = ShoppingPlan(
            items=items,
            total_cost=3000,
            available_budget=4000,
            emergency_reserve=1000,
            estimated_time=30,
        )
        assert len(plan.items) == 1
        assert plan.total_cost == 3000


class TestKeyItem:
    """Tests for KeyItem dataclass"""

    def test_key_item_creation(self):
        key_item = KeyItem(
            item_type=ItemType.TOWN_MAP,
            name="Town Map",
            description="A map of the region",
            obtained=False,
        )
        assert key_item.obtained is False
        assert key_item.used is False

    def test_key_item_obtain(self):
        key_item = KeyItem(
            item_type=ItemType.TOWN_MAP,
            name="Town Map",
            description="A map of the region",
        )
        key_item.obtained = True
        key_item.obtained_time = datetime.now()
        assert key_item.obtained is True


class TestTMData:
    """Tests for TMData dataclass"""

    def test_tm_data_creation(self):
        tm = TMData(
            tm_number=1,
            item_type=ItemType.TM01,
            move_name="Mega Punch",
            move_type="Normal",
            move_power=40,
            move_accuracy=85,
            compatible_species=[],
        )
        assert tm.tm_number == 1
        assert tm.is_hm is False

    def test_hm_data_creation(self):
        hm = TMData(
            tm_number=1,
            item_type=ItemType.HM01,
            move_name="Cut",
            move_type="Normal",
            move_power=50,
            move_accuracy=95,
            compatible_species=[],
            is_hm=True,
            hm_move_name="Cut",
        )
        assert hm.is_hm is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])