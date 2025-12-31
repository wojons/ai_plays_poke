"""
Tests for Tri-Tier Memory Architecture

Tests memory tiers, consolidation, database integration, and performance
"""

import pytest
import sys
import tempfile
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import time

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.memory import (
    ObserverMemory,
    StrategistMemory,
    TacticianMemory,
    MemoryConsolidator,
    ConsolidationConfig,
    ConsolidationResult,
    TickState,
    ActionRecord,
    SensoryInput,
    SessionObjective,
    BattleRecord,
    LocationVisited,
    ResourceSnapshot,
    LearnedPattern,
    SuccessfulStrategy,
    MistakeRecord,
    PlayerPreference,
    MemoryDatabaseMixin,
    MemoryGOAPIntegration,
    MemoryAIIntegration,
    create_observer_memory,
    create_strategist_memory,
    create_tactician_memory,
    create_memory_system,
    create_consolidator,
)


class TestTickState:
    """Tests for TickState dataclass"""
    
    def test_default_values(self):
        """Test default tick state values"""
        state = TickState()
        assert state.tick == 0
        assert state.timestamp == 0.0
        assert state.location == ""
        assert state.is_battle is False
        assert state.party_hp_percent == 100.0
        assert state.money == 0
        assert state.badges == []
        assert state.screen_type == "overworld"
        assert state.active_goal is None
    
    def test_custom_values(self):
        """Test tick state with custom values"""
        state = TickState(
            tick=500,
            timestamp=time.time(),
            location="Pallet Town",
            is_battle=True,
            party_hp_percent=85.5,
            money=3000,
            badges=["Boulder Badge"],
            screen_type="battle",
            active_goal="Defeat Brock"
        )
        assert state.tick == 500
        assert state.location == "Pallet Town"
        assert state.is_battle is True
        assert state.party_hp_percent == 85.5
        assert "Boulder Badge" in state.badges


class TestActionRecord:
    """Tests for ActionRecord dataclass"""
    
    def test_action_record_creation(self):
        """Test action record creation"""
        action = ActionRecord(
            tick=100,
            action_type="press",
            action_value="A",
            reasoning="Interact with NPC",
            confidence=0.85,
            success=True,
            outcome_summary="Dialog opened",
            duration_ms=50.0
        )
        assert action.tick == 100
        assert action.action_type == "press"
        assert action.action_value == "A"
        assert action.success is True
        assert action.confidence == 0.85


class TestSensoryInput:
    """Tests for SensoryInput dataclass"""
    
    def test_sensory_input_defaults(self):
        """Test sensory input default values"""
        sensory = SensoryInput()
        assert sensory.vision_labels == []
        assert sensory.ocr_text == ""
        assert sensory.ocr_confidence == 0.0
        assert sensory.screen_type == "unknown"
        assert sensory.enemy_pokemon is None
    
    def test_sensory_input_battle(self):
        """Test sensory input for battle"""
        sensory = SensoryInput(
            vision_labels=["pokemon", "health_bar", "menu"],
            ocr_text="Pikachu Lv.5",
            ocr_confidence=0.95,
            screen_type="battle",
            enemy_pokemon="Rattata",
            player_hp_percent=100.0,
            enemy_hp_percent=80.0,
            available_actions=["Tackle", "Thunder Shock", "Growl", "Run"]
        )
        assert sensory.enemy_pokemon == "Rattata"
        assert sensory.enemy_hp_percent == 80.0
        assert len(sensory.available_actions) == 4


class TestObserverMemory:
    """Tests for ObserverMemory (ephemeral, tick-level)"""
    
    def test_create_observer_memory(self):
        """Test factory function creates empty observer memory"""
        observer = create_observer_memory()
        assert observer is not None
        assert isinstance(observer, ObserverMemory)
        assert len(observer.recent_actions) == 0
        assert observer.decision_context == {}
        assert observer.current_state.tick == 0
    
    def test_add_single_action(self):
        """Test adding single action to observer memory"""
        observer = create_observer_memory()
        action = ActionRecord(
            tick=100,
            action_type="press",
            action_value="A",
            reasoning="Interact with NPC",
            confidence=0.85,
            success=True,
            outcome_summary="Dialog opened",
            duration_ms=50.0
        )
        observer.add_action(action)
        assert len(observer.recent_actions) == 1
        assert observer.recent_actions[0].action_type == "press"
    
    def test_add_multiple_actions_fifo(self):
        """Test FIFO buffer - max 10 actions"""
        observer = create_observer_memory()
        for i in range(15):
            action = ActionRecord(
                tick=i,
                action_type="press",
                action_value=str(i),
                reasoning=f"Action {i}",
                confidence=0.9,
                success=True,
                outcome_summary="Success",
                duration_ms=50.0
            )
            observer.add_action(action)
        assert len(observer.recent_actions) == 10
        assert observer.recent_actions[0].tick == 5
    
    def test_get_recent_outcomes(self):
        """Test getting recent outcomes"""
        observer = create_observer_memory()
        outcomes = observer.get_recent_outcomes()
        assert outcomes == []
        
        action = ActionRecord(
            tick=100, action_type="press", action_value="A",
            reasoning="Test", confidence=0.8, success=True,
            outcome_summary="OK", duration_ms=50.0
        )
        observer.add_action(action)
        
        outcomes = observer.get_recent_outcomes()
        assert len(outcomes) == 1
        assert outcomes[0]["success"] is True
        assert outcomes[0]["action_type"] == "press"
    
    def test_clear_observer(self):
        """Test clearing observer memory"""
        observer = create_observer_memory()
        observer.decision_context["test"] = "value"
        observer.current_state.location = "Test Location"
        observer.current_state.money = 5000
        
        action = ActionRecord(
            tick=100, action_type="press", action_value="A",
            reasoning="Test", confidence=0.8, success=True,
            outcome_summary="OK", duration_ms=50.0
        )
        observer.add_action(action)
        
        observer.clear()
        
        assert observer.decision_context == {}
        assert observer.current_state.location == ""
        assert observer.current_state.money == 0
        assert len(observer.recent_actions) == 0
    
    def test_update_state(self):
        """Test updating state"""
        observer = create_observer_memory()
        observer.update_state(
            location="Viridian City",
            is_battle=True,
            party_hp_percent=75.0
        )
        assert observer.current_state.location == "Viridian City"
        assert observer.current_state.is_battle is True
        assert observer.current_state.party_hp_percent == 75.0
    
    def test_success_rate(self):
        """Test success rate calculation"""
        observer = create_observer_memory()
        assert observer.get_success_rate() == 0.0
        
        for i in range(5):
            action = ActionRecord(
                tick=i, action_type="press", action_value="A",
                reasoning="Test", confidence=0.8,
                success=(i % 2 == 0),
                outcome_summary="OK", duration_ms=50.0
            )
            observer.add_action(action)
        
        assert observer.get_success_rate() == pytest.approx(0.6, rel=0.01)
    
    def test_avg_confidence(self):
        """Test average confidence calculation"""
        observer = create_observer_memory()
        assert observer.get_avg_confidence() == 0.0
        
        for i, conf in enumerate([0.5, 0.7, 0.9, 1.0]):
            action = ActionRecord(
                tick=i, action_type="press", action_value="A",
                reasoning="Test", confidence=conf, success=True,
                outcome_summary="OK", duration_ms=50.0
            )
            observer.add_action(action)
        
        assert observer.get_avg_confidence() == pytest.approx(0.775, rel=0.01)
    
    def test_serialization(self):
        """Test observer memory serialization"""
        observer = create_observer_memory()
        observer.current_state.tick = 100
        observer.current_state.location = "Viridian City"
        observer.current_state.screen_type = "battle"
        
        data = observer.to_dict()
        
        assert data["current_state"]["tick"] == 100
        assert data["current_state"]["location"] == "Viridian City"
        assert data["current_state"]["screen_type"] == "battle"
        assert data["recent_actions_count"] == 0
        assert data["recent_outcomes"] == []


