"""
Comprehensive Logging System for AI Plays Pokemon

Provides file-based structured logging with:
- Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Log file rotation (10MB files, 10 backups)
- Structured JSON logging
- Category-based logging (decisions, battles, errors, performance, api)
- Log level filtering
- Real-time log viewing support
"""

import os
import sys
import json
import gzip
import shutil
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
from functools import wraps
from pathlib import Path as FilePath
import traceback


class LogCategory:
    """Log category constants"""
    MAIN = "main"
    DECISIONS = "decisions"
    BATTLES = "battles"
    ERRORS = "errors"
    PERFORMANCE = "performance"
    API = "api"
    VISION = "vision"
    EMULATOR = "emulator"
    MEMORY = "memory"


class LogLevel:
    """Log level constants matching Python logging"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


# Level names for display
LOG_LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL"
}


class LogRotation:
    """Log rotation configuration"""
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    MAX_BACKUPS = 10
    ENCODING = "utf-8"


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def __init__(self, include_fields: Optional[List[str]] = None):
        super().__init__()
        self.include_fields = include_fields or [
            "timestamp", "level", "category", "message", "module", 
            "function", "line", "session_id", "tick"
        ]
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        # Get category and extra data from record
        category = getattr(record, "category", LogCategory.MAIN)
        extra_data = getattr(record, "extra_data", {})
        session_id = getattr(record, "session_id", "")
        tick = getattr(record, "tick", 0)
        
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": LOG_LEVEL_NAMES.get(record.levelno, "UNKNOWN"),
            "category": category,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "session_id": session_id,
            "tick": tick,
        }
        
        # Add extra data
        if extra_data:
            log_data["extra_data"] = extra_data
        
        # Include exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info) if record.exc_info[0] else None
            }
        
        if record.stack_info:
            log_data["stack_info"] = record.stack_info
        
        # Filter to include only specified fields
        filtered_data = {
            k: v for k, v in log_data.items() 
            if v is not None and v != "" and (not self.include_fields or k in self.include_fields)
        }
        
        return json.dumps(filtered_data, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    """Human-readable formatter"""
    
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        super().__init__(fmt=fmt or "%(asctime)s [%(levelname)s] [%(category)s] %(message)s", datefmt=datefmt)
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as human-readable string"""
        # Add category to record
        category = getattr(record, "category", LogCategory.MAIN)
        
        # Create formatted message
        formatter = logging.Formatter(self._fmt, self.datefmt)
        base_format = formatter.format(record)
        
        # Add extra data if present
        extra_data = getattr(record, "extra_data", {})
        if extra_data:
            extra_str = " | " + ", ".join(f"{k}={v}" for k, v in extra_data.items())
            return base_format + extra_str
        
        return base_format


