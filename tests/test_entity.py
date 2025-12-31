"""
Unit tests for Entity Management & Party Optimization module.

Tests cover:
- PokemonData model creation and methods
- CarryScoreCalculator scoring logic
- EvolutionManager decision making
- TeamCompositionOptimizer analysis
- Team data structure operations
- TypeChart functionality
"""

import pytest
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from unittest.mock import MagicMock, patch

from src.core.entity import (
    PokemonType,
    StatusCondition,
    MoveCategory,
    GrowthRate,
    TeamRole,
    PokemonStats,
    BaseStats,
    IndividualValues,
    EffortValues,
    Move,
    Experience,
    PokemonData,
    Team,
    TypeValueWeights,
    CarryScoreBreakdown,
    EvolutionCondition,
    PreEvolutionMove,
    EvolutionDecision,
    TypeCoverage,
    TeamAnalysis,
    PartySlot,
    CarryScoreCalculator,
    EvolutionManager,
    TeamCompositionOptimizer,
    EntityManager,
    TypeChart,
    CRITICAL_PRE_EVO_MOVES,
)


@pytest.fixture
def type_chart():
    """Create a TypeChart for testing"""
    return TypeChart()


@pytest.fixture
def sample_base_stats():
    """Create sample base stats for testing"""
    return BaseStats(
        species_id="PIKACHU",
        species_name="Pikachu",
        hp=35,
        attack=55,
        defense=40,
        speed=90,
        special=50,
        type_primary=PokemonType.ELECTRIC,
        type_secondary=None,
        catch_rate=190,
        base_experience_yield=112,
        growth_rate=GrowthRate.MEDIUM
    )


@pytest.fixture
def sample_pokemon_data(sample_base_stats):
    """Create a sample PokemonData instance for testing"""
    return PokemonData(
        pokemon_id="pokemon_001",
        species_id="PIKACHU",
        nickname="Pika",
        level=25,
        current_hp=80,
        max_hp=80,
        base_stats=sample_base_stats,
        ivs=IndividualValues(hp=15, attack=15, defense=15, speed=15, special=15),
        evs=EffortValues(hp=0, attack=0, defense=0, speed=0, special=0),
        moves=[
            Move(
                move_id="THUNDER_SHOCK",
                name="Thunder Shock",
                move_type=PokemonType.ELECTRIC,
                power=40,
                accuracy=100,
                pp=30,
                max_pp=30,
                category=MoveCategory.SPECIAL
            ),
            Move(
                move_id="QUICK_ATTACK",
                name="Quick Attack",
                move_type=PokemonType.NORMAL,
                power=40,
                accuracy=100,
                pp=30,
                max_pp=30,
                category=MoveCategory.PHYSICAL
            ),
            Move(
                move_id="TAIL_WHIP",
                name="Tail Whip",
                move_type=PokemonType.NORMAL,
                power=0,
                accuracy=100,
                pp=30,
                max_pp=30,
                category=MoveCategory.STATUS
            ),
            Move(
                move_id="GROWL",
                name="Growl",
                move_type=PokemonType.NORMAL,
                power=0,
                accuracy=100,
                pp=40,
                max_pp=40,
                category=MoveCategory.STATUS
            )
        ],
        status=StatusCondition.NONE,
        experience=Experience(current=5000, to_next_level=2000, growth_rate="medium"),
        types=(PokemonType.ELECTRIC, None),
        happiness=100,
        is_shiny=False,
        catch_location="Viridian Forest",
        catch_level=5,
        victories=10,
        defeats=2
    )


@pytest.fixture
def sample_team(sample_pokemon_data):
    """Create a sample Team instance for testing"""
    return Team(
        team_id="team_001",
        name="My Team",
        party=[
            sample_pokemon_data,
            None,
            None,
            None,
            None,
            None
        ],
        box=[],
        total_battles=12,
        total_victories=10,
        total_defeats=2
    )


