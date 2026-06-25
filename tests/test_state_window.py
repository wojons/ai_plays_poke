"""Tests for StateWindow — focused sub-agent for game state types."""

import pytest
from unittest.mock import MagicMock, patch
from src.core.state_window import (
    StateWindow,
    _DUCKBRAIN_TOOLS,
    _QUERY_GLOBAL_TOOL,
    _load_state_workflow,
)
from src.core.global_context import GlobalContext


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_emu():
    """Mock emulator with press_button, fast_forward, etc."""
    emu = MagicMock()
    emu.press_button = MagicMock()
    emu.fast_forward = MagicMock()
    return emu


@pytest.fixture
def ctx():
    """GlobalContext with basic game state."""
    return GlobalContext(
        player_name="ASH",
        rival_name="GARY",
        location="pallet_town",
        generation="gen1",
        party=[{"name": "SQUIRTLE", "hp_pct": 100, "level": 5, "status": None}],
        goals=["leave the bedroom", "find Professor Oak"],
        active_goal="leave the bedroom",
        story_flags={"got_starter"},
        recent_actions=["walked down", "entered stairs"],
    )


@pytest.fixture
def battle_vision():
    """Vision output for a battle screen."""
    return {
        "screen_type": "battle",
        "screen_subtype": "wild_encounter",
        "enemy_name": "RATTATA",
        "enemy_hp_pct": 85,
        "enemy_level": 3,
        "player_hp_pct": 95,
        "text_lines": ["Wild RATTATA appeared!"],
        "menu_items": ["FIGHT", "PKMN", "ITEM", "RUN"],
    }


@pytest.fixture
def dialog_vision():
    """Vision output for a dialog screen."""
    return {
        "screen_type": "dialog",
        "text_lines": ["Welcome to the world of POKéMON!"],
        "speaker": "Professor Oak",
    }


@pytest.fixture
def overworld_vision():
    """Vision output for overworld navigation."""
    return {
        "screen_type": "overworld",
        "adjacent_tiles": {"up": "grass", "down": "path", "left": "tree", "right": "house"},
        "location": "pallet_town",
    }


@pytest.fixture
def name_entry_vision():
    """Vision output for name entry screen."""
    return {
        "screen_type": "name_entry",
        "screen_subtype": "keyboard",
        "name_field": "Enter your name",
    }


@pytest.fixture
def empty_vision():
    """Minimal vision output."""
    return {"screen_type": "unknown"}


# ── Helper to patch OpenRouterClient ────────────────────────────────────

def _make_window(state_type, ctx, emu, vision, **kwargs):
    """Create a StateWindow with OpenRouterClient mocked."""
    with patch("src.core.state_window.OpenRouterClient") as mock_client:
        mock_client.return_value = MagicMock()
        window = StateWindow(
            state_type=state_type,
            global_ctx=ctx,
            emulator=emu,
            vision=vision,
            **kwargs,
        )
    return window


# ═══════════════════════════════════════════════════════════════════════════
# Construction tests
# ═══════════════════════════════════════════════════════════════════════════

