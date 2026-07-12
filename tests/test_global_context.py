"""Unit tests for GlobalContext — compacted game state manager."""



from src.core.global_context import GlobalContext


# ── Helpers ──────────────────────────────────────────────────────────────

def make_ctx(**overrides) -> GlobalContext:
    """Create a GlobalContext with convenient overrides."""
    kwargs = {
        "player_name": "RED",
        "rival_name": "BLUE",
        "location": "pallet_town",
        "generation": "gen1",
        "party": [
            {"name": "SQUIRTLE", "hp_pct": 100, "level": 5, "status": None},
            {"name": "PIDGEY", "hp_pct": 60, "level": 3, "status": "poison"},
        ],
        "goals": ["get_starter", "reach_rival"],
        "active_goal": "reach_rival",
        "badges": [],
        "key_items": ["POTION", "POKE_BALL"],
        "story_flags": {"got_starter", "left_lab"},
        "recent_actions": ["walked up", "pressed A on door", "entered lab"],
    }
    kwargs.update(overrides)
    return GlobalContext(**kwargs)


# ── Constructor & Dataclass Defaults ─────────────────────────────────────

class TestConstructor:
    """Test GlobalContext construction and default values."""

    def test_default_constructor(self):
        ctx = GlobalContext()
        assert ctx.player_name == ""
        assert ctx.rival_name == ""
        assert ctx.location == "bedroom"
        assert ctx.generation == "gen1"
        assert ctx.party == []
        assert ctx.goals == []
        assert ctx.active_goal == ""
        assert ctx.badges == []
        assert ctx.key_items == []
        assert ctx.story_flags == set()
        assert ctx.recent_actions == []
        assert ctx.duckbrain_namespace == ""

    def test_full_constructor(self):
        ctx = make_ctx()
        assert ctx.player_name == "RED"
        assert ctx.rival_name == "BLUE"
        assert ctx.location == "pallet_town"
        assert ctx.generation == "gen1"
        assert len(ctx.party) == 2
        assert ctx.party[0]["name"] == "SQUIRTLE"
        assert ctx.goals == ["get_starter", "reach_rival"]
        assert ctx.active_goal == "reach_rival"
        assert ctx.key_items == ["POTION", "POKE_BALL"]
        assert ctx.story_flags == {"got_starter", "left_lab"}
        assert ctx.recent_actions == ["walked up", "pressed A on door", "entered lab"]

    def test_run_id_is_generated(self):
        ctx = GlobalContext()
        assert ctx.run_id  # non-empty
        assert "_" in ctx.run_id  # YYYYMMDD_HHMMSS format

    def test_created_at_is_isoformat(self):
        ctx = GlobalContext()
        assert ctx.created_at  # non-empty
        assert "T" in ctx.created_at  # ISO format

    def test_party_field_is_distinct_instances(self):
        """Default factory must produce distinct lists per instance."""
        c1 = GlobalContext()
        c2 = GlobalContext()
        c1.party.append({"name": "TEST"})
        assert c2.party == []

    def test_goals_field_is_distinct_instances(self):
        c1 = GlobalContext()
        c2 = GlobalContext()
        c1.goals.append("test")
        assert c2.goals == []

    def test_recent_actions_field_is_distinct_instances(self):
        c1 = GlobalContext()
        c2 = GlobalContext()
        c1.recent_actions.append("test")
        assert c2.recent_actions == []

    def test_story_flags_field_is_distinct_instances(self):
        c1 = GlobalContext()
        c2 = GlobalContext()
        c1.story_flags.add("test")
        assert c2.story_flags == set()


# ── compact() ────────────────────────────────────────────────────────────