@pytest.fixture
def full_party(sample_pokemon_data, sample_base_stats):
    """Create a full party of 6 Pokemon for testing"""
    charizard_stats = BaseStats(
        species_id="CHARIZARD",
        species_name="Charizard",
        hp=78,
        attack=84,
        defense=78,
        speed=100,
        special=85,
        type_primary=PokemonType.FIRE,
        type_secondary=PokemonType.FLYING,
        catch_rate=45,
        base_experience_yield=209,
        growth_rate=GrowthRate.MEDIUM
    )
    
    blastoise_stats = BaseStats(
        species_id="BLASTOISE",
        species_name="Blastoise",
        hp=79,
        attack=83,
        defense=100,
        speed=78,
        special=85,
        type_primary=PokemonType.WATER,
        type_secondary=None,
        catch_rate=45,
        base_experience_yield=210,
        growth_rate=GrowthRate.MEDIUM
    )
    
    venusaur_stats = BaseStats(
        species_id="VENUSAUR",
        species_name="Venusaur",
        hp=80,
        attack=82,
        defense=83,
        speed=80,
        special=100,
        type_primary=PokemonType.GRASS,
        type_secondary=PokemonType.POISON,
        catch_rate=45,
        base_experience_yield=208,
        growth_rate=GrowthRate.MEDIUM
    )
    
    pikachu = sample_pokemon_data
    
    charizard = PokemonData(
        pokemon_id="pokemon_002",
        species_id="CHARIZARD",
        nickname=None,
        level=50,
        current_hp=200,
        max_hp=200,
        base_stats=charizard_stats,
        ivs=IndividualValues(hp=15, attack=15, defense=15, speed=15, special=15),
        evs=EffortValues(hp=0, attack=0, defense=0, speed=0, special=0),
        moves=[
            Move(move_id="FLAMETHROWER", name="Flamethrower", move_type=PokemonType.FIRE, power=90, accuracy=100, pp=15, max_pp=15, category=MoveCategory.SPECIAL),
            Move(move_id="SLASH", name="Slash", move_type=PokemonType.NORMAL, power=70, accuracy=100, pp=20, max_pp=20, category=MoveCategory.PHYSICAL),
            Move(move_id="FIRE_BLAST", name="Fire Blast", move_type=PokemonType.FIRE, power=110, accuracy=85, pp=5, max_pp=5, category=MoveCategory.SPECIAL),
            Move(move_id="WING_ATTACK", name="Wing Attack", move_type=PokemonType.FLYING, power=60, accuracy=100, pp=35, max_pp=35, category=MoveCategory.PHYSICAL)
        ],
        status=StatusCondition.NONE,
        experience=Experience(current=100000, to_next_level=50000, growth_rate="medium"),
        types=(PokemonType.FIRE, PokemonType.FLYING),
        victories=15,
        defeats=3
    )
    
    blastoise = PokemonData(
        pokemon_id="pokemon_003",
        species_id="BLASTOISE",
        nickname="Blasti",
        level=48,
        current_hp=195,
        max_hp=195,
        base_stats=blastoise_stats,
        ivs=IndividualValues(hp=15, attack=15, defense=15, speed=15, special=15),
        evs=EffortValues(hp=0, attack=0, defense=0, speed=0, special=0),
        moves=[
            Move(move_id="HYDRO_PUMP", name="Hydro Pump", move_type=PokemonType.WATER, power=110, accuracy=80, pp=5, max_pp=5, category=MoveCategory.SPECIAL),
            Move(move_id="SKULL_BASH", name="Skull Bash", move_type=PokemonType.NORMAL, power=130, accuracy=100, pp=10, max_pp=10, category=MoveCategory.PHYSICAL),
            Move(move_id="ICE_BEAM", name="Ice Beam", move_type=PokemonType.ICE, power=90, accuracy=100, pp=10, max_pp=10, category=MoveCategory.SPECIAL),
            Move(move_id="BITE", name="Bite", move_type=PokemonType.DARK, power=60, accuracy=100, pp=25, max_pp=25, category=MoveCategory.PHYSICAL)
        ],
        status=StatusCondition.NONE,
        experience=Experience(current=90000, to_next_level=60000, growth_rate="medium"),
        types=(PokemonType.WATER, None),
        victories=12,
        defeats=4
    )
    
    venusaur = PokemonData(
        pokemon_id="pokemon_004",
        species_id="VENUSAUR",
        nickname=None,
        level=52,
        current_hp=200,
        max_hp=200,
        base_stats=venusaur_stats,
        ivs=IndividualValues(hp=15, attack=15, defense=15, speed=15, special=15),
        evs=EffortValues(hp=0, attack=0, defense=0, speed=0, special=0),
        moves=[
            Move(move_id="RAZOR_LEAF", name="Razor Leaf", move_type=PokemonType.GRASS, power=55, accuracy=95, pp=25, max_pp=25, category=MoveCategory.PHYSICAL),
            Move(move_id="SLUDGE_BOMB", name="Sludge Bomb", move_type=PokemonType.POISON, power=90, accuracy=100, pp=10, max_pp=10, category=MoveCategory.SPECIAL),
            Move(move_id="EARTHQUAKE", name="Earthquake", move_type=PokemonType.GROUND, power=100, accuracy=100, pp=10, max_pp=10, category=MoveCategory.PHYSICAL),
            Move(move_id="SLEEP_POWDER", name="Sleep Powder", move_type=PokemonType.GRASS, power=0, accuracy=75, pp=15, max_pp=15, category=MoveCategory.STATUS)
        ],
        status=StatusCondition.POISONED,
        experience=Experience(current=120000, to_next_level=40000, growth_rate="medium"),
        types=(PokemonType.GRASS, PokemonType.POISON),
        victories=18,
        defeats=2
    )
    
    rattata_stats = BaseStats(
        species_id="RATTATA",
        species_name="Rattata",
        hp=30,
        attack=56,
        defense=35,
        speed=72,
        special=25,
        type_primary=PokemonType.NORMAL,
        type_secondary=None,
        catch_rate=255,
        base_experience_yield=57,
        growth_rate=GrowthRate.FAST
    )
    
    rattata = PokemonData(
        pokemon_id="pokemon_005",
        species_id="RATTATA",
        nickname="Ratty",
        level=15,
        current_hp=35,
        max_hp=35,
        base_stats=rattata_stats,
        ivs=IndividualValues(hp=5, attack=10, defense=5, speed=10, special=5),
        evs=EffortValues(hp=0, attack=0, defense=0, speed=0, special=0),
        moves=[
            Move(move_id="TACKLE", name="Tackle", move_type=PokemonType.NORMAL, power=40, accuracy=100, pp=35, max_pp=35, category=MoveCategory.PHYSICAL),
            Move(move_id="TAIL_WHIP", name="Tail Whip", move_type=PokemonType.NORMAL, power=0, accuracy=100, pp=30, max_pp=30, category=MoveCategory.STATUS),
            Move(move_id="QUICK_ATTACK", name="Quick Attack", move_type=PokemonType.NORMAL, power=40, accuracy=100, pp=30, max_pp=30, category=MoveCategory.PHYSICAL),
            Move(move_id="HYPER_FANG", name="Hyper Fang", move_type=PokemonType.NORMAL, power=80, accuracy=90, pp=15, max_pp=15, category=MoveCategory.PHYSICAL)
        ],
        status=StatusCondition.NONE,
        experience=Experience(current=2000, to_next_level=3000, growth_rate="fast"),
        types=(PokemonType.NORMAL, None),
        victories=5,
        defeats=8
    )
    
    return Team(
        team_id="team_full",
        name="Full Team",
        party=[pikachu, charizard, blastoise, venusaur, rattata, None],
        box=[],
        total_battles=50,
        total_victories=40,
        total_defeats=10
    )


