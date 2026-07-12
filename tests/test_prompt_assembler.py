"""
Unit tests for prompt_assembler.py — COV-15: 86% → 95%+

Tests using temp YAML directories (not real configs) for better isolation,
plus edge cases for internal helpers that aren't covered by existing integration tests.
"""

from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from src.core.prompt_assembler import (
    GEN_LABELS,
    GAME_NAMES,
    LAYER_ORDER,
    PromptStack,
    SafeDict,
    _build_enemy_info,
    _build_hp_info,
    _join_list,
)


# ════════════════════════════════════════════════════════════════════════════
# SafeDict — additional edge cases
# ════════════════════════════════════════════════════════════════════════════

class TestSafeDictExtended:
    """Extended SafeDict tests beyond basic missing/existing key coverage."""

    def test_inherits_dict_methods(self) -> None:
        d = SafeDict({"a": 1, "b": 2})
        assert len(d) == 2
        assert "a" in d
        assert d.get("c", "default") == "default"
        assert d.get("a") == 1

    def test_multiple_missing_keys(self) -> None:
        d = SafeDict()
        assert d["first"] == "{first}"
        assert d["second"] == "{second}"
        assert d["third"] == "{third}"

    def test_nested_dict_not_resolved(self) -> None:
        """SafeDict only handles top-level keys — nested access still raises."""
        d = SafeDict({"outer": {"inner": 5}})
        assert d["outer"] == {"inner": 5}

    def test_update_adds_keys(self) -> None:
        d = SafeDict({"a": 1})
        d.update({"b": 2, "c": 3})
        assert d["a"] == 1
        assert d["b"] == 2
        assert d["c"] == 3

    def test_setitem_after_missing(self) -> None:
        d = SafeDict()
        _ = d["missing"]  # creates placeholder via __missing__
        d["missing"] = "now set"
        assert d["missing"] == "now set"


# ════════════════════════════════════════════════════════════════════════════
# _join_list — additional edge cases
# ════════════════════════════════════════════════════════════════════════════

class TestJoinListExtended:
    """Extended _join_list tests for non-list, non-string, non-None values."""

    def test_join_int(self) -> None:
        assert _join_list(42) == "42"

    def test_join_dict(self) -> None:
        assert _join_list({"key": "val"}) == "{'key': 'val'}"

    def test_join_bool(self) -> None:
        assert _join_list(True) == "True"
        assert _join_list(False) == "False"

    def test_join_custom_separator(self) -> None:
        assert _join_list(["x", "y", "z"], sep="|") == "x|y|z"

    def test_join_single_item(self) -> None:
        assert _join_list(["only"], sep=", ") == "only"

    def test_join_mixed_types(self) -> None:
        assert _join_list([1, "two", 3.0], sep=", ") == "1, two, 3.0"


# ════════════════════════════════════════════════════════════════════════════
# _build_hp_info — additional edge cases
# ════════════════════════════════════════════════════════════════════════════

class TestBuildHpInfoExtended:
    """Extended _build_hp_info tests — 0-value, empty fallback, composite fallback."""

    def test_player_zero_percent(self) -> None:
        """Player HP at 0% — 0 is falsy but passes `is not None` check."""
        vision: Dict[str, Any] = {"player_hp_pct": 0}
        result = _build_hp_info(vision)
        assert "0%" in result
        assert "Enemy" not in result

    def test_enemy_zero_percent(self) -> None:
        """Enemy HP at 0% — 0 is falsy but passes `is not None` check."""
        vision: Dict[str, Any] = {"enemy_hp_pct": 0}
        result = _build_hp_info(vision)
        assert "0%" in result
        assert "Enemy" in result

    def test_both_zero_percent(self) -> None:
        vision: Dict[str, Any] = {"player_hp_pct": 0, "enemy_hp_pct": 0}
        result = _build_hp_info(vision)
        assert "Your HP: 0%" in result
        assert "Enemy HP: 0%" in result

    def test_hp_info_empty_string(self) -> None:
        """Falsy hp_info string (empty) — should return empty."""
        vision: Dict[str, Any] = {"hp_info": ""}
        result = _build_hp_info(vision)
        assert result == ""

    def test_hp_info_falsy_zero(self) -> None:
        """hp_info=0 is falsy — should NOT return '0'."""
        vision: Dict[str, Any] = {"hp_info": 0}
        result = _build_hp_info(vision)
        assert result == ""

    def test_only_enemy_hp_set(self) -> None:
        vision: Dict[str, Any] = {"enemy_hp_pct": 45}
        result = _build_hp_info(vision)
        assert "Enemy HP: 45%" in result
        assert "Your HP" not in result

    def test_hp_info_non_string(self) -> None:
        """hp_info as dict — should call str() on it."""
        vision: Dict[str, Any] = {"hp_info": {"current": 20, "max": 35}}
        result = _build_hp_info(vision)
        assert "20" in result  # str() of the dict


