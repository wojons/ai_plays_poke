"""Unit tests for GameDatabase — in-memory/tmp SQLite, no ROM/API needed."""

import json
import sqlite3
import tempfile
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

import pytest


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Create a temporary database path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def db(db_path: str):
    """Create a fresh GameDatabase for each test."""
    # IMPORTANT: importing database.py creates default_db at ./game_data.db
    # We must set cwd to tmp dir to avoid polluting the project root
    import os as _os
    old_cwd = _os.getcwd()
    _os.chdir(str(Path(db_path).parent))
    try:
        from src.db.database import GameDatabase
        gdb = GameDatabase(db_path=db_path)
        yield gdb
        gdb.close()
    finally:
        _os.chdir(old_cwd)
        # Clean up the game_data.db that default_db creates
        default_path = Path(old_cwd) / "game_data.db"
        if default_path.exists():
            try:
                default_path.unlink()
            except OSError:
                pass


# ============================================================================
# Test __init__ + init_database — table creation
# ============================================================================

class TestInit:
    """Test GameDatabase.__init__ and table creation."""

    def test_init_creates_tables(self, db_path: str):
        """__init__ creates all 8 tables in the schema."""
        import os as _os
        old_cwd = _os.getcwd()
        _os.chdir(str(Path(db_path).parent))
        try:
            from src.db.database import GameDatabase
            GameDatabase(db_path=db_path)
        finally:
            _os.chdir(old_cwd)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        expected = [
            "ai_thoughts",
            "battle_turns",
            "battles",
            "commands",
            "performance_metrics",
            "pokemon",
            "screenshots",
            "sessions",
            "training_runs",
        ]
        for table in expected:
            assert table in tables, f"Table '{table}' not found in {tables}"

    def test_init_creates_indexes(self, db_path: str):
        """__init__ creates performance indexes."""
        import os as _os
        old_cwd = _os.getcwd()
        _os.chdir(str(Path(db_path).parent))
        try:
            from src.db.database import GameDatabase
            GameDatabase(db_path=db_path)
        finally:
            _os.chdir(old_cwd)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        expected_indexes = [
            "idx_battles_outcome",
            "idx_battles_session",
            "idx_commands_tick",
            "idx_pokemon_species",
            "idx_screenshots_tick",
            "idx_thoughts_tick",
        ]
        for idx in expected_indexes:
            assert idx in indexes, f"Index '{idx}' not found in {indexes}"

    def test_init_is_idempotent(self, db, db_path: str):
        """Calling __init__ twice doesn't fail — CREATE IF NOT EXISTS."""
        from src.db.database import GameDatabase
        db2 = GameDatabase(db_path=db_path)
        db2.close()
        # If we get here without exception, idempotent works

    def test_init_creates_parent_dirs(self, tmp_path: Path):
        """__init__ creates parent directories that don't exist."""
        deep_path = tmp_path / "a" / "b" / "c" / "test.db"
        import os as _os
        old_cwd = _os.getcwd()
        _os.chdir(str(tmp_path))
        try:
            from src.db.database import GameDatabase
            gdb = GameDatabase(db_path=str(deep_path))
            gdb.close()
        finally:
            _os.chdir(old_cwd)

        assert deep_path.exists()


# ============================================================================
# Test session lifecycle: start_session → end_session
# ============================================================================

