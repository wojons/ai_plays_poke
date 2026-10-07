"""PERCEPT-1: vision usage rollup and summary-tail tests.

The vision path (cartographer + controller plans) now carries the
provider's usage block per call; these tests pin the per-run aggregation
and the final summary wording, including the None-preserving contract
("provider did not price this" must stay distinguishable from 0).
"""

from cron_runner import (
    _extract_vision_usage,
    _rollup_vision_usage,
    _sum_vision_usage,
    _format_summary,
)

import pytest


class TestExtractVisionUsage:
    def test_none_for_non_dict_response(self) -> None:
        assert _extract_vision_usage(None) is None
        assert _extract_vision_usage("boom") is None

    def test_normalizes_the_provider_block(self) -> None:
        usage = _extract_vision_usage(
            {
                "content": "x",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "cost": 0.01,
                },
            }
        )
        assert usage is not None
        assert usage["prompt_tokens"] == 10
        assert usage["completion_tokens"] == 5
        assert usage["total_tokens"] == 15
        assert usage["cost_usd"] == pytest.approx(0.01)

    def test_none_when_usage_absent(self) -> None:
        assert _extract_vision_usage({"content": "x"}) is None


class TestSumVisionUsage:
    def test_sum_two_blocks(self) -> None:
        left = {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "image_tokens": 80,
            "cost_usd": 0.2,
        }
        right = {
            "prompt_tokens": 50,
            "completion_tokens": 20,
            "total_tokens": 70,
            "image_tokens": None,
            "cost_usd": 0.1,
        }
        summed = _sum_vision_usage(left, right)
        assert summed["prompt_tokens"] == 150
        assert summed["completion_tokens"] == 30
        assert summed["total_tokens"] == 180
        assert summed["image_tokens"] == 80
        assert summed["cost_usd"] == pytest.approx(0.3)

    def test_none_operand_passes_through(self) -> None:
        block = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        assert _sum_vision_usage(None, block) is block
        assert _sum_vision_usage(block, None) is block
        assert _sum_vision_usage(None, None) is None

    def test_unpriced_cost_stays_none(self) -> None:
        left = {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "cost_usd": None,
        }
        right = {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "cost_usd": None,
        }
        assert _sum_vision_usage(left, right)["cost_usd"] is None


class TestRollupVisionUsage:
    def test_empty_results_yield_zeroed_rollup(self) -> None:
        rollup = _rollup_vision_usage([])
        assert rollup["calls"] == 0
        assert rollup["prompt_tokens"] == 0
        assert rollup["cost_usd"] is None
        assert rollup["image_tokens"] is None

    def test_sums_decision_and_cartographer_usage(self) -> None:
        results = [
            {
                "intent": "walk down",
                "vision_usage": {
                    "prompt_tokens": 2000,
                    "completion_tokens": 50,
                    "total_tokens": 2050,
                    "image_tokens": 1024,
                    "cost_usd": 0.005,
                },
                "_cartographer_usage": {
                    "prompt_tokens": 3000,
                    "completion_tokens": 200,
                    "total_tokens": 3200,
                    "image_tokens": 2048,
                    "cost_usd": 0.002,
                },
            },
            {
                "intent": "parse_fallback",
                "vision_usage": None,
                "_cartographer_usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 10,
                    "total_tokens": 110,
                    "image_tokens": None,
                    "cost_usd": None,
                },
            },
            {"event": "state_saved"},  # non-decision row, no usage keys
        ]
        rollup = _rollup_vision_usage(results)
        assert rollup["calls"] == 3
        assert rollup["prompt_tokens"] == 5100
        assert rollup["completion_tokens"] == 260
        assert rollup["total_tokens"] == 5360
        assert rollup["image_tokens"] == 3072
        assert rollup["cost_usd"] == pytest.approx(0.007)

    def test_all_unpriced_run_keeps_cost_none(self) -> None:
        results = [
            {
                "intent": "x",
                "vision_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "image_tokens": None,
                    "cost_usd": None,
                },
                "_cartographer_usage": None,
            }
        ]
        rollup = _rollup_vision_usage(results)
        assert rollup["calls"] == 1
        assert rollup["total_tokens"] == 15
        assert rollup["cost_usd"] is None


class TestFormatSummaryVisionTail:
    BASE_KWARGS = {
        "real_decisions": 3,
        "fallback_decisions": 1,
    }

    def test_no_vision_usage_keeps_line_unchanged(self) -> None:
        s = _format_summary("run1", 20, {"overworld"}, 5, 20, 3)
        assert "vision:" not in s
        assert "[run1] Done. 20 actions." in s

    def test_priced_run_states_tokens_and_cost(self) -> None:
        s = _format_summary(
            "run1",
            20,
            {"overworld"},
            0,
            20,
            3,
            vision_usage={
                "prompt_tokens": 5100,
                "completion_tokens": 260,
                "total_tokens": 5360,
                "image_tokens": 3072,
                "cost_usd": 0.007,
                "calls": 3,
            },
        )
        assert (
            "vision: 5100 prompt + 260 completion tokens (3072 image) "
            "across 3 calls, cost $0.007000"
        ) in s
        assert "[run1] Done. 20 actions." in s  # legacy head intact

    def test_unpriced_run_says_unknown_not_zero(self) -> None:
        s = _format_summary(
            "run1",
            20,
            {"overworld"},
            0,
            20,
            3,
            vision_usage={
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "image_tokens": None,
                "cost_usd": None,
                "calls": 1,
            },
        )
        assert "(unknown image) across 1 calls, cost unknown" in s
