"""
Unit tests for src/core/map_integrator.py — _parse_raw() and _dict_to_patch().

These are pure functions (string→dict, dict→ObsPatch) — no WorldState or
emulator dependencies. All tests use plain string inputs and temp dirs.
"""

from __future__ import annotations



from src.core.map_integrator import _dict_to_patch, _parse_raw


# ── _parse_raw tests ────────────────────────────────────────────────────────


class TestParseRawJson:
    """Tests for _parse_raw with JSON input."""

    def test_valid_json_flat(self) -> None:
        result = _parse_raw('{"tick": 5, "prev_tick": 4}')
        assert result == {"tick": 5, "prev_tick": 4}

    def test_valid_json_nested(self) -> None:
        raw = '{"movement": {"input": "UP", "result": "moved", "player_delta": [0, -1]}}'
        result = _parse_raw(raw)
        assert result["movement"]["input"] == "UP"
        assert result["movement"]["player_delta"] == [0, -1]

    def test_json_with_whitespace(self) -> None:
        result = _parse_raw('   {"tick": 1}   ')
        assert result == {"tick": 1}

    def test_json_with_newlines(self) -> None:
        result = _parse_raw('\n{"tick": 2}\n')
        assert result == {"tick": 2}

    def test_invalid_json_falls_back_to_yaml(self) -> None:
        """Invalid JSON that IS valid YAML returns the YAML-parsed value."""
        result = _parse_raw("not json at all!")
        # YAML safe_load parses "not json at all!" as a plain string.
        # cast() is a no-op at runtime — the raw YAML result is returned as-is.
        # Documented behaviour: _parse_raw does NOT validate the result is a dict.
        assert result == "not json at all!"

    def test_json_array_returns_list(self) -> None:
        """JSON array returns the list directly — cast() is no-op at runtime."""
        result = _parse_raw("[1, 2, 3]")
        # json.loads returns a list; cast(dict, list) is no-op.
        # Documented: _parse_raw does NOT validate the result type.
        assert isinstance(result, list)
        assert result == [1, 2, 3]


class TestParseRawMarkdownFenced:
    """Tests for _parse_raw with markdown-fenced input."""

    def test_fenced_json(self) -> None:
        raw = '```\n{"tick": 42}\n```'
        result = _parse_raw(raw)
        assert result == {"tick": 42}

    def test_fenced_json_with_language_tag(self) -> None:
        raw = '```json\n{"tick": 99}\n```'
        result = _parse_raw(raw)
        # The first line "```json" is stripped; the last "```" is stripped.
        # The content '{"tick": 99}' parses as JSON.
        assert result == {"tick": 99}

    def test_fenced_yaml(self) -> None:
        raw = '```yaml\ntick: 7\nprev_tick: 6\n```'
        result = _parse_raw(raw)
        assert result["tick"] == 7
        assert result["prev_tick"] == 6

    def test_fenced_but_content_not_json_uses_yaml(self) -> None:
        raw = '```\ntick: 3\nmovement:\n  input: A\n```'
        result = _parse_raw(raw)
        assert result["tick"] == 3
        assert result["movement"]["input"] == "A"

    def test_fenced_empty_content(self) -> None:
        raw = '```\n```'
        result = _parse_raw(raw)
        # Empty string after stripping fences — YAML safe_load("") returns None
        assert result == {}

    def test_fenced_with_only_opening_fence(self) -> None:
        """Only opening fence — treated as YAML with first line stripped."""
        raw = '```\ntick: 5'
        result = _parse_raw(raw)
        assert result["tick"] == 5


class TestParseRawEmptyAndEdgeCases:
    """Tests for _parse_raw edge cases."""

    def test_empty_string(self) -> None:
        result = _parse_raw("")
        assert result == {}

    def test_whitespace_only(self) -> None:
        result = _parse_raw("   \n  \t  ")
        assert result == {}

    def test_none_like_string(self) -> None:
        result = _parse_raw("null")
        # json.loads("null") returns None; cast(dict, None) is no-op.
        # Documented: _parse_raw does NOT validate result type.
        assert result is None

    def test_boolean_like_string(self) -> None:
        result = _parse_raw("true")
        # json.loads("true") returns True; cast(dict, True) is no-op.
        assert result is True

    def test_number_like_string(self) -> None:
        result = _parse_raw("42")
        # json.loads("42") returns 42; cast(dict, 42) is no-op.
        assert result == 42

    def test_single_line_markdown_fence(self) -> None:
        """Just a fence marker with no content."""
        result = _parse_raw("```json")
        assert result == {}

    def test_mixed_content_with_fence_and_extra_chars(self) -> None:
        """Content outside the fence is included."""
        raw = 'prefix text\n```json\n{"tick": 1}\n```\nsuffix text'
        result = _parse_raw(raw)
        # The fence stripping removes first line (prefix) and last line (suffix)
        # The remaining '```json\n{"tick": 1}\n```' — wait, that's re-examining...
        # Actually the algorithm: if starts with ```, strip first and last lines
        # Since it starts with "prefix" (no ```), the fence check is skipped
        # Then json.loads fails on the whole blob; YAML safe_load interprets
        # it as a multi-line string
        assert isinstance(result, dict)


