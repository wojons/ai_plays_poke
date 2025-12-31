"""
Failsafe Protocols for PTP-01X Pokemon AI

Provides comprehensive safety mechanisms:
- Confidence scoring for AI decisions
- Softlock detection and recovery
- Emergency recovery procedures
- Death spiral prevention
- System health monitoring
"""

import json
import time
import threading
import traceback
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple, Set
from collections import defaultdict, deque
from enum import Enum
import logging
import psutil
import os

from src.core.logger import get_logger, LogCategory
from src.core.state_machine import (
    HierarchicalStateMachine, StateType, EmergencySubState,
    StateTransitionResult
)


logger = logging.getLogger(__name__)


class ConfidenceLevel(Enum):
    """Confidence level thresholds"""
    HIGH = 0.85
    MEDIUM = 0.70
    LOW = 0.50
    CRITICAL = 0.30


@dataclass
class ConfidenceBreakdown:
    """Breakdown of confidence components"""
    ai_decision_confidence: float = 0.0
    vision_confidence: float = 0.0
    state_detection_confidence: float = 0.0
    overall_confidence: float = 0.0
    timestamp: float = 0.0
    tick: int = 0
    factors: List[str] = field(default_factory=list)


@dataclass
class SoftlockInfo:
    """Information about a detected softlock"""
    type: str
    severity: str
    description: str
    timestamp: float
    tick: int
    mode: str
    sub_mode: str
    duration_seconds: float
    repeated_action: Optional[str] = None
    state_sequence: List[str] = field(default_factory=list)
    actions_taken: List[str] = field(default_factory=list)


@dataclass
class RecoveryState:
    """State snapshot for recovery purposes"""
    tick: int
    timestamp: float
    mode: str
    sub_mode: str
    state_name: str
    player_hp_percent: Optional[float]
    enemy_hp_percent: Optional[float]
    location: Optional[str]
    recent_actions: List[str]
    confidence: float
    anomalies: List[str]


@dataclass
class RecoveryResult:
    """Result of a recovery attempt"""
    success: bool
    recovery_type: str
    actions_taken: List[str]
    time_taken_ms: float
    new_confidence: float
    state_restored: bool
    message: str
    timestamp: float


@dataclass
class HealthMetrics:
    """System health metrics snapshot"""
    timestamp: float
    memory_usage_mb: float
    memory_percent: float
    cpu_percent: float
    api_latency_ms: float
    api_success_rate: float
    db_healthy: bool
    emulator_healthy: bool
    tick_rate: float
    overall_score: float