# ════════════════════════════════════════════════════════════════════════════
# _build_enemy_info — additional edge cases
# ════════════════════════════════════════════════════════════════════════════

class TestBuildEnemyInfoExtended:
    """Extended _build_enemy_info tests — empty string, falsy values."""

    def test_enemy_pokemon_empty_string(self) -> None:
        """Empty string enemy_pokemon is falsy — should fall through to enemy_info."""
        vision: Dict[str, Any] = {"enemy_pokemon": ""}
        result = _build_enemy_info(vision)
        assert result == ""

    def test_enemy_pokemon_none_then_fallback(self) -> None:
        vision: Dict[str, Any] = {
            "enemy_pokemon": None,
            "enemy_info": "Wild RATTATA appeared!",
        }
        result = _build_enemy_info(vision)
        assert result == "Wild RATTATA appeared!"

    def test_enemy_info_zero(self) -> None:
        """enemy_info=0 is falsy — should NOT return '0'."""
        vision: Dict[str, Any] = {"enemy_info": 0}
        result = _build_enemy_info(vision)
        assert result == ""

    def test_enemy_info_dict(self) -> None:
        """enemy_info as dict — should str() it."""
        vision: Dict[str, Any] = {"enemy_info": {"name": "RATTATA", "level": 3}}
        result = _build_enemy_info(vision)
        assert "RATTATA" in result


# ════════════════════════════════════════════════════════════════════════════
# PromptStack with temp YAML directories
# ════════════════════════════════════════════════════════════════════════════

def _make_temp_config(
    tmp_path: Path,
    generation: str = "gen1",
    screen_type: str = "battle",
    include_flow: bool = False,
    flow_content: Dict[str, Any] | None = None,
    extra_layers: Dict[str, Any] | None = None,
) -> Path:
    """Create a minimal temp prompt config directory with one stack YAML."""
    configs_dir = tmp_path / "configs" / "prompts"
    gen_dir = configs_dir / generation
    gen_dir.mkdir(parents=True, exist_ok=True)

    layers: Dict[str, Any] = {
        "system": "System: {screen_type} [{game_name}] {hp_info} {enemy_info}",
        "tools": "Tools available: press_button, wait, fast_forward",
        "observation": "You see: {text_lines} | Menu: {menu_items}",
        "memory": "Recent: {recent_actions} | Party: {party_status}",
        "examples": [
            {"input": "What do you see?", "output": '{"action": "wait"}'},
        ],
    }
    if extra_layers:
        layers.update(extra_layers)

    yaml_path = gen_dir / f"{screen_type}.yaml"
    with open(yaml_path, "w", encoding="utf-8") as fh:
        yaml.dump(layers, fh, default_flow_style=False)

    if include_flow:
        flow = flow_content or {"flow": "GAME FLOW: Start → Oak's Lab → Route 1 → Viridian City"}
        flow_path = configs_dir / "flow.yaml"
        with open(flow_path, "w", encoding="utf-8") as fh:
            yaml.dump(flow, fh, default_flow_style=False)

    return configs_dir


