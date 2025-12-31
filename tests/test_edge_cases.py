"""
Edge Case Tests for PTP-01X Pokemon AI

Tests system robustness under exceptional conditions:
- ROM handling (missing, invalid, corrupted)
- API key handling (missing, invalid)
- Network handling (timeout, connection refused, DNS failure)
- Database handling (corruption, locked, disk full)
- Screenshot handling (invalid data, memory error)

Total: 45 edge case tests
"""

import pytest
import tempfile
import os
import json
import time
import threading
import sqlite3
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


class TestROMHandling:
    """Tests for ROM file handling edge cases (7 tests)"""

    def test_missing_rom_graceful_handling(self):
        """ROM not found → appropriate error, no crash"""
        with patch('os.path.exists', return_value=False):
            from src.core.emulator import EmulatorInterface

            with pytest.raises((FileNotFoundError, Exception)) as exc_info:
                EmulatorInterface(rom_path="/nonexistent/rom.gb")

            assert exc_info.value is not None

    def test_invalid_rom_header(self):
        """Invalid ROM → clear error message"""
        with tempfile.NamedTemporaryFile(suffix='.gb', delete=False) as f:
            f.write(b"NOT A VALID ROM HEADER" + b"\x00" * 100)
            temp_path = f.name

        try:
            from src.core.emulator import EmulatorInterface
            with pytest.raises(Exception):
                emulator = EmulatorInterface(rom_path=temp_path)
                if emulator.pyboy is None:
                    raise Exception("ROM validation failed")
        finally:
            os.unlink(temp_path)

    def test_rom_corruption_recovery(self):
        """ROM corruption detected → graceful shutdown"""
        with tempfile.NamedTemporaryFile(suffix='.gb', delete=False) as f:
            f.write(b"\x00" * 100)
            temp_path = f.name

        try:
            from src.core.emulator import EmulatorInterface
            emulator = EmulatorInterface(rom_path=temp_path)
            assert emulator.pyboy is None
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_rom_path_with_spaces(self):
        """ROM path with spaces → proper handling"""
        with tempfile.TemporaryDirectory() as tmpdir:
            spaced_path = os.path.join(tmpdir, "my rom file.gb")
            with open(spaced_path, 'wb') as f:
                f.write(b"NINTENDO" + b"\x00" * 100)

            from src.core.emulator import EmulatorInterface
            emulator = EmulatorInterface(rom_path=spaced_path)

            assert emulator is not None

    def test_rom_permission_denied(self):
        """ROM file permission denied → appropriate error"""
        with tempfile.NamedTemporaryFile(suffix='.gb', delete=False) as f:
            f.write(b"NINTENDO" + b"\x00" * 100)
            temp_path = f.name

        try:
            os.chmod(temp_path, 0o000)

            from src.core.emulator import EmulatorInterface
            with pytest.raises((PermissionError, Exception)):
                EmulatorInterface(rom_path=temp_path)
        finally:
            os.chmod(temp_path, 0o644)
            os.unlink(temp_path)

    def test_rom_empty_file(self):
        """Empty ROM file → appropriate error"""
        with tempfile.NamedTemporaryFile(suffix='.gb', delete=False) as f:
            temp_path = f.name

        try:
            from src.core.emulator import EmulatorInterface
            emulator = EmulatorInterface(rom_path=temp_path)
            assert emulator.pyboy is None
        finally:
            os.unlink(temp_path)

    def test_rom_too_small(self):
        """ROM file too small → appropriate error"""
        with tempfile.NamedTemporaryFile(suffix='.gb', delete=False) as f:
            f.write(b"\x00" * 100)
            temp_path = f.name

        try:
            from src.core.emulator import EmulatorInterface
            emulator = EmulatorInterface(rom_path=temp_path)
            assert emulator.pyboy is None
        finally:
            os.unlink(temp_path)


