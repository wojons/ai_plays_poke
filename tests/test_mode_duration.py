"""
Tests for Mode Duration Tracking System
"""

import pytest
import time
import tempfile
import os
from unittest.mock import MagicMock, patch
from src.core.mode_duration import (
    GameMode, OverworldSubMode, BattleSubMode, DialogSubMode, MenuSubMode, CutsceneSubMode,
    AnomalySeverity, EscalationTier, BreakoutStrategy,
    ModeClassification, ModeEntry, ModeExit, ModeDurationProfile, Anomaly, BreakoutResult, ResponsePlan,
    ModeClassifier, DurationTracker, DurationProfileLearner, DurationProfileStore,
    AnomalyDetector, AnomalyResponseSelector, BreakoutManager, BreakoutAnalytics,
    ModeDurationEscalation, ModeDurationTrackingSystem,
)


class TestModeClassifier:
    def setup_method(self):
        self.classifier = ModeClassifier()

    def test_classify_overworld(self):
        state = {"is_battle": False, "has_dialog": False, "is_menu": False, "screen_type": "overworld"}
        result = self.classifier.classify_mode(state, tick=100)
        assert result.mode == GameMode.OVERWORLD.value
        assert result.sub_mode == OverworldSubMode.NAVIGATION.value
        assert result.confidence > 0.7

    def test_classify_battle(self):
        state = {"is_battle": True, "has_dialog": False, "is_menu": False}
        result = self.classifier.classify_mode(state, tick=101)
        assert result.mode == GameMode.BATTLE.value
        assert result.sub_mode == BattleSubMode.WILD_NORMAL.value

    def test_classify_battle_with_trainer(self):
        state = {"is_battle": True, "trainer_name": "Blue"}
        result = self.classifier.classify_mode(state, tick=102)
        assert result.mode == GameMode.BATTLE.value
        assert result.sub_mode == BattleSubMode.TRAINER.value

    def test_classify_battle_gym_leader(self):
        state = {"is_battle": True, "gym_leader": True}
        result = self.classifier.classify_mode(state, tick=103)
        assert result.mode == GameMode.BATTLE.value
        assert result.sub_mode == BattleSubMode.GYM_LEADER.value

    def test_classify_dialog(self):
        state = {"has_dialog": True, "dialog_text": "Hello there!"}
        result = self.classifier.classify_mode(state, tick=104)
        assert result.mode == GameMode.DIALOG.value
        assert result.sub_mode == DialogSubMode.NPC_SHORT.value

    def test_classify_dialog_long(self):
        state = {"has_dialog": True, "dialog_text": "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8\nLine 9\nLine 10\nLine 11"}
        result = self.classifier.classify_mode(state, tick=105)
        assert result.mode == GameMode.DIALOG.value
        assert result.sub_mode == DialogSubMode.NPC_LONG.value

    def test_classify_menu(self):
        state = {"is_menu": True, "menu_type": "pokemon"}
        result = self.classifier.classify_mode(state, tick=106)
        assert result.mode == GameMode.MENU.value
        assert result.sub_mode == MenuSubMode.POKEMON.value

    def test_classify_cutscene(self):
        state = {"screen_type": "cutscene", "dialog_text": "Welcome to the world of Pokemon!"}
        result = self.classifier.classify_mode(state, tick=107)
        assert result.mode == GameMode.CUTSCENE.value
        assert result.sub_mode == CutsceneSubMode.INTRO.value

    def test_classify_cutscene_evolution(self):
        state = {"screen_type": "cutscene", "dialog_text": "What? Pikachu is evolving!"}
        result = self.classifier.classify_mode(state, tick=108)
        assert result.mode == GameMode.CUTSCENE.value
        assert result.sub_mode == CutsceneSubMode.EVOLUTION.value

    def test_classify_caching(self):
        state = {"is_battle": True}
        result1 = self.classifier.classify_mode(state, tick=109)
        time.sleep(0.05)
        result2 = self.classifier.classify_mode(state, tick=110)
        assert result1.timestamp == result2.timestamp


