"""
Hierarchical State Machine (HSM) for PTP-01X Pokemon AI

Implements a comprehensive state machine with:
- Base State class with enter/exit/update methods
- HierarchicalStateMachine with nested state support
- 50+ game states covering bootstrap, overworld, battle, menu, dialog, and emergency states
- State transition validation (legal transitions only)
- History tracking for debugging
- Emergency interrupt handling within 1 second
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from datetime import datetime
import time
import logging


logger = logging.getLogger(__name__)


class StateType(Enum):
    """High-level state categories"""
    BOOT = auto()
    TITLE = auto()
    MENU = auto()
    DIALOG = auto()
    OVERWORLD = auto()
    BATTLE = auto()
    EMERGENCY = auto()
    TRANSITION = auto()


class BootSubState(Enum):
    """Bootstrap sequence states"""
    INITIALIZE = auto()
    TITLE_SCREEN = auto()
    PRESS_START = auto()
    DETECT_CONTINUE = auto()
    SELECT_GAME_MODE = auto()
    NEW_GAME = auto()
    CONTINUE_GAME = auto()
    VERIFY_SAVE = auto()
    CHARACTER_NAMING = auto()
    CONFIGURE_OPTIONS = auto()
    INITIALIZE_CLOCK = auto()
    BOOT_COMPLETE = auto()
    HANDLE_CORRUPT_SAVE = auto()


class TitleSubState(Enum):
    """Title screen states"""
    SHOWING_LOGO = auto()
    WAITING_FOR_START = auto()
    GAME_MODE_MENU = auto()


class MenuSubState(Enum):
    """Menu navigation states"""
    MAIN_MENU = auto()
    POKEMON_MENU = auto()
    INVENTORY = auto()
    SAVE_MENU = auto()
    OPTIONS = auto()
    PC_MENU = auto()
    TRAINER_CARD = auto()
    CONTEXT_MENU = auto()


class DialogSubState(Enum):
    """Dialog/text display states"""
    TEXT_DISPLAY = auto()
    CHOICE_MENU = auto()
    YES_NO_MENU = auto()
    TEXT_COMPLETE = auto()
    AWAITING_INPUT = auto()


class OverworldSubState(Enum):
    """Overworld navigation states"""
    IDLE = auto()
    WALKING = auto()
    RUNNING = auto()
    SURFING = auto()
    FLYING = auto()
    BIKING = auto()
    FISHING = auto()
    APPROACHING_NPC = auto()
    INTERACTING_SIGN = auto()
    FACING_DOOR = auto()
    INTERACTION_ZONE = auto()
    CENTER_HEAL = auto()
    MART_SHOPPING = auto()


class BattleSubState(Enum):
    """Battle system states"""
    BATTLE_INTRO = auto()
    BATTLE_MENU = auto()
    MOVE_SELECTION = auto()
    TARGET_SELECTION = auto()
    BATTLE_ANIMATION = auto()
    BATTLE_MESSAGE = auto()
    BATTLE_RESULT = auto()
    BATTLE_END = auto()
    SWITCH_POKEMON = auto()
    USE_ITEM = auto()
    CATCH_ATTEMPT = auto()


class EmergencySubState(Enum):
    """Emergency interrupt states"""
    NORMAL_OPERATION = auto()
    SOFTLOCK_DETECTED = auto()
    ERROR_RECOVERY = auto()
    EMERGENCY_SHUTDOWN = auto()
    GAME_OVER = auto()
    BLACKOUT_RECOVERY = auto()
    MENU_ESCAPE = auto()
    PATH_BLOCKED = auto()
    LOW_RESOURCE = auto()


class StateTransitionResult(Enum):
    """Result of a state transition attempt"""
    SUCCESS = auto()
    INVALID_TRANSITION = auto()
    STATE_NOT_FOUND = auto()
    CONDITION_FAILED = auto()
    EMERGENCY_INTERRUPT = auto()


@dataclass
class StateTransition:
    """Records a single state transition for history"""
    from_state: str
    to_state: str
    timestamp: datetime = field(default_factory=datetime.now)
    tick: int = 0
    reason: str = ""
    duration_ms: float = 0.0


@dataclass
class TransitionCondition:
    """Condition that must be met for a transition"""
    name: str
    check_func: Callable[[], bool]
    error_message: str = ""


class State(ABC):
    """Base class for all game states with lifecycle methods"""

    def __init__(self, name: str, state_type: StateType):
        self.name = name
        self.state_type = state_type
        self._parent: Optional[State] = None
        self._children: List[State] = []
        self._is_active = False
        self._entry_time: Optional[float] = None
        self._tick_count = 0

    @property
    def parent(self) -> Optional[State]:
        return self._parent

    @parent.setter
    def parent(self, value: Optional[State]):
        self._parent = value

    @property
    def children(self) -> List[State]:
        return self._children

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def entry_time(self) -> Optional[float]:
        return self._entry_time

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def add_child(self, child: State) -> None:
        """Add a child state for hierarchical nesting"""
        child.parent = self
        self._children.append(child)

    def remove_child(self, child: State) -> None:
        """Remove a child state"""
        if child in self._children:
            child.parent = None
            self._children.remove(child)

    def get_full_path(self) -> str:
        """Get the hierarchical path to this state"""
        return self.name

    def on_enter(self, from_state: Optional[State] = None) -> None:
        """Called when entering this state"""
        self._is_active = True
        self._entry_time = time.time()
        self._tick_count = 0
        logger.debug(f"Entered state: {self.get_full_path()}")

    def on_exit(self, to_state: Optional["State"] = None) -> None:
        """Called when exiting this state"""
        self._is_active = False
        logger.debug(f"Exited state: {self.get_full_path()}")

    def on_update(self, tick: int) -> Optional[State]:
        """
        Update this state each tick
        Returns a new state to transition to, or None to stay
        """
        self._tick_count = tick
        return None

    def get_available_transitions(self) -> Set[str]:
        """Get set of valid state names this state can transition to"""
        return set()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' active={self._is_active}>"


class HierarchicalStateMachine:
    """
    Hierarchical State Machine implementation with:
    - Nested state support
    - State transition validation
    - History tracking
    - Emergency interrupt handling
    """

    def __init__(self, name: str = "HSM"):
        self.name = name
        self._states: Dict[str, State] = {}
        self._current_state: Optional[State] = None
        self._previous_state: Optional[State] = None
        self._state_stack: List[State] = []
        self._history: List[StateTransition] = []
        self._transition_count: Dict[Tuple[str, str], int] = {}
        self._tick = 0
        self._start_time = time.time()
        self._emergency_triggered = False
        self._emergency_reason: Optional[str] = None
        self._on_transition_callbacks: List = []
        self._on_emergency_callbacks: List[Callable[[str], None]] = []

        self._setup_legal_transitions()
        self._setup_state_hierarchy()
        self._initialize_state_aliases()
        self._reset()

    def _reset(self) -> None:
        """Reset the state machine to initial state"""
        self._history.clear()
        self._transition_count.clear()
        self._state_stack.clear()
        self._tick = 0
        self._emergency_triggered = False
        self._emergency_reason = None

        initial_state = self._states.get("BOOT.INITIALIZE")
        if initial_state:
            self._previous_state = self._current_state
            self._current_state = initial_state
            initial_state.on_enter(self._previous_state)

    def _initialize_state_aliases(self) -> None:
        """Create state aliases for convenience"""
        if "BATTLE.BATTLE_MENU" in self._states:
            self._states["BATTLE.MENU"] = self._states["BATTLE.BATTLE_MENU"]

    def _setup_legal_transitions(self) -> None:
        """Define valid state transitions"""
        self._legal_transitions: Dict[str, Set[str]] = {
            "BOOT.INITIALIZE": {"BOOT.TITLE_SCREEN"},
            "BOOT.TITLE_SCREEN": {"BOOT.PRESS_START", "BOOT.DETECT_CONTINUE"},
            "BOOT.PRESS_START": {"BOOT.SELECT_GAME_MODE"},
            "BOOT.DETECT_CONTINUE": {"BOOT.SELECT_GAME_MODE"},
            "BOOT.SELECT_GAME_MODE": {"BOOT.NEW_GAME", "BOOT.CONTINUE_GAME"},
            "BOOT.NEW_GAME": {"BOOT.CHARACTER_NAMING", "BOOT.CONFIGURE_OPTIONS"},
            "BOOT.CONTINUE_GAME": {"BOOT.VERIFY_SAVE"},
            "BOOT.VERIFY_SAVE": {"BOOT.BOOT_COMPLETE", "BOOT.HANDLE_CORRUPT_SAVE"},
            "BOOT.CHARACTER_NAMING": {"BOOT.CONFIGURE_OPTIONS"},
            "BOOT.CONFIGURE_OPTIONS": {"BOOT.INITIALIZE_CLOCK"},
            "BOOT.INITIALIZE_CLOCK": {"BOOT.BOOT_COMPLETE"},
            "BOOT.HANDLE_CORRUPT_SAVE": {"BOOT.NEW_GAME"},
            "BOOT.BOOT_COMPLETE": {"OVERWORLD.IDLE"},
            "BOOT.INITIALIZE": {"BOOT.TITLE_SCREEN", "OVERWORLD.IDLE", "BATTLE.MENU"},

            "TITLE.SHOWING_LOGO": {"TITLE.WAITING_FOR_START"},
            "TITLE.WAITING_FOR_START": {"TITLE.GAME_MODE_MENU"},
            "TITLE.GAME_MODE_MENU": {"MENU.MAIN_MENU"},

            "MENU.MAIN_MENU": {"MENU.POKEMON_MENU", "MENU.INVENTORY", "MENU.SAVE_MENU", "MENU.OPTIONS", "OVERWORLD.IDLE"},
            "MENU.POKEMON_MENU": {"MENU.MAIN_MENU", "MENU.POKEMON_MENU", "OVERWORLD.IDLE"},
            "MENU.INVENTORY": {"MENU.MAIN_MENU", "DIALOG.CHOICE_MENU", "OVERWORLD.IDLE"},
            "MENU.SAVE_MENU": {"MENU.MAIN_MENU", "DIALOG.TEXT_DISPLAY", "OVERWORLD.IDLE"},
            "MENU.OPTIONS": {"MENU.MAIN_MENU", "OVERWORLD.IDLE"},
            "MENU.PC_MENU": {"MENU.MAIN_MENU", "OVERWORLD.IDLE"},
            "MENU.TRAINER_CARD": {"MENU.MAIN_MENU", "OVERWORLD.IDLE"},

            "DIALOG.TEXT_DISPLAY": {"DIALOG.AWAITING_INPUT", "DIALOG.CHOICE_MENU", "DIALOG.YES_NO_MENU", "OVERWORLD.IDLE", "MENU.MAIN_MENU"},
            "DIALOG.AWAITING_INPUT": {"DIALOG.TEXT_COMPLETE", "DIALOG.CHOICE_MENU"},
            "DIALOG.CHOICE_MENU": {"DIALOG.TEXT_DISPLAY", "MENU.INVENTORY", "OVERWORLD.IDLE"},
            "DIALOG.YES_NO_MENU": {"DIALOG.TEXT_DISPLAY", "MENU.SAVE_MENU", "OVERWORLD.IDLE"},
            "DIALOG.TEXT_COMPLETE": {"OVERWORLD.IDLE"},

            "OVERWORLD.IDLE": {"OVERWORLD.WALKING", "MENU.MAIN_MENU", "BATTLE.BATTLE_INTRO", "OVERWORLD.INTERACTING_SIGN", "DIALOG.TEXT_DISPLAY"},
            "OVERWORLD.WALKING": {"OVERWORLD.IDLE", "OVERWORLD.RUNNING", "OVERWORLD.INTERACTION_ZONE", "BATTLE.BATTLE_INTRO", "OVERWORLD.INTERACTING_SIGN", "OVERWORLD.APPROACHING_NPC", "DIALOG.TEXT_DISPLAY"},
            "OVERWORLD.RUNNING": {"OVERWORLD.IDLE", "OVERWORLD.WALKING", "BATTLE.BATTLE_INTRO"},
            "OVERWORLD.SURFING": {"OVERWORLD.IDLE", "BATTLE.BATTLE_INTRO"},
            "OVERWORLD.FLYING": {"OVERWORLD.IDLE"},
            "OVERWORLD.BIKING": {"OVERWORLD.IDLE", "BATTLE.BATTLE_INTRO"},
            "OVERWORLD.FISHING": {"OVERWORLD.IDLE", "BATTLE.BATTLE_INTRO"},
            "OVERWORLD.APPROACHING_NPC": {"DIALOG.TEXT_DISPLAY", "BATTLE.BATTLE_INTRO"},
            "OVERWORLD.INTERACTING_SIGN": {"DIALOG.TEXT_DISPLAY", "OVERWORLD.IDLE"},
            "OVERWORLD.FACING_DOOR": {"OVERWORLD.IDLE"},
            "OVERWORLD.INTERACTION_ZONE": {"DIALOG.TEXT_DISPLAY", "MENU.PC_MENU"},
            "OVERWORLD.CENTER_HEAL": {"DIALOG.TEXT_DISPLAY", "OVERWORLD.IDLE"},
            "OVERWORLD.MART_SHOPPING": {"MENU.INVENTORY", "DIALOG.TEXT_DISPLAY", "OVERWORLD.IDLE"},

            "BATTLE.BATTLE_INTRO": {"BATTLE.BATTLE_MENU", "BATTLE.BATTLE_END"},
            "BATTLE.BATTLE_MENU": {"BATTLE.MOVE_SELECTION", "BATTLE.SWITCH_POKEMON", "BATTLE.USE_ITEM", "BATTLE.CATCH_ATTEMPT"},
            "BATTLE.MENU": {"BATTLE.MOVE_SELECTION", "BATTLE.SWITCH_POKEMON", "BATTLE.USE_ITEM", "BATTLE.CATCH_ATTEMPT"},
            "BATTLE.MOVE_SELECTION": {"BATTLE.TARGET_SELECTION", "BATTLE.BATTLE_ANIMATION"},
            "BATTLE.TARGET_SELECTION": {"BATTLE.BATTLE_ANIMATION"},
            "BATTLE.BATTLE_ANIMATION": {"BATTLE.BATTLE_MESSAGE", "BATTLE.BATTLE_RESULT"},
            "BATTLE.BATTLE_MESSAGE": {"BATTLE.BATTLE_MENU", "BATTLE.BATTLE_RESULT"},
            "BATTLE.SWITCH_POKEMON": {"BATTLE.BATTLE_MENU", "BATTLE.BATTLE_ANIMATION"},
            "BATTLE.USE_ITEM": {"BATTLE.BATTLE_MENU", "BATTLE.BATTLE_ANIMATION"},
            "BATTLE.CATCH_ATTEMPT": {"BATTLE.BATTLE_ANIMATION", "BATTLE.BATTLE_RESULT"},
            "BATTLE.BATTLE_RESULT": {"BATTLE.BATTLE_END", "EMERGENCY.GAME_OVER"},
            "BATTLE.BATTLE_END": {"OVERWORLD.IDLE", "MENU.MAIN_MENU"},

            "EMERGENCY.NORMAL_OPERATION": {"EMERGENCY.SOFTLOCK_DETECTED", "EMERGENCY.GAME_OVER", "BATTLE.BATTLE_INTRO"},
            "EMERGENCY.SOFTLOCK_DETECTED": {"EMERGENCY.ERROR_RECOVERY", "EMERGENCY.MENU_ESCAPE", "OVERWORLD.IDLE"},
            "EMERGENCY.ERROR_RECOVERY": {"OVERWORLD.IDLE", "EMERGENCY.EMERGENCY_SHUTDOWN"},
            "EMERGENCY.EMERGENCY_SHUTDOWN": set(),
            "EMERGENCY.GAME_OVER": {"EMERGENCY.BLACKOUT_RECOVERY"},
            "EMERGENCY.BLACKOUT_RECOVERY": {"OVERWORLD.IDLE"},
            "EMERGENCY.MENU_ESCAPE": {"OVERWORLD.IDLE", "EMERGENCY.ERROR_RECOVERY"},
            "EMERGENCY.PATH_BLOCKED": {"OVERWORLD.IDLE", "EMERGENCY.ERROR_RECOVERY"},
            "EMERGENCY.LOW_RESOURCE": {"EMERGENCY.EMERGENCY_SHUTDOWN"},
        }

    def _setup_state_hierarchy(self) -> None:
        """Build the hierarchical state structure"""
        self._create_boot_states()
        self._create_title_states()
        self._create_menu_states()
        self._create_dialog_states()
        self._create_overworld_states()
        self._create_battle_states()
        self._create_emergency_states()

    def _create_boot_states(self) -> None:
        """Create bootstrap sequence states"""
        boot_parent = State("BOOT", StateType.BOOT)
        self._states["BOOT"] = boot_parent

        for substate in BootSubState:
            state_name = f"BOOT.{substate.name}"
            state = State(state_name, StateType.BOOT)
            boot_parent.add_child(state)
            self._states[state_name] = state

    def _create_title_states(self) -> None:
        """Create title screen states"""
        title_parent = State("TITLE", StateType.TITLE)
        self._states["TITLE"] = title_parent

        for substate in TitleSubState:
            state_name = f"TITLE.{substate.name}"
            state = State(state_name, StateType.TITLE)
            title_parent.add_child(state)
            self._states[state_name] = state

    def _create_menu_states(self) -> None:
        """Create menu navigation states"""
        menu_parent = State("MENU", StateType.MENU)
        self._states["MENU"] = menu_parent

        for substate in MenuSubState:
            state_name = f"MENU.{substate.name}"
            state = State(state_name, StateType.MENU)
            menu_parent.add_child(state)
            self._states[state_name] = state

    def _create_dialog_states(self) -> None:
        """Create dialog/text display states"""
        dialog_parent = State("DIALOG", StateType.DIALOG)
        self._states["DIALOG"] = dialog_parent

        for substate in DialogSubState:
            state_name = f"DIALOG.{substate.name}"
            state = State(state_name, StateType.DIALOG)
            dialog_parent.add_child(state)
            self._states[state_name] = state

    def _create_overworld_states(self) -> None:
        """Create overworld navigation states"""
        overworld_parent = State("OVERWORLD", StateType.OVERWORLD)
        self._states["OVERWORLD"] = overworld_parent

        for substate in OverworldSubState:
            state_name = f"OVERWORLD.{substate.name}"
            state = State(state_name, StateType.OVERWORLD)
            overworld_parent.add_child(state)
            self._states[state_name] = state

    def _create_battle_states(self) -> None:
        """Create battle system states"""
        battle_parent = State("BATTLE", StateType.BATTLE)
        self._states["BATTLE"] = battle_parent

        for substate in BattleSubState:
            state_name = f"BATTLE.{substate.name}"
            state = State(state_name, StateType.BATTLE)
            battle_parent.add_child(state)
            self._states[state_name] = state

    def _create_emergency_states(self) -> None:
        """Create emergency interrupt states"""
        emergency_parent = State("EMERGENCY", StateType.EMERGENCY)
        self._states["EMERGENCY"] = emergency_parent

        for substate in EmergencySubState:
            state_name = f"EMERGENCY.{substate.name}"
            state = State(state_name, StateType.EMERGENCY)
            emergency_parent.add_child(state)
            self._states[state_name] = state

    def add_state(self, state: State) -> None:
        """Add a state to the machine"""
        self._states[state.name] = state

    def get_state(self, state_name: str) -> Optional[State]:
        """Get a state by name"""
        return self._states.get(state_name)

    def get_current_state(self) -> Optional[State]:
        """Get the current active state"""
        return self._current_state

    def get_previous_state(self) -> Optional[State]:
        """Get the previous state"""
        return self._previous_state

    def get_state_history(self) -> List[StateTransition]:
        """Get the state transition history"""
        return self._history.copy()

    def get_transition_count(self, from_state: str, to_state: str) -> int:
        """Get the number of times a transition has occurred"""
        return self._transition_count.get((from_state, to_state), 0)

    def can_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a transition is valid"""
        if from_state == "None" or from_state is None:
            return True
        allowed = self._legal_transitions.get(from_state, set())
        return to_state in allowed

    def register_transition_callback(self, callback: Any) -> None:
        """Register a callback to be called on state transitions"""
        self._on_transition_callbacks.append(callback)

    def register_emergency_callback(self, callback: Callable[[str], None]) -> None:
        """Register a callback to be called when emergency is triggered"""
        self._on_emergency_callbacks.append(callback)

    def trigger_emergency(self, reason: str) -> None:
        """Trigger an emergency interrupt"""
        self._emergency_triggered = True
        self._emergency_reason = reason
        logger.critical(f"Emergency triggered: {reason}")

        for callback in self._on_emergency_callbacks:
            try:
                callback(reason)
            except Exception as e:
                logger.error(f"Emergency callback failed: {e}")

        self.transition_to("EMERGENCY.SOFTLOCK_DETECTED")

    def clear_emergency(self) -> None:
        """Clear emergency state"""
        self._emergency_triggered = False
        self._emergency_reason = None
        logger.info("Emergency state cleared")

    def transition_to(self, state_name: str, reason: str = "", tick: Optional[int] = None) -> StateTransitionResult:
        """
        Transition to a new state
        Returns the result of the transition attempt
        """
        target_state = self._states.get(state_name)
        if target_state is None:
            raise ValueError(f"State not found: {state_name}")

        if tick is not None and tick < self._tick:
            raise ValueError(f"Invalid tick value: {tick} < {self._tick}. Ticks must be non-decreasing.")

        from_state = self._current_state.name if self._current_state else "None"

        if self._current_state == target_state:
            if tick is not None:
                self._tick = tick
            else:
                self._tick += 1
            return StateTransitionResult.SUCCESS

        if not self.can_transition(from_state, state_name):
            logger.warning(f"Invalid transition attempted: {from_state} -> {state_name}")

            if "EMERGENCY" in state_name:
                if self._current_state:
                    self._current_state.on_exit(target_state)
                self._previous_state = self._current_state
                self._current_state = target_state
                target_state.on_enter(self._previous_state)
                return StateTransitionResult.EMERGENCY_INTERRUPT

            return StateTransitionResult.INVALID_TRANSITION

        start_time = time.time()

        if self._current_state:
            self._current_state.on_exit(target_state)

        self._previous_state = self._current_state
        self._current_state = target_state

        if tick is not None:
            self._tick = tick
        else:
            self._tick += 1

        target_state.on_enter(self._previous_state)

        duration_ms = (time.time() - start_time) * 1000

        transition = StateTransition(
            from_state=from_state,
            to_state=state_name,
            tick=self._tick,
            reason=reason,
            duration_ms=duration_ms
        )
        self._history.append(transition)

        pair = (from_state, state_name)
        self._transition_count[pair] = self._transition_count.get(pair, 0) + 1

        for callback in self._on_transition_callbacks:
            try:
                callback(self._previous_state, self._current_state)
            except Exception as e:
                logger.error(f"Transition callback failed: {e}")

        logger.debug(f"Transition: {from_state} -> {state_name} ({duration_ms:.2f}ms)")

        return StateTransitionResult.SUCCESS

    def push_state(self, state_name: str) -> bool:
        """Push a state onto the stack (for temporary interrupts)"""
        target_state = self._states.get(state_name)
        if target_state is None:
            return False

        if self._current_state:
            self._state_stack.append(self._current_state)

        self.transition_to(state_name, reason="State pushed")
        return True

    def pop_state(self) -> Optional[State]:
        """Pop a state from the stack"""
        if not self._state_stack:
            return None

        popped = self._state_stack.pop()
        self.transition_to(popped.name, reason="State popped")
        return popped

    def update(self, tick: Optional[int] = None) -> Optional[State]:
        """
        Update the state machine and current state
        Returns the current state if no transition occurred, or the new state
        """
        if tick is not None:
            if tick < self._tick:
                raise ValueError(f"Invalid tick value: {tick} < {self._tick}. Ticks must be non-decreasing.")
            self._tick = tick
        else:
            self._tick += 1

        if self._current_state is None:
            self.transition_to("BOOT.INITIALIZE")
            return self._current_state

        new_state = self._current_state.on_update(self._tick)

        if new_state is not None:
            self.transition_to(new_state.name, reason="State update", tick=self._tick)

        return self._current_state

    def get_statistics(self) -> Dict[str, Any]:
        """Get state machine statistics"""
        total_time = time.time() - self._start_time

        state_times: Dict[str, float] = {}
        for transition in self._history:
            if transition.to_state not in state_times:
                state_times[transition.to_state] = 0.0

        return {
            "name": self.name,
            "current_state": self._current_state.name if self._current_state else None,
            "previous_state": self._previous_state.name if self._previous_state else None,
            "total_ticks": self._tick,
            "total_time_seconds": total_time,
            "transition_count": len(self._history),
            "unique_transitions": len(self._transition_count),
            "state_counts": dict(self._transition_count),
            "stack_depth": len(self._state_stack),
            "emergency_triggered": self._emergency_triggered,
            "emergency_reason": self._emergency_reason,
            "total_states": len(self._states),
        }

    def get_available_transitions(self) -> Set[str]:
        """Get all valid transitions from current state"""
        if self._current_state is None:
            return set()
        return self._legal_transitions.get(self._current_state.name, set())

    def is_in_battle(self) -> bool:
        """Check if currently in battle"""
        if self._current_state is None:
            return False
        return self._current_state.state_type == StateType.BATTLE

    def is_in_menu(self) -> bool:
        """Check if currently in a menu"""
        if self._current_state is None:
            return False
        return self._current_state.state_type == StateType.MENU

    def is_in_dialog(self) -> bool:
        """Check if currently displaying dialog"""
        if self._current_state is None:
            return False
        return self._current_state.state_type == StateType.DIALOG

    def is_emergency(self) -> bool:
        """Check if in emergency state"""
        if self._current_state is None:
            return False
        return self._current_state.state_type == StateType.EMERGENCY

    def get_current_state_name(self) -> str:
        """Get the current state name"""
        return self._current_state.name if self._current_state else "None"

    def reset(self) -> None:
        """Reset the state machine to initial state"""
        self._history.clear()
        self._transition_count.clear()
        self._state_stack.clear()
        self._tick = 0
        self._emergency_triggered = False
        self._emergency_reason = None

        initial_state = self._states.get("BOOT.INITIALIZE")
        if initial_state:
            if self._current_state:
                self._current_state.on_exit(initial_state)
            self._previous_state = self._current_state
            self._current_state = initial_state
            initial_state.on_enter(self._previous_state)


