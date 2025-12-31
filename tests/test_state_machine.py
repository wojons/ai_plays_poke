"""
Tests for Hierarchical State Machine (HSM) module
"""

import pytest
import time
from src.core.state_machine import (
    HierarchicalStateMachine,
    State,
    StateType,
    BootSubState,
    TitleSubState,
    MenuSubState,
    DialogSubState,
    OverworldSubState,
    BattleSubState,
    EmergencySubState,
    StateTransition,
    StateTransitionResult,
    create_hierarchical_state_machine,
)


@pytest.fixture
def fresh_hsm():
    """Create a fresh HSM for each test"""
    hsm = create_hierarchical_state_machine()
    return hsm


@pytest.fixture
def bootstrapped_hsm(fresh_hsm):
    """Create an HSM that has completed the bootstrap sequence"""
    for state in ["BOOT.TITLE_SCREEN", "BOOT.PRESS_START", "BOOT.SELECT_GAME_MODE",
                  "BOOT.NEW_GAME", "BOOT.CHARACTER_NAMING", "BOOT.CONFIGURE_OPTIONS",
                  "BOOT.INITIALIZE_CLOCK", "BOOT.BOOT_COMPLETE", "OVERWORLD.IDLE"]:
        fresh_hsm.transition_to(state)
    return fresh_hsm


class TestStateBaseClass:
    """Tests for the base State class"""

    def test_state_creation(self):
        """Test State can be created with name and type"""
        state = State("TEST", StateType.OVERWORLD)
        assert state.name == "TEST"
        assert state.state_type == StateType.OVERWORLD
        assert state.parent is None
        assert state.is_active is False

    def test_state_hierarchy(self):
        """Test parent-child state relationships"""
        parent = State("PARENT", StateType.OVERWORLD)
        child = State("PARENT.CHILD", StateType.OVERWORLD)

        parent.add_child(child)
        assert child.parent == parent
        assert child in parent.children

    def test_state_full_path(self):
        """Test state full path calculation"""
        state = State("PARENT.CHILD.GRANDCHILD", StateType.BOOT)
        assert state.get_full_path() == "PARENT.CHILD.GRANDCHILD"