class TestParseRawYamlFallback:
    """Tests for _parse_raw YAML fallback path."""

    def test_yaml_simple_key_value(self) -> None:
        result = _parse_raw("tick: 10")
        assert result["tick"] == 10

    def test_yaml_nested_mapping(self) -> None:
        raw = """tick: 5
prev_tick: 4
movement:
  input: DOWN
  result: blocked
  player_delta:
  - 0
  - 0"""
        result = _parse_raw(raw)
        assert result["tick"] == 5
        assert result["movement"]["input"] == "DOWN"
        assert result["movement"]["player_delta"] == [0, 0]

    def test_yaml_with_list(self) -> None:
        raw = "tick: 1\nedges:\n- from: [1, 2]\n  dir: N"
        result = _parse_raw(raw)
        assert result["tick"] == 1
        assert len(result["edges"]) == 1

    def test_yaml_with_literal_block_scalar(self) -> None:
        raw = "tick: 1\nterrain: |\n  TTTggg..."
        result = _parse_raw(raw)
        assert result["tick"] == 1
        assert "terrain" in result

    def test_yaml_returns_none_for_empty(self) -> None:
        """YAML safe_load on '' returns None in some yaml versions."""
        result = _parse_raw(" ")
        assert result == {}

    def test_yaml_boolean_values(self) -> None:
        result = _parse_raw("resync: true")
        assert result["resync"] is True


# ── _dict_to_patch tests ────────────────────────────────────────────────────


class TestDictToPatch:
    """Tests for _dict_to_patch — converts raw dict to ObsPatch."""

    def test_minimal_valid_dict(self) -> None:
        data = {"tick": 1, "prev_tick": 0}
        patch = _dict_to_patch(data)
        assert patch.tick == 1
        assert patch.prev_tick == 0
        # No movement, so should be None
        assert patch.movement is None

    def test_with_movement(self) -> None:
        data = {
            "tick": 5,
            "prev_tick": 4,
            "movement": {"input": "UP", "result": "moved", "player_delta": [0, -1]},
        }
        patch = _dict_to_patch(data)
        assert patch.tick == 5
        assert patch.movement is not None
        assert patch.movement.input == "UP"
        assert patch.movement.result == "moved"

    def test_with_viewport(self) -> None:
        data = {
            "tick": 2,
            "movement": {"input": "RIGHT", "result": "moved", "player_delta": [1, 0]},
            "viewport": {"origin_delta": [1, 0], "new_edge": "E"},
        }
        patch = _dict_to_patch(data)
        assert patch.viewport is not None
        assert patch.viewport.origin_delta == [1, 0]
        assert patch.viewport.new_edge == "E"

    def test_with_strip(self) -> None:
        data = {
            "tick": 3,
            "movement": {"input": "DOWN", "result": "moved", "player_delta": [0, 1]},
            "strip": {
                "edge": "S",
                "global_y": 10,
                "x_start": 0,
                "terrain": "TTT...ggg",
            },
        }
        patch = _dict_to_patch(data)
        assert patch.strip is not None
        assert patch.strip.edge == "S"
        assert patch.strip.terrain == "TTT...ggg"

    def test_with_edges(self) -> None:
        data = {
            "tick": 1,
            "movement": {"input": "LEFT", "result": "blocked", "player_delta": [0, 0]},
            "edges": [
                {"from": [5, 10], "dir": "W", "outcome": "blocked", "reason": "wall"}
            ],
        }
        patch = _dict_to_patch(data)
        assert len(patch.edges) == 1
        assert patch.edges[0].outcome == "blocked"

    def test_with_actor_updates(self) -> None:
        data = {
            "tick": 1,
            "movement": {"input": "A", "result": "dialog"},
            "actor_updates": [
                {"id": "npc1", "kind": "T", "pos": [5, 5], "facing": "N"}
            ],
        }
        patch = _dict_to_patch(data)
        assert len(patch.actor_updates) == 1
        assert patch.actor_updates[0].id == "npc1"

    def test_with_corrections(self) -> None:
        data = {
            "tick": 2,
            "movement": {"input": "UP", "result": "moved", "player_delta": [0, -1]},
            "corrections": [
                {"layer": "terrain", "at": [3, 3], "to": "T", "confidence": 0.8}
            ],
        }
        patch = _dict_to_patch(data)
        assert len(patch.corrections) == 1
        assert patch.corrections[0].to_char == "T"

    def test_with_resync(self) -> None:
        data = {
            "tick": 10,
            "resync": {
                "reason": "warp",
                "new_map_id": "route1",
                "viewport_origin": [100, 200],
                "player_pos": [105, 205],
            },
        }
        patch = _dict_to_patch(data)
        assert patch.resync is not None
        assert patch.resync.reason == "warp"
        assert patch.resync.new_map_id == "route1"

    def test_empty_dict(self) -> None:
        patch = _dict_to_patch({})
        assert patch.tick == 0
        assert patch.prev_tick == 0
        assert patch.movement is None
        assert patch.viewport is None

    def test_with_visited_add_list(self) -> None:
        data = {
            "tick": 1,
            "movement": {"input": "UP", "result": "moved", "player_delta": [0, -1]},
            "visited_add": [[5, 10], [5, 11]],
        }
        patch = _dict_to_patch(data)
        assert patch.visited_add == [[5, 10], [5, 11]]

    def test_with_visited_dict(self) -> None:
        data = {
            "tick": 1,
            "movement": {"input": "RIGHT", "result": "moved", "player_delta": [1, 0]},
            "visited": {"add": [[3, 3]]},
        }
        patch = _dict_to_patch(data)
        assert patch.visited_add == [[3, 3]]