class TestCompact:
    """Test the compact() summary method."""

    def test_compact_minimal(self):
        ctx = GlobalContext()
        result = ctx.compact()
        assert "GAME: Pokémon GEN1 — bedroom" in result
        assert "PARTY: none" in result

    def test_compact_with_player_and_rival(self):
        ctx = GlobalContext(player_name="ASH", rival_name="GARY")
        result = ctx.compact()
        assert "PLAYER: ASH" in result
        assert "RIVAL: GARY" in result

    def test_compact_with_player_no_rival(self):
        ctx = GlobalContext(player_name="ASH")
        result = ctx.compact()
        assert "PLAYER: ASH" in result
        assert "RIVAL:" not in result

    def test_compact_with_rival_no_player(self):
        ctx = GlobalContext(rival_name="GARY")
        result = ctx.compact()
        assert "RIVAL: GARY" in result
        assert "PLAYER:" not in result

    def test_compact_with_party(self):
        ctx = make_ctx()
        result = ctx.compact()
        assert "PARTY: SQUIRTLE Lv5 HP:100% | PIDGEY Lv3 HP:60% [poison]" in result

    def test_compact_with_party_no_status(self):
        ctx = GlobalContext(party=[{"name": "BULBASAUR", "hp_pct": 80, "level": 7}])
        result = ctx.compact()
        assert "BULBASAUR Lv7 HP:80%" in result
        assert "[" not in result  # no status bracket

    def test_compact_with_party_missing_fields(self):
        """Test party entries with missing hp_pct/level/name."""
        ctx = GlobalContext(party=[{"name": "X"}])
        result = ctx.compact()
        assert "X Lv? HP:?%" in result

    def test_compact_with_goals(self):
        ctx = GlobalContext(goals=["beat_gym", "catch_pikachu"])
        result = ctx.compact()
        assert "GOALS: beat_gym, catch_pikachu" in result

    def test_compact_no_goals(self):
        ctx = GlobalContext()
        result = ctx.compact()
        assert "GOALS:" not in result

    def test_compact_with_active_goal(self):
        ctx = GlobalContext(active_goal="catch_pikachu")
        result = ctx.compact()
        assert "ACTIVE: catch_pikachu" in result

    def test_compact_no_active_goal(self):
        ctx = GlobalContext()
        result = ctx.compact()
        assert "ACTIVE:" not in result

    def test_compact_with_story_flags(self):
        ctx = GlobalContext(story_flags={"got_starter", "beat_rival"})
        result = ctx.compact()
        assert "PROGRESS:" in result
        assert "beat_rival" in result
        assert "got_starter" in result

    def test_compact_no_story_flags(self):
        ctx = GlobalContext()
        result = ctx.compact()
        assert "PROGRESS:" not in result

    def test_compact_with_recent_actions(self):
        ctx = GlobalContext(recent_actions=["a", "b", "c"])
        result = ctx.compact()
        assert "RECENT: a → b → c" in result

    def test_compact_recent_actions_truncated_to_5(self):
        ctx = GlobalContext(
            recent_actions=["a1", "a2", "a3", "a4", "a5", "a6", "a7"]
        )
        result = ctx.compact()
        # Should show only last 5: a3-a7 (a1, a2 dropped)
        assert "a1" not in result
        assert "a2" not in result
        assert "a3" in result
        assert "a7" in result

    def test_compact_no_recent_actions(self):
        ctx = GlobalContext()
        result = ctx.compact()
        assert "RECENT:" not in result

    def test_compact_with_key_items(self):
        ctx = GlobalContext(key_items=["POTION", "POKE_BALL"])
        result = ctx.compact()
        assert "ITEMS: POTION, POKE_BALL" in result

    def test_compact_no_key_items(self):
        ctx = GlobalContext()
        result = ctx.compact()
        assert "ITEMS:" not in result

    def test_compact_full_state(self):
        """Smoke test: full state produces non-empty output."""
        ctx = make_ctx()
        result = ctx.compact()
        lines = result.split("\n")
        assert len(lines) >= 5  # GAME + PLAYER + RIVAL + PARTY + GOALS + ACTIVE + PROGRESS + RECENT + ITEMS
        assert result.strip()  # not empty

    def test_compact_location_in_output(self):
        ctx = GlobalContext(location="route_1", generation="gen1")
        result = ctx.compact()
        assert "GAME: Pokémon GEN1 — route_1" in result

    def test_compact_generation_uppercase(self):
        ctx = GlobalContext(generation="gen2")
        result = ctx.compact()
        assert "GEN2" in result


# ── record_action() ──────────────────────────────────────────────────────