class TestHierarchicalStateMachine:
    """Tests for the HierarchicalStateMachine class"""

    def test_hsm_creation(self, fresh_hsm):
        """Test HSM can be created and initialized"""
        assert fresh_hsm.name == "PTP-01X-HSM"
        assert fresh_hsm.get_current_state() is not None

    def test_hsm_factory(self, fresh_hsm):
        """Test factory function creates HSM with all states"""
        stats = fresh_hsm.get_statistics()
        assert stats["total_states"] >= 69  # 7 parent states + sub-states

    def test_initial_state_transition(self, fresh_hsm):
        """Test HSM transitions to initial state on reset/create"""
        assert fresh_hsm.get_current_state_name() == "BOOT.INITIALIZE"

    def test_bootstrap_sequence(self, fresh_hsm):
        """Test complete bootstrap sequence transitions"""
        bootstrap_path = [
            "BOOT.INITIALIZE",
            "BOOT.TITLE_SCREEN",
            "BOOT.PRESS_START",
            "BOOT.SELECT_GAME_MODE",
            "BOOT.NEW_GAME",
            "BOOT.CHARACTER_NAMING",
            "BOOT.CONFIGURE_OPTIONS",
            "BOOT.INITIALIZE_CLOCK",
            "BOOT.BOOT_COMPLETE",
            "OVERWORLD.IDLE",
        ]

        for state in bootstrap_path:
            result = fresh_hsm.transition_to(state)
            assert result == StateTransitionResult.SUCCESS, f"Failed to transition to {state}"

        assert fresh_hsm.get_current_state_name() == "OVERWORLD.IDLE"

    def test_overworld_transitions(self, bootstrapped_hsm):
        """Test overworld state transitions"""
        assert bootstrapped_hsm.is_in_battle() is False

        bootstrapped_hsm.transition_to("OVERWORLD.WALKING")
        assert bootstrapped_hsm.get_current_state_name() == "OVERWORLD.WALKING"

        bootstrapped_hsm.transition_to("OVERWORLD.RUNNING")
        assert bootstrapped_hsm.get_current_state_name() == "OVERWORLD.RUNNING"

        bootstrapped_hsm.transition_to("OVERWORLD.IDLE")

    def test_battle_transitions(self, bootstrapped_hsm):
        """Test battle state transitions"""
        bootstrapped_hsm.transition_to("BATTLE.BATTLE_INTRO")

        assert bootstrapped_hsm.is_in_battle() is True

        battle_path = [
            "BATTLE.BATTLE_MENU",
            "BATTLE.MOVE_SELECTION",
            "BATTLE.TARGET_SELECTION",
            "BATTLE.BATTLE_ANIMATION",
            "BATTLE.BATTLE_MESSAGE",
            "BATTLE.BATTLE_RESULT",
            "BATTLE.BATTLE_END",
        ]

        for state in battle_path:
            result = bootstrapped_hsm.transition_to(state)
            assert result == StateTransitionResult.SUCCESS, f"Failed to transition to {state}: {result}"

        bootstrapped_hsm.transition_to("OVERWORLD.IDLE")
        assert bootstrapped_hsm.is_in_battle() is False

    def test_menu_transitions(self, bootstrapped_hsm):
        """Test menu state transitions"""
        bootstrapped_hsm.transition_to("MENU.MAIN_MENU")

        assert bootstrapped_hsm.is_in_menu() is True

        bootstrapped_hsm.transition_to("MENU.POKEMON_MENU")
        bootstrapped_hsm.transition_to("MENU.MAIN_MENU")
        bootstrapped_hsm.transition_to("MENU.INVENTORY")
        bootstrapped_hsm.transition_to("OVERWORLD.IDLE")

        assert bootstrapped_hsm.is_in_menu() is False

    def test_dialog_transitions(self, bootstrapped_hsm):
        """Test dialog state transitions"""
        bootstrapped_hsm.transition_to("DIALOG.TEXT_DISPLAY")

        assert bootstrapped_hsm.is_in_dialog() is True

        bootstrapped_hsm.transition_to("DIALOG.AWAITING_INPUT")
        bootstrapped_hsm.transition_to("DIALOG.TEXT_COMPLETE")
        bootstrapped_hsm.transition_to("OVERWORLD.IDLE")

        assert bootstrapped_hsm.is_in_dialog() is False

    def test_invalid_transitions_blocked(self, fresh_hsm):
        """Test that invalid transitions are blocked"""
        fresh_hsm.transition_to("BOOT.TITLE_SCREEN")

        result = fresh_hsm.transition_to("OVERWORLD.IDLE")
        assert result == StateTransitionResult.INVALID_TRANSITION
        assert fresh_hsm.get_current_state_name() == "BOOT.TITLE_SCREEN"

    def test_emergency_interrupt(self, fresh_hsm):
        """Test emergency interrupt handling"""
        fresh_hsm.trigger_emergency("Test softlock")

        assert fresh_hsm.is_emergency() is True
        assert fresh_hsm.get_current_state_name() == "EMERGENCY.SOFTLOCK_DETECTED"

        stats = fresh_hsm.get_statistics()
        assert stats["emergency_triggered"] is True
        assert stats["emergency_reason"] == "Test softlock"

    def test_emergency_recovery(self, fresh_hsm):
        """Test recovering from emergency state"""
        fresh_hsm.trigger_emergency("Test")
        assert fresh_hsm.is_emergency() is True

        fresh_hsm.clear_emergency()
        result = fresh_hsm.transition_to("OVERWORLD.IDLE", reason="Recovery")
        assert result == StateTransitionResult.SUCCESS
        assert fresh_hsm.is_emergency() is False
        assert fresh_hsm.get_current_state_name() == "OVERWORLD.IDLE"

    def test_state_history(self, fresh_hsm):
        """Test state transition history is recorded"""
        fresh_hsm.transition_to("BOOT.TITLE_SCREEN")
        fresh_hsm.transition_to("BOOT.PRESS_START")

        history = fresh_hsm.get_state_history()
        assert len(history) >= 2

        for transition in history:
            assert isinstance(transition, StateTransition)
            assert transition.from_state is not None
            assert transition.to_state is not None
            assert transition.timestamp is not None

    def test_transition_counting(self, fresh_hsm):
        """Test transition counts are tracked"""
        fresh_hsm.transition_to("BOOT.TITLE_SCREEN")
        fresh_hsm.transition_to("BOOT.PRESS_START")
        fresh_hsm.transition_to("BOOT.TITLE_SCREEN")

        count = fresh_hsm.get_transition_count("BOOT.TITLE_SCREEN", "BOOT.PRESS_START")
        assert count >= 1

    def test_state_stack_push_pop(self, bootstrapped_hsm):
        """Test state stack for interrupt handling"""
        bootstrapped_hsm.transition_to("DIALOG.TEXT_DISPLAY")

        bootstrapped_hsm.push_state("DIALOG.CHOICE_MENU")
        assert bootstrapped_hsm.get_current_state_name() == "DIALOG.CHOICE_MENU"

        popped = bootstrapped_hsm.pop_state()
        assert popped is not None
        assert bootstrapped_hsm.get_current_state_name() == "DIALOG.TEXT_DISPLAY"

    def test_update_method(self, fresh_hsm):
        """Test HSM update method"""
        initial_state = fresh_hsm.get_current_state_name()
        updated_state = fresh_hsm.update()

        assert updated_state is not None
        stats = fresh_hsm.get_statistics()
        assert stats["total_ticks"] >= 1

    def test_callbacks(self, fresh_hsm):
        """Test transition and emergency callbacks"""
        transition_called = []
        emergency_called = []

        def on_transition(from_state, to_state):
            transition_called.append((from_state, to_state))

        def on_emergency(reason):
            emergency_called.append(reason)

        fresh_hsm.register_transition_callback(on_transition)
        fresh_hsm.register_emergency_callback(on_emergency)

        fresh_hsm.transition_to("BOOT.TITLE_SCREEN")
        fresh_hsm.trigger_emergency("Test")

        assert len(transition_called) >= 1
        assert len(emergency_called) == 1
        assert emergency_called[0] == "Test"

    def test_statistics(self, fresh_hsm):
        """Test HSM statistics generation"""
        fresh_hsm.transition_to("BOOT.TITLE_SCREEN")
        fresh_hsm.transition_to("BOOT.PRESS_START")

        stats = fresh_hsm.get_statistics()

        assert "current_state" in stats
        assert "previous_state" in stats
        assert "total_ticks" in stats
        assert "transition_count" in stats
        assert "total_states" in stats

    def test_reset(self, fresh_hsm):
        """Test HSM reset functionality"""
        fresh_hsm.transition_to("BOOT.TITLE_SCREEN")
        fresh_hsm.transition_to("BOOT.PRESS_START")

        fresh_hsm.reset()

        assert fresh_hsm.get_current_state_name() == "BOOT.INITIALIZE"

    def test_available_transitions(self, fresh_hsm):
        """Test getting available transitions from current state"""
        fresh_hsm.transition_to("BOOT.INITIALIZE")

        available = fresh_hsm.get_available_transitions()
        assert "BOOT.TITLE_SCREEN" in available

    def test_is_in_methods(self, bootstrapped_hsm):
        """Test is_in_* helper methods"""
        assert bootstrapped_hsm.is_in_battle() is False
        assert bootstrapped_hsm.is_in_menu() is False
        assert bootstrapped_hsm.is_in_dialog() is False
        assert bootstrapped_hsm.is_emergency() is False

        bootstrapped_hsm.transition_to("BATTLE.BATTLE_INTRO")
        assert bootstrapped_hsm.is_in_battle() is True

        bootstrapped_hsm.transition_to("BATTLE.BATTLE_END")
        bootstrapped_hsm.transition_to("MENU.MAIN_MENU")
        assert bootstrapped_hsm.is_in_menu() is True

    def test_battle_interrupt_from_overworld(self, bootstrapped_hsm):
        """Test battle can interrupt overworld navigation"""
        bootstrapped_hsm.transition_to("OVERWORLD.WALKING")

        result = bootstrapped_hsm.transition_to("BATTLE.BATTLE_INTRO", reason="Random encounter")
        assert result == StateTransitionResult.SUCCESS
        assert bootstrapped_hsm.is_in_battle() is True

    def test_dialog_interrupt_from_overworld(self, bootstrapped_hsm):
        """Test dialog can interrupt overworld navigation"""
        bootstrapped_hsm.transition_to("OVERWORLD.INTERACTING_SIGN")

        result = bootstrapped_hsm.transition_to("DIALOG.TEXT_DISPLAY", reason="Sign text")
        assert result == StateTransitionResult.SUCCESS
        assert bootstrapped_hsm.is_in_dialog() is True


