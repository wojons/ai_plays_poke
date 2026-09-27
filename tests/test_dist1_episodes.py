"""Unit tests for the DIST-1 episode driver (scripts/dist1_episodes.py).

All pure-function tests: parsed fixture rows shaped like real cron_runner
JSONL rows — no ROM, no emulator, no API calls.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import dist1_episodes  # noqa: E402


# ── fixtures shaped like real runner rows ────────────────────────────────────


def _decision_row(cycle, map_name, cost_usd=None):
    row = {
        "cycle": cycle,
        "screen": "overworld",
        "plan": ["UP"],
        "intent": "jev UP",
        "jev_answered": True,
        "map_name": map_name,
    }
    if cost_usd is not None:
        row["controller_call"] = {"ok": True, "cost_usd": cost_usd}
    return row


def _write_log(tmp_path, rows, name="run_x.jsonl"):
    p = tmp_path / name
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


class TestEpisodeMetricsFromLog:
    def test_route1_touch_and_return_mirrors_ctrlwin(self, tmp_path):
        # CTRL-WIN shape: Pallet -> Route 1 at c13 -> back in Pallet by c22.
        rows = [_decision_row(1, "Pallet Town")]
        rows += [_decision_row(c, "Route 1") for c in range(13, 22)]
        rows += [_decision_row(c, "Pallet Town") for c in range(22, 31)]
        m = dist1_episodes.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["first_transition_cycle"] == 13
        assert m["first_goal_map_cycle"] == 13
        assert m["goal_map_reached"] is True
        assert m["held_the_transition"] is False  # ended back in Pallet
        assert m["final_map"] == "Pallet Town"
        assert m["transitions_count"] == 2
        assert m["goal_map_cycles"] == 9
        assert m["cycles"] == 30
        assert m["maps_seen"] == ["Pallet Town", "Route 1"]

    def test_held_transition_ends_on_goal_map(self, tmp_path):
        rows = [_decision_row(c, "Pallet Town") for c in range(1, 8)]
        rows += [_decision_row(c, "Route 1") for c in range(8, 31)]
        m = dist1_episodes.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["first_transition_cycle"] == 8
        assert m["held_the_transition"] is True
        assert m["final_map"] == "Route 1"

    def test_censored_episode_no_map_change(self, tmp_path):
        rows = [_decision_row(c, "Pallet Town") for c in range(1, 31)]
        m = dist1_episodes.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["first_transition_cycle"] is None
        assert m["goal_map_reached"] is False
        assert m["held_the_transition"] is False
        assert m["transitions_count"] == 0

    def test_missing_log_reports_error_not_zeroes(self, tmp_path):
        m = dist1_episodes.episode_metrics_from_log(tmp_path / "nope.jsonl")
        assert "error" in m

    def test_teachers_costs_and_completion_counted(self, tmp_path):
        rows = [
            {"cycle": 1, "event": "teacher_escalation"},
            _decision_row(1, "Pallet Town", cost_usd=0.5),
            _decision_row(2, "Pallet Town"),
            {
                "cycle": 3,
                "event": "run_autonomy",
                "decisions_total": 2,
                "decision_mode": "jev",
            },
            {"cycle": 3, "event": "recovery", "reason": "direction-locked (UP x4)"},
        ]
        m = dist1_episodes.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["teacher_calls"] == 1
        assert m["run_completed"] is True
        assert m["cost_usd_observed"] == 0.5
        assert m["recovery_direction_lock_events"] == 1

    def test_nested_costs_are_summed(self, tmp_path):
        rows = [
            {
                "cycle": 1,
                "event": "teacher_escalation",
                "patch": {"cost_usd": 0.1},
                "pre_ask": {"cost_usd": 0.2},
            },
            _decision_row(1, "Pallet Town", cost_usd=0.3),
        ]
        m = dist1_episodes.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["cost_usd_observed"] == pytest.approx(0.6)


class TestParseLockRate:
    def test_parses_runner_summary_line(self):
        line = (
            "[dist1_llm_e001] Done. 27 actions. Screens: 30 | lock-rate: "
            "14/30 cycles with direction-lock warnings (47%) | distinct "
            "tiles: 17 | real_decisions=27 fallback_decisions=0"
        )
        assert dist1_episodes.parse_lock_rate(line) == (14, 30)

    def test_no_match_returns_none(self):
        assert dist1_episodes.parse_lock_rate("no summary here") is None
        assert dist1_episodes.parse_lock_rate("") is None

    def test_run_completed_needs_done_line(self):
        assert dist1_episodes.run_completed("Done. 27 actions. Screens: 30")
        assert not dist1_episodes.run_completed("mid-run output only")


class TestSummariseDistribution:
    def test_mixed_observed_and_censored(self):
        eps = [
            {
                "first_transition_cycle": 13,
                "held_the_transition": True,
                "direction_lock_rate": 0.4,
                "cost_usd_observed": 0.5,
            },
            {
                "first_transition_cycle": 20,
                "held_the_transition": False,
                "direction_lock_rate": 0.5,
                "cost_usd_observed": 0.5,
            },
            {
                "first_transition_cycle": None,
                "held_the_transition": False,
                "direction_lock_rate": 0.6,
                "cost_usd_observed": 0.5,
            },
            {
                "first_transition_cycle": None,
                "held_the_transition": False,
                "direction_lock_rate": None,
                "cost_usd_observed": 0.0,
            },
        ]
        s = dist1_episodes.summarise_distribution(eps)
        assert s["n_episodes"] == 4
        assert s["n_transitions_observed"] == 2
        assert s["n_censored_no_transition"] == 2
        assert s["cycles_to_first_transition"] == [13, 20]
        assert s["spread"]["min"] == 13
        assert s["spread"]["median"] == 16.5
        assert s["spread"]["max"] == 20
        assert s["spread"]["stdev"] > 0
        assert s["transitions_held"] == {"held": 1, "of": 4}
        assert s["direction_lock_rate"]["mean"] == pytest.approx(0.5)
        assert s["direction_lock_rate"]["per_episode"] == [0.4, 0.5, 0.6]
        assert s["cost_usd_observed_total"] == pytest.approx(1.5)

    def test_all_censored_reports_no_fabricated_spread(self):
        eps = [
            {
                "first_transition_cycle": None,
                "held_the_transition": False,
                "direction_lock_rate": 0.1,
                "cost_usd_observed": 0.1,
            },
        ]
        s = dist1_episodes.summarise_distribution(eps)
        assert s["n_transitions_observed"] == 0
        assert s["spread"] is None
        assert "censored" in s["spread_note"]

    def test_single_observation_zero_stdev(self):
        eps = [
            {
                "first_transition_cycle": 13,
                "held_the_transition": True,
                "direction_lock_rate": 0.0,
                "cost_usd_observed": 0.0,
            },
        ]
        s = dist1_episodes.summarise_distribution(eps)
        assert s["spread"]["stdev"] == 0.0
        assert s["spread"]["min"] == s["spread"]["max"] == 13


class TestBootStateGate:
    def test_wrong_boot_md5_skips_episode(self, tmp_path, monkeypatch):
        # A boot state that is NOT the documented rescued copy must abort the
        # battery before any LLM spend — the same-start-state guarantee.
        monkeypatch.setattr(dist1_episodes, "REPO", tmp_path)
        fake = tmp_path / "base-1_boot.state"
        fake.write_bytes(b"not the real state")
        monkeypatch.setattr(dist1_episodes, "BOOT_STATE", fake)
        row = dist1_episodes.run_episode("llm", 1, "dist1_gate_test")
        assert row["skipped"] is True
        assert "md5" in row["reason"]
        assert not (tmp_path / "cron_logs" / "run_dist1_gate_test.jsonl").exists()


class TestAlreadyDone:
    def test_completed_summary_enables_resume(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dist1_episodes, "REPO", tmp_path)
        logs = tmp_path / "cron_logs"
        logs.mkdir()
        (logs / "run_dist1_jev_e001.stdout.log").write_text(
            "Done. 30 actions. lock-rate: 0/30\n"
        )
        assert dist1_episodes.already_done("dist1_jev_e001") is True

    def test_missing_log_is_not_done(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dist1_episodes, "REPO", tmp_path)
        (tmp_path / "cron_logs").mkdir()
        assert dist1_episodes.already_done("dist1_jev_e002") is False


class TestReportArtifact:
    def test_report_writes_both_modes_with_spread(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dist1_episodes, "REPO", tmp_path)
        rows = []
        for mode, cycles in (("llm", [13, 20, None]), ("jev", [None, None])):
            for i, t in enumerate(cycles, 1):
                rows.append(
                    {
                        "at": "2026-09-27T00:00:00Z",
                        "run_id": f"dist1_{mode}_e{i:03d}",
                        "mode": mode,
                        "episode": i,
                        "exit_code": 0,
                        "duration_s": 60.0,
                        "cycles_requested": 30,
                        "boot_state": "data/baselines/base-1_boot.state",
                        "boot_md5": dist1_episodes.EXPECTED_BOOT_MD5,
                        "censored": t is None,
                        "runner_summary_parsed": True,
                        "direction_lock_warned_cycles": 3,
                        "direction_lock_total_cycles": 30,
                        "direction_lock_rate": 0.1,
                        "cycles": 30,
                        "decisions": 30,
                        "maps_seen": ["Pallet Town"],
                        "map_sequence": [],
                        "first_transition_cycle": t,
                        "transitions_count": 0,
                        "goal_map_reached": False,
                        "first_goal_map_cycle": None,
                        "held_the_transition": False,
                        "goal_map_cycles": 0,
                        "final_map": "Pallet Town",
                        "map_transitions": [],
                        "teacher_calls": 0,
                        "cost_usd_observed": 0.1,
                        "recovery_direction_lock_events": 0,
                        "run_completed": True,
                    }
                )
        ep_log = tmp_path / "episodes.jsonl"
        ep_log.write_text("".join(json.dumps(r) + "\n" for r in rows))
        out = tmp_path / "artifact.json"
        rc = dist1_episodes.cmd_report(ep_log, out)
        assert rc == 0
        art = json.loads(out.read_text())
        assert art["experiment"] == "DIST-1"
        assert art["conditions"]["boot_md5"] == dist1_episodes.EXPECTED_BOOT_MD5
        assert "censor" in art["conditions"]["censor_rule"]
        assert set(art["modes"]) == {"jev", "llm"}
        assert len(art["modes"]["llm"]["episodes"]) == 3
        assert len(art["modes"]["jev"]["episodes"]) == 2
        assert art["modes"]["llm"]["n_transitions_observed"] == 2
        assert art["modes"]["jev"]["spread"] is None
        assert art["modes"]["jev"]["spread_note"]
        # every episode row carries the per-episode metrics the row asks for
        for mode in ("llm", "jev"):
            for ep in art["modes"][mode]["episodes"]:
                assert "first_transition_cycle" in ep
                assert "held_the_transition" in ep
                assert ep["direction_lock"]["rate"] is not None
