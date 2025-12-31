"""
Tests for Save State Manager Module (Item 1.5)

Covers:
- SaveManager basic operations (10 tests)
- Snapshot creation with metadata (5 tests)
- Snapshot loading and validation (5 tests)
- Snapshot rotation and cleanup (5 tests)
- Emergency snapshots (3 tests)
- Event-triggered snapshots (3 tests)
- Configuration and integration (4 tests)

Total: 35 tests for comprehensive coverage
"""

import pytest
import time
import os
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from dataclasses import asdict

from src.core.save_manager import (
    SaveManager, SaveManagerConfig, SnapshotMetadata, SnapshotReason
)


class TestSaveManagerConfig:
    """Tests for SaveManagerConfig class"""

    def test_default_config(self):
        """Test default configuration values"""
        config = SaveManagerConfig()
        assert config.save_dir == "./game_saves"
        assert config.max_snapshots == 10
        assert config.snapshot_interval_ticks == 1000
        assert config.save_on_events == ["battle", "level_up", "badge"]
        assert config.compress_old is False
        assert config.validate_on_save is False
        assert config.emergency_snapshot_count == 3

    def test_custom_config(self):
        """Test custom configuration values"""
        config = SaveManagerConfig(
            save_dir="/custom/path",
            max_snapshots=20,
            snapshot_interval_ticks=500,
            save_on_events=["battle", "catch"],
            compress_old=True,
            validate_on_save=True,
            emergency_snapshot_count=5
        )
        assert config.save_dir == "/custom/path"
        assert config.max_snapshots == 20
        assert config.snapshot_interval_ticks == 500
        assert config.save_on_events == ["battle", "catch"]
        assert config.compress_old is True
        assert config.validate_on_save is True
        assert config.emergency_snapshot_count == 5


class TestSnapshotMetadata:
    """Tests for SnapshotMetadata class"""

    def test_create_metadata(self):
        """Test creating snapshot metadata"""
        metadata = SnapshotMetadata(
            snapshot_id="test_snapshot_123",
            created_at="2025-12-31T12:00:00",
            tick_count=1000,
            reason="interval",
            state_description="Test snapshot at tick 1000",
            location="Pallet Town",
            badges=2,
            team_hp_percent=85.5,
            file_size=1024,
            is_valid=True,
            game_state={"team": [{"name": "Pikachu", "hp_percent": 85.5}]}
        )
        
        assert metadata.snapshot_id == "test_snapshot_123"
        assert metadata.tick_count == 1000
        assert metadata.reason == "interval"
        assert metadata.location == "Pallet Town"
        assert metadata.badges == 2
        assert metadata.team_hp_percent == 85.5
        assert metadata.is_valid is True

    def test_metadata_to_dict(self):
        """Test converting metadata to dictionary"""
        metadata = SnapshotMetadata(
            snapshot_id="test_456",
            created_at="2025-12-31T12:00:00",
            tick_count=500,
            reason="manual",
            state_description="Manual snapshot"
        )
        
        data = metadata.to_dict()
        assert data["snapshot_id"] == "test_456"
        assert data["tick_count"] == 500
        assert data["reason"] == "manual"

    def test_metadata_from_dict(self):
        """Test creating metadata from dictionary"""
        data = {
            "snapshot_id": "from_dict_789",
            "created_at": "2025-12-31T12:00:00",
            "tick_count": 750,
            "reason": "battle_start",
            "state_description": "Battle snapshot",
            "location": None,
            "badges": 0,
            "team_hp_percent": None,
            "file_size": 2048,
            "is_valid": True,
            "game_state": None
        }
        
        metadata = SnapshotMetadata.from_dict(data)
        assert metadata.snapshot_id == "from_dict_789"
        assert metadata.tick_count == 750
        assert metadata.reason == "battle_start"