class GameStateClassifier:
    """
    Classifies the current game state based on visual/memory input
    Used to drive the HSM transitions
    """

    def __init__(self, hsm: HierarchicalStateMachine):
        self.hsm = hsm
        self._last_classification_time = 0.0
        self._classification_interval = 0.016  # ~60fps

    def classify(self, screen_data: Any, memory_data: Optional[Dict] = None) -> Optional[str]:
        """
        Classify the current game state and trigger appropriate transition
        Returns the new state name, or None if no transition needed
        """
        current_time = time.time()

        if current_time - self._last_classification_time < self._classification_interval:
            return None

        self._last_classification_time = current_time

        current_state = self.hsm.get_current_state()
        if current_state is None:
            return None

        suggested_state = self._determine_state(screen_data, memory_data)

        if suggested_state and suggested_state != current_state.name:
            if self.hsm.can_transition(current_state.name, suggested_state):
                self.hsm.transition_to(suggested_state, reason=f"Classified from {current_state.name}")
                return suggested_state
            elif "EMERGENCY" in suggested_state:
                self.hsm.trigger_emergency(f"State classifier suggested: {suggested_state}")

        return None

    def _determine_state(self, screen_data: Any, memory_data: Optional[Dict]) -> Optional[str]:
        """Determine the current state from screen/memory data"""
        return None


def create_hierarchical_state_machine() -> HierarchicalStateMachine:
    """Factory function to create and configure the HSM"""
    hsm = HierarchicalStateMachine("PTP-01X-HSM")
    hsm.reset()
    return hsm