class CategoryFilter(logging.Filter):
    """Filter logs by category"""
    
    def __init__(self, categories: Optional[List[str]] = None, exclude: bool = False):
        super().__init__()
        self.categories = set(categories or [])
        self.exclude = exclude
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Check if record should be logged"""
        record_category = getattr(record, "category", LogCategory.MAIN)
        
        if self.exclude:
            return record_category not in self.categories
        else:
            if not self.categories:
                return True
            return record_category in self.categories


class RotationFileHandler(logging.FileHandler):
    """File handler with automatic rotation"""
    
    def __init__(self, filename: str, mode: str = 'a', 
                 max_bytes: int = LogRotation.MAX_FILE_SIZE, 
                 backup_count: int = LogRotation.MAX_BACKUPS,
                 encoding: str = LogRotation.ENCODING,
                 delay: bool = False):
        super().__init__(filename, mode, encoding, delay)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._rotate_lock = threading.Lock()
        self._current_size = 0
        if os.path.exists(self.baseFilename):
            self._current_size = os.path.getsize(self.baseFilename)
    
    def should_rotate(self) -> bool:
        """Check if rotation is needed"""
        if self.max_bytes > 0:
            return self._current_size >= self.max_bytes
        return False
    
    def rotate(self):
        """Rotate log files"""
        with self._rotate_lock:
            if not self.should_rotate():
                return
            
            # Close current file
            if self.stream:
                self.stream.close()
                self.stream = None  # type: ignore[assignment]
            
            # Rename current file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_filename = f"{self.baseFilename}.{timestamp}"
            
            if os.path.exists(self.baseFilename):
                os.rename(self.baseFilename, new_filename)
                self._current_size = 0
            
            # Compress old log
            if os.path.exists(new_filename):
                self._compress_file(new_filename)
            
            # Remove old backups
            self._clean_old_backups()
    
    def _compress_file(self, filename: str):
        """Compress file with gzip"""
        try:
            with open(filename, 'rb') as f_in:
                with gzip.open(filename + '.gz', 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.remove(filename)
        except Exception:
            pass  # Ignore compression errors
    
    def _clean_old_backups(self):
        """Clean old backup files"""
        if self.backup_count <= 0:
            return
        
        base_dir = os.path.dirname(self.baseFilename)
        base_name = os.path.basename(self.baseFilename)
        
        # Find all backup files
        backups = []
        for f in os.listdir(base_dir):
            if f.startswith(base_name) and f != base_name:
                filepath = os.path.join(base_dir, f)
                try:
                    backups.append((filepath, os.path.getmtime(filepath)))
                except OSError:
                    continue
        
        # Sort by modification time (oldest first)
        backups.sort(key=lambda x: x[1])
        
        # Remove old backups
        while len(backups) > self.backup_count:
            oldest = backups.pop(0)
            try:
                os.remove(oldest[0])
            except OSError:
                pass
    
    def emit(self, record: logging.LogRecord):
        """Emit record with rotation check"""
        try:
            formatted = self.format(record)
            self._current_size += len(formatted)
        except Exception:
            self._current_size += 100  # Fallback size estimate
        
        if self.should_rotate():
            self.rotate()
        super().emit(record)


class AILogger:
    """
    Main logger class for AI Plays Pokemon
    
    Provides comprehensive logging capabilities:
    - Multiple output handlers (console, file, JSON file)
    - Category-based filtering
    - Automatic log rotation
    - Session-based log organization
    - Performance tracking
    """
    
    _instance: Optional['AILogger'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize logger"""
        if self._initialized:
            return
        
        self._initialized = True
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._base_log_dir = Path("logs")
        self._setup_complete = False
        
        # Initialize logger
        self.logger = logging.getLogger("ai_plays_poke")
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Default configuration
        self._config = {
            "log_level": logging.INFO,
            "console_log_level": logging.INFO,
            "file_log_level": logging.DEBUG,
            "json_log_level": logging.INFO,
            "enable_rotation": True,
            "max_file_size": LogRotation.MAX_FILE_SIZE,
            "max_backups": LogRotation.MAX_BACKUPS,
            "categories": None,  # None means log all
            "session_id": self._session_id
        }
    
    def setup(self, log_dir: Optional[str] = None, 
              config: Optional[Dict[str, Any]] = None) -> None:
        """
        Set up logging system
        
        Args:
            log_dir: Base log directory (default: logs/)
            config: Configuration dict with logging options
        """
        if self._setup_complete:
            self.warning("Logger already initialized, skipping setup")
            return
        
        # Update config
        if config:
            self._config.update(config)
        
        # Set log directory
        if log_dir:
            self._base_log_dir = Path(log_dir)
        else:
            self._base_log_dir = Path(self._config.get("log_dir", "logs"))
        
        # Create log directory structure
        self._create_log_directories()
        
        # Add handlers
        self._add_console_handler()
        self._add_file_handlers()
        
        # Store session ID in config
        self._config["session_id"] = self._session_id
        
        self._setup_complete = True
        self.info("🪵 Logging system initialized", category=LogCategory.MAIN)
        self.info(f"📁 Log directory: {self._base_log_dir}", category=LogCategory.MAIN)
        self.info(f"🆔 Session ID: {self._session_id}", category=LogCategory.MAIN)
    
    def _create_log_directories(self) -> None:
        """Create log directory structure"""
        self._base_log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create category subdirectories
        categories = [
            LogCategory.DECISIONS,
            LogCategory.BATTLES,
            LogCategory.ERRORS,
            LogCategory.PERFORMANCE,
            LogCategory.API,
            LogCategory.VISION,
            LogCategory.EMULATOR,
            LogCategory.MEMORY
        ]
        
        for category in categories:
            (self._base_log_dir / category).mkdir(exist_ok=True)
    
    def _add_console_handler(self) -> None:
        """Add console handler"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self._config.get("console_log_level", logging.INFO))
        console_handler.setFormatter(PlainFormatter())
        self.logger.addHandler(console_handler)
    
    def _add_file_handlers(self) -> None:
        """Add file handlers for different log types"""
        log_level = self._config.get("file_log_level", logging.DEBUG)
        max_bytes = self._config.get("max_file_size", LogRotation.MAX_FILE_SIZE)
        max_backups = self._config.get("max_backups", LogRotation.MAX_BACKUPS)
        
        # Main log file (text format)
        main_log_file = self._base_log_dir / "main.log"
        main_handler = RotationFileHandler(
            str(main_log_file),
            max_bytes=max_bytes,
            backup_count=max_backups
        )
        main_handler.setLevel(log_level)
        main_handler.setFormatter(PlainFormatter())
        self.logger.addHandler(main_handler)
        
        # JSON log file (structured data)
        json_log_file = self._base_log_dir / "structured.json.log"
        json_handler = RotationFileHandler(
            str(json_log_file),
            max_bytes=max_bytes,
            backup_count=max_backups
        )
        json_handler.setLevel(self._config.get("json_log_level", logging.INFO))
        json_handler.setFormatter(JSONFormatter())
        self.logger.addHandler(json_handler)
        
        # Category-specific logs
        self._add_category_file_handler(LogCategory.DECISIONS, log_level, max_bytes, max_backups)
        self._add_category_file_handler(LogCategory.BATTLES, log_level, max_bytes, max_backups)
        self._add_category_file_handler(LogCategory.ERRORS, logging.DEBUG, max_bytes, max_backups)
        self._add_category_file_handler(LogCategory.PERFORMANCE, logging.DEBUG, max_bytes, max_backups)
        self._add_category_file_handler(LogCategory.API, logging.DEBUG, max_bytes, max_backups)
    
    def _add_category_file_handler(self, category: str, log_level: int, 
                                    max_bytes: int, max_backups: int) -> None:
        """Add file handler for specific category"""
        category_dir = self._base_log_dir / category
        category_log_file = category_dir / f"{category}.log"
        
        handler = RotationFileHandler(
            str(category_log_file),
            max_bytes=max_bytes,
            backup_count=max_backups
        )
        handler.setLevel(log_level)
        handler.setFormatter(PlainFormatter())
        handler.addFilter(CategoryFilter(categories=[category]))
        self.logger.addHandler(handler)
    
    def _log_with_category(self, level: int, message: str, category: str,
                           tick: int = 0, **extra) -> None:
        """Internal logging method with category support"""
        # Build extra dict with our custom fields
        extra_data = extra.copy()
        extra_data["category"] = category
        extra_data["session_id"] = self._session_id
        extra_data["tick"] = tick
        
        # Use the logging methods that accept extra
        self.logger.log(level, message, extra=extra_data)
    
    # ============ Logging Methods ============
    
    def debug(self, message: str, category: str = LogCategory.MAIN,
              tick: int = 0, **extra) -> None:
        """Log debug message"""
        self._log_with_category(logging.DEBUG, message, category, tick, **extra)
    
    def info(self, message: str, category: str = LogCategory.MAIN,
             tick: int = 0, **extra) -> None:
        """Log info message"""
        self._log_with_category(logging.INFO, message, category, tick, **extra)
    
    def warning(self, message: str, category: str = LogCategory.MAIN,
                tick: int = 0, **extra) -> None:
        """Log warning message"""
        self._log_with_category(logging.WARNING, message, category, tick, **extra)
    
    def error(self, message: str, category: str = LogCategory.ERRORS,
              tick: int = 0, **extra) -> None:
        """Log error message"""
        self._log_with_category(logging.ERROR, message, category, tick, **extra)
    
    def critical(self, message: str, category: str = LogCategory.ERRORS,
                 tick: int = 0, **extra) -> None:
        """Log critical message"""
        self._log_with_category(logging.CRITICAL, message, category, tick, **extra)
    
    # ============ Specialized Logging Methods ============
    
    def log_decision(self, tick: int, decision_id: str, action: str, 
                     reasoning: str, game_state: Dict[str, Any]) -> None:
        """Log AI decision with full context"""
        self.info(
            f"Decision: {action} | Reasoning: {reasoning[:100]}...",
            category=LogCategory.DECISIONS,
            tick=tick,
            decision_id=decision_id,
            action=action,
            reasoning=reasoning,
            game_state=game_state
        )
    
    def log_battle_event(self, tick: int, event_type: str, 
                         pokemon: str, hp: float, action: Optional[str] = None) -> None:
        """Log battle event"""
        msg = f"Battle {event_type}: {pokemon} (HP: {hp}%)"
        if action:
            msg += f" | Action: {action}"
        
        self.info(
            msg,
            category=LogCategory.BATTLES,
            tick=tick,
            event_type=event_type,
            pokemon=pokemon,
            hp=hp,
            action=action
        )
    
    def log_api_call(self, model: str, duration_ms: float, 
                     input_tokens: int, output_tokens: int, 
                     cost: float, success: bool = True) -> None:
        """Log API call details"""
        self.info(
            f"API: {model} | {duration_ms:.0f}ms | "
            f"In: {input_tokens} | Out: {output_tokens} | "
            f"${cost:.6f} | Success: {success}",
            category=LogCategory.API,
            model=model,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            success=success
        )
    
    def log_vision_analysis(self, tick: int, screen_type: str, 
                            enemy_pokemon: str, player_hp: float,
                            enemy_hp: float, confidence: float = 1.0) -> None:
        """Log vision analysis result"""
        self.debug(
            f"Vision: {screen_type} | Enemy: {enemy_pokemon or 'None'} | "
            f"HP: {player_hp:.0f}%/{enemy_hp:.0f}% | Confidence: {confidence:.2f}",
            category=LogCategory.VISION,
            tick=tick,
            screen_type=screen_type,
            enemy_pokemon=enemy_pokemon,
            player_hp=player_hp,
            enemy_hp=enemy_hp,
            confidence=confidence
        )
    
    def log_performance_metric(self, metric_name: str, value: float, 
                               unit: str = "", tick: int = 0) -> None:
        """Log performance metric"""
        self.debug(
            f"Performance: {metric_name} = {value} {unit}",
            category=LogCategory.PERFORMANCE,
            tick=tick,
            metric_name=metric_name,
            value=value,
            unit=unit
        )
    
    def log_error_with_context(self, error: Exception, context: Dict[str, Any],
                               category: str = LogCategory.ERRORS) -> None:
        """Log error with full context"""
        self.error(
            f"Error: {type(error).__name__}: {str(error)}",
            category=category,
            **context,
            exc_info=True
        )
    
    # ============ Session Management ============
    
    def get_session_id(self) -> str:
        """Get current session ID"""
        return self._session_id
    
    def get_log_directory(self) -> Path:
        """Get log directory path"""
        return self._base_log_dir
    
    def get_log_files(self) -> Dict[str, Path]:
        """Get all log files"""
        files = {}
        if self._base_log_dir.exists():
            for f in self._base_log_dir.rglob("*.log"):
                if f.is_file():
                    files[str(f.relative_to(self._base_log_dir))] = f
        return files
    
    def get_log_size(self) -> Dict[str, int]:
        """Get total log file sizes"""
        sizes = {}
        for category in [LogCategory.MAIN] + [
            LogCategory.DECISIONS, LogCategory.BATTLES, 
            LogCategory.ERRORS, LogCategory.PERFORMANCE, LogCategory.API
        ]:
            log_file = self._base_log_dir / category / f"{category}.log"
            if log_file.exists():
                sizes[category] = log_file.stat().st_size
            else:
                sizes[category] = 0
        return sizes
    
    # ============ Utility Methods ============
    
    def set_level(self, level: Union[int, str]) -> None:
        """Set global log level"""
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)
        self._config["log_level"] = level
        self.logger.setLevel(level)
    
    def get_level(self) -> int:
        """Get current log level"""
        return self.logger.level
    
    def flush(self) -> None:
        """Flush all log handlers"""
        for handler in self.logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()
    
    def close(self) -> None:
        """Close all log handlers"""
        for handler in self.logger.handlers:
            handler.close()
        self._setup_complete = False


# ============ Decorators for Easy Logging ============

def log_function_call(category: str = LogCategory.MAIN, 
                      log_args: bool = False, log_result: bool = True):
    """
    Decorator to log function calls
    
    Args:
        category: Log category for the function calls
        log_args: Whether to log function arguments
        log_result: Whether to log function result
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger()
            
            # Log function call
            if log_args:
                logger.debug(
                    f"Calling {func.__name__}({args}, {kwargs})",
                    category=category
                )
            else:
                logger.debug(f"Calling {func.__name__}()", category=category)
            
            # Call function
            start_time = datetime.now()
            try:
                result = func(*args, **kwargs)
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                # Log result
                if log_result:
                    logger.debug(
                        f"{func.__name__} completed in {duration_ms:.2f}ms: {result}",
                        category=category,
                        duration_ms=duration_ms,
                        result=result
                    )
                
                return result
                
            except Exception as e:
                logger.log_error_with_context(
                    e, 
                    {"function": func.__name__, "args": str(args), "kwargs": str(kwargs)},
                    category=category
                )
                raise
        
        return wrapper
    return decorator