class TestSaveManagerBasic:
    """Tests for SaveManager basic operations"""

    def test_init_creates_directories(self):
        """Test that initialization creates necessary directories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            assert manager.snapshots_dir.exists()
            assert manager.emergency_dir.exists()
            assert manager.metadata_file.parent.exists()

    def test_init_loads_existing_index(self):
        """Test loading existing snapshot index on init"""
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshots_dir = Path(tmpdir) / "snapshots"
            snapshots_dir.mkdir()
            
            metadata_file = snapshots_dir / "snapshots.json"
            existing_data = [
                {
                    "snapshot_id": "existing_001",
                    "created_at": "2025-12-31T12:00:00",
                    "tick_count": 100,
                    "reason": "manual",
                    "state_description": "Existing snapshot",
                    "location": None,
                    "badges": 0,
                    "team_hp_percent": None,
                    "file_size": 100,
                    "is_valid": True,
                    "game_state": None
                }
            ]
            with open(metadata_file, 'w') as f:
                json.dump(existing_data, f)
            
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            assert "existing_001" in manager._snapshot_cache
            assert manager._snapshot_cache["existing_001"].tick_count == 100

    def test_set_tick_count(self):
        """Test updating tick count"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            manager.set_tick_count(5000)
            assert manager._tick_count == 5000

    def test_list_snapshots_empty(self):
        """Test listing snapshots when none exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            snapshots = manager.list_snapshots()
            assert len(snapshots) == 0

    def test_list_snapshots_with_data(self):
        """Test listing snapshots with existing data"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            manager._snapshot_cache["snap_001"] = SnapshotMetadata(
                snapshot_id="snap_001",
                created_at="2025-12-31T12:00:00",
                tick_count=100,
                reason="manual",
                state_description="Test"
            )
            
            snapshots = manager.list_snapshots()
            assert len(snapshots) == 1
            assert snapshots[0]["snapshot_id"] == "snap_001"


