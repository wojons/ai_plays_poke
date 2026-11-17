"""Low-cardinality Prometheus metrics for the gameplay runner and dashboard."""

from prometheus_client import REGISTRY, Counter, Gauge, Histogram


def _metric(factory, *args, **kwargs):
    """Return an existing registered series on reload, or register it once."""
    try:
        return factory(*args, **kwargs)
    except ValueError as exc:
        if "Duplicated timeseries" not in str(exc):
            raise
        # Re-import/reload should reuse the process-wide default registry series.
        return REGISTRY._names_to_collectors[args[0]]


_RUN_CYCLES = _metric(
    Counter,
    "aipp_run_cycles_total",
    "Completed gameplay cycles.",
    ("mode", "pipeline"),
)
_DECISION_DURATION = _metric(
    Histogram,
    "aipp_decision_duration_seconds",
    "Elapsed time spent in a gameplay decision cycle.",
    ("mode", "pipeline"),
)
_MODEL_CALLS = _metric(
    Counter,
    "aipp_model_calls_total",
    "Model API calls by model family and outcome.",
    ("model_family", "outcome"),
)
_MODEL_COST = _metric(
    Counter,
    "aipp_model_cost_usd_total",
    "Estimated model API cost in USD.",
    ("model_family",),
)
_RUNNER_UP = _metric(
    Gauge,
    "aipp_runner_up",
    "Whether a runner surface is currently up (1) or down (0).",
    ("surface",),
)

# ── Progress vs effort (MON-AIPP-3) ─────────────────────────────────
# A run can look healthy in-process — many decisions, no transport errors,
# high autonomy ratio — while achieving nothing. These counters make that
# state scrapeable: `aipp_episode_decisions_total` rising while
# `aipp_map_transitions_total` stays flat is a treadmill, and
# `aipp_backtrack_events_total` says how much of the effort went backwards.
# Every value is fed from the SAME run-end counters the autonomy row and the
# node_exporter textfile already use, so the three surfaces cannot drift.
_MAP_TRANSITIONS = _metric(
    Counter,
    "aipp_map_transitions_total",
    "Map transitions observed at run end.",
)
_EPISODE_DECISIONS = _metric(
    Counter,
    "aipp_episode_decisions_total",
    "Gameplay decisions taken at run end, by decision mode.",
    ("mode",),
)
_BACKTRACK_EVENTS = _metric(
    Counter,
    "aipp_backtrack_events_total",
    "Decision rows that repeated or revisited an already-seen tile state.",
)
_RUN_COMPLETED = _metric(
    Counter,
    "aipp_run_completed_total",
    "Completed gameplay runs by outcome.",
    ("outcome",),
)
_RUN_DURATION = _metric(
    Histogram,
    "aipp_run_duration_seconds",
    "Wall-clock duration of a gameplay run, by outcome.",
    ("outcome",),
)
_TEACHER_ESCALATIONS = _metric(
    Counter,
    "aipp_teacher_escalations_total",
    "Teacher (System-Two) escalations by whether they improved the decision.",
    ("improved",),
)

# Closed label vocabularies. Dashboards scrape these families, so an
# operator-supplied spelling must never be able to mint a new series.
_DECISION_MODE_LABELS = frozenset(
    {
        "system1",
        "system2",
        "system1+system2",
        "jev",
        "hybrid",
        "llm",
        "agentic",
        "unknown",
    }
)
_RUN_OUTCOME_LABELS = ("completed", "error", "gave_up", "unknown")

# Materialize zero-valued series so every P0 metric is visible on the first scrape.
_RUN_CYCLES.labels(mode="unknown", pipeline="unknown")
_DECISION_DURATION.labels(mode="unknown", pipeline="unknown")
_MODEL_CALLS.labels(model_family="other", outcome="ok")
_MODEL_COST.labels(model_family="other")
_RUNNER_UP.labels(surface="cron").set(0)
_RUNNER_UP.labels(surface="dashboard").set(0)
_MAP_TRANSITIONS.inc(0)
_EPISODE_DECISIONS.labels(mode="unknown").inc(0)
_BACKTRACK_EVENTS.inc(0)
_RUN_COMPLETED.labels(outcome="completed").inc(0)
_RUN_DURATION.labels(outcome="completed")
_TEACHER_ESCALATIONS.labels(improved="true").inc(0)
_TEACHER_ESCALATIONS.labels(improved="false").inc(0)


