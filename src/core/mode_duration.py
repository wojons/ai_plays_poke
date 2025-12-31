"""
Mode Duration Tracking System for PTP-01X Pokemon AI

Provides comprehensive mode duration tracking, learned duration profiling,
statistical anomaly detection, and adaptive break-out mechanisms.
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple, DefaultDict, cast
from collections import defaultdict
from enum import Enum
import threading


class GameMode(Enum):
    OVERWORLD = "OVERWORLD"
    BATTLE = "BATTLE"
    DIALOG = "DIALOG"
    MENU = "MENU"
    CUTSCENE = "CUTSCENE"
    TRANSITION = "TRANSITION"


class OverworldSubMode(Enum):
    NAVIGATION = "NAVIGATION"
    INTERACTION = "INTERACTION"
    PC = "PC"


class BattleSubMode(Enum):
    WILD_EASY = "WILD_EASY"
    WILD_NORMAL = "WILD_NORMAL"
    WILD_HARD = "WILD_HARD"
    TRAINER = "TRAINER"
    GYM_LEADER = "GYM_LEADER"
    ELITE_FOUR = "ELITE_FOUR"


class DialogSubMode(Enum):
    NPC_SHORT = "NPC_SHORT"
    NPC_LONG = "NPC_LONG"
    TUTORIAL = "TUTORIAL"
    QUEST = "QUEST"
    SHOP = "SHOP"


class MenuSubMode(Enum):
    PAUSE = "PAUSE"
    POKEMON = "POKEMON"
    BAG = "BAG"
    SAVE = "SAVE"


class CutsceneSubMode(Enum):
    INTRO = "INTRO"
    EVOLUTION = "EVOLUTION"
    VICTORY = "VICTORY"


class AnomalySeverity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EscalationTier(Enum):
    NONE = "NONE"
    ENHANCED_MONITORING = "ENHANCED_MONITORING"
    PLAN_SIMPLIFICATION = "PLAN_SIMPLIFICATION"
    EMERGENCY_PROTOCOL = "EMERGENCY_PROTOCOL"
    RESET_CONDITION = "RESET_CONDITION"


class BreakoutStrategy(Enum):
    STANDARD = "break_out_standard"
    AGGRESSIVE = "break_out_aggressive"
    IMMEDIATE = "break_out_immediate"
    FORCE = "force_break_out"
    CHECK_PROGRESS = "check_progress"
    INCREASE_MONITORING = "increase_monitoring"


@dataclass
class ModeClassification:
    mode: str
    sub_mode: str
    confidence: float
    timestamp: float
    tick: int
    state_snapshot: Optional[Dict[str, Any]] = None


@dataclass
class ModeEntry:
    mode: str
    sub_mode: str
    entry_time: float
    entry_tick: int
    context: Dict[str, Any] = field(default_factory=dict)
    state_snapshot: Optional[Dict[str, Any]] = None


@dataclass
class ModeExit:
    mode: str
    sub_mode: str
    exit_time: float
    exit_tick: int
    duration: float
    cumulative_session: float
    cumulative_hour: float
    cumulative_day: float
    exit_reason: str


@dataclass
class ModeDurationProfile:
    mode: str
    sub_mode: str
    sample_count: int
    mean_duration: float
    std_duration: float
    min_duration: float
    max_duration: float
    p50_duration: float
    p75_duration: float
    p95_duration: float
    p99_duration: float
    last_updated: float
    trend: str
    trend_slope: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModeDurationProfile':
        return cls(**data)


@dataclass
class Anomaly:
    type: str
    severity: str
    description: str
    value: float
    threshold: float
    deviation: Optional[float] = None
    window: Optional[str] = None
    recommended_action: str = "log_warning"


@dataclass
class BreakoutResult:
    success: bool
    strategy: str
    action: str
    attempts: int
    mode: str = ""
    sub_mode: str = ""


@dataclass
class ResponsePlan:
    actions: List[str]
    confidence_impact: int
    escalation_tier: str
    primary_anomaly: Optional[Anomaly] = None
    all_anomalies: List[Anomaly] = field(default_factory=list)


class ModeClassifier:
    def __init__(self, state_machine: Optional[Any] = None):
        self.state_machine = state_machine
        self._mode_cache: Optional[Tuple[ModeClassification, float]] = None
        self._cache_ttl = 0.1

    def classify_mode(self, current_state: Dict[str, Any], tick: int = 0) -> ModeClassification:
        current_time = time.time()
        if self._mode_cache and current_time - self._mode_cache[1] < self._cache_ttl:
            return self._mode_cache[0]

        base_mode = self._get_base_mode(current_state)
        visual_mode = self._get_visual_mode(current_state)
        text_context = self._get_text_context(current_state)
        sub_mode = self._determine_sub_mode(base_mode, visual_mode, text_context, current_state)
        confidence = self._calculate_confidence(base_mode, visual_mode, text_context)

        classification = ModeClassification(
            mode=base_mode, sub_mode=sub_mode, confidence=confidence,
            timestamp=current_time, tick=tick,
            state_snapshot=current_state.copy() if current_state else None
        )
        self._mode_cache = (classification, current_time)
        return classification

    def _get_base_mode(self, state: Dict[str, Any]) -> str:
        if state.get("is_battle", False):
            return GameMode.BATTLE.value
        elif state.get("has_dialog", False):
            return GameMode.DIALOG.value
        elif state.get("is_menu", False):
            return GameMode.MENU.value
        elif state.get("screen_type") == "cutscene":
            return GameMode.CUTSCENE.value
        elif state.get("screen_type") == "transition":
            return GameMode.TRANSITION.value
        return GameMode.OVERWORLD.value

    def _get_visual_mode(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "screen_type": state.get("screen_type", "unknown"),
            "menu_type": state.get("menu_type"),
            "near_pc": state.get("near_pc", 0),
            "near_npc": state.get("near_npc", 0),
            "enemy_level": state.get("enemy_level", 0),
            "party_level": state.get("party_level", 0),
            "dialog_text": state.get("dialog_text", ""),
        }

    def _get_text_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        dialog_text = state.get("dialog_text", "")
        return {
            "dialog_text": dialog_text,
            "line_count": dialog_text.count("\n") + 1 if dialog_text else 0,
            "is_tutorial": "tutorial" in dialog_text.lower() if dialog_text else False,
            "is_quest": "quest" in dialog_text.lower() if dialog_text else False,
            "is_shop": "shop" in dialog_text.lower() or "buy" in dialog_text.lower() if dialog_text else False,
            "trainer_name": state.get("trainer_name"),
            "gym_leader": state.get("gym_leader", False),
            "elite_four": state.get("elite_four", False),
        }

    def _determine_sub_mode(self, base_mode: str, visual_mode: Dict[str, Any],
                           text_context: Dict[str, Any], state: Dict[str, Any]) -> str:
        if base_mode == GameMode.BATTLE.value:
            return self._classify_battle_sub_mode(visual_mode, text_context)
        elif base_mode == GameMode.DIALOG.value:
            return self._classify_dialog_sub_mode(text_context)
        elif base_mode == GameMode.OVERWORLD.value:
            return self._classify_overworld_sub_mode(visual_mode)
        elif base_mode == GameMode.MENU.value:
            return self._classify_menu_sub_mode(visual_mode)
        elif base_mode == GameMode.CUTSCENE.value:
            return self._classify_cutscene_sub_mode(visual_mode, text_context)
        return f"{base_mode}_GENERIC"

    def _classify_battle_sub_mode(self, visual_mode: Dict[str, Any],
                                  text_context: Dict[str, Any]) -> str:
        if text_context.get("gym_leader"):
            return BattleSubMode.GYM_LEADER.value
        elif text_context.get("elite_four"):
            return BattleSubMode.ELITE_FOUR.value
        elif text_context.get("trainer_name"):
            return BattleSubMode.TRAINER.value
        enemy_level = visual_mode.get("enemy_level", 0)
        party_level = visual_mode.get("party_level", 0)
        if enemy_level == 0 or party_level == 0:
            return BattleSubMode.WILD_NORMAL.value
        elif enemy_level <= party_level - 5:
            return BattleSubMode.WILD_EASY.value
        elif enemy_level >= party_level + 5:
            return BattleSubMode.WILD_HARD.value
        return BattleSubMode.WILD_NORMAL.value

    def _classify_dialog_sub_mode(self, text_context: Dict[str, Any]) -> str:
        if text_context.get("is_tutorial"):
            return DialogSubMode.TUTORIAL.value
        elif text_context.get("is_quest"):
            return DialogSubMode.QUEST.value
        elif text_context.get("is_shop"):
            return DialogSubMode.SHOP.value
        elif text_context.get("line_count", 0) > 10:
            return DialogSubMode.NPC_LONG.value
        return DialogSubMode.NPC_SHORT.value

    def _classify_overworld_sub_mode(self, visual_mode: Dict[str, Any]) -> str:
        if visual_mode.get("near_pc"):
            return OverworldSubMode.PC.value
        elif visual_mode.get("near_npc"):
            return OverworldSubMode.INTERACTION.value
        return OverworldSubMode.NAVIGATION.value

    def _classify_menu_sub_mode(self, visual_mode: Dict[str, Any]) -> str:
        menu_type = visual_mode.get("menu_type", "").lower()
        if menu_type == "pokemon":
            return MenuSubMode.POKEMON.value
        elif menu_type == "bag":
            return MenuSubMode.BAG.value
        elif menu_type == "save":
            return MenuSubMode.SAVE.value
        return MenuSubMode.PAUSE.value

    def _classify_cutscene_sub_mode(self, visual_mode: Dict[str, Any],
                                    text_context: Dict[str, Any]) -> str:
        dialog_text = (text_context.get("dialog_text", "") or visual_mode.get("dialog_text", "")).lower()
        if "evolution" in dialog_text or "evolving" in dialog_text:
            return CutsceneSubMode.EVOLUTION.value
        elif "victory" in dialog_text:
            return CutsceneSubMode.VICTORY.value
        return CutsceneSubMode.INTRO.value

    def _calculate_confidence(self, base_mode: str, visual_mode: Dict[str, Any],
                              text_context: Dict[str, Any]) -> float:
        confidence = 0.7
        if visual_mode.get("screen_type"):
            confidence += 0.1
        if text_context.get("line_count", 0) > 0:
            confidence += 0.1
        if text_context.get("trainer_name"):
            confidence += 0.05
        return min(0.99, confidence)


class DurationTracker:
    def __init__(self):
        self.current_mode: Optional[ModeEntry] = None
        self._last_mode_key: Optional[str] = None
        self.mode_history: List[ModeExit] = []
        self.cumulative_stats: Dict[str, DefaultDict[str, float]] = {
            "session": defaultdict(float), "hour": defaultdict(float), "day": defaultdict(float),
        }
        self.session_start: float = time.time()
        self.hour_start: float = time.time()
        self.day_start: float = time.time()
        self.mode_sequence: List[str] = []
        self._lock = threading.Lock()

    def enter_mode(self, mode: str, sub_mode: str, context: Optional[Dict[str, Any]] = None,
                   state_snapshot: Optional[Dict[str, Any]] = None, tick: int = 0) -> Optional[ModeExit]:
        with self._lock:
            interrupted_exit = None
            if self.current_mode:
                prev_mode = self.current_mode
                prev_mode_key = f"{prev_mode.mode}/{prev_mode.sub_mode}"
                exit_time = time.time()
                duration = exit_time - prev_mode.entry_time
                self._last_mode_key = prev_mode_key
                self.cumulative_stats["session"][prev_mode_key] += duration
                self.cumulative_stats["hour"][prev_mode_key] += duration
                self.cumulative_stats["day"][prev_mode_key] += duration
                self._check_time_windows()
                interrupted_exit = ModeExit(
                    mode=prev_mode.mode, sub_mode=prev_mode.sub_mode,
                    exit_time=exit_time, exit_tick=tick, duration=duration,
                    cumulative_session=self.cumulative_stats["session"][prev_mode_key],
                    cumulative_hour=self.cumulative_stats["hour"][prev_mode_key],
                    cumulative_day=self.cumulative_stats["day"][prev_mode_key], exit_reason="interrupt",
                )
                self.mode_history.append(interrupted_exit)
                self._prune_history()
            self.current_mode = ModeEntry(
                mode=mode, sub_mode=sub_mode, entry_time=time.time(), entry_tick=tick,
                context=context or {}, state_snapshot=state_snapshot,
            )
            mode_key = f"{mode}/{sub_mode}"
            self.mode_sequence.append(mode_key)
            if len(self.mode_sequence) > 100:
                self.mode_sequence.pop(0)
            return interrupted_exit

    def exit_mode(self, reason: str = "natural", tick: int = 0) -> Optional[ModeExit]:
        with self._lock:
            if not self.current_mode:
                return None
            exit_time = time.time()
            duration = exit_time - self.current_mode.entry_time
            exit_tick = tick
            mode_key = f"{self.current_mode.mode}/{self.current_mode.sub_mode}"
            self._last_mode_key = mode_key
            self.cumulative_stats["session"][mode_key] += duration
            self.cumulative_stats["hour"][mode_key] += duration
            self.cumulative_stats["day"][mode_key] += duration
            self._check_time_windows()
            mode_exit = ModeExit(
                mode=self.current_mode.mode, sub_mode=self.current_mode.sub_mode,
                exit_time=exit_time, exit_tick=exit_tick, duration=duration,
                cumulative_session=self.cumulative_stats["session"][mode_key],
                cumulative_hour=self.cumulative_stats["hour"][mode_key],
                cumulative_day=self.cumulative_stats["day"][mode_key], exit_reason=reason,
            )
            self.mode_history.append(mode_exit)
            self._prune_history()
            self.current_mode = None
            return mode_exit

    def get_current_duration(self) -> float:
        if not self.current_mode:
            return 0.0
        return time.time() - self.current_mode.entry_time

    def get_current_cumulative(self, window: str = "session", mode: Optional[str] = None, sub_mode: Optional[str] = None) -> float:
        if mode and sub_mode:
            mode_key = f"{mode}/{sub_mode}"
            return cast(Dict[str, float], self.cumulative_stats.get(window, {})).get(mode_key, 0.0)
        if self.current_mode:
            mode_key = f"{self.current_mode.mode}/{self.current_mode.sub_mode}"
            return cast(Dict[str, float], self.cumulative_stats.get(window, {})).get(mode_key, 0.0)
        if self._last_mode_key:
            return cast(Dict[str, float], self.cumulative_stats.get(window, {})).get(self._last_mode_key, 0.0)
        return 0.0

    def get_mode_statistics(self, mode: str, sub_mode: str) -> Dict[str, Any]:
        relevant_exits = [e for e in self.mode_history if e.mode == mode and e.sub_mode == sub_mode]
        if not relevant_exits:
            return {"sample_count": 0}
        durations = [e.duration for e in relevant_exits]
        return {
            "sample_count": len(durations), "mean": sum(durations) / len(durations) if durations else 0,
            "min": min(durations) if durations else 0, "max": max(durations) if durations else 0,
            "total": sum(durations),
        }

    def _check_time_windows(self) -> None:
        current_time = time.time()
        if current_time - self.hour_start > 3600:
            self.cumulative_stats["hour"].clear()
            self.hour_start = current_time
        if current_time - self.day_start > 86400:
            self.cumulative_stats["day"].clear()
            self.day_start = current_time

    def _prune_history(self) -> None:
        cutoff_time = time.time() - 86400
        self.mode_history = [e for e in self.mode_history if e.exit_time > cutoff_time]

    def reset_session(self) -> None:
        with self._lock:
            self.session_start = time.time()
            self.cumulative_stats["session"].clear()
            self.mode_history.clear()
            self.mode_sequence.clear()


class DurationProfileLearner:
    def __init__(self, alpha: float = 0.3, min_samples: int = 5, outlier_threshold: float = 3.0):
        self.profiles: Dict[str, ModeDurationProfile] = {}
        self.alpha = alpha
        self.min_samples = min_samples
        self.outlier_threshold = outlier_threshold
        self._lock = threading.Lock()

    def update_profile(self, mode: str, sub_mode: str, duration: float) -> None:
        with self._lock:
            key = f"{mode}/{sub_mode}"
            if key not in self.profiles:
                self.profiles[key] = ModeDurationProfile(
                    mode=mode, sub_mode=sub_mode, sample_count=0, mean_duration=duration, std_duration=0,
                    min_duration=duration, max_duration=duration, p50_duration=duration, p75_duration=duration,
                    p95_duration=duration, p99_duration=duration, last_updated=time.time(), trend="stable", trend_slope=0,
                )
            profile = self.profiles[key]
            if profile.sample_count > self.min_samples:
                z_score = abs(duration - profile.mean_duration) / max(profile.std_duration, 0.001)
                if z_score > self.outlier_threshold:
                    return
            profile.sample_count += 1
            profile.last_updated = time.time()
            if profile.sample_count == 1:
                profile.mean_duration = duration
                profile.std_duration = 0
                profile.min_duration = duration
                profile.max_duration = duration
            else:
                old_mean = profile.mean_duration
                profile.mean_duration = old_mean + self.alpha * (duration - old_mean)
                if profile.std_duration == 0:
                    profile.std_duration = abs(duration - old_mean)
                else:
                    profile.std_duration = (1 - self.alpha) * profile.std_duration + self.alpha * abs(duration - old_mean)
                profile.min_duration = min(profile.min_duration, duration)
                profile.max_duration = max(profile.max_duration, duration)
            profile = self._update_percentiles(profile)
            profile = self._update_trend(profile)

    def _update_percentiles(self, profile: ModeDurationProfile) -> ModeDurationProfile:
        profile.p50_duration = profile.mean_duration
        profile.p75_duration = profile.mean_duration + 0.67 * max(profile.std_duration, 0.001)
        profile.p95_duration = profile.mean_duration + 1.645 * max(profile.std_duration, 0.001)
        profile.p99_duration = profile.mean_duration + 2.326 * max(profile.std_duration, 0.001)
        return profile

    def _update_trend(self, profile: ModeDurationProfile) -> ModeDurationProfile:
        if profile.sample_count < 10:
            profile.trend = "insufficient_data"
            profile.trend_slope = 0
            return profile
        recent_window = 3600
        cutoff = time.time() - recent_window
        recent_samples = [e.duration for e in DurationTracker().mode_history
                         if e.exit_time > cutoff and e.mode == profile.mode and e.sub_mode == profile.sub_mode]
        if len(recent_samples) < 5:
            profile.trend = "insufficient_data"
            profile.trend_slope = 0
            return profile
        recent_mean = sum(recent_samples) / len(recent_samples)
        trend_slope = recent_mean - profile.mean_duration
        if trend_slope > profile.std_duration * 0.5:
            profile.trend = "increasing"
        elif trend_slope < -profile.std_duration * 0.5:
            profile.trend = "decreasing"
        else:
            profile.trend = "stable"
        profile.trend_slope = trend_slope
        return profile

    def get_profile(self, mode: str, sub_mode: str) -> Optional[ModeDurationProfile]:
        return self.profiles.get(f"{mode}/{sub_mode}")

    def get_thresholds(self, mode: str, sub_mode: str) -> Dict[str, float]:
        profile = self.get_profile(mode, sub_mode)
        if not profile or profile.sample_count < self.min_samples:
            return self._get_default_thresholds(mode, sub_mode)
        return {"warning": profile.p75_duration, "critical": profile.p95_duration, "emergency": profile.p99_duration}

    def _get_default_thresholds(self, mode: str, sub_mode: str) -> Dict[str, float]:
        defaults = {
            f"{GameMode.BATTLE.value}/WILD_EASY": {"warning": 300, "critical": 600, "emergency": 1200},
            f"{GameMode.BATTLE.value}/WILD_NORMAL": {"warning": 300, "critical": 600, "emergency": 1200},
            f"{GameMode.BATTLE.value}/WILD_HARD": {"warning": 600, "critical": 1200, "emergency": 2400},
            f"{GameMode.BATTLE.value}/TRAINER": {"warning": 600, "critical": 1200, "emergency": 2400},
            f"{GameMode.BATTLE.value}/GYM_LEADER": {"warning": 900, "critical": 1800, "emergency": 3600},
            f"{GameMode.BATTLE.value}/ELITE_FOUR": {"warning": 1800, "critical": 3600, "emergency": 7200},
            f"{GameMode.DIALOG.value}/NPC_SHORT": {"warning": 60, "critical": 180, "emergency": 300},
            f"{GameMode.DIALOG.value}/NPC_LONG": {"warning": 600, "critical": 1200, "emergency": 2400},
            f"{GameMode.DIALOG.value}/TUTORIAL": {"warning": 1800, "critical": 3600, "emergency": 7200},
            f"{GameMode.DIALOG.value}/QUEST": {"warning": 900, "critical": 1800, "emergency": 3600},
            f"{GameMode.DIALOG.value}/SHOP": {"warning": 300, "critical": 600, "emergency": 1200},
            f"{GameMode.OVERWORLD.value}/NAVIGATION": {"warning": 300, "critical": 600, "emergency": 1200},
            f"{GameMode.OVERWORLD.value}/INTERACTION": {"warning": 120, "critical": 300, "emergency": 600},
            f"{GameMode.OVERWORLD.value}/PC": {"warning": 180, "critical": 300, "emergency": 600},
            f"{GameMode.MENU.value}/PAUSE": {"warning": 120, "critical": 300, "emergency": 600},
            f"{GameMode.MENU.value}/POKEMON": {"warning": 300, "critical": 600, "emergency": 1200},
            f"{GameMode.MENU.value}/BAG": {"warning": 120, "critical": 300, "emergency": 600},
            f"{GameMode.CUTSCENE.value}/INTRO": {"warning": 600, "critical": 1200, "emergency": 2400},
            f"{GameMode.CUTSCENE.value}/EVOLUTION": {"warning": 180, "critical": 300, "emergency": 600},
            f"{GameMode.CUTSCENE.value}/VICTORY": {"warning": 60, "critical": 120, "emergency": 180},
        }
        key = f"{mode}/{sub_mode}"
        return defaults.get(key, {"warning": 120, "critical": 300, "emergency": 600})  # type: ignore[return-value]


class DurationProfileStore:
    def __init__(self, storage_path: str = "data/duration_profiles.json"):
        self.storage_path = storage_path
        self._ensure_storage_exists()

    def _ensure_storage_exists(self) -> None:
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)

    def save_profile(self, profile: ModeDurationProfile) -> None:
        profiles = self._load_all()
        key = f"{profile.mode}/{profile.sub_mode}"
        profiles[key] = profile.to_dict()
        self._save_all(profiles)

    def _load_all(self) -> Dict[str, Any]:
        if not os.path.exists(self.storage_path):
            return {}
        try:
            with open(self.storage_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_all(self, profiles: Dict[str, Any]) -> None:
        with open(self.storage_path, "w") as f:
            json.dump(profiles, f, indent=2)

    def load_profiles(self) -> Dict[str, ModeDurationProfile]:
        profiles = {}
        data = self._load_all()
        for key, profile_data in data.items():
            mode, sub_mode = key.split("/")
            profiles[key] = ModeDurationProfile.from_dict(profile_data)
        return profiles


class AnomalyDetector:
    def __init__(self, profile_learner: DurationProfileLearner):
        self.profile_learner = profile_learner
        self.cumulative_thresholds = {
            "session": {"warning": 1800, "critical": 3600, "emergency": 7200},
            "hour": {"warning": 900, "critical": 1800, "emergency": 3600},
            "day": {"warning": 7200, "critical": 14400, "emergency": 28800},
        }

    def detect_anomalies(self, current_mode: str, current_sub_mode: str, current_duration: float,
                         cumulative_session: float, cumulative_hour: float, cumulative_day: float,
                         mode_sequence: List[str]) -> List[Anomaly]:
        anomalies = []
        duration_anomaly = self._detect_duration_anomaly(current_mode, current_sub_mode, current_duration)
        if duration_anomaly:
            anomalies.append(duration_anomaly)
        cumulative_anomalies = self._detect_cumulative_anomalies(
            current_mode, current_sub_mode, cumulative_session, cumulative_hour, cumulative_day)
        anomalies.extend(cumulative_anomalies)
        sequence_anomaly = self._detect_sequence_anomaly(mode_sequence)
        if sequence_anomaly:
            anomalies.append(sequence_anomaly)
        trend_anomaly = self._detect_trend_anomaly(current_mode, current_sub_mode)
        if trend_anomaly:
            anomalies.append(trend_anomaly)
        return anomalies

    def _detect_duration_anomaly(self, mode: str, sub_mode: str, duration: float) -> Optional[Anomaly]:
        profile = self.profile_learner.get_profile(mode, sub_mode)
        thresholds = self.profile_learner.get_thresholds(mode, sub_mode)
        if not profile or profile.sample_count < 5:
            if duration > thresholds["emergency"]:
                return Anomaly(
                    type="DURATION_UNKNOWN_MODE", severity=AnomalySeverity.HIGH.value,
                    description=f"Duration {duration:.0f}s exceeds emergency threshold {thresholds['emergency']}s",
                    value=duration, threshold=thresholds["emergency"], recommended_action="break_out_aggressive")
            return None
        if profile.std_duration > 0:
            z_score = (duration - profile.mean_duration) / profile.std_duration
        else:
            z_score = 0 if duration <= profile.mean_duration else float('inf')
        if z_score > 4.0:
            return Anomaly(
                type="DURATION_EXTREME", severity=AnomalySeverity.CRITICAL.value,
                description=f"Duration {duration:.0f}s is {z_score:.1f}σ above mean {profile.mean_duration:.0f}s",
                value=duration, threshold=thresholds["emergency"], deviation=z_score,
                recommended_action="break_out_immediate")
        elif z_score > 3.0:
            return Anomaly(
                type="DURATION_HIGH", severity=AnomalySeverity.HIGH.value,
                description=f"Duration {duration:.0f}s is {z_score:.1f}σ above mean",
                value=duration, threshold=thresholds["critical"], deviation=z_score,
                recommended_action="break_out_aggressive")
        elif duration > thresholds["emergency"]:
            return Anomaly(
                type="DURATION_THRESHOLD", severity=AnomalySeverity.HIGH.value,
                description=f"Duration {duration:.0f}s exceeds emergency threshold",
                value=duration, threshold=thresholds["emergency"], recommended_action="break_out_aggressive")
        elif duration > thresholds["critical"]:
            return Anomaly(
                type="DURATION_WARNING", severity=AnomalySeverity.MEDIUM.value,
                description=f"Duration {duration:.0f}s exceeds critical threshold",
                value=duration, threshold=thresholds["critical"], recommended_action="increase_monitoring")
        return None

    def _detect_cumulative_anomalies(self, mode: str, sub_mode: str, cumulative_session: float,
                                     cumulative_hour: float, cumulative_day: float) -> List[Anomaly]:
        anomalies = []
        mode_key = f"{mode}/{sub_mode}"
        thresholds = self.cumulative_thresholds["session"]
        if cumulative_session > thresholds["emergency"]:
            anomalies.append(Anomaly(
                type="CUMULATIVE_SESSION_EMERGENCY", severity=AnomalySeverity.HIGH.value,
                description=f"Cumulative session time in {mode_key}: {cumulative_session:.0f}s",
                value=cumulative_session, threshold=thresholds["emergency"], window="session",
                recommended_action="force_break_out"))
        elif cumulative_session > thresholds["critical"]:
            anomalies.append(Anomaly(
                type="CUMULATIVE_SESSION_CRITICAL", severity=AnomalySeverity.MEDIUM.value,
                description=f"Cumulative session time in {mode_key}: {cumulative_session:.0f}s",
                value=cumulative_session, threshold=thresholds["critical"], window="session",
                recommended_action="increase_monitoring"))
        thresholds = self.cumulative_thresholds["hour"]
        if cumulative_hour > thresholds["emergency"]:
            anomalies.append(Anomaly(
                type="CUMULATIVE_HOUR_EMERGENCY", severity=AnomalySeverity.HIGH.value,
                description=f"Cumulative hourly time in {mode_key}: {cumulative_hour:.0f}s",
                value=cumulative_hour, threshold=thresholds["emergency"], window="hour",
                recommended_action="force_break_out"))
        return anomalies

    def _detect_sequence_anomaly(self, sequence: List[str]) -> Optional[Anomaly]:
        if len(sequence) < 5:
            return None
        last_modes = [s.split("_")[0] for s in sequence[-10:]]
        mode_counts: Dict[str, int] = {}
        for m in last_modes:
            mode_counts[m] = mode_counts.get(m, 0) + 1
        most_frequent = max(mode_counts, key=lambda k: mode_counts.get(k, 0))
        frequency = mode_counts[most_frequent]
        if frequency >= 8:
            return Anomaly(
                type="MODE_STICKINESS", severity=AnomalySeverity.MEDIUM.value,
                description=f"Stuck in {most_frequent} mode ({frequency}/10 recent transitions)",
                value=frequency, threshold=8, recommended_action="check_mode_progress")
        if len(sequence) >= 6:
            oscillations = 0
            for i in range(len(sequence) - 2):
                if sequence[i] != sequence[i+1] and sequence[i+1] != sequence[i+2]:
                    oscillations += 1
            oscillation_ratio = oscillations / (len(sequence) - 2)
            if oscillation_ratio > 0.8:
                return Anomaly(
                    type="MODE_OSCILLATION", severity=AnomalySeverity.LOW.value,
                    description=f"Rapid mode oscillation detected ({oscillation_ratio:.0%})",
                    value=oscillation_ratio, threshold=0.8, recommended_action="log_for_analysis")
        return None

    def _detect_trend_anomaly(self, mode: str, sub_mode: str) -> Optional[Anomaly]:
        profile = self.profile_learner.get_profile(mode, sub_mode)
        if not profile or profile.trend in ["stable", "insufficient_data"]:
            return None
        if profile.trend == "increasing" and profile.trend_slope > profile.std_duration:
            return Anomaly(
                type="DURATION_TREND_INCREASING", severity=AnomalySeverity.LOW.value,
                description=f"Duration trend increasing for {mode}/{sub_mode}",
                value=profile.trend_slope, threshold=profile.std_duration, recommended_action="monitor_closely")
        return None


class AnomalyResponseSelector:
    def __init__(self):
        self.response_matrix = {
            "DURATION_EXTREME": {"actions": ["break_out_immediate", "log_critical", "notify"], "priority": 1, "confidence_impact": -30},
            "DURATION_HIGH": {"actions": ["break_out_aggressive", "log_error"], "priority": 2, "confidence_impact": -15},
            "DURATION_THRESHOLD": {"actions": ["break_out_standard", "log_warning"], "priority": 3, "confidence_impact": -10},
            "DURATION_WARNING": {"actions": ["increase_monitoring", "log_info"], "priority": 4, "confidence_impact": -5},
            "CUMULATIVE_SESSION_EMERGENCY": {"actions": ["force_break_out", "log_critical", "escalate"], "priority": 1, "confidence_impact": -25},
            "MODE_STICKINESS": {"actions": ["check_progress", "log_warning"], "priority": 5, "confidence_impact": -5},
            "MODE_OSCILLATION": {"actions": ["log_for_analysis"], "priority": 6, "confidence_impact": -2},
        }

    def select_response(self, anomalies: List[Anomaly]) -> ResponsePlan:
        if not anomalies:
            return ResponsePlan(actions=[], confidence_impact=0, escalation_tier="NONE")
        sorted_anomalies = sorted(anomalies, key=lambda a: self._get_priority(a.type))
        all_actions = []
        total_confidence_impact = 0
        highest_escalation = "NONE"
        for anomaly in sorted_anomalies:
            response = self.response_matrix.get(anomaly.type, {"actions": ["log_warning"], "confidence_impact": -5})
            all_actions.extend(response["actions"])
            total_confidence_impact += response["confidence_impact"]
            if anomaly.severity == "CRITICAL":
                highest_escalation = "EMERGENCY"
            elif anomaly.severity == "HIGH" and highest_escalation != "EMERGENCY":
                highest_escalation = "HIGH"
            elif anomaly.severity == "MEDIUM" and highest_escalation not in ["HIGH", "EMERGENCY"]:
                highest_escalation = "MEDIUM"
        unique_actions = list(dict.fromkeys(all_actions))
        return ResponsePlan(
            actions=unique_actions, confidence_impact=total_confidence_impact, escalation_tier=highest_escalation,
            primary_anomaly=sorted_anomalies[0], all_anomalies=anomalies)

    def _get_priority(self, anomaly_type: str) -> int:
        return self.response_matrix.get(anomaly_type, {}).get("priority", 10)


class BreakoutManager:
    def __init__(self, emulator_controller: Optional[Any] = None):
        self.emulator_controller = emulator_controller
        self.success_history: List[Dict[str, Any]] = []
        self.max_attempts = {
            BreakoutStrategy.IMMEDIATE.value: 3, BreakoutStrategy.AGGRESSIVE.value: 5,
            BreakoutStrategy.STANDARD.value: 3, BreakoutStrategy.FORCE.value: 1,
        }

    def execute_breakout(self, strategy: BreakoutStrategy, mode: str, sub_mode: str,
                         context: Optional[Dict[str, Any]] = None) -> BreakoutResult:
        max_attempts = self.max_attempts.get(strategy.value, 3)
        for attempt in range(max_attempts):
            success, action = self._execute_strategy(strategy, mode, sub_mode, context or {})
            self.success_history.append({
                "strategy": strategy.value, "mode": mode, "sub_mode": sub_mode,
                "attempt": attempt + 1, "success": success, "action": action, "timestamp": time.time(),
            })
            if success:
                return BreakoutResult(success=True, strategy=strategy.value, action=action, attempts=attempt + 1, mode=mode, sub_mode=sub_mode)
            time.sleep((attempt + 1) * 0.5)
        return BreakoutResult(success=False, strategy=strategy.value, action="ALL_ATTEMPTS_FAILED", attempts=max_attempts, mode=mode, sub_mode=sub_mode)

    def _execute_strategy(self, strategy: BreakoutStrategy, mode: str, sub_mode: str,
                          context: Dict[str, Any]) -> Tuple[bool, str]:
        if strategy == BreakoutStrategy.IMMEDIATE:
            return self._break_out_immediate(mode, sub_mode, context)
        elif strategy == BreakoutStrategy.AGGRESSIVE:
            return self._break_out_aggressive(mode, sub_mode, context)
        elif strategy == BreakoutStrategy.STANDARD:
            return self._break_out_standard(mode, sub_mode, context)
        elif strategy == BreakoutStrategy.FORCE:
            return self._force_break_out(mode, sub_mode, context)
        elif strategy == BreakoutStrategy.CHECK_PROGRESS:
            return self._check_progress(mode, sub_mode, context)
        elif strategy == BreakoutStrategy.INCREASE_MONITORING:
            return self._increase_monitoring(mode, sub_mode, context)
        return False, "UNKNOWN_STRATEGY"

    def _break_out_immediate(self, mode: str, sub_mode: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        if mode == GameMode.BATTLE.value:
            return self._battle_breakout_immediate()
        elif mode == GameMode.DIALOG.value:
            return self._dialog_breakout_immediate()
        elif mode == GameMode.MENU.value:
            return self._menu_breakout_immediate()
        return False, "UNKNOWN_MODE"

    def _break_out_aggressive(self, mode: str, sub_mode: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        success, action = self._break_out_standard(mode, sub_mode, context)
        if success:
            return success, action
        return self._break_out_immediate(mode, sub_mode, context)

    def _break_out_standard(self, mode: str, sub_mode: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        if mode == GameMode.BATTLE.value:
            return self._battle_breakout_standard()
        elif mode == GameMode.DIALOG.value:
            return self._dialog_breakout_standard()
        elif mode == GameMode.MENU.value:
            return self._menu_breakout_standard()
        return False, "UNKNOWN_MODE"

    def _force_break_out(self, mode: str, sub_mode: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        if mode == GameMode.BATTLE.value:
            if context.get("has_item", lambda x: False)("POKEBALL"):
                return True, "USE_BALL_ESCAPE"
            return True, "FORCE_EXIT"
        elif mode == GameMode.DIALOG.value:
            return True, "FORCE_SKIP"
        elif mode == GameMode.MENU.value:
            return True, "FORCE_CLOSE"
        return False, "FORCE_FAILED"

    def _check_progress(self, mode: str, sub_mode: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        last_state = context.get("last_state")
        current_state = context.get("current_state")
        if last_state and self._states_equivalent(last_state, current_state):
            return self._break_out_standard(mode, sub_mode, context)
        return True, "PROGRESS_DETECTED"

    def _increase_monitoring(self, mode: str, sub_mode: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        return True, "MONITORING_INCREASED"

    def _battle_breakout_standard(self) -> Tuple[bool, str]:
        return False, "RUN_FAILED"

    def _battle_breakout_immediate(self) -> Tuple[bool, str]:
        return False, "BATTLE_RESET"

    def _dialog_breakout_standard(self) -> Tuple[bool, str]:
        return False, "ADVANCE_FAILED"

    def _dialog_breakout_immediate(self) -> Tuple[bool, str]:
        return False, "DIALOG_SKIP_FAILED"

    def _menu_breakout_standard(self) -> Tuple[bool, str]:
        return False, "EXIT_FAILED"

    def _menu_breakout_immediate(self) -> Tuple[bool, str]:
        return False, "MENU_EXIT_FAILED"

    def _states_equivalent(self, state1: Optional[Dict[str, Any]],
                          state2: Optional[Dict[str, Any]]) -> bool:
        if not state1 or not state2:
            return False
        return state1.get("position") == state2.get("position") and state1.get("hp") == state2.get("hp")

    def get_success_rate(self, strategy: str, mode: str) -> float:
        key = f"{strategy}/{mode}"
        relevant = [r for r in self.success_history if f"{r['strategy']}/{r['mode']}" == key]
        if len(relevant) < 5:
            return 0.0
        success_count = sum(1 for r in relevant if r["success"])
        return success_count / len(relevant)


class BreakoutAnalytics:
    def __init__(self):
        self.breakout_history: List[Dict[str, Any]] = []
        self.success_rates: Dict[str, float] = {}

    def record_breakout(self, result: BreakoutResult) -> None:
        self.breakout_history.append({**asdict(result), "timestamp": time.time()})
        key = f"{result.strategy}/{result.mode}" if result.mode else f"{result.strategy}/unknown"
        self._update_success_rate(key, result.success)

    def get_success_rate(self, strategy: str, mode: str) -> float:
        key = f"{strategy}/{mode}"
        return self.success_rates.get(key, 0.0)

    def get_recommended_strategy(self, mode: str, sub_mode: str) -> BreakoutStrategy:
        strategies = [BreakoutStrategy.STANDARD, BreakoutStrategy.AGGRESSIVE,
                      BreakoutStrategy.IMMEDIATE, BreakoutStrategy.FORCE]
        best_strategy = BreakoutStrategy.STANDARD
        best_rate = 0.0
        for strategy in strategies:
            rate = self.get_success_rate(strategy.value, mode)
            if rate > best_rate:
                best_rate = rate
                best_strategy = strategy
        return best_strategy

    def _update_success_rate(self, key: str, success: bool) -> None:
        history = [r for r in self.breakout_history if f"{r['strategy']}/{r['mode']}" == key]
        if len(history) < 5:
            return
        recent = history[-20:]
        success_count = sum(1 for r in recent if r["success"])
        self.success_rates[key] = success_count / len(recent)


class ModeDurationEscalation:
    def __init__(self, confidence_scorer: Optional[Any] = None):
        self.confidence_scorer = confidence_scorer
        self.escalation_tiers = {
            EscalationTier.NONE: {"confidence_floor": 80, "actions": ["continue_normal"], "check_interval": 10.0},
            EscalationTier.ENHANCED_MONITORING: {"confidence_floor": 60, "actions": ["increase_check_frequency", "log_verbose"], "check_interval": 5.0},
            EscalationTier.PLAN_SIMPLIFICATION: {"confidence_floor": 40, "actions": ["simplify_strategy", "force_progress"], "check_interval": 2.0},
            EscalationTier.EMERGENCY_PROTOCOL: {"confidence_floor": 20, "actions": ["activate_failsafe", "attempt_recovery"], "check_interval": 1.0},
            EscalationTier.RESET_CONDITION: {"confidence_floor": 0, "actions": ["full_reset", "reload_checkpoint"], "check_interval": 0.5},
        }
        self.current_tier = EscalationTier.NONE
        self.tier_history: List[Dict[str, Any]] = []

    def update_escalation(self, anomalies: List[Anomaly], current_confidence: float) -> EscalationTier:
        target_tier = self._determine_tier_from_anomalies(anomalies)
        confidence_tier = self._determine_tier_from_confidence(current_confidence)
        target_tier = self._get_more_severe(target_tier, confidence_tier)
        if target_tier != self.current_tier:
            self._transition_tier(target_tier, anomalies, current_confidence)
        return self.current_tier

    def _determine_tier_from_anomalies(self, anomalies: List[Anomaly]) -> EscalationTier:
        if not anomalies:
            return EscalationTier.NONE
        severities = [a.severity for a in anomalies]
        if "CRITICAL" in severities:
            return EscalationTier.RESET_CONDITION
        elif "HIGH" in severities:
            return EscalationTier.EMERGENCY_PROTOCOL
        elif "MEDIUM" in severities:
            return EscalationTier.PLAN_SIMPLIFICATION
        return EscalationTier.ENHANCED_MONITORING

    def _determine_tier_from_confidence(self, confidence: float) -> EscalationTier:
        if confidence >= 80:
            return EscalationTier.NONE
        elif confidence >= 60:
            return EscalationTier.ENHANCED_MONITORING
        elif confidence >= 40:
            return EscalationTier.PLAN_SIMPLIFICATION
        elif confidence >= 20:
            return EscalationTier.EMERGENCY_PROTOCOL
        return EscalationTier.RESET_CONDITION

    def _get_more_severe(self, tier1: EscalationTier, tier2: EscalationTier) -> EscalationTier:
        tier_order = [EscalationTier.NONE, EscalationTier.ENHANCED_MONITORING, EscalationTier.PLAN_SIMPLIFICATION,
                      EscalationTier.EMERGENCY_PROTOCOL, EscalationTier.RESET_CONDITION]
        idx1 = tier_order.index(tier1)
        idx2 = tier_order.index(tier2)
        return tier1 if idx1 >= idx2 else tier2

    def _transition_tier(self, new_tier: EscalationTier, anomalies: List[Anomaly], confidence: float) -> None:
        old_tier = self.current_tier
        self.tier_history.append({
            "from_tier": old_tier.value, "to_tier": new_tier.value, "timestamp": time.time(),
            "confidence": confidence, "anomalies": [a.type for a in anomalies],
        })
        self.current_tier = new_tier

    def get_check_interval(self) -> float:
        return self.escalation_tiers[self.current_tier]["check_interval"]

    def get_confidence_floor(self) -> int:
        return self.escalation_tiers[self.current_tier]["confidence_floor"]


class ModeDurationTrackingSystem:
    def __init__(self, state_machine: Optional[Any] = None, confidence_scorer: Optional[Any] = None,
                 failsafe_manager: Optional[Any] = None, storage_path: str = "data/duration_profiles.json"):
        self.mode_classifier = ModeClassifier(state_machine)
        self.duration_tracker = DurationTracker()
        self.profile_learner = DurationProfileLearner()
        self.profile_store = DurationProfileStore(storage_path)
        self.anomaly_detector = AnomalyDetector(self.profile_learner)
        self.response_selector = AnomalyResponseSelector()
        self.breakout_manager = BreakoutManager()
        self.analytics = BreakoutAnalytics()
        self.escalation = ModeDurationEscalation(confidence_scorer)
        self.state_machine = state_machine
        self.confidence_scorer = confidence_scorer
        self.failsafe_manager = failsafe_manager
        self._load_profiles()

    def _load_profiles(self) -> None:
        profiles = self.profile_store.load_profiles()
        for key, profile in profiles.items():
            self.profile_learner.profiles[key] = profile

    def update(self, current_state: Dict[str, Any], tick: int = 0,
               current_confidence: float = 100.0) -> Dict[str, Any]:
        mode_classification = self.mode_classifier.classify_mode(current_state, tick)
        if self._is_mode_change(mode_classification):
            if self.duration_tracker.current_mode:
                self.duration_tracker.exit_mode(reason="interrupt", tick=tick)
            self.duration_tracker.enter_mode(
                mode=mode_classification.mode, sub_mode=mode_classification.sub_mode,
                context={"classification": mode_classification.__dict__}, state_snapshot=current_state, tick=tick)
        current_duration = self.duration_tracker.get_current_duration()
        cumulative_session = self.duration_tracker.get_current_cumulative("session")
        cumulative_hour = self.duration_tracker.get_current_cumulative("hour")
        cumulative_day = self.duration_tracker.get_current_cumulative("day")
        anomalies = self.anomaly_detector.detect_anomalies(
            current_mode=mode_classification.mode, current_sub_mode=mode_classification.sub_mode,
            current_duration=current_duration, cumulative_session=cumulative_session,
            cumulative_hour=cumulative_hour, cumulative_day=cumulative_day,
            mode_sequence=self.duration_tracker.mode_sequence)
        new_tier = self.escalation.update_escalation(anomalies, current_confidence)
        response = self.response_selector.select_response(anomalies)
        for anomaly in anomalies:
            if anomaly.recommended_action.startswith("break_out"):
                strategy = self.analytics.get_recommended_strategy(mode_classification.mode, mode_classification.sub_mode)
                result = self.breakout_manager.execute_breakout(
                    strategy=strategy, mode=mode_classification.mode, sub_mode=mode_classification.sub_mode,
                    context={"classification": mode_classification.__dict__})
                self.analytics.record_breakout(result)
        return {
            "mode": mode_classification.mode, "sub_mode": mode_classification.sub_mode,
            "confidence": mode_classification.confidence, "current_duration": current_duration,
            "cumulative_session": cumulative_session, "anomalies": [asdict(a) for a in anomalies],
            "escalation_tier": new_tier.value, "response_actions": response.actions,
            "confidence_impact": response.confidence_impact,
        }

    def on_mode_exit(self, mode: str, sub_mode: str, reason: str, tick: int = 0) -> None:
        duration = self.duration_tracker.get_current_duration()
        self.profile_learner.update_profile(mode, sub_mode, duration)
        profile = self.profile_learner.get_profile(mode, sub_mode)
        if profile:
            self.profile_store.save_profile(profile)
        self.duration_tracker.exit_mode(reason=reason, tick=tick)

    def _is_mode_change(self, new_classification: ModeClassification) -> bool:
        if not self.duration_tracker.current_mode:
            return True
        current = self.duration_tracker.current_mode
        return current.mode != new_classification.mode or current.sub_mode != new_classification.sub_mode

    def get_dashboard_data(self) -> Dict[str, Any]:
        current_duration = self.duration_tracker.get_current_duration()
        current_cumulative = self.duration_tracker.get_current_cumulative("session")
        return {
            "current_mode": self.duration_tracker.current_mode.mode if self.duration_tracker.current_mode else None,
            "current_sub_mode": self.duration_tracker.current_mode.sub_mode if self.duration_tracker.current_mode else None,
            "current_duration": current_duration, "cumulative_session": current_cumulative,
            "escalation_tier": self.escalation.current_tier.value,
            "active_anomalies": len(self.anomaly_detector.detect_anomalies(
                self.duration_tracker.current_mode.mode if self.duration_tracker.current_mode else "",
                self.duration_tracker.current_mode.sub_mode if self.duration_tracker.current_mode else "",
                current_duration, current_cumulative, 0, 0, self.duration_tracker.mode_sequence)),
            "mode_sequence": self.duration_tracker.mode_sequence[-10:],
        }