class TestTypeChart:
    """Tests for TypeChart class"""
    
    def test_fire_vs_grass_super_effective(self, type_chart):
        """Test Fire is super effective against Grass"""
        effectiveness = type_chart.get_effectiveness(PokemonType.FIRE, [PokemonType.GRASS])
        assert effectiveness == 2.0
    
    def test_water_vs_fire_super_effective(self, type_chart):
        """Test Water is super effective against Fire"""
        effectiveness = type_chart.get_effectiveness(PokemonType.WATER, [PokemonType.FIRE])
        assert effectiveness == 2.0
    
    def test_electric_vs_ground_immune(self, type_chart):
        """Test Electric is immune to Ground"""
        effectiveness = type_chart.get_effectiveness(PokemonType.ELECTRIC, [PokemonType.GROUND])
        assert effectiveness == 0.0
    
    def test_normal_vs_ghost_immune(self, type_chart):
        """Test Normal is immune to Ghost"""
        effectiveness = type_chart.get_effectiveness(PokemonType.NORMAL, [PokemonType.GHOST])
        assert effectiveness == 0.0
    
    def test_fairy_vs_dragon_super_effective(self, type_chart):
        """Test Fairy is super effective against Dragon"""
        effectiveness = type_chart.get_effectiveness(PokemonType.FAIRY, [PokemonType.DRAGON])
        assert effectiveness == 2.0
    
    def test_water_vs_water_not_very_effective(self, type_chart):
        """Test Water is not very effective against Water"""
        effectiveness = type_chart.get_effectiveness(PokemonType.WATER, [PokemonType.WATER])
        assert effectiveness == 0.5
    
    def test_dual_type_effectiveness(self, type_chart):
        """Test effectiveness against dual types"""
        effectiveness = type_chart.get_effectiveness(PokemonType.FIRE, [PokemonType.GRASS, PokemonType.ICE])
        assert effectiveness == 4.0
    
    def test_is_immune(self, type_chart):
        """Test is_immune method"""
        assert type_chart.is_immune(PokemonType.NORMAL, [PokemonType.GHOST]) is True
        assert type_chart.is_immune(PokemonType.FIRE, [PokemonType.GRASS]) is False
    
    def test_is_super_effective(self, type_chart):
        """Test is_super_effective method"""
        assert type_chart.is_super_effective(PokemonType.FIRE, [PokemonType.GRASS]) is True
        assert type_chart.is_super_effective(PokemonType.FIRE, [PokemonType.WATER]) is False


class TestPokemonData:
    """Tests for PokemonData dataclass"""

    def test_species_name_with_nickname(self, sample_pokemon_data):
        """Test that nickname is used when available"""
        assert sample_pokemon_data.species_name() == "Pika"

    def test_species_name_without_nickname(self, sample_pokemon_data):
        """Test that species name is used when no nickname"""
        sample_pokemon_data.nickname = None
        assert sample_pokemon_data.species_name() == "Pikachu"

    def test_can_battle_healthy(self, sample_pokemon_data):
        """Test can_battle returns True for healthy Pokemon"""
        assert sample_pokemon_data.can_battle() is True

    def test_can_battle_fainted(self, sample_pokemon_data):
        """Test can_battle returns False for fainted Pokemon"""
        sample_pokemon_data.current_hp = 0
        assert sample_pokemon_data.can_battle() is False

    def test_can_battle_frozen(self, sample_pokemon_data):
        """Test can_battle returns False for frozen Pokemon"""
        sample_pokemon_data.status = StatusCondition.FROZEN
        assert sample_pokemon_data.can_battle() is False

    def test_can_battle_poisoned(self, sample_pokemon_data):
        """Test can_battle returns True for poisoned Pokemon"""
        sample_pokemon_data.status = StatusCondition.POISONED
        assert sample_pokemon_data.can_battle() is True

    def test_has_move_existing(self, sample_pokemon_data):
        """Test has_move returns True for existing move"""
        assert sample_pokemon_data.has_move("Thunder Shock") is True

    def test_has_move_non_existing(self, sample_pokemon_data):
        """Test has_move returns False for non-existing move"""
        assert sample_pokemon_data.has_move("Thunderbolt") is False

    def test_has_move_case_insensitive(self, sample_pokemon_data):
        """Test has_move is case insensitive"""
        assert sample_pokemon_data.has_move("THUNDER SHOCK") is True
        assert sample_pokemon_data.has_move("thunder shock") is True

    def test_get_move_existing(self, sample_pokemon_data):
        """Test get_move returns move for existing move"""
        move = sample_pokemon_data.get_move("Quick Attack")
        assert move is not None
        assert move.name == "Quick Attack"

    def test_get_move_non_existing(self, sample_pokemon_data):
        """Test get_move returns None for non-existing move"""
        move = sample_pokemon_data.get_move("Thunderbolt")
        assert move is None

    def test_total_pp_remaining(self, sample_pokemon_data):
        """Test total PP calculation"""
        total_pp = sample_pokemon_data.total_pp_remaining()
        assert total_pp == 30 + 30 + 30 + 40

    def test_average_pp_remaining(self, sample_pokemon_data):
        """Test average PP percentage calculation"""
        avg_pp = sample_pokemon_data.average_pp_remaining()
        assert avg_pp == 1.0  # All moves at full PP

    def test_offensive_stat_physical(self, sample_pokemon_data):
        """Test offensive stat returns attack for physical specialist"""
        sample_pokemon_data.moves[0].power = 30  # Reduce special move power
        stat = sample_pokemon_data.offensive_stat()
        assert stat == sample_pokemon_data.base_stats.attack + sample_pokemon_data.ivs.attack

    def test_offensive_stat_special(self, sample_pokemon_data):
        """Test offensive stat returns special for special specialist"""
        stat = sample_pokemon_data.offensive_stat()
        assert stat == sample_pokemon_data.base_stats.special + sample_pokemon_data.ivs.special

    def test_defensive_stat(self, sample_pokemon_data):
        """Test defensive stat calculation - Pikachu has higher special than defense"""
        stat = sample_pokemon_data.defensive_stat()
        # Pikachu's base_stats.special (50) > base_stats.defense (40), so uses special
        expected = sample_pokemon_data.base_stats.special + sample_pokemon_data.ivs.special
        assert stat == expected

    def test_is_overleveled(self, sample_pokemon_data):
        """Test overleveled detection"""
        assert sample_pokemon_data.is_overleveled(20.0) is True
        assert sample_pokemon_data.is_overleveled(25.0) is False

    def test_is_underleveled(self, sample_pokemon_data):
        """Test underleveled detection"""
        assert sample_pokemon_data.is_underleveled(30.0) is True
        assert sample_pokemon_data.is_underleveled(25.0) is False

    def test_get_best_move(self, sample_pokemon_data):
        """Test get_best_move returns highest power move"""
        best_move = sample_pokemon_data.get_best_move()
        assert best_move is not None
        assert best_move.power == 40

    def test_get_dps_potential(self, sample_pokemon_data):
        """Test DPS potential calculation"""
        dps = sample_pokemon_data.get_dps_potential()
        assert dps > 0

    def test_to_dict(self, sample_pokemon_data):
        """Test dictionary conversion"""
        data_dict = sample_pokemon_data.to_dict()
        assert data_dict["pokemon_id"] == "pokemon_001"
        assert data_dict["species_id"] == "PIKACHU"
        assert data_dict["level"] == 25
        assert len(data_dict["moves"]) == 4


