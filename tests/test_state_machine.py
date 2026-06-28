"""
Unit tests for src/core/state_machine.py — enums, dataclasses, State base class,
HierarchicalStateMachine, GameStateClassifier, and factory function.
"""

import pytest
import time
from datetime import datetime

from src.core.state_machine import (
    StateType,
    BootSubState,
    TitleSubState,
    MenuSubState,
    DialogSubState,
    OverworldSubState,
    BattleSubState,
    EmergencySubState,
    StateTransitionResult,
    StateTransition,
    TransitionCondition,
    State,
    HierarchicalStateMachine,
    GameStateClassifier,
    create_hierarchical_state_machine,
)


# ── Enums ────────────────────────────────────────────────────────────────────

class TestStateType:
    def test_all_members(self):
        names = {m.name for m in StateType}
        assert "BOOT" in names
        assert "TITLE" in names
        assert "MENU" in names
        assert "DIALOG" in names
        assert "OVERWORLD" in names
        assert "BATTLE" in names
        assert "EMERGENCY" in names
        assert "TRANSITION" in names

    def test_values_distinct(self):
        vals = [m.value for m in StateType]
        assert len(vals) == len(set(vals))


class TestBootSubState:
    def test_member_count(self):
        assert len(list(BootSubState)) == 13

    def test_key_members(self):
        assert BootSubState.INITIALIZE is not None
        assert BootSubState.BOOT_COMPLETE is not None


class TestTitleSubState:
    def test_member_count(self):
        assert len(list(TitleSubState)) == 3

    def test_key_members(self):
        assert TitleSubState.SHOWING_LOGO is not None
        assert TitleSubState.GAME_MODE_MENU is not None


class TestMenuSubState:
    def test_member_count(self):
        assert len(list(MenuSubState)) == 8

    def test_key_members(self):
        assert MenuSubState.MAIN_MENU is not None
        assert MenuSubState.INVENTORY is not None


class TestDialogSubState:
    def test_member_count(self):
        assert len(list(DialogSubState)) == 5


class TestOverworldSubState:
    def test_member_count(self):
        assert len(list(OverworldSubState)) == 13


class TestBattleSubState:
    def test_member_count(self):
        assert len(list(BattleSubState)) == 11

    def test_key_members(self):
        assert BattleSubState.BATTLE_INTRO is not None
        assert BattleSubState.BATTLE_END is not None


class TestEmergencySubState:
    def test_member_count(self):
        assert len(list(EmergencySubState)) == 9

    def test_key_members(self):
        assert EmergencySubState.NORMAL_OPERATION is not None
        assert EmergencySubState.SOFTLOCK_DETECTED is not None


class TestStateTransitionResult:
    def test_all_values(self):
        assert StateTransitionResult.SUCCESS is not None
        assert StateTransitionResult.INVALID_TRANSITION is not None
        assert StateTransitionResult.STATE_NOT_FOUND is not None
        assert StateTransitionResult.CONDITION_FAILED is not None
        assert StateTransitionResult.EMERGENCY_INTERRUPT is not None

    def test_values_distinct(self):
        vals = [m.value for m in StateTransitionResult]
        assert len(vals) == len(set(vals))


# ── Dataclasses ──────────────────────────────────────────────────────────────

class TestStateTransition:
    def test_default_construction(self):
        st = StateTransition(from_state="A", to_state="B")
        assert st.from_state == "A"
        assert st.to_state == "B"
        assert isinstance(st.timestamp, datetime)
        assert st.tick == 0
        assert st.reason == ""
        assert st.duration_ms == 0.0

    def test_full_fields(self):
        now = datetime.now()
        st = StateTransition(
            from_state="OVERWORLD.IDLE", to_state="BATTLE.BATTLE_INTRO",
            timestamp=now, tick=5, reason="wild encounter", duration_ms=12.5,
        )
        assert st.from_state == "OVERWORLD.IDLE"
        assert st.to_state == "BATTLE.BATTLE_INTRO"
        assert st.timestamp == now
        assert st.tick == 5
        assert st.reason == "wild encounter"
        assert st.duration_ms == 12.5

    def test_default_timestamp(self):
        st1 = StateTransition(from_state="X", to_state="Y")
        st2 = StateTransition(from_state="X", to_state="Y")
        # both get current time; they should be very close
        diff = abs((st1.timestamp - st2.timestamp).total_seconds())
        assert diff < 1.0