class TestRecordAction:
    """Test the record_action() method."""

    def test_record_action_appends(self):
        ctx = GlobalContext()
        ctx.record_action("walked left")
        assert ctx.recent_actions == ["walked left"]

    def test_record_action_multiple(self):
        ctx = GlobalContext()
        for a in ["a", "b", "c"]:
            ctx.record_action(a)
        assert ctx.recent_actions == ["a", "b", "c"]

    def test_record_action_exact_20(self):
        ctx = GlobalContext()
        for i in range(20):
            ctx.record_action(f"action_{i}")
        assert len(ctx.recent_actions) == 20
        assert ctx.recent_actions[0] == "action_0"
        assert ctx.recent_actions[-1] == "action_19"

    def test_record_action_over_20_truncates(self):
        ctx = GlobalContext()
        for i in range(25):
            ctx.record_action(f"action_{i}")
        assert len(ctx.recent_actions) == 20
        # First 5 should be gone
        assert ctx.recent_actions[0] == "action_5"
        assert ctx.recent_actions[-1] == "action_24"

    def test_record_action_over_40_still_20(self):
        ctx = GlobalContext()
        for i in range(50):
            ctx.record_action(f"action_{i}")
        assert len(ctx.recent_actions) == 20
        assert ctx.recent_actions[0] == "action_30"

    def test_record_action_preserves_existing(self):
        ctx = make_ctx()
        old_len = len(ctx.recent_actions)
        ctx.record_action("new action")
        assert len(ctx.recent_actions) == old_len + 1
        assert ctx.recent_actions[-1] == "new action"


# ── add_goal() ───────────────────────────────────────────────────────────

class TestAddGoal:
    """Test the add_goal() method."""

    def test_add_goal_new(self):
        ctx = GlobalContext()
        ctx.add_goal("catch_pikachu")
        assert "catch_pikachu" in ctx.goals
        assert ctx.active_goal == "catch_pikachu"

    def test_add_goal_duplicate(self):
        ctx = GlobalContext(goals=["catch_pikachu"])
        ctx.add_goal("catch_pikachu")
        # Should not duplicate
        assert ctx.goals == ["catch_pikachu"]

    def test_add_goal_no_active_goal(self):
        """When no active goal is set, new goal becomes active."""
        ctx = GlobalContext()
        ctx.add_goal("first")
        assert ctx.active_goal == "first"

    def test_add_goal_existing_active_goal(self):
        """When active goal already exists, adding new goal doesn't change it."""
        ctx = GlobalContext(goals=["existing"], active_goal="existing")
        ctx.add_goal("new_goal")
        assert "new_goal" in ctx.goals
        assert ctx.active_goal == "existing"

    def test_add_goal_multiple(self):
        ctx = GlobalContext()
        ctx.add_goal("a")
        ctx.add_goal("b")
        ctx.add_goal("c")
        assert ctx.goals == ["a", "b", "c"]
        # active_goal was set to first, stays
        assert ctx.active_goal == "a"


# ── complete_goal() ──────────────────────────────────────────────────────

class TestCompleteGoal:
    """Test the complete_goal() method."""

    def test_complete_existing_goal(self):
        ctx = GlobalContext(goals=["a", "b", "c"], active_goal="a")
        ctx.complete_goal("b")
        assert ctx.goals == ["a", "c"]
        # active_goal unchanged
        assert ctx.active_goal == "a"

    def test_complete_nonexistent_goal(self):
        ctx = GlobalContext(goals=["a"], active_goal="a")
        ctx.complete_goal("nonexistent")
        assert ctx.goals == ["a"]

    def test_complete_active_goal_promotes_next(self):
        ctx = GlobalContext(goals=["a", "b", "c"], active_goal="a")
        ctx.complete_goal("a")
        assert ctx.goals == ["b", "c"]
        assert ctx.active_goal == "b"

    def test_complete_active_goal_last(self):
        """When active goal is the only remaining goal, active_goal becomes empty."""
        ctx = GlobalContext(goals=["a"], active_goal="a")
        ctx.complete_goal("a")
        assert ctx.goals == []
        assert ctx.active_goal == ""

    def test_complete_active_goal_already_last(self):
        """When completing the last goal (and it's not active), active_goal stays."""
        ctx = GlobalContext(goals=["a", "b"], active_goal="b")
        ctx.complete_goal("b")
        assert ctx.goals == ["a"]
        assert ctx.active_goal == "a"

    def test_complete_goal_when_only_one(self):
        ctx = GlobalContext(goals=["only"], active_goal="only")
        ctx.complete_goal("only")
        assert ctx.goals == []
        assert ctx.active_goal == ""


# ── set_flag() ───────────────────────────────────────────────────────────