class TestPromptStackWithTempDirs:
    """PromptStack tests using temp YAML directories (AC item 1)."""

    @pytest.fixture
    def configs_dir(self, tmp_path: Path) -> Path:
        return _make_temp_config(tmp_path)

    @pytest.fixture
    def configs_with_flow(self, tmp_path: Path) -> Path:
        return _make_temp_config(tmp_path, include_flow=True)

    # ── load_stack with temp dirs ──────────────────────────────────────

    def test_load_stack_happy_path(self, configs_dir: Path) -> None:
        ps = PromptStack(str(configs_dir))
        layers = ps.load_stack("gen1", "battle")
        assert isinstance(layers, dict)
        assert "system" in layers
        assert "tools" in layers
        assert "observation" in layers
        assert "memory" in layers
        assert "examples" in layers
        assert isinstance(layers["examples"], list)

    def test_load_stack_missing_file(self, configs_dir: Path) -> None:
        ps = PromptStack(str(configs_dir))
        with pytest.raises(FileNotFoundError) as exc_info:
            ps.load_stack("gen1", "nonexistent")
        assert "Prompt config not found" in str(exc_info.value)

    def test_load_stack_missing_generation(self, configs_dir: Path) -> None:
        ps = PromptStack(str(configs_dir))
        with pytest.raises(FileNotFoundError):
            ps.load_stack("gen9", "battle")

    def test_load_stack_returns_copy_not_ref(self, configs_dir: Path) -> None:
        """load_stack returns a dict copy — mutations don't affect cache."""
        ps = PromptStack(str(configs_dir))
        layers = ps.load_stack("gen1", "battle")
        layers["modified"] = "yes"
        # Second call should return original (unmodified)
        layers2 = ps.load_stack("gen1", "battle")
        assert "modified" not in layers2

    def test_load_stack_uses_cache(self, configs_dir: Path) -> None:
        """Second call to load_stack should return from cache (no re-read)."""
        ps = PromptStack(str(configs_dir))
        first = ps.load_stack("gen1", "battle")
        second = ps.load_stack("gen1", "battle")
        assert first == second
        assert "gen1/battle" in ps._cache

    # ── assemble with temp dirs ────────────────────────────────────────

    def test_assemble_basic(self, configs_dir: Path) -> None:
        ps = PromptStack(str(configs_dir))
        vision: Dict[str, Any] = {
            "screen_type": "battle",
            "enemy_pokemon": "Rattata",
            "player_hp_pct": 80,
            "enemy_hp_pct": 100,
            "text_lines": ["What will", "SQUIRTLE do?"],
            "menu_items": ["FIGHT", "BAG"],
        }
        memory: Dict[str, Any] = {
            "recent_actions": ["move north"],
            "party_status": "SQUIRTLE Lv7",
            "active_goal": "reach Viridian City",
        }
        result = ps.assemble("gen1", "battle", vision, memory)
        assert "battle" in result.lower()
        assert "Rattata" in result
        assert "80%" in result
        assert "100%" in result
        assert "SQUIRTLE" in result

    def test_assemble_flow_prepended(self, configs_with_flow: Path) -> None:
        """When flow.yaml exists, the flow text is prepended to the prompt."""
        ps = PromptStack(str(configs_with_flow))
        vision: Dict[str, Any] = {"screen_type": "battle"}
        memory: Dict[str, Any] = {
            "recent_actions": [],
            "party_status": "",
            "active_goal": "",
        }
        result = ps.assemble("gen1", "battle", vision, memory)
        assert "GAME FLOW" in result
        # Flow should appear before system layer content
        flow_pos = result.index("GAME FLOW")
        system_pos = result.index("System:")
        assert flow_pos < system_pos

    def test_assemble_no_flow(self, configs_dir: Path) -> None:
        """When flow.yaml doesn't exist, prompt assembles without flow section."""
        ps = PromptStack(str(configs_dir))
        vision: Dict[str, Any] = {"screen_type": "battle"}
        memory: Dict[str, Any] = {
            "recent_actions": [],
            "party_status": "",
            "active_goal": "",
        }
        result = ps.assemble("gen1", "battle", vision, memory)
        assert "GAME FLOW" not in result
        assert "System:" in result

    def test_assemble_with_missing_layer_values(self, configs_dir: Path) -> None:
        """SafeDict handles missing format keys gracefully."""
        ps = PromptStack(str(configs_dir))
        vision: Dict[str, Any] = {}
        memory: Dict[str, Any] = {}
        result = ps.assemble("gen1", "battle", vision, memory)
        # Should not crash; missing vars show as {key_name}
        assert "System:" in result

    # ── available_stacks with temp dirs ─────────────────────────────────

    def test_available_stacks_populated(self, configs_dir: Path) -> None:
        ps = PromptStack(str(configs_dir))
        stacks = ps.available_stacks()
        assert "gen1/battle" in stacks

    def test_available_stacks_multiple_files(self, tmp_path: Path) -> None:
        """Directory with multiple YAML files and non-YAML files."""
        configs = _make_temp_config(tmp_path, generation="gen1", screen_type="battle")
        # Add another screen type
        gen_dir = configs / "gen1"
        (gen_dir / "overworld.yaml").write_text("system: overworld prompt")
        # Add a non-YAML file that should be ignored
        (gen_dir / "README.txt").write_text("not a yaml file")
        ps = PromptStack(str(configs))
        stacks = ps.available_stacks()
        assert "gen1/battle" in stacks
        assert "gen1/overworld" in stacks
        assert "gen1/README" not in stacks  # .txt not .yaml

    def test_available_stacks_empty_directory(self, tmp_path: Path) -> None:
        """Config dir exists but has no YAML files."""
        configs_dir = tmp_path / "configs" / "prompts"
        gen_dir = configs_dir / "gen1"
        gen_dir.mkdir(parents=True, exist_ok=True)
        ps = PromptStack(str(configs_dir))
        stacks = ps.available_stacks()
        assert stacks == []

    def test_available_stacks_returns_sorted(self, tmp_path: Path) -> None:
        """available_stacks returns alphabetically sorted keys."""
        configs = _make_temp_config(tmp_path, generation="gen1", screen_type="c")
        gen_dir = configs / "gen1"
        (gen_dir / "a.yaml").write_text("system: a")
        (gen_dir / "b.yaml").write_text("system: b")
        ps = PromptStack(str(configs))
        stacks = ps.available_stacks()
        gen1_stacks = [s for s in stacks if s.startswith("gen1/")]
        assert gen1_stacks == ["gen1/a", "gen1/b", "gen1/c"]

    # ── _load_flow edge cases ──────────────────────────────────────────

    def test_load_flow_missing(self, configs_dir: Path) -> None:
        """When flow.yaml doesn't exist, _load_flow returns empty string."""
        ps = PromptStack(str(configs_dir))
        assert ps._flow == ""

    def test_load_flow_present(self, configs_with_flow: Path) -> None:
        ps = PromptStack(str(configs_with_flow))
        assert "GAME FLOW" in ps._flow

    def test_load_flow_missing_key(self, tmp_path: Path) -> None:
        """flow.yaml exists but has no 'flow' key."""
        configs = _make_temp_config(
            tmp_path, include_flow=True,
            flow_content={"other_key": "not the flow key"},
        )
        ps = PromptStack(str(configs))
        assert ps._flow == ""

    def test_load_flow_not_a_dict(self, tmp_path: Path) -> None:
        """flow.yaml is not a dict (e.g., a bare string)."""
        configs_dir = tmp_path / "configs" / "prompts"
        configs_dir.mkdir(parents=True)
        # Make a valid config for load_stack
        gen_dir = configs_dir / "gen1"
        gen_dir.mkdir()
        (gen_dir / "battle.yaml").write_text("system: test")
        # Write a non-dict flow.yaml
        (configs_dir / "flow.yaml").write_text("just a string, not a dict\n")
        ps = PromptStack(str(configs_dir))
        assert ps._flow == ""


