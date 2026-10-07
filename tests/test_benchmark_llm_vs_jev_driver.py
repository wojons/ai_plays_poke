"""BENCH-1 tests: the llm-vs-jev benchmark driver and its fail-closed guard.

All pure-function tests: parsed fixture rows shaped like real cron_runner
JSONL rows — no ROM, no emulator, no API calls, no subprocess launches
(run_episode / cmd_run are covered only via argv-planning and guard paths).

Load-bearing contracts under test:

  G1  a benchmark-labelled episode row with ANY jev_answered=True decision
      row in the llm arm is REJECTED (fail closed, never scored)
  G2  the guard proves itself non-vacuous: a clean llm row and a jev arm
      (where jev_answered=True is the EXPECTED state) both pass
  G3  report refuses to write an artifact from a rejected battery
  M   one command plans BOTH arms from the same boot state and cycle budget,
      interleaved, with distinct run ids
  T   the comparison table is regenerated from arm logs alone: every figure
      in an artifact traces to fixture rows, nothing hand-entered, and
      measurements the logs cannot support are null WITH a reason
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import benchmark_llm_vs_jev as bench  # noqa: E402


# ── fixtures shaped like real runner rows ────────────────────────────────────


def _llm_decision_row(cycle=1, map_name="Pallet Town", **overrides):
    """A pure-LLM decision row: intent present, jev_answered False by design."""
    row = {
        "cycle": cycle,
        "screen": "overworld",
        "pipeline": "agentic_tools",
        "decision_mode": "llm",
        "decision_mode_family": "system2",
        "agentic_tools_enabled": True,
        "agentic_tool_calls": 0,
        "plan": ["UP"],
        "intent": "walk somewhere sensible",
        "jev_answered": False,
        "jev_ok": None,
        "escalated": False,
        "missing_class": None,
        "map_name": map_name,
        "player_tile_x": 5,
        "player_tile_y": 8,
    }
    row.update(overrides)
    return row


def _jev_decision_row(cycle=1, map_name="Pallet Town", **overrides):
    row = {
        "cycle": cycle,
        "screen": "overworld",
        "pipeline": "jev",
        "decision_mode": "jev",
        "decision_mode_family": "system1+system2",
        "agentic_tools_enabled": False,
        "agentic_tool_calls": 0,
        "plan": ["UP"],
        "intent": "jev UP",
        "jev_answered": True,
        "jev_ok": True,
        "escalated": False,
        "missing_class": "none",
        "map_name": map_name,
        "player_tile_x": 5,
        "player_tile_y": 8,
    }
    row.update(overrides)
    return row


def _autonomy_row(decisions=3, escalated=0, mode="llm", teacher_count=0):
    tools_enabled = mode == "llm"
    pipeline = "agentic_tools" if tools_enabled else "jev"
    return {
        "run_id": "bench1_llm_ep1_x",
        "event": "run_autonomy",
        "decisions_total": decisions,
        "jev_answered": 0 if mode == "llm" else decisions,
        "escalated": escalated,
        "autonomy_ratio": 0.0 if mode == "llm" else 1.0,
        "teacher_escalations": {"count": teacher_count, "improved": 0},
        "decision_mode": mode,
        "decision_mode_family": "system2" if mode == "llm" else "system1+system2",
        "agentic_tools_enabled": tools_enabled,
        "agentic_tool_calls": 0,
        "pipeline": pipeline,
        "pipeline_counts": {pipeline: decisions},
    }


def _teacher_row(model_build="typesafe/jev-1.13-20260917", cost_usd=0.0004):
    return {
        "cycle": 1,
        "event": "teacher_escalation",
        "patch": {"ok": True, "cost_usd": cost_usd},
        "post_ask": {"ok": True, "model_build": model_build},
    }


def _controller_cost_row(cost_usd=0.002):
    """A controller decision row carrying its own LLM cost."""
    return _llm_decision_row(cost_usd=cost_usd)


def _write_log(tmp_path, rows, name="run_x.jsonl"):
    p = tmp_path / name
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def _episode_row(**overrides):
    """A complete benchmark episode row (as run_episode would emit)."""
    row = {
        "at": "2026-09-28T00:00:00Z",
        "run_id": "bench1_llm_ep1_20260928",
        "arm": "llm",
        "episode": 1,
        "exit_code": 0,
        "wall_time_s": 25.0,
        "cycles_requested": 5,
        "boot_state": "data/boot.state",
        "boot_sha256": "a" * 64,
        "ram_md5_before_episode": None,
        "cycles": 5,
        "decisions": 5,
        "real_decisions": 5,
        "fallback_decisions": 0,
        "jev_answered": 0,
        "jev_answered_true_rows": [],
        "escalated": 0,
        "jev_transport_failures": 0,
        "jev_error_rows": 0,
        "missing_classes": {},
        "teacher_calls": 0,
        "teacher_improved": 0,
        "model_build": None,
        "cost_usd_observed": 0.01,
        "tiles_visited_distinct": 4,
        "map_sequence": [{"cycle": 1, "map": "Pallet Town"}],
        "maps_seen": ["Pallet Town"],
        "map_transitions": [],
        "first_map_transition_cycle": None,
        "final_map": "Pallet Town",
        "recovery_events": 1,
        "lock_warn_cycles": 1,
        "lock_total_cycles": 5,
        "lock_rate": 0.2,
        "autonomy": {
            "decisions_total": 5,
            "jev_answered": 0,
            "escalated": 0,
            "autonomy_ratio": 0.0,
            "teacher_escalations": {"count": 0, "improved": 0},
        },
        "decision_mode_log": "llm",
        "decision_mode": "llm",
        "decision_mode_family": "system2",
        "agentic_tools_enabled": True,
        "agentic_tool_calls": 0,
        "pipeline": "agentic_tools",
        "pipeline_counts": {"agentic_tools": 5},
        "surface_stamp_mismatches": [],
        "run_completed": True,
        "errors": [],
    }
    row.update(overrides)
    bench.guard_benchmark_row(row)
    return row


def _battery_rows(n=2, cycles=5):
    """A clean two-arm episode log (llm + jev interleaved rows)."""
    _ = cycles
    rows = []
    for i in range(1, n + 1):
        rows.append(
            _episode_row(
                run_id=f"bench1_llm_ep{i}_20260928",
                arm="llm",
                episode=i,
                decisions=4 + i,
                real_decisions=4 + i,
                pipeline_counts={"agentic_tools": 4 + i},
                autonomy={
                    "decisions_total": 4 + i,
                    "jev_answered": 0,
                    "escalated": 0,
                    "autonomy_ratio": 0.0,
                    "teacher_escalations": {"count": 0, "improved": 0},
                },
            )
        )
        rows.append(
            _episode_row(
                run_id=f"bench1_jev_ep{i}_20260928",
                arm="jev",
                episode=i,
                decisions=6 + i,
                real_decisions=0,
                fallback_decisions=1,
                jev_answered=6 + i,
                escalated=2,
                teacher_calls=2,
                teacher_improved=1,
                cost_usd_observed=0.0004,
                lock_warn_cycles=0,
                lock_total_cycles=5,
                lock_rate=0.0,
                autonomy={
                    "decisions_total": 6 + i,
                    "jev_answered": 6 + i,
                    "escalated": 2,
                    "autonomy_ratio": 1.0,
                    "teacher_escalations": {"count": 2, "improved": 1},
                },
                decision_mode_log="jev",
                decision_mode="jev",
                decision_mode_family="system1+system2",
                agentic_tools_enabled=False,
                pipeline="jev",
                pipeline_counts={"jev": 6 + i},
            )
        )
    return rows


# ────────────────────────────────────── M: one command, both arms, one budget


class TestPlanRuns:
    def test_plans_both_arms_interleaved_from_one_budget(self):
        plan = bench.plan_runs(("llm", "jev"), 3, "bench1", "20260928")
        assert [p[0] for p in plan] == [
            "llm",
            "jev",
            "llm",
            "jev",
            "llm",
            "jev",
        ], "arms must interleave episode-by-episode"
        assert len(plan) == 6
        # every episode number appears once per arm
        for ep in (1, 2, 3):
            assert sorted(m for m, e, _ in plan if e == ep) == ["jev", "llm"]

    def test_run_ids_distinct_and_arm_stamped(self):
        plan = bench.plan_runs(("llm", "jev"), 2, "bench1", "20260928")
        ids = [run_id for _, _, run_id in plan]
        assert len(set(ids)) == len(ids), "duplicate run ids would collide logs"
        assert ids[0] == "bench1_llm_ep1_20260928"
        assert ids[1] == "bench1_jev_ep1_20260928"

    def test_argv_stamps_boot_state_cycles_and_mode(self, tmp_path):
        argv = bench._episode_argv(
            "llm", "run_x", 7, tmp_path / "boot.state", "python3"
        )
        assert any(a.endswith("cron_runner.py") for a in argv)
        i = argv.index("--decision-mode")
        assert argv[i + 1] == "llm"
        j = argv.index("--boot-state")
        assert argv[j + 1] == str(tmp_path / "boot.state")
        k = argv.index("--cycles")
        assert argv[k + 1] == "7"


# ───────────────────────────────────────── T: metrics from logs alone


class TestEpisodeMetricsFromLog:
    def test_efficiency_fields_mirror_the_run_autonomy_row(self, tmp_path):
        autonomy = {
            **_autonomy_row(decisions=4, mode="llm"),
            "map_transitions_observed": 2,
            "decisions_per_map_transition": 2.0,
            "state_comparisons": 3,
            "backtrack_events": 1,
            "backtrack_rate": 0.3333,
        }

        metrics = bench.episode_metrics_from_log(
            _write_log(tmp_path, [_llm_decision_row(), autonomy])
        )

        assert metrics["map_transitions_observed"] == 2
        assert metrics["decisions_per_map_transition"] == 2.0
        assert metrics["state_comparisons"] == 3
        assert metrics["backtrack_events"] == 1
        assert metrics["backtrack_rate"] == 0.3333
        assert metrics["autonomy"]["decisions_per_map_transition"] == 2.0
        assert metrics["autonomy"]["backtrack_rate"] == 0.3333

    def test_both_modes_stamp_comparable_tool_loop_fields(self, tmp_path):
        llm_rows = [
            _llm_decision_row(agentic_tool_calls=1),
            {
                **_autonomy_row(decisions=1, mode="llm"),
                "agentic_tool_calls": 1,
                "pipeline_counts": {"agentic_tools": 1},
            },
        ]
        jev_rows = [_jev_decision_row(), _autonomy_row(decisions=1, mode="jev")]

        llm = bench.episode_metrics_from_log(
            _write_log(tmp_path, llm_rows, "run_llm.jsonl")
        )
        jev = bench.episode_metrics_from_log(
            _write_log(tmp_path, jev_rows, "run_jev.jsonl")
        )

        assert jev["decision_mode"] == "jev"
        assert jev["decision_mode_family"] == "system1+system2"
        assert jev["agentic_tools_enabled"] is False
        assert jev["agentic_tool_calls"] == 0
        assert jev["pipeline"] == "jev"
        assert llm["decision_mode"] == "llm"
        assert llm["decision_mode_family"] == "system2"
        assert llm["agentic_tools_enabled"] is True
        assert llm["agentic_tool_calls"] >= 0
        assert llm["pipeline"] == "agentic_tools"
        assert llm["surface_stamp_mismatches"] == []
        assert jev["surface_stamp_mismatches"] == []

    def test_summary_surface_disagreement_is_rejected(self, tmp_path):
        rows = [
            _llm_decision_row(agentic_tool_calls=1),
            {
                **_autonomy_row(decisions=1, mode="llm"),
                "agentic_tools_enabled": False,
                "agentic_tool_calls": 1,
                "pipeline_counts": {"agentic_tools": 1},
            },
        ]
        metrics = bench.episode_metrics_from_log(_write_log(tmp_path, rows))
        row = _episode_row(**metrics)

        assert metrics["surface_stamp_mismatches"] == [
            {
                "field": "agentic_tools_enabled",
                "decision_rows": True,
                "run_autonomy": False,
            }
        ]
        assert row["guard"]["status"] == "rejected"
        assert row["guard"]["code"] == bench.REJECT_SURFACE_STAMP_MISMATCH

    def test_counts_controller_decisions_in_llm_arm(self, tmp_path):
        """The llm arm's decisions come from cron_runner's intent-row population
        (not the escalation-only population that undercounted ctrlwin)."""
        rows = [
            _llm_decision_row(1, "Pallet Town"),
            _llm_decision_row(2, "Pallet Town"),
            _llm_decision_row(3, "Route 1"),
            _autonomy_row(decisions=3, mode="llm"),
        ]
        m = bench.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["decisions"] == 3, (
            "controller decisions must be counted from intent rows, so the "
            "llm arm's decision count cannot collapse to 0"
        )
        assert m["real_decisions"] == 3
        assert m["fallback_decisions"] == 0
        assert m["jev_answered"] == 0
        assert m["decision_mode_log"] == "llm"
        assert m["run_completed"] is True

    def test_fallback_intents_split_from_real(self, tmp_path):
        rows = [
            _llm_decision_row(1, "Pallet Town", intent="parse_fallback"),
            _llm_decision_row(2, "Pallet Town"),
            _llm_decision_row(3, "Pallet Town", intent="parse_failure_fallback"),
        ]
        m = bench.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["decisions"] == 3
        assert m["real_decisions"] == 1
        assert m["fallback_decisions"] == 2

    def test_jev_arm_counts_answers_escalations_teacher_and_model(self, tmp_path):
        rows = [
            _jev_decision_row(1, "Pallet Town"),
            _jev_decision_row(2, "Pallet Town", escalated=True, jev_ok=False),
            _teacher_row(model_build="typesafe/jev-1.13-20260917"),
            _autonomy_row(decisions=2, escalated=1, mode="jev", teacher_count=1),
        ]
        m = bench.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["decisions"] == 2
        assert m["jev_answered"] == 2
        assert m["escalated"] == 1
        assert m["jev_transport_failures"] == 1
        assert m["teacher_calls"] == 1
        assert m["model_build"] == "typesafe/jev-1.13-20260917"

    def test_cost_usd_summed_from_every_row_shape(self, tmp_path):
        rows = [
            _controller_cost_row(cost_usd=0.002),
            _teacher_row(cost_usd=0.0004),
            {"event": "run_autonomy", "decision_mode": "llm"},
        ]
        m = bench.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["cost_usd_observed"] == pytest.approx(0.0024)

    def test_tiles_maps_transitions_and_first_transition_cycle(self, tmp_path):
        rows = [
            _llm_decision_row(1, "Pallet Town", player_tile_x=5, player_tile_y=8),
            _llm_decision_row(2, "Pallet Town", player_tile_x=5, player_tile_y=8),
            _llm_decision_row(4, "Route 1", player_tile_x=2, player_tile_y=1),
        ]
        m = bench.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["tiles_visited_distinct"] == 2
        assert m["maps_seen"] == ["Pallet Town", "Route 1"]
        assert m["map_transitions"] == [
            {"cycle": 4, "from_map": "Pallet Town", "to_map": "Route 1"}
        ]
        assert m["first_map_transition_cycle"] == 4
        assert m["final_map"] == "Route 1"

    def test_lock_rate_parsed_from_stdout_log(self, tmp_path):
        log_path = _write_log(tmp_path, [_autonomy_row()])
        stdout = tmp_path / "run_x.stdout.log"
        stdout.write_text(
            "[x] Done. 5 actions. Screens: {'overworld'} "
            "| lock-rate: 1/5 cycles with direction-lock warnings (20%) "
            "| distinct tiles: 4 | real_decisions=5 fallback_decisions=0\n"
        )
        m = bench.episode_metrics_from_log(log_path, stdout)
        assert m["lock_warn_cycles"] == 1
        assert m["lock_total_cycles"] == 5
        assert m["lock_rate"] == 0.2

    def test_missing_stdout_leaves_lock_rate_null(self, tmp_path):
        m = bench.episode_metrics_from_log(
            _write_log(tmp_path, [_autonomy_row()]),
            tmp_path / "nope.stdout.log",
        )
        assert m["lock_rate"] is None
        assert m["lock_warn_cycles"] is None

    def test_missing_log_records_error(self, tmp_path):
        m = bench.episode_metrics_from_log(tmp_path / "nope.jsonl")
        assert m["errors"] == ["log missing"]
        assert m["decisions"] == 0

    def test_error_and_recovery_rows(self, tmp_path):
        rows = [
            {"cycle": 1, "event": "recovery", "strategy": "menu_redraw"},
            {"cycle": 2, "event": "recovery_exhausted", "reason": "tile-locked"},
            {"cycle": 3, "error": "boom"},
        ]
        m = bench.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["recovery_events"] == 2
        assert len(m["errors"]) == 2


# ────────────────────────────────────── G: the fail-closed purity guard


class TestBenchmarkGuard:
    def test_g1_rejects_jev_answered_true_in_llm_arm(self):
        row = _episode_row(
            jev_answered=1,
            jev_answered_true_rows=[
                {"cycle": 3, "map": "Pallet Town", "intent": "jev LEFT"}
            ],
        )
        assert row["guard"]["status"] == "rejected"
        assert row["guard"]["code"] == bench.REJECT_JEV_IN_PURE_LLM
        assert any("cycle 3" in r for r in row["guard"]["reasons"])

    def test_g2_clean_llm_row_passes(self):
        row = _episode_row()
        assert row["guard"]["status"] == "clean"
        assert row["guard"]["code"] is None

    def test_g2b_jev_arm_with_answers_is_the_expected_state_not_a_reject(self):
        """Non-vacuity control: the guard fires on WHERE jev_answered=True
        appears (the llm arm), never on the field itself."""
        row = _episode_row(
            arm="jev",
            decision_mode_log="jev",
            jev_answered=5,
            jev_answered_true_rows=[
                {"cycle": 1, "map": "Pallet Town", "intent": "jev UP"}
            ],
        )
        assert row["guard"]["status"] == "clean"

    def test_mode_mismatch_between_arg_and_log_is_rejected(self):
        row = _episode_row(decision_mode_log="jev")
        assert row["guard"]["status"] == "rejected"
        assert row["guard"]["code"] == bench.REJECT_MODE_MISMATCH

    def test_missing_mode_log_is_not_yet_a_reject(self):
        """A log missing its autonomy row has no mode evidence either way; the
        run-incomplete comparability note covers it instead."""
        row = _episode_row(decision_mode_log=None)
        assert row["guard"]["status"] == "clean"

    def test_guard_stamp_is_idempotent(self):
        row = _episode_row()
        first = dict(row["guard"])
        bench.guard_benchmark_row(row)
        assert row["guard"] == first

    def test_report_refuses_a_rejected_battery(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        rows = _battery_rows()
        rows[0]["jev_answered"] = 1
        rows[0]["jev_answered_true_rows"] = [
            {"cycle": 2, "map": "Pallet Town", "intent": "jev UP"}
        ]
        bench.guard_benchmark_row(rows[0])
        ep_log = tmp_path / "cron_logs" / "bench1_ep.jsonl"
        ep_log.parent.mkdir(parents=True)
        ep_log.write_text("".join(json.dumps(r) + "\n" for r in rows))
        rc = bench.cmd_report(ep_log)
        assert rc == 3, "a contaminated arm must fail closed, not be scored"
        out = capsys.readouterr().out
        assert bench.REJECT_JEV_IN_PURE_LLM in out
        assert not (tmp_path / "data" / "baselines").exists(), (
            "no artifact may be written from a rejected battery"
        )

    def test_report_refuses_mode_mismatch_too(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        rows = _battery_rows()
        rows[1]["decision_mode_log"] = "llm"  # a jev-battery row stamped llm
        bench.guard_benchmark_row(rows[1])
        ep_log = tmp_path / "cron_logs" / "bench1_ep.jsonl"
        ep_log.parent.mkdir(parents=True)
        ep_log.write_text("".join(json.dumps(r) + "\n" for r in rows))
        assert bench.cmd_report(ep_log) == 3


# ───────────────────────────────────── T: artifact regenerated from logs


class TestCmdReport:
    def _write_battery(self, tmp_path, rows):
        ep_log = tmp_path / "cron_logs" / "bench1_ep.jsonl"
        ep_log.parent.mkdir(parents=True)
        ep_log.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return ep_log

    def test_writes_artifact_with_both_arm_rows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        ep_log = self._write_battery(tmp_path, _battery_rows())
        rc = bench.cmd_report(ep_log)
        assert rc == 0
        out = (
            tmp_path / "data" / "baselines" / f"bench1_headtohead_{bench.today()}.json"
        )
        assert out.exists()
        artifact = json.loads(out.read_text())
        assert artifact["benchmark_id"] == "BENCH-1"
        table = artifact["comparison"]["table"]
        assert [row["mode"] for row in table] == ["llm", "jev"]
        llm_row, jev_row = table
        # every figure traces to the fixture rows (decisions 5+6, cost, ...)
        assert llm_row["decisions"] == 5 + 6
        assert llm_row["jev_answered"] == 0
        assert jev_row["decisions"] == 7 + 8
        assert jev_row["jev_answered"] == 7 + 8
        assert jev_row["teacher_calls"] == 4
        assert artifact["conditions"]["cycles_per_episode"] == 5
        assert artifact["conditions"]["boot_state"] == "data/boot.state"
        assert len(artifact["episodes"]) == 4
        assert artifact["guard"]["rejected_rows"] == []

    def test_table_includes_all_required_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        ep_log = self._write_battery(tmp_path, _battery_rows())
        assert bench.cmd_report(ep_log) == 0
        artifact = json.loads(
            (
                tmp_path
                / "data"
                / "baselines"
                / f"bench1_headtohead_{bench.today()}.json"
            ).read_text()
        )
        row = artifact["comparison"]["table"][0]
        for field in (
            "mode",
            "decision_mode_family",
            "agentic_tools_enabled",
            "agentic_tool_calls",
            "pipeline",
            "pipeline_counts",
            "decisions",
            "cost_usd_observed",
            "tiles_visited_distinct",
            "maps_reached",
            "first_map_transition_cycle",
            "lock_rate",
            "fallback_decisions",
            "errors",
            "map_transitions_observed",
            "decisions_per_map_transition",
            "state_comparisons",
            "backtrack_events",
            "backtrack_rate",
        ):
            assert field in row, f"comparison table missing required field {field}"

    def test_table_aggregates_efficiency_as_weighted_counts(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        rows = _battery_rows()
        for row in rows:
            if row["arm"] == "llm":
                row.update(
                    map_transitions_observed=1,
                    state_comparisons=4,
                    backtrack_events=3,
                    decisions_per_map_transition=float(row["decisions"]),
                    backtrack_rate=0.75,
                )
            else:
                row.update(
                    map_transitions_observed=2,
                    state_comparisons=6,
                    backtrack_events=1,
                    decisions_per_map_transition=row["decisions"] / 2,
                    backtrack_rate=round(1 / 6, 4),
                )
        ep_log = self._write_battery(tmp_path, rows)

        assert bench.cmd_report(ep_log) == 0
        artifact = json.loads(
            (
                tmp_path
                / "data"
                / "baselines"
                / f"bench1_headtohead_{bench.today()}.json"
            ).read_text()
        )
        llm_row, jev_row = artifact["comparison"]["table"]
        assert llm_row["map_transitions_observed"] == 2
        assert llm_row["decisions_per_map_transition"] == 5.5
        assert llm_row["backtrack_rate"] == 0.75
        assert jev_row["map_transitions_observed"] == 4
        assert jev_row["decisions_per_map_transition"] == 3.75
        assert jev_row["backtrack_rate"] == pytest.approx(1 / 6, abs=1e-4)

    def test_null_measurements_carry_reasons(self, tmp_path, monkeypatch):
        """A censored measurement is null WITH a reason, never hand-entered."""
        monkeypatch.setattr(bench, "REPO", tmp_path)
        rows = _battery_rows()
        for r in rows:
            r["first_map_transition_cycle"] = None
            r["lock_warn_cycles"] = None
            r["lock_total_cycles"] = None
            r["lock_rate"] = None
        ep_log = self._write_battery(tmp_path, rows)
        assert bench.cmd_report(ep_log) == 0
        artifact = json.loads(
            (
                tmp_path
                / "data"
                / "baselines"
                / f"bench1_headtohead_{bench.today()}.json"
            ).read_text()
        )
        for row in artifact["comparison"]["table"]:
            assert row["first_map_transition_cycle"] is None
            assert "first_map_transition_cycle_reason" in row
            assert row["lock_rate"]["rate"] is None
            assert "lock_rate_reason" in row

    def test_comparability_note_on_mixed_boot_hashes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        rows = _battery_rows()
        rows[0]["boot_sha256"] = "b" * 64
        ep_log = self._write_battery(tmp_path, rows)
        assert bench.cmd_report(ep_log) == 0
        artifact = json.loads(
            (
                tmp_path
                / "data"
                / "baselines"
                / f"bench1_headtohead_{bench.today()}.json"
            ).read_text()
        )
        notes = artifact["comparison"]["comparability_notes"]
        assert any("boot" in n.lower() for n in notes)

    def test_decision_parity_mismatch_listed_not_smoothed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        rows = _battery_rows()
        rows[0]["decisions"] = 99  # disagrees with its own autonomy row (5)
        ep_log = self._write_battery(tmp_path, rows)
        assert bench.cmd_report(ep_log) == 0
        artifact = json.loads(
            (
                tmp_path
                / "data"
                / "baselines"
                / f"bench1_headtohead_{bench.today()}.json"
            ).read_text()
        )
        parity = artifact["summary"]["decision_row_parity_mismatches"]
        assert parity == [
            {
                "run_id": rows[0]["run_id"],
                "decision_rows_counted": 99,
                "autonomy_decisions_total": 5,
            }
        ]

    def test_refuses_when_one_arm_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        rows = [r for r in _battery_rows() if r["arm"] == "llm"]
        ep_log = self._write_battery(tmp_path, rows)
        assert bench.cmd_report(ep_log) == 2

    def test_refuses_empty_log(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        ep_log = self._write_battery(tmp_path, [])
        assert bench.cmd_report(ep_log) == 2

    def test_accepts_cwd_relative_episode_log(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        self._write_battery(tmp_path, _battery_rows())
        monkeypatch.chdir(tmp_path)
        assert bench.cmd_report(Path("cron_logs/bench1_ep.jsonl")) == 0

    def test_env_output_path_outside_repo_still_writes_and_exits_zero(
        self, tmp_path, monkeypatch
    ):
        """Regression: an artifact path outside REPO (env override) crashed on
        out.relative_to(REPO) AFTER writing the artifact — rc must be 0."""
        monkeypatch.setattr(bench, "REPO", tmp_path)
        ep_log = self._write_battery(tmp_path, _battery_rows())
        out = tmp_path / "elsewhere" / "bench1.json"
        monkeypatch.setenv("BENCH1_OUTPUT_PATH", str(out))
        assert bench.cmd_report(ep_log) == 0
        assert out.exists()
        assert json.loads(out.read_text())["benchmark_id"] == "BENCH-1"


# ───────────────────────────────────────── misc plumbing


class TestPlumbing:
    def test_run_aborts_without_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert bench.cmd_run(1, 1, tmp_path / "boot.state") == 2

    def test_run_aborts_on_missing_boot_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        assert bench.cmd_run(1, 1, tmp_path / "missing.state") == 2

    def test_output_path_is_env_overridable(self, monkeypatch):
        monkeypatch.setenv("BENCH1_OUTPUT_PATH", "data/baselines/custom.json")
        assert bench.output_path() == "data/baselines/custom.json"

    def test_already_done_requires_autonomy_row(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bench, "REPO", tmp_path)
        cron_logs = tmp_path / "cron_logs"
        cron_logs.mkdir()
        runlog = cron_logs / "run_bench1_llm_ep1_20260928.jsonl"
        assert bench.already_done("bench1_llm_ep1_20260928") is False
        runlog.write_text(json.dumps(_llm_decision_row()) + "\n")
        assert bench.already_done("bench1_llm_ep1_20260928") is False
        runlog.write_text(runlog.read_text() + json.dumps(_autonomy_row()) + "\n")
        assert bench.already_done("bench1_llm_ep1_20260928") is True

    def test_arm_is_benchmark_only_for_llm(self):
        assert bench.arm_is_benchmark("llm") is True
        assert bench.arm_is_benchmark("jev") is False
        assert bench.arm_is_benchmark(None) is False