class TestStateEnums:
    """Tests for state enum definitions"""

    def test_boot_substates(self):
        """Test all bootstrap sub-states exist"""
        expected = [
            "INITIALIZE", "TITLE_SCREEN", "PRESS_START", "DETECT_CONTINUE",
            "SELECT_GAME_MODE", "NEW_GAME", "CONTINUE_GAME", "VERIFY_SAVE",
            "CHARACTER_NAMING", "CONFIGURE_OPTIONS", "INITIALIZE_CLOCK",
            "BOOT_COMPLETE", "HANDLE_CORRUPT_SAVE"
        ]
        actual = [s.name for s in BootSubState]
        for exp in expected:
            assert exp in actual

    def test_overworld_substates(self):
        """Test all overworld sub-states exist"""
        expected = [
            "IDLE", "WALKING", "RUNNING", "SURFING", "FLYING", "BIKING", "FISHING",
            "APPROACHING_NPC", "INTERACTING_SIGN", "FACING_DOOR", "INTERACTION_ZONE",
            "CENTER_HEAL", "MART_SHOPPING"
        ]
        actual = [s.name for s in OverworldSubState]
        for exp in expected:
            assert exp in actual

    def test_battle_substates(self):
        """Test all battle sub-states exist"""
        expected = [
            "BATTLE_INTRO", "BATTLE_MENU", "MOVE_SELECTION", "TARGET_SELECTION",
            "BATTLE_ANIMATION", "BATTLE_MESSAGE", "BATTLE_RESULT", "BATTLE_END",
            "SWITCH_POKEMON", "USE_ITEM", "CATCH_ATTEMPT"
        ]
        actual = [s.name for s in BattleSubState]
        for exp in expected:
            assert exp in actual

    def test_menu_substates(self):
        """Test all menu sub-states exist"""
        expected = [
            "MAIN_MENU", "POKEMON_MENU", "INVENTORY", "SAVE_MENU", "OPTIONS",
            "PC_MENU", "TRAINER_CARD", "CONTEXT_MENU"
        ]
        actual = [s.name for s in MenuSubState]
        for exp in expected:
            assert exp in actual

    def test_dialog_substates(self):
        """Test all dialog sub-states exist"""
        expected = [
            "TEXT_DISPLAY", "CHOICE_MENU", "YES_NO_MENU", "TEXT_COMPLETE", "AWAITING_INPUT"
        ]
        actual = [s.name for s in DialogSubState]
        for exp in expected:
            assert exp in actual

    def test_emergency_substates(self):
        """Test all emergency sub-states exist"""
        expected = [
            "NORMAL_OPERATION", "SOFTLOCK_DETECTED", "ERROR_RECOVERY",
            "EMERGENCY_SHUTDOWN", "GAME_OVER", "BLACKOUT_RECOVERY",
            "MENU_ESCAPE", "PATH_BLOCKED", "LOW_RESOURCE"
        ]
        actual = [s.name for s in EmergencySubState]
        for exp in expected:
            assert exp in actual