# ════════════════════════════════════════════════════════════════════════════
# _format_layer — extended edge cases
# ════════════════════════════════════════════════════════════════════════════

class TestFormatLayerExtended:
    """Extended _format_layer tests for non-string, non-list types."""

    def test_format_int_template(self) -> None:
        """Template that is an int should be converted to str."""
        result = PromptStack._format_layer(42, SafeDict())
        assert result == "42"

    def test_format_dict_template(self) -> None:
        """Template that is a dict should be str()'d."""
        result = PromptStack._format_layer({"key": "val"}, SafeDict())
        assert "'key'" in result or '"key"' in result

    def test_format_empty_list(self) -> None:
        """Empty examples list should produce header only."""
        result = PromptStack._format_layer([], SafeDict())
        assert "Examples of correct responses:" in result
        # No Example N: lines
        assert "Example 1:" not in result

    def test_format_list_with_missing_keys(self) -> None:
        """Example list items missing input/output keys should not crash."""
        examples: List[Dict[str, str]] = [
            {"input": "What now?", "output": "wait"},
            {},  # empty dict — no input or output keys
            {"input": "Attack?"},
        ]
        result = PromptStack._format_layer(examples, SafeDict())
        assert "Example 1:" in result
        assert "Example 2:" in result
        assert "Example 3:" in result

    def test_format_list_string_preserves_braces(self) -> None:
        """Example list output with curly braces should NOT be format_mapped."""
        examples: List[Dict[str, str]] = [
            {
                "input": "What's happening?",
                "output": '{"action": "press_button", "button": "A"}',
            },
        ]
        result = PromptStack._format_layer(examples, SafeDict())
        # The JSON output should appear verbatim (not formatted)
        assert '{"action": "press_button"' in result