class TestTransitionCondition:
    def test_construction(self):
        tc = TransitionCondition(name="hp_above_zero", check_func=lambda: True)
        assert tc.name == "hp_above_zero"
        assert tc.error_message == ""

    def test_with_error_message(self):
        tc = TransitionCondition(
            name="has_pokemon",
            check_func=lambda: False,
            error_message="No Pokémon in party",
        )
        assert tc.error_message == "No Pokémon in party"
        assert tc.check_func() is False


# ── State Base Class ─────────────────────────────────────────────────────────

class TestStateBase:
    def test_constructor(self):
        s = State("TEST", StateType.OVERWORLD)
        assert s.name == "TEST"
        assert s.state_type == StateType.OVERWORLD
        assert s.parent is None
        assert s.children == []
        assert s.is_active is False

    def test_parent_property(self):
        s = State("CHILD", StateType.BOOT)
        p = State("PARENT", StateType.BOOT)
        s.parent = p
        assert s.parent is p
        s.parent = None
        assert s.parent is None

    def test_entry_time_property(self):
        """Coverage: line 186"""
        s = State("T", StateType.MENU)
        assert s.entry_time is None
        s.on_enter()
        assert s.entry_time is not None
        assert s.entry_time > 0

    def test_tick_count_property(self):
        """Coverage: line 190"""
        s = State("T", StateType.DIALOG)
        assert s.tick_count == 0
        s.on_update(42)
        assert s.tick_count == 42

    def test_is_active_false_initially(self):
        s = State("T", StateType.BOOT)
        assert s.is_active is False

    def test_on_enter_sets_active_and_entry_time(self):
        s = State("T", StateType.OVERWORLD)
        s.on_enter()
        assert s.is_active is True
        assert s.entry_time is not None

    def test_on_exit_sets_inactive(self):
        s = State("T", StateType.OVERWORLD)
        s.on_enter()
        assert s.is_active
        s.on_exit()
        assert s.is_active is False

    def test_on_update_returns_none(self):
        s = State("T", StateType.MENU)
        result = s.on_update(10)
        assert result is None
        assert s.tick_count == 10

    def test_add_child(self):
        parent = State("P", StateType.BOOT)
        child = State("C", StateType.BOOT)
        parent.add_child(child)
        assert child.parent is parent
        assert child in parent.children

    def test_remove_child(self):
        """Coverage: lines 199-201"""
        parent = State("P", StateType.BOOT)
        child = State("C", StateType.BOOT)
        parent.add_child(child)
        assert child in parent.children
        parent.remove_child(child)
        assert child.parent is None
        assert child not in parent.children

    def test_remove_child_not_present(self):
        parent = State("P", StateType.BOOT)
        child = State("C", StateType.BOOT)
        # Should not raise
        parent.remove_child(child)

    def test_get_full_path(self):
        s = State("OVERWORLD.IDLE", StateType.OVERWORLD)
        assert s.get_full_path() == "OVERWORLD.IDLE"

    def test_get_available_transitions(self):
        """Coverage: line 229"""
        s = State("T", StateType.MENU)
        assert s.get_available_transitions() == set()

    def test_str(self):
        """Coverage: line 232"""
        s = State("OVERWORLD.IDLE", StateType.OVERWORLD)
        assert str(s) == "State(OVERWORLD.IDLE)"

    def test_repr(self):
        s = State("T", StateType.BOOT)
        r = repr(s)
        assert "State" in r
        assert "T" in r
        assert "active=False" in r


# ── HierarchicalStateMachine ─────────────────────────────────────────────────