class TestSaveManagerSnapshotCreation:
    """Tests for snapshot creation functionality"""

    def test_save_snapshot_success(self):
        """Test successful snapshot creation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir, max_snapshots=5)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"test_state_data_12345"
            
            success, snapshot_id = manager.save_snapshot(
                emulator=mock_emulator,
                tick_count=1000,
                reason=SnapshotReason.INTERVAL,
                state_description="Test snapshot"
            )
            
            assert success is True
            assert snapshot_id.startswith("interval_")
            assert len(manager._snapshot_cache) == 1
            assert (manager.snapshots_dir / f"{snapshot_id}.state").exists()

    def test_save_snapshot_empty_state(self):
        """Test snapshot creation with empty state"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b""
            
            success, snapshot_id = manager.save_snapshot(
                emulator=mock_emulator,
                tick_count=1000,
                reason=SnapshotReason.MANUAL
            )
            
            assert success is False
            assert snapshot_id == ""
            assert len(manager._snapshot_cache) == 0

    def test_save_snapshot_with_game_state(self):
        """Test snapshot creation with game state info"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"state_data"
            
            game_state = {
                "location": "Viridian City",
                "badges": 3,
                "team": [{"name": "Pikachu", "hp_percent": 75.0}]
            }
            
            success, snapshot_id = manager.save_snapshot(
                emulator=mock_emulator,
                tick_count=5000,
                reason=SnapshotReason.LOCATION_CHANGE,
                game_state=game_state
            )
            
            assert success is True
            metadata = manager._snapshot_cache[snapshot_id]
            assert metadata.location == "Viridian City"
            assert metadata.badges == 3
            assert metadata.team_hp_percent == 75.0

    def test_snapshot_rotation(self):
        """Test automatic rotation when exceeding max snapshots"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir, max_snapshots=3)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"state_data"
            
            for i in range(5):
                manager.save_snapshot(
                    emulator=mock_emulator,
                    tick_count=i * 1000,
                    reason=SnapshotReason.INTERVAL
                )
            
            assert len(manager._snapshot_cache) == 3
            assert "interval_0" not in manager._snapshot_cache

    def test_snapshot_id_format(self):
        """Test that snapshot IDs have correct format"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"data"
            
            success, snapshot_id = manager.save_snapshot(
                emulator=mock_emulator,
                tick_count=1000,
                reason=SnapshotReason.BATTLE_START
            )
            
            assert success is True
            assert snapshot_id.startswith("battle_start_")


class TestSaveManagerLoading:
    """Tests for snapshot loading functionality"""

    def test_load_snapshot_success(self):
        """Test successful snapshot loading"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"test_state"
            
            success, snapshot_id = manager.save_snapshot(
                emulator=mock_emulator,
                tick_count=1000,
                reason=SnapshotReason.MANUAL
            )
            
            mock_emulator.load_state_bytes.reset_mock()
            mock_emulator.load_state_bytes.return_value = True
            
            load_success = manager.load_snapshot(snapshot_id, mock_emulator)
            
            assert load_success is True
            mock_emulator.load_state_bytes.assert_called_once()

    def test_load_snapshot_not_found(self):
        """Test loading non-existent snapshot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            
            success = manager.load_snapshot("nonexistent_123", mock_emulator)
            
            assert success is False

    def test_validate_snapshot_valid(self):
        """Test validation of valid snapshot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"test_state_data"
            
            success, snapshot_id = manager.save_snapshot(
                emulator=mock_emulator,
                tick_count=1000,
                reason=SnapshotReason.MANUAL
            )
            
            is_valid = manager.validate_snapshot(snapshot_id)
            assert is_valid is True
            assert manager._snapshot_cache[snapshot_id].is_valid is True

    def test_validate_snapshot_missing_file(self):
        """Test validation of snapshot with missing file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            manager._snapshot_cache["missing_001"] = SnapshotMetadata(
                snapshot_id="missing_001",
                created_at="2025-12-31T12:00:00",
                tick_count=100,
                reason="manual",
                state_description="Missing file",
                file_size=100
            )
            
            is_valid = manager.validate_snapshot("missing_001")
            assert is_valid is False
            assert manager._snapshot_cache["missing_001"].is_valid is False


class TestSaveManagerManagement:
    """Tests for snapshot management functionality"""

    def test_get_snapshot_info(self):
        """Test getting snapshot info"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            manager._snapshot_cache["info_001"] = SnapshotMetadata(
                snapshot_id="info_001",
                created_at="2025-12-31T12:00:00",
                tick_count=100,
                reason="manual",
                state_description="Test info",
                location="Pallet Town"
            )
            
            info = manager.get_snapshot_info("info_001")
            assert info is not None
            assert info["location"] == "Pallet Town"

    def test_get_recent_snapshots(self):
        """Test getting recent snapshots"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            for i in range(5):
                manager._snapshot_cache[f"recent_{i}"] = SnapshotMetadata(
                    snapshot_id=f"recent_{i}",
                    created_at="2025-12-31T12:00:00",
                    tick_count=i * 100,
                    reason="manual",
                    state_description=f"Snapshot {i}"
                )
            
            recent = manager.get_recent_snapshots(count=3)
            assert len(recent) == 3

    def test_delete_snapshot(self):
        """Test deleting a snapshot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"data"
            
            success, snapshot_id = manager.save_snapshot(
                emulator=mock_emulator,
                tick_count=1000,
                reason=SnapshotReason.MANUAL
            )
            
            state_file = manager.snapshots_dir / f"{snapshot_id}.state"
            assert state_file.exists()
            
            delete_success = manager.delete_snapshot(snapshot_id)
            
            assert delete_success is True
            assert snapshot_id not in manager._snapshot_cache
            assert not state_file.exists()

    def test_delete_snapshot_not_found(self):
        """Test deleting non-existent snapshot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            success = manager.delete_snapshot("nonexistent")
            assert success is False


class TestSaveManagerEmergency:
    """Tests for emergency snapshot functionality"""

    def test_save_emergency_snapshot(self):
        """Test creating emergency snapshot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"emergency_state_data"
            
            snapshot_id = manager.save_emergency_snapshot(
                emulator=mock_emulator,
                tick_count=5000,
                reason="crash_recovery"
            )
            
            assert snapshot_id.startswith("emergency_crash_recovery_")
            assert (manager.emergency_dir / f"{snapshot_id}.state").exists()
            assert (manager.emergency_dir / f"{snapshot_id}.json").exists()

    def test_get_emergency_snapshots(self):
        """Test getting emergency snapshots"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"data"
            
            manager.save_emergency_snapshot(mock_emulator, 1000, "test1")
            manager.save_emergency_snapshot(mock_emulator, 2000, "test2")
            
            emergency = manager.get_emergency_snapshots()
            assert len(emergency) == 2

    def test_emergency_snapshot_preserved_on_rotation(self):
        """Test that emergency snapshots are not affected by rotation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir, max_snapshots=2)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"data"
            
            for i in range(5):
                manager.save_snapshot(
                    emulator=mock_emulator,
                    tick_count=i * 1000,
                    reason=SnapshotReason.INTERVAL
                )
            
            manager.save_emergency_snapshot(mock_emulator, 10000, "critical")
            
            emergency = manager.get_emergency_snapshots()
            assert len(emergency) == 1