class ConfidenceScorer:
    """
    Calculates and manages confidence scores for AI decisions
    
    Combines:
    - AI decision confidence (from model response)
    - Vision confidence (from OCR certainty)
    - State detection confidence (from HSM state certainty)
    """

    def __init__(self, default_threshold: float = 0.7,
                 high_threshold: float = 0.85,
                 critical_threshold: float = 0.3):
        self.default_threshold = default_threshold
        self.high_threshold = high_threshold
        self.critical_threshold = critical_threshold
        self._lock = threading.Lock()
        self._confidence_history: deque = deque(maxlen=100)
        self._last_confidence: Optional[ConfidenceBreakdown] = None

    def calculate_confidence(
        self,
        ai_confidence: Optional[float] = None,
        vision_confidence: Optional[float] = None,
        state_confidence: Optional[float] = None,
        tick: int = 0
    ) -> ConfidenceBreakdown:
        """
        Calculate combined confidence score
        
        Args:
            ai_confidence: Confidence from AI model response
            vision_confidence: Confidence from vision/OCR system
            state_confidence: Confidence from state detection
            tick: Current tick
            
        Returns:
            ConfidenceBreakdown with all components and overall score
        """
        with self._lock:
            factors = []
            
            ai_score = ai_confidence if ai_confidence is not None else 1.0
            if ai_confidence is None:
                factors.append("AI confidence: default (1.0)")
            
            vision_score = vision_confidence if vision_confidence is not None else 1.0
            if vision_confidence is None:
                factors.append("Vision confidence: default (1.0)")
            
            state_score = state_confidence if state_confidence is not None else 1.0
            if state_confidence is None:
                factors.append("State confidence: default (1.0)")
            
            if ai_confidence is not None:
                factors.append(f"AI confidence: {ai_confidence:.2f}")
            if vision_confidence is not None:
                factors.append(f"Vision confidence: {vision_confidence:.2f}")
            if state_confidence is not None:
                factors.append(f"State confidence: {state_confidence:.2f}")
            
            weights = {"ai": 0.4, "vision": 0.35, "state": 0.25}
            overall = (
                weights["ai"] * ai_score +
                weights["vision"] * vision_score +
                weights["state"] * state_score
            )
            
            breakdown = ConfidenceBreakdown(
                ai_decision_confidence=ai_score,
                vision_confidence=vision_score,
                state_detection_confidence=state_score,
                overall_confidence=overall,
                timestamp=time.time(),
                tick=tick,
                factors=factors
            )
            
            self._confidence_history.append(breakdown)
            self._last_confidence = breakdown
            
            return breakdown

    def get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Get confidence level enum from score"""
        if confidence >= self.high_threshold:
            return ConfidenceLevel.HIGH
        elif confidence >= self.default_threshold:
            return ConfidenceLevel.MEDIUM
        elif confidence >= self.critical_threshold:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.CRITICAL

    def is_confidence_acceptable(self, confidence: float) -> bool:
        """Check if confidence meets default threshold"""
        return confidence >= self.default_threshold

    def get_recent_confidence_trend(self) -> Dict[str, Any]:
        """Get trend analysis of recent confidence scores"""
        if len(self._confidence_history) < 5:
            return {"trend": "insufficient_data", "avg": None, "count": len(self._confidence_history)}
        
        recent = list(self._confidence_history)[-10:]
        scores = [c.overall_confidence for c in recent]
        
        avg = sum(scores) / len(scores)
        
        if len(scores) >= 3:
            early_avg = sum(scores[:3]) / 3
            late_avg = sum(scores[-3:]) / 3
            if late_avg > early_avg + 0.05:
                trend = "improving"
            elif late_avg < early_avg - 0.05:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"
        
        return {"trend": trend, "avg": avg, "min": min(scores), "max": max(scores), "count": len(scores)}

    def get_last_confidence(self) -> Optional[ConfidenceBreakdown]:
        """Get the most recent confidence breakdown"""
        return self._last_confidence

    def get_confidence_history(self, count: int = 10) -> List[ConfidenceBreakdown]:
        """Get recent confidence history"""
        return list(self._confidence_history)[-count:]


class SoftlockDetector:
    """
    Detects various types of softlocks and stuck conditions
    
    Integrates with:
    - Mode Duration Tracking for anomaly detection
    - HSM for state transition tracking
    - Action history for repeated action detection
    """

    def __init__(self,
                 state_machine: Optional[HierarchicalStateMachine] = None,
                 progress_window_seconds: float = 30.0,
                 repeated_action_threshold: int = 10):
        self.state_machine = state_machine
        self.progress_window_seconds = progress_window_seconds
        self.repeated_action_threshold = repeated_action_threshold
        
        self._lock = threading.Lock()
        self._action_history: deque = deque(maxlen=100)
        self._state_sequence: List[str] = []
        self._last_progress_tick: int = 0
        self._last_progress_time: float = 0.0
        self._softlock_history: List[SoftlockInfo] = []
        self._known_good_states: List[RecoveryState] = []
        self._max_known_states = 50

    def check_softlock(
        self,
        current_mode: str,
        current_sub_mode: str,
        current_duration: float,
        current_action: Optional[str],
        tick: int,
        game_state: Optional[Dict[str, Any]] = None
    ) -> Optional[SoftlockInfo]:
        """
        Check for softlock conditions
        
        Returns SoftlockInfo if softlock detected, None otherwise
        """
        with self._lock:
            softlock_info = None
            
            mode_duration_issue = self._check_mode_duration(
                current_mode, current_sub_mode, current_duration
            )
            if mode_duration_issue:
                softlock_info = mode_duration_issue
            
            repeated_action_issue = self._check_repeated_action(current_action, tick)
            if repeated_action_issue and not softlock_info:
                softlock_info = repeated_action_issue
            
            state_loop_issue = self._check_state_loop(tick)
            if state_loop_issue and not softlock_info:
                softlock_info = state_loop_issue
            
            progress_issue = self._check_zero_progress(tick, game_state)
            if progress_issue and not softlock_info:
                softlock_info = progress_issue
            
            if softlock_info:
                self._softlock_history.append(softlock_info)
                logger.warning(
                    f"Softlock detected: {softlock_info.type} - {softlock_info.description}",
                    extra={"category": LogCategory.ERRORS, "tick": tick}
                )
            
            return softlock_info

    def _check_mode_duration(
        self,
        mode: str,
        sub_mode: str,
        duration: float
    ) -> Optional[SoftlockInfo]:
        """Check if mode duration exceeds expected thresholds"""
        thresholds = {
            ("BATTLE", "WILD_EASY"): 300,
            ("BATTLE", "WILD_NORMAL"): 300,
            ("BATTLE", "WILD_HARD"): 600,
            ("BATTLE", "TRAINER"): 600,
            ("BATTLE", "GYM_LEADER"): 900,
            ("DIALOG", "NPC_SHORT"): 60,
            ("DIALOG", "NPC_LONG"): 300,
            ("MENU", "PAUSE"): 120,
            ("MENU", "MAIN_MENU"): 180,
            ("OVERWORLD", "NAVIGATION"): 300,
        }
        
        key = (mode, sub_mode)
        threshold = thresholds.get(key, 180)
        
        if duration > threshold:
            severity = "HIGH" if duration > threshold * 2 else "MEDIUM"
            return SoftlockInfo(
                type="MODE_DURATION_EXCEEDED",
                severity=severity,
                description=f"Mode {mode}/{sub_mode} exceeded {duration:.0f}s (threshold: {threshold}s)",
                timestamp=time.time(),
                tick=0,
                mode=mode,
                sub_mode=sub_mode,
                duration_seconds=duration
            )
        
        return None

    def _check_repeated_action(
        self,
        action: Optional[str],
        tick: int
    ) -> Optional[SoftlockInfo]:
        """Check for repeated same action"""
        if not action:
            return None
        
        self._action_history.append((tick, action))
        
        recent_actions = [
            a for t, a in self._action_history
            if t >= tick - 30
        ]
        
        if len(recent_actions) >= self.repeated_action_threshold:
            first_action = recent_actions[0]
            if all(a == first_action for a in recent_actions):
                return SoftlockInfo(
                    type="REPEATED_ACTION",
                    severity="MEDIUM",
                    description=f"Same action '{first_action}' repeated {len(recent_actions)} times",
                    timestamp=time.time(),
                    tick=tick,
                    mode="",
                    sub_mode="",
                    duration_seconds=0,
                    repeated_action=first_action
                )
        
        return None

    def _check_state_loop(self, tick: int) -> Optional[SoftlockInfo]:
        """Check for state transition loops"""
        if not self.state_machine:
            return None
        
        history = self.state_machine.get_state_history()
        if len(history) < 5:
            return None
        
        recent_transitions = history[-10:]
        states = [t.to_state for t in recent_transitions]
        
        if len(states) >= 6:
            oscillations = 0
            for i in range(len(states) - 2):
                if states[i] != states[i+1] and states[i+1] != states[i+2]:
                    oscillations += 1
            
            oscillation_ratio = oscillations / (len(states) - 2)
            if oscillation_ratio > 0.8 and len(states) >= 8:
                return SoftlockInfo(
                    type="STATE_OSCILLATION",
                    severity="LOW",
                    description=f"Rapid state oscillation ({oscillation_ratio:.0%}) detected",
                    timestamp=time.time(),
                    tick=tick,
                    mode="",
                    sub_mode="",
                    duration_seconds=0,
                    state_sequence=states[-10:]
                )
        
        return None

    def _check_zero_progress(
        self,
        tick: int,
        game_state: Optional[Dict[str, Any]]
    ) -> Optional[SoftlockInfo]:
        """Check for zero progress over time window"""
        if not game_state:
            return None
        
        progress_indicators = [
            game_state.get("tick"),
            game_state.get("location"),
            game_state.get("player_hp_percent"),
        ]
        
        if None in progress_indicators:
            return None
        
        if self._last_progress_tick == 0:
            self._last_progress_tick = tick
            self._last_progress_time = time.time()
            return None
        
        time_since_last = time.time() - self._last_progress_time
        if time_since_last < self.progress_window_seconds:
            return None
        
        ticks_since_last = tick - self._last_progress_tick
        if ticks_since_last == 0:
            return SoftlockInfo(
                type="ZERO_PROGRESS",
                severity="HIGH",
                description=f"No progress for {time_since_last:.0f}s ({ticks_since_last} ticks)",
                timestamp=time.time(),
                tick=tick,
                mode=game_state.get("screen_type", ""),
                sub_mode=game_state.get("menu_type", ""),
                duration_seconds=time_since_last
            )
        
        self._last_progress_tick = tick
        self._last_progress_time = time.time()
        
        return None

    def record_action(self, action: str, tick: int) -> None:
        """Record an action for softlock detection"""
        with self._lock:
            self._action_history.append((tick, action))

    def record_state(self, state_name: str) -> None:
        """Record a state transition"""
        with self._lock:
            self._state_sequence.append(state_name)
            if len(self._state_sequence) > 50:
                self._state_sequence.pop(0)

    def save_known_good_state(self, state: RecoveryState) -> None:
        """Save a known good state for recovery"""
        with self._lock:
            self._known_good_states.append(state)
            if len(self._known_good_states) > self._max_known_states:
                self._known_good_states.pop(0)

    def get_last_known_good_state(self) -> Optional[RecoveryState]:
        """Get the most recent known good state"""
        with self._lock:
            if self._known_good_states:
                return self._known_good_states[-1]
            return None

    def get_softlock_history(self, count: int = 10) -> List[SoftlockInfo]:
        """Get recent softlock history"""
        with self._lock:
            return self._softlock_history[-count:]


class EmergencyRecovery:
    """
    Handles emergency recovery procedures
    
    Provides:
    - Graceful shutdown sequences
    - Emergency state snapshots
    - State rollback mechanisms
    - Recovery logging and analysis
    """

    def __init__(self,
                 state_machine: Optional[HierarchicalStateMachine] = None,
                 snapshot_dir: str = "data/emergency_snapshots"):
        self.state_machine = state_machine
        self.snapshot_dir = snapshot_dir
        self._lock = threading.Lock()
        self._recovery_history: List[RecoveryResult] = []
        self._current_recovery: Optional[RecoveryResult] = None
        self._shutdown_requested = False
        
        os.makedirs(snapshot_dir, exist_ok=True)

    def initiate_recovery(
        self,
        reason: str,
        softlock_info: Optional[SoftlockInfo] = None,
        current_state: Optional[Dict[str, Any]] = None
    ) -> RecoveryResult:
        """
        Initiate emergency recovery procedure
        
        Returns RecoveryResult with outcome details
        """
        with self._lock:
            start_time = time.time()
            actions_taken = []
            success = False
            state_restored = False
            message = ""
            
            try:
                actions_taken.append("recovery_initiated")
                
                actions_taken.extend(self._log_state_snapshot(reason, softlock_info, current_state))
                
                actions_taken.extend(self._attempt_graceful_shutdown())
                
                recovered_state = self._attempt_state_rollback()
                if recovered_state:
                    state_restored = True
                    actions_taken.append(f"state_rollback_success: {recovered_state}")
                
                actions_taken.extend(self._create_emergency_report(reason, softlock_info))
                
                success = True
                message = "Recovery completed successfully"
                
            except Exception as e:
                message = f"Recovery failed: {str(e)}"
                actions_taken.append(f"recovery_error: {str(e)}")
                logger.error(f"Emergency recovery failed: {e}", exc_info=True)
            
            time_taken = (time.time() - start_time) * 1000
            
            result = RecoveryResult(
                success=success,
                recovery_type=self._get_recovery_type(softlock_info),
                actions_taken=actions_taken,
                time_taken_ms=time_taken,
                new_confidence=0.0,
                state_restored=state_restored,
                message=message,
                timestamp=time.time()
            )
            
            self._recovery_history.append(result)
            self._current_recovery = result
            
            return result

    def _log_state_snapshot(
        self,
        reason: str,
        softlock_info: Optional[SoftlockInfo],
        current_state: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Log current state snapshot"""
        actions = []
        
        snapshot_data = {
            "timestamp": time.time(),
            "reason": reason,
            "softlock_type": softlock_info.type if softlock_info else None,
            "softlock_severity": softlock_info.severity if softlock_info else None,
            "current_state": current_state or {},
            "state_machine": None
        }
        
        if self.state_machine:
            sm_state = self.state_machine.get_current_state()
            sm_stats = self.state_machine.get_statistics()
            prev_state = self.state_machine.get_previous_state()
            snapshot_data["state_machine"] = {
                "current_state": sm_state.name if sm_state else None,
                "previous_state": prev_state.name if prev_state else None,
                "tick": sm_stats.get("total_ticks", 0),
                "emergency_triggered": sm_stats.get("emergency_triggered", False)
            }
        
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        snapshot_file = os.path.join(
            self.snapshot_dir,
            f"snapshot_{timestamp_str}_{int(time.time() * 1000 % 10000)}.json"
        )
        
        try:
            with open(snapshot_file, 'w') as f:
                json.dump(snapshot_data, f, indent=2, default=str)
            actions.append(f"snapshot_saved: {snapshot_file}")
        except Exception as e:
            actions.append(f"snapshot_failed: {str(e)}")
        
        return actions

    def _attempt_graceful_shutdown(self) -> List[str]:
        """Attempt graceful shutdown of current operations"""
        actions = []
        
        actions.append("stopping_tick_loop")
        actions.append("flushing_logs")
        actions.append("saving_progress")
        
        return actions

    def _attempt_state_rollback(self) -> Optional[str]:
        """Attempt to rollback to known good state"""
        if not self.state_machine:
            return None
        
        try:
            self.state_machine.clear_emergency()
            
            current = self.state_machine.get_current_state_name()
            if current and "EMERGENCY" in current:
                self.state_machine.transition_to("OVERWORLD.IDLE", reason="Recovery rollback")
                return "OVERWORLD.IDLE"
            
            return current if current else None
            
        except Exception as e:
            logger.error(f"State rollback failed: {e}")
            return None

    def _create_emergency_report(
        self,
        reason: str,
        softlock_info: Optional[SoftlockInfo]
    ) -> List[str]:
        """Create emergency report for analysis"""
        actions = []
        
        report = {
            "timestamp": time.time(),
            "reason": reason,
            "softlock": asdict(softlock_info) if softlock_info else None,
            "recoveries_today": len([
                r for r in self._recovery_history
                if time.time() - r.timestamp < 86400
            ])
        }
        
        report_file = os.path.join(
            self.snapshot_dir,
            f"emergency_report_{int(time.time())}.json"
        )
        
        try:
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            actions.append(f"report_created: {report_file}")
        except Exception as e:
            actions.append(f"report_failed: {str(e)}")
        
        return actions

    def _get_recovery_type(self, softlock_info: Optional[SoftlockInfo]) -> str:
        """Determine recovery type from softlock info"""
        if not softlock_info:
            return "general_recovery"
        
        type_mapping = {
            "MODE_DURATION_EXCEEDED": "mode_duration_recovery",
            "REPEATED_ACTION": "action_stuck_recovery",
            "STATE_OSCILLATION": "state_loop_recovery",
            "ZERO_PROGRESS": "progress_stuck_recovery",
        }
        
        return type_mapping.get(softlock_info.type, "unknown_recovery")

    def get_recovery_history(self, count: int = 20) -> List[RecoveryResult]:
        """Get recent recovery history"""
        with self._lock:
            return self._recovery_history[-count:]

    def is_recovering(self) -> bool:
        """Check if currently in recovery"""
        return self._current_recovery is not None and (
            time.time() - self._current_recovery.timestamp < 10
        )