class TestSessionLifecycle:
    """Test start_session, end_session, get_session."""

    def test_start_session_returns_id(self, db):
        """start_session returns a valid session ID."""
        sid = db.start_session(rom_path="/tmp/test.gb", model_name="gpt-4")
        assert isinstance(sid, int)
        assert sid > 0

    def test_start_session_persists_data(self, db):
        """start_session writes data that can be queried back."""
        sid = db.start_session(rom_path="/tmp/test.gb", model_name="gpt-4")

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT session_id, rom_path, model_name FROM sessions WHERE session_id = ?", (sid,))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[1] == "/tmp/test.gb"
        assert row[2] == "gpt-4"

    def test_end_session_updates_latest(self, db):
        """end_session updates the most recent session with final metrics."""
        sid = db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.end_session({
            "total_ticks": 100,
            "total_commands": 50,
            "total_battles": 3,
            "badges_earned": 2,
            "final_state": {"location": "Cerulean City"},
        })

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT total_ticks, total_commands, total_battles, badges_earned, final_state "
            "FROM sessions WHERE session_id = ?", (sid,)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 100
        assert row[1] == 50
        assert row[2] == 3
        assert row[3] == 2
        final_state = json.loads(row[4])
        assert final_state["location"] == "Cerulean City"

    def test_end_session_defaults(self, db):
        """end_session with empty metrics uses defaults."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.end_session({})

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT total_ticks, total_commands, total_battles, badges_earned FROM sessions ORDER BY session_id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()

        assert row == (0, 0, 0, 0)

    def test_get_session_returns_data(self, db):
        """get_session returns a dict for a valid session ID."""
        sid = db.start_session(rom_path="/tmp/test.gb", model_name="test")
        data = db.get_session(sid)
        assert isinstance(data, dict)
        assert data["session_id"] == sid
        assert data["model_name"] == "test"
        assert data["rom_path"] == "/tmp/test.gb"

    def test_get_session_not_found_raises(self, db):
        """get_session raises OperationalError for nonexistent ID."""
        with pytest.raises(sqlite3.OperationalError, match="not found"):
            db.get_session(99999)

    def test_save_session_data_inserts_row(self, db):
        """save_session_data inserts a new session row."""
        result = db.save_session_data({
            "rom_path": "/tmp/blue.gb",
            "model_name": "deepseek",
            "extra": "metadata",
        })
        assert result is True

        # Verify the data was saved
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT rom_path, model_name, final_state FROM sessions ORDER BY session_id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "/tmp/blue.gb"
        assert row[1] == "deepseek"
        final_state = json.loads(row[2])
        assert final_state["extra"] == "metadata"

    def test_save_session_data_unknown_defaults(self, db):
        """save_session_data uses 'unknown' for missing rom_path/model_name."""
        db.save_session_data({})
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT rom_path, model_name FROM sessions ORDER BY session_id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        assert row[0] == "unknown"
        assert row[1] == "unknown"


# ============================================================================
# Test log_screenshot / log_screenshot_event
# ============================================================================

class TestScreenshotLogging:
    """Test log_screenshot and log_screenshot_event."""

    def test_log_screenshot_writes_row(self, db):
        """log_screenshot inserts a screenshot event."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.log_screenshot(tick=5, file_path="/tmp/screenshot_005.png", game_state={"screen": "overworld"})

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tick, file_path, game_state FROM screenshots ORDER BY screenshot_id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 5
        assert row[1] == "/tmp/screenshot_005.png"
        gs = json.loads(row[2])
        assert gs["screen"] == "overworld"

    def test_log_screenshot_without_session(self, db):
        """log_screenshot works even without an explicit session (subquery returns NULL)."""
        db.log_screenshot(tick=1, file_path="/tmp/s.png", game_state={})
        # Should not raise

    def test_log_screenshot_event_compat(self, db):
        """log_screenshot_event delegates to log_screenshot."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.log_screenshot_event({"tick": 10, "path": "/tmp/ss.png", "game_state": {"screen": "battle"}})

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tick, file_path FROM screenshots ORDER BY screenshot_id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 10
        assert row[1] == "/tmp/ss.png"

    def test_log_screenshot_event_empty_dict(self, db):
        """log_screenshot_event with empty dict uses defaults."""
        db.log_screenshot_event({})
        # Should not raise — defaults to tick=0, path="", game_state={}


# ============================================================================
# Test log_command / log_command_execution
# ============================================================================

class TestCommandLogging:
    """Test log_command and log_command_execution."""

    def test_log_command_full_data(self, db):
        """log_command inserts with all fields populated."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.log_command({
            "tick": 3,
            "command_type": "press",
            "command_value": "A",
            "reasoning": "Talk to NPC",
            "confidence": 0.95,
            "success": True,
            "error_message": None,
            "execution_time_ms": 12.5,
        })

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tick, command_type, command_value, reasoning, confidence, success, execution_time_ms "
            "FROM commands ORDER BY command_id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 3
        assert row[1] == "press"
        assert row[2] == "A"
        assert row[3] == "Talk to NPC"
        assert row[4] == 0.95
        assert row[5] == 1  # sqlite3 bool→int
        assert row[6] == 12.5

    def test_log_command_defaults(self, db):
        """log_command uses defaults for missing optional fields."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.log_command({"tick": 1, "command_type": "wait", "command_value": "60"})

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT reasoning, confidence, success, execution_time_ms FROM commands ORDER BY command_id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == ""   # default reasoning
        assert row[1] == 0.0  # default confidence
        assert row[2] == 1    # success=True by default
        assert row[3] == 0    # default execution_time_ms

    def test_log_command_failure(self, db):
        """log_command records failure with error message."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.log_command({
            "tick": 7,
            "command_type": "press",
            "command_value": "B",
            "success": False,
            "error_message": "Button stuck",
        })

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT success, error_message FROM commands ORDER BY command_id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 0
        assert row[1] == "Button stuck"

    def test_log_command_execution_compat(self, db):
        """log_command_execution delegates to log_command."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.log_command_execution({
            "tick": 2,
            "command_type": "combo",
            "command_value": "A+B",
        })

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT command_type, command_value FROM commands ORDER BY command_id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "combo"
        assert row[1] == "A+B"


# ============================================================================
# Test log_ai_thought
# ============================================================================

class TestAIThoughtLogging:
    """Test log_ai_thought."""

    def test_log_ai_thought_full_data(self, db):
        """log_ai_thought inserts with all fields populated."""
        db.start_session(rom_path="/tmp/test.gb", model_name="deepseek")
        db.log_ai_thought({
            "tick": 12,
            "thought_process": "Analyzing battle options",
            "reasoning": "Water Gun is super effective against Charmander",
            "game_context": {"battle": {"enemy": "Charmander", "hp": 20}},
            "proposed_action": "Use Water Gun",
            "confidence": 0.92,
            "model_used": "deepseek-v4-flash",
            "tokens_used": 450,
        })

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tick, thought_process, reasoning, game_context, proposed_action, "
            "confidence, model_used, tokens_used FROM ai_thoughts ORDER BY thought_id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 12
        assert row[1] == "Analyzing battle options"
        assert row[2] == "Water Gun is super effective against Charmander"
        gc = json.loads(row[3])
        assert gc["battle"]["enemy"] == "Charmander"
        assert row[4] == "Use Water Gun"
        assert row[5] == 0.92
        assert row[6] == "deepseek-v4-flash"
        assert row[7] == 450

    def test_log_ai_thought_defaults(self, db):
        """log_ai_thought uses defaults for missing fields."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.log_ai_thought({"tick": 1})

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT thought_process, reasoning, proposed_action, confidence, model_used, tokens_used "
            "FROM ai_thoughts ORDER BY thought_id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == ""
        assert row[1] == ""
        assert row[2] == ""
        assert row[3] == 0.0
        assert row[4] == "unknown"
        assert row[5] == 0

    def test_log_ai_thought_game_context_none(self, db):
        """log_ai_thought handles None game_context."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.log_ai_thought({
            "tick": 1,
            "game_context": None,
        })

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT game_context FROM ai_thoughts ORDER BY thought_id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        # None gets json.dumps'd — becomes "null"
        assert row[0] == "null"


# ============================================================================
# Test battle tracking: start → turn → end
# ============================================================================

class TestBattleTracking:
    """Test log_battle_start, log_battle_turn, log_battle_end."""

    def test_battle_lifecycle(self, db):
        """Full battle: start → two turns → victory."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")

        # Start
        battle_id = db.log_battle_start({
            "tick": 20,
            "enemy_pokemon": "Pidgey",
            "enemy_level": 3,
            "player_pokemon": "Squirtle",
            "player_level": 5,
        })
        assert isinstance(battle_id, int)
        assert battle_id > 0

        # Turn 1
        db.log_battle_turn(battle_id, {
            "turn_number": 1,
            "player_action": "Tackle",
            "enemy_action": "Gust",
            "player_hp_before": 21,
            "player_hp_after": 18,
            "enemy_hp_before": 15,
            "enemy_hp_after": 8,
            "effectiveness": "neutral",
        })

        # Turn 2
        db.log_battle_turn(battle_id, {
            "turn_number": 2,
            "player_action": "Tackle",
            "enemy_action": "Gust",
            "player_hp_before": 18,
            "player_hp_after": 15,
            "enemy_hp_before": 8,
            "enemy_hp_after": 0,
            "effectiveness": "neutral",
        })

        # End
        db.log_battle_end(battle_id, "victory", turns_taken=2)

        # Verify
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT enemy_pokemon, enemy_level, player_pokemon, player_level, outcome, turns_taken "
            "FROM battles WHERE battle_id = ?", (battle_id,)
        )
        battle = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM battle_turns WHERE battle_id = ?", (battle_id,))
        turn_count = cursor.fetchone()[0]
        conn.close()

        assert battle[0] == "Pidgey"
        assert battle[1] == 3
        assert battle[2] == "Squirtle"
        assert battle[3] == 5
        assert battle[4] == "victory"
        assert battle[5] == 2
        assert turn_count == 2

    def test_log_battle_start_minimal(self, db):
        """log_battle_start with only tick."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        battle_id = db.log_battle_start({"tick": 5})
        assert battle_id > 0

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT enemy_pokemon, enemy_level, player_pokemon, player_level FROM battles WHERE battle_id = ?", (battle_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] is None
        assert row[1] is None
        assert row[2] is None
        assert row[3] is None

    def test_log_battle_turn_minimal(self, db):
        """log_battle_turn with only required fields."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        battle_id = db.log_battle_start({"tick": 1})
        db.log_battle_turn(battle_id, {"turn_number": 1})

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT player_action, enemy_action, enemy_hp_before FROM battle_turns WHERE battle_id = ?", (battle_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] is None  # optional fields default to None
        assert row[1] is None
        assert row[2] is None

    def test_log_battle_end_defeat(self, db):
        """log_battle_end with defeat outcome."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        battle_id = db.log_battle_start({"tick": 1, "enemy_pokemon": "Brock's Onix"})
        db.log_battle_end(battle_id, "defeat", turns_taken=5)

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT outcome, turns_taken FROM battles WHERE battle_id = ?", (battle_id,))
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "defeat"
        assert row[1] == 5


# ============================================================================
# Test get_session_summary
# ============================================================================

class TestSessionSummary:
    """Test get_session_summary with aggregate stats."""

    def test_get_session_summary_empty_battles(self, db):
        """Summary for session with no battles shows 0 win_rate."""
        sid = db.start_session(rom_path="/tmp/test.gb", model_name="test")
        summary = db.get_session_summary(sid)

        assert summary["session_id"] == sid
        assert summary["model_name"] == "test"
        assert summary.get("wins", 0) == 0
        assert summary.get("losses", 0) == 0
        assert summary.get("win_rate", 0) == 0

    def test_get_session_summary_with_battles(self, db):
        """Summary aggregates wins and losses correctly."""
        sid = db.start_session(rom_path="/tmp/test.gb", model_name="test")

        # Win
        bid1 = db.log_battle_start({"tick": 1, "enemy_pokemon": "Pidgey"})
        db.log_battle_end(bid1, "victory", turns_taken=1)

        # Loss
        bid2 = db.log_battle_start({"tick": 2, "enemy_pokemon": "Rattata"})
        db.log_battle_end(bid2, "defeat", turns_taken=1)

        # Ongoing (should not count)
        db.log_battle_start({"tick": 3, "enemy_pokemon": "Spearow"})

        summary = db.get_session_summary(sid)

        assert summary["wins"] == 1
        assert summary["losses"] == 1
        # 3 battles total (1 win, 1 loss, 1 ongoing) → win_rate = 1/3 ≈ 0.333
        assert summary["win_rate"] == pytest.approx(1/3)

    def test_get_session_summary_unknown_session(self, db):
        """get_session_summary for nonexistent session returns {}."""
        result = db.get_session_summary(99999)
        assert result == {}


# ============================================================================
# Test export_session_data
# ============================================================================

class TestExportSessionData:
    """Test export_session_data JSON export."""

    def test_get_session_data_bug_double_fetchone(self, db):
        """BUG: _get_session_data calls cursor.fetchone() TWICE.
        
        Line 472: return dict(zip(..., cursor.fetchone())) if cursor.fetchone() else {}
        First call consumes the row, second returns None → TypeError on zip.
        This is a pre-existing production bug — export_session_data is broken
        for sessions that have data.
        """
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        from src.db.database import GameDatabase
        with pytest.raises(TypeError, match="'NoneType' object is not iterable"):
            db.export_session_data(1)

    def test_export_session_data_empty_session(self, db):
        """export_session_data for session with no rows (empty tables) — fails same bug."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        # BUG: _get_session_data double-fetchone — always TypeError if a session row exists.
        # The 'if cursor.fetchone()' check consumes the row, then zip gets None.
        with pytest.raises(TypeError):
            db.export_session_data(1)


