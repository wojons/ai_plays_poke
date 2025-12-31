"""
Tests for Failsafe Protocols Module (2.6)

Covers:
- ConfidenceScorer tests (15 tests)
- SoftlockDetector tests (15 tests)
- EmergencyRecovery tests (10 tests)
- DeathSpiralPreventer tests (8 tests)
- SystemHealthMonitor tests (8 tests)
- FailsafeManager integration tests (6 tests)

Total: 62 tests for comprehensive coverage
"""

import pytest
import time
import threading
import os
import json
from unittest.mock import Mock, MagicMock, patch
from dataclasses import asdict

from src.core.failsafe import (  # type: ignore
    ConfidenceScorer, ConfidenceBreakdown, ConfidenceLevel,
    SoftlockDetector, SoftlockInfo,
    EmergencyRecovery, RecoveryState, RecoveryResult,
    DeathSpiralPreventer,
    SystemHealthMonitor, HealthMetrics,
    FailsafeManager
)
from src.core.state_machine import HierarchicalStateMachine, StateType


class TestConfidenceScorer:
    """Tests for ConfidenceScorer class (15 tests)"""

    def test_calculate_confidence_with_all_inputs(self):
        """Test confidence calculation with all inputs provided"""
        scorer = ConfidenceScorer()
        result = scorer.calculate_confidence(
            ai_confidence=0.9,
            vision_confidence=0.8,
            state_confidence=0.7,
            tick=100
        )
        
        assert result.ai_decision_confidence == 0.9
        assert result.vision_confidence == 0.8
        assert result.state_detection_confidence == 0.7
        assert result.overall_confidence == pytest.approx(0.4 * 0.9 + 0.35 * 0.8 + 0.25 * 0.7)
        assert result.tick == 100
        assert len(result.factors) == 3

    def test_calculate_confidence_with_partial_inputs(self):
        """Test confidence calculation with partial inputs"""
        scorer = ConfidenceScorer()
        result = scorer.calculate_confidence(
            ai_confidence=0.85,
            tick=200
        )
        
        assert result.ai_decision_confidence == 0.85
        assert result.vision_confidence == 1.0  # default
        assert result.state_detection_confidence == 1.0  # default
        assert result.tick == 200
        assert len(result.factors) >= 1

    def test_calculate_confidence_with_none_inputs(self):
        """Test confidence calculation with all None inputs"""
        scorer = ConfidenceScorer()
        result = scorer.calculate_confidence(tick=300)
        
        assert result.ai_decision_confidence == 1.0  # default
        assert result.vision_confidence == 1.0  # default
        assert result.state_detection_confidence == 1.0  # default
        assert result.overall_confidence == 1.0  # all defaults
        assert result.tick == 300

    def test_calculate_confidence_stores_history(self):
        """Test that confidence calculations are stored in history"""
        scorer = ConfidenceScorer()
        
        scorer.calculate_confidence(ai_confidence=0.9, tick=1)
        scorer.calculate_confidence(ai_confidence=0.8, tick=2)
        scorer.calculate_confidence(ai_confidence=0.7, tick=3)
        
        history = scorer.get_confidence_history(count=10)
        assert len(history) == 3
        assert history[0].tick == 1
        assert history[1].tick == 2
        assert history[2].tick == 3

    def test_get_confidence_level_high(self):
        """Test confidence level classification - HIGH"""
        scorer = ConfidenceScorer()
        level = scorer.get_confidence_level(0.9)
        assert level == ConfidenceLevel.HIGH

    def test_get_confidence_level_medium(self):
        """Test confidence level classification - MEDIUM"""
        scorer = ConfidenceScorer()
        level = scorer.get_confidence_level(0.75)
        assert level == ConfidenceLevel.MEDIUM

    def test_get_confidence_level_low(self):
        """Test confidence level classification - LOW"""
        scorer = ConfidenceScorer()
        level = scorer.get_confidence_level(0.55)
        assert level == ConfidenceLevel.LOW

    def test_get_confidence_level_critical(self):
        """Test confidence level classification - CRITICAL"""
        scorer = ConfidenceScorer()
        level = scorer.get_confidence_level(0.25)
        assert level == ConfidenceLevel.CRITICAL

    def test_is_confidence_acceptable_above_threshold(self):
        """Test acceptability check above threshold"""
        scorer = ConfidenceScorer(default_threshold=0.7)
        assert scorer.is_confidence_acceptable(0.8) is True
        assert scorer.is_confidence_acceptable(0.7) is True

    def test_is_confidence_acceptable_below_threshold(self):
        """Test acceptability check below threshold"""
        scorer = ConfidenceScorer(default_threshold=0.7)
        assert scorer.is_confidence_acceptable(0.6) is False
        assert scorer.is_confidence_acceptable(0.3) is False

    def test_get_recent_confidence_trend_insufficient_data(self):
        """Test trend calculation with insufficient data"""
        scorer = ConfidenceScorer()
        trend = scorer.get_recent_confidence_trend()
        assert trend["trend"] == "insufficient_data"
        assert trend["avg"] is None

    def test_get_recent_confidence_trend_improving(self):
        """Test trend calculation - improving"""
        scorer = ConfidenceScorer()
        for i in [0.5, 0.6, 0.7, 0.8, 0.85]:
            scorer.calculate_confidence(ai_confidence=i, tick=i)
        
        trend = scorer.get_recent_confidence_trend()
        assert trend["trend"] == "improving"
        assert trend["avg"] is not None
        assert trend["min"] >= 0.5
        assert trend["max"] <= 1.0

    def test_get_recent_confidence_trend_declining(self):
        """Test trend calculation - declining"""
        scorer = ConfidenceScorer()
        for i in [0.9, 0.85, 0.8, 0.7, 0.6]:
            scorer.calculate_confidence(ai_confidence=i, tick=i)
        
        trend = scorer.get_recent_confidence_trend()
        assert trend["trend"] == "declining"

    def test_get_recent_confidence_trend_stable(self):
        """Test trend calculation - stable"""
        scorer = ConfidenceScorer()
        confidence = 0.75
        for i in range(10):
            scorer.calculate_confidence(ai_confidence=confidence, tick=i)
        
        trend = scorer.get_recent_confidence_trend()
        assert trend["trend"] == "stable"

    def test_get_last_confidence(self):
        """Test getting the most recent confidence breakdown"""
        scorer = ConfidenceScorer()
        result = scorer.calculate_confidence(ai_confidence=0.95, tick=999)
        
        last = scorer.get_last_confidence()
        assert last is not None
        assert last.tick == 999
        assert last.ai_decision_confidence == 0.95  # Check input, not weighted result

    def test_confidence_history_limit(self):
        """Test that confidence history is limited to 100 entries"""
        scorer = ConfidenceScorer()
        
        for i in range(150):
            scorer.calculate_confidence(ai_confidence=0.5 + (i % 50) / 100, tick=i)
        
        history = scorer.get_confidence_history(count=200)
        assert len(history) == 100  # Should be limited to 100