class TestStrategistMemory:
    """Tests for StrategistMemory (session-level)"""
    
    def test_create_strategist_memory(self):
        """Test factory function creates strategist memory"""
        strategist = create_strategist_memory("session_001", 0)
        assert strategist is not None
        assert strategist.session_id == "session_001"
        assert strategist.session_start_tick == 0
        assert len(strategist.objectives) == 0
        assert strategist.total_battles == 0
        assert strategist.victories == 0
        assert strategist.defeats == 0
    
    def test_record_battle_victory(self):
        """Test recording battle victory"""
        strategist = create_strategist_memory("session_001", 0)
        battle = BattleRecord(
            battle_id="battle_001",
            start_tick=100,
            end_tick=105,
            enemy_pokemon="Pidgey",
            enemy_level=5,
            player_pokemon="Pikachu",
            player_level=5,
            outcome="victory",
            turns_taken=3,
            player_hp_remaining=25.0,
            moves_used=["Thunder Shock", "Quick Attack"],
            items_used=[],
            key_decisions=["Used super-effective move"]
        )
        strategist.record_battle(battle)
        
        assert strategist.total_battles == 1
        assert strategist.victories == 1
        assert strategist.defeats == 0
        assert len(strategist.battle_history) == 1
    
    def test_record_battle_defeat(self):
        """Test recording battle defeat"""
        strategist = create_strategist_memory("session_001", 0)
        battle = BattleRecord(
            battle_id="battle_001",
            start_tick=100,
            end_tick=105,
            enemy_pokemon="Geodude",
            enemy_level=7,
            player_pokemon="Pikachu",
            player_level=5,
            outcome="defeat",
            turns_taken=5,
            player_hp_remaining=0.0,
            moves_used=["Thunder Shock"],
            items_used=[],
            key_decisions=[]
        )
        strategist.record_battle(battle)
        
        assert strategist.total_battles == 1
        assert strategist.victories == 0
        assert strategist.defeats == 1
    
    def test_win_rate_empty(self):
        """Test win rate with no battles"""
        strategist = create_strategist_memory("session_001", 0)
        assert strategist.get_win_rate() == 0.0
    
    def test_win_rate_mixed(self):
        """Test win rate with mixed outcomes"""
        strategist = create_strategist_memory("session_001", 0)
        
        for i in range(4):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory" if i < 3 else "defeat",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=[],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        assert strategist.get_win_rate() == pytest.approx(0.75, rel=0.01)
    
    def test_add_objective(self):
        """Test adding session objective"""
        strategist = create_strategist_memory("session_001", 0)
        objective = SessionObjective(
            objective_id="obj_001",
            name="Defeat Brock",
            description="Defeat Pewter City Gym Leader Brock",
            objective_type="defeat_gym",
            priority=80,
            status="active",
            progress_percent=0.0,
            created_tick=0,
            completed_tick=None,
            prerequisites=[],
            related_location="Pewter City Gym"
        )
        strategist.add_objective(objective)
        
        assert len(strategist.objectives) == 1
        assert strategist.active_objective is not None
        assert strategist.active_objective.name == "Defeat Brock"
    
    def test_update_objective_progress(self):
        """Test updating objective progress"""
        strategist = create_strategist_memory("session_001", 0)
        objective = SessionObjective(
            objective_id="obj_001",
            name="Defeat Brock",
            description="Defeat gym",
            objective_type="defeat_gym",
            priority=80,
            status="active",
            progress_percent=0.0,
            created_tick=0,
            completed_tick=None,
            prerequisites=[],
            related_location="Pewter City"
        )
        strategist.add_objective(objective)
        strategist.update_objective_progress("obj_001", 50.0)
        
        assert strategist.objectives[0].progress_percent == 50.0
    
    def test_complete_objective(self):
        """Test completing objective"""
        strategist = create_strategist_memory("session_001", 0)
        objective = SessionObjective(
            objective_id="obj_001",
            name="Test",
            description="Test",
            objective_type="exploration",
            priority=50,
            status="active",
            progress_percent=75.0,
            created_tick=0,
            completed_tick=None,
            prerequisites=[],
            related_location=None
        )
        strategist.add_objective(objective)
        strategist.complete_objective("obj_001")
        
        assert strategist.objectives[0].status == "completed"
        assert strategist.objectives[0].progress_percent == 100.0
        assert strategist.active_objective is None
    
    def test_add_location_new(self):
        """Test adding new location"""
        strategist = create_strategist_memory("session_001", 0)
        location = LocationVisited(
            location_name="Pewter City",
            location_type="city",
            first_visit_tick=100,
            last_visit_tick=100,
            visit_count=1,
            explored_areas=["Pokemon Center"],
            unexplored_areas=["Museum"],
            points_of_interest=["Fossil restoration"],
            npcs_interacted=["Nurse Joy"]
        )
        strategist.add_location(location)
        
        assert "Pewter City" in strategist.locations_visited
        assert strategist.locations_visited["Pewter City"].visit_count == 1
    
    def test_add_location_existing(self):
        """Test adding to existing location"""
        strategist = create_strategist_memory("session_001", 0)
        
        location = LocationVisited(
            location_name="Route 1",
            location_type="route",
            first_visit_tick=10,
            last_visit_tick=10,
            visit_count=1,
            explored_areas=["Area A"],
            unexplored_areas=[],
            points_of_interest=[],
            npcs_interacted=[]
        )
        strategist.add_location(location)
        
        new_location = LocationVisited(
            location_name="Route 1",
            location_type="route",
            first_visit_tick=10,
            last_visit_tick=50,
            visit_count=2,
            explored_areas=["Area B"],
            unexplored_areas=[],
            points_of_interest=["Wild Pokemon"],
            npcs_interacted=[" Lass"]
        )
        strategist.add_location(new_location)
        
        assert strategist.locations_visited["Route 1"].visit_count == 2
        assert "Area B" in strategist.locations_visited["Route 1"].explored_areas
        assert "Wild Pokemon" in strategist.locations_visited["Route 1"].points_of_interest
    
    def test_update_money(self):
        """Test updating money"""
        strategist = create_strategist_memory("session_001", 0)
        strategist.update_money(3000)
        assert strategist.current_money == 3000
        strategist.update_money(-500)
        assert strategist.current_money == 2500
        strategist.update_money(-3000)
        assert strategist.current_money == 0
    
    def test_update_items(self):
        """Test updating items"""
        strategist = create_strategist_memory("session_001", 0)
        strategist.update_items("Potion", 5)
        assert strategist.current_items["Potion"] == 5
        strategist.update_items("Potion", 3)
        assert strategist.current_items["Potion"] == 8
        strategist.update_items("Potion", -10)
        assert "Potion" not in strategist.current_items
    
    def test_get_battles_by_outcome(self):
        """Test filtering battles by outcome"""
        strategist = create_strategist_memory("session_001", 0)
        
        for i in range(5):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory" if i % 2 == 0 else "defeat",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=[],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        victories = strategist.get_battles_by_outcome("victory")
        defeats = strategist.get_battles_by_outcome("defeat")
        
        assert len(victories) == 3
        assert len(defeats) == 2
    
    def test_get_recent_battles(self):
        """Test getting recent battles"""
        strategist = create_strategist_memory("session_001", 0)
        
        for i in range(10):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=[],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        recent = strategist.get_recent_battles(3)
        assert len(recent) == 3
        assert recent[0].battle_id == "b7"
    
    def test_get_objectives_progress(self):
        """Test getting objectives progress by type"""
        strategist = create_strategist_memory("session_001", 0)
        
        for obj_type in ["exploration", "defeat_gym", "exploration"]:
            objective = SessionObjective(
                objective_id=f"obj_{obj_type}",
                name="Test",
                description="Test",
                objective_type=obj_type,
                priority=50,
                status="active",
                progress_percent=50.0,
                created_tick=0,
                completed_tick=None,
                prerequisites=[],
                related_location=None
            )
            strategist.add_objective(objective)
        
        progress = strategist.get_objectives_progress()
        
        assert "exploration" in progress
        assert "defeat_gym" in progress
        assert progress["exploration"] == 50.0
        assert progress["defeat_gym"] == 50.0
    
    def test_clear_session(self):
        """Test clearing session data"""
        strategist = create_strategist_memory("session_001", 0)
        
        battle = BattleRecord(
            battle_id="b1",
            start_tick=0,
            end_tick=5,
            enemy_pokemon="Rattata",
            enemy_level=3,
            player_pokemon="Pikachu",
            player_level=5,
            outcome="victory",
            turns_taken=2,
            player_hp_remaining=30.0,
            moves_used=[],
            items_used=[],
            key_decisions=[]
        )
        strategist.record_battle(battle)
        strategist.current_money = 1000
        
        strategist.clear_session()
        
        assert strategist.total_battles == 0
        assert strategist.victories == 0
        assert strategist.current_money == 0
        assert len(strategist.battle_history) == 0
    
    def test_serialization(self):
        """Test strategist memory serialization"""
        strategist = create_strategist_memory("session_001", 0)
        data = strategist.to_dict()
        
        assert data["session_id"] == "session_001"
        assert data["total_battles"] == 0
        assert data["win_rate"] == 0.0
        assert data["locations_count"] == 0