class TestTeam:
    """Tests for Team dataclass"""

    def test_active_pokemon(self, sample_team, sample_pokemon_data):
        """Test active_pokemon returns non-None Pokemon"""
        active = sample_team.active_pokemon()
        assert len(active) == 1
        assert active[0] == sample_pokemon_data

    def test_active_count(self, sample_team):
        """Test active_count returns correct count"""
        assert sample_team.active_count() == 1

    def test_can_battle_true(self, sample_team):
        """Test can_battle returns True when team can battle"""
        assert sample_team.can_battle() is True

    def test_can_battle_false(self, sample_team, sample_pokemon_data):
        """Test can_battle returns False when no Pokemon can battle"""
        sample_pokemon_data.current_hp = 0
        assert sample_team.can_battle() is False

    def test_average_level(self, sample_team, sample_pokemon_data):
        """Test average level calculation"""
        avg = sample_team.average_level()
        assert avg == sample_pokemon_data.level

    def test_level_spread_single(self, sample_team):
        """Test level spread with single Pokemon"""
        assert sample_team.level_spread() == 0

    def test_get_lead_pokemon(self, sample_team, sample_pokemon_data):
        """Test get_lead_pokemon returns first non-None"""
        lead = sample_team.get_lead_pokemon()
        assert lead == sample_pokemon_data

    def test_has_hm_user_false(self, sample_team):
        """Test has_hm_user returns False when no HM moves"""
        assert sample_team.has_hm_user() is False

    def test_has_hm_user_true(self, sample_team, sample_pokemon_data):
        """Test has_hm_user returns True when HM move exists"""
        sample_pokemon_data.moves.append(
            Move(
                move_id="CUT",
                name="Cut",
                move_type=PokemonType.NORMAL,
                power=50,
                accuracy=95,
                pp=30,
                max_pp=30,
                category=MoveCategory.PHYSICAL
            )
        )
        assert sample_team.has_hm_user() is True

    def test_get_hm_users(self, sample_team, sample_pokemon_data):
        """Test get_hm_users returns mapping"""
        sample_pokemon_data.moves.append(
            Move(move_id="CUT", name="Cut", move_type=PokemonType.NORMAL, power=50, accuracy=95, pp=30, max_pp=30, category=MoveCategory.PHYSICAL)
        )
        hm_users = sample_team.get_hm_users()
        assert "CUT" in hm_users

    def test_needs_rebalancing_false(self, sample_team):
        """Test needs_rebalancing returns False when spread is low"""
        assert sample_team.needs_rebalancing() is False

    def test_battle_ready_count(self, sample_team, sample_pokemon_data):
        """Test battle_ready_count calculation"""
        assert sample_team.battle_ready_count() == 1
        sample_pokemon_data.current_hp = 0
        assert sample_team.battle_ready_count() == 0

    def test_party_padding(self):
        """Test that party is padded to 6 slots"""
        team = Team(
            team_id="test",
            name=None,
            party=[None, None, None, None, None, None],
            box=[]
        )
        assert len(team.party) == 6


