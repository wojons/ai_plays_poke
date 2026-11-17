"""MON-AIPP-4: model latency/token/retry families + the credential-validity gauge.

Covers the four families added to ``src/observability/metrics.py`` and the two
places that feed them:

* ``src/core/ai_client.py`` — ``log_api_call`` (duration, both token
  directions, cost) and the retry decision points (429/quota, 401|403/auth,
  >=500/5xx, socket timeout/timeout).
* ``cron_runner.py`` — ``_check_configured_keys`` (``aipp_credential_valid``
  per probed env-var NAME).

The registry is process-wide, so every assertion is a DELTA or a closed-vocab
membership test rather than an absolute value: another test module in the same
session may already have moved the same series.
"""

from __future__ import annotations

import importlib
import io
import json
import re
import urllib.error
from typing import Any

import pytest
import requests
import requests_mock
from prometheus_client import REGISTRY, generate_latest

import cron_runner
import src.core.ai_client as ai_client
from src.observability import metrics

_KEY_NAME_RE = re.compile(
    r'^aipp_credential_valid\{key_name="([^"]+)"\} ', re.MULTILINE
)
_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


def _exposition() -> str:
    return generate_latest(REGISTRY).decode()


def _value(name: str, **labels: str) -> float:
    """Read one sample's value from the live registry (0.0 when absent)."""
    label_text = ",".join(f'{key}="{val}"' for key, val in sorted(labels.items()))
    selector = f"{{{label_text}}}" if label_text else ""
    pattern = rf"^{re.escape(name)}{re.escape(selector)} ([0-9.eE+-]+)$"
    match = re.search(pattern, _exposition(), re.MULTILINE)
    return float(match.group(1)) if match else 0.0


def _key_name_series() -> set[str]:
    return set(_KEY_NAME_RE.findall(_exposition()))


