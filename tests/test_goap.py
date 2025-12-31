"""
Unit tests for GOAP Decision Core

Tests the goal hierarchy, action hierarchy, planning, prioritization, and monitoring.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.goap import (
    GoalType, ActionType, PlanStatus, PriorityLevel,
    GameState, Goal, DefeatGymGoal, CatchPokemonGoal, ReachLocationGoal,
    HealPartyGoal, TrainPokemonGoal, ObtainItemGoal,
    Action, NavigateAction, BattleAction, MenuAction, DialogAction,
    Plan, GoalStack, GoalDAG, PriorityQueue, GoalPriorityCalculator,
    GoalPrioritizer, Planner, PlanMonitor, HierarchicalPlanner,
    create_default_game_state, create_goap_system
)


class TestGameState:
    """Tests for GameState dataclass"""

    def test_default_game_state(self):
        state = GameState()
        assert state.tick == 0
        assert state.location == ""
        assert state.badges == 0
        assert state.money == 0
        assert state.party == []

    def test_game_state_with_party(self):
        state = GameState(
            party=[
                {"name": "Pikachu", "level": 5, "current_hp": 35, "max_hp": 35},
                {"name": "Charmander", "level": 5, "current_hp": 30, "max_hp": 39}
            ]
        )
        assert len(state.party) == 2
        assert state.get_avg_party_level() == 5.0

    def test_get_party_hp_percent(self):
        state = GameState(
            party=[
                {"current_hp": 50, "max_hp": 100},
                {"current_hp": 25, "max_hp": 50}
            ]
        )
        assert state.get_party_hp_percent() == 0.5

    def test_get_fainted_count(self):
        state = GameState(
            party=[
                {"current_hp": 0, "max_hp": 100},
                {"current_hp": 50, "max_hp": 100},
                {"current_hp": 0, "max_hp": 100}
            ]
        )
        assert state.get_fainted_count() == 2

    def test_get_low_hp_pokemon(self):
        state = GameState(
            party=[
                {"name": "A", "current_hp": 10, "max_hp": 100},
                {"name": "B", "current_hp": 50, "max_hp": 100},
                {"name": "C", "current_hp": 20, "max_hp": 100}
            ]
        )
        low_hp = state.get_low_hp_pokemon()
        assert len(low_hp) == 2

    def test_to_dict(self):
        state = GameState(location="Pallet Town", badges=1, money=3000)
        result = state.to_dict()
        assert result["location"] == "Pallet Town"
        assert result["badges"] == 1
        assert result["money"] == 3000
        assert "is_battle" in result

    def test_to_state_dict(self):
        state = GameState(
            party=[
                {"name": "Pikachu", "level": 5, "current_hp": 35, "max_hp": 35}
            ]
        )
        result = state.to_state_dict()
        assert result["location"] == ""
        assert "avg_party_level" in result
        assert result["avg_party_level"] == 5.0


class TestGoal:
    """Tests for base Goal class"""

    def test_goal_creation(self):
        goal = Goal(
            goal_id="test-1",
            name="Test Goal",
            description="A test goal",
            goal_type=GoalType.SHORT_TERM,
            priority=50
        )
        assert goal.goal_id == "test-1"
        assert goal.name == "Test Goal"
        assert goal.status == "PENDING"
        assert goal.progress == 0.0

    def test_goal_auto_id(self):
        goal = Goal(
            name="Test Goal",
            description="A test goal",
            goal_type=GoalType.IMMEDIATE,
            priority=100
        )
        assert goal.goal_id is not None
        assert len(goal.goal_id) > 0

    def test_is_feasible_no_requirements(self):
        goal = Goal(
            name="Test Goal",
            description="A test goal",
            goal_type=GoalType.IMMEDIATE,
            priority=50
        )
        state = GameState()
        feasible, missing = goal.is_feasible(state)
        assert feasible is True
        assert missing == {}

    def test_is_feasible_with_money_requirement(self):
        goal = Goal(
            name="Buy Potion",
            description="Buy a potion",
            goal_type=GoalType.SHORT_TERM,
            priority=50,
            required_resources={"money": 500}
        )
        state = GameState(money=300)
        feasible, missing = goal.is_feasible(state)
        assert feasible is False
        assert missing["money"] == 200

    def test_is_feasible_with_sufficient_money(self):
        goal = Goal(
            name="Buy Potion",
            description="Buy a potion",
            goal_type=GoalType.SHORT_TERM,
            priority=50,
            required_resources={"money": 500}
        )
        state = GameState(money=1000)
        feasible, missing = goal.is_feasible(state)
        assert feasible is True

    def test_is_feasible_with_level_requirement(self):
        goal = Goal(
            name="Defeat Gym",
            description="Defeat a gym",
            goal_type=GoalType.MEDIUM_TERM,
            priority=80,
            required_resources={"level": 12}
        )
        state = GameState(party=[{"level": 5}])
        feasible, missing = goal.is_feasible(state)
        assert feasible is False

    def test_calculate_utility(self):
        goal = Goal(
            name="Test Goal",
            description="A test goal",
            goal_type=GoalType.SHORT_TERM,
            priority=50,
            estimated_cost=100.0,
            estimated_value=200.0
        )
        state = GameState()
        utility = goal.calculate_utility(state)
        assert utility == 100.0


class TestDefeatGymGoal:
    """Tests for DefeatGymGoal"""

    def test_creation(self):
        goal = DefeatGymGoal(
            gym_name="Pewter City",
            gym_leader="Brock",
            required_badges=0,
            required_level=12
        )
        assert goal.gym_name == "Pewter City"
        assert goal.gym_leader == "Brock"
        assert goal.goal_type == GoalType.MEDIUM_TERM
        assert goal.priority == 80
        assert goal.required_resources["badges"] == 0
        assert goal.required_resources["level"] == 12

    def test_description(self):
        goal = DefeatGymGoal(gym_name="Cerulean City", gym_leader="Misty")
        assert "Misty" in goal.description
        assert "Cerulean City" in goal.description


class TestCatchPokemonGoal:
    """Tests for CatchPokemonGoal"""

    def test_creation(self):
        goal = CatchPokemonGoal(species="Pikachu", min_level=5, max_level=20)
        assert goal.species == "Pikachu"
        assert goal.min_level == 5
        assert goal.max_level == 20
        assert goal.location is None

    def test_creation_with_location(self):
        goal = CatchPokemonGoal(species="Pikachu", location="Route 1")
        assert goal.location == "Route 1"

    def test_is_feasible_wrong_location(self):
        goal = CatchPokemonGoal(species="Pikachu", location="Route 22")
        state = GameState(location="Route 1")
        feasible, missing = goal.is_feasible(state)
        assert feasible is False
        assert "location" in missing


class TestHealPartyGoal:
    """Tests for HealPartyGoal"""

    def test_creation_normal(self):
        goal = HealPartyGoal(urgency="normal")
        assert goal.urgency == "normal"
        assert goal.priority == 70

    def test_creation_critical(self):
        goal = HealPartyGoal(urgency="critical")
        assert goal.urgency == "critical"
        assert goal.priority == 95


class TestTrainPokemonGoal:
    """Tests for TrainPokemonGoal"""

    def test_creation(self):
        goal = TrainPokemonGoal(target_level=15, training_location="Route 22")
        assert goal.target_level == 15
        assert goal.training_location == "Route 22"
        assert goal.required_resources["level"] == 15


class TestObtainItemGoal:
    """Tests for ObtainItemGoal"""

    def test_creation_buy(self):
        goal = ObtainItemGoal(item_name="Poke Ball", quantity=10, buy=True, target_price=200)
        assert goal.item_name == "Poke Ball"
        assert goal.quantity == 10
        assert goal.buy is True
        assert goal.required_resources["money"] == 200

    def test_creation_find(self):
        goal = ObtainItemGoal(item_name="HM01", buy=False)
        assert goal.buy is False

    def test_priority_critical_items(self):
        goal = ObtainItemGoal(item_name="Poke Ball")
        assert goal.priority == 90


class TestAction:
    """Tests for base Action class"""

    def test_action_creation(self):
        action = NavigateAction("Route 1")
        assert action.action_id is not None
        assert action.status == "PENDING"
        assert action.progress == 0.0
        assert action.retry_count == 0

    def test_can_execute_default(self):
        action = NavigateAction("Route 1")
        state = GameState()
        assert action.can_execute(state) is True


class TestNavigateAction:
    """Tests for NavigateAction"""

    def test_creation(self):
        action = NavigateAction(target_location="Pewter City", method="astar")
        assert action.target_location == "Pewter City"
        assert action.method == "astar"
        assert action.action_type == ActionType.NAVIGATION

    def test_get_preconditions(self):
        action = NavigateAction("Route 1")
        preconditions = action.get_preconditions()
        assert "not_in_battle" in preconditions

    def test_get_effects(self):
        action = NavigateAction("Pewter City")
        effects = action.get_effects()
        assert effects["location"] == "Pewter City"

    def test_get_cost(self):
        action = NavigateAction("Route 1")
        assert action.get_cost() == 10.0

    def test_can_execute_in_battle(self):
        action = NavigateAction("Route 1")
        state = GameState()
        state.is_battle = True
        assert action.can_execute(state) is False


class TestBattleAction:
    """Tests for BattleAction"""

    def test_creation(self):
        action = BattleAction(battle_type="wild", target="Pikachu", strategy="catch")
        assert action.battle_type == "wild"
        assert action.target == "Pikachu"
        assert action.strategy == "catch"
        assert action.action_type == ActionType.BATTLE

    def test_get_preconditions(self):
        action = BattleAction()
        preconditions = action.get_preconditions()
        assert "in_battle" in preconditions

    def test_can_execute_not_in_battle(self):
        action = BattleAction()
        state = GameState()
        assert action.can_execute(state) is False


class TestMenuAction:
    """Tests for MenuAction"""

    def test_creation(self):
        action = MenuAction(menu_type="shop", action="buy", target="Potion", quantity=3)
        assert action.menu_type == "shop"
        assert action.action == "buy"
        assert action.target == "Potion"
        assert action.quantity == 3

    def test_get_effects_shop(self):
        action = MenuAction("shop", "buy", "Potion", 2)
        effects = action.get_effects()
        assert effects["item_obtained"] == "Potion"

    def test_get_effects_heal(self):
        action = MenuAction("pokemon_center", "heal")
        effects = action.get_effects()
        assert effects["party_healed"] is True


class TestDialogAction:
    """Tests for DialogAction"""

    def test_creation(self):
        action = DialogAction(npc_name="Professor Oak", dialog_type="talk")
        assert action.npc_name == "Professor Oak"
        assert action.dialog_type == "talk"
        assert action.action_type == ActionType.DIALOG

    def test_get_preconditions(self):
        action = DialogAction("Nurse Joy")
        preconditions = action.get_preconditions()
        assert "not_in_battle" in preconditions


class TestPlan:
    """Tests for Plan class"""

    def test_creation(self):
        actions = [NavigateAction("Route 1"), BattleAction()]
        plan = Plan(plan_id="plan-1", goal_id="goal-1", actions=actions)
        assert plan.plan_id == "plan-1"
        assert plan.goal_id == "goal-1"
        assert len(plan.actions) == 2
        assert plan.status == PlanStatus.PENDING
        assert plan.current_action_index == 0

    def test_get_current_action(self):
        actions = [NavigateAction("Route 1")]
        plan = Plan(plan_id="plan-1", goal_id="goal-1", actions=actions)
        assert plan.get_current_action() == actions[0]

    def test_get_current_action_complete(self):
        actions = [NavigateAction("Route 1")]
        plan = Plan(plan_id="plan-1", goal_id="goal-1", actions=actions)
        plan.current_action_index = 1
        assert plan.get_current_action() is None

    def test_is_complete(self):
        actions = [NavigateAction("Route 1")]
        plan = Plan(plan_id="plan-1", goal_id="goal-1", actions=actions)
        assert plan.is_complete() is False
        plan.current_action_index = 1
        assert plan.is_complete() is True

    def test_total_cost(self):
        actions = [NavigateAction("Route 1"), NavigateAction("Route 2"), BattleAction()]
        plan = Plan(plan_id="plan-1", goal_id="goal-1", actions=actions)
        assert plan.total_cost == 25.0


class TestGoalStack:
    """Tests for GoalStack"""

    def test_creation(self):
        stack = GoalStack()
        assert stack.is_empty()

    def test_push_and_pop(self):
        stack = GoalStack()
        goal1 = Goal(name="Goal 1", description="", goal_type=GoalType.SHORT_TERM, priority=50)
        goal2 = Goal(name="Goal 2", description="", goal_type=GoalType.SHORT_TERM, priority=60)

        stack.push(goal1)
        stack.push(goal2)

        popped = stack.pop()
        assert popped == goal2

    def test_push_duplicate_updates_priority(self):
        stack = GoalStack()
        goal1 = Goal(name="Goal", description="", goal_type=GoalType.SHORT_TERM, priority=50)
        goal2 = Goal(name="Goal", description="", goal_type=GoalType.SHORT_TERM, priority=80)

        stack.push(goal1)
        stack.push(goal2)

        assert stack.peek().priority == 80

    def test_remove(self):
        stack = GoalStack()
        goal = Goal(goal_id="goal-1", name="Goal", description="", goal_type=GoalType.SHORT_TERM, priority=50)
        stack.push(goal)
        assert stack.remove("goal-1")
        assert stack.is_empty()
        assert not stack.remove("nonexistent")

    def test_get_all_goals_sorted(self):
        stack = GoalStack()
        goal1 = Goal(name="Low", description="", goal_type=GoalType.SHORT_TERM, priority=30)
        goal2 = Goal(name="High", description="", goal_type=GoalType.IMMEDIATE, priority=90)
        goal3 = Goal(name="Medium", description="", goal_type=GoalType.SHORT_TERM, priority=60)

        stack.push(goal1)
        stack.push(goal2)
        stack.push(goal3)

        goals = stack.get_all_goals()
        assert goals[0].name == "High"


class TestGoalDAG:
    """Tests for GoalDAG"""

    def test_creation(self):
        dag = GoalDAG()
        assert len(dag.nodes) == 0
        assert len(dag.edges) == 0

    def test_add_goal(self):
        dag = GoalDAG()
        goal = Goal(goal_id="g1", name="Goal 1", description="", goal_type=GoalType.SHORT_TERM, priority=50)
        dag.add_goal(goal)
        assert "g1" in dag.nodes

    def test_add_prerequisite(self):
        dag = GoalDAG()
        goal1 = Goal(goal_id="g1", name="Goal 1", description="", goal_type=GoalType.SHORT_TERM, priority=50)
        goal2 = Goal(goal_id="g2", name="Goal 2", description="", goal_type=GoalType.MEDIUM_TERM, priority=60)
        dag.add_goal(goal1)
        dag.add_goal(goal2)
        dag.add_prerequisite("g2", "g1")

        prereqs = dag.get_prerequisites("g2")
        assert "g1" in prereqs

    def test_get_dependents(self):
        dag = GoalDAG()
        goal1 = Goal(goal_id="g1", name="Goal 1", description="", goal_type=GoalType.SHORT_TERM, priority=50)
        goal2 = Goal(goal_id="g2", name="Goal 2", description="", goal_type=GoalType.MEDIUM_TERM, priority=60)
        dag.add_goal(goal1)
        dag.add_goal(goal2)
        dag.add_prerequisite("g2", "g1")

        dependents = dag.get_dependents("g1")
        assert "g2" in dependents

    def test_topological_sort(self):
        dag = GoalDAG()
        goal1 = Goal(goal_id="g1", name="Goal 1", description="", goal_type=GoalType.SHORT_TERM, priority=50)
        goal2 = Goal(goal_id="g2", name="Goal 2", description="", goal_type=GoalType.SHORT_TERM, priority=60)
        goal3 = Goal(goal_id="g3", name="Goal 3", description="", goal_type=GoalType.SHORT_TERM, priority=70)
        dag.add_goal(goal1)
        dag.add_goal(goal2)
        dag.add_goal(goal3)
        dag.add_prerequisite("g2", "g1")
        dag.add_prerequisite("g3", "g2")

        sorted_goals = dag._topological_sort()
        assert sorted_goals.index("g1") < sorted_goals.index("g2")
        assert sorted_goals.index("g2") < sorted_goals.index("g3")


class TestPriorityQueue:
    """Tests for PriorityQueue"""

    def test_creation(self):
        pq = PriorityQueue()
        assert pq.is_empty()

    def test_push_and_pop(self):
        pq = PriorityQueue()
        goal1 = Goal(name="Low", description="", goal_type=GoalType.SHORT_TERM, priority=30)
        goal2 = Goal(name="High", description="", goal_type=GoalType.SHORT_TERM, priority=90)

        pq.push(goal1, 30)
        pq.push(goal2, 90)

        popped = pq.pop()
        assert popped == goal2

    def test_update_priority(self):
        pq = PriorityQueue()
        goal = Goal(goal_id="g1", name="Goal", description="", goal_type=GoalType.SHORT_TERM, priority=50)
        pq.push(goal, 50)

        result = pq.update_priority("g1", 80)
        assert result is True

        popped = pq.pop()
        assert popped.priority == 80


class TestGoalPriorityCalculator:
    """Tests for GoalPriorityCalculator"""

    def test_creation(self):
        calc = GoalPriorityCalculator()
        assert len(calc.success_history) == 0

    def test_calculate_priority_basic(self):
        calc = GoalPriorityCalculator()
        goal = Goal(name="Test", description="", goal_type=GoalType.SHORT_TERM, priority=50)
        state = GameState()
        priority = calc.calculate_priority(goal, state)
        assert priority > 0

    def test_temporal_multiplier(self):
        calc = GoalPriorityCalculator()
        goal = Goal(name="Test", description="", goal_type=GoalType.IMMEDIATE, priority=50,
                    deadline=datetime.now() + timedelta(seconds=30))
        state = GameState()
        priority = calc.calculate_priority(goal, state)
        assert priority > 50

    def test_record_success(self):
        calc = GoalPriorityCalculator()
        goal = Goal(name="Test", description="", goal_type=GoalType.SHORT_TERM, priority=50)
        calc.record_success(goal, True)
        calc.record_success(goal, True)
        calc.record_success(goal, False)
        assert calc.success_history["SHORT_TERM"] == [2, 3]


class TestGoalPrioritizer:
    """Tests for GoalPrioritizer"""

    def test_creation(self):
        prioritizer = GoalPrioritizer()
        assert prioritizer.calculator is not None
        assert prioritizer.priority_queue is not None

    def test_add_goal(self):
        prioritizer = GoalPrioritizer()
        goal = DefeatGymGoal(gym_name="Pewter City", gym_leader="Brock")
        state = GameState(party=[{"level": 15}])
        prioritizer.add_goal(goal, state)

        assert len(prioritizer.goal_dag.nodes) == 1
        assert not prioritizer.priority_queue.is_empty()

    def test_select_next_goal(self):
        prioritizer = GoalPrioritizer()
        goal1 = HealPartyGoal()
        goal2 = DefeatGymGoal(gym_name="Pewter City", gym_leader="Brock")
        state = GameState(party=[{"level": 15}])

        prioritizer.add_goal(goal1, state)
        prioritizer.add_goal(goal2, state)

        selected = prioritizer.select_next_goal(state)
        assert selected is not None


class TestPlanner:
    """Tests for Planner"""

    def test_creation(self):
        prioritizer = GoalPrioritizer()
        planner = Planner(prioritizer)
        assert planner.goal_prioritizer == prioritizer

    def test_create_plan_gym(self):
        prioritizer = GoalPrioritizer()
        planner = Planner(prioritizer)
        goal = DefeatGymGoal(gym_name="Pewter City", gym_leader="Brock", required_level=12)
        state = GameState(party=[{"level": 15}])

        plan = planner.create_plan(goal, state)
        assert len(plan.actions) >= 2
        assert plan.goal_id == goal.goal_id

    def test_create_plan_heal(self):
        prioritizer = GoalPrioritizer()
        planner = Planner(prioritizer)
        goal = HealPartyGoal()
        state = GameState()

        plan = planner.create_plan(goal, state)
        assert len(plan.actions) == 2

    def test_validate_plan(self):
        prioritizer = GoalPrioritizer()
        planner = Planner(prioritizer)
        goal = HealPartyGoal()
        state = GameState()

        plan = planner.create_plan(goal, state)
        valid, errors = planner.validate_plan(plan, state)
        assert valid is True


class TestPlanMonitor:
    """Tests for PlanMonitor"""

    def test_creation(self):
        prioritizer = GoalPrioritizer()
        planner = Planner(prioritizer)
        monitor = PlanMonitor(planner)
        assert monitor.replan_count == 0
        assert monitor.failure_count == 0

    def test_monitor_execution_success(self):
        prioritizer = GoalPrioritizer()
        planner = Planner(prioritizer)
        monitor = PlanMonitor(planner)

        goal = HealPartyGoal()
        state = GameState()
        plan = planner.create_plan(goal, state)

        success, new_plan = monitor.monitor_execution(plan, state)
        assert success is False
        assert new_plan is None
        assert plan.current_action_index == 1

    def test_monitor_execution_complete(self):
        prioritizer = GoalPrioritizer()
        planner = Planner(prioritizer)
        monitor = PlanMonitor(planner)

        goal = HealPartyGoal()
        state = GameState()
        plan = planner.create_plan(goal, state)
        plan.current_action_index = len(plan.actions) - 1

        success, new_plan = monitor.monitor_execution(plan, state)
        assert success is True

    def test_handle_interruption_random_battle(self):
        prioritizer = GoalPrioritizer()
        planner = Planner(prioritizer)
        monitor = PlanMonitor(planner)

        state = GameState()
        success, new_plan = monitor.handle_interruption("random_battle", state)
        assert success is True

    def test_handle_interruption_low_hp(self):
        prioritizer = GoalPrioritizer()
        planner = Planner(prioritizer)
        monitor = PlanMonitor(planner)

        state = GameState()
        success, new_plan = monitor.handle_interruption("low_hp", state)
        assert success is False
        assert new_plan is not None

    def test_get_statistics(self):
        prioritizer = GoalPrioritizer()
        planner = Planner(prioritizer)
        monitor = PlanMonitor(planner)

        stats = monitor.get_statistics()
        assert "total_executions" in stats
        assert "replan_count" in stats
        assert "failure_count" in stats


class TestHierarchicalPlanner:
    """Tests for HierarchicalPlanner"""

    def test_creation(self):
        planner = HierarchicalPlanner()
        assert planner.goal_prioritizer is not None
        assert planner.planner is not None
        assert planner.plan_monitor is not None

    def test_plan_generates_plan(self):
        planner = HierarchicalPlanner()
        state = GameState(party=[{"level": 15}])
        goal = HealPartyGoal()

        planner.add_goal(goal, state)
        plan = planner.plan(state)

        assert plan is not None
        assert len(plan.actions) >= 1

    def test_execute_step(self):
        planner = HierarchicalPlanner()
        state = GameState(party=[{"level": 15}])
        goal = HealPartyGoal()

        planner.add_goal(goal, state)
        plan = planner.plan(state)

        success, new_plan, new_state = planner.execute_step(state)
        assert success is False
        assert new_plan is not None

    def test_get_status(self):
        planner = HierarchicalPlanner()
        status = planner.get_status()
        assert "current_plan" in status
        assert "goals_in_queue" in status
        assert "monitor_stats" in status


class TestFactoryFunctions:
    """Tests for factory functions"""

    def test_create_default_game_state(self):
        state = create_default_game_state()
        assert state.location == "Pallet Town"
        assert state.money == 3000
        assert len(state.party) == 1
        assert state.party[0]["name"] == "Pikachu"

    def test_create_goap_system(self):
        system = create_goap_system()
        assert isinstance(system, HierarchicalPlanner)


class TestEdgeCases:
    """Tests for edge cases and error conditions"""

    def test_empty_stack_pop(self):
        stack = GoalStack()
        result = stack.pop()
        assert result is None

    def test_empty_stack_peek(self):
        stack = GoalStack()
        result = stack.peek()
        assert result is None

    def test_empty_queue_pop(self):
        pq = PriorityQueue()
        result = pq.pop()
        assert result is None

    def test_goal_stack_max_size(self):
        stack = GoalStack(max_size=3)
        for i in range(5):
            stack.push(Goal(name=f"Goal {i}", description="", goal_type=GoalType.SHORT_TERM, priority=50))
        assert len(stack.stack) == 3

    def test_invalid_priority_update(self):
        pq = PriorityQueue()
        result = pq.update_priority("nonexistent", 100)
        assert result is False

    def test_plan_with_no_actions(self):
        plan = Plan(plan_id="p1", goal_id="g1", actions=[])
        assert plan.is_complete()

    def test_action_max_retries(self):
        action = NavigateAction("Route 1")
        action.retry_count = 3
        action.max_retries = 3
        assert action.retry_count >= action.max_retries


if __name__ == "__main__":
    pytest.main([__file__, "-v"])