class TestTacticianMemory:
    """Tests for TacticianMemory (persistent, long-term)"""
    
    def test_create_tactician_memory(self):
        """Test factory function creates tactician memory"""
        tactician = create_tactician_memory()
        assert tactician is not None
        assert len(tactician.patterns) == 0
        assert len(tactician.strategies) == 0
        assert tactician.total_sessions == 0
        assert tactician.total_battles == 0
        assert tactician.overall_win_rate == 0.0
    
    def test_add_pattern_new(self):
        """Test adding new pattern"""
        tactician = create_tactician_memory()
        pattern = LearnedPattern(
            pattern_id="pattern_001",
            pattern_type="enemy_behavior",
            description="Geodude uses Rock Throw on turn 2",
            trigger_conditions={"enemy_species": "Geodude", "turn": 2},
            learned_from_session="session_001",
            learned_from_tick=500,
            success_count=5,
            failure_count=1,
            confidence=0.83,
            last_validated=time.time(),
            relevance_score=0.7
        )
        tactician.add_pattern(pattern)
        
        assert "pattern_001" in tactician.patterns
        assert tactician.patterns["pattern_001"].confidence == 0.83
    
    def test_add_pattern_update_existing(self):
        """Test updating existing pattern"""
        tactician = create_tactician_memory()
        
        pattern1 = LearnedPattern(
            pattern_id="pattern_001",
            pattern_type="enemy_behavior",
            description="Original",
            trigger_conditions={"enemy": "Geodude"},
            learned_from_session="session_001",
            learned_from_tick=500,
            success_count=3,
            failure_count=1,
            confidence=0.75,
            last_validated=time.time(),
            relevance_score=0.5
        )
        tactician.add_pattern(pattern1)
        
        pattern2 = LearnedPattern(
            pattern_id="pattern_001",
            pattern_type="enemy_behavior",
            description="Updated",
            trigger_conditions={"enemy": "Geodude"},
            learned_from_session="session_001",
            learned_from_tick=500,
            success_count=5,
            failure_count=1,
            confidence=0.83,
            last_validated=time.time(),
            relevance_score=0.8
        )
        tactician.add_pattern(pattern2)
        
        assert tactician.patterns["pattern_001"].confidence == 0.83
        assert tactician.patterns["pattern_001"].relevance_score == 0.8
    
    def test_record_strategy_success(self):
        """Test recording strategy success"""
        tactician = create_tactician_memory()
        
        strategy = SuccessfulStrategy(
            strategy_id="strat_001",
            context={"type": "wild"},
            enemy_type="Rattata",
            player_pokemon="Pikachu",
            strategy_description="Open with Quick Attack",
            moves_sequence=["Quick Attack"],
            success_rate=0.0,
            total_uses=0,
            first_used=time.time()
        )
        tactician.strategies["strat_001"] = strategy
        
        tactician.record_strategy_success("strat_001", True)
        assert tactician.strategies["strat_001"].total_uses == 1
        assert tactician.strategies["strat_001"].successful_uses == 1
        assert tactician.strategies["strat_001"].success_rate == 1.0
        
        tactician.record_strategy_success("strat_001", False)
        assert tactician.strategies["strat_001"].total_uses == 2
        assert tactician.strategies["strat_001"].successful_uses == 1
        assert tactician.strategies["strat_001"].success_rate == 0.5
    
    def test_get_or_create_strategy(self):
        """Test getting or creating strategy"""
        tactician = create_tactician_memory()
        
        strategy1 = tactician.get_or_create_strategy(
            context={"type": "wild"},
            enemy_type="Rattata",
            player_pokemon="Pikachu",
            moves_sequence=["Quick Attack"]
        )
        
        assert len(tactician.strategies) == 1
        assert strategy1.strategy_id is not None
        
        strategy2 = tactician.get_or_create_strategy(
            context={"type": "wild"},
            enemy_type="Rattata",
            player_pokemon="Pikachu",
            moves_sequence=["Quick Attack"]
        )
        
        assert strategy1.strategy_id == strategy2.strategy_id
    
    def test_add_mistake_new(self):
        """Test adding new mistake"""
        tactician = create_tactician_memory()
        mistake = MistakeRecord(
            mistake_id="mistake_001",
            description="Used Water move against Grass type",
            situation={"enemy_type": "Grass", "move_type": "Water"},
            outcome="Ineffective damage",
            severity="major",
            prevention_tip="Check type chart before attacking",
            first_occurred=time.time(),
            last_occurred=time.time(),
            occurrence_count=1
        )
        tactician.add_mistake(mistake)
        
        assert "mistake_001" in tactician.mistakes
        assert tactician.mistakes["mistake_001"].severity == "major"
    
    def test_add_mistake_merge(self):
        """Test merging similar mistakes"""
        tactician = create_tactician_memory()
        
        mistake1 = MistakeRecord(
            mistake_id="mistake_001",
            description="Used Water move",
            situation={"enemy_type": "Grass", "move_type": "Water"},
            outcome="Bad",
            severity="major",
            prevention_tip="Check types",
            first_occurred=time.time(),
            last_occurred=time.time(),
            occurrence_count=1
        )
        tactician.add_mistake(mistake1)
        
        mistake2 = MistakeRecord(
            mistake_id="mistake_002",
            description="Used Water move",
            situation={"enemy_type": "Grass", "move_type": "Water"},
            outcome="Bad",
            severity="major",
            prevention_tip="Check types",
            first_occurred=time.time(),
            last_occurred=time.time(),
            occurrence_count=1
        )
        tactician.add_mistake(mistake2)
        
        assert len(tactician.mistakes) == 1
        assert tactician.mistakes["mistake_001"].occurrence_count == 2
    
    def test_get_preference_existing(self):
        """Test getting existing preference"""
        tactician = create_tactician_memory()
        preference = PlayerPreference(
            preference_id="pref_001",
            category="move_order",
            description="Prefer strong moves",
            preference_value={"strategy": "strongest"},
            learned_from_session="session_001",
            confidence=0.75,
            created_at=time.time(),
            updated_at=time.time()
        )
        tactician.set_preference(preference)
        
        retrieved = tactician.get_preference("move_order")
        assert retrieved is not None
        assert retrieved.category == "move_order"
    
    def test_get_preference_nonexistent(self):
        """Test getting nonexistent preference"""
        tactician = create_tactician_memory()
        pref = tactician.get_preference("nonexistent")
        assert pref is None
    
    def test_set_preference_update(self):
        """Test updating existing preference"""
        tactician = create_tactician_memory()
        
        pref1 = PlayerPreference(
            preference_id="pref_001",
            category="move_order",
            description="Original",
            preference_value={"strategy": "original"},
            learned_from_session="session_001",
            confidence=0.5,
            created_at=time.time(),
            updated_at=time.time()
        )
        tactician.set_preference(pref1)
        
        pref2 = PlayerPreference(
            preference_id="pref_001",
            category="move_order",
            description="Updated",
            preference_value={"strategy": "updated"},
            learned_from_session="session_001",
            confidence=0.8,
            created_at=time.time(),
            updated_at=time.time()
        )
        tactician.set_preference(pref2)
        
        assert tactician.preferences["move_order"].preference_value["strategy"] == "updated"
        assert tactician.preferences["move_order"].confidence == 0.8
    
    def test_get_relevant_patterns(self):
        """Test getting relevant patterns"""
        tactician = create_tactician_memory()
        
        patterns = [
            LearnedPattern(
                pattern_id="p1",
                pattern_type="battle",
                description="Pikachu vs Electric",
                trigger_conditions={"player": "Pikachu", "enemy_type": "Electric"},
                learned_from_session="s1",
                learned_from_tick=100,
                confidence=0.8,
                relevance_score=0.7
            ),
            LearnedPattern(
                pattern_id="p2",
                pattern_type="battle",
                description="Pikachu vs Fire",
                trigger_conditions={"player": "Pikachu", "enemy_type": "Fire"},
                learned_from_session="s1",
                learned_from_tick=100,
                confidence=0.9,
                relevance_score=0.8
            )
        ]
        for p in patterns:
            tactician.add_pattern(p)
        
        relevant = tactician.get_relevant_patterns({"player": "Pikachu", "enemy_type": "Fire"})
        assert len(relevant) == 2
        assert relevant[0].pattern_id == "p2"
    
    def test_get_successful_strategies(self):
        """Test getting successful strategies"""
        tactician = create_tactician_memory()
        
        strat1 = SuccessfulStrategy(
            strategy_id="s1",
            context={"type": "wild"},
            enemy_type="Rattata",
            player_pokemon="Pikachu",
            strategy_description="Strategy 1",
            moves_sequence=["Quick Attack"],
            success_rate=0.9,
            total_uses=10,
            first_used=time.time()
        )
        tactician.strategies["s1"] = strat1
        
        strat2 = SuccessfulStrategy(
            strategy_id="s2",
            context={"type": "wild"},
            enemy_type="Pidgey",
            player_pokemon="Pikachu",
            strategy_description="Strategy 2",
            moves_sequence=["Thunder Shock"],
            success_rate=0.7,
            total_uses=10,
            first_used=time.time()
        )
        tactician.strategies["s2"] = strat2
        
        strategies = tactician.get_successful_strategies("Rattata", "Pikachu")
        assert len(strategies) == 1
        assert strategies[0].strategy_id == "s1"
    
    def test_get_mistakes_for_context(self):
        """Test getting mistakes for context"""
        tactician = create_tactician_memory()
        
        mistakes = [
            MistakeRecord(
                mistake_id="m1",
                description="Mistake 1",
                situation={"enemy_type": "Fire", "move_type": "Water"},
                outcome="Bad",
                severity="critical",
                prevention_tip="Check types",
                first_occurred=time.time(),
                last_occurred=time.time()
            ),
            MistakeRecord(
                mistake_id="m2",
                description="Mistake 2",
                situation={"enemy_type": "Grass", "move_type": "Water"},
                outcome="Bad",
                severity="minor",
                prevention_tip="Check types",
                first_occurred=time.time(),
                last_occurred=time.time()
            )
        ]
        for m in mistakes:
            tactician.add_mistake(m)
        
        relevant = tactician.get_mistakes_for_context({"enemy_type": "Fire"})
        assert len(relevant) == 1
        assert relevant[0].mistake_id == "m1"
    
    def test_get_patterns_by_type(self):
        """Test getting patterns by type"""
        tactician = create_tactician_memory()
        
        patterns = [
            LearnedPattern(pattern_id="p1", pattern_type="battle", description="1",
                          trigger_conditions={}, learned_from_session="s1", learned_from_tick=100),
            LearnedPattern(pattern_id="p2", pattern_type="exploration", description="2",
                          trigger_conditions={}, learned_from_session="s1", learned_from_tick=100),
            LearnedPattern(pattern_id="p3", pattern_type="battle", description="3",
                          trigger_conditions={}, learned_from_session="s1", learned_from_tick=100),
        ]
        for p in patterns:
            tactician.add_pattern(p)
        
        battle_patterns = tactician.get_patterns_by_type("battle")
        assert len(battle_patterns) == 2
    
    def test_get_high_confidence_patterns(self):
        """Test getting high confidence patterns"""
        tactician = create_tactician_memory()
        
        patterns = [
            LearnedPattern(pattern_id="p1", pattern_type="battle", description="1",
                          trigger_conditions={}, learned_from_session="s1", learned_from_tick=100,
                          confidence=0.9),
            LearnedPattern(pattern_id="p2", pattern_type="battle", description="2",
                          trigger_conditions={}, learned_from_session="s1", learned_from_tick=100,
                          confidence=0.5),
            LearnedPattern(pattern_id="p3", pattern_type="battle", description="3",
                          trigger_conditions={}, learned_from_session="s1", learned_from_tick=100,
                          confidence=0.8),
        ]
        for p in patterns:
            tactician.add_pattern(p)
        
        high_conf = tactician.get_high_confidence_patterns(0.7)
        assert len(high_conf) == 2
    
    def test_update_stats(self):
        """Test updating overall stats"""
        tactician = create_tactician_memory()
        
        tactician.update_stats(True)
        assert tactician.total_battles == 1
        assert tactician.overall_win_rate == 1.0
        
        tactician.update_stats(True)
        assert tactician.total_battles == 2
        assert tactician.overall_win_rate == 1.0
        
        tactician.update_stats(False)
        assert tactician.total_battles == 3
        assert tactician.overall_win_rate == pytest.approx(0.667, rel=0.01)
    
    def test_increment_sessions(self):
        """Test incrementing session counter"""
        tactician = create_tactician_memory()
        assert tactician.total_sessions == 0
        tactician.increment_sessions()
        assert tactician.total_sessions == 1
        tactician.increment_sessions()
        assert tactician.total_sessions == 2
    
    def test_prune_low_value(self):
        """Test pruning low value memories"""
        tactician = create_tactician_memory()
        
        for i in range(60):
            pattern = LearnedPattern(
                pattern_id=f"p{i}",
                pattern_type="battle",
                description=f"Pattern {i}",
                trigger_conditions={},
                learned_from_session="s1",
                learned_from_tick=100,
                confidence=0.5,
                relevance_score=0.1 if i < 50 else 0.9
            )
            tactician.add_pattern(pattern)
        
        config = ConsolidationConfig(max_patterns_per_type=50)
        pruned = tactician.prune_low_value(config)
        
        assert pruned == 10
        assert len(tactician.patterns) == 50
    
    def test_serialization(self):
        """Test tactician memory serialization"""
        tactician = create_tactician_memory()
        tactician.total_sessions = 5
        tactician.total_battles = 50
        tactician.overall_win_rate = 0.72
        
        data = tactician.to_dict()
        
        assert data["total_sessions"] == 5
        assert data["total_battles"] == 50
        assert data["overall_win_rate"] == 0.72
        assert data["patterns_count"] == 0