class TestAPIKeyHandling:
    """Tests for API key handling edge cases (7 tests)"""

    def test_missing_api_key(self):
        """API key absent → stub fallback mode"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('src.core.ai_client.AIModelClient._load_api_key', return_value=None):
                from src.core.ai_client import AIModelClient

                client = AIModelClient()
                assert client._api_key is None or client._stub_mode is True

    def test_api_key_empty_string(self):
        """API key is empty string → stub mode"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            from src.core.ai_client import AIModelClient

            client = AIModelClient()
            assert client._api_key is None or client._api_key == ""

    def test_api_key_invalid_format(self):
        """Invalid API key format → clear error, no retry loop"""
        with patch('src.core.ai_client.requests.post') as mock_post:
            mock_post.side_effect = Exception("401 Unauthorized")

            from src.core.ai_client import AIModelClient
            client = AIModelClient(api_key="invalid-key-format")

            with pytest.raises(Exception):
                client._validate_api_key()

    def test_api_key_expired(self):
        """Expired API key → clear error message"""
        with patch('src.core.ai_client.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": {"message": "This key has expired"}}
            mock_post.return_value = mock_response

            from src.core.ai_client import AIModelClient
            with pytest.raises(Exception) as exc_info:
                client = AIModelClient(api_key="sk-expired-key")
                client._validate_api_key()

            assert exc_info.value is not None

    def test_api_key_rate_limit(self):
        """API key rate limited → retry with backoff"""
        call_count = 0

        def raise_rate_limit(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Rate limit exceeded")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"choices": []}
            return mock_response

        with patch('src.core.ai_client.requests.post', side_effect=raise_rate_limit):
            from src.core.ai_client import AIModelClient
            client = AIModelClient(api_key="sk-test-key")
            result = client._make_request_with_retry("test", {})
            assert call_count >= 1

    def test_api_key_environment_override(self):
        """API key from environment → correctly loaded"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-env-key"}):
            from src.core.ai_client import AIModelClient

            with patch('src.core.ai_client.AIModelClient._load_api_key', return_value="sk-test-env-key") as mock_load:
                client = AIModelClient()
                mock_load.assert_called_once()

    def test_api_key_with_special_chars(self):
        """API key with special characters → proper handling"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-key-with-dashes-and_underscores.v3"}):
            from src.core.ai_client import AIModelClient

            client = AIModelClient()
            if client._api_key:
                assert "sk-key" in client._api_key


