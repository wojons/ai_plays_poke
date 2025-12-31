"""
Tests for Tactical Combat Heuristics module

Covers:
- DamageCalculator Gen 1 formula accuracy
- TypeChart effectiveness calculations
- MoveSelector scoring and prioritization
- EnemyPredictor behavior prediction
- BattleStrategist switch and catch decisions
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.combat import (
    PokemonType, StatusCondition, MoveCategory, StatStage,
    Move, Pokemon, DamageRange, MoveScore, SwitchCandidate, CatchAttempt,
    TypeChart, DamageCalculator, MoveSelector, EnemyPredictor, BattleStrategist,
    CombatManager
)


class TestTypeChart:
    """Test type effectiveness chart calculations"""

    def setup_method(self):
        self.type_chart = TypeChart()

    def test_fire_vs_grass_super_effective(self):
        """Fire should be super effective against Grass"""
        effectiveness = self.type_chart.get_effectiveness(
            PokemonType.FIRE, [PokemonType.GRASS]
        )
        assert effectiveness == 2.0

    def test_fire_vs_water_not_very_effective(self):
        """Fire should not be very effective against Water"""
        effectiveness = self.type_chart.get_effectiveness(
            PokemonType.FIRE, [PokemonType.WATER]
        )
        assert effectiveness == 0.5

    def test_electric_vs_ground_immune(self):
        """Electric should be immune to Ground"""
        effectiveness = self.type_chart.get_effectiveness(
            PokemonType.ELECTRIC, [PokemonType.GROUND]
        )
        assert effectiveness == 0.0

    def test_fighting_vs_ghost_immune(self):
        """Fighting should be immune to Ghost"""
        effectiveness = self.type_chart.get_effectiveness(
            PokemonType.FIGHTING, [PokemonType.GHOST]
        )
        assert effectiveness == 0.0

    def test_psychic_vs_dark_immune(self):
        """Psychic should be immune to Dark"""
        effectiveness = self.type_chart.get_effectiveness(
            PokemonType.PSYCHIC, [PokemonType.DARK]
        )
        assert effectiveness == 0.0

    def test_dual_type_multiplication(self):
        """Dual types should multiply effectiveness"""
        charizard_types = [PokemonType.FIRE, PokemonType.FLYING]
        water_effectiveness = self.type_chart.get_effectiveness(
            PokemonType.WATER, charizard_types
        )
        assert water_effectiveness == 2.0

    def test_super_effective_helper(self):
        """is_super_effective should detect >= 2.0"""
        assert self.type_chart.is_super_effective(
            PokemonType.FIRE, [PokemonType.GRASS]
        )
        assert not self.type_chart.is_super_effective(
            PokemonType.FIRE, [PokemonType.WATER]
        )

    def test_immune_helper(self):
        """is_immune should detect 0.0 effectiveness"""
        assert self.type_chart.is_immune(
            PokemonType.NORMAL, [PokemonType.GHOST]
        )
        assert not self.type_chart.is_immune(
            PokemonType.FIRE, [PokemonType.GRASS]
        )

    def test_all_18_types_present(self):
        """All 18 types should be in the chart"""
        expected_types = [
            PokemonType.NORMAL, PokemonType.FIRE, PokemonType.WATER,
            PokemonType.ELECTRIC, PokemonType.GRASS, PokemonType.ICE,
            PokemonType.FIGHTING, PokemonType.POISON, PokemonType.GROUND,
            PokemonType.FLYING, PokemonType.PSYCHIC, PokemonType.BUG,
            PokemonType.ROCK, PokemonType.GHOST, PokemonType.DRAGON,
            PokemonType.DARK, PokemonType.STEEL, PokemonType.FAIRY
        ]
        for ptype in expected_types:
            assert ptype in [t for t in PokemonType]

    def test_neutral_damage(self):
        """Neutral matchups should return 1.0"""
        effectiveness = self.type_chart.get_effectiveness(
            PokemonType.NORMAL, [PokemonType.ELECTRIC]
        )
        assert effectiveness == 1.0


class TestDamageCalculator:
    """Test Gen 1 damage calculation"""

    def setup_method(self):
        self.type_chart = TypeChart()
        self.calculator = DamageCalculator(self.type_chart)

    def test_base_damage_formula(self):
        """Test basic damage formula output"""
        damage = self.calculator.calculate_base_damage(
            level=50, power=100, attack=100, defense=100
        )
        assert damage > 0
        assert isinstance(damage, int)

    def test_stab_bonus(self):
        """STAB should increase damage by 1.5x"""
        damage_no_stab = self.calculator.calculate_base_damage(
            level=50, power=100, attack=100, defense=100, stab=1.0
        )
        damage_stab = self.calculator.calculate_base_damage(
            level=50, power=100, attack=100, defense=100, stab=1.5
        )
        assert damage_stab == int(damage_no_stab * 1.5)

    def test_type_effectiveness_multiplier(self):
        """Type effectiveness should multiply damage"""
        damage_neutral = self.calculator.calculate_base_damage(
            level=50, power=100, attack=100, defense=100,
            type_effectiveness=1.0
        )
        damage_super = self.calculator.calculate_base_damage(
            level=50, power=100, attack=100, defense=100,
            type_effectiveness=2.0
        )
        assert damage_super == damage_neutral * 2

    def test_critical_hit(self):
        """Critical hit should double damage"""
        damage_normal = self.calculator.calculate_base_damage(
            level=50, power=100, attack=100, defense=100,
            is_critical=False
        )
        damage_crit = self.calculator.calculate_base_damage(
            level=50, power=100, attack=100, defense=100,
            is_critical=True
        )
        assert damage_crit == damage_normal * 2

    def test_damage_range_bounds(self):
        """Damage range should be consistent with 85-100% random factor"""
        damage_085 = self.calculator.calculate_base_damage(
            level=50, power=100, attack=100, defense=100,
            random_factor=0.85
        )
        damage_100 = self.calculator.calculate_base_damage(
            level=50, power=100, attack=100, defense=100,
            random_factor=1.0
        )
        assert damage_085 <= damage_100

    def test_effective_stat_calculation(self):
        """Stat stages should modify stats correctly"""
        base_stat = 100
        assert self.calculator.calculate_effective_stat(base_stat, 0) == 100.0
        assert self.calculator.calculate_effective_stat(base_stat, 1) == 150.0
        assert self.calculator.calculate_effective_stat(base_stat, 2) == 200.0
        assert self.calculator.calculate_effective_stat(base_stat, -1) == 50.0

    def test_stab_detection(self):
        """STAB should be detected when move type matches Pokemon type"""
        pikachu_types = [PokemonType.ELECTRIC]
        assert self.calculator.calculate_stab(PokemonType.ELECTRIC, pikachu_types) == 1.5
        assert self.calculator.calculate_stab(PokemonType.NORMAL, pikachu_types) == 1.0

    def test_damage_range_calculation(self):
        """Damage range should provide min/max values"""
        attacker = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=100, attack=100, defense=80,
            speed=120, special=100, moves=[]
        )
        defender = Pokemon(
            name="Bulbasaur", level=45, types=[PokemonType.GRASS, PokemonType.POISON],
            max_hp=100, current_hp=80, attack=80, defense=80,
            speed=60, special=80, moves=[]
        )
        thunder_shock = Move(
            name="Thunder Shock", move_type=PokemonType.ELECTRIC,
            power=40, accuracy=100, pp=30, max_pp=30,
            category=MoveCategory.SPECIAL
        )

        damage_range = self.calculator.calculate_damage_range(
            attacker, defender, thunder_shock
        )

        assert damage_range.min_damage > 0
        assert damage_range.max_damage >= damage_range.min_damage
        assert damage_range.expected_damage >= damage_range.min_damage
        assert damage_range.expected_damage <= damage_range.max_damage

    def test_ko_prediction(self):
        """KO prediction should be accurate"""
        attacker = Pokemon(
            name="Charizard", level=50, types=[PokemonType.FIRE, PokemonType.FLYING],
            max_hp=100, current_hp=100, attack=120, defense=90,
            speed=100, special=130, moves=[]
        )
        defender = Pokemon(
            name="Butterfree", level=40, types=[PokemonType.BUG, PokemonType.FLYING],
            max_hp=80, current_hp=30, attack=70, defense=60,
            speed=80, special=90, moves=[]
        )
        flamethrower = Move(
            name="Flamethrower", move_type=PokemonType.FIRE,
            power=95, accuracy=100, pp=15, max_pp=15,
            category=MoveCategory.SPECIAL
        )

        damage_range = self.calculator.calculate_damage_range(
            attacker, defender, flamethrower
        )
        guaranteed, likely, possible = self.calculator.can_ko(
            damage_range, defender.current_hp
        )

        if guaranteed:
            assert defender.current_hp <= damage_range.min_damage

    def test_minimum_damage(self):
        """Minimum damage should always be at least 1"""
        damage = self.calculator.calculate_base_damage(
            level=1, power=1, attack=1, defense=1000,
            stab=1.0, type_effectiveness=1.0,
            is_critical=False, random_factor=0.85
        )
        assert damage >= 1


class TestMoveSelector:
    """Test move selection and scoring heuristics"""

    def setup_method(self):
        self.type_chart = TypeChart()
        self.selector = MoveSelector(self.type_chart)

    def test_stab_scoring_bonus(self):
        """STAB moves should score higher"""
        attacker = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=100, attack=100, defense=80,
            speed=120, special=100,
            moves=[
                Move(name="Thunder Shock", move_type=PokemonType.ELECTRIC,
                     power=40, accuracy=100, pp=30, max_pp=30,
                     category=MoveCategory.SPECIAL),
                Move(name="Quick Attack", move_type=PokemonType.NORMAL,
                     power=40, accuracy=100, pp=30, max_pp=30,
                     category=MoveCategory.PHYSICAL)
            ]
        )
        defender = Pokemon(
            name="Squirtle", level=45, types=[PokemonType.WATER],
            max_hp=100, current_hp=100, attack=80, defense=100,
            speed=60, special=80, moves=[]
        )

        thunder_score = self.selector.score_move(
            attacker.moves[0], attacker, defender
        )
        quick_score = self.selector.score_move(
            attacker.moves[1], attacker, defender
        )

        assert thunder_score.has_stab
        assert not quick_score.has_stab
        assert thunder_score.score > quick_score.score

    def test_type_effectiveness_scoring(self):
        """Super effective moves should score higher"""
        attacker = Pokemon(
            name="Charmander", level=50, types=[PokemonType.FIRE],
            max_hp=100, current_hp=100, attack=100, defense=80,
            speed=100, special=100,
            moves=[
                Move(name="Ember", move_type=PokemonType.FIRE,
                     power=40, accuracy=100, pp=40, max_pp=40,
                     category=MoveCategory.SPECIAL),
                Move(name="Scratch", move_type=PokemonType.NORMAL,
                     power=40, accuracy=100, pp=35, max_pp=35,
                     category=MoveCategory.PHYSICAL)
            ]
        )
        defender = Pokemon(
            name="Bulbasaur", level=45, types=[PokemonType.GRASS],
            max_hp=100, current_hp=100, attack=80, defense=80,
            speed=70, special=80, moves=[]
        )

        ember_score = self.selector.score_move(
            attacker.moves[0], attacker, defender
        )
        scratch_score = self.selector.score_move(
            attacker.moves[1], attacker, defender
        )

        assert ember_score.effectiveness == 2.0
        assert scratch_score.effectiveness == 1.0
        assert ember_score.score > scratch_score.score

    def test_accuracy_penalty(self):
        """Low accuracy moves should be penalized for risk-averse AI"""
        attacker = Pokemon(
            name="Charizard", level=50, types=[PokemonType.FIRE, PokemonType.FLYING],
            max_hp=100, current_hp=100, attack=120, defense=90,
            speed=100, special=130,
            moves=[
                Move(name="Flamethrower", move_type=PokemonType.FIRE,
                     power=95, accuracy=100, pp=15, max_pp=15,
                     category=MoveCategory.SPECIAL),
                Move(name="Blast Burn", move_type=PokemonType.FIRE,
                     power=150, accuracy=90, pp=5, max_pp=5,
                     category=MoveCategory.SPECIAL)
            ]
        )
        defender = Pokemon(
            name="Onix", level=45, types=[PokemonType.ROCK, PokemonType.GROUND],
            max_hp=100, current_hp=100, attack=90, defense=130,
            speed=70, special=60, moves=[]
        )

        risk_averse = self.selector.score_move(
            attacker.moves[1], attacker, defender, risk_averse=True
        )
        not_risk_averse = self.selector.score_move(
            attacker.moves[1], attacker, defender, risk_averse=False
        )

        assert risk_averse.score <= not_risk_averse.score

    def test_ko_bonus(self):
        """Moves that can KO should get significant bonus"""
        attacker = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=100, attack=100, defense=80,
            speed=120, special=100,
            moves=[
                Move(name="Thunder", move_type=PokemonType.ELECTRIC,
                     power=110, accuracy=70, pp=10, max_pp=10,
                     category=MoveCategory.SPECIAL)
            ]
        )
        defender = Pokemon(
            name="Weedle", level=10, types=[PokemonType.BUG, PokemonType.POISON],
            max_hp=30, current_hp=5, attack=30, defense=20,
            speed=50, special=20, moves=[]
        )

        score = self.selector.score_move(
            attacker.moves[0], attacker, defender
        )

        assert score.ko_likely

    def test_immune_moves_scored_zero(self):
        """Immune moves should get zero score"""
        attacker = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=100, attack=100, defense=80,
            speed=120, special=100,
            moves=[
                Move(name="Thunder", move_type=PokemonType.ELECTRIC,
                     power=110, accuracy=70, pp=10, max_pp=10,
                     category=MoveCategory.SPECIAL)
            ]
        )
        defender = Pokemon(
            name="Golem", level=45, types=[PokemonType.GROUND],
            max_hp=100, current_hp=100, attack=110, defense=120,
            speed=45, special=80, moves=[]
        )

        score = self.selector.score_move(
            attacker.moves[0], attacker, defender
        )

        assert score.score == 0.0
        assert "Immune" in score.notes[0]

    def test_select_best_move(self):
        """Select best move should return highest scoring move"""
        attacker = Pokemon(
            name="Blastoise", level=50, types=[PokemonType.WATER],
            max_hp=120, current_hp=100, attack=100, defense=120,
            speed=80, special=100,
            moves=[
                Move(name="Hydro Pump", move_type=PokemonType.WATER,
                     power=110, accuracy=80, pp=10, max_pp=10,
                     category=MoveCategory.SPECIAL),
                Move(name="Water Gun", move_type=PokemonType.WATER,
                     power=40, accuracy=100, pp=25, max_pp=25,
                     category=MoveCategory.SPECIAL),
                Move(name="Tackle", move_type=PokemonType.NORMAL,
                     power=40, accuracy=100, pp=35, max_pp=35,
                     category=MoveCategory.PHYSICAL)
            ]
        )
        defender = Pokemon(
            name="Charizard", level=45, types=[PokemonType.FIRE, PokemonType.FLYING],
            max_hp=100, current_hp=80, attack=110, defense=85,
            speed=100, special=120, moves=[]
        )

        best = self.selector.select_best_move(attacker, defender)

        assert best.move.name == "Hydro Pump"
        assert best.effectiveness == 2.0
        assert best.has_stab

    def test_priority_move_scoring(self):
        """Priority moves should get bonus when slower"""
        slow_pokemon = Pokemon(
            name="Slowpoke", level=50, types=[PokemonType.WATER, PokemonType.PSYCHIC],
            max_hp=100, current_hp=100, attack=80, defense=80,
            speed=30, special=80,
            moves=[
                Move(name="Quick Attack", move_type=PokemonType.NORMAL,
                     power=40, accuracy=100, pp=30, max_pp=30,
                     category=MoveCategory.PHYSICAL, priority=1),
                Move(name="Tackle", move_type=PokemonType.NORMAL,
                     power=40, accuracy=100, pp=35, max_pp=35,
                     category=MoveCategory.PHYSICAL)
            ]
        )
        fast_defender = Pokemon(
            name="Pikachu", level=45, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=100, attack=100, defense=80,
            speed=120, special=100, moves=[]
        )

        priority_score = self.selector.score_move(
            slow_pokemon.moves[0], slow_pokemon, fast_defender
        )
        normal_score = self.selector.score_move(
            slow_pokemon.moves[1], slow_pokemon, fast_defender
        )

        assert priority_score.score > normal_score.score


class TestEnemyPredictor:
    """Test enemy behavior prediction"""

    def setup_method(self):
        self.type_chart = TypeChart()
        self.predictor = EnemyPredictor(self.type_chart)

    def test_base_move_prediction(self):
        """Should predict known base moves"""
        moves = self.predictor.predict_moves("Pikachu", 50)
        assert "Thunder Shock" in moves
        assert "Quick Attack" in moves

    def test_trainer_behavior_retrieval(self):
        """Should retrieve behavior for trainer types"""
        gym_behavior = self.predictor.get_trainer_behavior("gym_leader")
        assert gym_behavior["aggression"] > 0.8
        assert gym_behavior["prefer_strong_moves"]

    def test_threat_level_calculation(self):
        """Threat level should reflect danger"""
        enemy = Pokemon(
            name="Gyarados", level=55, types=[PokemonType.WATER, PokemonType.FLYING],
            max_hp=120, current_hp=100, attack=130, defense=100,
            speed=85, special=100,
            moves=[
                Move(name="Hydro Pump", move_type=PokemonType.WATER,
                     power=110, accuracy=80, pp=10, max_pp=10,
                     category=MoveCategory.SPECIAL),
                Move(name="Hyper Beam", move_type=PokemonType.NORMAL,
                     power=150, accuracy=90, pp=5, max_pp=5,
                     category=MoveCategory.SPECIAL)
            ]
        )
        player = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=100, attack=100, defense=80,
            speed=120, special=100, moves=[]
        )

        threat = self.predictor.predict_threat_level(enemy, player)

        assert 0.0 <= threat <= 1.0
        assert threat > 0

    def test_unknown_species_default_moves(self):
        """Unknown species should get default moves"""
        moves = self.predictor.predict_moves("UnknownPokemon", 50)
        assert len(moves) > 0
        assert "Tackle" in moves

    def test_aggressive_trainer_prediction(self):
        """Aggressive trainers should prefer strong moves"""
        youngster = self.predictor.get_trainer_behavior("youngster")
        assert youngster["aggression"] > 0.5
        assert youngster["heal_threshold"] < 0.5


class TestBattleStrategist:
    """Test battle strategy decisions"""

    def setup_method(self):
        self.type_chart = TypeChart()
        self.strategist = BattleStrategist(self.type_chart)
        self.move_selector = MoveSelector(self.type_chart)

    def test_switch_on_low_hp(self):
        """Should switch when HP is critical"""
        current = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=5, attack=100, defense=80,
            speed=120, special=100, moves=[]
        )
        opponent = Pokemon(
            name="Charizard", level=55, types=[PokemonType.FIRE, PokemonType.FLYING],
            max_hp=120, current_hp=100, attack=120, defense=90,
            speed=100, special=130, moves=[
                Move(name="Flamethrower", move_type=PokemonType.FIRE,
                     power=95, accuracy=100, pp=15, max_pp=15,
                     category=MoveCategory.SPECIAL)
            ]
        )
        party = [
            Pokemon(name="Blastoise", level=52, types=[PokemonType.WATER],
                    max_hp=120, current_hp=100, attack=100, defense=120,
                    speed=70, special=100, moves=[])
        ]

        should_switch, reason, _ = self.strategist.should_switch(
            current, opponent, party, self.move_selector
        )

        assert should_switch
        assert "Critical HP" in reason or "emergency" in reason.lower()

    def test_switch_on_type_disadvantage(self):
        """Should switch when at severe type disadvantage"""
        current = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=80, attack=100, defense=80,
            speed=120, special=100,
            moves=[
                Move(name="Thunder", move_type=PokemonType.ELECTRIC,
                     power=110, accuracy=70, pp=10, max_pp=10,
                     category=MoveCategory.SPECIAL)
            ]
        )
        opponent = Pokemon(
            name="Golem", level=55, types=[PokemonType.GROUND],
            max_hp=120, current_hp=100, attack=130, defense=120,
            speed=45, special=80,
            moves=[
                Move(name="Earthquake", move_type=PokemonType.GROUND,
                     power=100, accuracy=100, pp=10, max_pp=10,
                     category=MoveCategory.PHYSICAL)
            ]
        )
        party = [
            Pokemon(name="Venusaur", level=52, types=[PokemonType.GRASS, PokemonType.POISON],
                    max_hp=120, current_hp=100, attack=100, defense=100,
                    speed=80, special=120, moves=[])
        ]

        should_switch, reason, _ = self.strategist.should_switch(
            current, opponent, party, self.move_selector
        )

        assert should_switch

    def test_no_switch_when_can_ko(self):
        """Should not switch when can KO opponent"""
        current = Pokemon(
            name="Charizard", level=60, types=[PokemonType.FIRE, PokemonType.FLYING],
            max_hp=120, current_hp=100, attack=130, defense=90,
            speed=110, special=140,
            moves=[
                Move(name="Flamethrower", move_type=PokemonType.FIRE,
                     power=95, accuracy=100, pp=15, max_pp=15,
                     category=MoveCategory.SPECIAL)
            ]
        )
        opponent = Pokemon(
            name="Weedle", level=10, types=[PokemonType.BUG, PokemonType.POISON],
            max_hp=30, current_hp=5, attack=30, defense=20,
            speed=50, special=20, moves=[]
        )
        party = []

        should_switch, reason, _ = self.strategist.should_switch(
            current, opponent, party, self.move_selector
        )

        assert not should_switch
        assert "Can KO" in reason

    def test_catch_probability_calculation(self):
        """Catch probability should account for HP and status"""
        catch = self.strategist.calculate_catch_probability(
            species="Pikachu",
            max_hp=100,
            current_hp=10,
            status=StatusCondition.ASLEEP,
            ball_type="Poke Ball"
        )

        assert catch.catch_rate > 0
        assert catch.status_factor == 2.5
        assert catch.hp_factor > 0
        assert 0.0 <= catch.success_probability <= 1.0

    def test_catch_ball_factor(self):
        """Different balls should have different factors"""
        catch_poke = self.strategist.calculate_catch_probability(
            "Pikachu", 100, 50, StatusCondition.NONE, "Poke Ball"
        )
        catch_great = self.strategist.calculate_catch_probability(
            "Pikachu", 100, 50, StatusCondition.NONE, "Great Ball"
        )
        catch_ultra = self.strategist.calculate_catch_probability(
            "Pikachu", 100, 50, StatusCondition.NONE, "Ultra Ball"
        )

        assert catch_great.ball_factor > catch_poke.ball_factor
        assert catch_ultra.ball_factor > catch_great.ball_factor

    def test_setup_opportunity_assessment(self):
        """Should assess if setup is safe"""
        attacker = Pokemon(
            name="Charizard", level=50, types=[PokemonType.FIRE, PokemonType.FLYING],
            max_hp=120, current_hp=100, attack=120, defense=90,
            speed=100, special=130, moves=[]
        )
        weak_opponent = Pokemon(
            name="Caterpie", level=5, types=[PokemonType.BUG],
            max_hp=20, current_hp=5, attack=15, defense=15,
            speed=20, special=15, moves=[
                Move(name="Tackle", move_type=PokemonType.NORMAL,
                     power=30, accuracy=100, pp=35, max_pp=35,
                     category=MoveCategory.PHYSICAL)
            ]
        )

        is_safe, score, reasoning = self.strategist.assess_setup_opportunity(
            attacker, weak_opponent
        )

        assert is_safe
        assert score > 0.5

    def test_1_hp_risk_assessment(self):
        """Should assess risk when enemy is at 1 HP"""
        attacker = Pokemon(
            name="Charizard", level=50, types=[PokemonType.FIRE, PokemonType.FLYING],
            max_hp=120, current_hp=100, attack=120, defense=90,
            speed=100, special=130,
            moves=[
                Move(name="Flamethrower", move_type=PokemonType.FIRE,
                     power=95, accuracy=100, pp=15, max_pp=15,
                     category=MoveCategory.SPECIAL),
                Move(name="Ember", move_type=PokemonType.FIRE,
                     power=40, accuracy=100, pp=40, max_pp=40,
                     category=MoveCategory.SPECIAL)
            ]
        )
        defender = Pokemon(
            name="Pidgey", level=20, types=[PokemonType.NORMAL, PokemonType.FLYING],
            max_hp=50, current_hp=1, attack=40, defense=35,
            speed=60, special=35, moves=[]
        )

        is_safe, reasoning = self.strategist.assess_1_hp_risk(
            attacker, defender, attacker.moves[0]
        )

        assert is_safe or "GUARANTEED" in reasoning or "HIGH chance" in reasoning

    def test_switch_candidate_evaluation(self):
        """Should evaluate switch candidates properly"""
        current = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=50, attack=100, defense=80,
            speed=120, special=100, moves=[]
        )
        opponent = Pokemon(
            name="Gyarados", level=55, types=[PokemonType.WATER, PokemonType.FLYING],
            max_hp=120, current_hp=100, attack=130, defense=100,
            speed=85, special=100,
            moves=[
                Move(name="Hydro Pump", move_type=PokemonType.WATER,
                     power=110, accuracy=80, pp=10, max_pp=10,
                     category=MoveCategory.SPECIAL)
            ]
        )
        party = [
            Pokemon(name="Vulpix", level=52, types=[PokemonType.FIRE],
                    max_hp=90, current_hp=100, attack=90, defense=80,
                    speed=100, special=110,
                    moves=[Move(name="Ember", move_type=PokemonType.FIRE,
                                power=40, accuracy=100, pp=40, max_pp=40,
                                category=MoveCategory.SPECIAL)]),
            Pokemon(name="Bulbasaur", level=48, types=[PokemonType.GRASS, PokemonType.POISON],
                    max_hp=100, current_hp=30, attack=80, defense=80,
                    speed=70, special=80,
                    moves=[Move(name="Vine Whip", move_type=PokemonType.GRASS,
                                power=35, accuracy=100, pp=35, max_pp=35,
                                category=MoveCategory.PHYSICAL)])
        ]

        candidates = self.strategist.evaluate_switch_candidates(
            current, opponent, party, self.move_selector
        )

        assert len(candidates) > 0
        best = candidates[0]
        assert best.pokemon_name == "Vulpix"
        assert best.score > 0


class TestCombatManager:
    """Test main combat manager"""

    def setup_method(self):
        self.combat = CombatManager()

    def test_get_combat_state(self):
        """Should return comprehensive combat state"""
        player = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=80, attack=100, defense=80,
            speed=120, special=100,
            moves=[
                Move(name="Thunder Shock", move_type=PokemonType.ELECTRIC,
                     power=40, accuracy=100, pp=30, max_pp=30,
                     category=MoveCategory.SPECIAL),
                Move(name="Quick Attack", move_type=PokemonType.NORMAL,
                     power=40, accuracy=100, pp=30, max_pp=30,
                     category=MoveCategory.PHYSICAL)
            ]
        )
        enemy = Pokemon(
            name="Squirtle", level=45, types=[PokemonType.WATER],
            max_hp=100, current_hp=60, attack=80, defense=100,
            speed=60, special=80,
            moves=[
                Move(name="Water Gun", move_type=PokemonType.WATER,
                     power=40, accuracy=100, pp=25, max_pp=25,
                     category=MoveCategory.SPECIAL)
            ]
        )

        state = self.combat.get_combat_state(player, enemy, "wild")

        assert "best_move" in state
        assert "best_move_score" in state
        assert "threat_level" in state
        assert "should_switch" in state
        assert state["best_move"] == "Thunder Shock"

    def test_calculate_catch_odds(self):
        """Should calculate catch odds for wild Pokemon"""
        odds = self.combat.calculate_catch_odds(
            species="Pikachu",
            max_hp=100,
            current_hp=20,
            status=StatusCondition.ASLEEP,
            ball_type="Poke Ball"
        )

        assert isinstance(odds, CatchAttempt)
        assert odds.success_probability > 0.5

    def test_combat_state_switch_recommendation(self):
        """Should recommend switch when appropriate"""
        player = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=10, attack=100, defense=80,
            speed=120, special=100,
            moves=[
                Move(name="Thunder Shock", move_type=PokemonType.ELECTRIC,
                     power=40, accuracy=100, pp=30, max_pp=30,
                     category=MoveCategory.SPECIAL)
            ]
        )
        enemy = Pokemon(
            name="Gyarados", level=60, types=[PokemonType.WATER, PokemonType.FLYING],
            max_hp=130, current_hp=100, attack=140, defense=110,
            speed=90, special=110,
            moves=[
                Move(name="Hydro Pump", move_type=PokemonType.WATER,
                     power=110, accuracy=80, pp=10, max_pp=10,
                     category=MoveCategory.SPECIAL),
                Move(name="Earthquake", move_type=PokemonType.GROUND,
                     power=100, accuracy=100, pp=10, max_pp=10,
                     category=MoveCategory.PHYSICAL)
            ]
        )

        state = self.combat.get_combat_state(player, enemy, "wild")

        assert state["should_switch"]


class TestStatStages:
    """Test stat stage calculations"""

    def test_multiplier_values(self):
        """Stat stages should have correct multipliers"""
        assert StatStage.ZERO.multiplier == 1.0
        assert StatStage.POSITIVE_1.multiplier == 1.5
        assert StatStage.POSITIVE_2.multiplier == 2.0
        assert StatStage.POSITIVE_6.multiplier == 4.0

    def test_negative_multipliers(self):
        """Negative stat stages should have reduced multipliers"""
        assert StatStage.NEGATIVE_1.multiplier == 0.6667
        assert StatStage.NEGATIVE_2.multiplier == 0.5
        assert StatStage.NEGATIVE_6.multiplier == 0.25


class TestMoveCategories:
    """Test move categories and attributes"""

    def test_move_creation(self):
        """Moves should be created with correct attributes"""
        move = Move(
            name="Thunderbolt",
            move_type=PokemonType.ELECTRIC,
            power=90,
            accuracy=100,
            pp=15,
            max_pp=15,
            category=MoveCategory.SPECIAL,
            priority=0,
            is_high_crit=False
        )

        assert move.name == "Thunderbolt"
        assert move.move_type == PokemonType.ELECTRIC
        assert move.power == 90
        assert move.category == MoveCategory.SPECIAL

    def test_status_move(self):
        """Status moves should have 0 power"""
        status_move = Move(
            name="Thunder Wave",
            move_type=PokemonType.ELECTRIC,
            power=0,
            accuracy=90,
            pp=20,
            max_pp=20,
            category=MoveCategory.STATUS
        )

        assert status_move.category == MoveCategory.STATUS
        assert status_move.power == 0

    def test_priority_move(self):
        """Priority moves should have positive priority"""
        quick_attack = Move(
            name="Quick Attack",
            move_type=PokemonType.NORMAL,
            power=40,
            accuracy=100,
            pp=30,
            max_pp=30,
            category=MoveCategory.PHYSICAL,
            priority=1
        )

        assert quick_attack.priority == 1

    def test_high_crit_move(self):
        """High crit moves should be marked"""
        slash = Move(
            name="Slash",
            move_type=PokemonType.NORMAL,
            power=70,
            accuracy=100,
            pp=20,
            max_pp=20,
            category=MoveCategory.PHYSICAL,
            is_high_crit=True
        )

        assert slash.is_high_crit


class TestPokemonData:
    """Test Pokemon data structure"""

    def test_pokemon_creation(self):
        """Pokemon should be created with correct attributes"""
        pikachu = Pokemon(
            name="Pikachu",
            level=50,
            types=[PokemonType.ELECTRIC],
            max_hp=100,
            current_hp=80,
            attack=100,
            defense=80,
            speed=120,
            special=100,
            moves=[],
            status=StatusCondition.NONE
        )

        assert pikachu.name == "Pikachu"
        assert pikachu.level == 50
        assert pikachu.types == [PokemonType.ELECTRIC]
        assert pikachu.current_hp == 80
        assert pikachu.status == StatusCondition.NONE

    def test_pokemon_with_moves(self):
        """Pokemon with moves should track them"""
        thunder_shock = Move(
            name="Thunder Shock", move_type=PokemonType.ELECTRIC,
            power=40, accuracy=100, pp=30, max_pp=30,
            category=MoveCategory.SPECIAL
        )
        quick_attack = Move(
            name="Quick Attack", move_type=PokemonType.NORMAL,
            power=40, accuracy=100, pp=30, max_pp=30,
            category=MoveCategory.PHYSICAL
        )

        pikachu = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=100, attack=100, defense=80,
            speed=120, special=100,
            moves=[thunder_shock, quick_attack]
        )

        assert len(pikachu.moves) == 2
        assert pikachu.moves[0].name == "Thunder Shock"

    def test_pokemon_with_status(self):
        """Pokemon should track status conditions"""
        paralyzed_pikachu = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=100, attack=100, defense=80,
            speed=120, special=100, moves=[],
            status=StatusCondition.PARALYZED
        )

        assert paralyzed_pikachu.status == StatusCondition.PARALYZED

    def test_pokemon_stat_stages(self):
        """Pokemon should track stat stages"""
        boosted_pokemon = Pokemon(
            name="Charizard", level=50, types=[PokemonType.FIRE, PokemonType.FLYING],
            max_hp=120, current_hp=100, attack=120, defense=90,
            speed=100, special=130, moves=[],
            attack_stage=2, special_stage=1
        )

        assert boosted_pokemon.attack_stage == 2
        assert boosted_pokemon.special_stage == 1


class TestStatusConditions:
    """Test status condition handling"""

    def test_status_none(self):
        """Default status should be NONE"""
        pokemon = Pokemon(
            name="Pikachu", level=50, types=[PokemonType.ELECTRIC],
            max_hp=100, current_hp=100, attack=100, defense=80,
            speed=120, special=100, moves=[]
        )

        assert pokemon.status == StatusCondition.NONE

    def test_all_statuses_defined(self):
        """All status conditions should be defined"""
        expected_statuses = [
            StatusCondition.NONE, StatusCondition.POISONED,
            StatusCondition.BADLY_POISONED, StatusCondition.BURNED,
            StatusCondition.PARALYZED, StatusCondition.ASLEEP,
            StatusCondition.FROZEN, StatusCondition.CONFUSED,
            StatusCondition.FLINCHED, StatusCondition.LEECH_SEEDED
        ]

        for status in expected_statuses:
            assert status is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])