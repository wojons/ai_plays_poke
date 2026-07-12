"""Unit tests for prompt_loader.py — YAML-based system prompt loading."""

import yaml

import src.core.prompt_loader as pl


# ── Helpers ──────────────────────────────────────────────────────────────

def write_prompt(dir_path, filename, content):
    """Write a YAML prompt file with either 'system' or 'system_extra' key."""
    path = dir_path / filename
    path.write_text(yaml.dump(content))
    return path


def setup_prompts_dir(tmp_path, core_content=None, hint_contents=None):
    """Set up a temp prompts directory with core.yaml and optional hint files.

    Returns (prompts_dir, hints_dir).
    """
    prompts_dir = tmp_path / "prompts" / "gen1"
    hints_dir = prompts_dir / "hints"
    hints_dir.mkdir(parents=True)

    # Write core.yaml
    if core_content:
        write_prompt(prompts_dir, "core.yaml", core_content)
    else:
        write_prompt(prompts_dir, "core.yaml", {"system": "CORE PROMPT"})

    # Write hint files
    if hint_contents:
        for i, content in enumerate(hint_contents):
            write_prompt(hints_dir, f"0{i+1}_mechanics.yaml" if i == 0 else
                         f"0{i+1}_genre.yaml" if i == 1 else
                         f"0{i+1}_starter.yaml" if i == 2 else
                         f"0{i+1}_navigation.yaml", content)

    return prompts_dir, hints_dir


# ── get_text_content() ───────────────────────────────────────────────────

class TestGetTextContent:
    """Test extracting text_content or text_lines from vision dicts."""

    def test_text_content_present(self):
        result = pl.get_text_content({"text_content": ["line1", "line2"]})
        assert result == ["line1", "line2"]

    def test_text_content_empty_list(self):
        result = pl.get_text_content({"text_content": []})
        assert result == []

    def test_text_content_not_list_falls_back(self):
        """text_content is a string, not a list — should fall back."""
        result = pl.get_text_content({"text_content": "not a list", "text_lines": ["a"]})
        assert result == ["a"]

    def test_text_lines_fallback(self):
        result = pl.get_text_content({"text_lines": ["fallback1", "fallback2"]})
        assert result == ["fallback1", "fallback2"]

    def test_text_lines_empty_list(self):
        result = pl.get_text_content({"text_lines": []})
        assert result == []

    def test_both_empty(self):
        result = pl.get_text_content({})
        assert result == []

    def test_neither_present(self):
        result = pl.get_text_content({"other": "data"})
        assert result == []

    def test_text_content_takes_priority(self):
        result = pl.get_text_content({
            "text_content": ["primary"],
            "text_lines": ["fallback"]
        })
        assert result == ["primary"]

    def test_text_lines_not_list(self):
        """text_lines is a string — should not return it."""
        result = pl.get_text_content({"text_lines": "not a list"})
        assert result == []

    def test_both_not_lists_returns_empty(self):
        result = pl.get_text_content({"text_content": "x", "text_lines": "y"})
        assert result == []


# ── _load_yaml_system() ──────────────────────────────────────────────────

class TestLoadYamlSystem:
    """Test the internal _load_yaml_system helper."""

    def test_loads_system_key(self, tmp_path):
        write_prompt(tmp_path, "test.yaml", {"system": "Hello World"})
        result = pl._load_yaml_system(tmp_path / "test.yaml")
        assert result == "Hello World"

    def test_loads_system_extra_key(self, tmp_path):
        write_prompt(tmp_path, "test.yaml", {"system_extra": "Extra Content"})
        result = pl._load_yaml_system(tmp_path / "test.yaml")
        assert result == "Extra Content"

    def test_prefers_system_over_system_extra(self, tmp_path):
        write_prompt(tmp_path, "test.yaml", {
            "system": "primary",
            "system_extra": "secondary"
        })
        result = pl._load_yaml_system(tmp_path / "test.yaml")
        assert result == "primary"

    def test_empty_dict_returns_empty_string(self, tmp_path):
        write_prompt(tmp_path, "test.yaml", {})
        result = pl._load_yaml_system(tmp_path / "test.yaml")
        assert result == ""

    def test_nondict_yaml_returns_empty_string(self, tmp_path):
        """YAML that parses to a list, not a dict."""
        path = tmp_path / "test.yaml"
        path.write_text("- item1\n- item2\n")
        result = pl._load_yaml_system(path)
        assert result == ""

    def test_missing_both_keys_returns_empty_string(self, tmp_path):
        write_prompt(tmp_path, "test.yaml", {"other": "data", "more": 42})
        result = pl._load_yaml_system(tmp_path / "test.yaml")
        assert result == ""

    def test_integer_value_converted_to_string(self, tmp_path):
        write_prompt(tmp_path, "test.yaml", {"system": 12345})
        result = pl._load_yaml_system(tmp_path / "test.yaml")
        assert result == "12345"
        assert isinstance(result, str)

    def test_boolean_value_converted_to_string(self, tmp_path):
        write_prompt(tmp_path, "test.yaml", {"system": True})
        result = pl._load_yaml_system(tmp_path / "test.yaml")
        assert result == "True"
        assert isinstance(result, str)


