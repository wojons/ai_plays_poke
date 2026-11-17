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

# ── Model call cost/errors, in depth (MON-AIPP-4) ───────────────────
# `log_api_call` already RECEIVES the duration, both token counts, the cost
# and the success flag of every model call and only prints them, so a slow or
# dead provider stays invisible to a scrape. These four families make the call
# shape scrapeable: latency, context growth by direction, failover cause by
# reason, and which configured credential is dead. `model_family` always comes
# from `model_family()` — never a raw model string — and `key_name` is a STATIC
# enum of the env-var NAMES this repo probes (spec §5), never a value.
_MODEL_CALL_DURATION = _metric(
    Histogram,
    "aipp_model_call_duration_seconds",
    "Model API call duration in seconds, by model family.",
    ("model_family",),
)
_MODEL_TOKENS = _metric(
    Counter,
    "aipp_model_tokens_total",
    "Tokens sent to and returned by model APIs, by model family and direction.",
    ("model_family", "direction"),
)
_MODEL_RETRIES = _metric(
    Counter,
    "aipp_model_retries_total",
    "Model API retry attempts, by model family and the reason that forced them.",
    ("model_family", "reason"),
)
_CREDENTIAL_VALID = _metric(
    Gauge,
    "aipp_credential_valid",
    "Boot key-liveness probe result by probed env-var name: 1 live, 0 dead.",
    ("key_name",),
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
_TOKEN_DIRECTION_LABELS = ("input", "output")
_RETRY_REASON_LABELS = ("auth", "quota", "5xx", "timeout")
# The only key NAMES this repo probes (cron_runner._KEY_PROBE_URLS). The enum
# lives here because cron_runner imports this module, not the other way round;
# tests/test_observability_model_metrics.py pins the two sets equal, so adding
# a probe URL without extending the enum fails loudly instead of minting a
# series outside the closed vocabulary.
_CREDENTIAL_KEY_LABELS = frozenset({"OPENROUTER_API_KEY", "DEEPSEEK_API_KEY"})

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
_MODEL_CALL_DURATION.labels(model_family="other")
_MODEL_TOKENS.labels(model_family="other", direction="input").inc(0)
_MODEL_TOKENS.labels(model_family="other", direction="output").inc(0)
_MODEL_RETRIES.labels(model_family="other", reason="auth").inc(0)
# `_CREDENTIAL_VALID` is deliberately NOT materialized: a series minted here
# would read as "dead" for a key this host never configured. The boot probe
# mints one series per CONFIGURED key NAME only, which is what keeps the
# `key_name` cardinality at the number of probes the host actually runs.


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


def token_direction_label(direction: str | None) -> str | None:
    """Map a token direction onto the closed vocabulary (None = do not count)."""
    if isinstance(direction, str) and direction in _TOKEN_DIRECTION_LABELS:
        return direction
    return None


def retry_reason_label(reason: str | None) -> str | None:
    """Map a retry cause onto the closed vocabulary; None when unattributable.

    An unattributable retry is NOT counted: a guessed bucket would make the
    breakdown look classified when it is not, which is worse than a gap the
    operator can see.
    """
    if isinstance(reason, str):
        normalised = reason.strip().lower()
        if normalised in _RETRY_REASON_LABELS:
            return normalised
    return None


def credential_key_label(key_name: str | None) -> str | None:
    """Map a probed env-var name onto the static enum; None mints no series."""
    if isinstance(key_name, str) and key_name in _CREDENTIAL_KEY_LABELS:
        return key_name
    return None


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


def observe_model_duration(model: str, seconds: float) -> None:
    """Record one model call's wall-clock duration (MON-AIPP-4)."""
    try:
        _MODEL_CALL_DURATION.labels(model_family=model_family(model)).observe(
            max(0.0, float(seconds or 0.0))
        )
    except Exception:  # noqa: BLE001 - telemetry must never escape to callers
        return None  # noqa: RET501


def observe_model_tokens(model: str, input_tokens: int, output_tokens: int) -> None:
    """Record both token directions for one model call (MON-AIPP-4).

    Both directions are published from the same call so a dashboard can divide
    output by input without two different sampling paths; a negative count is
    clamped to zero rather than allowed to walk a counter backwards.
    """
    try:
        family = model_family(model)
        _MODEL_TOKENS.labels(model_family=family, direction="input").inc(
            max(0, int(input_tokens or 0))
        )
        _MODEL_TOKENS.labels(model_family=family, direction="output").inc(
            max(0, int(output_tokens or 0))
        )
    except Exception:  # noqa: BLE001 - telemetry must never escape to callers
        return None  # noqa: RET501


def observe_model_retry(model: str, reason: str | None, count: int = 1) -> None:
    """Record retry attempts attributed to the cause that forced them.

    Called at the point a retry is DECIDED (the backoff loop), because that is
    where the status code or exception class is in hand. An unattributable
    reason, or a non-positive count, records nothing.
    """
    try:
        reason_label = retry_reason_label(reason)
        amount = max(0, int(count or 0))
        if reason_label is None or amount <= 0:
            return None
        _MODEL_RETRIES.labels(
            model_family=model_family(model), reason=reason_label
        ).inc(amount)
    except Exception:  # noqa: BLE001 - telemetry must never escape to callers
        return None  # noqa: RET501


def set_credential_valid(key_name: str, valid: bool) -> None:
    """Publish one boot key-liveness result (MON-AIPP-4).

    ``key_name`` is an ENV-VAR NAME from the static enum; a name outside it
    (a key this repo does not probe) records nothing, so an unconfigured
    credential can never appear as a dead series.
    """
    try:
        label = credential_key_label(key_name)
        if label is None:
            return None
        _CREDENTIAL_VALID.labels(key_name=label).set(1 if valid else 0)
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