class TestTacticianMemoryDatabase:
    """Tests for TacticianMemory database operations"""
    
    def test_save_and_load_patterns(self):
        """Test saving and loading patterns from database"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_memory.db")
            
            tactician1 = create_tactician_memory()
            pattern = LearnedPattern(
                pattern_id="test_pattern",
                pattern_type="battle",
                description="Test pattern",
                trigger_conditions={"key": "value"},
                learned_from_session="s1",
                learned_from_tick=100,
                success_count=5,
                failure_count=1,
                confidence=0.83,
                last_validated=time.time(),
                relevance_score=0.7
            )
            tactician1.add_pattern(pattern)
            tactician1.total_sessions = 3
            
            assert tactician1.save_to_database(db_path) is True
            
            tactician2 = create_tactician_memory()
            assert tactician2.load_from_database(db_path) is True
            assert "test_pattern" in tactician2.patterns
            assert tactician2.patterns["test_pattern"].confidence == 0.83
            assert tactician2.total_sessions == 3
    
    def test_save_and_load_strategies(self):
        """Test saving and loading strategies from database"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_memory.db")
            
            tactician1 = create_tactician_memory()
            strategy = SuccessfulStrategy(
                strategy_id="strat_001",
                context={"type": "wild"},
                enemy_type="Rattata",
                player_pokemon="Pikachu",
                strategy_description="Test strategy",
                moves_sequence=["Quick Attack"],
                success_rate=0.9,
                total_uses=10,
                first_used=time.time()
            )
            tactician1.strategies["strat_001"] = strategy
            
            assert tactician1.save_to_database(db_path) is True
            
            tactician2 = create_tactician_memory()
            assert tactician2.load_from_database(db_path) is True
            assert "strat_001" in tactician2.strategies
            assert tactician2.strategies["strat_001"].success_rate == 0.9
    
    def test_save_and_load_mistakes(self):
        """Test saving and loading mistakes from database"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_memory.db")
            
            tactician1 = create_tactician_memory()
            mistake = MistakeRecord(
                mistake_id="mistake_001",
                description="Test mistake",
                situation={"key": "value"},
                outcome="Bad",
                severity="major",
                prevention_tip="Be careful",
                first_occurred=time.time(),
                last_occurred=time.time(),
                occurrence_count=3
            )
            tactician1.add_mistake(mistake)
            
            assert tactician1.save_to_database(db_path) is True
            
            tactician2 = create_tactician_memory()
            assert tactician2.load_from_database(db_path) is True
            assert "mistake_001" in tactician2.mistakes
            assert tactician2.mistakes["mistake_001"].occurrence_count == 3
    
    def test_save_and_load_preferences(self):
        """Test saving and loading preferences from database"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_memory.db")
            
            tactician1 = create_tactician_memory()
            preference = PlayerPreference(
                preference_id="pref_001",
                category="move_order",
                description="Test preference",
                preference_value={"strategy": "strongest"},
                learned_from_session="s1",
                confidence=0.8,
                created_at=time.time(),
                updated_at=time.time()
            )
            tactician1.set_preference(preference)
            
            assert tactician1.save_to_database(db_path) is True
            
            tactician2 = create_tactician_memory()
            assert tactician2.load_from_database(db_path) is True
            pref = tactician2.get_preference("move_order")
            assert pref is not None
            assert pref.preference_value["strategy"] == "strongest"


