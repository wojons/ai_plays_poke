"""Unit tests for PTP-01X exception hierarchy (src/core/exceptions.py).

Tests cover:
- PokemonAIError base class construction (default, custom message, code, context)
- All 12 subclass construction and attribute preservation
- isinstance checks against base and intermediate classes
"""

import pytest

from src.core.exceptions import (
    PokemonAIError,
    ROMError,
    APIError,
    NetworkError,
    DatabaseError,
    VisionError,
    StateMachineError,
    CombatError,
    MemoryError,
    NavigationError,
    DialogueError,
    EntityError,
    ConfigurationError,
)

# ── All 12 exception subclasses ──────────────────────────────────────────

ALL_SUBCLASSES = [
    ROMError,
    APIError,
    NetworkError,
    DatabaseError,
    VisionError,
    StateMachineError,
    CombatError,
    MemoryError,
    NavigationError,
    DialogueError,
    EntityError,
    ConfigurationError,
]


# ── PokemonAIError Base Class ────────────────────────────────────────────

class TestPokemonAIError:
    """Test the base PokemonAIError exception class."""

    def test_default_message(self):
        """Default message when no args provided."""
        exc = PokemonAIError()
        assert exc.message == "An unspecified PTP-01X error occurred"
        assert str(exc) == "An unspecified PTP-01X error occurred"
        assert exc.code is None
        assert exc.context == {}

    def test_custom_message(self):
        """Custom message overrides default."""
        exc = PokemonAIError("something broke")
        assert exc.message == "something broke"
        assert str(exc) == "something broke"
        assert exc.code is None

    def test_with_code(self):
        """Error code is stored and accessible."""
        exc = PokemonAIError("auth failed", code=401)
        assert exc.code == 401
        assert exc.message == "auth failed"

    def test_with_context(self):
        """Context kwargs are stored as a dict."""
        exc = PokemonAIError("not found", entity="pokemon", entity_id=25)
        assert exc.context == {"entity": "pokemon", "entity_id": 25}

    def test_message_code_context_combo(self):
        """All three fields together."""
        exc = PokemonAIError(
            "battle error", code=500, move="tackle", damage=42
        )
        assert exc.message == "battle error"
        assert exc.code == 500
        assert exc.context == {"move": "tackle", "damage": 42}

    def test_is_exception(self):
        """PokemonAIError is a proper Exception."""
        exc = PokemonAIError()
        assert isinstance(exc, Exception)
        assert isinstance(exc, PokemonAIError)

    def test_empty_context_default(self):
        """When no kwargs, context is empty dict."""
        exc = PokemonAIError("hello", code=200)
        assert exc.context == {}

    def test_code_none_by_default(self):
        """Code defaults to None even with context kwargs."""
        exc = PokemonAIError("hello", foo="bar")
        assert exc.code is None
        assert exc.context == {"foo": "bar"}

    def test_large_code_value(self):
        """Code can be any integer."""
        exc = PokemonAIError("overflow", code=99999)
        assert exc.code == 99999

    def test_message_empty_string(self):
        """Message can be empty string."""
        exc = PokemonAIError("")
        assert exc.message == ""
        assert str(exc) == ""


# ── Subclass Inheritance Tests ───────────────────────────────────────────

class TestExceptionInheritance:
    """Test that all subclasses inherit from PokemonAIError."""

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_inherits_from_pokemon_ai_error(self, cls):
        """Each subclass is a PokemonAIError."""
        exc = cls("test")
        assert isinstance(exc, PokemonAIError)

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_inherits_from_exception(self, cls):
        """Each subclass is also a Python Exception."""
        exc = cls("test")
        assert isinstance(exc, Exception)

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_subclass_not_base_class(self, cls):
        """Each subclass is its own type, not the base."""
        exc = cls("test")
        assert type(exc) is not PokemonAIError
        assert type(exc) is cls


# ── Subclass Attribute Preservation ──────────────────────────────────────

class TestSubclassAttributes:
    """Test that all subclasses preserve message, code, and context."""

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_preserves_custom_message(self, cls):
        """Custom message flows through to .message and str()."""
        msg = f"custom error from {cls.__name__}"
        exc = cls(msg)
        assert exc.message == msg
        assert str(exc) == msg

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_preserves_code(self, cls):
        exc = cls("error", code=42)
        assert exc.code == 42

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_preserves_context(self, cls):
        exc = cls("error", key1="val1", key2=123)
        assert exc.context == {"key1": "val1", "key2": 123}

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_default_message_when_no_args(self, cls):
        """Default message from base class when no args."""
        exc = cls()
        assert exc.message == "An unspecified PTP-01X error occurred"
        assert exc.code is None
        assert exc.context == {}

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_default_code_is_none(self, cls):
        exc = cls("msg")
        assert exc.code is None

    @pytest.mark.parametrize("cls", ALL_SUBCLASSES)
    def test_default_context_is_empty(self, cls):
        exc = cls("msg", code=500)
        assert exc.context == {}


