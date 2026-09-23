"""GAP-052: the LLM escape hatch — controller model plumbing + parse hardening.

The row came out of the 2026-09-09b dogfood run, which lost every controller
call for two reasons:

1. the controller model was hardcoded to ``openai/gpt-5.6-luna`` (no flag, no
   env hook), so a user whose OpenRouter key was out of credit had no way to
   point the run at the provider that still worked; and
2. DeepSeek returns its reasoning INLINE in the content string
   (``<think>...</think>``, bare ``</think>``, ``|end_of_thought|``), so
   ``json.loads`` failed and ``controller_plan`` degraded to a blind
   ``["A"]`` plan (``parse_fallback``) on every cycle.

These tests drive the REAL ``controller_plan`` request/parse path with a
scripted client — no emulator, no network, no live LLM call — and cover model
resolution precedence (flag > env > default), think-token stripping, balanced
JSON extraction, and the single larger-budget retry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import cron_runner


@pytest.fixture(autouse=True)
def _no_controller_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize ambient controller-model env vars for every test here.

    A developer (or the fleet) may export these, which would silently change
    the "default" assertions below. Names are literals on purpose: a fixture
    must not depend on a symbol the change under test introduces, or every
    test would error (instead of failing for its own reason) when run against
    the pre-fix code. ``test_env_var_names_are_the_documented_pair`` pins the
    constant to this list.
    """
    for name in ("CRON_CONTROLLER_MODEL", "POKE_CONTROLLER_MODEL"):
        monkeypatch.delenv(name, raising=False)


class _RecordingClient:
    """OpenRouterClient stand-in: records each call's kwargs, replays a script.

    The last scripted response repeats when ``controller_plan`` calls again
    (the GAP-052 retry), so ``calls`` is the retry-observability surface.
    """

    def __init__(self, *responses: str | None) -> None:
        self.responses: list[str | None] = list(responses) or [None]
        self.calls: list[dict[str, Any]] = []

    def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return {"content": self.responses[index]}

    @property
    def models(self) -> list[Any]:
        return [call.get("model") for call in self.calls]


def _plan(client: _RecordingClient, **kwargs: Any) -> dict[str, Any]:
    """Run the real controller prompt/parse path over the scripted response."""
    return cron_runner.controller_plan(
        client, {"map_name": "Pallet Town"}, "", "", **kwargs
    )


CLEAN_PLAN = '{"plan": ["UP", "A"], "intent": "walk north to Route 1"}'
DEEPSEEK_STYLE = (
    "<think>The player is in Oak's Lab; the north door is an exit.</think>\n"
    '{"plan": ["UP", "UP", "A"], "intent": "head north out of the lab", '
    '"note": "Oak\'s Lab north door leads out."}|end_of_thought|'
)


# ── model resolution precedence ─────────────────────────────────────