class TestMemoryConsolidator:
    """Tests for MemoryConsolidator"""
    
    def test_create_consolidator(self):
        """Test factory function creates consolidator"""
        observer = create_observer_memory()
        strategist = create_strategist_memory("session_001", 0)
        tactician = create_tactician_memory()
        consolidator = create_consolidator(
            observer=observer,
            strategist=strategist,
            tactician=tactician
        )
        assert consolidator is not None
        assert consolidator.config.tick_interval == 1000
    
    def test_default_config(self):
        """Test default consolidation configuration"""
        config = ConsolidationConfig()
        assert config.tick_interval == 1000
        assert config.session_end_consolidate is True
        assert config.pattern_threshold == 0.7
        assert config.min_occurrences_for_pattern == 3
        assert config.max_patterns_per_type == 50
        assert config.max_strategies == 100
        assert config.max_mistakes == 200
    
    def test_set_references(self):
        """Test setting memory references"""
        consolidator = create_consolidator()
        observer = create_observer_memory()
        strategist = create_strategist_memory("session_001", 0)
        tactician = create_tactician_memory()
        
        consolidator.set_observer(observer)
        consolidator.set_strategist(strategist)
        consolidator.set_tactician(tactician)
        
        assert consolidator.observer is observer
        assert consolidator.strategist is strategist
        assert consolidator.tactician is tactician
    
    def test_tick_no_consolidation(self):
        """Test tick without consolidation"""
        consolidator = create_consolidator()
        result = consolidator.tick(100)
        assert result is None
    
    def test_tick_with_consolidation(self):
        """Test tick with consolidation"""
        observer = create_observer_memory()
        observer.current_state.tick = 1500
        strategist = create_strategist_memory("session_001", 0)
        tactician = create_tactician_memory()
        consolidator = create_consolidator(
            observer=observer,
            strategist=strategist,
            tactician=tactician
        )
        
        result = consolidator.tick(1500)
        
        assert result is not None
        assert result.success is True
        assert result.consolidation_time_ms >= 0
    
    def test_consolidate_observer_to_strategist(self):
        """Test consolidating observer to strategist"""
        observer = create_observer_memory()
        for i in range(5):
            action = ActionRecord(
                tick=i, action_type="press", action_value="A",
                reasoning="Test", confidence=0.8,
                success=(i % 2 == 0),
                outcome_summary="OK", duration_ms=50.0
            )
            observer.add_action(action)
        
        strategist = create_strategist_memory("session_001", 0)
        consolidator = create_consolidator(observer=observer, strategist=strategist)
        
        result = consolidator.consolidate_observer_to_strategist()
        
        assert result.success is True
        assert result.patterns_extracted >= 0
        assert consolidator._pending_patterns is not None
    
    def test_consolidate_strategist_to_tactician(self):
        """Test consolidating strategist to tactician"""
        strategist = create_strategist_memory("session_001", 0)
        
        for i in range(3):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory" if i < 2 else "defeat",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=["Quick Attack", "Thunder Shock"],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        tactician = create_tactician_memory()
        consolidator = create_consolidator(strategist=strategist, tactician=tactician)
        
        result = consolidator.consolidate_strategist_to_tactician()
        
        assert result.success is True
        assert result.details["battles_analyzed"] == 3
    
    def test_apply_forgetting(self):
        """Test applying forgetting logic"""
        tactician = create_tactician_memory()
        
        for i in range(60):
            pattern = LearnedPattern(
                pattern_id=f"p{i}",
                pattern_type="battle",
                description=f"Pattern {i}",
                trigger_conditions={},
                learned_from_session="s1",
                learned_from_tick=100,
                confidence=0.5,
                relevance_score=0.1
            )
            tactician.add_pattern(pattern)
        
        config = ConsolidationConfig(max_patterns_per_type=50)
        consolidator = create_consolidator(tactician=tactician, config=config)
        
        result = consolidator.apply_forgetting()
        
        assert result.success is True
        assert result.memories_pruned >= 10
    
    def test_prioritize_memories(self):
        """Test prioritizing memories"""
        observer = create_observer_memory()
        strategist = create_strategist_memory("session_001", 0)
        objective = SessionObjective(
            objective_id="obj_001",
            name="Test",
            description="Test",
            objective_type="exploration",
            priority=50,
            status="active",
            progress_percent=0.0,
            created_tick=0,
            completed_tick=None,
            prerequisites=[],
            related_location=None
        )
        strategist.add_objective(objective)
        
        for i in range(3):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=[],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        tactician = create_tactician_memory()
        consolidator = create_consolidator(
            observer=observer,
            strategist=strategist,
            tactician=tactician
        )
        
        priorities = consolidator.prioritize_memories()
        
        assert "observer" in priorities
        assert "strategist" in priorities
        assert "tactician" in priorities
        assert "obj_001" in priorities["strategist"]
    
    def test_get_consolidation_status(self):
        """Test consolidation status"""
        consolidator = create_consolidator()
        status = consolidator.get_consolidation_status()
        
        assert "last_consolidation_tick" in status
        assert "consolidation_history_length" in status
        assert "config" in status
        assert status["config"]["tick_interval"] == 1000
    
    def test_get_avg_consolidation_time(self):
        """Test average consolidation time"""
        consolidator = create_consolidator()
        assert consolidator.get_avg_consolidation_time() == 0.0