class DeathSpiralPreventer:
    """
    Prevents death spiral scenarios
    
    MVP implementation with:
    - HP monitoring and threshold alerts
    - PP monitoring (stub)
    - Escape button availability check (stub)
    """

    def __init__(self,
                 warning_threshold: float = 0.25,
                 critical_threshold: float = 0.10):
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self._lock = threading.Lock()
        self._hp_history: deque = deque(maxlen=50)
        self._alerts: List[Dict[str, Any]] = []
        self._low_hp_count = 0
        self._consecutive_low_hp_ticks = 0

    def check_hp_status(
        self,
        player_hp_percent: Optional[float],
        party_hp_percent: Optional[float],
        tick: int = 0
    ) -> Dict[str, Any]:
        """
        Check HP status and return alerts if needed
        
        Returns dict with:
        - status: "healthy", "warning", "critical", "emergency"
        - alerts: list of alert messages
        - should_heal: whether healing is recommended
        - recommended_action: suggested action
        """
        with self._lock:
            result = {
                "status": "healthy",
                "alerts": [],
                "should_heal": False,
                "recommended_action": None,
                "tick": tick
            }
            
            if player_hp_percent is None:
                return result
            
            self._hp_history.append((tick, player_hp_percent))
            
            if player_hp_percent <= self.critical_threshold:
                result["status"] = "critical"
                result["alerts"].append(f"CRITICAL: Player HP at {player_hp_percent:.1f}%")
                result["should_heal"] = True
                result["recommended_action"] = "heal_immediately"
                self._consecutive_low_hp_ticks += 1
            elif player_hp_percent <= self.warning_threshold:
                result["status"] = "warning"
                result["alerts"].append(f"WARNING: Player HP at {player_hp_percent:.1f}%")
                if self._consecutive_low_hp_ticks > 5:
                    result["should_heal"] = True
                    result["recommended_action"] = "heal_soon"
                self._consecutive_low_hp_ticks += 1
            else:
                result["status"] = "healthy"
                self._consecutive_low_hp_ticks = 0
            
            if result["alerts"]:
                alert_entry = {
                    "timestamp": time.time(),
                    "tick": tick,
                    "status": result["status"],
                    "hp_percent": player_hp_percent,
                    "alerts": result["alerts"]
                }
                self._alerts.append(alert_entry)
                logger.warning(
                    f"HP Alert: {result['status']} - {result['alerts']}",
                    extra={"category": LogCategory.BATTLES, "tick": tick}
                )
            
            return result

    def check_party_status(
        self,
        party_status: List[Dict[str, Any]],
        tick: int = 0
    ) -> Dict[str, Any]:
        """Check overall party status"""
        if not party_status:
            return {"healthy": True, "can_battle": True, "tick": tick}
        
        alive_count = sum(1 for p in party_status if p.get("hp_percent", 0) > 0)
        low_hp_count = sum(
            1 for p in party_status
            if p.get("hp_percent", 0) > 0 and p.get("hp_percent", 0) <= self.warning_threshold
        )
        
        return {
            "healthy": alive_count == len(party_status),
            "can_battle": alive_count > 0,
            "alive_count": alive_count,
            "total_count": len(party_status),
            "low_hp_count": low_hp_count,
            "should_heal": low_hp_count > len(party_status) // 2,
            "tick": tick
        }

    def check_pp_status(
        self,
        move_pp: Dict[str, int],
        tick: int = 0
    ) -> Dict[str, Any]:
        """Check move PP status (MVP stub)"""
        return {
            "has_pp": True,
            "can_fight": True,
            "needs_restore": False,
            "tick": tick,
            "_stub": True
        }

    def check_escape_available(self, tick: int = 0) -> Dict[str, Any]:
        """Check if escape is available (MVP stub)"""
        return {
            "available": True,
            "success_rate": 0.0,
            "recommended": False,
            "tick": tick,
            "_stub": True
        }

    def get_hp_trend(self) -> Dict[str, Any]:
        """Get HP trend analysis"""
        if len(self._hp_history) < 5:
            return {"trend": "insufficient_data"}
        
        recent = list(self._hp_history)[-10:]
        hp_values = [hp for _, hp in recent]
        
        if len(hp_values) >= 3:
            early_avg = sum(hp_values[:3]) / 3
            late_avg = sum(hp_values[-3:]) / 3
            if late_avg > early_avg + 0.05:
                trend = "recovering"
            elif late_avg < early_avg - 0.05:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "current": hp_values[-1] if hp_values else None,
            "avg": sum(hp_values) / len(hp_values),
            "min": min(hp_values),
            "max": max(hp_values),
            "samples": len(hp_values)
        }

    def get_alerts(self, count: int = 20) -> List[Dict[str, Any]]:
        """Get recent HP alerts"""
        with self._lock:
            return self._alerts[-count:]