class TestHSMConstructor:
    def test_default_name(self):
        hsm = HierarchicalStateMachine()
        assert hsm.name == "HSM"

    def test_custom_name(self):
        hsm = HierarchicalStateMachine("MyHSM")
        assert hsm.name == "MyHSM"

    def test_initial_state_is_boot(self):
        hsm = HierarchicalStateMachine()
        cs = hsm.get_current_state()
        assert cs is not None
        assert cs.name == "BOOT.INITIALIZE"

    def test_all_states_created(self):
        hsm = HierarchicalStateMachine()
        assert hsm.get_state("BOOT.INITIALIZE") is not None
        assert hsm.get_state("OVERWORLD.IDLE") is not None
        assert hsm.get_state("BATTLE.BATTLE_INTRO") is not None
        assert hsm.get_state("MENU.MAIN_MENU") is not None
        assert hsm.get_state("DIALOG.TEXT_DISPLAY") is not None
        assert hsm.get_state("EMERGENCY.SOFTLOCK_DETECTED") is not None

    def test_battle_menu_alias(self):
        """Coverage: line 284 — _initialize_state_aliases"""
        hsm = HierarchicalStateMachine()
        assert hsm.get_state("BATTLE.MENU") is not None
        assert hsm.get_state("BATTLE.MENU") is hsm.get_state("BATTLE.BATTLE_MENU")

    def test_parent_child_relationships(self):
        hsm = HierarchicalStateMachine()
        root_boot = hsm.get_state("BOOT")
        assert root_boot is not None
        init_state = hsm.get_state("BOOT.INITIALIZE")
        assert init_state is not None
        assert init_state.parent is root_boot