class TestMemoryGOAPIntegration:
    """Tests for GOAP integration"""
    
    def test_get_context_for_planning(self):
        """Test getting context for planning"""
        observer = create_observer_memory()
        observer.current_state.location = "Route 1"
        observer.current_state.party_hp_percent = 80.0
        
        strategist = create_strategist_memory("session_001", 0)
        objective = SessionObjective(
            objective_id="obj_001",
            name="Test",
            description="Test",
            objective_type="exploration",
            priority=50,
            status="active",
            progress_percent=25.0,
            created_tick=0,
            completed_tick=None,
            prerequisites=[],
            related_location=None
        )
        strategist.add_objective(objective)
        
        for i in range(5):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=[],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        tactician = create_tactician_memory()
        tactician.total_sessions = 10
        
        context = MemoryGOAPIntegration.get_context_for_planning(
            observer, strategist, tactician
        )
        
        assert "observer" in context
        assert "strategist" in context
        assert "tactician" in context
        assert context["observer"]["current_location"] == "Route 1"
        assert context["strategist"]["active_objective"] == "Test"
        assert context["strategist"]["session_win_rate"] == 1.0
        assert context["tactician"]["total_sessions"] == 10
    
    def test_query_strategist_objectives(self):
        """Test querying strategist objectives"""
        strategist = create_strategist_memory("session_001", 0)
        
        for i, status in enumerate(["active", "pending", "completed", "active"]):
            objective = SessionObjective(
                objective_id=f"obj_{i}",
                name=f"Objective {i}",
                description="Test",
                objective_type="exploration",
                priority=50,
                status=status,
                progress_percent=50.0,
                created_tick=0,
                completed_tick=None,
                prerequisites=[],
                related_location=None
            )
            strategist.add_objective(objective)
        
        objectives = MemoryGOAPIntegration.query_strategist_objectives(strategist)

        assert len(objectives) == 2
        assert all(o.status == "active" for o in objectives)
    
    def test_query_tactician_strategies(self):
        """Test querying tactician strategies"""
        tactician = create_tactician_memory()
        
        for i in range(5):
            strategy = SuccessfulStrategy(
                strategy_id=f"s{i}",
                context={"type": "wild"},
                enemy_type="Rattata",
                player_pokemon="Pikachu",
                strategy_description=f"Strategy {i}",
                moves_sequence=["Quick Attack"],
                success_rate=0.7 + i * 0.05,
                total_uses=10,
                first_used=time.time()
            )
            tactician.strategies[f"s{i}"] = strategy
        
        strategies = MemoryGOAPIntegration.query_tactician_strategies(
            tactician,
            {"enemy_type": "Rattata", "player_pokemon": "Pikachu"}
        )
        
        assert len(strategies) == 5
        assert strategies[0].strategy_id == "s4"
    
    def test_record_planning_outcome(self):
        """Test recording planning outcome"""
        observer = create_observer_memory()
        action = ActionRecord(
            tick=100, action_type="press", action_value="A",
            reasoning="Test", confidence=0.8, success=True,
            outcome_summary="OK", duration_ms=50.0
        )
        observer.add_action(action)
        
        MemoryGOAPIntegration.record_planning_outcome(observer, False, "Failed")
        
        assert observer.recent_actions[0].success is False
        assert observer.recent_actions[0].outcome_summary == "Failed"


