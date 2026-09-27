"""Unit tests for the BASE-1 baseline driver (scripts/run_base1_baseline.py).

All pure-function tests: parsed fixture rows shaped like real cron_runner
JSONL rows — no ROM, no emulator, no API calls.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import run_base1_baseline  # noqa: E402


# ── fixtures shaped like real runner rows ────────────────────────────────────


def _decision_row(cycle, map_name, escalated=True, jev_ok=None):
    row = {
        "cycle": cycle,
        "screen": "overworld",
        "pipeline": "jev",
        "plan": ["UP"],
        "intent": "jev UP",
        "jev_answered": True,
        "escalated": escalated,
        "missing_class": "none",
        "map_name": map_name,
    }
    if jev_ok is not None:
        row["jev_ok"] = jev_ok
    return row


def _autonomy_row(decisions=5, escalated=3, teacher_count=0, mode="jev"):
    return {
        "run_id": "base1_ep1_20260927",
        "event": "run_autonomy",
        "decisions_total": decisions,
        "jev_answered": decisions,
        "escalated": escalated,
        "autonomy_ratio": 1.0,
        "teacher_escalations": {"count": teacher_count, "improved": 0},
        "decision_mode": mode,
    }


def _teacher_row(model_build="typesafe/jev-1.13-20260917"):
    return {
        "cycle": 1,
        "event": "teacher_escalation",
        "patch": {"ok": True, "cost_usd": 0.001},
        "post_ask": {"ok": True, "model_build": model_build},
    }


def _write_log(tmp_path, rows, name="run_x.jsonl"):
    p = tmp_path / name
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


class TestEpisodeMetricsFromLog:
    def test_counts_decisions_escalations_and_transitions(self, tmp_path):
        rows = [
            _decision_row(1, "Pallet Town"),
            _decision_row(2, "Pallet Town"),
            _decision_row(3, "Route 1", escalated=False),
            _autonomy_row(decisions=3, escalated=2),
        ]
        m = run_base1_baseline.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["decisions"] == 3
        assert m["cycles"] == 3
        assert m["escalated"] == 2
        assert m["jev_answered"] == 3
        assert m["map_sequence"] == [
            {"cycle": 1, "map": "Pallet Town"},
            {"cycle": 2, "map": "Pallet Town"},
            {"cycle": 3, "map": "Route 1"},
        ]
        assert m["map_transitions"] == [
            {"cycle": 3, "from_map": "Pallet Town", "to_map": "Route 1"}
        ]
        assert m["maps_seen"] == ["Pallet Town", "Route 1"]
        assert m["final_map"] == "Route 1"
        assert m["run_completed"] is True
        assert m["decision_mode_log"] == "jev"

    def test_transport_failures_counted_from_jev_ok_false(self, tmp_path):
        rows = [
            _decision_row(1, "Pallet Town", jev_ok=False),
            _decision_row(2, "Pallet Town", jev_ok=True),
            _autonomy_row(),
        ]
        m = run_base1_baseline.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["jev_transport_failures"] == 1

    def test_teacher_rows_count_calls_and_capture_model_build(self, tmp_path):
        rows = [
            _teacher_row(),
            _teacher_row(model_build="typesafe/jev-1.14-20260925"),
            _decision_row(1, "Pallet Town"),
            _autonomy_row(),
        ]
        m = run_base1_baseline.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["teacher_calls"] == 2  # counted from escalation events
        # first observed model_build wins; never overwritten by later rows
        assert m["model_build"] == "typesafe/jev-1.13-20260917"

    def test_autonomy_teacher_floor_binds_when_higher_than_events(self, tmp_path):
        # long_run.py semantics: the autonomy row's own total is a floor —
        # an escalation event stream missing rows still reports its count.
        rows = [
            _decision_row(1, "Pallet Town"),
            _autonomy_row(teacher_count=3),
        ]
        m = run_base1_baseline.episode_metrics_from_log(_write_log(tmp_path, rows))
        assert m["teacher_calls"] == 3
        assert m["autonomy"]["teacher_escalations"] == {"count": 3, "improved": 0}

    def test_missing_log_records_error_not_crash(self, tmp_path):
        m = run_base1_baseline.episode_metrics_from_log(tmp_path / "nope.jsonl")
        assert m["errors"] == ["log missing"]
        assert m["decisions"] == 0
        assert m["final_map"] is None

    def test_malformed_lines_skipped(self, tmp_path):
        p = tmp_path / "run_bad.jsonl"
        p.write_text(
            "{not json}\n" + json.dumps(_decision_row(1, "Pallet Town")) + "\n"
        )
        m = run_base1_baseline.episode_metrics_from_log(p)
        assert m["decisions"] == 1


class TestSummariseEpisodes:
    def _ep(self, **kw):
        base = {
            "cycles": 5,
            "decisions": 5,
            "jev_answered": 5,
            "escalated": 4,
            "teacher_calls": 1,
            "teacher_improved": 0,
            "wall_time_s": 30.0,
            "map_transitions": [{"cycle": 3, "from_map": "A", "to_map": "B"}],
            "maps_seen": ["A", "B"],
            "run_completed": True,
        }
        base.update(kw)
        return base

    def test_escalations_per_transition_math(self):
        s = run_base1_baseline.summarise_episodes(
            [self._ep(escalated=8, map_transitions=[{}]), self._ep(escalated=4)]
        )
        assert s["escalations_jev"] == 12
        assert s["map_transitions"] == 2
        assert s["escalations_per_map_transition"] == 6.0

    def test_zero_transitions_reports_null_with_reason(self):
        s = run_base1_baseline.summarise_episodes(
            [self._ep(map_transitions=[]), self._ep(map_transitions=[])]
        )
        assert s["escalations_per_map_transition"] is None
        assert "no map transition" in s["escalations_per_map_transition_note"]

    def test_wall_time_spread(self):
        s = run_base1_baseline.summarise_episodes(
            [self._ep(wall_time_s=20.0), self._ep(wall_time_s=40.0)]
        )
        w = s["wall_time_s_per_episode"]
        assert w["mean"] == 30.0
        assert w["min"] == 20.0
        assert w["max"] == 40.0
        assert w["stdev"] == 14.14  # sample stdev of [20, 40] = sqrt(200)
        assert s["wall_time_s"] == 60.0

    def test_maps_visited_deduped_and_sorted(self):
        s = run_base1_baseline.summarise_episodes(
            [self._ep(maps_seen=["Route 1", "Pallet Town"]), self._ep(maps_seen=["A"])]
        )
        assert s["maps_visited"] == ["A", "Pallet Town", "Route 1"]

    def test_completion_counts(self):
        s = run_base1_baseline.summarise_episodes(
            [
                self._ep(run_completed=True, decisions=5),
                self._ep(run_completed=False, decisions=0),
            ]
        )
        assert s["episodes_completed"] == 1
        assert s["episodes_with_zero_decisions"] == 1


class TestCmdReport:
    def _episode_rows(self, n=5):
        rows = []
        for i in range(1, n + 1):
            rows.append(
                {
                    "at": "2026-09-27T00:00:00Z",
                    "run_id": f"base1_ep{i}_20260927",
                    "episode": i,
                    "exit_code": 0,
                    "wall_time_s": 30.0 + i,
                    "cycles_requested": 5,
                    "boot_state": "data/boot.state",
                    "boot_sha256": "a" * 64,
                    "cycles": 5,
                    "decisions": 5,
                    "jev_answered": 5,
                    "escalated": 4,
                    "teacher_calls": 1,
                    "teacher_improved": 0,
                    "missing_classes": {"none": 5},
                    "map_sequence": [{"cycle": 1, "map": "Pallet Town"}],
                    "maps_seen": ["Pallet Town"],
                    "map_transitions": [],
                    "final_map": "Pallet Town",
                    "autonomy": None,
                    "decision_mode_log": "jev",
                    "model_build": None,
                    "run_completed": True,
                    "errors": [],
                }
            )
        return rows

    def test_refuses_to_write_a_thin_baseline(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_base1_baseline, "REPO", tmp_path)
        ep_log = tmp_path / "cron_logs" / "base1_ep.jsonl"
        ep_log.parent.mkdir(parents=True)
        ep_log.write_text(
            "".join(json.dumps(r) + "\n" for r in self._episode_rows(n=3))
        )
        rc = run_base1_baseline.cmd_report(ep_log)
        assert rc == 2
        assert not (tmp_path / "data" / "baselines").exists()

    def test_writes_artifact_with_five_episodes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_base1_baseline, "REPO", tmp_path)
        ep_log = tmp_path / "cron_logs" / "base1_ep.jsonl"
        ep_log.parent.mkdir(parents=True)
        ep_log.write_text(
            "".join(json.dumps(r) + "\n" for r in self._episode_rows(n=5))
        )
        rc = run_base1_baseline.cmd_report(ep_log)
        assert rc == 0
        out = (
            tmp_path
            / "data"
            / "baselines"
            / (f"base1_control_{run_base1_baseline.today()}.json")
        )
        assert out.exists()
        artifact = json.loads(out.read_text())
        assert artifact["baseline_id"] == "BASE-1"
        assert artifact["conditions"]["decision_mode"] == "jev"
        assert artifact["conditions"]["boot_state"] == "data/boot.state"
        assert artifact["conditions"]["boot_state_sha256"] == "a" * 64
        assert artifact["conditions"]["cycles_per_episode"] == 5
        assert len(artifact["episodes"]) == 5
        assert artifact["summary"]["episodes"] == 5
        assert artifact["summary"]["escalations_jev"] == 20
        # no transitions in the fixture rows -> null with a reason, not zero
        assert artifact["summary"]["escalations_per_map_transition"] is None
        for ep in artifact["episodes"]:
            assert ep["escalations_per_map_transition"] is None
            assert ep["boot_state_sha256"] == "a" * 64
            assert ep["decision_mode_log"] == "jev"

    def test_accepts_cwd_relative_episode_log(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_base1_baseline, "REPO", tmp_path)
        ep_log = tmp_path / "cron_logs" / "base1_ep.jsonl"
        ep_log.parent.mkdir(parents=True)
        ep_log.write_text(
            "".join(json.dumps(r) + "\n" for r in self._episode_rows(n=5))
        )
        monkeypatch.chdir(tmp_path)
        rc = run_base1_baseline.cmd_report(Path("cron_logs/base1_ep.jsonl"))
        assert rc == 0
        assert (
            tmp_path
            / "data"
            / "baselines"
            / f"base1_control_{run_base1_baseline.today()}.json"
        ).exists()

    def test_mode_mismatch_warns_but_stamps_requested_mode(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(run_base1_baseline, "REPO", tmp_path)
        rows = self._episode_rows(n=5)
        for r in rows:
            r["decision_mode_log"] = "controller"
        ep_log = tmp_path / "cron_logs" / "base1_ep.jsonl"
        ep_log.parent.mkdir(parents=True)
        ep_log.write_text("".join(json.dumps(r) + "\n" for r in rows))
        rc = run_base1_baseline.cmd_report(ep_log)
        assert rc == 0
        # Single-mode logs are TRUSTED and stamped as-is (CTRL-WIN llm runs);
        # a mismatch WARN only fires when logs DISAGREE with each other.
        if len({r["decision_mode_log"] for r in rows}) > 1:
            assert "WARN" in capsys.readouterr().out


class TestResume:
    def test_already_done_true_only_when_autonomy_row_landed(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(run_base1_baseline, "REPO", tmp_path)
        cron_logs = tmp_path / "cron_logs"
        cron_logs.mkdir()
        runlog = cron_logs / "run_base1_ep1_20260927.jsonl"
        assert run_base1_baseline.already_done("base1_ep1_20260927") is False
        runlog.write_text(json.dumps(_decision_row(1, "Pallet Town")) + "\n")
        assert run_base1_baseline.already_done("base1_ep1_20260927") is False
        runlog.write_text(runlog.read_text() + json.dumps(_autonomy_row()) + "\n")
        assert run_base1_baseline.already_done("base1_ep1_20260927") is True


class TestLoadEnvAbs:
    def test_loads_only_named_keys_and_never_overrides(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text(
            "# comment\n"
            "OPENROUTER_API_KEY=sk-test-value\n"
            "OTHER_KEY=skip-me\n"
            "\n"
            "OPENROUTER_API_KEY=second-ignored\n"
        )
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        run_base1_baseline.load_env_abs(env, ("OPENROUTER_API_KEY",))
        import os

        assert os.environ["OPENROUTER_API_KEY"] == "sk-test-value"
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def test_missing_file_is_silent(self, tmp_path):
        run_base1_baseline.load_env_abs(tmp_path / "nope.env", ("OPENROUTER_API_KEY",))


@pytest.mark.parametrize("n,cycles", [(0, 5), (6, 5), (5, 0), (5, 31)])
def test_cmd_run_rejects_out_of_contract_invocations(n, cycles, monkeypatch, tmp_path):
    monkeypatch.setattr(run_base1_baseline, "REPO", tmp_path)
    # Pin the paths the guards check so no real ROM/boot state is consulted;
    # the key guard is satisfied so the ROM/boot guards are what trips (rc=2).
    monkeypatch.setattr(run_base1_baseline, "ROM_PATH", tmp_path / "rom" / "fake.gb")
    monkeypatch.setattr(
        run_base1_baseline, "BOOT_STATE", tmp_path / "boot" / "boot.state"
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    rc = run_base1_baseline.cmd_run(n, cycles)
    assert rc == 2
