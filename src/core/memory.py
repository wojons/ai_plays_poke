"""
Tri-Tier Memory Architecture for PTP-01X Pokemon AI

Implements three-tier memory system:
- ObserverMemory: Ephemeral, tick-level working memory
- StrategistMemory: Session-level tactical memory
- TacticianMemory: Persistent, long-term learned knowledge
- MemoryConsolidator: Pattern recognition and memory management

Performance Specifications:
- Observer query: <1ms
- Strategist query: <5ms
- Tactician query: <10ms
- Consolidation: <100ms
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json
import time
import logging
import sqlite3
import uuid
from enum import Enum, auto
from collections import defaultdict


logger = logging.getLogger(__name__)


class MemoryTier(Enum):
    """Memory tier identification"""
    OBSERVER = auto()
    STRATEGIST = auto()
    TACTICIAN = auto()


MAX_RECENT_ACTIONS = 10


# ============================================================================
# OBSERVER MEMORY (Ephemeral, Tick-Level)
# ============================================================================

@dataclass
class TickState:
    """Current tick game state snapshot"""
    tick: int = 0
    timestamp: float = 0.0
    location: str = ""
    is_battle: bool = False
    party_hp_percent: float = 100.0
    money: int = 0
    badges: List[str] = field(default_factory=list)
    screen_type: str = "overworld"
    active_goal: Optional[str] = None


@dataclass
class ActionRecord:
    """Recent action with outcome"""
    tick: int
    action_type: str
    action_value: str
    reasoning: str
    confidence: float
    success: bool
    outcome_summary: str
    duration_ms: float


@dataclass
class SensoryInput:
    """Immediate vision/OCR input"""
    vision_labels: List[str] = field(default_factory=list)
    ocr_text: str = ""
    ocr_confidence: float = 0.0
    screen_type: str = "unknown"
    enemy_pokemon: Optional[str] = None
    player_hp_percent: float = 100.0
    enemy_hp_percent: Optional[float] = None
    available_actions: List[str] = field(default_factory=list)


@dataclass
class ObserverMemory:
    """
    Ephemeral working memory for current decision context
    
    Lifecycle: Created per decision, cleared after action execution
    Performance: <1ms query time
    """
    current_state: TickState = field(default_factory=TickState)
    recent_actions: List[ActionRecord] = field(default_factory=list)
    sensory_input: SensoryInput = field(default_factory=SensoryInput)
    decision_context: Dict[str, Any] = field(default_factory=dict)
    
    def get_recent_outcomes(self) -> List[Dict[str, Any]]:
        """Get summary of recent action outcomes"""
        return [
            {
                "tick": action.tick,
                "action_type": action.action_type,
                "action_value": action.action_value,
                "success": action.success,
                "outcome_summary": action.outcome_summary,
                "confidence": action.confidence
            }
            for action in self.recent_actions
        ]
    
    def add_action(self, action: ActionRecord):
        """Record action and maintain FIFO buffer (max 10 actions)"""
        self.recent_actions.append(action)
        if len(self.recent_actions) > MAX_RECENT_ACTIONS:
            self.recent_actions.pop(0)
    
    def clear(self):
        """Reset memory for new decision cycle"""
        self.decision_context.clear()
        self.recent_actions.clear()
        self.sensory_input = SensoryInput()
        self.current_state = TickState()
    
    def update_state(self, **kwargs):
        """Update current state with new values"""
        for key, value in kwargs.items():
            if hasattr(self.current_state, key):
                setattr(self.current_state, key, value)
    
    def get_success_rate(self) -> float:
        """Get success rate of recent actions"""
        if not self.recent_actions:
            return 0.0
        successful = sum(1 for a in self.recent_actions if a.success)
        return successful / len(self.recent_actions)
    
    def get_avg_confidence(self) -> float:
        """Get average confidence of recent actions"""
        if not self.recent_actions:
            return 0.0
        return sum(a.confidence for a in self.recent_actions) / len(self.recent_actions)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for debugging"""
        return {
            "current_state": {
                "tick": self.current_state.tick,
                "location": self.current_state.location,
                "is_battle": self.current_state.is_battle,
                "screen_type": self.current_state.screen_type,
                "party_hp_percent": self.current_state.party_hp_percent,
                "money": self.current_state.money,
                "badges": self.current_state.badges,
                "active_goal": self.current_state.active_goal,
            },
            "recent_actions_count": len(self.recent_actions),
            "recent_outcomes": self.get_recent_outcomes(),
            "sensory_input": {
                "vision_labels": self.sensory_input.vision_labels,
                "screen_type": self.sensory_input.screen_type,
                "enemy_pokemon": self.sensory_input.enemy_pokemon,
                "player_hp_percent": self.sensory_input.player_hp_percent,
                "available_actions": self.sensory_input.available_actions,
                "ocr_confidence": self.sensory_input.ocr_confidence,
            },
            "decision_context_keys": list(self.decision_context.keys()),
        }


# ============================================================================
# STRATEGIST MEMORY (Session-Level)
# ============================================================================

@dataclass
class SessionObjective:
    """Current session objective"""
    objective_id: str
    name: str
    description: str
    objective_type: str
    priority: int
    status: str
    progress_percent: float
    created_tick: int
    completed_tick: Optional[int]
    prerequisites: List[str]
    related_location: Optional[str]


@dataclass
class BattleRecord:
    """Single battle outcome"""
    battle_id: str
    start_tick: int
    end_tick: int
    enemy_pokemon: str
    enemy_level: int
    player_pokemon: str
    player_level: int
    outcome: str
    turns_taken: int
    player_hp_remaining: float
    moves_used: List[str]
    items_used: List[str]
    key_decisions: List[str]


@dataclass
class LocationVisited:
    """Location exploration record"""
    location_name: str
    location_type: str
    first_visit_tick: int
    last_visit_tick: int
    visit_count: int
    explored_areas: List[str]
    unexplored_areas: List[str]
    points_of_interest: List[str]
    npcs_interacted: List[str]


@dataclass
class ResourceSnapshot:
    """Resource state at point in time"""
    tick: int
    money: int
    items: Dict[str, int]
    tms_obtained: List[int]
    hms_obtained: List[str]


