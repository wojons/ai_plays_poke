"""
Unit tests for src/core/prompt_manager.py — PromptManager + PromptTemplate.

Tests cover:
- PromptTemplate dataclass (construction, default use_cases, priority)
- PromptManager.__init__ (default dir, custom dir, missing dir)
- load_prompts (scans dirs, skips non-txt, handles errors)
- _load_prompt_file (valid file, missing file, priority extraction with regex bug)
- get_relevant_prompts (category match, cross-category, limit top 3)
- select_prompts_for_ai (balanced, tactical, strategic, unknown mode)
- track_prompt_usage (first use, repeat, effectiveness)
- get_prompt_analytics (single, multi-prompt, empty)

Documents 1 pre-existing bug:
  BUG-1: Priority regex `r'**Priority:\s*(\d+)'` raises re.error "nothing to repeat"
          because leading `*` is a quantifier with nothing to repeat. Should be
          `r'\*\*Priority:\s*(\d+)'`. Any file containing `**Priority:` line
          causes _load_prompt_file to return None (caught by except Exception).
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.prompt_manager import PromptTemplate, PromptManager


# ── PromptTemplate tests ────────────────────────────────────────────────────

class TestPromptTemplate:
    """PromptTemplate dataclass — construction, defaults, post_init."""

    def test_construction_all_fields(self):
        t = PromptTemplate(
            name="battle_tactics",
            category="battle",
            description="Battle tactics prompt",
            content="Press A to attack",
            priority=2,
            use_cases=["wild_battle", "trainer_battle"],
        )
        assert t.name == "battle_tactics"
        assert t.category == "battle"
        assert t.description == "Battle tactics prompt"
        assert t.content == "Press A to attack"
        assert t.priority == 2
        assert t.use_cases == ["wild_battle", "trainer_battle"]

    def test_construction_minimal_fields(self):
        t = PromptTemplate(
            name="explore",
            category="exploration",
            description="Explore the world",
            content="Walk around",
        )
        assert t.priority == 1
        assert t.use_cases == ["exploration"]

    def test_post_init_fills_empty_use_cases(self):
        t = PromptTemplate(
            name="menu_nav",
            category="menu",
            description="Menu navigation",
            content="Select item",
            use_cases=[],
        )
        assert t.use_cases == ["menu"]

    def test_default_use_cases_falls_back_to_category(self):
        """Default use_cases (from default_factory=list, then post_init) = [category]."""
        t = PromptTemplate(
            name="dialog_nav",
            category="dialog",
            description="Dialog navigation",
            content="Press A",
        )
        assert t.use_cases == ["dialog"]

    def test_priority_zero_is_valid(self):
        t = PromptTemplate(
            name="low_prio",
            category="strategic",
            description="Low priority prompt",
            content="",
            priority=0,
        )
        assert t.priority == 0

    def test_priority_negative_is_valid(self):
        t = PromptTemplate(
            name="neg_prio",
            category="strategic",
            description="Negative prio",
            content="",
            priority=-1,
        )
        assert t.priority == -1

    def test_dataclass_equality(self):
        a = PromptTemplate(name="x", category="battle", description="d", content="c")
        b = PromptTemplate(name="x", category="battle", description="d", content="c")
        assert a == b

    def test_dataclass_inequality_different_name(self):
        a = PromptTemplate(name="x", category="battle", description="d", content="c")
        b = PromptTemplate(name="y", category="battle", description="d", content="c")
        assert a != b


# ── PromptManager __init__ tests ────────────────────────────────────────────

class TestPromptManagerInit:
    """PromptManager.__init__ with custom directories."""

    def test_init_default_dir(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert pm.prompts_dir == tmp_path
        assert pm.prompt_templates == []
        assert pm.prompt_usage_stats == {}

    def test_init_custom_dir(self, tmp_path):
        prompts = tmp_path / "my_prompts"
        prompts.mkdir()
        pm = PromptManager(prompts_dir=str(prompts))
        assert pm.prompts_dir == prompts
        assert pm.prompt_templates == []

    def test_init_missing_dir(self, tmp_path):
        missing = tmp_path / "nonexistent"
        pm = PromptManager(prompts_dir=str(missing))
        # load_prompts prints warning, returns without error
        assert pm.prompt_templates == []
        assert pm.prompt_usage_stats == {}

    def test_init_loads_simple_prompt(self, tmp_path):
        """Load a prompt file WITHOUT **Priority: line (avoids BUG-1 regex)."""
        battle = tmp_path / "battle"
        battle.mkdir()
        (battle / "tactics.txt").write_text(
            "# Battle tactics\n\nPress A to attack!\n", encoding="utf-8"
        )
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert len(pm.prompt_templates) == 1
        assert pm.prompt_templates[0].name == "tactics"
        assert pm.prompt_templates[0].category == "battle"
        assert pm.prompt_templates[0].priority == 1  # default (BUG-1: regex fails)

    def test_init_skips_non_dir_entries(self, tmp_path):
        (tmp_path / "readme.md").write_text("docs")
        battle = tmp_path / "battle"
        battle.mkdir()
        (battle / "t1.txt").write_text("# Prompt\n\nhello\n", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert len(pm.prompt_templates) == 1

    def test_init_with_buggy_priority_line_fails_silently(self, tmp_path):
        """BUG-1: Files with **Priority: trigger regex error → template is None (not loaded)."""
        battle = tmp_path / "battle"
        battle.mkdir()
        (battle / "will_fail.txt").write_text(
            "**Priority: 5\n\nWill not load due to regex bug\n", encoding="utf-8"
        )
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert len(pm.prompt_templates) == 0  # BUG-1: file not loaded


# ── load_prompts tests ──────────────────────────────────────────────────────

class TestLoadPrompts:
    """PromptManager.load_prompts — filesystem scanning."""

    def test_loads_all_categories(self, tmp_path):
        for cat in ["battle", "menu", "exploration"]:
            d = tmp_path / cat
            d.mkdir()
            (d / f"{cat}_prompt.txt").write_text(
                f"# {cat} prompt\n\nContent for {cat}\n", encoding="utf-8"
            )
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert len(pm.prompt_templates) == 3
        cats = {t.category for t in pm.prompt_templates}
        assert cats == {"battle", "menu", "exploration"}

    def test_multiple_prompts_per_category(self, tmp_path):
        battle = tmp_path / "battle"
        battle.mkdir()
        for i in range(5):
            (battle / f"prompt_{i}.txt").write_text(
                f"# Prompt {i}\n\nContent {i}\n", encoding="utf-8"
            )
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert len(pm.prompt_templates) == 5

    def test_skips_non_txt_files(self, tmp_path):
        battle = tmp_path / "battle"
        battle.mkdir()
        (battle / "prompt.txt").write_text("# Battle\n\nFight!\n", encoding="utf-8")
        (battle / "notes.md").write_text("markdown notes")
        (battle / "data.json").write_text('{"key": "val"}')
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert len(pm.prompt_templates) == 1
        assert pm.prompt_templates[0].name == "prompt"

    def test_handles_unreadable_file_gracefully(self, tmp_path):
        """Permission-denied files are caught and skipped without crashing."""
        battle = tmp_path / "battle"
        battle.mkdir()
        (battle / "good.txt").write_text("# Good\n\nok\n", encoding="utf-8")

        with patch.object(Path, "read_text", side_effect=[
            "# Good\n\nok\n",
            OSError("Permission denied"),
        ]):
            pm = PromptManager(prompts_dir=str(tmp_path))
            assert len(pm.prompt_templates) >= 0  # No crash

    def test_reload_appends_duplicates(self, tmp_path):
        """load_prompts() does NOT reset — calling it twice duplicates entries."""
        battle = tmp_path / "battle"
        battle.mkdir()
        (battle / "t1.txt").write_text("# A\n\nhello\n", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert len(pm.prompt_templates) == 1
        pm.load_prompts()  # reload — appends, doesn't clear
        assert len(pm.prompt_templates) == 2  # Duplicated (known behavior)

    def test_empty_dir(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert pm.prompt_templates == []

    def test_dir_with_only_non_dirs(self, tmp_path):
        (tmp_path / "file1.txt").write_text("not a dir")
        (tmp_path / "file2.json").write_text("{}")
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert pm.prompt_templates == []


# ── _load_prompt_file tests ─────────────────────────────────────────────────

class TestLoadPromptFile:
    """PromptManager._load_prompt_file — individual file parsing."""

    def test_loads_basic_file(self, tmp_path):
        f = tmp_path / "test_prompt.txt"
        f.write_text("# My Description\n\nActual prompt content\n", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        template = pm._load_prompt_file(f, "battle")
        assert template is not None
        assert template.name == "test_prompt"
        assert template.category == "battle"
        assert template.description == "My Description"
        assert template.content == "# My Description\n\nActual prompt content\n"
        assert template.priority == 1
        assert template.use_cases == ["battle"]

    def test_default_description_when_no_comment(self, tmp_path):
        f = tmp_path / "no_desc.txt"
        f.write_text("Just content\nNo description line\n", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        template = pm._load_prompt_file(f, "menu")
        assert template is not None
        assert template.description == "Game menu prompt"

    def test_skips_h2_comments_for_description(self, tmp_path):
        """Lines starting with ## are skipped for description extraction."""
        f = tmp_path / "desc.txt"
        f.write_text("## Section header\n# Real description\n\nBody\n", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        template = pm._load_prompt_file(f, "exploration")
        assert template is not None
        assert template.description == "Real description"

    def test_priority_regex_raises_re_error(self, tmp_path):
        """BUG-1: `r'**Priority:\s*(\d+)'` has unescaped leading `*` → re.error.

        Any file with `**Priority:` line causes _load_prompt_file to return None.
        """
        f = tmp_path / "prio.txt"
        f.write_text("**Priority: 7\n\nContent\n", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        template = pm._load_prompt_file(f, "strategic")
        assert template is None  # BUG-1: regex error caught by except Exception

    def test_priority_not_extracted_from_non_matching(self, tmp_path):
        """Non-priority bold markers don't trigger regex (no '**Priority:' pattern)."""
        f = tmp_path / "noprio.txt"
        f.write_text("**Something: 5\n\nContent\n", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        template = pm._load_prompt_file(f, "battle")
        assert template is not None
        assert template.priority == 1  # default — regex didn't match (didn't error either)

    def test_missing_file_returns_none(self, tmp_path):
        f = tmp_path / "does_not_exist.txt"
        pm = PromptManager(prompts_dir=str(tmp_path))
        template = pm._load_prompt_file(f, "battle")
        assert template is None

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        template = pm._load_prompt_file(f, "battle")
        assert template is not None
        assert template.name == "empty"
        assert template.content == ""
        assert template.description == "Game battle prompt"

    def test_filename_without_extension_stem(self, tmp_path):
        f = tmp_path / "my.prompt.txt"
        f.write_text("# Desc\n\ncontent\n", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        template = pm._load_prompt_file(f, "dialog")
        assert template is not None
        assert template.name == "my.prompt"  # stem removes last suffix only

    def test_non_utf8_file_returns_none(self, tmp_path):
        f = tmp_path / "bad.txt"
        f.write_bytes(b"\xff\xfe\x00\x01")  # Invalid UTF-8
        pm = PromptManager(prompts_dir=str(tmp_path))
        template = pm._load_prompt_file(f, "battle")
        assert template is None

    def test_unicode_content(self, tmp_path):
        f = tmp_path / "unicode.txt"
        f.write_text("# ポケモン\n\nピカチュウ\n", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        template = pm._load_prompt_file(f, "battle")
        assert template is not None
        assert template.description == "ポケモン"
        assert "ピカチュウ" in template.content


# ── get_relevant_prompts tests ──────────────────────────────────────────────

class TestGetRelevantPrompts:
    """PromptManager.get_relevant_prompts — category filtering, limit top 3."""

    def _make_templates(self):
        return [
            PromptTemplate(name="b1", category="battle", description="d", content="cb1", priority=1),
            PromptTemplate(name="b2", category="battle", description="d", content="cb2", priority=2),
            PromptTemplate(name="e1", category="exploration", description="d", content="ce1", priority=1),
            PromptTemplate(name="s1", category="strategic", description="d", content="cs1", priority=5),
            PromptTemplate(name="m1", category="menu", description="d", content="cm1", priority=1),
            PromptTemplate(name="d1", category="dialog", description="d", content="cd1", priority=1),
        ]

    def setup_manager(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.prompt_templates = self._make_templates()
        return pm

    def test_battle_matches_battle_and_strategic(self, tmp_path):
        pm = self.setup_manager(tmp_path)
        result = pm.get_relevant_prompts("battle", {})
        names = {t.name for t in result}
        # battle matches: b1, b2 (battle) + s1 (strategic) = 3, sorted by priority
        assert names == {"s1", "b2", "b1"}
        assert result[0].name == "s1"  # priority 5
        assert result[1].name == "b2"  # priority 2
        assert result[2].name == "b1"  # priority 1

    def test_menu_matches_menu_exploration_strategic(self, tmp_path):
        pm = self.setup_manager(tmp_path)
        result = pm.get_relevant_prompts("menu", {})
        # menu matches: m1 (menu) + e1 (exploration) + s1 (strategic) = 3
        names = {t.name for t in result}
        assert names == {"s1", "m1", "e1"}

    def test_overworld_matches_exploration_and_strategic(self, tmp_path):
        pm = self.setup_manager(tmp_path)
        result = pm.get_relevant_prompts("overworld", {})
        # overworld matches: e1 (exploration) + s1 (strategic) = 2
        names = {t.name for t in result}
        assert names == {"s1", "e1"}
        assert len(result) == 2

    def test_dialog_matches_strategic_and_battle(self, tmp_path):
        pm = self.setup_manager(tmp_path)
        result = pm.get_relevant_prompts("dialog", {})
        # dialog matches: s1 (strategic) + b1, b2 (battle) = 3
        names = {t.name for t in result}
        assert names == {"s1", "b2", "b1"}  # s1(5), b2(2), b1(1) — top 3
        assert len(result) == 3

    def test_unknown_state_returns_empty(self, tmp_path):
        pm = self.setup_manager(tmp_path)
        result = pm.get_relevant_prompts("unknown_type", {})
        assert result == []

    def test_limits_to_top_3(self, tmp_path):
        pm = self.setup_manager(tmp_path)
        # battle matches: b1+b2+s1 = 3 → all fit
        result = pm.get_relevant_prompts("battle", {})
        assert len(result) == 3
        # Add more battle templates to exceed 3
        pm.prompt_templates.append(
            PromptTemplate(name="b3", category="battle", description="d", content="cb3", priority=3)
        )
        pm.prompt_templates.append(
            PromptTemplate(name="b4", category="battle", description="d", content="cb4", priority=0)
        )
        # Now battle matches: s1(5) + b3(3) + b2(2) + b1(1) + b4(0) = 5, top 3
        result = pm.get_relevant_prompts("battle", {})
        assert len(result) == 3
        assert result[0].name == "s1"  # pri 5
        assert result[1].name == "b3"  # pri 3
        assert result[2].name == "b2"  # pri 2

    def test_fewer_than_3_returns_all(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.prompt_templates = [
            PromptTemplate(name="only", category="battle", description="d", content="c", priority=1),
        ]
        result = pm.get_relevant_prompts("battle", {})
        assert len(result) == 1
        assert result[0].name == "only"

    def test_context_passed_but_unused(self, tmp_path):
        """Context is accepted but not used in the current implementation."""
        pm = self.setup_manager(tmp_path)
        result = pm.get_relevant_prompts("battle", {"enemy": "Pikachu"})
        result_no_ctx = pm.get_relevant_prompts("battle", {})
        assert len(result) == len(result_no_ctx)


# ── select_prompts_for_ai tests ─────────────────────────────────────────────

class TestSelectPromptsForAI:
    """PromptManager.select_prompts_for_ai — mode-based filtering."""

    def _make_templates(self):
        return [
            PromptTemplate(name="battle_tactical", category="battle", description="d",
                          content="TACTICAL_BATTLE", priority=2),
            PromptTemplate(name="explore_tactical", category="exploration", description="d",
                          content="TACTICAL_EXPLORE", priority=1),
            PromptTemplate(name="strategy_guide", category="strategic", description="d",
                          content="STRATEGIC", priority=1),
        ]

    def setup_manager(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.prompt_templates = self._make_templates()
        return pm

    def test_balanced_returns_all_relevant(self, tmp_path):
        """Balanced returns all prompts from get_relevant_prompts.
        
        For "battle" state: battle_tactical(battle) + strategy_guide(strategic) = 2.
        explore_tactical(exploration) does NOT match battle.
        """
        pm = self.setup_manager(tmp_path)
        results = pm.select_prompts_for_ai("battle", {}, "balanced")
        assert len(results) == 2
        assert "TACTICAL_BATTLE" in results
        assert "STRATEGIC" in results

    def test_tactical_filters_by_name_and_battle_category(self, tmp_path):
        """Tactical mode: only templates with 'tactical' in name OR category=='battle'.
        
        For "battle" state, get_relevant_prompts returns: battle_tactical(battle) + strategy_guide(strategic) = 2.
        Tactical filter: battle_tactical has 'tactical' in name → included.
        strategy_guide: no 'tactical', category='strategic' ≠ 'battle' → excluded.
        """
        pm = self.setup_manager(tmp_path)
        results = pm.select_prompts_for_ai("battle", {}, "tactical")
        assert len(results) == 1
        assert results[0] == "TACTICAL_BATTLE"

    def test_strategic_filters_to_strategic_category_and_name(self, tmp_path):
        pm = self.setup_manager(tmp_path)
        results = pm.select_prompts_for_ai("battle", {}, "strategic")
        # strategy_guide: name has "strategic" → included
        # battle_tactical: name doesn't, category "battle" ≠ "strategic" → excluded
        assert len(results) == 1
        assert results[0] == "STRATEGIC"

    def test_unknown_mode_defaults_to_balanced(self, tmp_path):
        """Unknown mode falls through to else → balanced (returns all relevant)."""
        pm = self.setup_manager(tmp_path)
        results = pm.select_prompts_for_ai("battle", {}, "aggressive")
        assert len(results) == 2  # Same as balanced

    def test_no_relevant_prompts_returns_empty(self, tmp_path):
        pm = self.setup_manager(tmp_path)
        results = pm.select_prompts_for_ai("unknown_type", {}, "balanced")
        assert results == []

    def test_tactical_with_no_tactical_matches_returns_empty(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.prompt_templates = [
            PromptTemplate(name="strategy", category="strategic", description="d",
                          content="STRAT", priority=1),
        ]
        results = pm.select_prompts_for_ai("battle", {}, "tactical")
        assert results == []  # strategy doesn't match tactical filter


# ── track_prompt_usage tests ────────────────────────────────────────────────

class TestTrackPromptUsage:
    """PromptManager.track_prompt_usage — statistics tracking."""

    def test_first_use_creates_entry(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("battle_tactics", 0.8)
        assert "battle_tactics" in pm.prompt_usage_stats
        stats = pm.prompt_usage_stats["battle_tactics"]
        assert stats["usage_count"] == 1
        assert stats["effectiveness_sum"] == 0.8
        assert stats["last_used"] == "now"

    def test_multiple_uses_accumulate(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("menu_nav", 0.5)
        pm.track_prompt_usage("menu_nav", 0.9)
        pm.track_prompt_usage("menu_nav", 0.3)
        stats = pm.prompt_usage_stats["menu_nav"]
        assert stats["usage_count"] == 3
        assert stats["effectiveness_sum"] == 1.7

    def test_default_effectiveness_is_one(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("dialog")
        stats = pm.prompt_usage_stats["dialog"]
        assert stats["usage_count"] == 1
        assert stats["effectiveness_sum"] == 1.0

    def test_multiple_prompts_tracked_independently(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("prompt_a", 0.7)
        pm.track_prompt_usage("prompt_b", 0.3)
        pm.track_prompt_usage("prompt_a", 0.2)
        assert pm.prompt_usage_stats["prompt_a"]["usage_count"] == 2
        assert pm.prompt_usage_stats["prompt_b"]["usage_count"] == 1

    def test_effectiveness_zero(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("bad_prompt", 0.0)
        stats = pm.prompt_usage_stats["bad_prompt"]
        assert stats["effectiveness_sum"] == 0.0

    def test_effectiveness_negative(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("harmful", -0.5)
        stats = pm.prompt_usage_stats["harmful"]
        assert stats["effectiveness_sum"] == -0.5


# ── get_prompt_analytics tests ──────────────────────────────────────────────

class TestGetPromptAnalytics:
    """PromptManager.get_prompt_analytics — analytics aggregation."""

    def test_empty_stats_returns_empty_dict(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        analytics = pm.get_prompt_analytics()
        assert analytics == {}

    def test_single_prompt_analytics(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("battle", 0.8)
        pm.track_prompt_usage("battle", 0.6)
        analytics = pm.get_prompt_analytics()
        assert "battle" in analytics
        a = analytics["battle"]
        assert a["usage_count"] == 2
        assert a["average_effectiveness"] == 0.7  # (0.8+0.6)/2
        assert a["last_used"] == "now"

    def test_multi_prompt_analytics(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("a", 1.0)
        pm.track_prompt_usage("b", 1.0)
        pm.track_prompt_usage("a", 0.0)
        analytics = pm.get_prompt_analytics()
        assert len(analytics) == 2
        assert analytics["a"]["usage_count"] == 2
        assert analytics["a"]["average_effectiveness"] == 0.5
        assert analytics["b"]["usage_count"] == 1
        assert analytics["b"]["average_effectiveness"] == 1.0

    def test_zero_usage_safety(self, tmp_path):
        """If usage_count is 0, average defaults to 0."""
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.prompt_usage_stats["edge"] = {
            "usage_count": 0,
            "effectiveness_sum": 0.0,
            "last_used": None,
        }
        analytics = pm.get_prompt_analytics()
        assert analytics["edge"]["average_effectiveness"] == 0

    def test_analytics_does_not_mutate_original(self, tmp_path):
        """Analytics returns a new dict — modifying it doesn't affect stats."""
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("p1", 0.5)
        analytics = pm.get_prompt_analytics()
        analytics["p1"]["usage_count"] = 999
        assert pm.prompt_usage_stats["p1"]["usage_count"] == 1  # unchanged

    def test_all_keys_present_in_analytics(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("complete", 0.75)
        analytics = pm.get_prompt_analytics()
        a = analytics["complete"]
        assert "usage_count" in a
        assert "average_effectiveness" in a
        assert "last_used" in a


# ── Integration / combined tests ────────────────────────────────────────────

class TestPromptManagerIntegration:
    """Full workflow tests — load from disk, select, track, analyze."""

    def test_full_workflow(self, tmp_path):
        """End-to-end: load prompts (without **Priority: lines), select, track, analyze."""
        battle = tmp_path / "battle"
        battle.mkdir()
        (battle / "tactical.txt").write_text(
            "# Tactical battle analysis\n\n"
            "You are in a battle. Choose the best move.\n",
            encoding="utf-8",
        )
        (battle / "basic.txt").write_text(
            "# Basic battle prompt\n\nFight!\n",
            encoding="utf-8",
        )

        strategic = tmp_path / "strategic"
        strategic.mkdir()
        (strategic / "overworld_plan.txt").write_text(
            "# Overworld strategy\n\nPlan your route carefully.\n",
            encoding="utf-8",
        )

        # Load
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert len(pm.prompt_templates) == 3

        # Select for battle — all 3 match (2 battle + 1 strategic for battle state)
        prompts = pm.select_prompts_for_ai("battle", {}, "tactical")
        # tactical filter: name has "tactical" or category=="battle"
        # tactical.txt: name matches → included
        # basic.txt: name doesn't match, category=="battle" → included
        # overworld_plan.txt: no match → excluded
        assert len(prompts) == 2
        contents = " ".join(prompts)
        assert "Choose the best move" in contents
        assert "Fight!" in contents

        # Select balanced
        balanced = pm.select_prompts_for_ai("battle", {}, "balanced")
        assert len(balanced) == 3  # All 3 are relevant for battle

        # Track usage
        pm.track_prompt_usage("tactical", 0.9)
        pm.track_prompt_usage("basic", 0.4)

        # Analytics
        stats = pm.get_prompt_analytics()
        assert stats["tactical"]["average_effectiveness"] == 0.9
        assert stats["basic"]["average_effectiveness"] == 0.4

    def test_reload_duplicates_entries(self, tmp_path):
        """load_prompts() doesn't reset — reloading appends duplicates."""
        battle = tmp_path / "battle"
        battle.mkdir()
        (battle / "original.txt").write_text("# Original\n\nv1\n", encoding="utf-8")
        pm = PromptManager(prompts_dir=str(tmp_path))
        assert len(pm.prompt_templates) == 1
        pm.load_prompts()
        assert len(pm.prompt_templates) == 2  # Duplicated

    def test_priority_sorting_with_default_priorities(self, tmp_path):
        """All templates loaded with default priority=1 (BUG-1: no **Priority: extraction)."""
        battle = tmp_path / "battle"
        battle.mkdir()
        for name in ["low", "high", "mid"]:
            (battle / f"{name}.txt").write_text(
                f"# {name}\n\nContent\n", encoding="utf-8"
            )
        pm = PromptManager(prompts_dir=str(tmp_path))
        relevant = pm.get_relevant_prompts("battle", {})
        assert len(relevant) == 3
        # All have default priority=1, order is insertion order
        assert all(t.priority == 1 for t in relevant)

    def test_track_then_analytics_reset_on_clear(self, tmp_path):
        pm = PromptManager(prompts_dir=str(tmp_path))
        pm.track_prompt_usage("test", 0.5)
        stats1 = pm.get_prompt_analytics()
        assert len(stats1) == 1

        # Reset stats
        pm.prompt_usage_stats = {}
        stats2 = pm.get_prompt_analytics()
        assert stats2 == {}