class TestSetFlag:
    """Test the set_flag() method."""

    def test_set_flag(self):
        ctx = GlobalContext()
        ctx.set_flag("got_starter")
        assert "got_starter" in ctx.story_flags

    def test_set_flag_duplicate(self):
        ctx = GlobalContext(story_flags={"got_starter"})
        ctx.set_flag("got_starter")
        # Set, so duplicates are fine — should still be 1
        assert ctx.story_flags == {"got_starter"}

    def test_set_flag_multiple(self):
        ctx = GlobalContext()
        ctx.set_flag("a")
        ctx.set_flag("b")
        ctx.set_flag("c")
        assert ctx.story_flags == {"a", "b", "c"}

    def test_set_flag_does_not_affect_other_fields(self):
        ctx = make_ctx()
        old_goals = ctx.goals.copy()
        ctx.set_flag("new_flag")
        assert ctx.goals == old_goals


# ── update_party() ───────────────────────────────────────────────────────

class TestUpdateParty:
    """Test the update_party() method."""

    def test_update_party_replaces(self):
        ctx = make_ctx()
        old_len = len(ctx.party)
        new_party = [{"name": "CHARMANDER", "hp_pct": 50, "level": 4}]
        ctx.update_party(new_party)
        assert ctx.party == new_party
        assert len(ctx.party) != old_len

    def test_update_party_to_empty(self):
        ctx = make_ctx()
        ctx.update_party([])
        assert ctx.party == []

    def test_update_party_to_larger(self):
        ctx = make_ctx()
        new_party = [
            {"name": "A", "hp_pct": 100, "level": 10},
            {"name": "B", "hp_pct": 80, "level": 8},
            {"name": "C", "hp_pct": 60, "level": 6},
        ]
        ctx.update_party(new_party)
        assert ctx.party == new_party

    def test_update_party_reflected_in_compact(self):
        ctx = GlobalContext()
        ctx.update_party([{"name": "EEVEE", "hp_pct": 90, "level": 12, "status": "sleep"}])
        result = ctx.compact()
        assert "EEVEE Lv12 HP:90% [sleep]" in result


# ── set_location() ───────────────────────────────────────────────────────

class TestSetLocation:
    """Test the set_location() method."""

    def test_set_location(self):
        ctx = GlobalContext()
        ctx.set_location("route_1")
        assert ctx.location == "route_1"

    def test_set_location_overwrites(self):
        ctx = GlobalContext(location="bedroom")
        ctx.set_location("pallet_town")
        assert ctx.location == "pallet_town"

    def test_set_location_reflected_in_compact(self):
        ctx = GlobalContext()
        ctx.set_location("viridian_city")
        result = ctx.compact()
        assert "viridian_city" in result

    def test_set_location_empty_string(self):
        ctx = GlobalContext(location="bedroom")
        ctx.set_location("")
        assert ctx.location == ""


# ── Integration / Combined Operations ────────────────────────────────────

class TestIntegration:
    """Test combined operations simulating real gameplay workflows."""

    def test_full_gameplay_flow(self):
        """Simulate a typical gameplay sequence."""
        ctx = GlobalContext(player_name="RED", rival_name="BLUE")

        # Start journey
        ctx.add_goal("get_starter")
        ctx.add_goal("reach_rival")
        assert ctx.goals == ["get_starter", "reach_rival"]
        assert ctx.active_goal == "get_starter"

        # Set flags
        ctx.set_flag("entered_lab")
        ctx.set_flag("got_starter")
        ctx.update_party([{"name": "SQUIRTLE", "hp_pct": 100, "level": 5, "status": None}])

        # Complete first goal
        ctx.complete_goal("get_starter")
        assert ctx.active_goal == "reach_rival"

        # Move locations
        ctx.set_location("pallet_town")
        ctx.set_location("route_1")

        # Record actions
        ctx.record_action("entered lab")
        ctx.record_action("picked SQUIRTLE")
        ctx.record_action("left lab")
        ctx.record_action("walked to route 1")

        # Verify compact output
        result = ctx.compact()
        assert "PLAYER: RED" in result
        assert "RIVAL: BLUE" in result
        assert "SQUIRTLE" in result
        assert "route_1" in result
        assert "PROGRESS:" in result

    def test_many_actions_then_compact(self):
        """Record 30+ actions, verify truncation in compact."""
        ctx = GlobalContext()
        for i in range(35):
            ctx.record_action(f"step_{i}")
        result = ctx.compact()
        # Only last 5 should appear
        assert "step_15" not in result
        assert "step_34" in result

    def test_goal_lifecycle(self):
        ctx = GlobalContext()
        ctx.add_goal("a")
        ctx.add_goal("b")
        ctx.add_goal("c")
        ctx.complete_goal("a")
        ctx.complete_goal("b")
        ctx.complete_goal("c")
        assert ctx.goals == []
        assert ctx.active_goal == ""