# ============ Global Logger Instance ============

def get_logger() -> AILogger:
    """Get global logger instance"""
    return AILogger()


# ============ Initialize with Environment ============

def setup_from_env(log_dir: Optional[str] = None) -> AILogger:
    """Set up logger from environment variables"""
    logger = get_logger()
    
    # Get configuration from environment
    config = {}
    
    # Log level
    log_level = os.environ.get("AI_LOG_LEVEL", "INFO")
    config["log_level"] = getattr(logging, log_level.upper(), logging.INFO)
    
    # Console log level
    console_level = os.environ.get("AI_CONSOLE_LOG_LEVEL", "INFO")
    config["console_log_level"] = getattr(logging, console_level.upper(), logging.INFO)
    
    # File log level
    file_level = os.environ.get("AI_FILE_LOG_LEVEL", "DEBUG")
    config["file_log_level"] = getattr(logging, file_level.upper(), logging.DEBUG)
    
    # Enable rotation
    config["enable_rotation"] = os.environ.get("AI_LOG_ROTATION", "true").lower() == "true"
    
    # Max file size
    max_size = os.environ.get("AI_LOG_MAX_SIZE", "10485760")  # 10MB default
    try:
        config["max_file_size"] = int(max_size)
    except ValueError:
        config["max_file_size"] = 10 * 1024 * 1024
    
    # Max backups
    max_backups = os.environ.get("AI_LOG_MAX_BACKUPS", "10")
    try:
        config["max_backups"] = int(max_backups)
    except ValueError:
        config["max_backups"] = 10
    
    # Setup logger
    logger.setup(log_dir=log_dir, config=config)
    
    return logger