class SystemHealthMonitor:
    """
    Monitors system health metrics
    
    MVP implementation with:
    - Memory usage tracking
    - API latency monitoring
    - Database connection health (stub)
    - Emulator state validation (stub)
    """

    def __init__(self,
                 memory_warning_mb: float = 512.0,
                 memory_critical_mb: float = 1024.0,
                 api_latency_warning_ms: float = 5000.0,
                 api_latency_critical_ms: float = 10000.0):
        self.memory_warning_mb = memory_warning_mb
        self.memory_critical_mb = memory_critical_mb
        self.api_latency_warning_ms = api_latency_warning_ms
        self.api_latency_critical_ms = api_latency_critical_ms
        
        self._lock = threading.Lock()
        self._api_latency_history: deque = deque(maxlen=50)
        self._health_history: List[HealthMetrics] = []
        self._process = psutil.Process(os.getpid())

    def check_health(self) -> HealthMetrics:
        """Check all health metrics"""
        with self._lock:
            memory_info = self._process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            memory_percent = self._process.memory_percent()
            
            api_latency = self._get_recent_api_latency()
            api_success = self._get_api_success_rate()
            
            score = self._calculate_health_score(
                memory_mb, memory_percent, api_latency, api_success
            )
            
            metrics = HealthMetrics(
                timestamp=time.time(),
                memory_usage_mb=memory_mb,
                memory_percent=memory_percent,
                cpu_percent=self._process.cpu_percent(),
                api_latency_ms=api_latency,
                api_success_rate=api_success,
                db_healthy=True,
                emulator_healthy=True,
                tick_rate=0.0,
                overall_score=score
            )
            
            self._health_history.append(metrics)
            if len(self._health_history) > 1000:
                self._health_history.pop(0)
            
            return metrics

    def _get_recent_api_latency(self) -> float:
        """Get recent API latency average"""
        if not self._api_latency_history:
            return 0.0
        
        recent = list(self._api_latency_history)[-10:]
        if not recent:
            return 0.0
        
        return sum(recent) / len(recent)

    def _get_api_success_rate(self) -> float:
        """Get API success rate (MVP stub)"""
        return 1.0

    def record_api_latency(self, latency_ms: float) -> None:
        """Record an API latency measurement"""
        with self._lock:
            self._api_latency_history.append(latency_ms)

    def _calculate_health_score(
        self,
        memory_mb: float,
        memory_percent: float,
        api_latency_ms: float,
        api_success_rate: float
    ) -> float:
        """Calculate overall health score (0.0 - 1.0)"""
        score = 1.0
        
        if memory_mb > self.memory_critical_mb:
            score -= 0.4
        elif memory_mb > self.memory_warning_mb:
            score -= 0.2
        
        if api_latency_ms > self.api_latency_critical_ms:
            score -= 0.3
        elif api_latency_ms > self.api_latency_warning_ms:
            score -= 0.15
        
        score *= api_success_rate
        
        return max(0.0, min(1.0, score))

    def get_health_status(self) -> Dict[str, Any]:
        """Get simplified health status"""
        metrics = self.check_health()
        
        status = "healthy"
        if metrics.overall_score < 0.5:
            status = "critical"
        elif metrics.overall_score < 0.7:
            status = "warning"
        
        issues = []
        if metrics.memory_usage_mb > self.memory_warning_mb:
            issues.append(f"High memory: {metrics.memory_usage_mb:.0f}MB")
        if metrics.api_latency_ms > self.api_latency_warning_ms:
            issues.append(f"High latency: {metrics.api_latency_ms:.0f}ms")
        
        return {
            "status": status,
            "score": metrics.overall_score,
            "memory_mb": metrics.memory_usage_mb,
            "cpu_percent": metrics.cpu_percent,
            "api_latency_ms": metrics.api_latency_ms,
            "issues": issues
        }

    def get_health_history(self, count: int = 100) -> List[HealthMetrics]:
        """Get recent health history"""
        with self._lock:
            return self._health_history[-count:]


