"""Unit tests for decision.py — DecisionLoop orchestration of vision → prompt → thinking → execution."""

from unittest.mock import MagicMock, patch, call

import numpy as np

from src.core.decision import DecisionLoop


# ── Helpers ──────────────────────────────────────────────────────────────

def mock_screenshot():
    """Return a small numpy array representing a GBA screenshot."""
    return np.zeros((240, 160, 3), dtype=np.uint8)


def create_decision_loop(**overrides):
    """Create a DecisionLoop with all dependencies mocked."""
    with (
        patch("src.core.decision.VisionClient"),
        patch("src.core.decision.PromptStack"),
        patch("src.core.decision.GameMemory"),
        patch("src.core.decision.OpenRouterClient"),
        patch("src.core.decision.Path.mkdir"),
        patch("src.core.decision.Image"),
        patch("src.core.decision.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.strftime.return_value = "20260101_000000"
        mock_emu = MagicMock()
        mock_emu.capture.return_value = mock_screenshot()

        loop = DecisionLoop(
            emulator=mock_emu,
            generation=overrides.get("generation", "gen1"),
            thinking_model=overrides.get("thinking_model", "openrouter/owl-alpha"),
            vision_model=overrides.get("vision_model", "google/gemma-3-12b-it"),
        )

        # Store mock references for assertions
        loop._mock_emu = mock_emu
        loop._mock_vision = loop.vision
        loop._mock_prompt = loop.prompt_stack
        loop._mock_memory = loop.memory
        loop._mock_client = loop.client

        yield loop


# ── Constructor ──────────────────────────────────────────────────────────

class TestConstructor:
    """Test DecisionLoop.__init__."""

    def test_creates_screenshots_directory(self):
        with (
            patch("src.core.decision.VisionClient"),
            patch("src.core.decision.PromptStack"),
            patch("src.core.decision.GameMemory"),
            patch("src.core.decision.OpenRouterClient"),
            patch("src.core.decision.Path.mkdir") as mock_mkdir,
            patch("src.core.decision.Image"),
            patch("src.core.decision.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "20260101_000000"
            emu = MagicMock()

            loop = DecisionLoop(emu)

            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
            assert loop._step_count == 0
            assert loop._last_vision == {"screen_type": "unknown"}

    def test_stores_generation_and_model(self):
        with (
            patch("src.core.decision.VisionClient"),
            patch("src.core.decision.PromptStack"),
            patch("src.core.decision.GameMemory"),
            patch("src.core.decision.OpenRouterClient"),
            patch("src.core.decision.Path.mkdir"),
            patch("src.core.decision.Image"),
            patch("src.core.decision.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "20260101_000000"
            emu = MagicMock()

            loop = DecisionLoop(emu, generation="gen3", thinking_model="test/model")

            assert loop.generation == "gen3"
            assert loop.thinking_model == "test/model"

    def test_run_id_is_generated(self):
        with (
            patch("src.core.decision.VisionClient"),
            patch("src.core.decision.PromptStack"),
            patch("src.core.decision.GameMemory"),
            patch("src.core.decision.OpenRouterClient"),
            patch("src.core.decision.Path.mkdir"),
            patch("src.core.decision.Image"),
            patch("src.core.decision.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "20260101_123456"
            emu = MagicMock()

            loop = DecisionLoop(emu)

            assert loop._run_id == "20260101_123456"


# ── step() — Happy Path ──────────────────────────────────────────────────

class TestStepHappyPath:
    """Test DecisionLoop.step() through the full pipeline with all components succeeding."""

    def test_step_increments_counter(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "assembled prompt"
            loop._mock_memory.snapshot.return_value = {"recent_actions": []}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray") as mock_img:
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "pressed a (5 frames)"
                mock_img.return_value.save = MagicMock()

                loop.step()
                assert loop._step_count == 1

                loop.step()
                assert loop._step_count == 2

    def test_step_captures_screenshot(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray") as mock_img:
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                loop.step()
                loop._mock_emu.capture.assert_called_once()
                mock_img.return_value.save.assert_called_once()

    def test_step_calls_vision_analyze(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                loop.step()
                loop._mock_vision.analyze.assert_called_once()
                call_args = loop._mock_vision.analyze.call_args
                assert call_args[1]["game"] == "gen1"

    def test_step_assemble_prompt_with_screen_type(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "battle", "enemy": "PIDGEY"}
            loop._mock_prompt.assemble.return_value = "battle prompt"
            loop._mock_memory.snapshot.return_value = {"active_goal": "win"}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                loop.step()
                loop._mock_prompt.assemble.assert_called_once()
                call_kw = loop._mock_prompt.assemble.call_args[1]
                assert call_kw["screen_type"] == "battle"
                assert "vision_output" in call_kw
                assert "memory_context" in call_kw

    def test_step_calls_thinking_model(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = "raw response"

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                loop.step()
                loop._mock_client.send_tool_request.assert_called_once()
                call_kw = loop._mock_client.send_tool_request.call_args[1]
                assert call_kw["prompt"] == "prompt"
                assert call_kw["model"] == "openrouter/owl-alpha"
                assert call_kw["max_tokens"] == 200
                assert call_kw["temperature"] == 0.3

    def test_step_executes_tool_call(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "wait", "arguments": {"frames": 30}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "wait", "arguments": {"frames": 30}}
                mock_exec.return_value = "waited 30 frames"

                loop.step()
                mock_exec.assert_called_once_with(
                    loop._mock_emu,
                    tool_name="wait",
                    arguments={"frames": 30},
                )

    def test_step_sets_success_on_good_result(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "pressed a (5 frames)"

                result = loop.step()
                assert result["success"] is True

    def test_step_records_action_in_memory(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "walked up 1 tile"

                loop.step()
                loop._mock_memory.record_action.assert_called_once_with("walked up 1 tile")

    def test_step_result_has_all_keys(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                result = loop.step()
                for key in ("vision", "screen_type", "prompt", "raw_response",
                            "tool_call", "action", "success", "screenshot", "run_dir"):
                    assert key in result, f"Missing key: {key}"


# ── step() — Vision Failure ──────────────────────────────────────────────

class TestStepVisionFailure:
    """Test DecisionLoop.step() when vision analysis fails."""

    def test_vision_failure_uses_fallback(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.side_effect = RuntimeError("vision failed")
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                result = loop.step()
                assert result["vision"] == {"screen_type": "unknown"}
                assert result["screen_type"] == "unknown"

    def test_vision_failure_preserves_last_known_state(self):
        for loop in create_decision_loop():
            # First step succeeds
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld", "location": "pallet"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                loop.step()

            # Second step: vision fails → uses _last_vision from step 1
            loop._mock_vision.analyze.side_effect = RuntimeError("vision failed")
            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                result = loop.step()
                assert result["vision"]["location"] == "pallet"


# ── step() — Prompt Assembly Failure ─────────────────────────────────────

class TestStepPromptFailure:
    """Test DecisionLoop.step() when prompt assembly fails."""

    def test_prompt_failure_falls_back_to_overworld(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "unknown_screen"}
            loop._mock_prompt.assemble.side_effect = [
                ValueError("no prompt for unknown_screen"),  # first call fails
                "overworld prompt",                          # fallback succeeds
            ]
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                result = loop.step()
                # Should have tried overworld on second call
                assert loop._mock_prompt.assemble.call_count == 2
                second_call_kw = loop._mock_prompt.assemble.call_args_list[1][1]
                assert second_call_kw["screen_type"] == "overworld"
                assert result["prompt"] == "overworld prompt"


# ── step() — Thinking Model Failure ──────────────────────────────────────

class TestStepThinkingFailure:
    """Test DecisionLoop.step() when the thinking model API fails."""

    def test_thinking_failure_uses_default_press_a(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.side_effect = RuntimeError("API down")

            with patch("src.core.decision.parse_tool_call"), \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_exec.return_value = "pressed a (5 frames)"

                result = loop.step()
                assert result["raw_response"] == ""
                # Default fallback: press A
                mock_exec.assert_called_once()
                call_kw = mock_exec.call_args[1]
                assert call_kw["tool_name"] == "press_button"
                assert call_kw["arguments"] == {"button": "a", "duration": 5}

    def test_thinking_failure_sets_success_based_on_exec_result(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.side_effect = RuntimeError("API down")

            with patch("src.core.decision.parse_tool_call"), \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_exec.return_value = "Error: button failed"

                result = loop.step()
                assert result["success"] is False  # "Error: ..." starts with "Error"


# ── step() — Tool Parse Failure ──────────────────────────────────────────

class TestStepToolParseFailure:
    """Test DecisionLoop.step() when tool call parsing fails."""

    def test_parse_failure_uses_default_press_a(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = "garbage response"

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = None  # parse fails
                mock_exec.return_value = "pressed a (5 frames)"

                result = loop.step()
                assert result["tool_call"] == {"name": "press_button", "arguments": {"button": "a", "duration": 5}}

    def test_empty_response_uses_default(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = ""  # empty

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_exec.return_value = "OK"

                result = loop.step()
                # parse_tool_call should NOT be called when raw_response is empty
                mock_parse.assert_not_called()
                assert result["tool_call"]["name"] == "press_button"


# ── step() — Execution Result Mapping ────────────────────────────────────

class TestStepExecutionResult:
    """Test DecisionLoop.step() success/failure detection from execute_tool_call output."""

    def test_error_result_maps_to_failure(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "Error: invalid button 'x'"

                result = loop.step()
                assert result["success"] is False
                assert result["action"] == "Error: invalid button 'x'"

    def test_non_error_result_maps_to_success(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "pressed a (5 frames)"

                result = loop.step()
                assert result["success"] is True


# ── run() ────────────────────────────────────────────────────────────────

class TestRun:
    """Test DecisionLoop.run() — the loop wrapper."""

    def test_run_calls_step_n_times(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                results = loop.run(max_steps=3, screenshot_interval=30)

                assert len(results) == 3
                loop._mock_emu.wait.assert_has_calls([call(30), call(30), call(30)])

    def test_run_handles_step_exception(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"), \
                 patch("src.core.decision.traceback.print_exc"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                # Step 2: execute_tool_call throws → step() propagates to run()'s handler
                mock_exec.side_effect = [
                    "OK",
                    RuntimeError("emulator crashed"),
                    "OK",
                ]

                results = loop.run(max_steps=3, screenshot_interval=10)

                assert len(results) == 3
                # The second result should be the error fallback from run()
                assert results[1]["success"] is False
                assert "[ERROR step 1]" in results[1]["action"]
                assert results[1]["screen_type"] == "unknown"

    def test_run_returns_list_of_dicts(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                results = loop.run(max_steps=2)
                assert isinstance(results, list)
                assert len(results) == 2
                for r in results:
                    assert isinstance(r, dict)


# ── Integration — Screenshot Paths ───────────────────────────────────────

class TestScreenshotPaths:
    """Test that screenshots are saved with correct paths."""

    def test_step_saves_screenshot_with_expected_path(self):
        for loop in create_decision_loop():
            loop._mock_vision.analyze.return_value = {"screen_type": "overworld"}
            loop._mock_prompt.assemble.return_value = "prompt"
            loop._mock_memory.snapshot.return_value = {}
            loop._mock_client.send_tool_request.return_value = '{"name": "press_button", "arguments": {"button": "a"}}'

            with patch("src.core.decision.parse_tool_call") as mock_parse, \
                 patch("src.core.decision.execute_tool_call") as mock_exec, \
                 patch("src.core.decision.Image.fromarray"):
                mock_parse.return_value = {"name": "press_button", "arguments": {"button": "a"}}
                mock_exec.return_value = "OK"

                result = loop.step()
                assert "step_0001.png" in result["screenshot"]
                assert "run_20260101_000000" in result["run_dir"]