# ============ Example Usage ============

if __name__ == "__main__":
    # Initialize logger
    logger = setup_from_env()
    
    # Test logging
    logger.info("🪵 Test message - Logger initialized successfully!")
    
    # Log with category
    logger.debug("Debug message", category=LogCategory.DECISIONS)
    logger.info("Info message", category=LogCategory.BATTLES)
    logger.warning("Warning message", category=LogCategory.ERRORS)
    
    # Log specialized events
    logger.log_decision(
        tick=123,
        decision_id="dec_001",
        action="press:A",
        reasoning="Enemy has low HP, finish with basic attack",
        game_state={"screen": "battle", "turn": 3}
    )
    
    logger.log_battle_event(
        tick=124,
        event_type="attack",
        pokemon="Charmander",
        hp=85.0,
        action="Ember"
    )
    
    logger.log_api_call(
        model="openai/gpt-4o",
        duration_ms=1500.5,
        input_tokens=429,
        output_tokens=24,
        cost=0.005010
    )
    
    logger.log_vision_analysis(
        tick=125,
        screen_type="battle",
        enemy_pokemon="Pidgey",
        player_hp=85.0,
        enemy_hp=20.0,
        confidence=0.95
    )
    
    # Log performance metric
    logger.log_performance_metric("decision_latency_ms", 142.5, tick=125)
    
    # Log error with context
    try:
        raise ValueError("Test error")
    except Exception as e:
        logger.log_error_with_context(
            e,
            {"action": "test_action", "state": "testing"},
            category=LogCategory.ERRORS
        )
    
    # Get log info
    print(f"\n📊 Session ID: {logger.get_session_id()}")
    print(f"📁 Log Directory: {logger.get_log_directory()}")
    print(f"📈 Log Files: {logger.get_log_files()}")
    print(f"💾 Log Sizes: {logger.get_log_size()}")
    
    # Cleanup
    logger.close()
    print("\n✅ Logger test complete!")