class TestHSMStates:
    def test_get_state_existing(self):
        """Coverage: line 454"""
        hsm = HierarchicalStateMachine()
        s = hsm.get_state("OVERWORLD.IDLE")
        assert s is not None
        assert s.name == "OVERWORLD.IDLE"

    def test_get_state_missing(self):
        hsm = HierarchicalStateMachine()
        assert hsm.get_state("NONEXISTENT") is None

    def test_add_state(self):
        """Coverage: line 450"""
        hsm = HierarchicalStateMachine()
        new_state = State("CUSTOM.STATE", StateType.OVERWORLD)
        hsm.add_state(new_state)
        assert hsm.get_state("CUSTOM.STATE") is new_state

    def test_get_current_state(self):
        hsm = HierarchicalStateMachine()
        cs = hsm.get_current_state()
        assert cs is not None
        assert cs.name == "BOOT.INITIALIZE"

    def test_get_previous_state(self):
        hsm = HierarchicalStateMachine()
        # Initially None since reset sets previous to None
        hsm.transition_to("OVERWORLD.IDLE")
        ps = hsm.get_previous_state()
        assert ps is not None
        assert ps.name == "BOOT.INITIALIZE"

    def test_get_state_history(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        hist = hsm.get_state_history()
        assert len(hist) >= 1
        assert hist[0].from_state == "BOOT.INITIALIZE"
        assert hist[0].to_state == "OVERWORLD.IDLE"

    def test_get_transition_count(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        count = hsm.get_transition_count("BOOT.INITIALIZE", "OVERWORLD.IDLE")
        assert count == 1
        assert hsm.get_transition_count("A", "B") == 0


class TestHSMCanTransition:
    def test_valid_transition(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        assert hsm.can_transition("OVERWORLD.IDLE", "MENU.MAIN_MENU") is True

    def test_invalid_transition(self):
        hsm = HierarchicalStateMachine()
        assert hsm.can_transition("BOOT.INITIALIZE", "BATTLE.BATTLE_ANIMATION") is False

    def test_from_none_string(self):
        """Coverage: line 474-475 — from_state "None" or None"""
        hsm = HierarchicalStateMachine()
        assert hsm.can_transition("None", "ANYTHING") is True

    def test_from_none_value(self):
        hsm = HierarchicalStateMachine()
        assert hsm.can_transition(None, "ANYTHING") is True  # type: ignore[arg-type]


class TestHSMTransitionTo:
    def test_valid_transition(self):
        hsm = HierarchicalStateMachine()
        result = hsm.transition_to("OVERWORLD.IDLE")
        assert result == StateTransitionResult.SUCCESS
        assert hsm.get_current_state().name == "OVERWORLD.IDLE"

    def test_invalid_transition(self):
        hsm = HierarchicalStateMachine()
        result = hsm.transition_to("BATTLE.BATTLE_ANIMATION")
        assert result == StateTransitionResult.INVALID_TRANSITION
        assert hsm.get_current_state().name == "BOOT.INITIALIZE"

    def test_state_not_found(self):
        hsm = HierarchicalStateMachine()
        with pytest.raises(ValueError, match="State not found"):
            hsm.transition_to("DOES.NOT_EXIST")

    def test_same_state_increments_tick(self):
        """Coverage: transition_to same-state branch"""
        hsm = HierarchicalStateMachine()
        assert hsm._tick == 0
        result = hsm.transition_to("BOOT.INITIALIZE")
        assert result == StateTransitionResult.SUCCESS
        assert hsm._tick == 1

    def test_same_state_with_explicit_tick(self):
        hsm = HierarchicalStateMachine()
        result = hsm.transition_to("BOOT.INITIALIZE", tick=42)
        assert result == StateTransitionResult.SUCCESS
        assert hsm._tick == 42

    def test_tick_must_be_non_decreasing(self):
        hsm = HierarchicalStateMachine()
        hsm._tick = 100
        with pytest.raises(ValueError, match="Invalid tick value"):
            hsm.transition_to("OVERWORLD.IDLE", tick=50)

    def test_emergency_interrupt(self):
        """Coverage: lines 532-534 — emergency transition bypasses validation"""
        hsm = HierarchicalStateMachine()
        # SOFTLOCK_DETECTED is not in INITIALIZE's legal transitions
        result = hsm.transition_to("EMERGENCY.SOFTLOCK_DETECTED")
        assert result == StateTransitionResult.EMERGENCY_INTERRUPT
        assert hsm.get_current_state().name == "EMERGENCY.SOFTLOCK_DETECTED"

    def test_transition_updates_previous_state(self):
        """Coverage: lines 543-546"""
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        ps = hsm.get_previous_state()
        assert ps.name == "BOOT.INITIALIZE"

    def test_transition_records_history(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        hist = hsm.get_state_history()
        assert len(hist) >= 1
        assert hist[-1].from_state == "BOOT.INITIALIZE"
        assert hist[-1].to_state == "OVERWORLD.IDLE"

    def test_transition_with_reason(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE", reason="test reason")
        hist = hsm.get_state_history()
        assert hist[-1].reason == "test reason"


class TestHSMCallbacks:
    def test_transition_callback_called(self):
        """Coverage: lines 570-574 — callback invocation + exception"""
        hsm = HierarchicalStateMachine()
        calls = []

        def cb(prev, curr):
            calls.append((prev.name if prev else None, curr.name if curr else None))

        hsm.register_transition_callback(cb)
        hsm.transition_to("OVERWORLD.IDLE")
        assert len(calls) == 1
        assert calls[0][0] == "BOOT.INITIALIZE"
        assert calls[0][1] == "OVERWORLD.IDLE"

    def test_transition_callback_exception_logged(self):
        """Coverage: line 573-574"""
        hsm = HierarchicalStateMachine()

        def failing_cb(prev, curr):
            raise RuntimeError("callback boom")

        hsm.register_transition_callback(failing_cb)
        # Should not raise — exception is caught and logged
        result = hsm.transition_to("OVERWORLD.IDLE")
        assert result == StateTransitionResult.SUCCESS

    def test_emergency_callback_called(self):
        """Coverage: emergency callback invocation"""
        hsm = HierarchicalStateMachine()
        calls = []

        def ecb(reason):
            calls.append(reason)

        hsm.register_emergency_callback(ecb)
        hsm.trigger_emergency("test emergency")
        assert len(calls) == 1
        assert calls[0] == "test emergency"

    def test_emergency_callback_exception_logged(self):
        """Coverage: lines 496-497"""
        hsm = HierarchicalStateMachine()

        def failing_ecb(reason):
            raise RuntimeError("emergency callback boom")

        hsm.register_emergency_callback(failing_ecb)
        # Should not raise — exception is caught and logged
        hsm.trigger_emergency("test")


class TestHSMEmergency:
    def test_trigger_emergency(self):
        hsm = HierarchicalStateMachine()
        hsm.trigger_emergency("softlock")
        assert hsm._emergency_triggered is True
        assert hsm._emergency_reason == "softlock"

    def test_clear_emergency(self):
        hsm = HierarchicalStateMachine()
        hsm.trigger_emergency("softlock")
        hsm.clear_emergency()
        assert hsm._emergency_triggered is False
        assert hsm._emergency_reason is None

    def test_is_emergency(self):
        """Coverage: line 675"""
        hsm = HierarchicalStateMachine()
        assert hsm.is_emergency() is False
        hsm.trigger_emergency("test")
        assert hsm.is_emergency() is True


class TestHSMIsInMethods:
    def test_is_in_battle(self):
        """Coverage: line 657"""
        hsm = HierarchicalStateMachine()
        assert hsm.is_in_battle() is False
        hsm.transition_to("OVERWORLD.IDLE")
        hsm.transition_to("BATTLE.BATTLE_INTRO")
        assert hsm.is_in_battle() is True

    def test_is_in_menu(self):
        """Coverage: line 663"""
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        assert hsm.is_in_menu() is False
        hsm.transition_to("MENU.MAIN_MENU")
        assert hsm.is_in_menu() is True

    def test_is_in_dialog(self):
        """Coverage: line 669"""
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        assert hsm.is_in_dialog() is False
        hsm.transition_to("DIALOG.TEXT_DISPLAY")
        assert hsm.is_in_dialog() is True

    def test_is_in_None_returns_false(self):
        """Coverage: lines 651, 663, 669, 675 — current state is None"""
        hsm = HierarchicalStateMachine()
        hsm._current_state = None
        assert hsm.is_in_battle() is False
        assert hsm.is_in_menu() is False
        assert hsm.is_in_dialog() is False
        assert hsm.is_emergency() is False


class TestHSMGetCurrentStateName:
    def test_with_state(self):
        hsm = HierarchicalStateMachine()
        assert hsm.get_current_state_name() == "BOOT.INITIALIZE"

    def test_without_state(self):
        hsm = HierarchicalStateMachine()
        hsm._current_state = None
        assert hsm.get_current_state_name() == "None"


class TestHSMPushPop:
    def test_push_state(self):
        """Coverage: lines 586-589"""
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        result = hsm.push_state("MENU.MAIN_MENU")
        assert result is True
        assert hsm.get_current_state().name == "MENU.MAIN_MENU"

    def test_push_state_nonexistent(self):
        """Coverage: line 584"""
        hsm = HierarchicalStateMachine()
        result = hsm.push_state("DOES.NOT_EXIST")
        assert result is False

    def test_pop_state_returns_previous(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        hsm.push_state("MENU.MAIN_MENU")
        popped = hsm.pop_state()
        assert popped is not None
        assert popped.name == "OVERWORLD.IDLE"
        assert hsm.get_current_state().name == "OVERWORLD.IDLE"

    def test_pop_state_empty_stack(self):
        """Coverage: lines 594-595"""
        hsm = HierarchicalStateMachine()
        result = hsm.pop_state()
        assert result is None


class TestHSMUpdate:
    def test_update_increments_tick(self):
        hsm = HierarchicalStateMachine()
        result = hsm.update()
        assert result is not None
        assert result.name == "BOOT.INITIALIZE"
        assert hsm._tick == 1

    def test_update_with_explicit_tick(self):
        hsm = HierarchicalStateMachine()
        result = hsm.update(tick=42)
        assert hsm._tick == 42

    def test_update_invalid_tick(self):
        """Coverage: lines 607-609"""
        hsm = HierarchicalStateMachine()
        hsm._tick = 100
        with pytest.raises(ValueError, match="Invalid tick value"):
            hsm.update(tick=50)

    def test_update_no_current_state(self):
        """Coverage: lines 614-615"""
        hsm = HierarchicalStateMachine()
        hsm._current_state = None
        result = hsm.update()
        assert result is not None
        # Should have transitioned to BOOT.INITIALIZE
        assert result.name == "BOOT.INITIALIZE"

    def test_update_with_on_update_returning_new_state(self):
        """Coverage: line 620 — on_update returns non-None"""
        hsm = HierarchicalStateMachine()
        # Monkey-patch on_update on current state to return a new state
        hsm.transition_to("OVERWORLD.IDLE")

        target = hsm.get_state("MENU.MAIN_MENU")
        original_on_update = hsm._current_state.on_update

        def patched_on_update(tick):
            return target

        hsm._current_state.on_update = patched_on_update
        try:
            result = hsm.update()
            assert result.name == "MENU.MAIN_MENU"
        finally:
            hsm._current_state.on_update = original_on_update


class TestHSMReset:
    def test_reset_clears_history(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        hsm.transition_to("MENU.MAIN_MENU")
        assert len(hsm.get_state_history()) >= 2
        hsm.reset()
        assert len(hsm.get_state_history()) == 0

    def test_reset_clears_stack(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        hsm.push_state("MENU.MAIN_MENU")
        assert len(hsm._state_stack) > 0
        hsm.reset()
        assert len(hsm._state_stack) == 0

    def test_reset_sets_initial_state(self):
        """Coverage: lines 693-695 — reset with current state"""
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        hsm.reset()
        assert hsm.get_current_state().name == "BOOT.INITIALIZE"
        assert hsm._emergency_triggered is False
        assert hsm._emergency_reason is None

    def test_reset_no_initial_state(self):
        """Coverage: line 692->exit — initial state missing from _states"""
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        # Remove the INITIALIZE state to trigger the branch
        del hsm._states["BOOT.INITIALIZE"]
        hsm.reset()
        # reset is a no-op when initial state is missing
        assert hsm.get_current_state().name == "OVERWORLD.IDLE"


class TestHSMGetAvailableTransitions:
    def test_with_current_state(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        transitions = hsm.get_available_transitions()
        assert "MENU.MAIN_MENU" in transitions

    def test_without_current_state(self):
        """Coverage: line 651"""
        hsm = HierarchicalStateMachine()
        hsm._current_state = None
        assert hsm.get_available_transitions() == set()


class TestHSMGetStatistics:
    def test_basic_stats(self):
        """Coverage: get_statistics + transition_count loop (line 630)"""
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        hsm.transition_to("MENU.MAIN_MENU")
        hsm.transition_to("OVERWORLD.IDLE")
        stats = hsm.get_statistics()
        assert stats["name"] == "HSM"
        assert stats["current_state"] == "OVERWORLD.IDLE"
        assert stats["total_ticks"] >= 0
        assert stats["transition_count"] >= 3
        assert stats["total_states"] > 0
        assert stats["emergency_triggered"] is False
        assert stats["emergency_reason"] is None

    def test_stats_with_emergency(self):
        hsm = HierarchicalStateMachine()
        hsm.trigger_emergency("test")
        stats = hsm.get_statistics()
        assert stats["emergency_triggered"] is True
        assert stats["emergency_reason"] == "test"


# ── GameStateClassifier ──────────────────────────────────────────────────────

class TestGameStateClassifier:
    def test_constructor(self):
        """Coverage: lines 707-709"""
        hsm = HierarchicalStateMachine()
        gsc = GameStateClassifier(hsm)
        assert gsc.hsm is hsm
        assert gsc._classification_interval == 0.016

    def test_classify_no_current_state(self):
        """Coverage: lines 724-725 — current state is None"""
        hsm = HierarchicalStateMachine()
        hsm._current_state = None
        gsc = GameStateClassifier(hsm)
        result = gsc.classify("dummy_screen")
        assert result is None

    def test_classify_rate_limited(self):
        """Coverage: lines 718-719 — classification interval not elapsed"""
        hsm = HierarchicalStateMachine()
        gsc = GameStateClassifier(hsm)
        gsc._last_classification_time = time.time() + 10  # far in the future
        result = gsc.classify("dummy_screen")
        assert result is None

    def test_classify_no_state_change(self):
        """Coverage: classify with _determine_state returning None"""
        hsm = HierarchicalStateMachine()
        gsc = GameStateClassifier(hsm)
        # _determine_state returns None by default
        result = gsc.classify("dummy_screen")
        assert result is None

    def test_determine_state_returns_none(self):
        """Coverage: line 740"""
        hsm = HierarchicalStateMachine()
        gsc = GameStateClassifier(hsm)
        result = gsc._determine_state("screen", None)
        assert result is None

    def test_classify_with_suggested_state(self):
        """Coverage: suggested state path (lines 729-732)"""
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        gsc = GameStateClassifier(hsm)

        # Patch _determine_state to suggest a valid transition
        def mock_determine(screen_data, memory_data):
            return "MENU.MAIN_MENU"

        gsc._determine_state = mock_determine  # type: ignore[assignment]
        # Reset classification time so interval check passes
        gsc._last_classification_time = 0
        result = gsc.classify("dummy_screen")
        assert result == "MENU.MAIN_MENU"
        assert hsm.get_current_state().name == "MENU.MAIN_MENU"

    def test_classify_invalid_suggested_state(self):
        """Classification suggests state not in legal transitions"""
        hsm = HierarchicalStateMachine()
        gsc = GameStateClassifier(hsm)

        def mock_determine(screen_data, memory_data):
            return "BATTLE.BATTLE_ANIMATION"  # not valid from INITIALIZE

        gsc._determine_state = mock_determine  # type: ignore[assignment]
        gsc._last_classification_time = 0
        result = gsc.classify("dummy_screen")
        # Should return None since transition is invalid (not emergency)
        assert result is None

    def test_classify_emergency_suggested(self):
        """Coverage: suggested EMERGENCY state (lines 733-734)"""
        hsm = HierarchicalStateMachine()
        gsc = GameStateClassifier(hsm)

        def mock_determine(screen_data, memory_data):
            return "EMERGENCY.SOFTLOCK_DETECTED"

        gsc._determine_state = mock_determine  # type: ignore[assignment]
        gsc._last_classification_time = 0
        result = gsc.classify("dummy_screen")
        assert result is None  # classify returns None for emergency (triggered via trigger_emergency)
        assert hsm._emergency_triggered is True


# ── Factory Function ─────────────────────────────────────────────────────────

class TestFactory:
    def test_create_hierarchical_state_machine(self):
        hsm = create_hierarchical_state_machine()
        assert isinstance(hsm, HierarchicalStateMachine)
        assert hsm.name == "PTP-01X-HSM"
        assert hsm.get_current_state() is not None
        assert hsm.get_current_state().name == "BOOT.INITIALIZE"


# ── Full Transition Chain ────────────────────────────────────────────────────

class TestFullTransitionChain:
    def test_overworld_to_battle_flow(self):
        hsm = HierarchicalStateMachine()
        # INITIALIZE -> OVERWORLD.IDLE
        hsm.transition_to("OVERWORLD.IDLE")
        assert hsm.get_current_state().name == "OVERWORLD.IDLE"
        # OVERWORLD.IDLE -> BATTLE.BATTLE_INTRO
        result = hsm.transition_to("BATTLE.BATTLE_INTRO")
        assert result == StateTransitionResult.SUCCESS
        assert hsm.is_in_battle() is True
        # BATTLE.BATTLE_INTRO -> BATTLE.BATTLE_MENU
        hsm.transition_to("BATTLE.BATTLE_MENU")
        # BATTLE.BATTLE_MENU -> BATTLE.MOVE_SELECTION
        hsm.transition_to("BATTLE.MOVE_SELECTION")
        # MOVE_SELECTION -> BATTLE_ANIMATION
        hsm.transition_to("BATTLE.BATTLE_ANIMATION")
        # BATTLE_ANIMATION -> BATTLE_RESULT
        hsm.transition_to("BATTLE.BATTLE_RESULT")
        # BATTLE_RESULT -> BATTLE_END
        hsm.transition_to("BATTLE.BATTLE_END")
        # BATTLE_END -> OVERWORLD.IDLE
        hsm.transition_to("OVERWORLD.IDLE")
        assert hsm.is_in_battle() is False

    def test_dialog_flow(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        # Interact with sign
        hsm.transition_to("OVERWORLD.INTERACTING_SIGN")
        result = hsm.transition_to("DIALOG.TEXT_DISPLAY")
        assert result == StateTransitionResult.SUCCESS
        assert hsm.is_in_dialog() is True
        # Complete dialog
        hsm.transition_to("DIALOG.TEXT_COMPLETE")
        hsm.transition_to("OVERWORLD.IDLE")
        assert hsm.is_in_dialog() is False

    def test_push_pop_menu_flow(self):
        hsm = HierarchicalStateMachine()
        hsm.transition_to("OVERWORLD.IDLE")
        # Open menu (push current state)
        hsm.push_state("MENU.MAIN_MENU")
        assert hsm.get_current_state().name == "MENU.MAIN_MENU"
        # Navigate submenus
        hsm.transition_to("MENU.INVENTORY")
        assert hsm.get_current_state().name == "MENU.INVENTORY"
        # Return to main
        hsm.transition_to("MENU.MAIN_MENU")
        # Close menu (pop back to overworld)
        hsm.pop_state()
        assert hsm.get_current_state().name == "OVERWORLD.IDLE"
