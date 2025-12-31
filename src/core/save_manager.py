"""
Save State Manager for PTP-01X Pokemon AI

Provides comprehensive save state management:
- PyBoy native save state integration
- Snapshot creation with metadata
- Automatic snapshot rotation
- Event-triggered snapshots
- Emergency recovery snapshots
- CLI-configurable behavior

Integration Points:
- src/core/emulator.py - PyBoy save/load state methods
- src/game_loop.py - Snapshot triggering during game loop
- src/core/failsafe.py - Emergency recovery snapshots
- src/ptp_cli/flags.py - CLI configuration
"""

import json
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from collections import OrderedDict
import threading
import logging


logger = logging.getLogger(__name__)


class SnapshotReason(Enum):
    """Reason for snapshot creation"""
    MANUAL = "manual"
    INTERVAL = "interval"
    BATTLE_START = "battle_start"
    BATTLE_END = "battle_end"
    LEVEL_UP = "level_up"
    LOCATION_CHANGE = "location_change"
    CATCH = "catch"
    BADGE = "badge"
    EVENT = "event"
    EMERGENCY = "emergency"
    PRE_RECOVERY = "pre_recovery"


@dataclass
class SnapshotMetadata:
    """Metadata for a save state snapshot"""
    snapshot_id: str
    created_at: str
    tick_count: int
    reason: str
    state_description: str
    location: Optional[str] = None
    badges: int = 0
    team_hp_percent: Optional[float] = None
    file_size: int = 0
    is_valid: bool = True
    game_state: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SnapshotMetadata':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class SaveManagerConfig:
    """Configuration for SaveManager"""
    save_dir: str = "./game_saves"
    max_snapshots: int = 10
    snapshot_interval_ticks: int = 1000
    save_on_events: List[str] = field(default_factory=lambda: ["battle", "level_up", "badge"])
    compress_old: bool = False
    validate_on_save: bool = False
    emergency_snapshot_count: int = 3


