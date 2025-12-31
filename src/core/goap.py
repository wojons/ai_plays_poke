"""
GOAP (Goal-Oriented Action Planning) Decision Core for PTP-01X Pokemon AI

Implements comprehensive goal-based decision making with:
- Goal class hierarchy (DefeatGymGoal, CatchPokemonGoal, ReachLocationGoal, etc.)
- Action class hierarchy (NavigateAction, BattleAction, MenuAction, DialogAction)
- Hierarchical planning with goal decomposition and dependency resolution
- Goal prioritization with multi-factor scoring
- Plan monitoring with failure detection and replanning
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from datetime import datetime
import time
import logging
import uuid
import heapq
from collections import defaultdict


logger = logging.getLogger(__name__)


class GoalType(Enum):
    """Goal type categories"""
    IMMEDIATE = auto()
    SHORT_TERM = auto()
    MEDIUM_TERM = auto()
    LONG_TERM = auto()


class ActionType(Enum):
    """Action type categories"""
    NAVIGATION = auto()
    BATTLE = auto()
    MENU = auto()
    DIALOG = auto()
    WAIT = auto()


class PlanStatus(Enum):
    """Status of a plan"""
    PENDING = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    FAILED = auto()
    ABORTED = auto()


class PriorityLevel(Enum):
    """Priority levels for goals"""
    CRITICAL = 95
    HIGH = 70
    MEDIUM = 40
    LOW = 0


@dataclass
class GameState:
    """Represents the current game state for planning"""
    tick: int = 0
    timestamp: str = ""
    location: str = ""
    badges: int = 0
    money: int = 0
    is_battle: bool = False
    party: List[Dict[str, Any]] = field(default_factory=list)
    inventory: Dict[str, int] = field(default_factory=dict)
    active_quests: List[str] = field(default_factory=list)
    pokedex_caught: int = 0
    pokedex_seen: int = 0
    hms_obtained: List[str] = field(default_factory=list)
    tms_obtained: List[int] = field(default_factory=list)

    def get_avg_party_level(self) -> float:
        if not self.party:
            return 0.0
        return sum(p.get("level", 1) for p in self.party) / len(self.party)

    def get_party_hp_percent(self) -> float:
        if not self.party:
            return 0.0
        total_hp = sum(p.get("current_hp", 0) for p in self.party)
        max_hp = sum(p.get("max_hp", 1) for p in self.party)
        return total_hp / max_hp if max_hp > 0 else 0.0

    def get_fainted_count(self) -> int:
        return sum(1 for p in self.party if p.get("current_hp", 0) == 0)

    def get_low_hp_pokemon(self) -> List[Dict[str, Any]]:
        return [p for p in self.party if p.get("current_hp", 0) / p.get("max_hp", 1) < 0.25]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "timestamp": self.timestamp,
            "location": self.location,
            "badges": self.badges,
            "money": self.money,
            "is_battle": self.is_battle,
            "party": self.party,
            "inventory": self.inventory,
            "active_quests": self.active_quests,
            "pokedex_caught": self.pokedex_caught,
            "pokedex_seen": self.pokedex_seen,
            "hms_obtained": self.hms_obtained,
            "tms_obtained": self.tms_obtained,
        }

    def to_state_dict(self) -> Dict[str, Any]:
        return {
            **self.to_dict(),
            "avg_party_level": self.get_avg_party_level(),
            "party_hp_percent": self.get_party_hp_percent(),
            "fainted_count": self.get_fainted_count(),
        }


@dataclass
class Goal:
    """Base class for all goals"""
    goal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    goal_type: GoalType = GoalType.SHORT_TERM
    priority: int = 50
    status: str = "PENDING"
    progress: float = 0.0
    prerequisites: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    required_resources: Dict[str, Any] = field(default_factory=dict)
    estimated_cost: float = 0.0
    estimated_value: float = 0.0
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3

    def is_feasible(self, state: GameState) -> Tuple[bool, Dict[str, Any]]:
        missing = {}
        for resource, required in self.required_resources.items():
            if resource == "money":
                if state.money < required:
                    missing["money"] = required - state.money
            elif resource == "badges":
                if state.badges < required:
                    missing["badges"] = required - state.badges
            elif resource == "level":
                if state.get_avg_party_level() < required:
                    missing["level"] = required - state.get_avg_party_level()
            elif resource == "pokemon_species":
                has_species = any(p.get("species") == required for p in state.party)
                if not has_species:
                    missing["pokemon_species"] = required
        return len(missing) == 0, missing

    def calculate_utility(self, state: GameState) -> float:
        if self.estimated_cost == 0:
            return self.estimated_value * self.priority
        return (self.estimated_value / self.estimated_cost) * self.priority

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "name": self.name,
            "description": self.description,
            "goal_type": self.goal_type.name,
            "priority": self.priority,
            "status": self.status,
            "progress": self.progress,
            "prerequisites": self.prerequisites,
            "dependencies": self.dependencies,
            "required_resources": self.required_resources,
            "estimated_cost": self.estimated_cost,
            "estimated_value": self.estimated_value,
        }


class DefeatGymGoal(Goal):
    """Goal to defeat a specific gym leader"""

    def __init__(self, gym_name: str, gym_leader: str, required_badges: int = 1,
                 required_level: int = 12, estimated_cost: float = 1000.0):
        super().__init__(
            goal_id=str(uuid.uuid4()),
            name=f"Defeat {gym_leader}",
            description=f"Defeat {gym_leader} at {gym_name} to earn the gym badge",
            goal_type=GoalType.MEDIUM_TERM,
            priority=80,
            required_resources={"badges": required_badges, "level": required_level},
            estimated_cost=estimated_cost,
            estimated_value=100.0
        )
        self.gym_name = gym_name
        self.gym_leader = gym_leader
        self.required_badges = required_badges
        self.required_level = required_level


class CatchPokemonGoal(Goal):
    """Goal to catch a specific Pokemon species"""

    def __init__(self, species: str, min_level: int = 1, max_level: int = 100,
                 location: Optional[str] = None, estimated_cost: float = 100.0):
        super().__init__(
            goal_id=str(uuid.uuid4()),
            name=f"Catch {species}",
            description=f"Catch a {species} Pokemon",
            goal_type=GoalType.SHORT_TERM,
            priority=60,
            required_resources={},
            estimated_cost=estimated_cost,
            estimated_value=50.0
        )
        self.species = species
        self.min_level = min_level
        self.max_level = max_level
        self.location = location

    def is_feasible(self, state: GameState) -> Tuple[bool, Dict[str, Any]]:
        feasible, missing = super().is_feasible(state)
        if self.location and state.location != self.location:
            missing["location"] = self.location
        return len(missing) == 0, missing


class ReachLocationGoal(Goal):
    """Goal to reach a specific location"""

    def __init__(self, location_name: str, location_type: str = "route",
                 required_badges: int = 0, estimated_cost: float = 200.0):
        super().__init__(
            goal_id=str(uuid.uuid4()),
            name=f"Reach {location_name}",
            description=f"Navigate to {location_name}",
            goal_type=GoalType.SHORT_TERM,
            priority=50,
            required_resources={"badges": required_badges},
            estimated_cost=estimated_cost,
            estimated_value=30.0
        )
        self.location_name = location_name
        self.location_type = location_type
        self.required_badges = required_badges


class HealPartyGoal(Goal):
    """Goal to heal the party at a Pokemon Center"""

    def __init__(self, urgency: str = "normal"):
        priority = 95 if urgency == "critical" else 70
        super().__init__(
            goal_id=str(uuid.uuid4()),
            name="Heal Party",
            description="Visit Pokemon Center to heal party",
            goal_type=GoalType.IMMEDIATE,
            priority=priority,
            required_resources={},
            estimated_cost=50.0,
            estimated_value=80.0
        )
        self.urgency = urgency


class TrainPokemonGoal(Goal):
    """Goal to train Pokemon to a target level"""

    def __init__(self, target_level: int, training_location: str = "nearest_route",
                 estimated_cost: float = 500.0):
        super().__init__(
            goal_id=str(uuid.uuid4()),
            name=f"Train to Level {target_level}",
            description=f"Train party Pokemon to level {target_level}",
            goal_type=GoalType.SHORT_TERM,
            priority=55,
            required_resources={"level": target_level},
            estimated_cost=estimated_cost,
            estimated_value=60.0
        )
        self.target_level = target_level
        self.training_location = training_location


class ObtainItemGoal(Goal):
    """Goal to obtain a specific item"""

    def __init__(self, item_name: str, quantity: int = 1, buy: bool = True,
                 target_price: Optional[int] = None, estimated_cost: float = 100.0):
        priority = 90 if item_name in ["Poke Ball", "Potion"] else 50
        super().__init__(
            goal_id=str(uuid.uuid4()),
            name=f"Obtain {item_name}",
            description=f"{'Buy' if buy else 'Find'} {quantity}x {item_name}",
            goal_type=GoalType.SHORT_TERM,
            priority=priority,
            required_resources={"money": target_price} if buy and target_price else {},
            estimated_cost=estimated_cost,
            estimated_value=40.0
        )
        self.item_name = item_name
        self.quantity = quantity
        self.buy = buy
        self.target_price = target_price


class Action(ABC):
    """Base class for all actions"""

    def __init__(self, action_id: Optional[str] = None):
        self.action_id = action_id or str(uuid.uuid4())
        self.status = "PENDING"
        self.progress = 0.0
        self.retry_count = 0
        self.max_retries = 3
        self.execution_time: Optional[float] = None
        self.error_message: Optional[str] = None

    @property
    @abstractmethod
    def action_type(self) -> ActionType:
        pass

    @abstractmethod
    def get_preconditions(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_effects(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_cost(self) -> float:
        pass

    @abstractmethod
    def execute(self, state: GameState) -> Tuple[bool, GameState]:
        pass

    def can_execute(self, state: GameState) -> bool:
        preconditions = self.get_preconditions()
        if not preconditions:
            return True
        for key, required in preconditions.items():
            if key == "location":
                if state.location != required:
                    return False
            elif key == "in_battle":
                if not state.is_battle:
                    return False
            elif key == "not_in_battle":
                if state.is_battle:
                    return False
            elif key == "money":
                if state.money < required:
                    return False
        return True


class NavigateAction(Action):
    """Action to navigate to a location"""

    def __init__(self, target_location: str, method: str = "astar",
                 action_id: Optional[str] = None):
        super().__init__(action_id)
        self.target_location = target_location
        self.method = method

    @property
    def action_type(self) -> ActionType:
        return ActionType.NAVIGATION

    def get_preconditions(self) -> Dict[str, Any]:
        return {"not_in_battle": True}

    def get_effects(self) -> Dict[str, Any]:
        return {"location": self.target_location}

    def get_cost(self) -> float:
        return 10.0

    def execute(self, state: GameState) -> Tuple[bool, GameState]:
        try:
            logger.info(f"Navigating to {self.target_location} using {self.method}")
            new_state = GameState(**state.to_dict())
            new_state.location = self.target_location
            self.status = "COMPLETED"
            return True, new_state
        except Exception as e:
            self.error_message = str(e)
            self.status = "FAILED"
            return False, state


class BattleAction(Action):
    """Action to engage in battle"""

    def __init__(self, battle_type: str = "wild", target: Optional[str] = None,
                 strategy: str = "auto", action_id: Optional[str] = None):
        super().__init__(action_id)
        self.battle_type = battle_type
        self.target = target
        self.strategy = strategy

    @property
    def action_type(self) -> ActionType:
        return ActionType.BATTLE

    def get_preconditions(self) -> Dict[str, Any]:
        return {"in_battle": True}

    def get_effects(self) -> Dict[str, Any]:
        return {"xp_gained": 100, "battle_won": True}

    def get_cost(self) -> float:
        return 5.0

    def execute(self, state: GameState) -> Tuple[bool, GameState]:
        try:
            logger.info(f"Executing battle action: {self.battle_type} battle")
            new_state = GameState(**state.to_dict())
            new_state.tick += 1
            self.status = "COMPLETED"
            return True, new_state
        except Exception as e:
            self.error_message = str(e)
            self.status = "FAILED"
            return False, state


class MenuAction(Action):
    """Action to perform menu operations"""

    def __init__(self, menu_type: str, action: str, target: Optional[str] = None,
                 quantity: int = 1, action_id: Optional[str] = None):
        super().__init__(action_id)
        self.menu_type = menu_type
        self.action = action
        self.target = target
        self.quantity = quantity

    @property
    def action_type(self) -> ActionType:
        return ActionType.MENU

    def get_preconditions(self) -> Dict[str, Any]:
        return {}

    def get_effects(self) -> Dict[str, Any]:
        effects = {}
        if self.menu_type == "shop" and self.action == "buy":
            effects["item_obtained"] = self.target
        elif self.menu_type == "pokemon_center" and self.action == "heal":
            effects["party_healed"] = True
        return effects

    def get_cost(self) -> float:
        return 2.0

    def execute(self, state: GameState) -> Tuple[bool, GameState]:
        try:
            logger.info(f"Executing menu action: {self.menu_type} - {self.action}")
            new_state = GameState(**state.to_dict())
            if self.menu_type == "shop" and self.action == "buy":
                if self.target:
                    new_state.inventory[self.target] = new_state.inventory.get(self.target, 0) + self.quantity
            elif self.menu_type == "pokemon_center" and self.action == "heal":
                for pokemon in new_state.party:
                    pokemon["current_hp"] = pokemon.get("max_hp", pokemon.get("current_hp", 100))
            self.status = "COMPLETED"
            return True, new_state
        except Exception as e:
            self.error_message = str(e)
            self.status = "FAILED"
            return False, state


class DialogAction(Action):
    """Action to interact with NPCs via dialog"""

    def __init__(self, npc_name: str, dialog_type: str = "talk",
                 action_id: Optional[str] = None):
        super().__init__(action_id)
        self.npc_name = npc_name
        self.dialog_type = dialog_type

    @property
    def action_type(self) -> ActionType:
        return ActionType.DIALOG

    def get_preconditions(self) -> Dict[str, Any]:
        return {"not_in_battle": True}

    def get_effects(self) -> Dict[str, Any]:
        return {"dialog_completed": True, "npc_interaction": self.npc_name}

    def get_cost(self) -> float:
        return 3.0

    def execute(self, state: GameState) -> Tuple[bool, GameState]:
        try:
            logger.info(f"Executing dialog action: {self.dialog_type} with {self.npc_name}")
            new_state = GameState(**state.to_dict())
            self.status = "COMPLETED"
            return True, new_state
        except Exception as e:
            self.error_message = str(e)
            self.status = "FAILED"
            return False, state


@dataclass
class Plan:
    """Represents a plan to achieve a goal"""
    plan_id: str
    goal_id: str
    actions: List[Action]
    status: PlanStatus = PlanStatus.PENDING
    current_action_index: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_cost: float = 0.0
    success_rate: float = 0.0

    def __post_init__(self):
        if not self.plan_id:
            self.plan_id = str(uuid.uuid4())
        self.total_cost = sum(a.get_cost() for a in self.actions)

    def get_current_action(self) -> Optional[Action]:
        if 0 <= self.current_action_index < len(self.actions):
            return self.actions[self.current_action_index]
        return None

    def is_complete(self) -> bool:
        return self.current_action_index >= len(self.actions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "status": self.status.name,
            "current_action": self.current_action_index,
            "total_actions": len(self.actions),
            "total_cost": self.total_cost,
        }


class GoalStack:
    """LIFO stack for managing goals"""

    def __init__(self, max_size: int = 50):
        self.stack: List[Goal] = []
        self.max_size = max_size

    def push(self, goal: Goal) -> None:
        for existing in self.stack:
            if existing.goal_id == goal.goal_id:
                existing.priority = max(existing.priority, goal.priority)
                return
        self.stack.append(goal)
        if len(self.stack) > self.max_size:
            self.stack.pop(0)

    def pop(self) -> Optional[Goal]:
        if not self.stack:
            return None
        return self.stack.pop()

    def peek(self) -> Optional[Goal]:
        if not self.stack:
            return None
        return self.stack[-1]

    def remove(self, goal_id: str) -> bool:
        for i, goal in enumerate(self.stack):
            if goal.goal_id == goal_id:
                self.stack.pop(i)
                return True
        return False

    def get_all_goals(self) -> List[Goal]:
        type_order = {GoalType.IMMEDIATE: 0, GoalType.SHORT_TERM: 1,
                      GoalType.MEDIUM_TERM: 2, GoalType.LONG_TERM: 3}
        return sorted(self.stack, key=lambda g: (g.priority, type_order.get(g.goal_type, 4)), reverse=True)

    def is_empty(self) -> bool:
        return len(self.stack) == 0

    def clear(self) -> None:
        self.stack.clear()


class GoalDAG:
    """Directed Acyclic Graph for goal enablement tracking"""

    def __init__(self):
        self.nodes: Dict[str, Goal] = {}
        self.edges: List[Tuple[str, str]] = []

    def add_goal(self, goal: Goal) -> None:
        self.nodes[goal.goal_id] = goal

    def add_prerequisite(self, goal_id: str, prerequisite_id: str) -> None:
        self.edges.append((prerequisite_id, goal_id))

    def get_prerequisites(self, goal_id: str) -> List[str]:
        return [from_id for from_id, to_id in self.edges if to_id == goal_id]

    def get_dependents(self, goal_id: str) -> List[str]:
        return [to_id for from_id, to_id in self.edges if from_id == goal_id]

    def get_critical_path(self) -> List[str]:
        if not self.nodes:
            return []

        distance = {goal_id: 0 for goal_id in self.nodes}
        sorted_goals = self._topological_sort()

        for goal_id in sorted_goals:
            prerequisites = self.get_prerequisites(goal_id)
            for prereq_id in prerequisites:
                if distance[prereq_id] + 1 > distance[goal_id]:
                    distance[goal_id] = distance[prereq_id] + 1

        max_distance_goal = max(distance, key=distance.get)

        critical_path = []
        current = max_distance_goal
        while current:
            critical_path.append(current)
            prerequisites = self.get_prerequisites(current)
            if not prerequisites:
                break
            current = max(prerequisites, key=lambda p: distance[p])

        critical_path.reverse()
        return critical_path

    def _topological_sort(self) -> List[str]:
        in_degree = {goal_id: 0 for goal_id in self.nodes}
        for from_id, to_id in self.edges:
            in_degree[to_id] = in_degree.get(to_id, 0) + 1

        queue = [goal_id for goal_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for dependent in self.get_dependents(node):
                in_degree[dependent] = in_degree.get(dependent, 0) - 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        return result


class PriorityQueue:
    """Priority queue for goal selection"""

    def __init__(self):
        self.heap: List[Tuple[float, str, Goal]] = []
        self.goal_map: Dict[str, Tuple[float, Goal]] = {}

    def push(self, goal: Goal, priority: float) -> None:
        heapq.heappush(self.heap, (-priority, goal.goal_id, goal))
        self.goal_map[goal.goal_id] = (priority, goal)

    def pop(self) -> Optional[Goal]:
        while self.heap:
            neg_priority, _, goal = heapq.heappop(self.heap)
            if goal.goal_id in self.goal_map:
                current_priority, _ = self.goal_map[goal.goal_id]
                if abs(current_priority + neg_priority) < 0.001:
                    del self.goal_map[goal.goal_id]
                    return goal
        return None

    def peek(self) -> Optional[Goal]:
        if not self.heap:
            return None
        _, _, goal = self.heap[0]
        return goal

    def update_priority(self, goal_id: str, new_priority: float) -> bool:
        if goal_id not in self.goal_map:
            return False
        old_priority, old_goal = self.goal_map[goal_id]
        old_goal.priority = int(new_priority)
        heapq.heappush(self.heap, (-new_priority, goal_id, old_goal))
        self.goal_map[goal_id] = (new_priority, old_goal)
        return True

    def is_empty(self) -> bool:
        return len(self.heap) == 0


class GoalPriorityCalculator:
    """Calculates priority scores for goals using multi-factor analysis"""

    def __init__(self):
        self.success_history: Dict[str, Tuple[int, int]] = {}

    def calculate_priority(self, goal: Goal, state: GameState) -> float:
        base_priority = goal.priority

        temporal_multiplier = self._calculate_temporal_multiplier(goal, state)
        dependency_multiplier = self._calculate_dependency_multiplier(goal)
        efficiency_multiplier = self._calculate_efficiency_multiplier(goal, state)
        success_multiplier = self._calculate_success_multiplier(goal)

        risk_penalty = self._calculate_risk_penalty(goal, state)

        final_priority = (base_priority * temporal_multiplier *
                         dependency_multiplier * efficiency_multiplier *
                         success_multiplier) - risk_penalty

        return min(max(final_priority, 0), 100)

    def _calculate_temporal_multiplier(self, goal: Goal, state: GameState) -> float:
        if not goal.deadline:
            return 1.0
        time_remaining = (goal.deadline - datetime.now()).total_seconds()
        if time_remaining < 60:
            return 2.0
        elif time_remaining < 600:
            return 1.5
        elif time_remaining < 3600:
            return 1.2
        return 1.0

    def _calculate_dependency_multiplier(self, goal: Goal) -> float:
        num_dependents = len(goal.dependencies)
        if num_dependents >= 3:
            return 1.5
        elif num_dependents >= 1:
            return 1.2
        return 1.0

    def _calculate_efficiency_multiplier(self, goal: Goal, state: GameState) -> float:
        value = goal.estimated_value
        cost = goal.estimated_cost
        if cost == 0:
            return 1.3
        efficiency = value / cost
        if efficiency > 2.0:
            return 1.3
        elif efficiency > 1.0:
            return 1.1
        elif efficiency > 0.5:
            return 0.9
        return 0.7

    def _calculate_risk_penalty(self, goal: Goal, state: GameState) -> float:
        failure_prob = self._estimate_failure_probability(goal, state)
        if failure_prob > 0.5:
            return 20
        elif failure_prob > 0.2:
            return 10
        return 0

    def _estimate_failure_probability(self, goal: Goal, state: GameState) -> float:
        base_failure = {"BATTLE": 0.3, "SHOPPING": 0.0, "HEALING": 0.0,
                       "NAVIGATION": 0.1, "EXPLORATION": 0.2}.get(goal.name.split()[0].lower(), 0.2)
        if "battle" in goal.name.lower() or "defeat" in goal.name.lower():
            party_level = state.get_avg_party_level()
            target_level = goal.required_resources.get("level", party_level)
            if party_level > target_level:
                return base_failure * 0.5
            elif party_level < target_level - 5:
                return min(base_failure * 2.0, 0.8)
        return base_failure

    def _calculate_success_multiplier(self, goal: Goal) -> float:
        goal_type = goal.goal_type.name
        if goal_type not in self.success_history:
            return 1.0
        successes, total = self.success_history[goal_type]
        success_rate = successes / total if total > 0 else 0.5
        if success_rate > 0.8:
            return 1.2
        elif success_rate > 0.5:
            return 1.0
        return 0.7

    def record_success(self, goal: Goal, success: bool) -> None:
        goal_type = goal.goal_type.name
        if goal_type not in self.success_history:
            self.success_history[goal_type] = [0, 0]
        if success:
            self.success_history[goal_type][0] += 1
        self.success_history[goal_type][1] += 1


class GoalPrioritizer:
    """Manages goal prioritization and selection"""

    def __init__(self):
        self.calculator = GoalPriorityCalculator()
        self.priority_queue = PriorityQueue()
        self.goal_dag = GoalDAG()

    def add_goal(self, goal: Goal, state: GameState) -> None:
        self.goal_dag.add_goal(goal)
        priority = self.calculator.calculate_priority(goal, state)
        self.priority_queue.push(goal, priority)

    def add_prerequisite(self, goal_id: str, prerequisite_id: str) -> None:
        self.goal_dag.add_prerequisite(goal_id, prerequisite_id)

    def select_next_goal(self, state: GameState) -> Optional[Goal]:
        while not self.priority_queue.is_empty():
            goal = self.priority_queue.pop()
            if goal:
                feasible, _ = goal.is_feasible(state)
                if feasible:
                    return goal
        return None

    def reprioritize(self, state: GameState) -> None:
        all_goals = list(self.goal_dag.nodes.values())
        for goal in all_goals:
            priority = self.calculator.calculate_priority(goal, state)
            self.priority_queue.update_priority(goal.goal_id, priority)

    def get_urgent_goals(self, state: GameState) -> List[Goal]:
        urgent = []
        for goal in self.goal_dag.nodes.values():
            if goal.goal_type == GoalType.IMMEDIATE:
                urgent.append(goal)
            elif goal.priority >= PriorityLevel.CRITICAL.value:
                urgent.append(goal)
        return sorted(urgent, key=lambda g: g.priority, reverse=True)

    def get_strategic_goals(self, state: GameState) -> List[Goal]:
        strategic = []
        for goal in self.goal_dag.nodes.values():
            if goal.goal_type in [GoalType.MEDIUM_TERM, GoalType.LONG_TERM]:
                strategic.append(goal)
        return sorted(strategic, key=lambda g: g.priority, reverse=True)


class Planner:
    """Hierarchical planner for goal achievement"""

    def __init__(self, goal_prioritizer: GoalPrioritizer):
        self.goal_prioritizer = goal_prioritizer
        self.plans: Dict[str, Plan] = {}
        self.current_plan: Optional[Plan] = None

    def create_plan(self, goal: Goal, state: GameState) -> Plan:
        actions = self._decompose_goal(goal, state)
        plan = Plan(
            plan_id=str(uuid.uuid4()),
            goal_id=goal.goal_id,
            actions=actions
        )
        self.plans[plan.plan_id] = plan
        return plan

    def _decompose_goal(self, goal: Goal, state: GameState) -> List[Action]:
        actions: List[Action] = []

        if isinstance(goal, DefeatGymGoal):
            actions = self._decompose_gym_goal(goal, state)
        elif isinstance(goal, CatchPokemonGoal):
            actions = self._decompose_catch_goal(goal, state)
        elif isinstance(goal, HealPartyGoal):
            actions = self._decompose_heal_goal(goal, state)
        elif isinstance(goal, TrainPokemonGoal):
            actions = self._decompose_train_goal(goal, state)
        elif isinstance(goal, ObtainItemGoal):
            actions = self._decompose_item_goal(goal, state)
        elif isinstance(goal, ReachLocationGoal):
            actions = [NavigateAction(goal.location_name)]

        return actions

    def _decompose_gym_goal(self, goal: DefeatGymGoal, state: GameState) -> List[Action]:
        actions: List[Action] = []
        if state.get_avg_party_level() < goal.required_level:
            train_goal = TrainPokemonGoal(goal.required_level)
            actions.extend(self._decompose_goal(train_goal, state))
        actions.append(NavigateAction(goal.gym_name))
        actions.append(DialogAction("Gym Leader", "battle"))
        actions.append(BattleAction("trainer", goal.gym_leader, "gym_strategy"))
        return actions

    def _decompose_catch_goal(self, goal: CatchPokemonGoal, state: GameState) -> List[Action]:
        actions: List[Action] = []
        if goal.location:
            actions.append(NavigateAction(goal.location))
        actions.append(BattleAction("wild", goal.species, "catch"))
        actions.append(MenuAction("bag", "use_item", "Poke Ball"))
        return actions

    def _decompose_heal_goal(self, goal: HealPartyGoal, state: GameState) -> List[Action]:
        actions: List[Action] = []
        actions.append(NavigateAction("Pokemon Center", method="nearest"))
        actions.append(DialogAction("Nurse", "heal"))
        return actions

    def _decompose_train_goal(self, goal: TrainPokemonGoal, state: GameState) -> List[Action]:
        actions: List[Action] = []
        actions.append(NavigateAction(goal.training_location))
        while state.get_avg_party_level() < goal.target_level:
            actions.append(BattleAction("wild", strategy="train"))
        return actions

    def _decompose_item_goal(self, goal: ObtainItemGoal, state: GameState) -> List[Action]:
        actions: List[Action] = []
        if goal.buy:
            actions.append(NavigateAction("PokeMart", method="nearest"))
            actions.append(MenuAction("shop", "buy", goal.item_name, goal.quantity))
        return actions

    def validate_plan(self, plan: Plan, state: GameState) -> Tuple[bool, List[str]]:
        errors = []
        for action in plan.actions:
            if not action.can_execute(state):
                errors.append(f"Action {action.action_type} preconditions not met")
        return len(errors) == 0, errors

    def resolve_dependencies(self, goal: Goal, state: GameState) -> List[Goal]:
        prerequisites = []
        for prereq_id in goal.prerequisites:
            prereq_goal = self.goal_prioritizer.goal_dag.nodes.get(prereq_id)
            if prereq_goal:
                feasible, _ = prereq_goal.is_feasible(state)
                if not feasible:
                    prerequisites.extend(self.resolve_dependencies(prereq_goal, state))
                    prerequisites.append(prereq_goal)
        return prerequisites

    def get_current_plan(self) -> Optional[Plan]:
        return self.current_plan

    def set_current_plan(self, plan: Plan) -> None:
        self.current_plan = plan


class PlanMonitor:
    """Monitors plan execution and handles failures"""

    def __init__(self, planner: Planner):
        self.planner = planner
        self.execution_history: List[Dict[str, Any]] = []
        self.replan_count: int = 0
        self.failure_count: int = 0
        self.last_replan_time: Optional[float] = None

    def monitor_execution(self, plan: Plan, state: GameState) -> Tuple[bool, Optional[Plan]]:
        current_action = plan.get_current_action()
        if not current_action:
            return True, None

        if not current_action.can_execute(state):
            if current_action.retry_count >= current_action.max_retries:
                return self._handle_action_failure(plan, state)
            current_action.retry_count += 1
            return False, None

        success, new_state = current_action.execute(state)

        self.execution_history.append({
            "timestamp": time.time(),
            "action": current_action.action_type.name,
            "success": success,
            "state": new_state.to_dict() if new_state else None
        })

        if success:
            plan.current_action_index += 1
            if plan.is_complete():
                return True, None
            return False, None
        else:
            return self._handle_action_failure(plan, state)

    def _handle_action_failure(self, plan: Plan, state: GameState) -> Tuple[bool, Optional[Plan]]:
        self.failure_count += 1
        goal = self.planner.goal_prioritizer.goal_dag.nodes.get(plan.goal_id)
        if goal:
            goal.retry_count += 1
            if goal.retry_count >= goal.max_retries:
                return False, None

        return self._replan(plan, state)

    def _replan(self, failed_plan: Plan, state: GameState) -> Tuple[bool, Optional[Plan]]:
        self.replan_count += 1
        self.last_replan_time = time.time()

        goal = self.planner.goal_prioritizer.goal_dag.nodes.get(failed_plan.goal_id)
        if not goal:
            return False, None

        if self.replan_count > 10:
            logger.warning("Too many replans, entering emergency mode")
            return False, None

        new_plan = self.planner.create_plan(goal, state)
        valid, errors = self.planner.validate_plan(new_plan, state)
        if not valid:
            logger.warning(f"Plan validation failed: {errors}")
            return False, None

        logger.info(f"Replanned for goal {goal.name}")
        return False, new_plan

    def handle_interruption(self, interruption_type: str, state: GameState) -> Tuple[bool, Optional[Plan]]:
        if interruption_type == "random_battle":
            logger.info("Random battle interruption - pausing plan")
            return True, None
        elif interruption_type == "low_hp":
            heal_goal = HealPartyGoal(urgency="critical")
            heal_plan = self.planner.create_plan(heal_goal, state)
            return False, heal_plan
        elif interruption_type == "softlock":
            logger.warning("Softlock detected - emergency recovery")
            return False, None

        return True, None

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "total_executions": len(self.execution_history),
            "replan_count": self.replan_count,
            "failure_count": self.failure_count,
            "success_rate": len([e for e in self.execution_history if e.get("success")]) / max(len(self.execution_history), 1),
            "last_replan_time": self.last_replan_time,
        }


class HierarchicalPlanner:
    """Multi-layer hierarchical planner with strategic, tactical, operational, and reactive layers"""

    def __init__(self):
        self.goal_prioritizer = GoalPrioritizer()
        self.planner = Planner(self.goal_prioritizer)
        self.plan_monitor = PlanMonitor(self.planner)
        self.current_plan: Optional[Plan] = None

    def plan(self, state: GameState) -> Optional[Plan]:
        self.goal_prioritizer.reprioritize(state)
        next_goal = self.goal_prioritizer.select_next_goal(state)
        if not next_goal:
            return None

        prerequisites = self.planner.resolve_dependencies(next_goal, state)
        for prereq in prerequisites:
            self.goal_prioritizer.add_goal(prereq, state)

        plan = self.planner.create_plan(next_goal, state)
        valid, errors = self.planner.validate_plan(plan, state)
        if not valid:
            logger.warning(f"Plan validation failed: {errors}")
            return None

        self.current_plan = plan
        return plan

    def execute_step(self, state: GameState) -> Tuple[bool, Optional[Plan], GameState]:
        if not self.current_plan:
            new_plan = self.plan(state)
            if not new_plan:
                return True, None, state
            self.current_plan = new_plan

        success, new_plan = self.plan_monitor.monitor_execution(self.current_plan, state)

        if new_plan:
            self.current_plan = new_plan

        if success and self.current_plan.is_complete():
            goal = self.goal_prioritizer.goal_dag.nodes.get(self.current_plan.goal_id)
            if goal:
                goal.status = "COMPLETED"
                self.goal_prioritizer.calculator.record_success(goal, True)
            self.current_plan = None
            return True, None, state

        return False, self.current_plan, state

    def handle_interruption(self, interruption_type: str, state: GameState) -> Tuple[bool, Optional[Plan]]:
        return self.plan_monitor.handle_interruption(interruption_type, state)

    def add_goal(self, goal: Goal, state: GameState) -> None:
        self.goal_prioritizer.add_goal(goal, state)

    def get_status(self) -> Dict[str, Any]:
        return {
            "current_plan": self.current_plan.to_dict() if self.current_plan else None,
            "goals_in_queue": len(self.goal_prioritizer.priority_queue.heap),
            "monitor_stats": self.plan_monitor.get_statistics(),
        }


def create_default_game_state() -> GameState:
    """Factory function to create a default game state"""
    return GameState(
        tick=0,
        timestamp=datetime.now().isoformat(),
        location="Pallet Town",
        badges=0,
        money=3000,
        party=[
            {"name": "Pikachu", "species": "Pikachu", "level": 5, "current_hp": 35, "max_hp": 35, "moves": ["Tackle", "Growl", "Thunder Shock", "Quick Attack"]}
        ],
        inventory={"Poke Ball": 5, "Potion": 2},
        active_quests=["becoming_champion"],
        pokedex_caught=0,
        pokedex_seen=3,
        hms_obtained=[],
        tms_obtained=[]
    )


def create_goap_system() -> HierarchicalPlanner:
    """Factory function to create a fully configured GOAP system"""
    return HierarchicalPlanner()