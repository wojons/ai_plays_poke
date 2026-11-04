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

# Materialize zero-valued series so every P0 metric is visible on the first scrape.
_RUN_CYCLES.labels(mode="unknown", pipeline="unknown")
_DECISION_DURATION.labels(mode="unknown", pipeline="unknown")
_MODEL_CALLS.labels(model_family="other", outcome="ok")
_MODEL_COST.labels(model_family="other")
_RUNNER_UP.labels(surface="cron").set(0)
_RUNNER_UP.labels(surface="dashboard").set(0)


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