class TestMemoryAIIntegration:
    """Tests for AI integration"""
    
    def test_inject_memory_context(self):
        """Test injecting memory context"""
        observer = create_observer_memory()
        observer.current_state.location = "Pallet Town"
        
        strategist = create_strategist_memory("session_001", 0)
        for i in range(5):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=[],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        tactician = create_tactician_memory()
        
        context = MemoryAIIntegration.inject_memory_context(
            observer, strategist, tactician
        )
        
        assert "tactical" in context
        assert "strategic" in context
        assert "recent_actions" in context
        assert "action_success_rate" in context
        assert context["session_performance"]["win_rate"] == 1.0
    
    def test_get_tactical_context(self):
        """Test getting tactical context"""
        tactician = create_tactician_memory()
        
        strategy = SuccessfulStrategy(
            strategy_id="s1",
            context={"type": "wild"},
            enemy_type="Rattata",
            player_pokemon="Pikachu",
            strategy_description="Open with Quick Attack",
            moves_sequence=["Quick Attack"],
            success_rate=0.9,
            total_uses=10,
            first_used=time.time()
        )
        tactician.strategies["s1"] = strategy
        
        mistake = MistakeRecord(
            mistake_id="m1",
            description="Used Water move",
            situation={"enemy_type": "Grass", "move_type": "Water"},
            outcome="Bad",
            severity="major",
            prevention_tip="Check types",
            first_occurred=time.time(),
            last_occurred=time.time()
        )
        tactician.add_mistake(mistake)
        
        context = MemoryAIIntegration.get_tactical_context(
            tactician,
            {"enemy_pokemon": "Rattata"}
        )
        
        assert "Rattata" in context or "Previously effective" in context
    
    def test_get_strategic_context(self):
        """Test getting strategic context"""
        strategist = create_strategist_memory("session_001", 0)
        strategist.current_money = 5000
        
        objective = SessionObjective(
            objective_id="obj_001",
            name="Defeat Brock",
            description="Test",
            objective_type="defeat_gym",
            priority=80,
            status="active",
            progress_percent=60.0,
            created_tick=0,
            completed_tick=None,
            prerequisites=[],
            related_location="Pewter City"
        )
        strategist.add_objective(objective)
        
        for i in range(10):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=[],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        context = MemoryAIIntegration.get_strategic_context(strategist)
        
        assert "Brock" in context
        assert "60%" in context or "60.0%" in context
        assert "100%" in context or "1.0" in context
    
    def test_get_recent_actions_summary(self):
        """Test getting recent actions summary"""
        observer = create_observer_memory()
        
        for i, (success, action_type) in enumerate([(True, "press"), (True, "hold"), (False, "press")]):
            action = ActionRecord(
                tick=i, action_type=action_type, action_value="A",
                reasoning=f"Action {i}", confidence=0.8,
                success=success, outcome_summary="OK", duration_ms=50.0
            )
            observer.add_action(action)
        
        summary = MemoryAIIntegration.get_recent_actions_summary(observer)
        
        assert "Last 3 actions" in summary or "3" in summary
        assert "OK" in summary or "FAIL" in summary


class TestMemorySystem:
    """Tests for complete memory system"""
    
    def test_create_memory_system(self):
        """Test creating complete memory system"""
        observer, strategist, tactician, consolidator = create_memory_system(
            session_id="session_001",
            start_tick=0
        )
        
        assert observer is not None
        assert strategist is not None
        assert tactician is not None
        assert consolidator is not None
        assert strategist.session_id == "session_001"
        assert consolidator.observer is observer
        assert consolidator.strategist is strategist
        assert consolidator.tactician is tactician
    
    def test_full_memory_tier_integration(self):
        """Test full integration between memory tiers"""
        observer, strategist, tactician, consolidator = create_memory_system(
            session_id="session_001",
            start_tick=0
        )
        
        observer.current_state.location = "Route 1"
        observer.current_state.is_battle = True
        observer.current_state.party_hp_percent = 75.0
        
        battle = BattleRecord(
            battle_id="b1",
            start_tick=100,
            end_tick=105,
            enemy_pokemon="Caterpie",
            enemy_level=3,
            player_pokemon="Pikachu",
            player_level=5,
            outcome="victory",
            turns_taken=2,
            player_hp_remaining=35.0,
            moves_used=["Thunder Shock"],
            items_used=[],
            key_decisions=["Used super-effective move"]
        )
        strategist.record_battle(battle)
        
        pattern = LearnedPattern(
            pattern_id="p1",
            pattern_type="battle_opening",
            description="Open with Thunder Shock against bug types",
            trigger_conditions={"enemy_type": "Bug"},
            learned_from_session="session_001",
            learned_from_tick=100,
            success_count=10,
            failure_count=0,
            confidence=1.0,
            last_validated=time.time(),
            relevance_score=0.9
        )
        tactician.add_pattern(pattern)
        
        assert strategist.total_battles == 1
        assert len(tactician.patterns) == 1
        assert tactician.patterns["p1"].success_count == 10
        
        context = MemoryGOAPIntegration.get_context_for_planning(
            observer, strategist, tactician
        )
        assert context["strategist"]["session_battles"] == 1
        assert context["tactician"]["pattern_count"] == 1
    
    def test_battle_to_strategy_consolidation(self):
        """Test battle outcomes becoming strategies"""
        observer, strategist, tactician, consolidator = create_memory_system(
            session_id="session_001",
            start_tick=0
        )
        
        for i in range(5):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=["Quick Attack", "Thunder Shock"],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        result = consolidator.consolidate_strategist_to_tactician()
        
        assert result.success is True
        assert result.details["battles_analyzed"] == 5


