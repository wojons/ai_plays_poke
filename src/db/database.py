"""
SQLite Database Module for AI Plays Pokemon

Tracks:
- Overall sessions and performance stats
- AI commands sent to emulator
- AI thinking processes/reasoning
- Battle events (start, end, turns)
- Pokemon encountered
- Screenshot events
- Training runs for model comparison
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base exception for database errors."""
    pass


class ConstraintViolationError(DatabaseError):
    """Raised when a database constraint is violated."""
    pass


class InterruptError(DatabaseError):
    """Raised when a database operation is interrupted."""
    pass


class GameDatabase:
    """
    Main database class for tracking all game events and AI decisions
    """
    
    def __init__(self, db_path: str):
        """
        Initialize database at specified path
        
        Args:
            db_path: Path to SQLite database file (will be created if not exists)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """Initialize all database tables"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=0.001)
        except sqlite3.OperationalError as e:
            raise DatabaseError(f"Database is locked or unavailable: {e}")
        
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    end_time TEXT,
                    rom_path TEXT,
                    model_name TEXT,
                    total_ticks INTEGER DEFAULT 0,
                    total_commands INTEGER DEFAULT 0,
                    total_battles INTEGER DEFAULT 0,
                    badges_earned INTEGER DEFAULT 0,
                    final_state TEXT
                )
            """)
            
            # Screenshot events
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS screenshots (
                    screenshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    file_path TEXT,
                    game_state TEXT,
                    session_id INTEGER,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # Commands sent to emulator
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS commands (
                    command_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    command_type TEXT,
                    command_value TEXT,
                    reasoning TEXT,
                    confidence REAL,
                    success BOOLEAN,
                    error_message TEXT,
                    execution_time_ms REAL,
                    session_id INTEGER,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # AI thinking processes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_thoughts (
                    thought_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    thought_process TEXT,
                    reasoning TEXT,
                    game_context TEXT,
                    proposed_action TEXT,
                    confidence REAL,
                    model_used TEXT,
                    tokens_used INTEGER,
                    session_id INTEGER,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # Battle tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS battles (
                    battle_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_tick INTEGER,
                    end_tick INTEGER,
                    start_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    end_time TEXT,
                    enemy_pokemon TEXT,
                    enemy_level INTEGER,
                    player_pokemon TEXT,
                    player_level INTEGER,
                    outcome TEXT,
                    turns_taken INTEGER,
                    session_id INTEGER,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # Battle turns (detailed per-turn data)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS battle_turns (
                    turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    battle_id INTEGER,
                    turn_number INTEGER,
                    player_action TEXT,
                    enemy_action TEXT,
                    player_hp_before INTEGER,
                    player_hp_after INTEGER,
                    enemy_hp_before INTEGER,
                    enemy_hp_after INTEGER,
                    effectiveness TEXT,
                    FOREIGN KEY(battle_id) REFERENCES battles(battle_id)
                )
            """)
            
            # Pokemon encountered
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pokemon (
                    pokemon_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    species TEXT,
                    level INTEGER,
                    types TEXT,
                    caught BOOLEAN DEFAULT FALSE,
                    location TEXT,
                    tick_encountered INTEGER,
                    session_id INTEGER,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # Performance metrics snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    win_rate REAL,
                    avg_damage_ratio REAL,
                    commands_per_minute REAL,
                    avg_confidence REAL,
                    session_id INTEGER,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # Training runs (for comparing different AI models)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS training_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT,
                    model_config TEXT,
                    session_id INTEGER,
                    ticks_completed INTEGER,
                    final_score REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # Create indexes for better query performance
            cursor.executescript("""
                CREATE INDEX IF NOT EXISTS idx_screenshots_tick ON screenshots(tick);
                CREATE INDEX IF NOT EXISTS idx_commands_tick ON commands(tick);
                CREATE INDEX IF NOT EXISTS idx_thoughts_tick ON ai_thoughts(tick);
                CREATE INDEX IF NOT EXISTS idx_battles_session ON battles(session_id);
                CREATE INDEX IF NOT EXISTS idx_battles_outcome ON battles(outcome);
                CREATE INDEX IF NOT EXISTS idx_pokemon_species ON pokemon(species);
            """)
            
            conn.commit()
    
    def start_session(self, rom_path: str, model_name: str = "unknown") -> int | None:
        """
        Start a new tracked session
        
        Args:
            rom_path: Path to ROM file
            model_name: Name of AI model being used
            
        Returns:
            session_id: New session ID
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sessions (rom_path, model_name, start_time) VALUES (?, ?, ?)",
                (rom_path, model_name, datetime.now().isoformat())
            )
            session_id = cursor.lastrowid
            conn.commit()
            print(f"✅ Database: Started session {session_id} with model '{model_name}'")
            return session_id
    
    def end_session(self, final_metrics: Dict[str, Any]):
        """
        End current session with final metrics
        
        Args:
            final_metrics: Dictionary with final stats
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions 
                SET end_time = ?, total_ticks = ?, total_commands = ?, 
                    total_battles = ?, badges_earned = ?, final_state = ?
                WHERE session_id = (SELECT MAX(session_id) FROM sessions)
            """, (
                datetime.now().isoformat(),
                final_metrics.get("total_ticks", 0),
                final_metrics.get("total_commands", 0),
                final_metrics.get("total_battles", 0),
                final_metrics.get("badges_earned", 0),
                json.dumps(final_metrics.get("final_state", {}))
            ))
            conn.commit()
            print("✅ Database: Session ended and metrics saved")
    
    def log_screenshot(self, tick: int, file_path: str, game_state: Dict[str, Any]):
        """Log a screenshot capture event"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO screenshots (tick, file_path, game_state, session_id)
                VALUES (?, ?, ?, (SELECT MAX(session_id) FROM sessions))
            """, (
                tick,
                file_path,
                json.dumps(game_state)
            ))
            conn.commit()
    
    def log_command(self, command_data: Dict[str, Any]):
        """
        Log a command sent to emulator
        
        Args:
            command_data: Dictionary containing:
                - tick: Current tick
                - command_type: "press", "hold", "sequence", "batch"
                - command_value: The actual button/command
                - reasoning: AI's reasoning
                - confidence: AI confidence (0-1)
                - success: Whether command succeeded
                - error_message: Error if failed
                - execution_time_ms: Time to execute
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO commands (
                    tick, command_type, command_value, reasoning, confidence,
                    success, error_message, execution_time_ms, session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, (SELECT MAX(session_id) FROM sessions))
            """, (
                command_data["tick"],
                command_data["command_type"],
                command_data["command_value"],
                command_data.get("reasoning", ""),
                command_data.get("confidence", 0.0),
                command_data.get("success", True),
                command_data.get("error_message", None),
                command_data.get("execution_time_ms", 0)
            ))
            conn.commit()
    
    def log_ai_thought(self, thought_data: Dict[str, Any]):
        """
        Log AI thinking process
        
        Args:
            thought_data: Dictionary containing:
                - tick: Current tick
                - thought_process: What the AI is thinking
                - reasoning: Detailed reasoning
                - game_context: Current game state context
                - proposed_action: What action AI wants to take
                - confidence: Confidence level
                - model_used: Which AI model
                - tokens_used: Prompt/completion tokens
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ai_thoughts (
                    tick, thought_process, reasoning, game_context,
                    proposed_action, confidence, model_used, tokens_used, session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, (SELECT MAX(session_id) FROM sessions))
            """, (
                thought_data["tick"],
                thought_data.get("thought_process", ""),
                thought_data.get("reasoning", ""),
                json.dumps(thought_data.get("game_context", {})),
                thought_data.get("proposed_action", ""),
                thought_data.get("confidence", 0.0),
                thought_data.get("model_used", "unknown"),
                thought_data.get("tokens_used", 0)
            ))
            conn.commit()
    
    def log_battle_start(self, battle_data: Dict[str, Any]) -> int | None:
        """
        Start tracking a battle
        
        Args:
            battle_data: Dictionary with battle info
            
        Returns:
            battle_id: ID of new battle record
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO battles (
                    start_tick, enemy_pokemon, enemy_level, 
                    player_pokemon, player_level, outcome, session_id
                ) VALUES (?, ?, ?, ?, ?, 'ongoing', (SELECT MAX(session_id) FROM sessions))
            """, (
                battle_data["tick"],
                battle_data.get("enemy_pokemon"),
                battle_data.get("enemy_level"),
                battle_data.get("player_pokemon"),
                battle_data.get("player_level")
            ))
            battle_id = cursor.lastrowid
            conn.commit()
            return battle_id
    
    def log_battle_end(self, battle_id: int, outcome: str, turns_taken: int):
        """End a battle with outcome"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE battles 
                SET end_time = ?, end_tick = ?, outcome = ?, turns_taken = ?
                WHERE battle_id = ?
            """, (
                datetime.now().isoformat(),
                None,  # Will be filled by current tick
                outcome,
                turns_taken,
                battle_id
            ))
            conn.commit()
    
    def log_battle_turn(self, battle_id: int, turn_data: Dict[str, Any]):
        """Log a single battle turn"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO battle_turns (
                    battle_id, turn_number, player_action, enemy_action,
                    player_hp_before, player_hp_after, enemy_hp_before, enemy_hp_after, effectiveness
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                battle_id,
                turn_data["turn_number"],
                turn_data.get("player_action"),
                turn_data.get("enemy_action"),
                turn_data.get("player_hp_before"),
                turn_data.get("player_hp_after"),
                turn_data.get("enemy_hp_before"),
                turn_data.get("enemy_hp_after"),
                turn_data.get("effectiveness")
            ))
            conn.commit()
    
    def get_session_summary(self, session_id: int) -> Dict[str, Any]:
        """Get summary statistics for a session"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM sessions WHERE session_id = ?
            """, (session_id,))
            session = cursor.fetchone()
            
            if not session:
                return {}
            
            columns = [desc[0] for desc in cursor.description]
            session_dict = dict(zip(columns, session))
            
            # Get battle stats
            cursor.execute("""
                SELECT COUNT(*) as total_battles,
                       SUM(CASE WHEN outcome = 'victory' THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN outcome = 'defeat' THEN 1 ELSE 0 END) as losses
                FROM battles WHERE session_id = ?
            """, (session_id,))
            battle_stats = cursor.fetchone()
            
            if battle_stats:
                session_dict.update({
                    "wins": battle_stats[1] or 0,
                    "losses": battle_stats[2] or 0,
                    "win_rate": (battle_stats[1] / battle_stats[0]) if battle_stats[0] > 0 else 0
                })
            
            return session_dict
    
    def export_session_data(self, session_id: int, format: str = "json") -> str:
        """Export all session data for analysis"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Collect all data
            data = {
                "session": self._get_session_data(cursor, session_id),
                "commands": self._get_commands(cursor, session_id),
                "thoughts": self._get_thoughts(cursor, session_id),
                "battles": self._get_battles(cursor, session_id),
                "screenshots": self._get_screenshots(cursor, session_id)
            }
        
        output_path = f"session_{session_id}_export.json"
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        
        return output_path
    
    def _get_session_data(self, cursor, session_id: int) -> Dict:
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        return dict(zip([d[0] for d in cursor.description], cursor.fetchone())) if cursor.fetchone() else {}
    
    def _get_commands(self, cursor, session_id: int) -> List[Dict]:
        cursor.execute("SELECT * FROM commands WHERE session_id = ?", (session_id,))
        return [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
    
    def _get_thoughts(self, cursor, session_id: int) -> List[Dict]:
        cursor.execute("SELECT * FROM ai_thoughts WHERE session_id = ?", (session_id,))
        return [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
    
    def _get_battles(self, cursor, session_id: int) -> List[Dict]:
        cursor.execute("SELECT * FROM battles WHERE session_id = ?", (session_id,))
        return [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
    
    def _get_screenshots(self, cursor, session_id: int) -> List[Dict]:
        cursor.execute("SELECT * FROM screenshots WHERE session_id = ?", (session_id,))
        return [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]

    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        Internal method to execute a SQL query with proper error handling.

        Args:
            query: SQL query string
            params: Tuple of parameters for the query

        Returns:
            sqlite3.Cursor object

        Raises:
            ConstraintViolationError: If a constraint violation occurs
            DatabaseError: For other database errors
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return cursor
        except sqlite3.IntegrityError as e:
            logger.error(f"Constraint violation in query: {query} with params {params}: {e}")
            raise ConstraintViolationError(f"Database constraint violated: {e}") from e
        except sqlite3.Error as e:
            logger.error(f"Database error in query: {query} with params {params}: {e}")
            raise DatabaseError(f"Database operation failed: {e}") from e

    def close(self):
        """
        Close the database connection and perform cleanup.
        Since this implementation uses context managers internally,
        this method is primarily a no-op for API compatibility.
        """
        logger.info("Database connection closed")
        pass

    def get_session(self, session_id: int) -> Dict[str, Any]:
        """
        Get a session by its ID.

        Args:
            session_id: The session ID to retrieve

        Returns:
            Dictionary containing session data

        Raises:
            sqlite3.OperationalError: If session is not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row is None:
                raise sqlite3.OperationalError(f"Session {session_id} not found")
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))

    def save_session_data(self, data: Dict[str, Any]) -> bool:
        """
        Save arbitrary session data to the database.

        Args:
            data: Dictionary of data to save

        Returns:
            True if successful, False otherwise

        Raises:
            KeyboardInterrupt: If operation is interrupted
        """
        try:
            self._execute(
                "INSERT INTO sessions (rom_path, model_name, final_state) VALUES (?, ?, ?)",
                (
                    data.get("rom_path", "unknown"),
                    data.get("model_name", "unknown"),
                    json.dumps(data)
                )
            )
            return True
        except KeyboardInterrupt:
            logger.warning("Session data save interrupted")
            raise


# Create database instance with default path
default_db = GameDatabase("./game_data.db")