@dataclass
class StrategistMemory:
    """
    Session-level tactical memory
    
    Lifecycle: Created at session start, consolidated at session end
    Performance: <5ms query time
    """
    session_id: str
    session_start_tick: int
    objectives: List[SessionObjective]
    active_objective: Optional[SessionObjective]
    battle_history: List[BattleRecord]
    locations_visited: Dict[str, LocationVisited]
    resource_history: List[ResourceSnapshot]
    total_battles: int = 0
    victories: int = 0
    defeats: int = 0
    current_money: int = 0
    current_items: Dict[str, int] = field(default_factory=dict)
    
    def get_objectives_progress(self) -> Dict[str, float]:
        """Get completion percentage by objective type"""
        progress_by_type = defaultdict(list)
        for obj in self.objectives:
            progress_by_type[obj.objective_type].append(obj.progress_percent)
        
        return {
            obj_type: sum(progress) / len(progress) if progress else 0.0
            for obj_type, progress in progress_by_type.items()
        }
    
    def get_win_rate(self) -> float:
        """Calculate session battle win rate"""
        if self.total_battles == 0:
            return 0.0
        return self.victories / self.total_battles
    
    def record_battle(self, battle: BattleRecord):
        """Add battle to history and update stats"""
        self.battle_history.append(battle)
        self.total_battles += 1
        
        if battle.outcome == "victory":
            self.victories += 1
        elif battle.outcome == "defeat":
            self.defeats += 1
    
    def update_objective_progress(self, objective_id: str, progress: float):
        """Update objective progress"""
        for obj in self.objectives:
            if obj.objective_id == objective_id:
                obj.progress_percent = min(100.0, max(0.0, progress))
                if obj.progress_percent >= 100.0:
                    obj.status = "completed"
                    obj.completed_tick = self.battle_history[-1].end_tick if self.battle_history else None
                break
    
    def add_objective(self, objective: SessionObjective):
        """Add new objective"""
        self.objectives.append(objective)
        if objective.status == "active" and self.active_objective is None:
            self.active_objective = objective
    
    def complete_objective(self, objective_id: str):
        """Mark objective as completed"""
        for obj in self.objectives:
            if obj.objective_id == objective_id:
                obj.status = "completed"
                obj.progress_percent = 100.0
                obj.completed_tick = self.battle_history[-1].end_tick if self.battle_history else None
                if self.active_objective and self.active_objective.objective_id == objective_id:
                    self.active_objective = None
                break
    
    def add_location(self, location: LocationVisited):
        """Record new location visit"""
        if location.location_name in self.locations_visited:
            existing = self.locations_visited[location.location_name]
            existing.visit_count += 1
            existing.last_visit_tick = location.last_visit_tick
            for area in location.explored_areas:
                if area not in existing.explored_areas:
                    existing.explored_areas.append(area)
            for poi in location.points_of_interest:
                if poi not in existing.points_of_interest:
                    existing.points_of_interest.append(poi)
            for npc in location.npcs_interacted:
                if npc not in existing.npcs_interacted:
                    existing.npcs_interacted.append(npc)
        else:
            self.locations_visited[location.location_name] = location
    
    def snapshot_resources(self, tick: int):
        """Record current resource state"""
        snapshot = ResourceSnapshot(
            tick=tick,
            money=self.current_money,
            items=dict(self.current_items),
            tms_obtained=[],  # Would be populated from inventory
            hms_obtained=[]   # Would be populated from inventory
        )
        self.resource_history.append(snapshot)
        if len(self.resource_history) > 100:
            self.resource_history.pop(0)
    
    def update_money(self, amount: int):
        """Update current money"""
        self.current_money = max(0, self.current_money + amount)
    
    def update_items(self, item: str, quantity: int):
        """Update item quantity"""
        current = self.current_items.get(item, 0)
        new_quantity = max(0, current + quantity)
        if new_quantity == 0:
            self.current_items.pop(item, None)
        else:
            self.current_items[item] = new_quantity
    
    def get_battles_by_outcome(self, outcome: str) -> List[BattleRecord]:
        """Get all battles with specific outcome"""
        return [b for b in self.battle_history if b.outcome == outcome]
    
    def get_recent_battles(self, count: int = 5) -> List[BattleRecord]:
        """Get most recent battles"""
        return self.battle_history[-count:] if count > 0 else self.battle_history
    
    def get_session_duration_ticks(self) -> int:
        """Get session duration in ticks"""
        if not self.battle_history:
            return 0
        return self.battle_history[-1].end_tick - self.session_start_tick
    
    def clear_session(self):
        """Clear session data for new session"""
        self.objectives.clear()
        self.active_objective = None
        self.battle_history.clear()
        self.locations_visited.clear()
        self.resource_history.clear()
        self.total_battles = 0
        self.victories = 0
        self.defeats = 0
        self.current_money = 0
        self.current_items.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for debugging"""
        return {
            "session_id": self.session_id,
            "session_start_tick": self.session_start_tick,
            "total_battles": self.total_battles,
            "victories": self.victories,
            "defeats": self.defeats,
            "win_rate": self.get_win_rate(),
            "active_objective": self.active_objective.name if self.active_objective else None,
            "locations_count": len(self.locations_visited),
            "objectives_count": len(self.objectives),
            "completed_objectives": len([o for o in self.objectives if o.status == "completed"]),
            "session_duration_ticks": self.get_session_duration_ticks(),
            "current_money": self.current_money,
            "current_items_count": len(self.current_items),
        }


# ============================================================================
# TACTICIAN MEMORY (Persistent, Long-Term)
# ============================================================================

@dataclass
class LearnedPattern:
    """Learned pattern from experience"""
    pattern_id: str
    pattern_type: str
    description: str
    trigger_conditions: Dict[str, Any]
    learned_from_session: str
    learned_from_tick: int
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.0
    last_validated: float = 0.0
    relevance_score: float = 0.5
    
    def update_confidence(self):
        """Update confidence based on success/failure ratio"""
        total = self.success_count + self.failure_count
        if total > 0:
            self.confidence = self.success_count / total
        self.last_validated = time.time()


@dataclass
class SuccessfulStrategy:
    """Strategy that worked in past battles"""
    strategy_id: str
    context: Dict[str, Any]
    enemy_type: str
    player_pokemon: str
    strategy_description: str
    moves_sequence: List[str]
    success_rate: float = 0.0
    total_uses: int = 0
    successful_uses: int = 0
    first_used: float = 0.0
    last_used: float = 0.0
    
    def record_use(self, success: bool):
        """Record a use of this strategy"""
        self.total_uses += 1
        if success:
            self.successful_uses += 1
        self.success_rate = self.successful_uses / self.total_uses if self.total_uses > 0 else 0.0
        self.last_used = time.time()


@dataclass
class MistakeRecord:
    """Mistake to avoid in future"""
    mistake_id: str
    description: str
    situation: Dict[str, Any]
    outcome: str
    severity: str
    prevention_tip: str
    first_occurred: float
    last_occurred: float
    occurrence_count: int = 1
    
    def record_occurrence(self):
        """Record another occurrence of this mistake"""
        self.last_occurred = time.time()
        self.occurrence_count += 1


@dataclass
class PlayerPreference:
    """Player-configured or learned preferences"""
    preference_id: str
    category: str
    description: str
    preference_value: Any
    learned_from_session: str
    confidence: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class TacticianMemory:
    """
    Persistent long-term memory
    
    Lifecycle: Loaded at startup, saved periodically, pruned periodically
    Performance: <10ms query time
    """
    patterns: Dict[str, LearnedPattern] = field(default_factory=dict)
    strategies: Dict[str, SuccessfulStrategy] = field(default_factory=dict)
    mistakes: Dict[str, MistakeRecord] = field(default_factory=dict)
    preferences: Dict[str, PlayerPreference] = field(default_factory=dict)
    total_sessions: int = 0
    total_battles: int = 0
    overall_win_rate: float = 0.0
    last_saved: float = 0.0
    
    def add_pattern(self, pattern: LearnedPattern):
        """Add or update learned pattern"""
        if pattern.pattern_id in self.patterns:
            existing = self.patterns[pattern.pattern_id]
            existing.success_count = pattern.success_count
            existing.failure_count = pattern.failure_count
            existing.confidence = pattern.confidence
            existing.relevance_score = max(existing.relevance_score, pattern.relevance_score)
            existing.last_validated = time.time()
        else:
            pattern.last_validated = time.time()
            self.patterns[pattern.pattern_id] = pattern
    
    def record_strategy_success(self, strategy_id: str, success: bool):
        """Record successful use of strategy"""
        if strategy_id in self.strategies:
            self.strategies[strategy_id].record_use(success)
    
    def get_or_create_strategy(
        self,
        context: Dict[str, Any],
        enemy_type: str,
        player_pokemon: str,
        moves_sequence: List[str]
    ) -> SuccessfulStrategy:
        """Get existing strategy or create new one"""
        strategy_key = self._generate_strategy_key(context, enemy_type, player_pokemon, moves_sequence)
        
        if strategy_key in self.strategies:
            return self.strategies[strategy_key]
        
        strategy = SuccessfulStrategy(
            strategy_id=strategy_key,
            context=context,
            enemy_type=enemy_type,
            player_pokemon=player_pokemon,
            strategy_description=f"Strategy against {enemy_type} using {player_pokemon}",
            moves_sequence=moves_sequence,
            first_used=time.time()
        )
        self.strategies[strategy_key] = strategy
        return strategy
    
    def _generate_strategy_key(
        self,
        context: Dict[str, Any],
        enemy_type: str,
        player_pokemon: str,
        moves_sequence: List[str]
    ) -> str:
        """Generate unique strategy key"""
        key_parts = [
            enemy_type,
            player_pokemon,
            ",".join(sorted(moves_sequence))
        ]
        return f"strat_{'_'.join(key_parts)}"
    
    def add_mistake(self, mistake: MistakeRecord):
        """Record new mistake to avoid"""
        if mistake.mistake_id in self.mistakes:
            self.mistakes[mistake.mistake_id].record_occurrence()
        else:
            if not self.merge_similar_mistake(mistake):
                mistake.first_occurred = time.time()
                mistake.last_occurred = time.time()
                self.mistakes[mistake.mistake_id] = mistake
    
    def merge_similar_mistake(self, mistake: MistakeRecord) -> bool:
        """Try to merge with existing similar mistake, return True if merged"""
        for existing_id, existing in self.mistakes.items():
            if self._situations_similar(existing.situation, mistake.situation):
                existing.occurrence_count += mistake.occurrence_count
                existing.last_occurred = time.time()
                return True
        return False
    
    def _situations_similar(self, sit1: Dict[str, Any], sit2: Dict[str, Any]) -> bool:
        """Check if two situations are similar enough to merge"""
        common_keys = set(sit1.keys()) & set(sit2.keys())
        if not common_keys:
            return False
        matches = sum(1 for k in common_keys if sit1.get(k) == sit2.get(k))
        return matches / len(common_keys) >= 0.7
    
    def get_preference(self, category: str) -> Optional[PlayerPreference]:
        """Get preference for category"""
        return self.preferences.get(category)
    
    def set_preference(self, preference: PlayerPreference):
        """Set or update preference"""
        if preference.category in self.preferences:
            existing = self.preferences[preference.category]
            existing.preference_value = preference.preference_value
            existing.confidence = max(existing.confidence, preference.confidence)
            existing.updated_at = time.time()
        else:
            preference.created_at = time.time()
            preference.updated_at = time.time()
            self.preferences[preference.category] = preference
    
    def get_relevant_patterns(self, context: Dict[str, Any]) -> List[LearnedPattern]:
        """Get patterns relevant to current context"""
        relevant = []
        for pattern in self.patterns.values():
            if self._context_matches(pattern.trigger_conditions, context):
                relevant.append(pattern)
        return sorted(relevant, key=lambda p: p.relevance_score, reverse=True)
    
    def _context_matches(self, conditions: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if context matches pattern conditions"""
        if not conditions:
            return True
        if not context:
            return True
        matches = sum(1 for k, v in conditions.items() if context.get(k) == v)
        return matches / len(conditions) >= 0.5
    
    def get_successful_strategies(
        self,
        enemy_type: str,
        player_pokemon: str
    ) -> List[SuccessfulStrategy]:
        """Get strategies that worked against similar enemies"""
        candidates = []
        for strategy in self.strategies.values():
            type_match = enemy_type == strategy.enemy_type or strategy.enemy_type in enemy_type or enemy_type in strategy.enemy_type
            if not player_pokemon:
                pokemon_match = True
            else:
                pokemon_match = player_pokemon == strategy.player_pokemon
            if type_match and pokemon_match:
                candidates.append(strategy)
        return sorted(candidates, key=lambda s: s.success_rate, reverse=True)
    
    def get_mistakes_for_context(self, context: Dict[str, Any]) -> List[MistakeRecord]:
        """Get mistakes relevant to current situation"""
        relevant = []
        for mistake in self.mistakes.values():
            if self._context_matches(mistake.situation, context):
                relevant.append(mistake)
        return sorted(relevant, key=lambda m: self._severity_weight(m.severity), reverse=True)
    
    def _severity_weight(self, severity: str) -> int:
        """Get numeric weight for severity"""
        weights = {"critical": 3, "major": 2, "minor": 1}
        return weights.get(severity.lower(), 0)
    
    def get_patterns_by_type(self, pattern_type: str) -> List[LearnedPattern]:
        """Get all patterns of a specific type"""
        return [p for p in self.patterns.values() if p.pattern_type == pattern_type]
    
    def get_high_confidence_patterns(self, threshold: float = 0.7) -> List[LearnedPattern]:
        """Get patterns above confidence threshold"""
        return [p for p in self.patterns.values() if p.confidence >= threshold]
    
    def update_stats(self, battle_won: bool):
        """Update overall stats after a battle"""
        self.total_battles += 1
        if battle_won:
            if self.overall_win_rate == 0:
                self.overall_win_rate = 1.0
            else:
                self.overall_win_rate = (self.overall_win_rate * (self.total_battles - 1) + 1) / self.total_battles
        else:
            if self.overall_win_rate == 0:
                self.overall_win_rate = 0.0
            else:
                self.overall_win_rate = (self.overall_win_rate * (self.total_battles - 1)) / self.total_battles
    
    def increment_sessions(self):
        """Increment session counter"""
        self.total_sessions += 1
    
    def load_from_database(self, db_path: str) -> bool:
        """Load persistent memory from database"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT pattern_id, pattern_type, description, trigger_conditions, learned_from_session, learned_from_tick, success_count, failure_count, confidence, last_validated, relevance_score FROM tactician_patterns")
            for row in cursor.fetchall():
                pattern = LearnedPattern(
                    pattern_id=row[0],
                    pattern_type=row[1],
                    description=row[2],
                    trigger_conditions=json.loads(row[3]) if row[3] else {},
                    learned_from_session=row[4],
                    learned_from_tick=row[5],
                    success_count=row[6],
                    failure_count=row[7],
                    confidence=row[8],
                    last_validated=row[9],
                    relevance_score=row[10]
                )
                self.patterns[pattern.pattern_id] = pattern
            
            cursor.execute("SELECT strategy_id, context, enemy_type, player_pokemon, strategy_description, moves_sequence, success_rate, total_uses, successful_uses, first_used, last_used FROM successful_strategies")
            for row in cursor.fetchall():
                strategy = SuccessfulStrategy(
                    strategy_id=row[0],
                    context=json.loads(row[1]) if row[1] else {},
                    enemy_type=row[2],
                    player_pokemon=row[3],
                    strategy_description=row[4],
                    moves_sequence=json.loads(row[5]) if row[5] else [],
                    success_rate=row[6],
                    total_uses=row[7],
                    successful_uses=row[8],
                    first_used=row[9],
                    last_used=row[10]
                )
                self.strategies[strategy.strategy_id] = strategy
            
            cursor.execute("SELECT mistake_id, description, situation, outcome, severity, prevention_tip, first_occurred, last_occurred, occurrence_count FROM mistake_records")
            for row in cursor.fetchall():
                mistake = MistakeRecord(
                    mistake_id=row[0],
                    description=row[1],
                    situation=json.loads(row[2]) if row[2] else {},
                    outcome=row[3],
                    severity=row[4],
                    prevention_tip=row[5],
                    first_occurred=row[6],
                    last_occurred=row[7],
                    occurrence_count=row[8]
                )
                self.mistakes[mistake.mistake_id] = mistake
            
            cursor.execute("SELECT preference_id, category, description, preference_value, learned_from_session, confidence, created_at, updated_at FROM player_preferences")
            for row in cursor.fetchall():
                preference = PlayerPreference(
                    preference_id=row[0],
                    category=row[1],
                    description=row[2],
                    preference_value=json.loads(row[3]) if row[3] else None,
                    learned_from_session=row[4],
                    confidence=row[5],
                    created_at=row[6],
                    updated_at=row[7]
                )
                self.preferences[preference.category] = preference
            
            cursor.execute("SELECT total_sessions, total_battles, overall_win_rate FROM tactician_stats")
            stats = cursor.fetchone()
            if stats:
                self.total_sessions = stats[0]
                self.total_battles = stats[1]
                self.overall_win_rate = stats[2]
            
            conn.close()
            self.last_saved = time.time()
            logger.info(f"Loaded {len(self.patterns)} patterns, {len(self.strategies)} strategies, {len(self.mistakes)} mistakes, {len(self.preferences)} preferences")
            return True
        except Exception as e:
            logger.error(f"Failed to load tactician memory: {e}")
            return False
    
    def save_to_database(self, db_path: str) -> bool:
        """Save persistent memory to database"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tactician_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    pattern_type TEXT,
                    description TEXT,
                    trigger_conditions TEXT,
                    learned_from_session TEXT,
                    learned_from_tick INTEGER,
                    success_count INTEGER,
                    failure_count INTEGER,
                    confidence REAL,
                    last_validated REAL,
                    relevance_score REAL
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS successful_strategies (
                    strategy_id TEXT PRIMARY KEY,
                    context TEXT,
                    enemy_type TEXT,
                    player_pokemon TEXT,
                    strategy_description TEXT,
                    moves_sequence TEXT,
                    success_rate REAL,
                    total_uses INTEGER,
                    successful_uses INTEGER,
                    first_used REAL,
                    last_used REAL
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mistake_records (
                    mistake_id TEXT PRIMARY KEY,
                    description TEXT,
                    situation TEXT,
                    outcome TEXT,
                    severity TEXT,
                    prevention_tip TEXT,
                    first_occurred REAL,
                    last_occurred REAL,
                    occurrence_count INTEGER
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_preferences (
                    preference_id TEXT PRIMARY KEY,
                    category TEXT UNIQUE,
                    description TEXT,
                    preference_value TEXT,
                    learned_from_session TEXT,
                    confidence REAL,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tactician_stats (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_sessions INTEGER,
                    total_battles INTEGER,
                    overall_win_rate REAL
                )
            """)
            
            for pattern in self.patterns.values():
                cursor.execute("""
                    INSERT OR REPLACE INTO tactician_patterns
                    (pattern_id, pattern_type, description, trigger_conditions, learned_from_session, learned_from_tick, success_count, failure_count, confidence, last_validated, relevance_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pattern.pattern_id,
                    pattern.pattern_type,
                    pattern.description,
                    json.dumps(pattern.trigger_conditions),
                    pattern.learned_from_session,
                    pattern.learned_from_tick,
                    pattern.success_count,
                    pattern.failure_count,
                    pattern.confidence,
                    pattern.last_validated,
                    pattern.relevance_score
                ))
            
            for strategy in self.strategies.values():
                cursor.execute("""
                    INSERT OR REPLACE INTO successful_strategies
                    (strategy_id, context, enemy_type, player_pokemon, strategy_description, moves_sequence, success_rate, total_uses, successful_uses, first_used, last_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    strategy.strategy_id,
                    json.dumps(strategy.context),
                    strategy.enemy_type,
                    strategy.player_pokemon,
                    strategy.strategy_description,
                    json.dumps(strategy.moves_sequence),
                    strategy.success_rate,
                    strategy.total_uses,
                    strategy.successful_uses,
                    strategy.first_used,
                    strategy.last_used
                ))
            
            for mistake in self.mistakes.values():
                cursor.execute("""
                    INSERT OR REPLACE INTO mistake_records
                    (mistake_id, description, situation, outcome, severity, prevention_tip, first_occurred, last_occurred, occurrence_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mistake.mistake_id,
                    mistake.description,
                    json.dumps(mistake.situation),
                    mistake.outcome,
                    mistake.severity,
                    mistake.prevention_tip,
                    mistake.first_occurred,
                    mistake.last_occurred,
                    mistake.occurrence_count
                ))
            
            for preference in self.preferences.values():
                cursor.execute("""
                    INSERT OR REPLACE INTO player_preferences
                    (preference_id, category, description, preference_value, learned_from_session, confidence, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    preference.preference_id,
                    preference.category,
                    preference.description,
                    json.dumps(preference.preference_value),
                    preference.learned_from_session,
                    preference.confidence,
                    preference.created_at,
                    preference.updated_at
                ))
            
            cursor.execute("""
                INSERT OR REPLACE INTO tactician_stats (id, total_sessions, total_battles, overall_win_rate)
                VALUES (1, ?, ?, ?)
            """, (self.total_sessions, self.total_battles, self.overall_win_rate))
            
            conn.commit()
            conn.close()
            self.last_saved = time.time()
            logger.info(f"Saved {len(self.patterns)} patterns, {len(self.strategies)} strategies, {len(self.mistakes)} mistakes, {len(self.preferences)} preferences")
            return True
        except Exception as e:
            logger.error(f"Failed to save tactician memory: {e}")
            return False
    
    def prune_low_value(self, config: "ConsolidationConfig") -> int:
        """Prune low-value memories based on config"""
        pruned_count = 0
        
        patterns_by_type = defaultdict(list)
        for pattern in self.patterns.values():
            patterns_by_type[pattern.pattern_type].append(pattern)
        
        for pattern_type, patterns in patterns_by_type.items():
            if len(patterns) <= config.max_patterns_per_type:
                continue
            patterns.sort(key=lambda p: (p.relevance_score, p.confidence), reverse=True)
            for pattern in patterns[config.max_patterns_per_type:]:
                del self.patterns[pattern.pattern_id]
                pruned_count += 1
        
        if len(self.strategies) > config.max_strategies:
            strategies = sorted(self.strategies.values(), key=lambda s: s.success_rate, reverse=True)
            for strategy in strategies[config.max_strategies:]:
                del self.strategies[strategy.strategy_id]
                pruned_count += 1
        
        if len(self.mistakes) > config.max_mistakes:
            mistakes = sorted(self.mistakes.values(), key=lambda m: self._severity_weight(m.severity), reverse=True)
            for mistake in mistakes[config.max_mistakes:]:
                del self.mistakes[mistake.mistake_id]
                pruned_count += 1
        
        return pruned_count
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for debugging"""
        return {
            "total_sessions": self.total_sessions,
            "total_battles": self.total_battles,
            "overall_win_rate": self.overall_win_rate,
            "patterns_count": len(self.patterns),
            "strategies_count": len(self.strategies),
            "mistakes_count": len(self.mistakes),
            "preferences_count": len(self.preferences),
            "patterns_by_type": {
                pt: len([p for p in self.patterns.values() if p.pattern_type == pt])
                for pt in set(p.pattern_type for p in self.patterns.values())
            },
            "high_confidence_patterns": len(self.get_high_confidence_patterns()),
        }


# ============================================================================
# MEMORY CONSOLIDATOR
# ============================================================================

@dataclass
class ConsolidationConfig:
    """Configuration for consolidation behavior"""
    tick_interval: int = 1000
    session_end_consolidate: bool = True
    pattern_threshold: float = 0.7
    min_occurrences_for_pattern: int = 3
    forgetting_decay_rate: float = 0.95
    max_patterns_per_type: int = 50
    max_strategies: int = 100
    max_mistakes: int = 200
    importance_threshold: float = 0.3


@dataclass
class ConsolidationResult:
    """Result of a consolidation operation"""
    success: bool
    patterns_extracted: int = 0
    strategies_created: int = 0
    mistakes_recorded: int = 0
    memories_pruned: int = 0
    consolidation_time_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class MemoryConsolidator:
    """
    Manages memory consolidation between tiers
    
    Responsibilities:
    - Pattern recognition from Observer -> Strategist
    - Strategy extraction from Strategist -> Tactician
    - Forgetting logic (decay, prune)
    - Memory prioritization
    
    Performance: <100ms consolidation time
    """
    
    def __init__(
        self,
        config: Optional[ConsolidationConfig] = None,
        observer_memory: Optional[ObserverMemory] = None,
        strategist_memory: Optional[StrategistMemory] = None,
        tactician_memory: Optional[TacticianMemory] = None
    ):
        self.config = config or ConsolidationConfig()
        self.observer = observer_memory
        self.strategist = strategist_memory
        self.tactician = tactician_memory
        self.last_consolidation_tick = 0
        self.consolidation_history: List[ConsolidationResult] = []
        self._pending_patterns: List[Dict[str, Any]] = []
        self._pending_strategies: List[Dict[str, Any]] = []
        self._pending_mistakes: List[Dict[str, Any]] = []
    
    def tick(self, current_tick: int) -> Optional[ConsolidationResult]:
        """
        Called every tick - checks if consolidation needed
        
        Triggers consolidation every N ticks or at session end
        """
        if current_tick - self.last_consolidation_tick >= self.config.tick_interval:
            return self.consolidate_all()
        return None
    
    def consolidate_all(self) -> ConsolidationResult:
        """Perform full consolidation cycle"""
        start_time = time.time()
        result = ConsolidationResult(success=True)
        
        if self.observer and self.strategist:
            observer_result = self.consolidate_observer_to_strategist()
            result.patterns_extracted = observer_result.patterns_extracted
            result.details["observer_consolidation"] = observer_result.details
        
        if self.strategist and self.tactician:
            strategist_result = self.consolidate_strategist_to_tactician()
            result.strategies_created = strategist_result.strategies_created
            result.mistakes_recorded = strategist_result.mistakes_recorded
            result.details["strategist_consolidation"] = strategist_result.details
        
        if self.tactician:
            forgetting_result = self.apply_forgetting()
            result.memories_pruned = forgetting_result.memories_pruned
            result.details["forgetting"] = forgetting_result.details
        
        result.consolidation_time_ms = (time.time() - start_time) * 1000
        self.last_consolidation_tick = self.observer.current_state.tick if self.observer else 0
        self.consolidation_history.append(result)
        
        if len(self.consolidation_history) > 100:
            self.consolidation_history = self.consolidation_history[-100:]
        
        logger.info(f"Consolidation completed in {result.consolidation_time_ms:.2f}ms: "
                   f"+{result.patterns_extracted} patterns, +{result.strategies_created} strategies, "
                   f"-{result.memories_pruned} pruned")
        return result
    
    def consolidate_observer_to_strategist(self) -> ConsolidationResult:
        """
        Extract patterns from recent observer memory to strategist
        
        - Identify recurring action sequences
        - Detect common situations
        - Aggregate successful/failed approaches
        """
        result = ConsolidationResult(success=True)
        
        if not self.observer or not self.strategist:
            result.success = False
            result.details["error"] = "Missing observer or strategist memory"
            return result
        
        recent_actions = self.observer.recent_actions
        if len(recent_actions) < self.config.min_occurrences_for_pattern:
            result.details["message"] = "Not enough actions for pattern extraction"
            return result
        
        successful_actions = [a for a in recent_actions if a.success]
        failed_actions = [a for a in recent_actions if not a.success]
        
        if successful_actions:
            success_pattern = {
                "pattern_type": "action_sequence",
                "description": f"Successful sequence: {', '.join(a.action_value for a in successful_actions[-3:])}",
                "trigger_conditions": {
                    "action_types": list(set(a.action_type for a in successful_actions)),
                    "success_rate": len(successful_actions) / len(recent_actions)
                },
                "actions": [a.action_value for a in successful_actions],
                "success": True
            }
            self._pending_patterns.append(success_pattern)
            result.patterns_extracted += 1
        
        if failed_actions:
            failure_pattern = {
                "pattern_type": "failed_approach",
                "description": f"Failed sequence: {', '.join(a.action_value for a in failed_actions[-3:])}",
                "trigger_conditions": {
                    "action_types": list(set(a.action_type for a in failed_actions)),
                    "success_rate": len(successful_actions) / len(recent_actions) if recent_actions else 0
                },
                "actions": [a.action_value for a in failed_actions],
                "success": False
            }
            self._pending_patterns.append(failure_pattern)
            result.patterns_extracted += 1
        
        result.details["pending_patterns"] = len(self._pending_patterns)
        return result
    
    def consolidate_strategist_to_tactician(self) -> ConsolidationResult:
        """
        Extract learned strategies from session to long-term memory
        
        - Identify battle patterns with high success rates
        - Extract successful move sequences
        - Record mistakes with high severity
        - Update preferences based on behavior
        """
        result = ConsolidationResult(success=True)
        
        if not self.strategist or not self.tactician:
            result.success = False
            result.details["error"] = "Missing strategist or tactician memory"
            return result
        
        battles = self.strategist.battle_history
        if not battles:
            result.details["message"] = "No battles to consolidate"
            return result
        
        battle_outcomes = defaultdict(lambda: {"wins": 0, "losses": 0, "moves": []})
        
        for battle in battles:
            key = f"{battle.enemy_pokemon}_{battle.player_pokemon}"
            if battle.outcome == "victory":
                battle_outcomes[key]["wins"] += 1
                battle_outcomes[key]["moves"].extend(battle.moves_used)
            else:
                battle_outcomes[key]["losses"] += 1
        
        for key, outcome in battle_outcomes.items():
            total = outcome["wins"] + outcome["losses"]
            win_rate = outcome["wins"] / total if total > 0 else 0
            
            if win_rate >= self.config.pattern_threshold and outcome["moves"]:
                parts = key.split("_")
                enemy_type = parts[0] if parts else "Unknown"
                player_pokemon = parts[1] if len(parts) > 1 else "Unknown"
                
                if self.tactician:
                    strategy = self.tactician.get_or_create_strategy(
                        context={"battle_type": "wild"},
                        enemy_type=enemy_type,
                        player_pokemon=player_pokemon,
                        moves_sequence=list(dict.fromkeys(outcome["moves"][-5:]))
                    )
                    strategy.record_use(True)
                    result.strategies_created += 1
        
        for battle in battles:
            if battle.outcome == "defeat":
                mistake_key = f"mistake_{battle.enemy_pokemon}_{battle.player_pokemon}_{battle.turns_taken}"
                mistake = MistakeRecord(
                    mistake_id=mistake_key,
                    description=f"Lost to {battle.enemy_pokemon} with {battle.player_pokemon}",
                    situation={
                        "enemy_pokemon": battle.enemy_pokemon,
                        "enemy_level": battle.enemy_level,
                        "player_pokemon": battle.player_pokemon,
                        "player_level": battle.player_level,
                        "turns_taken": battle.turns_taken
                    },
                    outcome="defeat",
                    severity="major" if battle.player_hp_remaining == 0 else "minor",
                    prevention_tip="Consider switching Pokemon or using different strategy",
                    first_occurred=time.time(),
                    last_occurred=time.time(),
                    occurrence_count=1
                )
                
                if self.tactician:
                    if not self.tactician.merge_similar_mistake(mistake):
                        self.tactician.add_mistake(mistake)
                        result.mistakes_recorded += 1
        
        result.details["battles_analyzed"] = len(battles)
        return result
    
    def apply_forgetting(self) -> ConsolidationResult:
        """
        Remove or decay old memories
        
        - Apply decay to old patterns
        - Prune low-relevance items
        - Archive instead of delete when valuable
        """
        result = ConsolidationResult(success=True)
        
        if not self.tactician:
            return result
        
        start_count = len(self.tactician.patterns) + len(self.tactician.strategies) + len(self.tactician.mistakes)
        
        pruned = self.tactician.prune_low_value(self.config)
        result.memories_pruned = pruned
        
        end_count = len(self.tactician.patterns) + len(self.tactician.strategies) + len(self.tactician.mistakes)
        
        result.details["patterns"] = len(self.tactician.patterns)
        result.details["strategies"] = len(self.tactician.strategies)
        result.details["mistakes"] = len(self.tactician.mistakes)
        result.details["pruned"] = pruned
        
        return result
    
    def prioritize_memories(self) -> Dict[str, List[str]]:
        """
        Rank memories by importance for retention
        
        Returns:
            Dict with tier -> list of memory_ids sorted by priority
        """
        priorities = {
            "observer": [],
            "strategist": [],
            "tactician": []
        }
        
        if self.observer:
            priorities["observer"] = ["current_state", "recent_actions"]
        
        if self.strategist:
            priorities["strategist"] = [
                obj.objective_id for obj in self.strategist.objectives if obj.status == "active"
            ]
            priorities["strategist"].extend(
                b.battle_id for b in self.strategist.battle_history[-10:]
            )
        
        if self.tactician:
            priorities["tactician"] = sorted(
                [p.pattern_id for p in self.tactician.patterns.values()],
                key=lambda pid: self.tactician.patterns[pid].relevance_score,
                reverse=True
            )[:20]
        
        return priorities
    
    def get_consolidation_status(self) -> Dict[str, Any]:
        """Get current consolidation status and statistics"""
        return {
            "last_consolidation_tick": self.last_consolidation_tick,
            "consolidation_history_length": len(self.consolidation_history),
            "pending_patterns": len(self._pending_patterns),
            "pending_strategies": len(self._pending_strategies),
            "pending_mistakes": len(self._pending_mistakes),
            "config": {
                "tick_interval": self.config.tick_interval,
                "pattern_threshold": self.config.pattern_threshold,
                "min_occurrences": self.config.min_occurrences_for_pattern,
                "max_patterns_per_type": self.config.max_patterns_per_type,
                "max_strategies": self.config.max_strategies,
                "max_mistakes": self.config.max_mistakes,
            }
        }
    
    def set_observer(self, memory: ObserverMemory):
        """Set observer memory reference"""
        self.observer = memory
    
    def set_strategist(self, memory: StrategistMemory):
        """Set strategist memory reference"""
        self.strategist = memory
    
    def set_tactician(self, memory: TacticianMemory):
        """Set tactician memory reference"""
        self.tactician = memory
    
    def get_avg_consolidation_time(self) -> float:
        """Get average consolidation time in ms"""
        if not self.consolidation_history:
            return 0.0
        return sum(r.consolidation_time_ms for r in self.consolidation_history) / len(self.consolidation_history)


# ============================================================================
# INTEGRATION MIXINS
# ============================================================================

class MemoryDatabaseMixin:
    """Mixins for database operations"""
    
    @staticmethod
    def save_tactician_memory(
        tactician: TacticianMemory,
        db_path: str
    ) -> bool:
        """Save tactician memory to database"""
        return tactician.save_to_database(db_path)
    
    @staticmethod
    def load_tactician_memory(db_path: str) -> TacticianMemory:
        """Load tactician memory from database"""
        tactician = TacticianMemory()
        tactician.load_from_database(db_path)
        return tactician
    
    @staticmethod
    def save_strategist_checkpoint(
        strategist: StrategistMemory,
        db: Any,
        session_id: int
    ) -> bool:
        """Save strategist memory as checkpoint"""
        try:
            cursor = db.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO strategist_checkpoints
                (session_id, session_data, battle_history, locations, objectives)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session_id,
                json.dumps(strategist.to_dict()),
                json.dumps([b.to_dict() if hasattr(b, 'to_dict') else b for b in strategist.battle_history]),
                json.dumps(strategist.locations_visited),
                json.dumps([o.to_dict() if hasattr(o, 'to_dict') else o for o in strategist.objectives])
            ))
            db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save strategist checkpoint: {e}")
            return False
    
    @staticmethod
    def load_strategist_checkpoint(
        db: Any,
        session_id: int
    ) -> Optional[StrategistMemory]:
        """Load strategist memory from checkpoint"""
        try:
            cursor = db.cursor()
            cursor.execute("""
                SELECT session_data FROM strategist_checkpoints
                WHERE session_id = ?
            """, (session_id,))
            row = cursor.fetchone()
            if row:
                data = json.loads(row[0])
                strategist = StrategistMemory(
                    session_id=data["session_id"],
                    session_start_tick=data["session_start_tick"],
                    objectives=[],
                    active_objective=None,
                    battle_history=[],
                    locations_visited={},
                    resource_history=[]
                )
                return strategist
            return None
        except Exception as e:
            logger.error(f"Failed to load strategist checkpoint: {e}")
            return None


class MemoryGOAPIntegration:
    """Integration with GOAP planner"""
    
    @staticmethod
    def get_context_for_planning(
        observer: ObserverMemory,
        strategist: StrategistMemory,
        tactician: TacticianMemory
    ) -> Dict[str, Any]:
        """Compile memory context for GOAP decision making"""
        return {
            "observer": {
                "current_location": observer.current_state.location,
                "is_battle": observer.current_state.is_battle,
                "party_hp_percent": observer.current_state.party_hp_percent,
                "screen_type": observer.current_state.screen_type,
                "recent_success_rate": observer.get_success_rate(),
                "recent_avg_confidence": observer.get_avg_confidence(),
            },
            "strategist": {
                "active_objective": strategist.active_objective.name if strategist.active_objective else None,
                "active_objective_type": strategist.active_objective.objective_type if strategist.active_objective else None,
                "active_objective_progress": strategist.active_objective.progress_percent if strategist.active_objective else 0.0,
                "session_win_rate": strategist.get_win_rate(),
                "session_battles": strategist.total_battles,
                "session_victories": strategist.victories,
                "visited_locations": list(strategist.locations_visited.keys()),
                "objectives_progress": strategist.get_objectives_progress(),
            },
            "tactician": {
                "total_sessions": tactician.total_sessions,
                "overall_win_rate": tactician.overall_win_rate,
                "high_confidence_patterns": len(tactician.get_high_confidence_patterns()),
                "pattern_count": len(tactician.patterns),
                "strategy_count": len(tactician.strategies),
            }
        }
    
    @staticmethod
    def query_strategist_objectives(
        strategist: StrategistMemory
    ) -> List[SessionObjective]:
        """Get active objectives for GOAP"""
        return [o for o in strategist.objectives if o.status == "active"]
    
    @staticmethod
    def query_tactician_strategies(
        tactician: TacticianMemory,
        context: Dict[str, Any]
    ) -> List[SuccessfulStrategy]:
        """Get relevant strategies for current context"""
        enemy_type = context.get("enemy_type", "")
        player_pokemon = context.get("player_pokemon", "")
        return tactician.get_successful_strategies(enemy_type, player_pokemon)
    
    @staticmethod
    def record_planning_outcome(
        observer: ObserverMemory,
        success: bool,
        outcome: str
    ):
        """Record planning outcome for learning"""
        if observer.recent_actions:
            observer.recent_actions[-1].success = success
            observer.recent_actions[-1].outcome_summary = outcome
    
    @staticmethod
    def get_action_history_for_planning(
        observer: ObserverMemory
    ) -> List[Dict[str, Any]]:
        """Get action history formatted for GOAP"""
        return observer.get_recent_outcomes()


class MemoryAIIntegration:
    """Integration with AI Client for context injection"""
    
    @staticmethod
    def inject_memory_context(
        observer: ObserverMemory,
        strategist: StrategistMemory,
        tactician: TacticianMemory
    ) -> Dict[str, Any]:
        """
        Inject memory context into AI prompts
        
        Returns:
            Dict with context sections for different AI models
        """
        return {
            "tactical": MemoryAIIntegration.get_tactical_context(tactician, {
                "location": observer.current_state.location,
                "is_battle": observer.current_state.is_battle,
                "enemy_pokemon": observer.sensory_input.enemy_pokemon,
            }),
            "strategic": MemoryAIIntegration.get_strategic_context(strategist),
            "recent_actions": MemoryAIIntegration.get_recent_actions_summary(observer),
            "action_success_rate": observer.get_success_rate(),
            "session_performance": {
                "win_rate": strategist.get_win_rate(),
                "battles": strategist.total_battles,
                "victories": strategist.victories,
            }
        }
    
    @staticmethod
    def get_tactical_context(
        tactician: TacticianMemory,
        battle_context: Dict[str, Any]
    ) -> str:
        """Get tactical context for battle AI"""
        context_parts = []
        
        enemy_type = battle_context.get("enemy_pokemon", "")
        if enemy_type:
            strategies = tactician.get_successful_strategies(enemy_type, "")
            if strategies:
                context_parts.append(f"Previously effective strategies against {enemy_type}:")
                for strategy in strategies[:3]:
                    context_parts.append(f"  - {strategy.strategy_description} ({strategy.success_rate*100:.0f}% success)")
        
        mistakes = tactician.get_mistakes_for_context(battle_context)
        if mistakes:
            context_parts.append(f"\nMistakes to avoid ({len(mistakes)} relevant):")
            for mistake in mistakes[:2]:
                context_parts.append(f"  - {mistake.description}: {mistake.prevention_tip}")
        
        return "\n".join(context_parts) if context_parts else "No tactical patterns yet."
    
    @staticmethod
    def get_strategic_context(
        strategist: StrategistMemory
    ) -> str:
        """Get strategic context for planning AI"""
        context_parts = []
        
        if strategist.active_objective:
            context_parts.append(f"Current Objective: {strategist.active_objective.name}")
            context_parts.append(f"Progress: {strategist.active_objective.progress_percent:.0f}%")
        
        context_parts.append(f"Session Performance: {strategist.get_win_rate()*100:.0f}% win rate ({strategist.victories}W-{strategist.defeats}L)")
        
        visited = list(strategist.locations_visited.keys())
        if visited:
            context_parts.append(f"Visited Locations: {', '.join(visited[-5:])}")
        
        return "\n".join(context_parts)
    
    @staticmethod
    def get_recent_actions_summary(
        observer: ObserverMemory
    ) -> str:
        """Get summary of recent actions for AI context"""
        if not observer.recent_actions:
            return "No recent actions."
        
        recent = observer.recent_actions[-5:]
        successes = sum(1 for a in recent if a.success)
        
        parts = [
            f"Last {len(recent)} actions ({successes} successful):"
        ]
        for action in recent:
            status = "OK" if action.success else "FAIL"
            parts.append(f"  [{status}] {action.action_type}:{action.action_value} - {action.reasoning[:30]}")
        
        return "\n".join(parts)
    
    @staticmethod
    def get_pattern_context(
        tactician: TacticianMemory,
        context: Dict[str, Any]
    ) -> str:
        """Get patterns relevant to current context"""
        patterns = tactician.get_relevant_patterns(context)
        if not patterns:
            return "No relevant patterns."
        
        return "\n".join([
            f"- {p.description} (confidence: {p.confidence:.0%})"
            for p in patterns[:5]
        ])


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def create_observer_memory() -> ObserverMemory:
    """Factory function to create observer memory"""
    return ObserverMemory()


def create_strategist_memory(session_id: str, start_tick: int) -> StrategistMemory:
    """Factory function to create strategist memory for session"""
    return StrategistMemory(
        session_id=session_id,
        session_start_tick=start_tick,
        objectives=[],
        active_objective=None,
        battle_history=[],
        locations_visited={},
        resource_history=[]
    )


def create_tactician_memory() -> TacticianMemory:
    """Factory function to create tactician memory"""
    return TacticianMemory()


def create_consolidator(
    observer: Optional[ObserverMemory] = None,
    strategist: Optional[StrategistMemory] = None,
    tactician: Optional[TacticianMemory] = None,
    config: Optional[ConsolidationConfig] = None
) -> MemoryConsolidator:
    """Factory function to create memory consolidator"""
    return MemoryConsolidator(
        config=config,
        observer_memory=observer,
        strategist_memory=strategist,
        tactician_memory=tactician
    )


def create_memory_system(
    session_id: str,
    start_tick: int,
    config: Optional[ConsolidationConfig] = None
) -> Tuple[ObserverMemory, StrategistMemory, TacticianMemory, MemoryConsolidator]:
    """
    Factory function to create complete memory system
    
    Returns:
        Tuple of (observer, strategist, tactician, consolidator)
    """
    observer = create_observer_memory()
    strategist = create_strategist_memory(session_id, start_tick)
    tactician = create_tactician_memory()
    consolidator = create_consolidator(
        observer=observer,
        strategist=strategist,
        tactician=tactician,
        config=config
    )
    return observer, strategist, tactician, consolidator