# ── load_system_prompt() — core + hint stacking ──────────────────────────

class TestLoadSystemPrompt:
    """Test the composed system prompt loading with hint levels."""

    def _patch_dirs(self, monkeypatch, prompts_dir, hints_dir):
        """Monkeypatch module-level _PROMPTS_DIR and _HINTS_DIR."""
        monkeypatch.setattr(pl, "_PROMPTS_DIR", prompts_dir)
        monkeypatch.setattr(pl, "_HINTS_DIR", hints_dir)

    def _clear_cache(self):
        pl._cache.clear()

    # ── Hint level 0 (benchmark = core only) ────────────────────────────

    def test_level_0_loads_core_only(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"},
            hint_contents=[{"system": "HINT1"}, {"system": "HINT2"}]
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=0)
        assert result == "CORE"
        assert "HINT1" not in result
        assert "HINT2" not in result

    # ── Hint level 1 ────────────────────────────────────────────────────

    def test_level_1_loads_core_plus_mechanics(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"},
            hint_contents=[{"system": "MECHANICS"}, {"system": "GENRE"}]
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=1)
        assert "CORE" in result
        assert "MECHANICS" in result
        assert "GENRE" not in result

    # ── Hint level 2 ────────────────────────────────────────────────────

    def test_level_2_loads_core_plus_two_hints(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"},
            hint_contents=[
                {"system": "MECHANICS"}, {"system": "GENRE"}, {"system": "STARTER"}
            ]
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=2)
        assert "CORE" in result
        assert "MECHANICS" in result
        assert "GENRE" in result
        assert "STARTER" not in result

    # ── Hint level 3 ────────────────────────────────────────────────────

    def test_level_3_loads_three_hints(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"},
            hint_contents=[
                {"system": "MECH"}, {"system": "GENRE"}, {"system": "START"},
                {"system": "NAV"}
            ]
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=3)
        assert "CORE" in result
        assert "MECH" in result
        assert "GENRE" in result
        assert "START" in result
        assert "NAV" not in result

    # ── Hint level 4 ────────────────────────────────────────────────────

    def test_level_4_loads_all_hints(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"},
            hint_contents=[
                {"system": "MECH"}, {"system": "GENRE"}, {"system": "START"},
                {"system": "NAV"}
            ]
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=4)
        assert "CORE" in result
        assert "MECH" in result
        assert "GENRE" in result
        assert "START" in result
        assert "NAV" in result

    # ── Hint level > 4 ──────────────────────────────────────────────────

    def test_level_5_clamped_to_4(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"},
            hint_contents=[
                {"system": "H1"}, {"system": "H2"}, {"system": "H3"}, {"system": "H4"}
            ]
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=5)
        assert "H4" in result
        # h5 shouldn't exist anyway, but range clamps

    # ── Missing core.yaml ───────────────────────────────────────────────

    def test_missing_core_returns_empty(self, tmp_path, monkeypatch):
        prompts_dir = tmp_path / "prompts" / "gen1"
        hints_dir = prompts_dir / "hints"
        hints_dir.mkdir(parents=True)
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=0)
        assert result == ""

    # ── Missing hint files ──────────────────────────────────────────────

    def test_missing_hint_files_skipped(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"}
            # No hint files at all
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=4)
        assert result == "CORE"

    def test_partial_hint_files(self, tmp_path, monkeypatch):
        """Only hint files 1 and 3 exist — 2 and 4 missing."""
        prompts_dir = tmp_path / "prompts" / "gen1"
        hints_dir = prompts_dir / "hints"
        hints_dir.mkdir(parents=True)

        write_prompt(prompts_dir, "core.yaml", {"system": "CORE"})
        write_prompt(hints_dir, "01_mechanics.yaml", {"system": "H1"})
        write_prompt(hints_dir, "03_starter.yaml", {"system": "H3"})
        # 02 and 04 missing

        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=4)
        assert "CORE" in result
        assert "H1" in result
        assert "H3" in result
        # H2 and H4 should be missing — gaps are fine

    def test_hint_with_empty_system_skipped(self, tmp_path, monkeypatch):
        """A hint file exists but has no system/system_extra key."""
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"},
            hint_contents=[
                {"system": "H1"},
                {"other": "data"},  # no system key → skipped
                {"system": "H3"},
            ]
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=4)
        assert "CORE" in result
        assert "H1" in result
        assert "H3" in result
        # "data" should not appear
        assert "data" not in result

    def test_hint_with_system_extra_loaded(self, tmp_path, monkeypatch):
        """Hint files using system_extra key."""
        prompts_dir = tmp_path / "prompts" / "gen1"
        hints_dir = prompts_dir / "hints"
        hints_dir.mkdir(parents=True)

        write_prompt(prompts_dir, "core.yaml", {"system": "CORE"})
        write_prompt(hints_dir, "01_mechanics.yaml", {"system_extra": "HINT1"})
        write_prompt(hints_dir, "02_genre.yaml", {"system_extra": "HINT2"})

        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=2)
        assert "HINT1" in result
        assert "HINT2" in result

    # ── Cache behavior ──────────────────────────────────────────────────

    def test_caches_results(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"}
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result1 = pl.load_system_prompt(hint_level=0)
        # Delete the core file — should still return cached result
        (prompts_dir / "core.yaml").unlink()
        result2 = pl.load_system_prompt(hint_level=0)
        assert result1 == result2

    def test_different_levels_cached_separately(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"},
            hint_contents=[{"system": "H1"}, {"system": "H2"}]
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        r0 = pl.load_system_prompt(hint_level=0)
        r2 = pl.load_system_prompt(hint_level=2)
        assert r0 != r2  # different levels produce different output
        # And both are cached
        assert 0 in pl._cache
        assert 2 in pl._cache
        assert pl._cache[0] == r0
        assert pl._cache[2] == r2

    def test_negative_hint_level(self, tmp_path, monkeypatch):
        """Negative hint level — range(min(neg, 4)) = range(neg) = empty."""
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "CORE"},
            hint_contents=[{"system": "H1"}]
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=-1)
        assert result == "CORE"  # no hints loaded for negative

    # ── Parts joined by double newline ──────────────────────────────────

    def test_parts_joined_by_double_newline(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path,
            core_content={"system": "AAA"},
            hint_contents=[{"system": "BBB"}, {"system": "CCC"}]
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        self._clear_cache()

        result = pl.load_system_prompt(hint_level=2)
        assert result == "AAA\n\nBBB\n\nCCC"

    # ── Integration: real fixture files (if available) ──────────────────

    def test_loads_real_core_yaml(self):
        """Load the actual core.yaml from the project — smoke test."""
        self._clear_cache()
        result = pl.load_system_prompt(hint_level=0)
        assert isinstance(result, str)
        assert len(result) > 0
        # Core should contain essential Pokémon terminology
        assert "pokémon" in result.lower() or "game" in result.lower()

    def test_loads_real_full_stack(self):
        """Load actual core + all 4 hints — smoke test."""
        self._clear_cache()
        result = pl.load_system_prompt(hint_level=4)
        assert isinstance(result, str)
        assert len(result) > 0


# ── Edge Cases ───────────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases and error scenarios."""

    @staticmethod
    def _patch_dirs(monkeypatch, prompts_dir, hints_dir):
        monkeypatch.setattr(pl, "_PROMPTS_DIR", prompts_dir)
        monkeypatch.setattr(pl, "_HINTS_DIR", hints_dir)

    def test_load_system_prompt_multiple_calls_uses_cache(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path, core_content={"system": "CORE"}
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        pl._cache.clear()

        first = pl.load_system_prompt(hint_level=0)
        # Modify the file on disk (shouldn't affect cached result)
        write_prompt(prompts_dir, "core.yaml", {"system": "MODIFIED"})
        second = pl.load_system_prompt(hint_level=0)
        assert second == first  # cache hit
        assert "MODIFIED" not in second

    def test_load_system_prompt_then_cache_clear_reloads(self, tmp_path, monkeypatch):
        prompts_dir, hints_dir = setup_prompts_dir(
            tmp_path, core_content={"system": "ORIGINAL"}
        )
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        pl._cache.clear()

        first = pl.load_system_prompt(hint_level=0)
        write_prompt(prompts_dir, "core.yaml", {"system": "UPDATED"})
        pl._cache.clear()
        second = pl.load_system_prompt(hint_level=0)
        assert second == "UPDATED"
        assert second != first

    def test_core_with_multiline_system_value(self, tmp_path, monkeypatch):
        prompts_dir = tmp_path / "prompts" / "gen1"
        hints_dir = prompts_dir / "hints"
        hints_dir.mkdir(parents=True)

        path = prompts_dir / "core.yaml"
        path.write_text("system: |\n  Line 1\n  Line 2\n  Line 3\n")
        self._patch_dirs(monkeypatch, prompts_dir, hints_dir)
        pl._cache.clear()

        result = pl.load_system_prompt(hint_level=0)
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result

    def test_cache_cleared_between_tests(self):
        """Cache from a previous test shouldn't leak. This test runs last and
        verifies the cache is empty (or can be cleared)."""
        pl._cache.clear()
        assert pl._cache == {}

    def test_module_globals_point_at_real_dirs(self):
        """Sanity check: the module-level paths exist on disk."""
        assert pl._PROMPTS_DIR.exists()
        assert pl._HINTS_DIR.exists()