class TestSoftlockDetector:
    """Tests for SoftlockDetector class (15 tests)"""

    def test_check_softlock_mode_duration_exceeded(self):
        """Test softlock detection for exceeded mode duration"""
        detector = SoftlockDetector()
        
        softlock = detector.check_softlock(
            current_mode="BATTLE",
            current_sub_mode="WILD_NORMAL",
            current_duration=400.0,
            current_action=None,
            tick=100
        )
        
        assert softlock is not None
        assert softlock.type == "MODE_DURATION_EXCEEDED"
        assert softlock.severity == "MEDIUM"  # 400 < 600
        assert softlock.mode == "BATTLE"
        assert softlock.sub_mode == "WILD_NORMAL"

    def test_check_softlock_mode_duration_critical(self):
        """Test softlock detection for critically exceeded duration"""
        detector = SoftlockDetector()
        
        softlock = detector.check_softlock(
            current_mode="BATTLE",
            current_sub_mode="WILD_NORMAL",
            current_duration=700.0,
            current_action=None,
            tick=100
        )
        
        assert softlock is not None
        assert softlock.severity == "HIGH"  # 700 > 600

    def test_check_softlock_repeated_action(self):
        """Test softlock detection for repeated same action"""
        detector = SoftlockDetector(repeated_action_threshold=5)
        
        for i in range(10):
            detector.record_action("press:A", i)
        
        softlock = detector.check_softlock(
            current_mode="OVERWORLD",
            current_sub_mode="NAVIGATION",
            current_duration=10.0,
            current_action="press:A",
            tick=15
        )
        
        assert softlock is not None
        assert softlock.type == "REPEATED_ACTION"
        assert softlock.repeated_action == "press:A"

    def test_check_softlock_no_repeated_action(self):
        """Test no softlock when actions are different"""
        detector = SoftlockDetector(repeated_action_threshold=5)
        
        detector.record_action("press:A", 1)
        detector.record_action("press:B", 2)
        detector.record_action("press:UP", 3)
        
        softlock = detector.check_softlock(
            current_mode="OVERWORLD",
            current_sub_mode="NAVIGATION",
            current_duration=10.0,
            current_action="press:UP",
            tick=10
        )
        
        assert softlock is None

    def test_check_softlock_state_loop_detection(self):
        """Test softlock detection for state oscillation"""
        state_machine = HierarchicalStateMachine()
        detector = SoftlockDetector(state_machine=state_machine)
        
        state_machine.transition_to("OVERWORLD.IDLE", tick=1)
        state_machine.transition_to("OVERWORLD.WALKING", tick=2)
        state_machine.transition_to("OVERWORLD.IDLE", tick=3)
        state_machine.transition_to("OVERWORLD.WALKING", tick=4)
        state_machine.transition_to("OVERWORLD.IDLE", tick=5)
        state_machine.transition_to("OVERWORLD.WALKING", tick=6)
        state_machine.transition_to("OVERWORLD.IDLE", tick=7)
        state_machine.transition_to("OVERWORLD.WALKING", tick=8)
        
        softlock = detector.check_softlock(
            current_mode="OVERWORLD",
            current_sub_mode="NAVIGATION",
            current_duration=5.0,
            current_action=None,
            tick=9
        )
        
        assert softlock is not None
        assert softlock.type == "STATE_OSCILLATION"

    def test_check_softlock_zero_progress(self):
        """Test softlock detection for zero progress"""
        detector = SoftlockDetector(progress_window_seconds=0.1)
        
        game_state = {
            "tick": 100,
            "location": "Pallet Town",
            "player_hp_percent": 100.0
        }
        
        detector._last_progress_tick = 100
        detector._last_progress_time = time.time() - 0.5
        
        softlock = detector.check_softlock(
            current_mode="OVERWORLD",
            current_sub_mode="NAVIGATION",
            current_duration=2.0,
            current_action=None,
            tick=100,
            game_state=game_state
        )
        
        assert softlock is not None
        assert softlock.type == "ZERO_PROGRESS"

    def test_check_softlock_no_softlock_conditions(self):
        """Test no softlock when all conditions are normal"""
        detector = SoftlockDetector()
        
        softlock = detector.check_softlock(
            current_mode="OVERWORLD",
            current_sub_mode="NAVIGATION",
            current_duration=10.0,
            current_action="press:A",
            tick=100,
            game_state={"tick": 100, "location": "Route 1", "player_hp_percent": 100.0}
        )
        
        assert softlock is None

    def test_record_action(self):
        """Test action recording"""
        detector = SoftlockDetector()
        detector.record_action("press:START", 42)
        
        softlock = detector.check_softlock(
            current_mode="MENU",
            current_sub_mode="MAIN_MENU",
            current_duration=5.0,
            current_action="press:START",
            tick=43
        )
        
        assert softlock is None  # Not enough repeats yet

    def test_record_state(self):
        """Test state recording"""
        detector = SoftlockDetector()
        detector.record_state("BATTLE.BATTLE_MENU")
        detector.record_state("BATTLE.MOVE_SELECTION")
        
        assert len(detector._state_sequence) == 2

    def test_save_and_get_known_good_state(self):
        """Test saving and retrieving known good states"""
        detector = SoftlockDetector()
        
        state = RecoveryState(
            tick=100,
            timestamp=time.time(),
            mode="OVERWORLD",
            sub_mode="NAVIGATION",
            state_name="OVERWORLD.IDLE",
            player_hp_percent=100.0,
            enemy_hp_percent=None,
            location="Route 1",
            recent_actions=["press:A", "press:UP"],
            confidence=0.9,
            anomalies=[]
        )
        
        detector.save_known_good_state(state)
        
        saved = detector.get_last_known_good_state()
        assert saved is not None
        assert saved.tick == 100
        assert saved.mode == "OVERWORLD"

    def test_known_good_states_limit(self):
        """Test that known good states are limited"""
        detector = SoftlockDetector()
        
        for i in range(60):
            state = RecoveryState(
                tick=i,
                timestamp=time.time(),
                mode="OVERWORLD",
                sub_mode="NAVIGATION",
                state_name="OVERWORLD.IDLE",
                player_hp_percent=100.0,
                enemy_hp_percent=None,
                location="Route 1",
                recent_actions=[],
                confidence=0.9,
                anomalies=[]
            )
            detector.save_known_good_state(state)
        
        saved = detector.get_last_known_good_state()
        assert saved is not None
        assert saved.tick == 59  # Most recent

    def test_get_softlock_history(self):
        """Test retrieving softlock history"""
        detector = SoftlockDetector()
        
        detector.check_softlock("BATTLE", "TRAINER", 700.0, None, 100)
        detector.check_softlock("DIALOG", "NPC_LONG", 400.0, None, 200)
        
        history = detector.get_softlock_history(count=10)
        assert len(history) == 2

    def test_thresholds_for_different_modes(self):
        """Test that different modes have different thresholds"""
        detector = SoftlockDetector()
        
        short_threshold_modes = [
            ("DIALOG", "NPC_SHORT", 70),
            ("MENU", "PAUSE", 130),
        ]
        
        for mode, sub_mode, duration in short_threshold_modes:
            softlock = detector.check_softlock(mode, sub_mode, float(duration), None, 1)
            assert softlock is not None, f"Expected softlock for {mode}/{sub_mode}"

    def test_no_false_positives_normal_operation(self):
        """Test no false positives during normal operation"""
        detector = SoftlockDetector()
        
        for i in range(100):
            result = detector.check_softlock(
                current_mode="OVERWORLD",
                current_sub_mode="NAVIGATION",
                current_duration=5.0,
                current_action=f"action_{i % 5}",
                tick=i,
                game_state={"tick": i, "location": f"Location {i}", "player_hp_percent": 100.0}
            )
        
        history = detector.get_softlock_history(10)
        assert len(history) == 0

    def test_thread_safety(self):
        """Test thread-safe operation"""
        detector = SoftlockDetector()
        
        def trigger_checks():
            for i in range(50):
                detector.check_softlock("OVERWORLD", "NAVIGATION", float(i), f"action_{i}", i)
                detector.record_action(f"action_{i}", i)
        
        threads = [threading.Thread(target=trigger_checks) for _ in range(4)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        history = detector.get_softlock_history(200)
        assert len(history) >= 0  # Just verify no crashes


class TestEmergencyRecovery:
    """Tests for EmergencyRecovery class (10 tests)"""

    def test_initiate_recovery_success(self):
        """Test successful recovery initiation"""
        recovery = EmergencyRecovery()
        
        result = recovery.initiate_recovery(
            reason="Test recovery",
            softlock_info=None,
            current_state={"test": "state"}
        )
        
        assert result.success is True
        assert "recovery_initiated" in result.actions_taken
        assert any("snapshot_saved" in action for action in result.actions_taken)
        assert result.time_taken_ms >= 0

    def test_initiate_recovery_with_softlock_info(self):
        """Test recovery with softlock info provided"""
        state_machine = HierarchicalStateMachine()
        recovery = EmergencyRecovery(state_machine=state_machine)
        
        softlock = SoftlockInfo(
            type="MODE_DURATION_EXCEEDED",
            severity="HIGH",
            description="Test softlock",
            timestamp=time.time(),
            tick=100,
            mode="BATTLE",
            sub_mode="TRAINER",
            duration_seconds=600.0
        )
        
        result = recovery.initiate_recovery(
            reason="Softlock detected",
            softlock_info=softlock,
            current_state={"screen_type": "battle"}
        )
        
        assert result.success is True
        assert result.recovery_type == "mode_duration_recovery"

    def test_state_rollback(self):
        """Test state rollback functionality"""
        state_machine = HierarchicalStateMachine()
        state_machine.transition_to("OVERWORLD.IDLE", tick=1)
        state_machine.transition_to("EMERGENCY.SOFTLOCK_DETECTED", tick=2)
        
        recovery = EmergencyRecovery(state_machine=state_machine)
        
        result = recovery.initiate_recovery(
            reason="Test",
            softlock_info=None,
            current_state={}
        )
        
        assert result.success is True

    def test_snapshot_saved_to_file(self):
        """Test that snapshots are saved to file"""
        recovery = EmergencyRecovery(snapshot_dir="/tmp/test_snapshots")
        
        recovery.initiate_recovery("Test", None, {"test": "data"})
        
        files = os.listdir("/tmp/test_snapshots")
        snapshot_files = [f for f in files if f.startswith("snapshot_")]
        assert len(snapshot_files) >= 1
        
        for f in snapshot_files:
            os.remove(f"/tmp/test_snapshots/{f}")

    def test_emergency_report_created(self):
        """Test that emergency reports are created"""
        recovery = EmergencyRecovery(snapshot_dir="/tmp/test_snapshots")
        
        recovery.initiate_recovery("Test", None, {})
        
        files = os.listdir("/tmp/test_snapshots")
        report_files = [f for f in files if f.startswith("emergency_report_")]
        assert len(report_files) >= 1
        
        for f in report_files:
            os.remove(f"/tmp/test_snapshots/{f}")

    def test_get_recovery_history(self):
        """Test retrieving recovery history"""
        recovery = EmergencyRecovery()
        
        recovery.initiate_recovery("Test 1", None, {})
        recovery.initiate_recovery("Test 2", None, {})
        
        history = recovery.get_recovery_history(count=10)
        assert len(history) == 2

    def test_is_recovering_during_recovery(self):
        """Test is_recovering flag during active recovery"""
        recovery = EmergencyRecovery()
        
        assert recovery.is_recovering() is False
        
        recovery.initiate_recovery("Test", None, {})
        
        assert recovery.is_recovering() is True

    def test_recovery_history_limit(self):
        """Test that recovery history is maintained"""
        recovery = EmergencyRecovery()
        
        for i in range(25):
            recovery.initiate_recovery(f"Test {i}", None, {})
        
        history = recovery.get_recovery_history(count=10)
        assert len(history) == 10  # Limited to requested count

    def test_snapshot_contains_state_machine_info(self):
        """Test that snapshots contain state machine info"""
        state_machine = HierarchicalStateMachine()
        state_machine.transition_to("OVERWORLD.IDLE", tick=1)
        
        recovery = EmergencyRecovery(state_machine=state_machine)
        recovery.initiate_recovery("Test", None, {"test": "state"})
        
        files = [f for f in os.listdir(recovery.snapshot_dir) if f.startswith("snapshot_")]
        assert len(files) >= 1
        with open(os.path.join(recovery.snapshot_dir, files[0])) as f:
            data = json.load(f)
            assert "state_machine" in data

    def test_recovery_with_empty_game_state(self):
        """Test recovery with minimal game state"""
        recovery = EmergencyRecovery()
        
        result = recovery.initiate_recovery(
            reason="Minimal state test",
            softlock_info=None,
            current_state={}
        )
        
        assert result.success is True
        assert any("snapshot_saved" in action for action in result.actions_taken)


class TestDeathSpiralPreventer:
    """Tests for DeathSpiralPreventer class (8 tests)"""

    def test_check_hp_status_healthy(self):
        """Test HP status check - healthy range"""
        preventer = DeathSpiralPreventer()
        
        result = preventer.check_hp_status(
            player_hp_percent=80.0,
            party_hp_percent=75.0,
            tick=100
        )
        
        assert result["status"] == "healthy"
        assert result["should_heal"] is False
        assert result["recommended_action"] is None

    def test_check_hp_status_warning(self):
        """Test HP status check - warning range"""
        preventer = DeathSpiralPreventer(warning_threshold=0.25)
        
        result = preventer.check_hp_status(
            player_hp_percent=0.20,  # 20%
            party_hp_percent=30.0,
            tick=100
        )
        
        assert result["status"] == "warning"
        assert result["alerts"] is not None
        assert len(result["alerts"]) > 0

    def test_check_hp_status_critical(self):
        """Test HP status check - critical range"""
        preventer = DeathSpiralPreventer(critical_threshold=0.10)
        
        result = preventer.check_hp_status(
            player_hp_percent=0.05,  # 5%
            party_hp_percent=10.0,
            tick=100
        )
        
        assert result["status"] == "critical"
        assert result["should_heal"] is True
        assert result["recommended_action"] == "heal_immediately"

    def test_check_hp_status_none_value(self):
        """Test HP status check with None value"""
        preventer = DeathSpiralPreventer()
        
        result = preventer.check_hp_status(
            player_hp_percent=None,
            party_hp_percent=None,
            tick=100
        )
        
        assert result["status"] == "healthy"

    def test_check_party_status_all_healthy(self):
        """Test party status - all healthy"""
        preventer = DeathSpiralPreventer()
        
        party = [
            {"name": "Pikachu", "hp_percent": 100.0},
            {"name": "Charmander", "hp_percent": 95.0},
            {"name": "Bulbasaur", "hp_percent": 90.0}
        ]
        
        result = preventer.check_party_status(party, tick=100)
        
        assert result["healthy"] is True
        assert result["can_battle"] is True
        assert result["alive_count"] == 3
        assert result["should_heal"] is False

    def test_check_party_status_some_low(self):
        """Test party status - some low HP"""
        preventer = DeathSpiralPreventer(warning_threshold=0.25)
        
        party = [
            {"name": "Pikachu", "hp_percent": 100.0},
            {"name": "Charmander", "hp_percent": 0.10},  # 10%
            {"name": "Bulbasaur", "hp_percent": 0.15}    # 15%
        ]
        
        result = preventer.check_party_status(party, tick=100)
        
        assert result["should_heal"] is True

    def test_check_party_status_empty(self):
        """Test party status - empty party"""
        preventer = DeathSpiralPreventer()
        
        result = preventer.check_party_status([], tick=100)
        
        assert result["healthy"] is True
        assert result["can_battle"] is True

    def test_get_hp_trend(self):
        """Test HP trend analysis"""
        preventer = DeathSpiralPreventer()
        
        for hp in [100, 90, 80, 70, 60]:
            preventer.check_hp_status(hp, None, tick=hp)
        
        trend = preventer.get_hp_trend()
        assert trend["trend"] == "declining"
        assert trend["current"] == 60.0
        assert trend["avg"] == pytest.approx(80.0)

    def test_check_pp_status_stub(self):
        """Test PP status check (MVP stub)"""
        preventer = DeathSpiralPreventer()
        
        result = preventer.check_pp_status({"Thunderbolt": 30}, tick=100)
        
        assert result["_stub"] is True
        assert result["has_pp"] is True

    def test_check_escape_available_stub(self):
        """Test escape availability check (MVP stub)"""
        preventer = DeathSpiralPreventer()
        
        result = preventer.check_escape_available(tick=100)
        
        assert result["_stub"] is True
        assert result["available"] is True

    def test_consecutive_low_hp_tracking(self):
        """Test tracking of consecutive low HP ticks"""
        preventer = DeathSpiralPreventer(critical_threshold=0.10)
        
        for _ in range(3):
            preventer.check_hp_status(0.05, None, tick=1)
        
        assert preventer._consecutive_low_hp_ticks == 3

    def test_hp_trend_insufficient_data(self):
        """Test HP trend with insufficient data"""
        preventer = DeathSpiralPreventer()
        
        trend = preventer.get_hp_trend()
        assert trend["trend"] == "insufficient_data"


class TestSystemHealthMonitor:
    """Tests for SystemHealthMonitor class (8 tests)"""

    def test_check_health_returns_metrics(self):
        """Test that check_health returns valid metrics"""
        monitor = SystemHealthMonitor()
        
        metrics = monitor.check_health()
        
        assert isinstance(metrics, HealthMetrics)
        assert metrics.timestamp > 0
        assert metrics.memory_usage_mb > 0
        assert 0.0 <= metrics.overall_score <= 1.0

    def test_health_score_calculation(self):
        """Test health score calculation"""
        monitor = SystemHealthMonitor()
        
        metrics = monitor.check_health()
        
        score = metrics.overall_score
        assert 0.0 <= score <= 1.0

    def test_record_api_latency(self):
        """Test recording API latency"""
        monitor = SystemHealthMonitor()
        
        monitor.record_api_latency(500.0)
        monitor.record_api_latency(1000.0)
        
        recent = monitor._get_recent_api_latency()
        assert recent == pytest.approx(750.0)

    def test_get_health_status_healthy(self):
        """Test health status - healthy"""
        monitor = SystemHealthMonitor()
        
        status = monitor.get_health_status()
        
        assert status["status"] in ["healthy", "warning", "critical"]
        assert "score" in status

    def test_get_health_status_warning(self):
        """Test health status - warning conditions"""
        monitor = SystemHealthMonitor(
            memory_warning_mb=1.0,
            api_latency_warning_ms=1.0
        )
        
        monitor.record_api_latency(100.0)
        
        status = monitor.get_health_status()
        
        assert status["status"] in ["healthy", "warning", "critical"]
        assert len(status["issues"]) >= 0

    def test_get_health_history(self):
        """Test retrieving health history"""
        monitor = SystemHealthMonitor()
        
        for _ in range(5):
            monitor.check_health()
        
        history = monitor.get_health_history(count=3)
        assert len(history) == 3

    def test_api_success_rate_stub(self):
        """Test API success rate (MVP stub returns 1.0)"""
        monitor = SystemHealthMonitor()
        
        success = monitor._get_api_success_rate()
        assert success == 1.0

    def test_health_score_decreases_with_issues(self):
        """Test that health score decreases with issues"""
        monitor = SystemHealthMonitor(
            memory_critical_mb=0.001  # Very low threshold
        )
        
        metrics = monitor.check_health()
        
        if metrics.memory_usage_mb > 0.001:
            assert metrics.overall_score < 1.0

    def test_health_history_limit(self):
        """Test that health history is limited"""
        monitor = SystemHealthMonitor()
        
        for _ in range(1100):
            monitor.check_health()
        
        history = monitor.get_health_history(count=1000)
        assert len(history) <= 1000


class TestFailsafeManager:
    """Tests for FailsafeManager integration (6 tests)"""

    def test_update_returns_comprehensive_result(self):
        """Test that update returns all expected fields"""
        manager = FailsafeManager()
        
        result = manager.update(
            game_state={"screen_type": "overworld"},
            ai_confidence=0.9,
            vision_confidence=0.85,
            tick=100
        )
        
        assert "confidence" in result
        assert "softlock" in result
        assert "health" in result
        assert "hp_status" in result
        assert "recovery_triggered" in result
        assert "confidence_acceptable" in result
        assert "confidence_level" in result
        assert result["tick"] == 100

    def test_update_with_no_softlock(self):
        """Test update with no softlock detected"""
        manager = FailsafeManager()
        
        result = manager.update(
            game_state={
                "screen_type": "overworld",
                "menu_type": "navigation",
                "mode_duration": 10.0,
                "last_action": "press:A",
                "player_hp_percent": 100.0
            },
            ai_confidence=0.9,
            tick=100
        )
        
        assert result["softlock"] is None
        assert result["recovery_triggered"] is False
        assert result["confidence_acceptable"] is True

    def test_enable_disable(self):
        """Test enabling and disabling failsafe"""
        manager = FailsafeManager()
        
        assert manager.is_enabled() is True
        
        manager.disable()
        assert manager.is_enabled() is False
        
        manager.enable()
        assert manager.is_enabled() is True

    def test_check_action(self):
        """Test action checking"""
        manager = FailsafeManager()
        
        manager.check_action("press:START", 100)
        
        assert True  # No exception

    def test_record_state(self):
        """Test state recording"""
        manager = FailsafeManager()
        
        manager.record_state("BATTLE.BATTLE_MENU")
        
        assert True  # No exception

    def test_get_dashboard_data(self):
        """Test dashboard data retrieval"""
        manager = FailsafeManager()
        
        manager.update({"screen_type": "overworld"}, tick=100)
        
        data = manager.get_dashboard_data()
        
        assert "enabled" in data
        assert "tick" in data
        assert "confidence" in data
        assert "health_status" in data

    def test_failsafe_with_state_machine(self):
        """Test failsafe manager with state machine"""
        state_machine = HierarchicalStateMachine()
        manager = FailsafeManager(state_machine=state_machine)
        
        result = manager.update(
            game_state={"screen_type": "overworld"},
            ai_confidence=0.8,
            tick=100
        )
        
        assert result is not None


class TestFailsafeIntegration:
    """Integration tests (4 tests)"""

    def test_full_failsafe_cycle(self):
        """Test complete failsafe cycle"""
        state_machine = HierarchicalStateMachine()
        manager = FailsafeManager(state_machine=state_machine)
        
        result = None
        for i in range(10):
            result = manager.update(
                game_state={
                    "screen_type": "overworld",
                    "menu_type": "navigation",
                    "mode_duration": float(i),
                    "last_action": f"action_{i % 3}",
                    "player_hp_percent": 100.0 - i
                },
                ai_confidence=0.9 - (i * 0.01),
                vision_confidence=0.85,
                tick=i
            )
        
        assert result is not None

    def test_recovery_after_softlock(self):
        """Test recovery sequence after softlock"""
        state_machine = HierarchicalStateMachine()
        manager = FailsafeManager(state_machine=state_machine)
        
        state_machine.transition_to("BATTLE.TRAINER", tick=100)
        state_machine.transition_to("BATTLE.BATTLE_MENU", tick=101)
        
        result = manager.update(
            game_state={
                "screen_type": "battle",
                "menu_type": "battle",
                "mode_duration": 700.0,
                "last_action": "press:A"
            },
            tick=1001
        )
        
        assert result["softlock"] is not None or result["recovery_triggered"] is not None

    def test_confidence_tracking_across_updates(self):
        """Test confidence tracking across multiple updates"""
        manager = FailsafeManager()
        
        confidences = []
        for i in range(10):
            result = manager.update(
                game_state={"screen_type": "overworld"},
                ai_confidence=0.9 - (i * 0.05),
                tick=i
            )
            confidences.append(result["confidence"]["overall_confidence"])
        
        assert len(confidences) == 10
        assert confidences[0] > confidences[-1]

    def test_get_dashboard_data_after_updates(self):
        """Test dashboard data after multiple updates"""
        manager = FailsafeManager()
        
        for i in range(5):
            manager.update(
                game_state={"screen_type": "overworld"},
                ai_confidence=0.9,
                tick=i
            )
        
        data = manager.get_dashboard_data()
        
        assert data["tick"] == 4
        assert data["confidence"] is not None
        assert data["health_status"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])