class TestControllerModelResolution:
    """flag > CRON_CONTROLLER_MODEL > POKE_CONTROLLER_MODEL > default."""

    def test_default_is_the_unchanged_luna_string(self) -> None:
        assert cron_runner.DEFAULT_CONTROLLER_MODEL == "openai/gpt-5.6-luna"
        assert cron_runner.resolve_controller_model(None) == "openai/gpt-5.6-luna"
        assert cron_runner.resolve_controller_model() == "openai/gpt-5.6-luna"

    def test_env_var_names_are_the_documented_pair(self) -> None:
        # Pins the constant the autouse fixture spells out literally.
        assert cron_runner.CONTROLLER_MODEL_ENV_VARS == (
            "CRON_CONTROLLER_MODEL",
            "POKE_CONTROLLER_MODEL",
        )

    def test_flag_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CRON_CONTROLLER_MODEL", "deepseek-chat")
        assert (
            cron_runner.resolve_controller_model("deepseek-reasoner")
            == "deepseek-reasoner"
        )

    def test_env_used_when_no_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CRON_CONTROLLER_MODEL", "deepseek-chat")
        assert cron_runner.resolve_controller_model(None) == "deepseek-chat"

    def test_gap049_env_kept_working(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # GAP-049 shipped POKE_CONTROLLER_MODEL; GAP-052 extends, never replaces.
        monkeypatch.setenv("POKE_CONTROLLER_MODEL", "poke-controller")
        assert cron_runner.resolve_controller_model(None) == "poke-controller"

    def test_cron_env_beats_the_gap049_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("POKE_CONTROLLER_MODEL", "poke-controller")
        monkeypatch.setenv("CRON_CONTROLLER_MODEL", "deepseek-chat")
        assert cron_runner.resolve_controller_model(None) == "deepseek-chat"

    def test_blank_values_fall_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # An empty flag/env must not become an empty model name.
        monkeypatch.setenv("CRON_CONTROLLER_MODEL", "   ")
        assert (
            cron_runner.resolve_controller_model("")
            == cron_runner.DEFAULT_CONTROLLER_MODEL
        )
        monkeypatch.setenv("POKE_CONTROLLER_MODEL", "poke-controller")
        assert cron_runner.resolve_controller_model(" ") == "poke-controller"

    def test_values_are_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CRON_CONTROLLER_MODEL", "  deepseek-chat  ")
        assert cron_runner.resolve_controller_model(None) == "deepseek-chat"
        assert (
            cron_runner.resolve_controller_model(" deepseek-reasoner ")
            == "deepseek-reasoner"
        )

    def test_source_reports_the_winning_layer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert cron_runner._controller_model_override(None) is None
        monkeypatch.setenv("CRON_CONTROLLER_MODEL", "deepseek-chat")
        assert cron_runner._controller_model_override(None) == (
            "deepseek-chat",
            "env CRON_CONTROLLER_MODEL",
        )
        assert cron_runner._controller_model_override("x") == (
            "x",
            "flag --controller-model",
        )


# ── the model reaches the client ────────────────────────────────────


class TestModelReachesTheClient:
    """Acceptance 1: flag/env change the request; absence changes nothing."""

    def test_default_request_is_byte_identical_to_pre_gap052(self) -> None:
        client = _RecordingClient(CLEAN_PLAN)

        decision = _plan(client)

        assert len(client.calls) == 1  # a clean answer is never retried
        call = client.calls[0]
        assert call["model"] == "openai/gpt-5.6-luna"
        assert call["temperature"] == 0.3
        assert call["max_tokens"] == 300 == cron_runner.CONTROLLER_MAX_TOKENS
        assert call["thinking"] == {"type": "disabled"}
        assert decision["plan"] == ["UP", "A"]
        assert decision["intent"] == "walk north to Route 1"

    def test_flag_model_reaches_the_client(self) -> None:
        client = _RecordingClient(CLEAN_PLAN)

        _plan(client, model="deepseek-chat")

        assert client.models == ["deepseek-chat"]

    def test_env_model_reaches_the_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CRON_CONTROLLER_MODEL", "deepseek-chat")
        client = _RecordingClient(CLEAN_PLAN)

        _plan(client)

        assert client.models == ["deepseek-chat"]

    def test_env_model_reaches_the_client_through_main_plumbing(self) -> None:
        # The CLI parser is the only way a flag enters the process; main()
        # then resolves it and hands the result to controller_plan. main()
        # itself boots an emulator, so the wiring is asserted against the
        # module source read from DISK — inspect.getsource() of a live function
        # resolves through linecache line numbers, which drift (and return an
        # unrelated function) if the file is edited while the suite runs.
        args = cron_runner._main_parser().parse_args(
            ["--controller-model", "deepseek-chat"]
        )
        assert args.controller_model == "deepseek-chat"
        assert cron_runner._main_parser().parse_args([]).controller_model is None

        source = Path(str(cron_runner.__file__)).read_text(encoding="utf-8")
        assert "resolve_controller_model(args.controller_model)" in source
        assert "model=controller_model," in source

    def test_retry_uses_the_same_override(self) -> None:
        client = _RecordingClient("the model rambled", CLEAN_PLAN)

        decision = _plan(client, model="deepseek-chat")

        assert client.models == ["deepseek-chat", "deepseek-chat"]
        assert decision["plan"] == ["UP", "A"]


# ── --dry-run reports what the run would use ────────────────────────


class TestDryRunReportsTheModel:
    """The summary line must name the resolved model (and stay stable)."""

    @pytest.fixture(autouse=True)
    def _offline(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        # No dotenv load, no configured keys, no network (mirrors GAP-048 tests).
        monkeypatch.setattr(cron_runner, "_load_dotenv_stdlib", lambda: None)
        for name in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        rom = tmp_path / "rom.gb"
        rom.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(rom))
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", tmp_path / "boot.state")
        (tmp_path / "boot.state").write_bytes(b"x")

    def _model_line(self, capsys: pytest.CaptureFixture[str], argv: list[str]) -> str:
        with pytest.raises(SystemExit) as exit_info:
            cron_runner._dry_run_precheck(argv)
        assert exit_info.value.code == 0
        lines = [
            line
            for line in capsys.readouterr().out.splitlines()
            if "Model/provider:" in line
        ]
        assert len(lines) == 1, f"expected one Model/provider line, got {lines}"
        return lines[0]

    def test_no_override_line_is_byte_identical(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        line = self._model_line(capsys, ["--dry-run"])
        assert line == (
            "  Model/provider: controller=openai/gpt-5.6-luna (OpenRouter) · "
            "state_window=deepseek-v4-flash (api.deepseek.com when DEEPSEEK_API_KEY "
            "set, else OpenRouter) · cartographer=google/gemma-3-12b-it (only when "
            "USE_RAM_READER=False)"
        )

    def test_flag_is_reported_with_its_source(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        line = self._model_line(
            capsys, ["--dry-run", "--controller-model", "deepseek-chat"]
        )
        assert "controller=deepseek-chat (flag --controller-model;" in line

    def test_env_override_is_reported(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("CRON_CONTROLLER_MODEL", "deepseek-chat")
        line = self._model_line(capsys, ["--dry-run"])
        assert "controller=deepseek-chat (env CRON_CONTROLLER_MODEL;" in line


# ── think-token stripping + JSON extraction ─────────────────────────


class TestNoisyResponseParsing:
    """Acceptance 2: deepseek-style noise must parse into a real plan."""

    def test_inline_think_block_is_stripped(self) -> None:
        client = _RecordingClient(DEEPSEEK_STYLE)

        decision = _plan(client)

        assert decision["plan"] == ["UP", "UP", "A"]
        assert decision["intent"] == "head north out of the lab"
        assert decision["intent"] not in cron_runner.FALLBACK_INTENTS
        assert "<think>" not in decision["raw_response"]

    def test_fenced_think_block_is_stripped(self) -> None:
        client = _RecordingClient(
            "```json\n<think>The exit is east.</think>\n"
            '{"plan": ["RIGHT"], "intent": "go east"}\n```'
        )

        decision = _plan(client)

        assert decision["plan"] == ["RIGHT"]

    def test_bare_closing_think_tag_is_stripped(self) -> None:
        client = _RecordingClient('{"plan": ["A"], "intent": "talk"}</think>')

        decision = _plan(client)

        assert decision["plan"] == ["A"]
        assert decision["intent"] == "talk"

    def test_end_of_thought_markers_stripped_inline_and_trailing(self) -> None:
        client = _RecordingClient(
            '|end_of_thought|{"plan": ["LEFT"], "intent": "west"}|end_of_thought|'
        )

        decision = _plan(client)

        assert decision["plan"] == ["LEFT"]
        assert "end_of_thought" not in decision["raw_response"]

    def test_trailing_partial_marker_after_the_brace_is_dropped(self) -> None:
        client = _RecordingClient(
            '{"plan": ["UP", "UP"], "intent": "north"} |end_of_th<'
        )

        decision = _plan(client)

        assert decision["plan"] == ["UP", "UP"]

    def test_prose_around_the_json_object_is_tolerated(self) -> None:
        client = _RecordingClient(
            'Sure! Let me think.\n{"plan": ["START"], "intent": "menu"}\nDone.'
        )

        decision = _plan(client)

        assert decision["plan"] == ["START"]
        assert decision["intent"] == "menu"

    def test_nested_json_object_is_kept_whole(self) -> None:
        # The pre-GAP-052 r"\{[^}]+\}" regex truncated at the first "}".
        client = _RecordingClient(
            '{"plan": ["A"], "meta": {"blocked": {"up": true}}, "intent": "nested"}'
        )

        decision = _plan(client)

        assert decision["plan"] == ["A"]
        assert decision["meta"] == {"blocked": {"up": True}}

    def test_brace_inside_a_string_does_not_truncate(self) -> None:
        client = _RecordingClient('{"plan": ["B"], "intent": "use } carefully"}')

        decision = _plan(client)

        assert decision["plan"] == ["B"]
        assert decision["intent"] == "use } carefully"

    def test_marker_inside_a_json_value_is_preserved(self) -> None:
        # Marker-shaped text inside a string is data, not transport noise.
        client = _RecordingClient(
            '{"plan": ["A"], "intent": "walk to the |end| of the path"}'
        )

        decision = _plan(client)

        assert decision["intent"] == "walk to the |end| of the path"

    def test_agent_memory_fields_survive_the_noise_strip(self) -> None:
        # note/goal/study drive the DuckBrain memory writes in the main loop.
        client = _RecordingClient(DEEPSEEK_STYLE)

        decision = _plan(client)

        assert decision["note"] == "Oak's Lab north door leads out."

    def test_legacy_button_format_is_still_accepted(self) -> None:
        client = _RecordingClient(
            '<think>just a leg press</think>{"button": "A", "intent": "talk"}'
        )

        decision = _plan(client)

        assert decision["plan"] == ["A"]
        assert decision["intent"] == "talk"

    def test_clean_response_is_not_retried(self) -> None:
        client = _RecordingClient(CLEAN_PLAN, CLEAN_PLAN)

        _plan(client)

        assert len(client.calls) == 1


# ── one retry with a larger budget ──────────────────────────────────


class TestParseFailureRetry:
    """Acceptance 2: exactly one retry, with max_tokens + 100."""

    def test_retry_recovers_a_plan_after_garbage(self) -> None:
        client = _RecordingClient(
            "the model rambled and never emitted JSON", CLEAN_PLAN
        )

        decision = _plan(client)

        assert decision["plan"] == ["UP", "A"]
        assert decision["intent"] == "walk north to Route 1"
        assert decision["intent"] not in cron_runner.FALLBACK_INTENTS
        assert len(client.calls) == 2
        assert client.calls[0]["max_tokens"] == cron_runner.CONTROLLER_MAX_TOKENS
        assert (
            client.calls[1]["max_tokens"]
            == cron_runner.CONTROLLER_MAX_TOKENS
            + cron_runner.CONTROLLER_RETRY_TOKEN_BUMP
        )
        assert client.calls[1]["temperature"] == 0.3

    def test_retry_resends_the_same_prompt(self) -> None:
        client = _RecordingClient("no json here", CLEAN_PLAN)

        _plan(client)

        assert client.calls[1]["messages"] == client.calls[0]["messages"]
        assert client.calls[1]["thinking"] == client.calls[0]["thinking"]

    def test_retry_recovers_after_a_noisy_first_answer(self) -> None:
        # The first answer is truncated mid-think; the retry completes.
        client = _RecordingClient(
            "<think>I should head north but I am not", DEEPSEEK_STYLE
        )

        decision = _plan(client)

        assert decision["plan"] == ["UP", "UP", "A"]
        assert len(client.calls) == 2

    def test_planless_json_is_retried_then_falls_back_to_parse_fallback(self) -> None:
        client = _RecordingClient('{"thought": "I am not sure what to do"}')

        decision = _plan(client)

        assert len(client.calls) == 2
        assert decision["plan"] == ["A"]
        assert decision["intent"] == "parse_fallback"  # GAP-053 label preserved

    def test_double_failure_falls_back_to_parse_failure_fallback(self) -> None:
        client = _RecordingClient("the model rambled and never emitted JSON")

        decision = _plan(client)

        assert decision["plan"] == ["A"]
        assert decision["intent"] == "parse_failure_fallback"

    def test_at_most_one_retry(self) -> None:
        client = _RecordingClient("rambling one", "rambling two", "rambling three")

        decision = _plan(client)

        assert len(client.calls) == 2
        assert decision["intent"] == "parse_failure_fallback"

    def test_empty_retry_keeps_the_first_diagnosis(self) -> None:
        client = _RecordingClient('{"thought": "no plan"}', "")

        decision = _plan(client)

        assert decision["intent"] == "parse_fallback"
        assert decision["raw_response"] == '{"thought": "no plan"}'

    def test_missing_content_is_treated_as_a_parse_failure(self) -> None:
        client = _RecordingClient(None, CLEAN_PLAN)

        decision = _plan(client)

        assert decision["plan"] == ["UP", "A"]
        assert len(client.calls) == 2


# ── the helpers themselves ──────────────────────────────────────────


class TestStripHelpers:
    """Direct unit coverage for the strip/extract primitives."""

    def test_strip_removes_think_blocks_and_markers(self) -> None:
        stripped = cron_runner._strip_model_noise(DEEPSEEK_STYLE)
        assert "<think>" not in stripped and "</think>" not in stripped
        assert "end_of_thought" not in stripped
        assert stripped.startswith('{"plan"')

    def test_strip_of_empty_and_clean_text(self) -> None:
        assert cron_runner._strip_model_noise("") == ""
        assert cron_runner._strip_model_noise(CLEAN_PLAN) == CLEAN_PLAN

    def test_extract_first_json_object_handles_nesting_and_escapes(self) -> None:
        assert (
            cron_runner._extract_first_json_object('junk {"a": {"b": "}"}} tail')
            == '{"a": {"b": "}"}}'
        )
        escaped = '{"a": "escaped \\"quote\\" inside"}'
        assert cron_runner._extract_first_json_object(f"noise {escaped}") == escaped
        # An unterminated object is not "extracted" as a truncated fragment.
        assert (
            cron_runner._extract_first_json_object('{"a": "escaped \\" } tail') is None
        )
        assert cron_runner._extract_first_json_object("no braces at all") is None

    def test_interpret_kinds(self) -> None:
        assert cron_runner._interpret_controller_response(CLEAN_PLAN)[0] == "plan"
        assert (
            cron_runner._interpret_controller_response('{"button": "A"}')[0] == "button"
        )
        assert (
            cron_runner._interpret_controller_response('{"thought": "x"}')[0]
            == "unreadable"
        )
        assert (
            cron_runner._interpret_controller_response("not json")[0] == "unparseable"
        )
        # A non-object JSON value is "readable but no plan" — parse_fallback,
        # exactly as before GAP-052.
        assert cron_runner._interpret_controller_response("[1, 2]")[0] == "unreadable"