class TestDurationTracker:
    def setup_method(self):
        self.tracker = DurationTracker()

    def test_enter_and_exit_mode(self):
        self.tracker.enter_mode("BATTLE", "WILD", tick=100)
        assert self.tracker.current_mode is not None
        assert self.tracker.current_mode.mode == "BATTLE"
        assert self.tracker.current_mode.sub_mode == "WILD"
        time.sleep(0.1)
        exit_record = self.tracker.exit_mode(reason="natural", tick=110)
        assert exit_record is not None
        assert exit_record.mode == "BATTLE"
        assert exit_record.duration > 0

    def test_get_current_duration(self):
        self.tracker.enter_mode("OVERWORLD", "NAVIGATION", tick=100)
        time.sleep(0.1)
        duration = self.tracker.get_current_duration()
        assert duration >= 0.1
        self.tracker.exit_mode(reason="natural", tick=200)

    def test_cumulative_tracking(self):
        self.tracker.enter_mode("BATTLE", "WILD", tick=100)
        time.sleep(0.1)
        self.tracker.exit_mode(reason="natural", tick=200)
        self.tracker.enter_mode("BATTLE", "WILD", tick=200)
        time.sleep(0.1)
        self.tracker.exit_mode(reason="natural", tick=300)
        cumulative = self.tracker.get_current_cumulative("session")
        assert cumulative > 0

    def test_mode_sequence_tracking(self):
        self.tracker.enter_mode("OVERWORLD", "NAVIGATION", tick=100)
        self.tracker.exit_mode(reason="natural", tick=101)
        self.tracker.enter_mode("DIALOG", "NPC_SHORT", tick=101)
        self.tracker.exit_mode(reason="natural", tick=102)
        assert len(self.tracker.mode_sequence) == 2
        assert self.tracker.mode_sequence[0] == "OVERWORLD/NAVIGATION"
        assert self.tracker.mode_sequence[1] == "DIALOG/NPC_SHORT"

    def test_mode_transition_interrupt(self):
        self.tracker.enter_mode("OVERWORLD", "NAVIGATION", tick=100)
        time.sleep(0.1)
        interrupt_exit = self.tracker.enter_mode("BATTLE", "WILD", tick=110)
        assert self.tracker.current_mode.mode == "BATTLE"
        assert interrupt_exit.exit_reason == "interrupt"
        exit_record = self.tracker.exit_mode(reason="natural", tick=200)
        assert exit_record.exit_reason == "natural"


class TestDurationProfileLearner:
    def setup_method(self):
        self.learner = DurationProfileLearner()

    def test_update_profile_new(self):
        self.learner.update_profile("BATTLE", "WILD", 100.0)
        profile = self.learner.get_profile("BATTLE", "WILD")
        assert profile is not None
        assert profile.sample_count == 1
        assert profile.mean_duration == 100.0

    def test_update_profile_accumulates(self):
        for i in range(5):
            self.learner.update_profile("BATTLE", "WILD", 100.0 + i * 10)
        profile = self.learner.get_profile("BATTLE", "WILD")
        assert profile.sample_count == 5
        assert profile.mean_duration > 100.0

    def test_outlier_detection(self):
        for i in range(10):
            self.learner.update_profile("BATTLE", "WILD", 100.0)
        self.learner.update_profile("BATTLE", "WILD", 1000.0)
        profile = self.learner.get_profile("BATTLE", "WILD")
        assert profile.sample_count == 10

    def test_get_thresholds_unknown_profile(self):
        thresholds = self.learner.get_thresholds("UNKNOWN", "MODE")
        assert "warning" in thresholds
        assert "critical" in thresholds
        assert "emergency" in thresholds

    def test_get_thresholds_known_profile(self):
        for i in range(10):
            self.learner.update_profile("BATTLE", "WILD", 100.0)
        thresholds = self.learner.get_thresholds("BATTLE", "WILD")
        assert thresholds["warning"] > 0
        assert thresholds["critical"] > thresholds["warning"]
        assert thresholds["emergency"] > thresholds["critical"]