class TestSaveManagerEvents:
    """Tests for event-triggered snapshot functionality"""

    def test_should_snapshot_interval_true(self):
        """Test interval snapshot trigger"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(
                save_dir=tmpdir,
                snapshot_interval_ticks=1000
            )
            manager = SaveManager(config)
            manager._last_snapshot_tick = 0
            
            assert manager.should_snapshot_interval(1001) is True

    def test_should_snapshot_interval_false(self):
        """Test interval not yet reached"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(
                save_dir=tmpdir,
                snapshot_interval_ticks=1000
            )
            manager = SaveManager(config)
            manager._last_snapshot_tick = 0
            
            assert manager.should_snapshot_interval(500) is False

    def test_should_snapshot_event(self):
        """Test event-triggered snapshot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(
                save_dir=tmpdir,
                save_on_events=["battle", "level_up"]
            )
            manager = SaveManager(config)
            
            assert manager.should_snapshot_event("battle") is True
            assert manager.should_snapshot_event("level_up") is True
            assert manager.should_snapshot_event("catch") is False


class TestSaveManagerStatistics:
    """Tests for save manager statistics"""

    def test_get_statistics(self):
        """Test getting statistics"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(
                save_dir=tmpdir,
                max_snapshots=10,
                snapshot_interval_ticks=1000
            )
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"state_data"
            
            manager.save_snapshot(
                emulator=mock_emulator,
                tick_count=1000,
                reason=SnapshotReason.MANUAL
            )
            
            stats = manager.get_statistics()
            
            assert stats["total_snapshots"] == 1
            assert stats["valid_snapshots"] == 1
            assert stats["max_snapshots"] == 10
            assert stats["snapshot_interval_ticks"] == 1000
            assert stats["total_size_bytes"] > 0

    def test_cleanup_all(self):
        """Test cleanup of all snapshots"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"data"
            
            manager.save_snapshot(mock_emulator, 1000, SnapshotReason.MANUAL)
            manager.save_emergency_snapshot(mock_emulator, 2000, "test")
            
            result = manager.cleanup_all()
            
            assert result["snapshots_deleted"] == 1
            assert result["emergency_deleted"] >= 1
            assert len(manager._snapshot_cache) == 0


class TestSaveManagerIntegration:
    """Integration tests for SaveManager"""

    def test_full_snapshot_lifecycle(self):
        """Test complete snapshot lifecycle"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir, max_snapshots=5)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"full_lifecycle_test"
            
            saved_ids = []
            for i in range(3):
                success, snapshot_id = manager.save_snapshot(
                    emulator=mock_emulator,
                    tick_count=i * 1000,
                    reason=SnapshotReason.INTERVAL,
                    state_description=f"Lifecycle snapshot {i}"
                )
                assert success is True
                saved_ids.append(snapshot_id)
            
            snapshots = manager.list_snapshots()
            assert len(snapshots) == 3
            
            mock_emulator.load_state_bytes.reset_mock()
            mock_emulator.load_state_bytes.return_value = True
            
            load_success = manager.load_snapshot(saved_ids[-1], mock_emulator)
            assert load_success is True
            
            stats = manager.get_statistics()
            assert stats["total_snapshots"] == 3

    def test_thread_safety(self):
        """Test thread-safe operations"""
        import threading
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir, max_snapshots=100)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"thread_test"
            
            def save_snapshots():
                for i in range(10):
                    manager.save_snapshot(
                        emulator=mock_emulator,
                        tick_count=i,
                        reason=SnapshotReason.MANUAL
                    )
            
            threads = [threading.Thread(target=save_snapshots) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            assert len(manager._snapshot_cache) <= config.max_snapshots

    def test_snapshot_with_all_reasons(self):
        """Test creating snapshots with all reason types"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(save_dir=tmpdir)
            manager = SaveManager(config)
            
            mock_emulator = Mock()
            mock_emulator.get_state_bytes.return_value = b"data"
            
            for reason in SnapshotReason:
                success, snapshot_id = manager.save_snapshot(
                    emulator=mock_emulator,
                    tick_count=0,
                    reason=reason
                )
                assert success is True
                assert reason.value in snapshot_id

    def test_config_validation(self):
        """Test configuration validation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SaveManagerConfig(
                save_dir=tmpdir,
                snapshot_interval_ticks=50,
                max_snapshots=0
            )
            manager = SaveManager(config)
            
            assert manager.config.snapshot_interval_ticks == 50
            assert manager.config.max_snapshots == 0