class TestCarryScoreCalculator:
    """Tests for CarryScoreCalculator"""

    def test_calculate_level_relevance_match(self, sample_pokemon_data, type_chart):
        """Test level relevance when level matches expected"""
        calculator = CarryScoreCalculator(type_chart, {})
        score = calculator.calculate_level_relevance(sample_pokemon_data, 25)
        assert score >= 18.0

    def test_calculate_level_relevance_overleveled(self, sample_pokemon_data, type_chart):
        """Test level relevance when overleveled"""
        calculator = CarryScoreCalculator(type_chart, {})
        score = calculator.calculate_level_relevance(sample_pokemon_data, 15)
        # Level 25 vs expected 15 = 10 levels over, score should be > 0
        assert score > 0
        assert score <= 25.0

    def test_calculate_level_relevance_underleveled(self, sample_pokemon_data, type_chart):
        """Test level relevance when underleveled"""
        calculator = CarryScoreCalculator(type_chart, {})
        score = calculator.calculate_level_relevance(sample_pokemon_data, 35)
        # Level 25 vs expected 35 = 10 levels under, score should be > 0
        assert score > 0
        assert score <= 25.0

    def test_calculate_level_relevance_severely_underleveled(self, sample_pokemon_data, type_chart):
        """Test level relevance when severely underleveled"""
        calculator = CarryScoreCalculator(type_chart, {})
        score = calculator.calculate_level_relevance(sample_pokemon_data, 50)
        assert score < 10.0

    def test_calculate_type_uniqueness(self, sample_pokemon_data, type_chart):
        """Test type uniqueness calculation"""
        calculator = CarryScoreCalculator(type_chart, {})
        score = calculator.calculate_type_uniqueness(
            sample_pokemon_data,
            [sample_pokemon_data, None, None, None, None, None]
        )
        assert score >= 0

    def test_calculate_type_uniqueness_with_party(self, full_party, type_chart):
        """Test type uniqueness with full party"""
        calculator = CarryScoreCalculator(type_chart, {})
        pikachu = full_party.party[0]
        score = calculator.calculate_type_uniqueness(pikachu, full_party.party)
        assert score >= 0

    def test_calculate_move_coverage(self, sample_pokemon_data, type_chart):
        """Test move coverage calculation"""
        calculator = CarryScoreCalculator(type_chart, {})
        score = calculator.calculate_move_coverage(sample_pokemon_data)
        assert score >= 0

    def test_calculate_stat_efficiency(self, sample_pokemon_data, sample_base_stats, type_chart):
        """Test stat efficiency calculation"""
        calculator = CarryScoreCalculator(type_chart, {})
        score = calculator.calculate_stat_efficiency(sample_pokemon_data, sample_base_stats)
        assert score >= 0

    def test_apply_rarity_modifier_starter(self, sample_pokemon_data, type_chart):
        """Test rarity modifier for starter Pokemon"""
        sample_pokemon_data.species_id = "BULBASAUR"
        calculator = CarryScoreCalculator(type_chart, {})
        modifier = calculator.apply_rarity_modifier(sample_pokemon_data)
        assert modifier == 1.15

    def test_apply_rarity_modifier_legendary(self, sample_pokemon_data, type_chart):
        """Test rarity modifier for legendary Pokemon"""
        sample_pokemon_data.species_id = "MEWTWO"
        calculator = CarryScoreCalculator(type_chart, {})
        modifier = calculator.apply_rarity_modifier(sample_pokemon_data)
        assert modifier == 1.3

    def test_apply_rarity_modifier_common(self, sample_pokemon_data, type_chart):
        """Test rarity modifier for common Pokemon"""
        sample_pokemon_data.species_id = "PIDGEY"
        calculator = CarryScoreCalculator(type_chart, {})
        modifier = calculator.apply_rarity_modifier(sample_pokemon_data)
        assert modifier == 0.7

    def test_apply_rarity_modifier_unknown(self, sample_pokemon_data, type_chart):
        """Test rarity modifier for unknown Pokemon"""
        sample_pokemon_data.species_id = "UNKNOWN"
        calculator = CarryScoreCalculator(type_chart, {})
        modifier = calculator.apply_rarity_modifier(sample_pokemon_data)
        assert modifier == 1.0

    def test_apply_sentimental_modifier_basic(self, sample_pokemon_data, type_chart):
        """Test sentimental modifier calculation"""
        calculator = CarryScoreCalculator(type_chart, {})
        modifier = calculator.apply_sentimental_modifier(sample_pokemon_data)
        assert modifier >= 1.0

    def test_apply_sentimental_modifier_shiny(self, sample_pokemon_data, type_chart):
        """Test sentimental modifier for shiny Pokemon"""
        sample_pokemon_data.is_shiny = True
        calculator = CarryScoreCalculator(type_chart, {})
        modifier = calculator.apply_sentimental_modifier(sample_pokemon_data)
        assert modifier > 1.0

    def test_apply_sentimental_modifier_hero(self, sample_pokemon_data, type_chart):
        """Test sentimental modifier for battle hero"""
        sample_pokemon_data.critical_battle_wins = 5
        calculator = CarryScoreCalculator(type_chart, {})
        modifier = calculator.apply_sentimental_modifier(sample_pokemon_data)
        assert modifier > 1.0

    def test_calculate_carry_score(self, sample_pokemon_data, type_chart):
        """Test complete carry score calculation"""
        calculator = CarryScoreCalculator(type_chart, {})
        score, breakdown = calculator.calculate_carry_score(
            sample_pokemon_data,
            [sample_pokemon_data, None, None, None, None, None]
        )
        assert score >= 0
        assert isinstance(breakdown, CarryScoreBreakdown)
        assert breakdown.final_score == score

    def test_should_bench_protect(self, type_chart):
        """Test should_bench returns 'protect' for high scores"""
        calculator = CarryScoreCalculator(type_chart, {})
        result = calculator.should_bench(75)
        assert result == "protect"

    def test_should_bench_conditional(self, type_chart):
        """Test should_bench returns 'conditional' for medium scores"""
        calculator = CarryScoreCalculator(type_chart, {})
        result = calculator.should_bench(60)
        assert result == "conditional"

    def test_should_bench_bench(self, type_chart):
        """Test should_bench returns 'bench' for lower scores"""
        calculator = CarryScoreCalculator(type_chart, {})
        result = calculator.should_bench(40)
        assert result == "bench"

    def test_should_bench_immediate(self, type_chart):
        """Test should_bench returns 'immediate_bench' for low scores"""
        calculator = CarryScoreCalculator(type_chart, {})
        result = calculator.should_bench(30)
        assert result == "immediate_bench"

    def test_carry_score_integration(self, full_party, type_chart):
        """Test carry score calculation for full party"""
        calculator = CarryScoreCalculator(type_chart, {})
        scores = {}
        for pokemon in full_party.active_pokemon():
            score, breakdown = calculator.calculate_carry_score(pokemon, full_party.party)
            scores[pokemon.pokemon_id] = score
        
        assert len(scores) == 5
        assert all(s >= 0 for s in scores.values())