# ════════════════════════════════════════════════════════════════════════════
# PromptStack __init__ edge cases
# ════════════════════════════════════════════════════════════════════════════

class TestPromptStackInit:
    """PromptStack constructor edge cases."""

    def test_init_with_relative_path(self) -> None:
        """Init with a relative path — Path(configs_dir) is NOT resolved to absolute."""
        ps = PromptStack("configs/prompts")
        assert isinstance(ps._configs_dir, Path)
        assert not ps._configs_dir.is_absolute()
        assert str(ps._configs_dir) == "configs/prompts"

    def test_init_default_path(self) -> None:
        """Default configs_dir is 'configs/prompts'."""
        ps = PromptStack()
        assert ps._configs_dir.name == "prompts"
        assert str(ps._configs_dir).endswith("configs/prompts")

    def test_init_creates_empty_cache(self) -> None:
        ps = PromptStack()
        assert ps._cache == {}


# ════════════════════════════════════════════════════════════════════════════
# Module-level constants
# ════════════════════════════════════════════════════════════════════════════

class TestModuleConstants:
    """Verify module-level constants are correct."""

    def test_game_names(self) -> None:
        assert GAME_NAMES["gen1"] == "Pokémon Red/Blue/Yellow"
        assert GAME_NAMES["gen3"] == "Pokémon FireRed/LeafGreen"

    def test_gen_labels(self) -> None:
        assert GEN_LABELS["gen1"] == "Generation 1 (Game Boy)"
        assert GEN_LABELS["gen3"] == "Generation 3 (Game Boy Advance)"

    def test_layer_order(self) -> None:
        assert LAYER_ORDER == ("system", "tools", "observation", "memory", "examples")


# ════════════════════════════════════════════════════════════════════════════
# assemble — menu_options fallback and enemy_info injection
# ════════════════════════════════════════════════════════════════════════════

class TestAssembleInjection:
    """Tests for format_map injection paths through assemble()."""

    @pytest.fixture
    def configs_dir(self, tmp_path: Path) -> Path:
        return _make_temp_config(tmp_path)

    def test_menu_options_fallback(self, configs_dir: Path) -> None:
        """menu_options is used as fallback when menu_items is missing."""
        ps = PromptStack(str(configs_dir))
        vision: Dict[str, Any] = {
            "screen_type": "battle",
            "menu_options": ["START", "SAVE", "OPTIONS"],
        }
        memory: Dict[str, Any] = {
            "recent_actions": [],
            "party_status": "",
            "active_goal": "",
        }
        result = ps.assemble("gen1", "battle", vision, memory)
        assert "START" in result

    def test_gen1_game_name(self, configs_dir: Path) -> None:
        ps = PromptStack(str(configs_dir))
        result = ps.assemble("gen1", "battle", {}, {})
        assert "Red/Blue/Yellow" in result

    def test_unknown_generation(self, tmp_path: Path) -> None:
        """Unknown generation string — load_stack raises FileNotFoundError when no config."""
        configs = _make_temp_config(tmp_path, generation="gen1", screen_type="battle")
        ps = PromptStack(str(configs))
        # gen9 doesn't exist as a config directory — expect FileNotFoundError
        with pytest.raises(FileNotFoundError):
            ps.assemble("gen9", "battle", {"screen_type": "battle"}, {})

    def test_assemble_with_party_status_string(self, configs_dir: Path) -> None:
        """party_status as a plain string (not dict/list)."""
        ps = PromptStack(str(configs_dir))
        memory: Dict[str, Any] = {
            "recent_actions": [],
            "party_status": "CHARMANDER Lv5",
            "active_goal": "",
        }
        result = ps.assemble("gen1", "battle", {"screen_type": "battle"}, memory)
        assert "CHARMANDER" in result

    def test_assemble_with_empty_active_goal(self, configs_dir: Path) -> None:
        """active_goal is empty string — should not crash."""
        ps = PromptStack(str(configs_dir))
        memory: Dict[str, Any] = {
            "recent_actions": [],
            "party_status": "",
            "active_goal": "",
        }
        result = ps.assemble("gen1", "battle", {"screen_type": "battle"}, memory)
        assert "battle" in result.lower()