class TestDurationProfileStore:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.temp_dir, "test_profiles.json")
        self.store = DurationProfileStore(storage_path=self.storage_path)

    def test_save_and_load_profile(self):
        profile = ModeDurationProfile(
            mode="BATTLE", sub_mode="WILD", sample_count=5, mean_duration=120.0, std_duration=20.0,
            min_duration=100.0, max_duration=140.0, p50_duration=120.0, p75_duration=130.0,
            p95_duration=140.0, p99_duration=145.0, last_updated=time.time(), trend="stable", trend_slope=0.0,
        )
        self.store.save_profile(profile)
        profiles = self.store.load_profiles()
        assert "BATTLE/WILD" in profiles
        loaded = profiles["BATTLE/WILD"]
        assert loaded.mode == "BATTLE"
        assert loaded.sub_mode == "WILD"
        assert loaded.mean_duration == 120.0


class TestAnomalyDetector:
    def setup_method(self):
        self.learner = DurationProfileLearner()
        self.detector = AnomalyDetector(self.learner)

    def test_no_anomaly_normal_duration(self):
        anomalies = self.detector.detect_anomalies(
            "BATTLE", "WILD", 50.0, 100.0, 50.0, 500.0, [])
        assert len(anomalies) == 0

    def test_anomaly_unknown_mode_exceeds_emergency(self):
        anomalies = self.detector.detect_anomalies(
            "UNKNOWN", "MODE", 700.0, 0, 0, 0, [])
        assert len(anomalies) == 1
        assert anomalies[0].type == "DURATION_UNKNOWN_MODE"

    def test_anomaly_z_score_extreme(self):
        for i in range(10):
            self.learner.update_profile("BATTLE", "WILD", 100.0)
        anomalies = self.detector.detect_anomalies(
            "BATTLE", "WILD", 500.0, 0, 0, 0, [])
        assert len(anomalies) >= 1
        extreme_anomaly = [a for a in anomalies if a.type == "DURATION_EXTREME"]
        assert len(extreme_anomaly) == 1

    def test_anomaly_sequence_stickiness(self):
        sequence = ["BATTLE_WILD"] * 8 + ["DIALOG_NPC"] * 2
        anomalies = self.detector.detect_anomalies("", "", 0, 0, 0, 0, sequence)
        stickiness = [a for a in anomalies if a.type == "MODE_STICKINESS"]
        assert len(stickiness) == 1

    def test_anomaly_sequence_oscillation(self):
        sequence = ["BATTLE", "DIALOG", "BATTLE", "DIALOG", "BATTLE", "DIALOG"]
        anomalies = self.detector.detect_anomalies("", "", 0, 0, 0, 0, sequence)
        oscillation = [a for a in anomalies if a.type == "MODE_OSCILLATION"]
        assert len(oscillation) == 1

    def test_anomaly_cumulative_session_emergency(self):
        anomalies = self.detector.detect_anomalies(
            "BATTLE", "WILD", 0, 8000.0, 0, 0, [])
        emergency = [a for a in anomalies if a.type == "CUMULATIVE_SESSION_EMERGENCY"]
        assert len(emergency) == 1