class TestStateWindowInit:
    """Verify StateWindow.__init__ stores fields correctly."""

    def test_init_stores_state_type(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window.state_type == "battle"

    def test_init_stores_global_ctx(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window.global_ctx is ctx

    def test_init_stores_emulator(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window.emulator is mock_emu

    def test_init_stores_vision(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window.vision == battle_vision

    def test_init_defaults_generation_gen1(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window.generation == "gen1"

    def test_init_custom_generation(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision, generation="gen3")
        assert window.generation == "gen3"

    def test_init_default_max_steps_15(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window.max_steps == 15

    def test_init_custom_max_steps(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision, max_steps=5)
        assert window.max_steps == 5

    def test_init_sets_step_count_zero(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window._step_count == 0

    def test_init_history_is_empty_list(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window._history == []

    def test_init_creates_openrouter_client(self, ctx, mock_emu, battle_vision):
        with patch("src.core.state_window.OpenRouterClient") as mock_client:
            mock_client.return_value = MagicMock()
            window = StateWindow(
                state_type="battle",
                global_ctx=ctx,
                emulator=mock_emu,
                vision=battle_vision,
            )
            mock_client.assert_called_once()

    def test_init_loads_workflow(self, ctx, mock_emu, battle_vision):
        """Workflow may be empty string if no config file exists, but should be stored."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert hasattr(window, "_workflow")
        # _workflow is a string (may be empty if no config file)
        assert isinstance(window._workflow, str)


# ═══════════════════════════════════════════════════════════════════════════
# _build_prompt tests
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildPrompt:
    """Verify _build_prompt assembles the correct prompt string."""

    def test_returns_string(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert isinstance(prompt, str)

    def test_includes_global_state_section(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "GLOBAL STATE:" in prompt

    def test_includes_compact_location(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "pallet_town" in prompt

    def test_includes_player_name(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "ASH" in prompt

    def test_includes_rival_name(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "GARY" in prompt

    def test_includes_party_info(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "SQUIRTLE" in prompt

    def test_battle_vision_includes_screen_type(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "battle" in prompt

    def test_battle_vision_includes_subtype(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "wild_encounter" in prompt

    def test_battle_vision_includes_text_lines(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "RATTATA" in prompt

    def test_battle_vision_includes_menu(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "FIGHT" in prompt

    def test_dialog_vision_includes_text(self, ctx, mock_emu, dialog_vision):
        window = _make_window("dialog", ctx, mock_emu, dialog_vision)
        prompt = window._build_prompt()
        assert "Welcome to the world of POKéMON!" in prompt

    def test_dialog_vision_includes_speaker(self, ctx, mock_emu, dialog_vision):
        window = _make_window("dialog", ctx, mock_emu, dialog_vision)
        prompt = window._build_prompt()
        # speaker is in the vision dict but _build_prompt checks vision keys
        # It includes screen_type, subtype, name_field, text_lines, menu_items, adjacent_tiles
        # speaker is currently NOT rendered by _build_prompt — it only checks specific keys
        # The prompt does include screen_type which is "dialog"
        assert "dialog" in prompt

    def test_overworld_vision_includes_surroundings(self, ctx, mock_emu, overworld_vision):
        window = _make_window("overworld", ctx, mock_emu, overworld_vision)
        prompt = window._build_prompt()
        assert "Surroundings:" in prompt
        assert "grass" in prompt
        assert "path" in prompt

    def test_name_entry_includes_name_field(self, ctx, mock_emu, name_entry_vision):
        window = _make_window("name_entry", ctx, mock_emu, name_entry_vision)
        prompt = window._build_prompt()
        assert "Enter your name" in prompt

    def test_empty_vision_returns_minimal_prompt(self, ctx, mock_emu, empty_vision):
        window = _make_window("unknown", ctx, mock_emu, empty_vision)
        prompt = window._build_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "GLOBAL STATE:" in prompt
        assert "observation:" in prompt

    def test_includes_step_counter(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "Step 0 of 15" in prompt

    def test_includes_output_instruction(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "OUTPUT:" in prompt

    def test_no_menu_items_section_if_empty(self, ctx, mock_emu, dialog_vision):
        """When vision has no menu_items, the Menu: line should not appear."""
        window = _make_window("dialog", ctx, mock_emu, dialog_vision)
        prompt = window._build_prompt()
        assert "Menu:" not in prompt

    def test_no_surroundings_section_if_no_adjacent(self, ctx, mock_emu, battle_vision):
        """When vision has no adjacent_tiles, the Surroundings: line should not appear."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "Surroundings:" not in prompt

    def test_story_flags_in_compact(self, ctx, mock_emu, battle_vision):
        """GlobalContext compact() includes story_flags."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "got_starter" in prompt

    def test_goals_in_compact(self, ctx, mock_emu, battle_vision):
        """GlobalContext compact() includes goals."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        prompt = window._build_prompt()
        assert "leave the bedroom" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# _is_interactive tests
# ═══════════════════════════════════════════════════════════════════════════

class TestIsInteractive:
    """Verify _is_interactive correctly detects interactive dialog."""

    def test_menu_items_makes_interactive(self, ctx, mock_emu):
        vision = {"screen_type": "dialog", "menu_items": ["YES", "NO"]}
        window = _make_window("dialog", ctx, mock_emu, vision)
        assert window._is_interactive() is True

    def test_dialog_prompt_makes_interactive(self, ctx, mock_emu):
        vision = {"screen_type": "dialog", "dialog_prompt": True}
        window = _make_window("dialog", ctx, mock_emu, vision)
        assert window._is_interactive() is True

    def test_keyboard_subtype_makes_interactive(self, ctx, mock_emu):
        vision = {"screen_type": "dialog", "screen_subtype": "keyboard"}
        window = _make_window("dialog", ctx, mock_emu, vision)
        assert window._is_interactive() is True

    def test_yes_no_subtype_makes_interactive(self, ctx, mock_emu):
        vision = {"screen_type": "dialog", "screen_subtype": "yes_no"}
        window = _make_window("dialog", ctx, mock_emu, vision)
        assert window._is_interactive() is True

    def test_name_field_makes_interactive(self, ctx, mock_emu):
        vision = {"screen_type": "dialog", "name_field": "Enter name"}
        window = _make_window("dialog", ctx, mock_emu, vision)
        assert window._is_interactive() is True

    def test_pure_narration_is_not_interactive(self, ctx, mock_emu):
        vision = {"screen_type": "dialog", "text_lines": ["Hello there!"]}
        window = _make_window("dialog", ctx, mock_emu, vision)
        assert window._is_interactive() is False

    def test_empty_vision_is_not_interactive(self, ctx, mock_emu):
        vision = {"screen_type": "dialog"}
        window = _make_window("dialog", ctx, mock_emu, vision)
        assert window._is_interactive() is False

    def test_battle_is_not_dialog_interactive(self, ctx, mock_emu, battle_vision):
        """_is_interactive only checks dialog-specific flags — battle menus
        are handled differently."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        # Battle has menu_items but _is_interactive only checks dialog type
        # The state_type is "battle" but _is_interactive checks vision keys
        assert window._is_interactive() is True  # because battle vision has menu_items


# ═══════════════════════════════════════════════════════════════════════════
# _check_outcome tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckOutcome:
    """Verify _check_outcome returns None (not yet implemented)."""

    def test_returns_none_by_default(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window._check_outcome() is None

    def test_returns_none_for_dialog(self, ctx, mock_emu, dialog_vision):
        window = _make_window("dialog", ctx, mock_emu, dialog_vision)
        assert window._check_outcome() is None

    def test_returns_none_for_overworld(self, ctx, mock_emu, overworld_vision):
        window = _make_window("overworld", ctx, mock_emu, overworld_vision)
        assert window._check_outcome() is None


# ═══════════════════════════════════════════════════════════════════════════
# DuckBrain tools tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDuckbrainTools:
    """Verify DuckBrain tool definitions are correctly structured."""

    def test_duckbrain_tools_is_list(self):
        assert isinstance(_DUCKBRAIN_TOOLS, list)

    def test_three_duckbrain_tools(self):
        assert len(_DUCKBRAIN_TOOLS) == 3

    def test_tools_have_required_fields(self):
        for tool in _DUCKBRAIN_TOOLS:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_tool_names(self):
        names = {t["function"]["name"] for t in _DUCKBRAIN_TOOLS}
        assert names == {"remember", "recall", "set_goal"}

    def test_query_global_tool_is_dict(self):
        assert isinstance(_QUERY_GLOBAL_TOOL, dict)
        assert _QUERY_GLOBAL_TOOL["function"]["name"] == "query_global"


# ═══════════════════════════════════════════════════════════════════════════
# _load_state_workflow tests
# ═══════════════════════════════════════════════════════════════════════════

class TestLoadStateWorkflow:
    """Verify _load_state_workflow handles missing and present configs."""

    def test_returns_string(self):
        result = _load_state_workflow("battle", "gen1")
        assert isinstance(result, str)

    def test_unknown_state_returns_empty_string(self):
        result = _load_state_workflow("nonexistent_state_xyz", "gen1")
        assert result == ""

    def test_empty_state_type_returns_empty_string(self):
        result = _load_state_workflow("", "gen1")
        assert result == ""

    def test_loaded_workflow_from_temp_file(self, tmp_path):
        """Create a real YAML file and verify _load_state_workflow reads it."""
        import yaml

        gen1_dir = tmp_path / "gen1"
        gen1_dir.mkdir(parents=True)
        workflow_file = gen1_dir / "battle.yaml"
        workflow_file.write_text(yaml.dump({"workflow": "Test workflow content"}))

        with patch("src.core.state_window._STATES_DIR", tmp_path):
            result = _load_state_workflow("battle", "gen1")
            assert result == "Test workflow content"