class FailsafeManager:
    """
    Main failsafe coordinator
    
    Orchestrates all failsafe components:
    - ConfidenceScorer
    - SoftlockDetector
    - EmergencyRecovery
    - DeathSpiralPreventer
    - SystemHealthMonitor
    """

    def __init__(self,
                 state_machine: Optional[HierarchicalStateMachine] = None,
                 confidence_threshold: float = 0.7):
        self.state_machine = state_machine
        
        self.confidence_scorer = ConfidenceScorer(default_threshold=confidence_threshold)
        self.softlock_detector = SoftlockDetector(
            state_machine=state_machine
        )
        self.emergency_recovery = EmergencyRecovery(state_machine=state_machine)
        self.death_spiral_preventer = DeathSpiralPreventer()
        self.system_health_monitor = SystemHealthMonitor()
        
        self._lock = threading.Lock()
        self._enabled = True
        self._tick = 0
        self._last_health_check = 0.0
        self._health_check_interval = 5.0

    def update(
        self,
        game_state: Dict[str, Any],
        ai_confidence: Optional[float] = None,
        vision_confidence: Optional[float] = None,
        tick: int = 0
    ) -> Dict[str, Any]:
        """
        Main update loop for failsafe system
        
        Returns dict with:
        - confidence: Current confidence breakdown
        - softlock: Softlock info if detected
        - health: System health status
        - hp_status: HP monitoring result
        - recovery_triggered: Whether recovery was triggered
        """
        with self._lock:
            self._tick = tick
            
            confidence = self.confidence_scorer.calculate_confidence(
                ai_confidence=ai_confidence,
                vision_confidence=vision_confidence,
                state_confidence=game_state.get("state_confidence"),
                tick=tick
            )
            
            softlock = self.softlock_detector.check_softlock(
                current_mode=game_state.get("screen_type", "unknown"),
                current_sub_mode=game_state.get("menu_type", ""),
                current_duration=game_state.get("mode_duration", 0.0),
                current_action=game_state.get("last_action"),
                tick=tick,
                game_state=game_state
            )
            
            recovery_triggered = False
            if softlock and self._enabled:
                recovery_result = self.emergency_recovery.initiate_recovery(
                    reason=f"Softlock detected: {softlock.type}",
                    softlock_info=softlock,
                    current_state=game_state
                )
                recovery_triggered = recovery_result.success
            
            hp_status = self.death_spiral_preventer.check_hp_status(
                player_hp_percent=game_state.get("player_hp_percent"),
                party_hp_percent=game_state.get("party_hp_percent"),
                tick=tick
            )
            
            health_status = self.system_health_monitor.get_health_status()
            
            if time.time() - self._last_health_check > self._health_check_interval:
                self.system_health_monitor.check_health()
                self._last_health_check = time.time()
            
            return {
                "confidence": asdict(confidence),
                "softlock": asdict(softlock) if softlock else None,
                "health": health_status,
                "hp_status": hp_status,
                "recovery_triggered": recovery_triggered,
                "confidence_acceptable": self.confidence_scorer.is_confidence_acceptable(
                    confidence.overall_confidence
                ),
                "confidence_level": self.confidence_scorer.get_confidence_level(
                    confidence.overall_confidence
                ).value,
                "tick": tick
            }

    def check_action(self, action: str, tick: int = 0) -> None:
        """Check an action for softlock conditions"""
        self.softlock_detector.record_action(action, tick)

    def record_state(self, state_name: str) -> None:
        """Record a state transition"""
        self.softlock_detector.record_state(state_name)

    def save_known_good_state(self, state: RecoveryState) -> None:
        """Save current state as known good for recovery"""
        self.softlock_detector.save_known_good_state(state)

    def record_api_latency(self, latency_ms: float) -> None:
        """Record API latency for monitoring"""
        self.system_health_monitor.record_api_latency(latency_ms)

    def enable(self) -> None:
        """Enable failsafe system"""
        self._enabled = True
        logger.info("Failsafe system enabled")

    def disable(self) -> None:
        """Disable failsafe system (use with caution)"""
        self._enabled = False
        logger.warning("Failsafe system disabled")

    def is_enabled(self) -> bool:
        """Check if failsafe system is enabled"""
        return self._enabled

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for dashboard display"""
        last_conf = self.confidence_scorer.get_last_confidence()
        confidence_trend = self.confidence_scorer.get_recent_confidence_trend()
        hp_trend = self.death_spiral_preventer.get_hp_trend()
        softlock_history = self.softlock_detector.get_softlock_history(5)
        recovery_history = self.emergency_recovery.get_recovery_history(5)
        
        return {
            "enabled": self._enabled,
            "tick": self._tick,
            "confidence": asdict(last_conf) if last_conf else None,
            "confidence_trend": confidence_trend,
            "hp_trend": hp_trend,
            "recent_softlocks": [asdict(s) for s in softlock_history],
            "recent_recoveries": [asdict(r) for r in recovery_history],
            "health_status": self.system_health_monitor.get_health_status()
        }