class SaveManager:
    """
    Comprehensive save state manager for Pokemon AI
    
    Features:
    - Create snapshots with full metadata
    - Load snapshots by ID
    - List available snapshots
    - Automatic rotation keeping last N snapshots
    - Event-triggered snapshots
    - Emergency snapshots preserved separately
    - Thread-safe operations
    """
    
    def __init__(self, config: Optional[SaveManagerConfig] = None):
        """
        Initialize SaveManager
        
        Args:
            config: Optional configuration, uses defaults if not provided
        """
        self.config = config or SaveManagerConfig()
        self.save_dir = Path(self.config.save_dir)
        self.snapshots_dir = self.save_dir / "snapshots"
        self.emergency_dir = self.save_dir / "emergency_snapshots"
        self.metadata_file = self.snapshots_dir / "snapshots.json"
        
        self._lock = threading.Lock()
        self._snapshot_cache: OrderedDict[str, SnapshotMetadata] = OrderedDict()
        self._last_snapshot_tick: int = 0
        self._tick_count: int = 0
        
        self._setup_directories()
        self._load_snapshot_index()
    
    def _setup_directories(self) -> None:
        """Create necessary directories"""
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.emergency_dir.mkdir(parents=True, exist_ok=True)
    
    def _generate_snapshot_id(self, reason: SnapshotReason) -> str:
        """Generate unique snapshot ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{reason.value}_{timestamp}_{int(time.time() * 1000 % 10000)}"
    
    def _load_snapshot_index(self) -> None:
        """Load existing snapshot metadata from index file"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    data = json.load(f)
                    for snapshot_data in data:
                        metadata = SnapshotMetadata.from_dict(snapshot_data)
                        self._snapshot_cache[metadata.snapshot_id] = metadata
            except Exception as e:
                logger.warning(f"Failed to load snapshot index: {e}")
    
    def _save_snapshot_index(self) -> None:
        """Save snapshot metadata to index file"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(
                    [asdict(m) for m in self._snapshot_cache.values()],
                    f,
                    indent=2
                )
        except Exception as e:
            logger.error(f"Failed to save snapshot index: {e}")
    
    def set_tick_count(self, tick_count: int) -> None:
        """Update the current tick count"""
        with self._lock:
            self._tick_count = tick_count
    
    def save_snapshot(
        self,
        emulator,
        tick_count: int,
        reason: SnapshotReason,
        state_description: str = "",
        game_state: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """
        Create a snapshot with full emulator state and metadata
        
        Args:
            emulator: EmulatorInterface instance
            tick_count: Current tick count
            reason: Reason for snapshot
            state_description: Human-readable description of state
            game_state: Optional game state information
            
        Returns:
            Tuple of (success: bool, snapshot_id: str)
        """
        with self._lock:
            try:
                snapshot_id = self._generate_snapshot_id(reason)
                state_path = self.snapshots_dir / f"{snapshot_id}.state"
                
                state_bytes = emulator.get_state_bytes()
                if not state_bytes:
                    logger.error("Failed to get state bytes from emulator")
                    return False, ""
                
                with open(state_path, 'wb') as f:
                    f.write(state_bytes)
                
                location = None
                badges = 0
                team_hp_percent = None
                
                if game_state:
                    location = game_state.get("location")
                    badges = game_state.get("badges", 0)
                    team_info = game_state.get("team")
                    if team_info and isinstance(team_info, list) and len(team_info) > 0:
                        first_pokemon = team_info[0]
                        if isinstance(first_pokemon, dict):
                            team_hp_percent = first_pokemon.get("hp_percent")
                        elif isinstance(first_pokemon, str):
                            team_hp_percent = 100.0
                
                metadata = SnapshotMetadata(
                    snapshot_id=snapshot_id,
                    created_at=datetime.now().isoformat(),
                    tick_count=tick_count,
                    reason=reason.value,
                    state_description=state_description or f"Snapshot at tick {tick_count}",
                    location=location,
                    badges=badges,
                    team_hp_percent=team_hp_percent,
                    file_size=len(state_bytes),
                    is_valid=True,
                    game_state=game_state
                )
                
                self._snapshot_cache[snapshot_id] = metadata
                self._last_snapshot_tick = tick_count
                
                self._cleanup_old_snapshots()
                self._save_snapshot_index()
                
                logger.info(f"Snapshot created: {snapshot_id} ({len(state_bytes)} bytes)")
                return True, snapshot_id
                
            except Exception as e:
                logger.error(f"Failed to save snapshot: {e}")
                return False, ""
    
    def _cleanup_old_snapshots(self) -> int:
        """Remove old snapshots, keeping most recent N"""
        max_snapshots = self.config.max_snapshots
        
        while len(self._snapshot_cache) > max_snapshots:
            oldest_id = next(iter(self._snapshot_cache))
            metadata = self._snapshot_cache.pop(oldest_id)
            
            state_file = self.snapshots_dir / f"{oldest_id}.state"
            if state_file.exists():
                state_file.unlink()
            
            logger.info(f"Cleaned up old snapshot: {oldest_id}")
        
        return max(0, len(self._snapshot_cache) - max_snapshots)
    
    def load_snapshot(self, snapshot_id: str, emulator) -> bool:
        """
        Restore emulator from a specific snapshot
        
        Args:
            snapshot_id: ID of snapshot to load
            emulator: EmulatorInterface instance
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                if snapshot_id not in self._snapshot_cache:
                    logger.error(f"Snapshot not found: {snapshot_id}")
                    return False
                
                metadata = self._snapshot_cache[snapshot_id]
                state_path = self.snapshots_dir / f"{snapshot_id}.state"
                
                if not state_path.exists():
                    logger.error(f"Snapshot file not found: {state_path}")
                    return False
                
                with open(state_path, 'rb') as f:
                    state_data = f.read()
                
                success = emulator.load_state_bytes(state_data)
                
                if success:
                    logger.info(f"Loaded snapshot: {snapshot_id}")
                    self._move_to_front(snapshot_id)
                
                return success
                
            except Exception as e:
                logger.error(f"Failed to load snapshot: {e}")
                return False
    
    def _move_to_front(self, snapshot_id: str) -> None:
        """Move snapshot to front of cache (mark as recently used)"""
        if snapshot_id in self._snapshot_cache:
            metadata = self._snapshot_cache.pop(snapshot_id)
            self._snapshot_cache[snapshot_id] = metadata
    
    def list_snapshots(self, include_invalid: bool = False) -> List[Dict[str, Any]]:
        """
        List all available snapshots with metadata
        
        Args:
            include_invalid: Include invalid/broken snapshots
            
        Returns:
            List of snapshot metadata dictionaries
        """
        with self._lock:
            snapshots = []
            for snapshot_id, metadata in self._snapshot_cache.items():
                if not include_invalid and not metadata.is_valid:
                    continue
                snapshots.append(metadata.to_dict())
            return snapshots
    
    def get_snapshot_info(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed info for a specific snapshot
        
        Args:
            snapshot_id: ID of snapshot
            
        Returns:
            Snapshot metadata dict or None if not found
        """
        with self._lock:
            if snapshot_id in self._snapshot_cache:
                return self._snapshot_cache[snapshot_id].to_dict()
            return None
    
    def get_recent_snapshots(self, count: int = 5) -> List[Dict[str, Any]]:
        """
        Get most recent snapshots
        
        Args:
            count: Number of recent snapshots to return
            
        Returns:
            List of recent snapshot metadata
        """
        with self._lock:
            recent = list(self._snapshot_cache.items())[-count:]
            return [asdict(m) for _, m in recent]
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """
        Delete a specific snapshot
        
        Args:
            snapshot_id: ID of snapshot to delete
            
        Returns:
            True if deleted, False otherwise
        """
        with self._lock:
            if snapshot_id not in self._snapshot_cache:
                return False
            
            metadata = self._snapshot_cache.pop(snapshot_id)
            
            state_file = self.snapshots_dir / f"{snapshot_id}.state"
            if state_file.exists():
                state_file.unlink()
            
            self._save_snapshot_index()
            logger.info(f"Deleted snapshot: {snapshot_id}")
            return True
    
    def save_emergency_snapshot(
        self,
        emulator,
        tick_count: int,
        reason: str = "emergency"
    ) -> str:
        """
        Create an emergency snapshot (preserved separately)
        
        Args:
            emulator: EmulatorInterface instance
            tick_count: Current tick count
            reason: Reason for emergency snapshot
            
        Returns:
            Snapshot ID
        """
        snapshot_id = f"emergency_{reason}_{int(time.time() * 1000)}"
        state_path = self.emergency_dir / f"{snapshot_id}.state"
        
        state_bytes = emulator.get_state_bytes()
        if not state_bytes:
            logger.error("Failed to get state bytes for emergency snapshot")
            return ""
        
        with open(state_path, 'wb') as f:
            f.write(state_bytes)
        
        metadata = SnapshotMetadata(
            snapshot_id=snapshot_id,
            created_at=datetime.now().isoformat(),
            tick_count=tick_count,
            reason="emergency",
            state_description=f"Emergency snapshot: {reason}",
            file_size=len(state_bytes),
            is_valid=True
        )
        
        metadata_path = self.emergency_dir / f"{snapshot_id}.json"
        with open(metadata_path, 'w') as f:
            json.dump(asdict(metadata), f, indent=2)
        
        logger.warning(f"Emergency snapshot created: {snapshot_id}")
        return snapshot_id
    
    def get_emergency_snapshots(self) -> List[Dict[str, Any]]:
        """
        Get all emergency snapshots
        
        Returns:
            List of emergency snapshot metadata
        """
        snapshots = []
        for metadata_file in self.emergency_dir.glob("*.json"):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = SnapshotMetadata.from_dict(json.load(f))
                    snapshots.append(metadata.to_dict())
            except Exception as e:
                logger.warning(f"Failed to read emergency snapshot metadata: {e}")
        
        return sorted(snapshots, key=lambda x: x.get('created_at', ''), reverse=True)
    
    def should_snapshot_interval(self, tick_count: int) -> bool:
        """Check if interval snapshot should be taken"""
        if tick_count - self._last_snapshot_tick >= self.config.snapshot_interval_ticks:
            return True
        return False
    
    def should_snapshot_event(self, event: str) -> bool:
        """Check if event-triggered snapshot should be taken"""
        return event.lower() in [e.lower() for e in self.config.save_on_events]
    
    def validate_snapshot(self, snapshot_id: str) -> bool:
        """
        Validate that a snapshot can be loaded
        
        Args:
            snapshot_id: ID of snapshot to validate
            
        Returns:
            True if valid, False otherwise
        """
        with self._lock:
            if snapshot_id not in self._snapshot_cache:
                return False
            
            metadata = self._snapshot_cache[snapshot_id]
            state_path = self.snapshots_dir / f"{snapshot_id}.state"
            
            if not state_path.exists():
                metadata.is_valid = False
                self._save_snapshot_index()
                return False
            
            file_size = state_path.stat().st_size
            if file_size != metadata.file_size:
                logger.warning(f"Snapshot size mismatch: expected {metadata.file_size}, got {file_size}")
                metadata.is_valid = False
                self._save_snapshot_index()
                return False
            
            return True
    
    def cleanup_all(self) -> Dict[str, int]:
        """
        Clean up all snapshots and emergency snapshots
        
        Returns:
            Dict with counts of deleted items
        """
        with self._lock:
            result = {"snapshots_deleted": 0, "emergency_deleted": 0}
            
            for snapshot_id in list(self._snapshot_cache.keys()):
                if self.delete_snapshot(snapshot_id):
                    result["snapshots_deleted"] += 1
            
            for emergency_file in self.emergency_dir.glob("*.state"):
                emergency_file.unlink()
                result["emergency_deleted"] += 1
            
            for metadata_file in self.emergency_dir.glob("*.json"):
                metadata_file.unlink()
            
            return result
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get save manager statistics
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            valid_count = sum(1 for m in self._snapshot_cache.values() if m.is_valid)
            total_size = sum(m.file_size for m in self._snapshot_cache.values())
            
            return {
                "total_snapshots": len(self._snapshot_cache),
                "valid_snapshots": valid_count,
                "invalid_snapshots": len(self._snapshot_cache) - valid_count,
                "total_size_bytes": total_size,
                "total_size_mb": total_size / (1024 * 1024),
                "max_snapshots": self.config.max_snapshots,
                "snapshot_interval_ticks": self.config.snapshot_interval_ticks,
                "last_snapshot_tick": self._last_snapshot_tick,
                "current_tick": self._tick_count,
                "save_directory": str(self.save_dir),
                "snapshots_directory": str(self.snapshots_dir),
                "emergency_directory": str(self.emergency_dir)
            }