class TestAnomalyResponseSelector:
    def setup_method(self):
        self.selector = AnomalyResponseSelector()

    def test_no_anomalies(self):
        response = self.selector.select_response([])
        assert response.escalation_tier == "NONE"
        assert len(response.actions) == 0

    def test_critical_anomaly_escalates(self):
        anomalies = [
            Anomaly(type="DURATION_EXTREME", severity="CRITICAL", description="Test",
                    value=100, threshold=50, recommended_action="break_out_immediate")
        ]
        response = self.selector.select_response(anomalies)
        assert response.escalation_tier == "EMERGENCY"
        assert "break_out_immediate" in response.actions

    def test_high_anomaly_escalates(self):
        anomalies = [
            Anomaly(type="DURATION_HIGH", severity="HIGH", description="Test",
                    value=100, threshold=50, recommended_action="break_out_aggressive")
        ]
        response = self.selector.select_response(anomalies)
        assert response.escalation_tier == "HIGH"

    def test_medium_anomaly_escalates(self):
        anomalies = [
            Anomaly(type="DURATION_WARNING", severity="MEDIUM", description="Test",
                    value=100, threshold=50, recommended_action="increase_monitoring")
        ]
        response = self.selector.select_response(anomalies)
        assert response.escalation_tier == "MEDIUM"


class TestBreakoutManager:
    def setup_method(self):
        self.manager = BreakoutManager()

    def test_execute_breakout_success(self):
        result = self.manager.execute_breakout(
            BreakoutStrategy.STANDARD, "BATTLE", "WILD", {})
        assert result is not None
        assert result.strategy == "break_out_standard"

    def test_execute_breakout_multiple_attempts(self):
        result = self.manager.execute_breakout(
            BreakoutStrategy.IMMEDIATE, "BATTLE", "WILD", {})
        assert result is not None
        assert result.attempts <= 3

    def test_breakout_history_tracking(self):
        self.manager.execute_breakout(BreakoutStrategy.STANDARD, "BATTLE", "WILD", {})
        assert len(self.manager.success_history) == 3


class TestBreakoutAnalytics:
    def setup_method(self):
        self.analytics = BreakoutAnalytics()

    def test_record_breakout(self):
        result = BreakoutResult(success=True, strategy="test", action="test_action", attempts=1)
        self.analytics.record_breakout(result)
        assert len(self.analytics.breakout_history) == 1

    def test_get_recommended_strategy(self):
        strategy = self.analytics.get_recommended_strategy("BATTLE", "WILD")
        assert strategy == BreakoutStrategy.STANDARD


class TestModeDurationEscalation:
    def setup_method(self):
        self.escalation = ModeDurationEscalation()

    def test_initial_tier_none(self):
        assert self.escalation.current_tier == EscalationTier.NONE

    def test_update_escalation_no_anomalies(self):
        tier = self.escalation.update_escalation([], 90.0)
        assert tier == EscalationTier.NONE

    def test_update_escalation_critical_anomaly(self):
        anomalies = [
            Anomaly(type="DURATION_EXTREME", severity="CRITICAL", description="Test",
                    value=100, threshold=50)
        ]
        tier = self.escalation.update_escalation(anomalies, 90.0)
        assert tier == EscalationTier.RESET_CONDITION

    def test_update_escalation_high_anomaly(self):
        anomalies = [
            Anomaly(type="DURATION_HIGH", severity="HIGH", description="Test",
                    value=100, threshold=50)
        ]
        tier = self.escalation.update_escalation(anomalies, 90.0)
        assert tier == EscalationTier.EMERGENCY_PROTOCOL

    def test_update_escalation_low_confidence(self):
        tier = self.escalation.update_escalation([], 30.0)
        assert tier == EscalationTier.EMERGENCY_PROTOCOL

    def test_get_check_interval(self):
        interval = self.escalation.get_check_interval()
        assert interval == 10.0

    def test_tier_transition_tracking(self):
        anomalies = [Anomaly(type="DURATION_EXTREME", severity="CRITICAL", description="Test",
                             value=100, threshold=50)]
        self.escalation.update_escalation(anomalies, 90.0)
        assert len(self.escalation.tier_history) == 1


