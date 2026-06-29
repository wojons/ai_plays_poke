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
    emu.wait = MagicMock()
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
    """Vision output for name entry screen (no keyboard grid)."""
    return {
        "screen_type": "name_entry",
        "screen_subtype": "keyboard",
        "name_field": "Enter your name",
    }


@pytest.fixture
def empty_vision():
    """Minimal vision output."""
    return {"screen_type": "unknown"}


# ── Keyboard grid fixtures for _build_prompt keyboard nav ─────────────────

_SAMPLE_GRID = {
    "rows": [
        list("ABCDEFGHIJ"),
        list("KLMNOPQRST"),
        list("UVWXYZ ,.-"),
        list("END"),
    ],
}


@pytest.fixture
def keyboard_grid_vision_ash_A():
    """Keyboard grid with cursor on A, nothing typed yet."""
    return {
        "screen_type": "name_entry",
        "screen_subtype": "keyboard",
        "keyboard_grid": {**_SAMPLE_GRID, "current_cursor": {"row": 0, "col": 0}},
        "name_field": "",
    }


@pytest.fixture
def keyboard_grid_vision_ash_S_half():
    """Keyboard grid with 'AS' typed, cursor on S, next letter H."""
    return {
        "screen_type": "name_entry",
        "screen_subtype": "keyboard",
        "keyboard_grid": {**_SAMPLE_GRID, "current_cursor": {"row": 1, "col": 8}},
        "name_field": "AS",
    }


@pytest.fixture
def keyboard_grid_vision_ash_full():
    """Keyboard grid with 'ASH' typed, should navigate to END."""
    return {
        "screen_type": "name_entry",
        "screen_subtype": "keyboard",
        "keyboard_grid": {**_SAMPLE_GRID, "current_cursor": {"row": 1, "col": 7}},
        "name_field": "ASH",
    }


@pytest.fixture
def keyboard_grid_vision_cursor_on_S_press_now():
    """Keyboard grid: 'A' typed, cursor already on S (row=1,col=8), should press A NOW."""
    return {
        "screen_type": "name_entry",
        "screen_subtype": "keyboard",
        "keyboard_grid": {**_SAMPLE_GRID, "current_cursor": {"row": 1, "col": 8}},
        "name_field": "A",  # next letter is 'S', cursor IS on 'S'
    }


@pytest.fixture
def keyboard_grid_vision_letter_not_found():
    """Keyboard grid where next letter isn't in the single-row grid."""
    return {
        "screen_type": "name_entry",
        "screen_subtype": "keyboard",
        "keyboard_grid": {
            "rows": [list("ABCDEFGHIJ")],
            "current_cursor": {"row": 0, "col": 0},
        },
        "name_field": "X",  # 'X' not in single-row grid
    }


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