class TestEdgeCases:
    """Tests for edge cases and error handling"""
    
    def test_empty_recent_actions(self):
        """Test observer with no recent actions"""
        observer = create_observer_memory()
        outcomes = observer.get_recent_outcomes()
        assert outcomes == []
    
    def test_win_rate_no_battles(self):
        """Test win rate with no battles"""
        strategist = create_strategist_memory("session_001", 0)
        win_rate = strategist.get_win_rate()
        assert win_rate == 0.0
    
    def test_empty_patterns_query(self):
        """Test querying patterns when none exist"""
        tactician = create_tactician_memory()
        patterns = tactician.get_relevant_patterns({"test": "context"})
        assert patterns == []
    
    def test_nonexistent_preference(self):
        """Test getting nonexistent preference"""
        tactician = create_tactician_memory()
        pref = tactician.get_preference("nonexistent")
        assert pref is None
    
    def test_empty_consolidation_history(self):
        """Test consolidator with no history"""
        consolidator = create_consolidator()
        status = consolidator.get_consolidation_status()
        assert status["consolidation_history_length"] == 0
    
    def test_invalid_battle_record(self):
        """Test handling invalid battle data"""
        strategist = create_strategist_memory("session_001", 0)
        
        battle = BattleRecord(
            battle_id="b1",
            start_tick=100,
            end_tick=105,
            enemy_pokemon="Rattata",
            enemy_level=3,
            player_pokemon="Pikachu",
            player_level=5,
            outcome="unknown",
            turns_taken=2,
            player_hp_remaining=30.0,
            moves_used=[],
            items_used=[],
            key_decisions=[]
        )
        strategist.record_battle(battle)
        
        assert strategist.total_battles == 1
        assert strategist.victories == 0
        assert strategist.defeats == 0
    
    def test_max_actions_fifo_order(self):
        """Test FIFO order with max actions"""
        observer = create_observer_memory()
        
        for i in range(20):
            action = ActionRecord(
                tick=i, action_type="press", action_value=str(i),
                reasoning="Test", confidence=0.8, success=True,
                outcome_summary="OK", duration_ms=50.0
            )
            observer.add_action(action)
        
        assert len(observer.recent_actions) == 10
        assert observer.recent_actions[0].action_value == "10"
        assert observer.recent_actions[-1].action_value == "19"
    
    def test_mistake_severity_sorting(self):
        """Test mistakes are sorted by severity"""
        tactician = create_tactician_memory()
        
        for severity in ["minor", "critical", "major"]:
            mistake = MistakeRecord(
                mistake_id=f"m_{severity}",
                description=f"Mistake {severity}",
                situation={"type": severity},
                outcome="Bad",
                severity=severity,
                prevention_tip="Be careful",
                first_occurred=time.time(),
                last_occurred=time.time()
            )
            tactician.add_mistake(mistake)
        
        mistakes = tactician.get_mistakes_for_context({})
        assert len(mistakes) == 3
        assert mistakes[0].severity == "critical"
    
    def test_consolidator_missing_references(self):
        """Test consolidator with missing memory references"""
        consolidator = create_consolidator()
        
        result = consolidator.consolidate_observer_to_strategist()
        assert result.success is False
        
        result = consolidator.consolidate_strategist_to_tactician()
        assert result.success is False


class TestPerformance:
    """Performance tests for memory operations"""
    
    def test_observer_query_performance(self):
        """Test observer query performance (<1ms)"""
        observer = create_observer_memory()
        for i in range(10):
            action = ActionRecord(
                tick=i, action_type="press", action_value="A",
                reasoning="Test", confidence=0.8, success=True,
                outcome_summary="OK", duration_ms=50.0
            )
            observer.add_action(action)
        
        iterations = 1000
        start = time.perf_counter()
        for _ in range(iterations):
            observer.get_recent_outcomes()
            observer.get_success_rate()
            observer.get_avg_confidence()
        elapsed = (time.perf_counter() - start) * 1000
        
        avg_time = elapsed / iterations
        assert avg_time < 1.0, f"Observer query took {avg_time:.2f}ms"
    
    def test_strategist_query_performance(self):
        """Test strategist query performance (<5ms)"""
        strategist = create_strategist_memory("session_001", 0)
        
        for i in range(100):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory" if i % 2 == 0 else "defeat",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=[],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            strategist.get_win_rate()
            strategist.get_objectives_progress()
            strategist.get_battles_by_outcome("victory")
        elapsed = (time.perf_counter() - start) * 1000
        
        avg_time = elapsed / iterations
        assert avg_time < 5.0, f"Strategist query took {avg_time:.2f}ms"
    
    def test_tactician_query_performance(self):
        """Test tactician query performance (<10ms)"""
        tactician = create_tactician_memory()
        
        for i in range(100):
            pattern = LearnedPattern(
                pattern_id=f"p{i}",
                pattern_type="battle",
                description=f"Pattern {i}",
                trigger_conditions={"type": i % 5},
                learned_from_session="s1",
                learned_from_tick=100,
                confidence=0.5 + (i % 5) * 0.1,
                relevance_score=0.5
            )
            tactician.add_pattern(pattern)
        
        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            tactician.get_relevant_patterns({"type": 2})
            tactician.get_patterns_by_type("battle")
            tactician.get_high_confidence_patterns(0.7)
        elapsed = (time.perf_counter() - start) * 1000
        
        avg_time = elapsed / iterations
        assert avg_time < 10.0, f"Tactician query took {avg_time:.2f}ms"
    
    def test_consolidation_performance(self):
        """Test consolidation performance (<100ms)"""
        observer, strategist, tactician, consolidator = create_memory_system(
            session_id="session_001",
            start_tick=0
        )
        
        for i in range(20):
            action = ActionRecord(
                tick=i, action_type="press", action_value="A",
                reasoning="Test", confidence=0.8, success=True,
                outcome_summary="OK", duration_ms=50.0
            )
            observer.add_action(action)
        
        for i in range(20):
            battle = BattleRecord(
                battle_id=f"b{i}",
                start_tick=i*10,
                end_tick=i*10+5,
                enemy_pokemon="Rattata",
                enemy_level=3,
                player_pokemon="Pikachu",
                player_level=5,
                outcome="victory",
                turns_taken=2,
                player_hp_remaining=30.0,
                moves_used=["Quick Attack"],
                items_used=[],
                key_decisions=[]
            )
            strategist.record_battle(battle)
        
        for i in range(50):
            pattern = LearnedPattern(
                pattern_id=f"p{i}",
                pattern_type="battle",
                description=f"Pattern {i}",
                trigger_conditions={},
                learned_from_session="s1",
                learned_from_tick=100,
                confidence=0.5,
                relevance_score=0.1
            )
            tactician.add_pattern(pattern)
        
        start = time.perf_counter()
        result = consolidator.consolidate_all()
        elapsed = (time.perf_counter() - start) * 1000
        
        assert result.consolidation_time_ms < 100.0, f"Consolidation took {result.consolidation_time_ms:.2f}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])