def decision_mode_label(mode: str | None) -> str:
    """Map a decision-mode spelling onto the closed exporter vocabulary."""
    if isinstance(mode, str):
        normalised = mode.strip().lower()
        if normalised in _DECISION_MODE_LABELS:
            return normalised
    return "unknown"


def run_outcome_label(outcome: str | None) -> str:
    """Map a run outcome onto the closed exporter vocabulary."""
    if isinstance(outcome, str) and outcome in _RUN_OUTCOME_LABELS:
        return outcome
    return "unknown"


def model_family(model: str) -> str:
    """Map arbitrary model identifiers into a closed, low-cardinality set."""
    lowered = model.lower()
    for token, family in (
        ("claude", "claude"),
        ("gpt", "gpt"),
        ("deepseek", "deepseek"),
        ("gemini", "gemini"),
        ("gemma", "local"),
        ("ollama", "local"),
        ("local", "local"),
    ):
        if token in lowered:
            return family
    return "other"


def observe_cycle(mode: str, pipeline: str) -> None:
    try:
        _RUN_CYCLES.labels(mode=mode, pipeline=pipeline).inc()
    except Exception:  # noqa: BLE001 - telemetry must never escape to callers
        return None  # noqa: RET501


def observe_decision_seconds(mode: str, pipeline: str, seconds: float) -> None:
    try:
        _DECISION_DURATION.labels(mode=mode, pipeline=pipeline).observe(seconds)
    except Exception:  # noqa: BLE001 - telemetry must never escape to callers
        return None  # noqa: RET501


def observe_model_call(model: str, cost: float, success: bool) -> None:
    try:
        family = model_family(model)
        outcome = "ok" if success else "error"
        _MODEL_CALLS.labels(model_family=family, outcome=outcome).inc()
        if cost > 0:
            _MODEL_COST.labels(model_family=family).inc(cost)
    except Exception:  # noqa: BLE001 - telemetry must never escape to callers
        return None  # noqa: RET501


def set_runner_up(surface: str, up: bool = True) -> None:
    try:
        _RUNNER_UP.labels(surface=surface).set(1 if up else 0)
    except Exception:  # noqa: BLE001 - telemetry must never escape to callers
        return None  # noqa: RET501


def observe_run_end(
    *,
    mode: str | None,
    outcome: str | None,
    duration_s: float,
    decisions_total: int,
    map_transitions: int,
    backtrack_events: int,
    teacher_escalations: int = 0,
    teacher_improved: int = 0,
) -> None:
    """Publish one finished run's progress-vs-effort counters (MON-AIPP-3).

    Called from the run-end path with the SAME block the autonomy row and the
    node_exporter textfile are written from, so a scrape, a log row and a
    textfile sample of the same run agree by construction. Counters are
    cumulative within the process (one process per cron run); the textfile
    keeps the across-run total.

    ``teacher_improved`` is clamped to ``teacher_escalations`` so the two
    ``improved`` series can never claim more successes than escalations — a
    counter that exceeds its denominator is worse than a missing one.
    """
    try:
        outcome_label = run_outcome_label(outcome)
        escalations = max(0, int(teacher_escalations or 0))
        improved = min(max(0, int(teacher_improved or 0)), escalations)
        _RUN_COMPLETED.labels(outcome=outcome_label).inc()
        _RUN_DURATION.labels(outcome=outcome_label).observe(
            max(0.0, float(duration_s or 0.0))
        )
        _EPISODE_DECISIONS.labels(mode=decision_mode_label(mode)).inc(
            max(0, int(decisions_total or 0))
        )
        _MAP_TRANSITIONS.inc(max(0, int(map_transitions or 0)))
        _BACKTRACK_EVENTS.inc(max(0, int(backtrack_events or 0)))
        _TEACHER_ESCALATIONS.labels(improved="true").inc(improved)
        _TEACHER_ESCALATIONS.labels(improved="false").inc(escalations - improved)
    except Exception:  # noqa: BLE001 - telemetry must never escape to callers
        return None  # noqa: RET501