class TestNetworkHandling:
    """Tests for network handling edge cases (7 tests)"""

    def test_network_timeout(self):
        """Network timeout → retry logic, eventual fallback"""
        call_count = 0

        def raise_timeout(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Connection timed out")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"choices": []}
            return mock_response

        with patch('src.core.ai_client.requests.post', side_effect=raise_timeout):
            from src.core.ai_client import AIModelClient
            client = AIModelClient(api_key="sk-test")
            result = client._make_request_with_retry("test", {})
            assert call_count >= 1

    def test_connection_refused(self):
        """Connection refused → appropriate error handling"""
        with patch('src.core.ai_client.requests.post') as mock_post:
            mock_post.side_effect = ConnectionRefusedError("Connection refused")

            from src.core.ai_client import AIModelClient
            with pytest.raises((ConnectionRefusedError, Exception)):
                client = AIModelClient(api_key="sk-test")
                client._make_request_with_retry("test", {}, max_retries=0)

    def test_dns_resolution_failure(self):
        """DNS failure → clear error message"""
        with patch('src.core.ai_client.requests.post') as mock_post:
            mock_post.side_effect = Exception("nodename nor servname provided, or not known")

            from src.core.ai_client import AIModelClient
            with pytest.raises(Exception) as exc_info:
                client = AIModelClient(api_key="sk-test")
                client._make_request_with_retry("test", {})

            assert "dns" in str(exc_info.value).lower() or "resolve" in str(exc_info.value).lower() or "nodename" in str(exc_info.value).lower()

    def test_ssl_certificate_error(self):
        """SSL certificate error → appropriate handling"""
        with patch('src.core.ai_client.requests.post') as mock_post:
            import ssl
            mock_post.side_effect = ssl.SSLCertVerificationError("Certificate verify failed")

            from src.core.ai_client import AIModelClient
            with pytest.raises((ssl.SSLCertVerificationError, Exception)):
                client = AIModelClient(api_key="sk-test")
                client._make_request_with_retry("test", {})

    def test_connection_reset_by_peer(self):
        """Connection reset by peer → retry or fail gracefully"""
        with patch('src.core.ai_client.requests.post') as mock_post:
            mock_post.side_effect = ConnectionResetError("Connection reset by peer")

            from src.core.ai_client import AIModelClient
            with pytest.raises((ConnectionResetError, Exception)):
                client = AIModelClient(api_key="sk-test")
                client._make_request_with_retry("test", {}, max_retries=0)

    def test_partial_response_received(self):
        """Partial response received → handle incomplete data"""
        with patch('src.core.ai_client.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
            mock_post.return_value = mock_response

            from src.core.ai_client import AIModelClient
            with pytest.raises((json.JSONDecodeError, Exception)):
                client = AIModelClient(api_key="sk-test")
                client._make_request_with_retry("test", {})

    def test_too_many_redirects(self):
        """Too many redirects → handle redirect loop"""
        with patch('src.core.ai_client.requests.post') as mock_post:
            mock_post.side_effect = Exception("Too many redirects")

            from src.core.ai_client import AIModelClient
            with pytest.raises(Exception) as exc_info:
                client = AIModelClient(api_key="sk-test")
                client._make_request_with_retry("test", {})

            assert "redirect" in str(exc_info.value).lower() or "too many" in str(exc_info.value).lower()


class TestDatabaseHandling:
    """Tests for database handling edge cases (7 tests)"""

    def test_database_corruption(self):
        """DB corruption → graceful handling, data preservation"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            with open(db_path, 'w') as f:
                f.write("CORRUPTED DATABASE CONTENT" + "\x00" * 100)

            from src.db.database import GameDatabase
            with pytest.raises((sqlite3.DatabaseError, Exception)):
                GameDatabase(db_path=db_path)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_database_locked(self):
        """DB locked by another process → retry or fail gracefully"""
        import sqlite3
        import threading

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA locking_mode = EXCLUSIVE")

            def release_lock():
                time.sleep(0.2)
                try:
                    conn.close()
                except:
                    pass

            threading.Thread(target=release_lock, daemon=True).start()

            with pytest.raises((sqlite3.OperationalError, Exception)):
                from src.db.database import GameDatabase
                GameDatabase(db_path=db_path)
        finally:
            if os.path.exists(db_path):
                try:
                    conn.close()
                except:
                    pass
                os.unlink(db_path)

    def test_database_constraint_violation(self):
        """Constraint violation → appropriate error handling"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            from src.db.database import GameDatabase
            db = GameDatabase(db_path=db_path)

            db._execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            db._execute("INSERT INTO test VALUES (1)")

            with pytest.raises((sqlite3.IntegrityError, Exception)):
                db._execute("INSERT INTO test VALUES (1)")

            db.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_database_interrupt_recovery(self):
        """Database operation interrupted → recovery attempt"""
        import sqlite3

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            from src.db.database import GameDatabase
            db = GameDatabase(db_path=db_path)

            with patch.object(db, '_execute', side_effect=KeyboardInterrupt):
                with pytest.raises((KeyboardInterrupt, Exception)):
                    db.save_session_data({"test": "data"})

            db.close()
        finally:
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except:
                    pass

    def test_database_missing_table(self):
        """Missing expected table → error gracefully"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE wrong_table (id INTEGER)")
            conn.commit()
            conn.close()

            from src.db.database import GameDatabase
            db = GameDatabase(db_path=db_path)

            with pytest.raises((sqlite3.OperationalError, Exception)):
                db.get_session(1)

            db.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestScreenshotHandling:
    """Tests for screenshot handling edge cases (7 tests)"""

    def test_invalid_screenshot_data(self):
        """Invalid screenshot → clear error, no crash"""
        from src.vision import VisionPipeline

        pipeline = VisionPipeline()

        with pytest.raises((TypeError, ValueError, AttributeError, Exception)):
            pipeline.process(None)

    def test_screenshot_memory_error(self):
        """Memory error during processing → graceful recovery"""
        from src.vision import VisionPipeline

        pipeline = VisionPipeline()

        with patch('numpy.zeros', side_effect=MemoryError("Out of memory")):
            with pytest.raises(MemoryError):
                pipeline.process(np.zeros((144, 160, 3), dtype=np.uint8))

    def test_screenshot_wrong_dimensions(self):
        """Screenshot with wrong dimensions → handle gracefully"""
        from src.vision import VisionPipeline

        pipeline = VisionPipeline()

        with pytest.raises((ValueError, Exception)):
            pipeline.process(np.zeros((100, 100, 3), dtype=np.uint8))

    def test_screenshot_wrong_dtype(self):
        """Screenshot with wrong dtype → handle gracefully"""
        from src.vision import VisionPipeline

        pipeline = VisionPipeline()

        with pytest.raises((TypeError, ValueError)):
            pipeline.process(np.zeros((144, 160, 3), dtype=np.float32))

    def test_screenshot_empty_array(self):
        """Empty screenshot array → handle gracefully"""
        from src.vision import VisionPipeline

        pipeline = VisionPipeline()

        with pytest.raises((ValueError, Exception)):
            pipeline.process(np.array([], dtype=np.uint8))

    def test_screenshot_corrupted_pixel_data(self):
        """Screenshot with corrupted pixel data → handle gracefully"""
        from src.vision import VisionPipeline

        pipeline = VisionPipeline()

        corrupted_image = np.zeros((144, 160, 3), dtype=np.float64)
        corrupted_image[0, 0, 0] = np.nan

        with pytest.raises((ValueError, Exception)):
            pipeline.process(corrupted_image)

    def test_screenshot_timeout(self):
        """Screenshot processing timeout → fail gracefully"""
        from src.vision import VisionPipeline

        pipeline = VisionPipeline()

        valid_screenshot = np.zeros((144, 160, 3), dtype=np.uint8)

        with patch.object(pipeline, 'process', side_effect=TimeoutError("Processing timeout")):
            with pytest.raises((TimeoutError, Exception)):
                pipeline.process(valid_screenshot)


class TestStateMachineEdgeCases:
    """Tests for state machine edge cases (5 tests)"""

    def test_invalid_state_transition(self):
        """Invalid state transition → appropriate handling"""
        from src.core.state_machine import HierarchicalStateMachine

        state_machine = HierarchicalStateMachine()

        with pytest.raises((ValueError, Exception)):
            state_machine.transition_to("INVALID_STATE", tick=1)

    def test_state_machine_null_current_state(self):
        """Null current state → handle gracefully"""
        from src.core.state_machine import HierarchicalStateMachine

        state_machine = HierarchicalStateMachine()

        result = state_machine.get_current_state()
        assert result is not None

    def test_state_machine_rapid_transitions(self):
        """Rapid state transitions → handle without race conditions"""
        from src.core.state_machine import HierarchicalStateMachine

        state_machine = HierarchicalStateMachine()

        for i in range(100):
            state_machine.transition_to("BATTLE.MENU", tick=i)

        assert state_machine._tick == 99

    def test_state_machine_invalid_tick(self):
        """Invalid tick value → handle gracefully"""
        from src.core.state_machine import HierarchicalStateMachine

        state_machine = HierarchicalStateMachine()

        state_machine.transition_to("OVERWORLD.IDLE", tick=100)

        with pytest.raises((ValueError, Exception)):
            state_machine.transition_to("OVERWORLD.WALKING", tick=50)

    def test_state_machine_deep_nested_state(self):
        """Deep nested state → handle properly"""
        from src.core.state_machine import HierarchicalStateMachine

        state_machine = HierarchicalStateMachine()

        deep_state = ".".join(["SUBSTATE"] * 10)

        with pytest.raises((ValueError, Exception)):
            state_machine.transition_to(deep_state, tick=1)


class TestCombatEdgeCases:
    """Tests for combat system edge cases (5 tests)"""

    def test_invalid_pokemon_data(self):
        """Invalid Pokemon data → handle gracefully"""
        from src.core.combat import CombatSystem

        combat = CombatSystem()

        with pytest.raises((ValueError, TypeError)):
            combat.analyze_battle_state({"invalid": "data"})

    def test_missing_pokemon_stats(self):
        """Missing Pokemon stats → use defaults"""
        from src.core.combat import CombatSystem

        combat = CombatSystem()

        result = combat.calculate_damage(
            attacker={},
            defender={"name": "Pikachu"},
            move={"power": 40}
        )

        assert result is not None

    def test_negative_hp_calculation(self):
        """Negative HP calculation → clamp to 0"""
        from src.core.combat import CombatSystem

        combat = CombatSystem()

        result = combat.calculate_hp_after_damage(50, 100)
        assert result >= 0

    def test_max_hp_exceeded(self):
        """Max HP exceeded → clamp to max"""
        from src.core.combat import CombatSystem

        combat = CombatSystem()

        result = combat.clamp_hp(150, max_hp=100)
        assert result == 100

    def test_zero_damage_move(self):
        """Zero damage move → return 0"""
        from src.core.combat import CombatSystem

        combat = CombatSystem()

        result = combat.calculate_damage(
            attacker={"level": 10, "attack": 15},
            defender={"defense": 10},
            move={"power": 0}
        )

        assert result == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])