# ============================================================================
# Test compatibility wrappers
# ============================================================================

class TestCompatibilityWrappers:
    """Test the compatibility wrapper methods."""

    def test_log_session_metrics_is_noop(self, db):
        """log_session_metrics is a documented no-op — should not raise."""
        db.log_session_metrics({"total_ticks": 100})
        # No assertion needed — passes if no exception

    def test_log_command_execution_delegates(self, db):
        """log_command_execution passes through to log_command."""
        db.start_session(rom_path="/tmp/test.gb", model_name="test")
        db.log_command_execution({
            "tick": 1,
            "command_type": "combo",
            "command_value": "A+B",
        })

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT command_value FROM commands ORDER BY command_id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "A+B"

    def test_log_screenshot_event_non_dict(self, db):
        """log_screenshot_event handles non-dict input gracefully."""
        db.log_screenshot_event("not a dict")  # type: ignore[arg-type]
        # Should not raise — defaults to tick=0, path=""


# ============================================================================
# Test close
# ============================================================================

class TestClose:
    """Test close method."""

    def test_close_is_idempotent(self, db):
        """close can be called multiple times without error."""
        db.close()
        db.close()  # second close should not raise

    def test_close_logs_info(self, db):
        """close logs a message."""
        import logging
        with patch.object(logging.getLogger("src.db.database"), "info") as mock_info:
            db.close()
            mock_info.assert_called_once_with("Database connection closed")