class TestModeDurationTrackingSystem:
    def setup_method(self):
        self.mdts = ModeDurationTrackingSystem()

    def test_update_classifies_mode(self):
        state = {"is_battle": True}
        result = self.mdts.update(state, tick=100)
        assert result["mode"] == GameMode.BATTLE.value
        assert result["sub_mode"] == BattleSubMode.WILD_NORMAL.value

    def test_update_detects_anomalies(self):
        state = {"is_battle": True}
        result = self.mdts.update(state, tick=100)
        assert "anomalies" in result
        assert "escalation_tier" in result

    def test_update_tracks_duration(self):
        state = {"is_battle": True}
        self.mdts.update(state, tick=100)
        time.sleep(0.1)
        result = self.mdts.update(state, tick=101)
        assert result["current_duration"] >= 0.1

    def test_on_mode_exit_learns_profile(self):
        self.mdts.duration_tracker.enter_mode("BATTLE", "WILD", tick=100)
        time.sleep(0.1)
        self.mdts.on_mode_exit("BATTLE", "WILD", "natural", tick=200)
        profile = self.mdts.profile_learner.get_profile("BATTLE", "WILD")
        assert profile is not None

    def test_get_dashboard_data(self):
        state = {"is_battle": True}
        self.mdts.update(state, tick=100)
        data = self.mdts.get_dashboard_data()
        assert "current_mode" in data
        assert "current_duration" in data
        assert "escalation_tier" in data

    def test_integration_with_state_machine(self):
        state_machine = MagicMock()
        mdts = ModeDurationTrackingSystem(state_machine=state_machine)
        state = {"is_battle": False}
        result = mdts.update(state, tick=100)
        assert result["mode"] == GameMode.OVERWORLD.value


class TestDataClasses:
    def test_mode_classification_serialization(self):
        mc = ModeClassification(
            mode="BATTLE", sub_mode="WILD", confidence=0.85,
            timestamp=time.time(), tick=100
        )
        assert mc.mode == "BATTLE"

    def test_mode_duration_profile_serialization(self):
        profile = ModeDurationProfile(
            mode="BATTLE", sub_mode="WILD", sample_count=10, mean_duration=120.0,
            std_duration=20.0, min_duration=100.0, max_duration=140.0,
            p50_duration=120.0, p75_duration=130.0, p95_duration=140.0,
            p99_duration=145.0, last_updated=time.time(), trend="stable", trend_slope=0.0,
        )
        data = profile.to_dict()
        assert data["mode"] == "BATTLE"
        loaded = ModeDurationProfile.from_dict(data)
        assert loaded.mode == profile.mode

    def test_anomaly_serialization(self):
        anomaly = Anomaly(
            type="DURATION_HIGH", severity="HIGH", description="Test anomaly",
            value=100.0, threshold=50.0, deviation=2.5
        )
        assert anomaly.type == "DURATION_HIGH"
        assert anomaly.severity == "HIGH"

    def test_breakout_result(self):
        result = BreakoutResult(
            success=True, strategy="break_out_standard", action="RUN", attempts=2
        )
        assert result.success is True
        assert result.attempts == 2


class TestEdgeCases:
    def test_empty_state(self):
        classifier = ModeClassifier()
        result = classifier.classify_mode({}, tick=0)
        assert result.mode == GameMode.OVERWORLD.value

    def test_empty_state_duration_tracker(self):
        tracker = DurationTracker()
        assert tracker.get_current_duration() == 0.0
        assert tracker.get_current_cumulative() == 0.0
        assert tracker.exit_mode() is None

    def test_anomaly_detector_empty_sequence(self):
        learner = DurationProfileLearner()
        detector = AnomalyDetector(learner)
        anomalies = detector.detect_anomalies("", "", 0, 0, 0, 0, [])
        assert len(anomalies) == 0

    def test_profile_learner_zero_duration(self):
        learner = DurationProfileLearner()
        learner.update_profile("TEST", "MODE", 0.0)
        profile = learner.get_profile("TEST", "MODE")
        assert profile is not None
        assert profile.mean_duration == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