# ── Error-Specific isinstance Checks ─────────────────────────────────────

class TestSpecificExceptions:
    """Test each specific exception class independently."""

    def test_rom_error(self):
        exc = ROMError("bad rom", code=1, path="/tmp/test.gb")
        assert isinstance(exc, ROMError)
        assert isinstance(exc, PokemonAIError)
        assert exc.message == "bad rom"
        assert exc.code == 1
        assert exc.context == {"path": "/tmp/test.gb"}

    def test_api_error(self):
        exc = APIError("rate limited", code=429, endpoint="/v1/chat")
        assert isinstance(exc, APIError)
        assert isinstance(exc, PokemonAIError)
        assert exc.code == 429

    def test_network_error(self):
        exc = NetworkError("timeout", host="api.example.com", port=443)
        assert isinstance(exc, NetworkError)
        assert exc.context == {"host": "api.example.com", "port": 443}

    def test_database_error(self):
        exc = DatabaseError("integrity violation", code=23000, query="SELECT *")
        assert isinstance(exc, DatabaseError)
        assert exc.code == 23000

    def test_vision_error(self):
        exc = VisionError("low confidence", confidence=0.3)
        assert isinstance(exc, VisionError)
        assert exc.context == {"confidence": 0.3}

    def test_state_machine_error(self):
        exc = StateMachineError(
            "invalid transition",
            current_state="battle",
            event="run_away"
        )
        assert isinstance(exc, StateMachineError)
        assert exc.context["current_state"] == "battle"

    def test_combat_error(self):
        exc = CombatError("overflow", damage=9999)
        assert isinstance(exc, CombatError)
        assert exc.context == {"damage": 9999}

    def test_memory_error_at_game_level(self):
        """MemoryError from our hierarchy, NOT Python's builtin."""
        exc = MemoryError("bad address", address=0xC000)
        assert isinstance(exc, MemoryError)
        assert isinstance(exc, PokemonAIError)
        # Verify it is NOT the builtin MemoryError
        assert type(exc).__name__ == "MemoryError"
        import builtins
        assert not isinstance(exc, builtins.MemoryError)

    def test_navigation_error(self):
        exc = NavigationError("no path", current=(5, 5), target=(20, 30))
        assert isinstance(exc, NavigationError)
        assert exc.context["current"] == (5, 5)

    def test_dialogue_error(self):
        exc = DialogueError("invalid option", dialogue_id="oak_intro", valid_options=["YES", "NO"])
        assert isinstance(exc, DialogueError)
        assert "valid_options" in exc.context

    def test_entity_error(self):
        exc = EntityError("not found", entity_type="pokemon", entity_id=25)
        assert isinstance(exc, EntityError)
        assert exc.context["entity_id"] == 25

    def test_configuration_error(self):
        exc = ConfigurationError("missing setting", setting="LOG_LEVEL")
        assert isinstance(exc, ConfigurationError)
        assert exc.context == {"setting": "LOG_LEVEL"}


# ── Edge Cases ───────────────────────────────────────────────────────────

class TestExceptionEdgeCases:
    """Edge cases for the exception hierarchy."""

    def test_multiple_kwargs_with_special_names(self):
        """Context keys that could collide with message/code."""
        # 'message' collides with the __init__ parameter — raises TypeError
        with pytest.raises(TypeError, match="multiple values"):
            PokemonAIError("msg", code=1, message="override_attempt")
        # But code_ goes into context (doesn't collide with 'code')
        exc = PokemonAIError("msg", code=1, code_=999)
        assert exc.code == 1
        assert exc.context == {"code_": 999}

    def test_empty_kwargs(self):
        exc = PokemonAIError("msg")
        assert exc.context == {}

    def test_nested_context_values(self):
        """Context can contain nested structures."""
        nested = {"list": [1, 2, 3], "dict": {"a": 1}}
        exc = PokemonAIError("complex", data=nested)
        assert exc.context["data"] == nested

    def test_catch_by_base_class(self):
        """All subclasses can be caught by PokemonAIError."""
        for cls in ALL_SUBCLASSES:
            exc = cls("test")
            try:
                raise exc
            except PokemonAIError:
                pass  # expected
            else:
                pytest.fail(f"{cls.__name__} was not caught by PokemonAIError")

    def test_catch_by_exception(self):
        """All subclasses can be caught by plain Exception."""
        for cls in ALL_SUBCLASSES:
            exc = cls("test")
            try:
                raise exc
            except Exception:
                pass
            else:
                pytest.fail(f"{cls.__name__} was not caught by Exception")

    def test_raise_and_catch_specific(self):
        """Specific subclass catches only its own type."""
        try:
            raise ROMError("bad rom")
        except ROMError:
            pass
        except PokemonAIError:
            pytest.fail("ROMError caught by PokemonAIError instead of ROMError")
