"""Unit tests for GAP-028: boot-state resolution + lock-rate summary metrics.

Covers cron_runner._resolve_boot_state (default / skip / explicit path)
and _format_summary (per-run lock-rate fraction + distinct-tile count).

DF-JEV-1 adds the overworld JEV tier: ``_jev_overworld_decision`` (a JEV hit
supplies the plan + the AC-1 fields, a miss falls back to ``controller_plan``)
and the per-decision rows' contribution to the run's autonomy ratio.
"""

from __future__ import annotations

import ast
import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

import cron_runner
from src.core import jev_client


@pytest.fixture(autouse=True)
def _hermetic_api_keys(monkeypatch):
    """Keep this module's tests off the network (GAP-048).

    ``--dry-run`` probes each CONFIGURED API key over HTTP, and the repo-root
    ``.env`` holds real keys that ``_load_dotenv_stdlib()`` copies into
    ``os.environ`` — so a test that reaches ``_dry_run_summary`` would make a
    real request. Neutralize the dotenv load and strip ambient keys; tests that
    exercise the probes set their own keys and mock ``urllib.request.urlopen``.
    """
    monkeypatch.setattr(cron_runner, "_load_dotenv_stdlib", lambda: None)
    for name in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


class TestResolveBootState:
    """--boot-state / data/boot.state resolution (GAP-028)."""

    def test_default_uses_data_boot_state_when_present(
        self, monkeypatch, tmp_path
    ) -> None:
        ckpt = tmp_path / "boot.state"
        ckpt.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", ckpt)
        assert cron_runner._resolve_boot_state(None) == ckpt

    def test_skip_returns_none(self) -> None:
        assert cron_runner._resolve_boot_state("skip") is None
        assert cron_runner._resolve_boot_state("SKIP") is None

    def test_missing_default_returns_none(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", tmp_path / "nope.state")
        assert cron_runner._resolve_boot_state(None) is None

    def test_explicit_path_used(self, tmp_path) -> None:
        ckpt = tmp_path / "custom.state"
        ckpt.write_bytes(b"x")
        assert cron_runner._resolve_boot_state(str(ckpt)) == ckpt

    def test_explicit_missing_path_returns_none(self, tmp_path) -> None:
        assert cron_runner._resolve_boot_state(str(tmp_path / "missing.state")) is None


class TestFormatSummary:
    """Final summary line: lock-rate fraction + distinct tiles (GAP-028)."""

    def test_includes_lock_rate_and_tiles(self) -> None:
        s = cron_runner._format_summary("run1", 20, {"overworld"}, 5, 20, 3)
        assert "[run1] Done. 20 actions. Screens: {'overworld'}" in s
        assert "lock-rate: 5/20 cycles" in s
        assert "25%" in s
        assert "distinct tiles: 3" in s

    def test_zero_lock_rate(self) -> None:
        s = cron_runner._format_summary("run2", 10, {"overworld"}, 0, 10, 1)
        assert "lock-rate: 0/10 cycles" in s
        assert "0%" in s

    def test_half_lock_rate_rounds_to_50_percent(self) -> None:
        s = cron_runner._format_summary("run3", 10, {"overworld"}, 5, 10, 2)
        assert "50%" in s

    def test_one_hundred_percent_lock_rate(self) -> None:
        s = cron_runner._format_summary("run4", 5, {"overworld"}, 5, 5, 1)
        assert "lock-rate: 5/5 cycles" in s
        assert "100%" in s


class TestDryRun:
    """--dry-run precheck (GAP-032): validates setup, exits 0, never boots.

    The precheck runs at import time before the heavy third-party imports,
    so these tests exercise it directly with explicit argv (same pattern as
    TestResolveBootState). A subprocess test is unnecessary: the precheck's
    only side effects are stdout prints and sys.exit.
    """

    def test_dry_run_exits_zero_with_config_summary(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        rom = tmp_path / "rom.gb"
        rom.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(rom))
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", tmp_path / "boot.state")
        (tmp_path / "boot.state").write_bytes(b"x")
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "ROM path:" in out and "[OK]" in out
        assert "Boot state:" in out
        assert "Cycles:" in out
        assert "Run ID:" in out
        assert "Model/provider:" in out
        assert "no emulator boot, no LLM completions" in out
        assert "📡" not in out  # no API call lines

    def test_dry_run_reflects_cycles_run_id_and_boot_state(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        rom = tmp_path / "rom.gb"
        rom.write_bytes(b"x")
        ckpt = tmp_path / "ckpt.state"
        ckpt.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(rom))
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(
                [
                    "--dry-run",
                    "--cycles",
                    "5",
                    "--run-id",
                    "probe",
                    "--boot-state",
                    str(ckpt),
                ]
            )
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "Cycles:         5" in out
        assert "Run ID:         probe" in out
        assert f"{ckpt}  [OK]" in out

    def test_dry_run_boot_state_skip_prints_bypass(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        rom = tmp_path / "rom.gb"
        rom.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(rom))
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run", "--boot-state", "skip"])
        assert e.value.code == 0
        assert "skip (legacy intro bypass)" in capsys.readouterr().out

    def test_dry_run_missing_boot_state_still_exits_zero(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        rom = tmp_path / "rom.gb"
        rom.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(rom))
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(
                ["--dry-run", "--boot-state", str(tmp_path / "nope.state")]
            )
        assert e.value.code == 0
        assert "fall back to intro bypass" in capsys.readouterr().out

    def test_dry_run_missing_rom_exits_one(self, monkeypatch, capsys, tmp_path) -> None:
        monkeypatch.setattr(cron_runner, "ROM", str(tmp_path / "nope.gb"))
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 1
        assert "ERROR: ROM not found" in capsys.readouterr().out

    def test_no_dry_run_returns_without_exiting(self) -> None:
        assert cron_runner._dry_run_precheck(["--cycles", "3"]) is None

    def test_main_parser_exposes_dry_run_flag(self) -> None:
        # --help must list --dry-run (GAP-032 acceptance); the flag must
        # parse on the real parser main() uses.
        args = cron_runner._main_parser().parse_args(["--dry-run"])
        assert args.dry_run is True


class TestRomFlag:
    """--rom flag flows into the dry-run summary (GAP-033).

    cron.sh passes --rom <path> through to cron_runner.py; these tests prove
    the flag is accepted by both the early precheck parser (bare-python3
    path) and the real _main_parser, and that the resolved ROM is what the
    dry-run summary validates/reports. Mock-free and fast — no emulator boot.
    """

    def test_dry_run_reports_explicit_rom_ok(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        rom = tmp_path / "custom.gb"
        rom.write_bytes(b"x")
        ckpt = tmp_path / "boot.state"
        ckpt.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", ckpt)
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run", "--rom", str(rom)])
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert f"ROM path:       {rom}  [OK]" in out
        assert "Validation OK" in out

    def test_dry_run_missing_explicit_rom_exits_one(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        # A non-existent --rom path must be reported MISSING and exit 1,
        # regardless of where the module-level ROM constant points.
        monkeypatch.setattr(
            cron_runner,
            "ROM",
            "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb",
        )
        missing = tmp_path / "nope.gb"
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run", "--rom", str(missing)])
        assert e.value.code == 1
        out = capsys.readouterr().out
        assert f"ROM path:       {missing}  [MISSING]" in out
        assert "ERROR: ROM not found" in out

    def test_dry_run_without_rom_uses_module_default(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        # No --rom → the precheck falls back to the module ROM constant,
        # preserving pre-GAP-033 behavior for direct cron_runner runs.
        rom = tmp_path / "rom.gb"
        rom.write_bytes(b"x")
        ckpt = tmp_path / "boot.state"
        ckpt.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(rom))
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", ckpt)
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 0
        assert f"ROM path:       {rom}  [OK]" in capsys.readouterr().out

    def test_main_parser_exposes_rom_flag(self) -> None:
        args = cron_runner._main_parser().parse_args(["--rom", "data/rom/foo.gb"])
        assert args.rom == "data/rom/foo.gb"
        # default is None → module constant used
        assert cron_runner._main_parser().parse_args([]).rom is None


class TestBootStateRomMismatch:
    """GAP-037: warn when a Blue-ROM checkpoint boots into a non-Blue ROM.

    data/boot.state was captured from the Blue SGB ROM; PyBoy's
    load_state never validates the savestate against the loaded
    cartridge, so a Blue checkpoint loaded into e.g. pokemon_red.gb
    yields garbage RAM with zero errors. The warning must fire only when
    a checkpoint is actually going to be loaded (--boot-state skip
    suppresses it) and the ROM header title (offset 0x134) is not Blue.
    """

    @staticmethod
    def _fake_rom(tmp_path, title: str) -> str:
        """Write a fake ROM whose header title (0x134, 16 bytes) is `title`."""
        rom = tmp_path / "rom.gb"
        data = bytearray(0x150)
        data[0x134 : 0x134 + len(title)] = title.encode("ascii")
        rom.write_bytes(bytes(data))
        return str(rom)

    def test_mismatch_warns_for_non_blue_rom(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        # A boot checkpoint (Blue) loaded into a Red ROM must print the
        # actionable mismatch warning.
        rom = self._fake_rom(tmp_path, "POKEMON RED")
        ckpt = tmp_path / "boot.state"
        ckpt.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "BOOT_STATE_ROM_TITLE", "POKEMON BLUE")
        cron_runner._warn_boot_state_rom_mismatch("run_gap037", ckpt, rom)
        out = capsys.readouterr().out
        assert "WARNING:" in out
        assert "was saved from the Blue ROM (POKEMON BLUE)" in out
        assert "--rom is POKEMON RED" in out
        assert "--boot-state skip" in out

    def test_no_warning_for_blue_rom(self, monkeypatch, capsys, tmp_path) -> None:
        # Blue ROM + Blue checkpoint: the standard workflow must stay silent.
        rom = self._fake_rom(tmp_path, "POKEMON BLUE")
        ckpt = tmp_path / "boot.state"
        ckpt.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "BOOT_STATE_ROM_TITLE", "POKEMON BLUE")
        cron_runner._warn_boot_state_rom_mismatch("run1", ckpt, rom)
        assert capsys.readouterr().out == ""

    def test_no_warning_when_boot_state_skipped(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        # --boot-state skip → boot_path is None → no checkpoint is loaded,
        # so no warning even with a Red ROM.
        rom = self._fake_rom(tmp_path, "POKEMON RED")
        monkeypatch.setattr(cron_runner, "BOOT_STATE_ROM_TITLE", "POKEMON BLUE")
        cron_runner._warn_boot_state_rom_mismatch("run2", None, rom)
        assert capsys.readouterr().out == ""

    def test_no_warning_when_checkpoint_missing(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        # _resolve_boot_state returns None for a missing checkpoint; a
        # missing checkpoint falls back to the intro bypass and never
        # loads Blue RAM, so it must not warn either.
        rom = self._fake_rom(tmp_path, "POKEMON RED")
        monkeypatch.setattr(cron_runner, "BOOT_STATE_ROM_TITLE", "POKEMON BLUE")
        assert cron_runner._resolve_boot_state(str(tmp_path / "nope.state")) is None
        cron_runner._warn_boot_state_rom_mismatch("run3", None, rom)
        assert capsys.readouterr().out == ""

    def test_no_warning_for_unreadable_rom(self, monkeypatch, capsys, tmp_path) -> None:
        # Unreadable / too-short ROM → title unknown → never warn.
        ckpt = tmp_path / "boot.state"
        ckpt.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "BOOT_STATE_ROM_TITLE", "POKEMON BLUE")
        cron_runner._warn_boot_state_rom_mismatch(
            "run4", ckpt, str(tmp_path / "missing.gb")
        )
        assert capsys.readouterr().out == ""

    def test_dry_run_summary_prints_mismatch_warning(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        # The --dry-run pre-flight (the cheap path a user runs first) must
        # surface the same mismatch so the problem is visible before boot.
        rom = self._fake_rom(tmp_path, "POKEMON RED")
        ckpt = tmp_path / "boot.state"
        ckpt.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", ckpt)
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run", "--rom", rom])
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "WARNING:" in out and "POKEMON RED" in out
        assert "use --boot-state skip for non-Blue ROMs" in out


class _FakeProbeResponse:
    """Minimal urlopen() response stub: context manager + status/read."""

    def __init__(self, status: int = 200, body: bytes = b"{}") -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeProbeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class TestDryRunKeyLiveness:
    """GAP-048: --dry-run probes CONFIGURED keys instead of trusting presence.

    Pre-GAP-048 an expired OPENROUTER_API_KEY printed "OPENROUTER_API_KEY=set"
    and exited 0, then 401'd on every real call — the user got "Validation OK"
    followed by a dead 20-cycle run. Every test here mocks
    ``urllib.request.urlopen``: the suite must never make a real HTTP request.
    """

    @pytest.fixture
    def rom(self, monkeypatch, tmp_path) -> str:
        """An existing ROM + boot state, so the ROM check can't mask the key result."""
        path = tmp_path / "rom.gb"
        path.write_bytes(b"x")
        monkeypatch.setattr(cron_runner, "ROM", str(path))
        monkeypatch.setattr(cron_runner, "DEFAULT_BOOT_STATE", tmp_path / "boot.state")
        (tmp_path / "boot.state").write_bytes(b"x")
        return str(path)

    @staticmethod
    def _http_error(request, status: int, body: dict | bytes):
        """Build the HTTPError urlopen raises for a non-200 response."""
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        return urllib.error.HTTPError(
            request.full_url, status, "Unauthorized", None, io.BytesIO(raw)
        )

    def test_dead_openrouter_key_exits_nonzero_with_verbatim_provider_error(
        self, rom, monkeypatch, capsys
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-expired")

        def fake_urlopen(request, timeout=None):
            raise self._http_error(
                request, 401, {"error": {"message": "API key expired"}}
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 1
        out = capsys.readouterr().out
        assert "OPENROUTER_API_KEY=set" in out  # presence still reported
        assert "OPENROUTER_API_KEY DEAD — API key expired" in out
        assert "[DRY-RUN] ERROR: OPENROUTER_API_KEY is dead — API key expired" in out
        assert "Validation OK" not in out

    def test_live_keys_exit_zero_and_send_bearer_auth(
        self, rom, monkeypatch, capsys
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-live")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-live")
        seen: list[tuple[str, str | None]] = []

        def fake_urlopen(request, timeout=None):
            seen.append((request.full_url, request.get_header("Authorization")))
            return _FakeProbeResponse()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "OPENROUTER_API_KEY live" in out
        assert "DEEPSEEK_API_KEY live" in out
        assert "Validation OK — exiting 0." in out
        assert {url for url, _ in seen} == set(cron_runner._KEY_PROBE_URLS.values())
        assert {auth for _, auth in seen} == {
            "Bearer sk-or-v1-live",
            "Bearer sk-deepseek-live",
        }

    def test_skip_key_check_makes_no_network_call(
        self, rom, monkeypatch, capsys
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-expired")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-expired")

        def boom(*args, **kwargs):
            raise AssertionError("network call attempted despite --skip-key-check")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run", "--skip-key-check"])
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "skipped (--skip-key-check)" in out
        assert "Validation OK — exiting 0." in out

    def test_dead_deepseek_key_probes_models_endpoint(
        self, rom, monkeypatch, capsys
    ) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-expired")
        urls: list[str] = []

        def fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            raise self._http_error(
                request,
                401,
                b'{"message": "Authentication Fails, Your api key is invalid"}',
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 1
        out = capsys.readouterr().out
        assert urls == [cron_runner._KEY_PROBE_URLS["DEEPSEEK_API_KEY"]]
        assert "Authentication Fails, Your api key is invalid" in out
        assert "DEEPSEEK_API_KEY is dead" in out

    def test_network_error_is_dead_with_verbatim_error(
        self, rom, monkeypatch, capsys
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-whatever")

        def fake_urlopen(request, timeout=None):
            raise urllib.error.URLError(
                "[Errno -3] Temporary failure in name resolution"
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 1
        out = capsys.readouterr().out
        assert "Temporary failure in name resolution" in out
        assert "OPENROUTER_API_KEY is dead" in out

    def test_no_configured_keys_never_probes(self, rom, monkeypatch, capsys) -> None:
        def boom(*args, **kwargs):
            raise AssertionError("network call attempted with no configured keys")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "no configured keys to probe" in out
        assert "Validation OK — exiting 0." in out

    def test_dead_key_and_missing_rom_report_both(
        self, monkeypatch, capsys, tmp_path
    ) -> None:
        monkeypatch.setattr(cron_runner, "ROM", str(tmp_path / "nope.gb"))
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-expired")

        def fake_urlopen(request, timeout=None):
            raise self._http_error(
                request, 401, {"error": {"message": "API key expired"}}
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(SystemExit) as e:
            cron_runner._dry_run_precheck(["--dry-run"])
        assert e.value.code == 1
        out = capsys.readouterr().out
        assert "ERROR: ROM not found" in out
        assert "ERROR: OPENROUTER_API_KEY is dead — API key expired" in out

    def test_skip_key_check_flag_exposed_on_both_parsers(self) -> None:
        assert (
            cron_runner._main_parser().parse_args(["--dry-run"]).skip_key_check is False
        )
        parsed = cron_runner._main_parser().parse_args(
            ["--dry-run", "--skip-key-check"]
        )
        assert parsed.skip_key_check is True
        # The early (bare-python3) parser accepts it too, and without
        # --dry-run the precheck still returns instead of exiting.
        assert cron_runner._dry_run_precheck(["--skip-key-check"]) is None

    def test_extract_provider_error_fallbacks(self) -> None:
        extract = cron_runner._extract_provider_error
        assert (
            extract('{"error": {"message": "API key expired"}}', 401)
            == "API key expired"
        )
        assert extract('{"error": "quota exceeded"}', 402) == "quota exceeded"
        assert extract('{"message": "Bad request"}', 400) == "Bad request"
        assert extract("plain text error", 500) == "plain text error"
        assert extract("", 503) == "HTTP 503"


# ── DF-JEV-1: the JEV tier in the overworld decision loop ───────────
#
# PRD v3 stages 5-6: the cheap System-One tier decides from the bounded RAM
# projection, and a miss (invalid action, transport error) falls back to
# `controller_plan()`. These tests drive the real `_jev_overworld_decision`
# seam with a mocked `jev_client.decide` — no emulator, no network, no LLM.

# A live `RAMReader.observe()` shape, trimmed to the fields the projection
# reads. The stuck signal (repeat counts) and the goal/events come from the
# loop's own cross-cycle state, which the tests pass in explicitly.
_OBS: dict[str, Any] = {
    "result": "overworld",
    "map_id": 40,
    "map_name": "Oaks Lab",
    "player_tile_x": 6,
    "player_tile_y": 4,
    "player_facing": "up",
    "party_count": 0,
    "first_party_species": None,
    "adjacent": {
        "up": "wall",
        "down": "floor",
        "left": "floor",
        "right": "floor",
    },
    "minimap": "",
    "overworld_grid": "",
    "visible_exits": [],
    "text_content": [],
    "menu_state": {},
}


class _ScriptedClient:
    """OpenRouterClient stand-in returning one canned controller response."""

    def __init__(self, content: str) -> None:
        self.content = content

    def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        return {"content": self.content}


def _jev_payload(
    action: Any,
    *,
    ok: bool = True,
    escalate: bool = False,
    missing_class: str = "none",
) -> dict[str, Any]:
    """One normalized `jev_client.decide()` payload."""
    distribution = {action: 0.94} if isinstance(action, str) else {}
    return {
        "ok": ok,
        "next_action": action,
        "phase": "EXPLORE",
        "raw": {
            "next_action": {"choice": action, "distribution": distribution},
            "phase": {"choice": "EXPLORE", "distribution": {"EXPLORE": 1.0}},
        },
        "escalate": escalate,
        "escalate_reason": (
            "low_confidence_act (0.31)" if escalate else "jev_confident"
        ),
        "missing_class": missing_class,
    }


def _install_decide(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """Patch `jev_client.decide` with a recorder and return its call log."""
    calls: list[dict[str, Any]] = []

    def fake_decide(state: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"state": state, **kwargs})
        return payload

    monkeypatch.setattr(jev_client, "decide", fake_decide)
    return calls


def _jev_decision(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> dict[str, Any]:
    """One overworld cycle decided by JEV, through the real seam."""
    _install_decide(monkeypatch, payload)
    decision = cron_runner._jev_overworld_decision(
        _OBS,
        goal="leave Oaks Lab and head toward Route 1",
        visited={(6, 4): 3, (6, 5): 1},
        recent_events=[{"cycle": 2, "action": "UP", "result": "no change"}],
        last_action="UP",
        last_action_changed_state=False,
    )
    assert decision, "JEV should have decided this cycle"
    return decision


def _jev_row(monkeypatch: pytest.MonkeyPatch, action: str) -> dict[str, Any]:
    """One overworld cycle decided by JEV on a confident answer."""
    return _jev_decision(monkeypatch, _jev_payload(action))


def _decision_row(
    decision: dict[str, Any], pipeline: str, cycle: int
) -> dict[str, Any]:
    """The per-decision row `plan_entry` stamps, built from a decision payload.

    `plan_entry` is built inline in `main()` (no seam to call), so the row shape
    this file relies on is pinned against cron_runner.py's own source by
    `TestPlanEntryRowShape` below — the mirror cannot drift unnoticed.
    """
    missing_class = decision.get("missing_class")
    return {
        "cycle": cycle,
        "screen": "overworld",
        "pipeline": pipeline,
        "plan": decision.get("plan", ["A"]),
        "intent": decision.get("intent", ""),
        "jev_answered": bool(decision.get("jev_answered", False)),
        "escalated": bool(decision.get("escalated", False)),
        "missing_class": missing_class if isinstance(missing_class, str) else None,
        "raw_distribution": decision.get("raw_distribution"),
    }


class TestJevOverworldDecision:
    """DF-JEV-1 (1): a JEV hit supplies the plan and the AC-1 fields."""

    def test_hit_uses_jevs_action_and_records_the_distribution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        raw = _jev_payload("RIGHT")["raw"]
        _install_decide(monkeypatch, _jev_payload("RIGHT"))

        decision = cron_runner._jev_overworld_decision(
            _OBS,
            goal="leave Oaks Lab and head toward Route 1",
            visited={(6, 4): 3, (6, 5): 1},
            recent_events=[{"cycle": 2, "action": "UP", "result": "no change"}],
            last_action="UP",
            last_action_changed_state=False,
        )

        assert decision["plan"] == ["RIGHT"]
        assert decision["intent"] == "jev RIGHT"
        assert decision["jev_answered"] is True
        assert decision["escalated"] is False
        assert decision["missing_class"] == "none"
        assert decision["raw_distribution"] == raw
        assert decision["jev_projection_chars"] > 0
        assert decision["jev_escalate_reason"] == "jev_confident"

    def test_the_live_ram_state_reaches_jev_as_the_projection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _install_decide(monkeypatch, _jev_payload("RIGHT"))

        cron_runner._jev_overworld_decision(
            _OBS,
            goal="leave Oaks Lab and head toward Route 1",
            visited={(6, 4): 3, (6, 5): 1},
            recent_events=[{"cycle": 2, "action": "UP", "result": "no change"}],
            last_action="UP",
            last_action_changed_state=False,
        )

        assert len(calls) == 1
        projection = calls[0]["state"]
        # map / tile / party / adjacency / goal / cross-cycle material
        assert "Oaks Lab" in projection
        assert "PARTY: empty (no Pokemon yet)" in projection
        assert "UP=wall DOWN=floor LEFT=floor RIGHT=floor" in projection
        assert "leave Oaks Lab and head toward Route 1" in projection
        assert "(6, 4)*x3" in projection  # repeat counts = the stuck signal
        assert "action=UP" in projection
        # The overworld question set: no battle vocabulary on this call.
        assert "in_battle" not in calls[0]

    def test_a_failed_last_direction_action_reaches_the_gate_as_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _install_decide(monkeypatch, _jev_payload("LEFT", escalate=True))

        decision = cron_runner._jev_overworld_decision(
            _OBS, last_action="UP", last_action_changed_state=False
        )

        # PRD v3 §3.2 trigger 1: the loop's same-tile streak is handed to the
        # gate as a failure, and the gate's escalation is recorded on the row.
        assert calls[0]["last_action_failed"] is True
        assert decision["escalated"] is True
        assert decision["jev_escalate_reason"] == "low_confidence_act (0.31)"

    def test_a_movement_action_is_still_the_plan_when_the_gate_escalates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_decide(
            monkeypatch,
            _jev_payload("DOWN", escalate=True, missing_class="map_topology"),
        )

        decision = cron_runner._jev_overworld_decision(
            _OBS, last_action="UP", last_action_changed_state=False
        )

        # Escalation is recorded for the teacher tier (stages 7-8, not built);
        # it does not stop the cheap tier from acting this cycle.
        assert decision["plan"] == ["DOWN"]
        assert decision["escalated"] is True
        assert decision["missing_class"] == "map_topology"

    def test_wait_means_press_nothing_not_press_a(self, monkeypatch) -> None:
        _install_decide(monkeypatch, _jev_payload("WAIT"))

        decision = cron_runner._jev_overworld_decision(_OBS)

        assert decision["plan"] == []
        assert decision["intent"] == "jev WAIT (no press)"
        assert decision["jev_answered"] is True

    def test_lowercase_answer_is_a_hit_like_the_starter_branch(
        self, monkeypatch
    ) -> None:
        _install_decide(monkeypatch, _jev_payload("right"))

        assert cron_runner._jev_overworld_decision(_OBS)["plan"] == ["RIGHT"]

    def test_the_overworld_vocabulary_is_the_button_set(self) -> None:
        assert cron_runner.OVERWORLD_ACTIONS == frozenset(
            {"UP", "DOWN", "LEFT", "RIGHT", "A", "B", "START", "WAIT"}
        )
        assert cron_runner.OVERWORLD_ACTIONS == frozenset(jev_client.BUTTONS)
        # Battle moves are not overworld actions.
        assert "MOVE_1" not in cron_runner.OVERWORLD_ACTIONS


class TestJevOverworldMiss:
    """DF-JEV-1 (2): a miss falls back to controller_plan() and never presses."""

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"ok": False, "error": "no key available"}, id="transport"),
            pytest.param(_jev_payload("RIGHT", ok=False), id="ok-false"),
            pytest.param(_jev_payload(None), id="no-action"),
            pytest.param({"ok": True, "raw": {}}, id="absent-action"),
            pytest.param(_jev_payload("TACKLE"), id="not-in-vocabulary"),
            pytest.param(_jev_payload("MOVE_1"), id="battle-move"),
            pytest.param(_jev_payload(7), id="non-string-action"),
            pytest.param(_jev_payload(""), id="empty-action"),
        ],
    )
    def test_miss_returns_no_plan(self, monkeypatch, payload) -> None:
        _install_decide(monkeypatch, payload)

        miss = cron_runner._jev_overworld_decision(_OBS)
        assert "plan" not in miss
        assert "jev_answered" not in miss

    def test_a_raising_tier_fails_closed_and_says_so(self, monkeypatch, capsys) -> None:
        def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("decisions endpoint exploded")

        monkeypatch.setattr(jev_client, "decide", boom)

        miss = cron_runner._jev_overworld_decision(_OBS)
        assert miss["ok"] is False
        assert "decisions endpoint exploded" in miss["error"]
        out = capsys.readouterr().out
        # Fail closed, but never silently: a broken tier must be visible.
        assert "decisions endpoint exploded" in out
        assert "falling back" in out

    def test_miss_leaves_the_loop_on_the_controller_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_decide(monkeypatch, _jev_payload("TACKLE"))
        miss = cron_runner._jev_overworld_decision(_OBS)
        assert "plan" not in miss

        # The fallback path's controller payload carries no JEV keys by itself;
        # jev_answered=False — exactly the pre-DF-JEV-1 behaviour.
        decision = cron_runner.controller_plan(
            _ScriptedClient('{"plan": ["UP"], "intent": "walk north"}'),
            _OBS,
            "",
            "",
        )

        assert decision["plan"] == ["UP"]
        assert "jev_answered" not in decision
        assert bool(decision.get("jev_answered", False)) is False
        assert bool(decision.get("escalated", False)) is False
        assert decision.get("raw_distribution") is None


class TestPlanEntryRowShape:
    """The row `main()` stamps: pinned to cron_runner.py's own source."""

    @staticmethod
    def _plan_entry_source() -> ast.Dict:
        source = Path(cron_runner.__file__).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "plan_entry"
                for target in node.targets
            ):
                assert isinstance(node.value, ast.Dict)
                return node.value
        raise AssertionError("plan_entry assignment not found in cron_runner.py")

    @staticmethod
    def _field(entry: ast.Dict, key: str) -> str:
        for field_key, value in zip(entry.keys, entry.values):
            if isinstance(field_key, ast.Constant) and field_key.value == key:
                return ast.unparse(value)
        raise AssertionError(f"{key} not stamped on plan_entry")

    @staticmethod
    def _if_on(name: str) -> ast.If:
        source = Path(cron_runner.__file__).read_text(encoding="utf-8")
        matches = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.If) and ast.unparse(node.test) == name
        ]
        assert len(matches) == 1, f"expected one `if {name}:`, found {len(matches)}"
        return matches[0]

    def test_row_names_the_pipeline_that_decided(self) -> None:
        entry = self._plan_entry_source()

        assert self._field(entry, "pipeline") == "_decision_pipeline"
        assert cron_runner.JEV_PIPELINE == "jev"

    def test_row_stamps_the_jev_proof_fields_from_the_payload(self) -> None:
        entry = self._plan_entry_source()

        assert "decision.get('raw_distribution')" == self._field(
            entry, "raw_distribution"
        )
        assert "decision.get('jev_answered'" in self._field(entry, "jev_answered")
        assert "decision.get('escalated'" in self._field(entry, "escalated")

    def test_jev_hit_selects_jev_pipeline_and_the_miss_calls_the_controller(
        self,
    ) -> None:
        node = self._if_on("_jev_attempt and _jev_attempt.get('jev_answered')")

        hit = [ast.unparse(stmt) for stmt in node.body]
        assert "decision = {**_jev_attempt, **_jev_outcome}" in hit
        assert "_decision_pipeline = JEV_PIPELINE" in hit

        miss = [ast.unparse(stmt) for stmt in node.orelse]
        assert "_decision_pipeline = pipeline_name" in miss
        assert any("controller_plan(" in stmt for stmt in miss)


class TestAutonomyRatioFromRealRows:
    """DF-JEV-1 (4): the run's ratio is counted from per-decision rows."""

    def test_ratio_is_jev_answered_over_decisions_total(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rows = [
            _decision_row(_jev_row(monkeypatch, "RIGHT"), "jev", 1),
            _decision_row(_jev_row(monkeypatch, "DOWN"), "jev", 2),
            _decision_row(_jev_row(monkeypatch, "A"), "jev", 3),
        ]
        fallback = cron_runner.controller_plan(
            _ScriptedClient('{"plan": ["A"], "intent": "try the door"}'), _OBS, "", ""
        )
        rows.append(_decision_row(fallback, "RAM reader", 4))

        block = cron_runner._autonomy_counters(rows)

        assert block["decisions_total"] == 4
        assert block["jev_answered"] == 3
        assert block["escalated"] == 0
        assert block["autonomy_ratio"] == 0.75
        assert (
            block["autonomy_ratio"] == block["jev_answered"] / block["decisions_total"]
        )

    def test_run_autonomy_row_reports_the_same_ratio(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rows = [
            _decision_row(_jev_row(monkeypatch, "RIGHT"), "jev", 1),
            _decision_row(
                _jev_decision(
                    monkeypatch,
                    _jev_payload("LEFT", escalate=True, missing_class="object_purpose"),
                ),
                "jev",
                2,
            ),
        ]
        fallback = cron_runner.controller_plan(
            _ScriptedClient('{"plan": ["A"]}'), _OBS, "", ""
        )
        rows.append(_decision_row(fallback, "RAM reader", 3))

        block = cron_runner._autonomy_counters(rows)
        buffer = io.StringIO()
        row = cron_runner._write_autonomy_row(buffer, "df-jev-1", block)
        parsed = json.loads(buffer.getvalue())

        assert parsed == row
        assert parsed["event"] == cron_runner.AUTONOMY_LOG_EVENT
        assert block["decisions_total"] == 3
        assert block["jev_answered"] == 2
        assert parsed["autonomy_ratio"] == round(
            parsed["jev_answered"] / parsed["decisions_total"], 4
        )
        assert parsed["escalation_rate_by_missing_class"] == {"object_purpose": 1.0}