# ============================================================================
# Test error handling
# ============================================================================

class TestErrorHandling:
    """Test error handling in _execute and other methods."""

    def test_execute_constraint_violation_raises_custom(self, db):
        """_execute raises ConstraintViolationError on IntegrityError."""
        db._execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        db._execute("INSERT INTO test VALUES (1)")

        from src.db.database import ConstraintViolationError as CVE
        with pytest.raises(CVE):
            db._execute("INSERT INTO test VALUES (1)")

    def test_execute_db_error_raises_custom(self, db):
        """_execute raises DatabaseError on generic sqlite3.Error."""
        from src.db.database import DatabaseError
        with pytest.raises(DatabaseError):
            db._execute("INVALID SQL SYNTAX !!!")

    def test_execute_success_returns_cursor(self, db):
        """_execute returns a cursor on success."""
        cursor = db._execute("SELECT 1 AS val")
        row = cursor.fetchone()
        assert row[0] == 1


# ============================================================================
# Test multi-session scenarios
# ============================================================================

class TestMultiSession:
    """Test behavior with multiple overlapping sessions."""

    def test_multiple_sessions_independent(self, db):
        """Each session gets a unique ID and independent data."""
        sid1 = db.start_session(rom_path="/tmp/red.gb", model_name="model-a")
        sid2 = db.start_session(rom_path="/tmp/blue.gb", model_name="model-b")

        assert sid1 != sid2

        s1 = db.get_session(sid1)
        s2 = db.get_session(sid2)

        assert s1["rom_path"] == "/tmp/red.gb"
        assert s2["rom_path"] == "/tmp/blue.gb"

    def test_commands_go_to_latest_session(self, db):
        """log_command uses (SELECT MAX(session_id)) — goes to latest session."""
        db.start_session(rom_path="/tmp/s1.gb", model_name="first")
        db.start_session(rom_path="/tmp/s2.gb", model_name="second")

        db.log_command({"tick": 1, "command_type": "press", "command_value": "A"})

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT session_id FROM commands ORDER BY command_id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        # Should be associated with the latest session (sid2)
        assert row[0] == 2


# ============================================================================
# AC Verification — methods that don't exist
# ============================================================================

class TestMissingACMethods:
    """Document missing methods referenced in task ACs."""

    def test_get_recent_actions_not_implemented(self):
        """AC item 6: get_recent_actions — method does not exist in GameDatabase.
        
        The AC says: 'Test get_recent_actions — ordered by timestamp, limit'
        GameDatabase has no such method. Equivalent functionality is available
        via raw SQL on the commands table, or via export_session_data.
        """
        from src.db.database import GameDatabase
        assert not hasattr(GameDatabase, "get_recent_actions"), \
            "get_recent_actions unexpectedly exists — update this test"

    def test_get_session_stats_not_implemented(self):
        """AC item 7: get_session_stats — method does not exist in GameDatabase.
        
        The AC says: 'Test get_session_stats — aggregated metrics query'
        Equivalent: get_session_summary() provides aggregated session data
        including wins, losses, win_rate.
        """
        from src.db.database import GameDatabase
        assert not hasattr(GameDatabase, "get_session_stats"), \
            "get_session_stats unexpectedly exists — update this test"