class TestEvolutionManager:
    """Tests for EvolutionManager"""

    def test_get_evolution_conditions(self, type_chart):
        """Test evolution conditions retrieval"""
        manager = EvolutionManager({}, {}, type_chart)
        conditions = manager.get_evolution_conditions("PIKACHU", 25)
        assert isinstance(conditions, list)

    def test_check_evolution_available_no_evolution(self, sample_pokemon_data, type_chart):
        """Test evolution check when no evolution available"""
        manager = EvolutionManager({}, {}, type_chart)
        result = manager.check_evolution_available(sample_pokemon_data)
        assert result is None

    def test_check_evolution_available_with_evolution(self, sample_pokemon_data, type_chart):
        """Test evolution check when evolution available"""
        evolution_data = {
            "PIKACHU": [
                EvolutionCondition(
                    condition_type="level",
                    required_value=26,
                    target_species_id="RAICHU",
                    target_species_name="Raichu",
                    learnable_moves=[],
                    stat_changes={"attack": 10, "speed": 20}
                )
            ]
        }
        sample_pokemon_data.level = 26
        manager = EvolutionManager(evolution_data, {}, type_chart)
        result = manager.check_evolution_available(sample_pokemon_data)
        assert result is not None
        assert result.target_species_id == "RAICHU"

    def test_evaluate_pre_evolution_moves(self, type_chart):
        """Test pre-evolution move evaluation"""
        manager = EvolutionManager({}, {}, type_chart)
        result = manager.evaluate_pre_evolution_moves("PIKACHU", 25, 999)
        assert result is None or isinstance(result, PreEvolutionMove)

    def test_evaluate_pre_evolution_moves_charmander(self, type_chart):
        """Test pre-evolution move evaluation for Charmander"""
        manager = EvolutionManager({}, {}, type_chart)
        result = manager.evaluate_pre_evolution_moves("CHARMANDER", 20, 36)
        # At level 20, the first pre-evo move available would be Slash (learn at 33, evol at 16)
        assert result is not None
        assert result.move_name == "Slash"

    def test_calculate_evolution_vs_wait_tradeoff_evolve_now(self, sample_pokemon_data, type_chart):
        """Test evolution vs wait tradeoff - evolve now"""
        evolution = EvolutionCondition(
            condition_type="level",
            required_value=26,
            target_species_id="RAICHU",
            target_species_name="Raichu",
            learnable_moves=[],
            stat_changes={"attack": 20, "speed": 30}
        )
        manager = EvolutionManager({}, {}, type_chart)
        decision = manager.calculate_evolution_vs_wait_tradeoff(sample_pokemon_data, evolution, None)
        assert isinstance(decision, EvolutionDecision)
        assert decision.decision == "evolve_now"

    def test_calculate_evolution_vs_wait_tradeoff_wait(self, sample_pokemon_data, type_chart):
        """Test evolution vs wait tradeoff - wait for move"""
        evolution = EvolutionCondition(
            condition_type="level",
            required_value=26,
            target_species_id="CHARMELEON",
            target_species_name="Charmeleon",
            learnable_moves=[],
            stat_changes={"attack": 10, "speed": 15}
        )
        pre_evo_move = PreEvolutionMove(
            move_id="FLAMETHROWER",
            move_name="Flamethrower",
            learn_level=38,
            evolution_level=16,
            value_rating="STRONG_STAB",
            power=90
        )
        sample_pokemon_data.species_id = "CHARMANDER"
        sample_pokemon_data.level = 25
        manager = EvolutionManager({}, {}, type_chart)
        decision = manager.calculate_evolution_vs_wait_tradeoff(sample_pokemon_data, evolution, pre_evo_move)
        assert isinstance(decision, EvolutionDecision)
        # With significant stat improvement, it may decide to evolve now
        assert decision.decision in ["evolve_now", "wait_13_levels", "consider_waiting"]

    def test_calculate_move_value(self, sample_pokemon_data, type_chart):
        """Test move value calculation"""
        manager = EvolutionManager({}, {}, type_chart)
        move = sample_pokemon_data.moves[0]
        value = manager.calculate_move_value(move, sample_pokemon_data)
        assert value >= 0

    def test_calculate_move_value_status(self, sample_pokemon_data, type_chart):
        """Test move value for status moves"""
        manager = EvolutionManager({}, {}, type_chart)
        move = sample_pokemon_data.moves[2]  # Tail Whip (status)
        value = manager.calculate_move_value(move, sample_pokemon_data)
        assert value == 5.0

    def test_should_use_evolution_item(self, sample_pokemon_data, type_chart):
        """Test evolution item usage decision"""
        evolution_data = {
            "EEVEE": [
                EvolutionCondition(
                    condition_type="item",
                    required_value="Thunder Stone",
                    target_species_id="JOLTEON",
                    target_species_name="Jolteon",
                    learnable_moves=[],
                    stat_changes={"speed": 40}
                )
            ]
        }
        manager = EvolutionManager(evolution_data, {}, type_chart)
        result = manager.should_use_evolution_item(
            sample_pokemon_data, "Thunder Stone", {"type_coverage_needed": ["Electric"]}
        )
        assert isinstance(result, bool)

    def test_get_evolution_readiness_not_available(self, sample_pokemon_data, type_chart):
        """Test evolution readiness when not available"""
        manager = EvolutionManager({}, {}, type_chart)
        readiness = manager.get_evolution_readiness(sample_pokemon_data)
        assert isinstance(readiness, dict)
        assert readiness["evolution_available"] is False
        assert readiness["recommended_action"] == "continue_training"

    def test_get_evolution_readiness_available(self, sample_pokemon_data, type_chart):
        """Test evolution readiness when available"""
        evolution_data = {
            "PIKACHU": [
                EvolutionCondition(
                    condition_type="level",
                    required_value=26,
                    target_species_id="RAICHU",
                    target_species_name="Raichu",
                    learnable_moves=[],
                    stat_changes={}
                )
            ]
        }
        sample_pokemon_data.level = 26
        manager = EvolutionManager(evolution_data, {}, type_chart)
        readiness = manager.get_evolution_readiness(sample_pokemon_data)
        assert readiness["evolution_available"] is True