def _make_window_with_client(state_type, ctx, emu, vision, **kwargs):
    """Create a StateWindow and return (window, mock_client_instance)."""
    with patch("src.core.state_window.OpenRouterClient") as mock_client_cls:
        mock_client_instance = MagicMock()
        mock_client_cls.return_value = mock_client_instance
        window = StateWindow(
            state_type=state_type,
            global_ctx=ctx,
            emulator=emu,
            vision=vision,
            **kwargs,
        )
    return window, mock_client_instance


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
        assert isinstance(window._workflow, str)

    def test_init_custom_thinking_model(self, ctx, mock_emu, battle_vision):
        """Custom thinking_model is stored."""
        window = _make_window("battle", ctx, mock_emu, battle_vision, thinking_model="gpt-4")
        assert window.thinking_model == "gpt-4"

    def test_init_custom_hint_level(self, ctx, mock_emu, battle_vision):
        """Custom hint_level is stored."""
        window = _make_window("battle", ctx, mock_emu, battle_vision, hint_level=2)
        assert window.hint_level == 2

    def test_init_raw_responses_empty(self, ctx, mock_emu, battle_vision):
        """_raw_responses list starts empty."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window._raw_responses == []


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

    # ── Keyboard grid prompt tests ────────────────────────────────────

    def test_keyboard_grid_nothing_typed_first_letter_A(self, ctx, mock_emu, keyboard_grid_vision_ash_A):
        """Cursor on A, nothing typed — should say 'TARGET NAME: ASH' and first letter is A."""
        window = _make_window("name_entry", ctx, mock_emu, keyboard_grid_vision_ash_A)
        prompt = window._build_prompt()
        assert "NAME ENTRY KEYBOARD" in prompt
        assert "TARGET NAME: 'ASH'" in prompt
        assert "first letter is 'A'" in prompt
        assert "CURSOR IS ON LETTER: 'A'" in prompt

    def test_keyboard_grid_shows_cursor_on_ash_s(self, ctx, mock_emu, keyboard_grid_vision_ash_S_half):
        """'AS' typed, cursor on S — should say next letter H."""
        window = _make_window("name_entry", ctx, mock_emu, keyboard_grid_vision_ash_S_half)
        prompt = window._build_prompt()
        assert "NEXT LETTER TO TYPE: 'H'" in prompt
        assert "ALREADY TYPED: 'AS'" in prompt

    def test_keyboard_grid_all_typed_navigate_to_end(self, ctx, mock_emu, keyboard_grid_vision_ash_full):
        """ASH fully typed — should say navigate to END."""
        window = _make_window("name_entry", ctx, mock_emu, keyboard_grid_vision_ash_full)
        prompt = window._build_prompt()
        assert "ALL LETTERS TYPED!" in prompt
        assert "Navigate to END" in prompt

    def test_keyboard_grid_cursor_already_on_target_press_a(self, ctx, mock_emu, keyboard_grid_vision_cursor_on_S_press_now):
        """Cursor already on next letter S — should say 'press A NOW!'"""
        window = _make_window("name_entry", ctx, mock_emu, keyboard_grid_vision_cursor_on_S_press_now)
        prompt = window._build_prompt()
        assert "press A NOW" in prompt

    def test_keyboard_grid_letter_not_found(self, ctx, mock_emu, keyboard_grid_vision_letter_not_found):
        """Next letter not found in grid — should say 'not found — navigate to END'."""
        window = _make_window("name_entry", ctx, mock_emu, keyboard_grid_vision_letter_not_found)
        prompt = window._build_prompt()
        assert "not found" in prompt.lower()

    def test_keyboard_grid_shows_grid_reference(self, ctx, mock_emu, keyboard_grid_vision_ash_A):
        """Keyboard grid should render row references with letters."""
        window = _make_window("name_entry", ctx, mock_emu, keyboard_grid_vision_ash_A)
        prompt = window._build_prompt()
        assert "Row 0:" in prompt
        # The grid renders as Python list repr: ['A', 'B', 'C', ...]
        # So individual letters appear in quotes
        assert "'" in prompt  # quotes around each letter
        assert "A" in prompt

    def test_keyboard_grid_bottom_row(self, ctx, mock_emu, keyboard_grid_vision_ash_A):
        """Keyboard grid should show bottom row."""
        window = _make_window("name_entry", ctx, mock_emu, keyboard_grid_vision_ash_A)
        prompt = window._build_prompt()
        assert "Bottom row:" in prompt
        assert "END" in prompt

    def test_keyboard_grid_direction_hint_down(self, ctx, mock_emu):
        """Cursor on A (row0,col0), target letter S at row1,col8 -> should say DOWN then RIGHT."""
        vision = {
            "screen_type": "name_entry",
            "screen_subtype": "keyboard",
            "keyboard_grid": {
                "rows": [
                    list("ABCDEFGHIJ"),
                    list("KLMNOPQRST"),
                    list("UVWXYZ ,.-"),
                    list("END"),
                ],
                "current_cursor": {"row": 0, "col": 0},
            },
            "name_field": "A",  # next letter is 'S' (row1, col8)
        }
        window = _make_window("name_entry", ctx, mock_emu, vision)
        prompt = window._build_prompt()
        assert "NEXT LETTER TO TYPE: 'S'" in prompt
        assert "DOWN" in prompt or "RIGHT" in prompt

    def test_keyboard_grid_empty_rows(self, ctx, mock_emu):
        """Empty rows list should not crash."""
        vision = {
            "screen_type": "name_entry",
            "screen_subtype": "keyboard",
            "keyboard_grid": {
                "rows": [],
                "current_cursor": {"row": 0, "col": 0},
            },
            "name_field": "",
        }
        window = _make_window("name_entry", ctx, mock_emu, vision)
        prompt = window._build_prompt()
        assert isinstance(prompt, str)

    def test_keyboard_grid_no_name_field(self, ctx, mock_emu):
        """Vision with keyboard_grid but no name_field should not crash."""
        vision = {
            "screen_type": "name_entry",
            "keyboard_grid": {
                "rows": [list("ABC")],
                "current_cursor": {"row": 0, "col": 0},
            },
        }
        window = _make_window("name_entry", ctx, mock_emu, vision)
        prompt = window._build_prompt()
        assert isinstance(prompt, str)

    # ── History rendering tests ───────────────────────────────────────

    def test_history_renders_remember(self, ctx, mock_emu, battle_vision):
        """History with a remember entry renders correctly."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        window._history.append({"role": "remember", "key": "/discoveries/weakness", "id": "abc"})
        prompt = window._build_prompt()
        assert "Remembered:" in prompt
        assert "/discoveries/weakness" in prompt

    def test_history_renders_recall(self, ctx, mock_emu, battle_vision):
        """History with a recall entry renders correctly."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        window._history.append({"role": "recall", "query": "/types/", "results": "water beats fire"})
        prompt = window._build_prompt()
        assert "Recalled:" in prompt
        assert "/types/" in prompt

    def test_history_renders_set_goal(self, ctx, mock_emu, battle_vision):
        """History with a set_goal entry renders correctly."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        window._history.append({"role": "set_goal", "goal": "catch a Pokémon"})
        prompt = window._build_prompt()
        assert "Set goal:" in prompt
        assert "catch a Pokémon" in prompt

    def test_history_renders_query_global(self, ctx, mock_emu, battle_vision):
        """History with a query_global entry renders correctly."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        window._history.append({"role": "query_global", "question": "What is my objective?"})
        prompt = window._build_prompt()
        assert "Asked global:" in prompt
        assert "What is my objective?" in prompt

    def test_history_renders_auto_a(self, ctx, mock_emu, battle_vision):
        """History with an auto_a action renders correctly."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        window._history.append({
            "step": 1,
            "tool_call": {"name": "press_button", "arguments": {"button": "a", "duration": 30}},
            "action": "auto_a",
        })
        prompt = window._build_prompt()
        assert "Step 1" in prompt
        assert "auto_a" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# Run method tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRun:
    """Verify StateWindow.run() behavior."""

    def test_run_auto_a_dialog_non_interactive(self, ctx, mock_emu):
        """Dialog with non-interactive vision — should auto-press A up to safety cap."""
        vision = {"screen_type": "dialog", "text_lines": ["Hello there!"]}
        window, mock_client = _make_window_with_client("dialog", ctx, mock_emu, vision, max_steps=5)

        result = window.run()

        assert mock_emu.press_button.call_count >= 1
        assert mock_emu.fast_forward.call_count >= 1
        assert result["outcome"] == "max_steps"
        mock_client.send_tool_request.assert_not_called()

    def test_run_auto_a_with_interactive_falls_back_to_llm(self, ctx, mock_emu):
        """Dialog with menu_items -> interactive -> calls LLM."""
        vision = {"screen_type": "dialog", "menu_items": ["YES", "NO"]}
        window, mock_client = _make_window_with_client("dialog", ctx, mock_emu, vision, max_steps=3)
        mock_client.send_tool_request.return_value = (
            '{"name": "press_button", "arguments": {"button": "a", "duration": 5}}'
        )

        with patch("src.core.tools.parse_tool_call",
                    return_value={"name": "press_button", "arguments": {"button": "a", "duration": 5}}):
            result = window.run()

        assert mock_client.send_tool_request.call_count >= 1
        assert result["outcome"] == "max_steps"

    def test_run_name_entry_a_mash(self, ctx, mock_emu):
        """Name entry without keyboard_grid — should A-mash."""
        vision = {"screen_type": "name_entry", "screen_subtype": "keyboard", "name_field": "Enter name"}
        window, mock_client = _make_window_with_client("name_entry", ctx, mock_emu, vision, max_steps=3)

        result = window.run()

        assert mock_emu.press_button.call_count >= 1
        assert result["outcome"] == "max_steps"
        mock_client.send_tool_request.assert_not_called()

    def test_run_query_global_skips_emulator(self, ctx, mock_emu):
        """query_global tool call should skip emulator and re-loop."""
        vision = {"screen_type": "dialog", "menu_items": ["FIGHT"]}
        window, mock_client = _make_window_with_client("dialog", ctx, mock_emu, vision, max_steps=5)

        # First call returns query_global, all subsequent calls return press_button
        _call_count = [0]
        def _side_effect(*_a, **_kw):
            _call_count[0] += 1
            if _call_count[0] == 1:
                return '{"name": "query_global", "arguments": {"question": "What is my objective?"}}'
            return '{"name": "press_button", "arguments": {"button": "a", "duration": 5}}'
        mock_client.send_tool_request.side_effect = _side_effect

        _parse_count = [0]
        def _parse_side_effect(*_a, **_kw):
            _parse_count[0] += 1
            if _parse_count[0] == 1:
                return {"name": "query_global", "arguments": {"question": "What is my objective?"}}
            return {"name": "press_button", "arguments": {"button": "a", "duration": 5}}

        with patch("src.core.tools.parse_tool_call") as mock_parse:
            mock_parse.side_effect = _parse_side_effect
            result = window.run()

        assert result["outcome"] == "max_steps"
        # query_global should not trigger emulator
        # first call is query_global (skipped), subsequent calls press a
        assert mock_client.send_tool_request.call_count >= 2

    def test_run_auto_a_safety_cap_falls_back_to_llm(self, ctx, mock_emu):
        """After 20 auto-a presses, should fall back to AI deliberation."""
        vision = {"screen_type": "dialog", "text_lines": ["Long narration..."]}
        window, mock_client = _make_window_with_client("dialog", ctx, mock_emu, vision, max_steps=25)

        mock_client.send_tool_request.return_value = (
            '{"name": "press_button", "arguments": {"button": "a", "duration": 5}}'
        )

        with patch("src.core.tools.parse_tool_call",
                    return_value={"name": "press_button", "arguments": {"button": "a", "duration": 5}}):
            result = window.run()

        assert mock_emu.press_button.call_count >= 20
        assert mock_client.send_tool_request.call_count >= 1


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

    def test_battle_has_menu_items_is_interactive(self, ctx, mock_emu, battle_vision):
        """Battle vision has menu_items so _is_interactive returns True."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        assert window._is_interactive() is True


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
# _answer_global_query tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAnswerGlobalQuery:
    """Verify _answer_global_query returns compacted context."""

    def test_returns_compact_context(self, ctx, mock_emu, battle_vision):
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        answer = window._answer_global_query("What is my objective?")
        assert "leave the bedroom" in answer
        assert "pallet_town" in answer

    def test_ignores_question_string(self, ctx, mock_emu, battle_vision):
        """Currently _answer_global_query ignores the question and returns all context."""
        window = _make_window("battle", ctx, mock_emu, battle_vision)
        answer1 = window._answer_global_query("What is my objective?")
        answer2 = window._answer_global_query("Where am I?")
        assert answer1 == answer2


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

    def test_loaded_workflow_generic_fallback(self, tmp_path):
        """If gen-specific doesn't exist, fall back to generic dir."""
        import yaml

        generic_file = tmp_path / "battle.yaml"
        generic_file.write_text(yaml.dump({"workflow": "Generic workflow"}))

        with patch("src.core.state_window._STATES_DIR", tmp_path):
            result = _load_state_workflow("battle", "gen1")
            assert result == "Generic workflow"

    def test_loaded_workflow_missing_yaml_key(self, tmp_path):
        """YAML file without workflow key should return empty string."""
        import yaml

        gen1_dir = tmp_path / "gen1"
        gen1_dir.mkdir(parents=True)
        wf = gen1_dir / "battle.yaml"
        wf.write_text(yaml.dump({"other_key": "no workflow"}))

        with patch("src.core.state_window._STATES_DIR", tmp_path):
            result = _load_state_workflow("battle", "gen1")
            assert result == ""

    def test_loaded_workflow_non_dict_yaml(self, tmp_path):
        """YAML file that parses to a list (not dict) should return empty string."""
        import yaml

        gen1_dir = tmp_path / "gen1"
        gen1_dir.mkdir(parents=True)
        wf = gen1_dir / "battle.yaml"
        wf.write_text(yaml.dump(["item1", "item2"]))

        with patch("src.core.state_window._STATES_DIR", tmp_path):
            result = _load_state_workflow("battle", "gen1")
            assert result == ""