def _ok_payload(
    prompt_tokens: int = 100, completion_tokens: int = 20
) -> dict[str, Any]:
    return {
        "id": "cmpl-test",
        "model": "openai/gpt-4o-mini",
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> ai_client.OpenRouterClient:
    """A client on a closed breaker with no DeepSeek routing and no real sleep."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(ai_client.time, "sleep", lambda *_: None)
    return ai_client.OpenRouterClient(api_key="test-key")


class TestDeclarations:
    """The families exist, once, with the labels the spec asks for."""

    @pytest.mark.parametrize(
        ("family", "openmetrics_type"),
        [
            ("aipp_model_call_duration_seconds", "histogram"),
            ("aipp_model_tokens_total", "counter"),
            ("aipp_model_retries_total", "counter"),
            ("aipp_credential_valid", "gauge"),
        ],
    )
    def test_family_declared_exactly_once(
        self, family: str, openmetrics_type: str
    ) -> None:
        exposition = _exposition()
        assert exposition.count(f"# TYPE {family} {openmetrics_type}") == 1
        assert f"# HELP {family} " in exposition

    def test_pre_existing_families_still_declared_once(self) -> None:
        """MON-AIPP-4 must not rename, relabel or re-register a prior family."""
        exposition = _exposition()
        for family in (
            "aipp_run_cycles_total",
            "aipp_decision_duration_seconds",
            "aipp_model_calls_total",
            "aipp_model_cost_usd_total",
            "aipp_runner_up",
            "aipp_map_transitions_total",
        ):
            assert exposition.count(f"# TYPE {family} ") == 1, family

    def test_module_reload_reuses_registered_series(self) -> None:
        reloaded = importlib.reload(metrics)
        try:
            # Same collector objects => a reload cannot duplicate or orphan them.
            assert reloaded._MODEL_TOKENS is metrics._MODEL_TOKENS
            assert _exposition().count("# TYPE aipp_model_tokens_total counter") == 1
        finally:
            importlib.reload(metrics)

    def test_closed_label_vocabularies(self) -> None:
        assert metrics.retry_reason_label("quota") == "quota"
        assert metrics.retry_reason_label(" QUOTA ") == "quota"
        assert metrics.retry_reason_label("rate_limited") is None
        assert metrics.retry_reason_label(None) is None
        assert metrics.token_direction_label("output") == "output"
        assert metrics.token_direction_label("both") is None
        # A key this repo does not probe is never a series, however it is spelled.
        assert metrics.credential_key_label("ANTHROPIC_API_KEY") is None
        assert metrics.credential_key_label("sk-or-v1-deadbeef") is None

    def test_credential_enum_matches_the_names_the_repo_actually_probes(self) -> None:
        """Drift guard: a new probe URL must extend the label enum too."""
        assert set(metrics._CREDENTIAL_KEY_LABELS) == set(cron_runner._KEY_PROBE_URLS)


class TestLogApiCallFeedsFamilies:
    """`log_api_call` receives the values today and used to only print them."""

    def test_duration_tokens_and_cost_move_together(self) -> None:
        duration_count = _value(
            "aipp_model_call_duration_seconds_count", model_family="gpt"
        )
        duration_sum = _value(
            "aipp_model_call_duration_seconds_sum", model_family="gpt"
        )
        tokens_in = _value(
            "aipp_model_tokens_total", model_family="gpt", direction="input"
        )
        tokens_out = _value(
            "aipp_model_tokens_total", model_family="gpt", direction="output"
        )
        cost = _value("aipp_model_cost_usd_total", model_family="gpt")

        ai_client.log_api_call("openai/gpt-4o-mini", 250.0, 1000, 500, 0.002, True)

        assert (
            _value("aipp_model_call_duration_seconds_count", model_family="gpt")
            == duration_count + 1
        )
        assert _value(
            "aipp_model_call_duration_seconds_sum", model_family="gpt"
        ) == pytest.approx(duration_sum + 0.25)
        assert (
            _value("aipp_model_tokens_total", model_family="gpt", direction="input")
            == tokens_in + 1000
        )
        assert (
            _value("aipp_model_tokens_total", model_family="gpt", direction="output")
            == tokens_out + 500
        )
        assert _value("aipp_model_cost_usd_total", model_family="gpt") == pytest.approx(
            cost + 0.002
        )

    def test_raw_model_string_never_becomes_a_label(self) -> None:
        before = _value("aipp_model_calls_total", model_family="claude", outcome="ok")
        ai_client.log_api_call(
            "anthropic/claude-3-haiku-20240307", 10.0, 10, 5, 0.0001, True
        )
        exposition = _exposition()
        assert "anthropic/claude-3-haiku-20240307" not in exposition
        assert 'model_family="claude-3-haiku' not in exposition
        assert (
            _value("aipp_model_calls_total", model_family="claude", outcome="ok")
            == before + 1
        )

    def test_failure_still_records_latency_but_no_tokens(self) -> None:
        duration_count = _value(
            "aipp_model_call_duration_seconds_count", model_family="gemini"
        )
        errors = _value(
            "aipp_model_calls_total", model_family="gemini", outcome="error"
        )
        ai_client.log_api_call("google/gemini-2.0-flash", 400.0, 0, 0, 0.0, False)
        assert (
            _value("aipp_model_call_duration_seconds_count", model_family="gemini")
            == duration_count + 1
        )
        assert (
            _value("aipp_model_calls_total", model_family="gemini", outcome="error")
            == errors + 1
        )

    def test_optional_retry_parameters_are_recorded(self) -> None:
        before = _value(
            "aipp_model_retries_total", model_family="deepseek", reason="quota"
        )
        ai_client.log_api_call(
            "deepseek-chat", 100.0, 10, 5, 0.0, True, retry_count=2, reason="quota"
        )
        assert (
            _value("aipp_model_retries_total", model_family="deepseek", reason="quota")
            == before + 2
        )

    def test_unattributable_retry_mints_no_series(self) -> None:
        before = sum(
            _value("aipp_model_retries_total", model_family="other", reason=reason)
            for reason in metrics._RETRY_REASON_LABELS
        )
        ai_client.log_api_call(
            "openai/gpt-4o-mini", 100.0, 10, 5, 0.0, False, retry_count=1, reason="??"
        )
        after = sum(
            _value("aipp_model_retries_total", model_family="other", reason=reason)
            for reason in metrics._RETRY_REASON_LABELS
        )
        assert after == before
        assert 'reason="??"' not in _exposition()


class TestChatCompletionRetryAttribution:
    """A retry is counted where it is decided, from what the branch knows."""

    def test_rate_limit_retry_is_attributed_to_quota_and_the_call_succeeds(
        self, client: ai_client.OpenRouterClient
    ) -> None:
        before_quota = _value(
            "aipp_model_retries_total", model_family="gpt", reason="quota"
        )
        before_ok = _value("aipp_model_calls_total", model_family="gpt", outcome="ok")
        before_tokens = _value(
            "aipp_model_tokens_total", model_family="gpt", direction="input"
        )

        with requests_mock.Mocker() as mock:
            mock.post(
                _CHAT_URL,
                [
                    {
                        "status_code": 429,
                        "json": {"error": {"message": "rate limited"}},
                    },
                    {"status_code": 200, "json": _ok_payload()},
                ],
            )
            result = client.chat_completion(
                model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hi"}]
            )

        assert result["content"] == "ok"
        assert (
            _value("aipp_model_retries_total", model_family="gpt", reason="quota")
            == before_quota + 1
        )
        assert (
            _value("aipp_model_calls_total", model_family="gpt", outcome="ok")
            == before_ok + 1
        )
        assert (
            _value("aipp_model_tokens_total", model_family="gpt", direction="input")
            == before_tokens + 100
        )

    def test_auth_failure_retries_are_attributed_to_auth(
        self, client: ai_client.OpenRouterClient
    ) -> None:
        before_auth = _value(
            "aipp_model_retries_total", model_family="gpt", reason="auth"
        )
        before_errors = _value(
            "aipp_model_calls_total", model_family="gpt", outcome="error"
        )

        with requests_mock.Mocker() as mock:
            mock.post(
                _CHAT_URL,
                status_code=401,
                json={"error": {"message": "API key expired"}},
            )
            with pytest.raises(Exception, match="401"):
                client.chat_completion(
                    model="openai/gpt-4o-mini",
                    messages=[{"role": "user", "content": "hi"}],
                )

        # Three attempts, two of which were retried: the last one has nowhere
        # left to retry, so it must NOT be counted as a retry.
        assert (
            _value("aipp_model_retries_total", model_family="gpt", reason="auth")
            == before_auth + 2
        )
        # A call that died is still a call.
        assert (
            _value("aipp_model_calls_total", model_family="gpt", outcome="error")
            == before_errors + 1
        )

    def test_server_error_retries_are_attributed_to_5xx(
        self, client: ai_client.OpenRouterClient
    ) -> None:
        before_5xx = _value(
            "aipp_model_retries_total", model_family="gpt", reason="5xx"
        )

        with requests_mock.Mocker() as mock:
            mock.post(
                _CHAT_URL,
                status_code=503,
                json={"error": {"message": "upstream down"}},
            )
            with pytest.raises(Exception, match="503"):
                client.chat_completion(
                    model="openai/gpt-4o-mini",
                    messages=[{"role": "user", "content": "hi"}],
                )

        assert (
            _value("aipp_model_retries_total", model_family="gpt", reason="5xx")
            == before_5xx + 2
        )

    def test_socket_timeout_is_attributed_to_timeout(
        self, client: ai_client.OpenRouterClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        before = _value(
            "aipp_model_retries_total", model_family="gpt", reason="timeout"
        )

        def _timeout(*_args: Any, **_kwargs: Any) -> None:
            raise requests.exceptions.ConnectTimeout("timed out")

        monkeypatch.setattr(ai_client.requests, "post", _timeout)
        with pytest.raises(requests.exceptions.ConnectTimeout):
            client.chat_completion(
                model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hi"}]
            )

        assert (
            _value("aipp_model_retries_total", model_family="gpt", reason="timeout")
            == before + 2
        )


class _LiveProbe:
    """urllib response stub for a 200 key-liveness probe."""

    def __init__(self) -> None:
        self.status = 200

    def read(self) -> bytes:
        return b"{}"

    def __enter__(self) -> "_LiveProbe":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None


@pytest.fixture
def no_ambient_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cron_runner, "_load_dotenv_stdlib", lambda: None)
    for name in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)


class TestCredentialValidGauge:
    """The boot probe publishes 1/0 per CONFIGURED key NAME — nothing else."""

    def test_live_probe_sets_one_for_the_configured_key_only(
        self, no_ambient_keys: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        seen: list[str] = []

        def fake_urlopen(request: Any, timeout: float | None = None) -> _LiveProbe:
            _ = timeout
            seen.append(request.full_url)
            return _LiveProbe()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        before = _key_name_series()

        assert cron_runner._check_configured_keys(False) == []

        # Only the CONFIGURED key was probed, so only it could mint a series.
        assert seen == [cron_runner._KEY_PROBE_URLS["OPENROUTER_API_KEY"]]
        assert _value("aipp_credential_valid", key_name="OPENROUTER_API_KEY") == 1.0
        added = _key_name_series() - before
        assert added <= {"OPENROUTER_API_KEY"}
        assert "DEEPSEEK_API_KEY" not in added

    def test_dead_probe_sets_zero_and_flips_back_to_one(
        self, no_ambient_keys: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        def dead_urlopen(request: Any, timeout: float | None = None) -> None:
            _ = timeout
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                None,
                io.BytesIO(
                    json.dumps({"error": {"message": "API key expired"}}).encode()
                ),
            )

        monkeypatch.setattr("urllib.request.urlopen", dead_urlopen)
        dead = cron_runner._check_configured_keys(False)
        assert dead and dead[0][0] == "OPENROUTER_API_KEY"
        assert _value("aipp_credential_valid", key_name="OPENROUTER_API_KEY") == 0.0

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _LiveProbe())
        assert cron_runner._check_configured_keys(False) == []
        assert _value("aipp_credential_valid", key_name="OPENROUTER_API_KEY") == 1.0

    def test_no_configured_key_mints_nothing(
        self, no_ambient_keys: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("no key is configured; nothing may be probed")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        before = _key_name_series()
        assert cron_runner._check_configured_keys(False) == []
        assert _key_name_series() == before

    def test_skip_key_check_mints_nothing(
        self, no_ambient_keys: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        before = _key_name_series()
        assert cron_runner._check_configured_keys(True) == []
        assert _key_name_series() == before

    def test_key_name_series_never_exceeds_the_cardinality_budget(self) -> None:
        """AC3 in-process: the exposition carries at most 3 `key_name=` samples."""
        exposition = _exposition()
        assert exposition.count("key_name=") <= 3
        assert _key_name_series() <= set(metrics._CREDENTIAL_KEY_LABELS)


class TestAcceptancePromQLShapes:
    """AC1: the two dashboard queries are computable from these families."""

    def test_error_ratio_and_hourly_spend_are_non_zero(self) -> None:
        ok_before = sum(
            _value("aipp_model_calls_total", model_family="local", outcome=outcome)
            for outcome in ("ok", "error")
        )
        error_before = _value(
            "aipp_model_calls_total", model_family="local", outcome="error"
        )
        cost_before = _value("aipp_model_cost_usd_total", model_family="local")

        # A simulated run segment: two good calls, one dead one.
        ai_client.log_api_call("ollama/gemma-3-12b-it", 900.0, 400, 60, 0.00002, True)
        ai_client.log_api_call("ollama/gemma-3-12b-it", 800.0, 380, 55, 0.00002, True)
        ai_client.log_api_call("ollama/gemma-3-12b-it", 30000.0, 0, 0, 0.0, False)

        ok_after = sum(
            _value("aipp_model_calls_total", model_family="local", outcome=outcome)
            for outcome in ("ok", "error")
        )
        error_after = _value(
            "aipp_model_calls_total", model_family="local", outcome="error"
        )
        cost_after = _value("aipp_model_cost_usd_total", model_family="local")

        assert ok_after - ok_before == 3
        assert error_after - error_before == 1
        assert cost_after - cost_before == pytest.approx(0.00004)
        # sum(rate(calls{outcome!="ok"})) / sum(rate(calls)) over this segment
        error_ratio = (error_after - error_before) / (ok_after - ok_before)
        assert error_ratio == pytest.approx(1 / 3)