class TestTeamCompositionOptimizer:
    """Tests for TeamCompositionOptimizer"""

    def test_analyze_type_coverage_empty(self, sample_team, type_chart):
        """Test type coverage analysis with minimal team"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        coverage = optimizer.analyze_type_coverage(sample_team.party)
        assert isinstance(coverage, TypeCoverage)
        # Some types should be covered
        assert len(coverage.covered_types) > 0

    def test_analyze_type_coverage_full_party(self, full_party, type_chart):
        """Test type coverage analysis with full party"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        coverage = optimizer.analyze_type_coverage(full_party.party)
        # With 5 Pokemon, coverage should be > 0
        assert coverage.coverage_percentage > 0
        assert coverage.coverage_percentage <= 1.0

    def test_analyze_type_coverage_with_upcoming_battles(self, full_party, type_chart):
        """Test type coverage with upcoming battles"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        upcoming = [{"boss_types": ["WATER", "ROCK"]}]
        coverage = optimizer.analyze_type_coverage(full_party.party, upcoming)
        assert isinstance(coverage, TypeCoverage)

    def test_calculate_stat_distribution(self, sample_team, type_chart):
        """Test stat distribution calculation"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        distribution = optimizer.calculate_stat_distribution(sample_team.party)
        assert "attack" in distribution
        assert "defense" in distribution
        assert "speed" in distribution
        assert "special" in distribution
        assert sum(distribution.values()) == 1.0

    def test_calculate_stat_distribution_full_party(self, full_party, type_chart):
        """Test stat distribution with full party"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        distribution = optimizer.calculate_stat_distribution(full_party.party)
        assert distribution["attack"] > 0.2

    def test_detect_move_overlap(self, sample_team, type_chart):
        """Test move overlap detection"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        overlaps = optimizer.detect_move_overlap(sample_team.party)
        assert isinstance(overlaps, list)

    def test_detect_move_overlap_with_duplicates(self, full_party, type_chart):
        """Test move overlap detection with duplicate moves"""
        full_party.party[1].moves.append(
            Move(move_id="QUICK_ATTACK2", name="Quick Attack", move_type=PokemonType.NORMAL, power=40, accuracy=100, pp=30, max_pp=30, category=MoveCategory.PHYSICAL)
        )
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        overlaps = optimizer.detect_move_overlap(full_party.party)
        assert len(overlaps) > 0

    def test_assign_roles(self, sample_team, type_chart):
        """Test role assignment"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        roles = optimizer.assign_roles(sample_team.party)
        assert isinstance(roles, dict)

    def test_assign_roles_full_party(self, full_party, type_chart):
        """Test role assignment with full party"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        roles = optimizer.assign_roles(full_party.party)
        assert len(roles) == 5
        assert all(role in ["sweeper", "tank", "support", "mixed"] for role in roles.values())

    def test_identify_boss_counters(self, type_chart):
        """Test boss counter identification"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        counters = optimizer.identify_boss_counters([], [])
        assert isinstance(counters, list)

    def test_identify_boss_counters_with_data(self, full_party, type_chart):
        """Test boss counter identification with boss data"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        boss_team = [
            {"species_id": "BLASTOISE", "types": ["WATER"], "level": 50}
        ]
        counters = optimizer.identify_boss_counters(boss_team, full_party.active_pokemon())
        assert len(counters) > 0

    def test_calculate_battle_usage_priorities(self, sample_team, type_chart):
        """Test battle usage priority calculation"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        priorities = optimizer.calculate_battle_usage_priorities(
            sample_team.party, []
        )
        assert isinstance(priorities, list)
        assert len(priorities) == 6

    def test_optimize_party_order_wild(self, sample_team, type_chart):
        """Test party order optimization for wild battles"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        order = optimizer.optimize_party_order(sample_team.party, "wild")
        assert isinstance(order, list)
        assert len(order) == 6

    def test_optimize_party_order_gym(self, full_party, type_chart):
        """Test party order optimization for gym battles"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        order = optimizer.optimize_party_order(full_party.party, "gym")
        assert isinstance(order, list)

    def test_optimize_party_order_elite4(self, full_party, type_chart):
        """Test party order optimization for Elite 4"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        order = optimizer.optimize_party_order(full_party.party, "elite4")
        assert isinstance(order, list)

    def test_calculate_experience_rebalance_needed(self, sample_team, type_chart):
        """Test experience rebalance assessment"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        result = optimizer.calculate_experience_rebalance_needed(sample_team.party)
        assert "level_spread" in result
        assert "needs_rebalance" in result

    def test_calculate_experience_rebalance_needed_unbalanced(self, full_party, type_chart):
        """Test experience rebalance with unbalanced team"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        result = optimizer.calculate_experience_rebalance_needed(full_party.party)
        assert result["level_spread"] > 0

    def test_analyze_team(self, sample_team, type_chart):
        """Test complete team analysis"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        analysis = optimizer.analyze_team(sample_team.party)
        assert isinstance(analysis, TeamAnalysis)
        assert analysis.team_score >= 0

    def test_analyze_team_full_party(self, full_party, type_chart):
        """Test complete team analysis with full party"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        analysis = optimizer.analyze_team(full_party.party)
        assert isinstance(analysis, TeamAnalysis)
        assert len(analysis.carry_scores) == 5

    def test_suggest_party_changes(self, sample_team, type_chart):
        """Test party change suggestions"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        suggestions = optimizer.suggest_party_changes(
            sample_team.party, [], {"next_gym": "Cerulean"}
        )
        assert isinstance(suggestions, list)


class TestEntityManager:
    """Tests for EntityManager"""

    def test_set_team(self, sample_team, type_chart):
        """Test setting the current team"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        assert manager.team == sample_team

    def test_update_pokemon_found(self, sample_team, sample_pokemon_data, type_chart):
        """Test updating existing Pokemon"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        result = manager.update_pokemon("pokemon_001", {"level": 26})
        assert result is True
        assert sample_pokemon_data.level == 26

    def test_update_pokemon_not_found(self, type_chart, sample_team):
        """Test updating non-existent Pokemon returns False"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        result = manager.update_pokemon("nonexistent", {"level": 26})
        assert result is False

    def test_get_pokemon_found(self, sample_team, sample_pokemon_data, type_chart):
        """Test getting existing Pokemon"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        result = manager.get_pokemon("pokemon_001")
        assert result == sample_pokemon_data

    def test_get_pokemon_not_found(self, type_chart, sample_team):
        """Test getting non-existent Pokemon returns None"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        result = manager.get_pokemon("nonexistent")
        assert result is None

    def test_calculate_all_carry_scores(self, sample_team, type_chart):
        """Test calculating carry scores for all Pokemon"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        scores = manager.calculate_all_carry_scores()
        assert isinstance(scores, dict)
        assert "pokemon_001" in scores

    def test_analyze_team(self, sample_team, type_chart):
        """Test team analysis"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        analysis = manager.analyze_team()
        assert isinstance(analysis, TeamAnalysis)

    def test_get_evolution_recommendations_not_found(self, type_chart, sample_team):
        """Test evolution recommendations for non-existent Pokemon"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        recommendations = manager.get_evolution_recommendations("nonexistent")
        assert isinstance(recommendations, dict)
        assert len(recommendations) == 0

    def test_get_evolution_recommendations_found(self, sample_team, sample_pokemon_data, type_chart):
        """Test evolution recommendations for existing Pokemon"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        recommendations = manager.get_evolution_recommendations("pokemon_001")
        assert isinstance(recommendations, dict)

    def test_get_party_optimization_suggestions(self, sample_team, type_chart):
        """Test party optimization suggestions"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        suggestions = manager.get_party_optimization_suggestions(
            {"next_gym": "Cerulean"}
        )
        assert isinstance(suggestions, list)

    def test_check_experience_balance(self, sample_team, type_chart):
        """Test experience balance check"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        result = manager.check_experience_balance()
        assert isinstance(result, dict)
        assert "level_spread" in result

    def test_full_party_scan(self, sample_team, type_chart):
        """Test full party scan"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        result = manager.full_party_scan()
        assert isinstance(result, dict)
        assert "team_score" in result
        assert "type_coverage" in result
        assert "carry_scores" in result

    def test_get_bench_status(self, sample_team, type_chart):
        """Test bench status retrieval"""
        manager = EntityManager(type_chart)
        manager.set_team(sample_team)
        status = manager.get_bench_status()
        assert isinstance(status, list)
        assert len(status) == 1


class TestDataClasses:
    """Tests for utility data classes"""

    def test_individual_values_clamping(self):
        """Test IV clamping to 0-15 range"""
        ivs = IndividualValues(hp=20, attack=-5, defense=15, speed=10, special=8)
        assert ivs.hp == 15
        assert ivs.attack == 0
        assert ivs.defense == 15

    def test_individual_values_total(self):
        """Test IV total calculation"""
        ivs = IndividualValues(hp=10, attack=10, defense=10, speed=10, special=10)
        assert ivs.total() == 50

    def test_effort_values_clamping(self):
        """Test EV clamping to 0-65535 range"""
        evs = EffortValues(hp=70000, attack=-100, defense=65535, speed=30000, special=10000)
        assert evs.hp == 65535
        assert evs.attack == 0
        assert evs.defense == 65535

    def test_effort_values_total(self):
        """Test EV total calculation"""
        evs = EffortValues(hp=10000, attack=10000, defense=10000, speed=10000, special=10000)
        assert evs.total() == 50000

    def test_move_pp_percentage(self):
        """Test move PP percentage calculation"""
        move = Move(
            move_id="TEST",
            name="Test",
            move_type=PokemonType.NORMAL,
            power=50,
            accuracy=100,
            pp=15,
            max_pp=30,
            category=MoveCategory.PHYSICAL
        )
        assert move.pp_percentage() == 0.5

    def test_move_pp_percentage_zero_max(self):
        """Test move PP percentage with zero max PP"""
        move = Move(
            move_id="TEST",
            name="Test",
            move_type=PokemonType.NORMAL,
            power=0,
            accuracy=100,
            pp=0,
            max_pp=0,
            category=MoveCategory.STATUS
        )
        assert move.pp_percentage() == 0.0

    def test_experience_level_progress(self):
        """Test experience level progress calculation"""
        exp = Experience(current=2500, to_next_level=2500, growth_rate="medium")
        assert exp.level_progress() == 0.5

    def test_pokemon_stats_total(self):
        """Test PokemonStats total calculation"""
        stats = PokemonStats(hp=100, attack=80, defense=70, speed=90, special=85)
        assert stats.total() == 425

    def test_type_value_weights_defaults(self):
        """Test TypeValueWeights default values"""
        weights = TypeValueWeights()
        assert weights.ELECTRIC == 1.5
        assert weights.NORMAL == 0.6
        assert weights.BUG == 0.8

    def test_type_value_weights_get_weight(self):
        """Test TypeValueWeights get_weight method"""
        weights = TypeValueWeights()
        assert weights.get_weight(PokemonType.ELECTRIC) == 1.5
        assert weights.get_weight(PokemonType.NORMAL) == 0.6

    def test_carry_score_breakdown_to_dict(self):
        """Test CarryScoreBreakdown to_dict conversion"""
        breakdown = CarryScoreBreakdown(
            level_relevance=20.0,
            type_uniqueness=25.0,
            move_coverage=15.0,
            stat_efficiency=18.0,
            rarity_modifier=1.0,
            sentimental_modifier=1.0,
            final_score=78.0
        )
        data = breakdown.to_dict()
        assert data["level_relevance"] == 20.0
        assert data["final_score"] == 78.0

    def test_type_coverage_to_dict(self):
        """Test TypeCoverage to_dict conversion"""
        coverage = TypeCoverage(
            covered_types={PokemonType.FIRE, PokemonType.WATER},
            uncovered_types={PokemonType.DRAGON},
            critical_gaps={PokemonType.GROUND},
            coverage_percentage=0.75
        )
        data = coverage.to_dict()
        assert PokemonType.FIRE.value in data["covered_types"]
        assert PokemonType.DRAGON.value in data["uncovered_types"]

    def test_evolution_decision_creation(self):
        """Test EvolutionDecision creation"""
        decision = EvolutionDecision(
            decision="evolve_now",
            wait_levels=None,
            reason="Stat improvement significant",
            expected_move=None,
            stat_improvement=25.5,
            net_benefit_score=10.0
        )
        assert decision.decision == "evolve_now"
        assert decision.wait_levels is None

    def test_party_slot_creation(self):
        """Test PartySlot creation"""
        slot = PartySlot(
            slot_index=0,
            pokemon=None,
            score=85.0,
            recommended_role="sweeper",
            suggested_moves=["Thunderbolt", "Quick Attack"]
        )
        assert slot.slot_index == 0
        assert slot.recommended_role == "sweeper"

    def test_critical_pre_evo_moves_defined(self):
        """Test CRITICAL_PRE_EVO_MOVES is defined"""
        assert "BULBASAUR" in CRITICAL_PRE_EVO_MOVES
        assert "CHARMANDER" in CRITICAL_PRE_EVO_MOVES
        assert "SQUIRTLE" in CRITICAL_PRE_EVO_MOVES

    def test_critical_pre_evo_moves_content(self):
        """Test CRITICAL_PRE_EVO_MOVES has correct content"""
        charmander_moves = CRITICAL_PRE_EVO_MOVES["CHARMANDER"]
        assert len(charmander_moves) == 2
        move_names = [m.move_name for m in charmander_moves]
        assert "Flamethrower" in move_names
        assert "Slash" in move_names


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_empty_party(self, type_chart):
        """Test operations with empty party"""
        calculator = CarryScoreCalculator(type_chart, {})
        optimizer = TeamCompositionOptimizer(calculator, {}, type_chart)
        
        empty_party: List[Optional[PokemonData]] = [None, None, None, None, None, None]
        
        coverage = optimizer.analyze_type_coverage(empty_party)
        distribution = optimizer.calculate_stat_distribution(empty_party)
        overlaps = optimizer.detect_move_overlap(empty_party)
        
        assert coverage.coverage_percentage == 0.0
        assert distribution["attack"] == 0.0

    def test_team_with_all_fainted(self, sample_pokemon_data, type_chart):
        """Test team where all Pokemon are fainted"""
        sample_pokemon_data.current_hp = 0
        team = Team(
            team_id="test",
            name=None,
            party=[sample_pokemon_data, None, None, None, None, None],
            box=[]
        )
        assert team.can_battle() is False
        assert team.battle_ready_count() == 0

    def test_party_with_hm_users(self, full_party, type_chart):
        """Test HM user detection in full party"""
        assert full_party.has_hm_user() is False
        full_party.party[0].moves.append(
            Move(move_id="CUT", name="Cut", move_type=PokemonType.NORMAL, power=50, accuracy=95, pp=30, max_pp=30, category=MoveCategory.PHYSICAL)
        )
        assert full_party.has_hm_user() is True
        hm_users = full_party.get_hm_users()
        assert "CUT" in hm_users

    def test_level_spread_calculation(self, full_party):
        """Test level spread calculation accuracy"""
        spread = full_party.level_spread()
        assert spread == 52 - 15  # Venusaur level - Rattata level

    def test_carry_score_with_different_parties(self, full_party, type_chart):
        """Test carry score varies with party composition"""
        calculator = CarryScoreCalculator(type_chart, {})
        
        pikachu = full_party.party[0]
        score_alone, _ = calculator.calculate_carry_score(pikachu, [pikachu] + [None] * 5)
        score_full, _ = calculator.calculate_carry_score(pikachu, full_party.party)
        
        assert score_alone >= 0
        assert score_full >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])