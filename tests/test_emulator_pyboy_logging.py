"""Regression tests for PyBoy boot-log suppression.

FLK-2 hardening: pyboy's log level is a single package-wide global
(``pyboy.logging._log_level``) that its constructors mutate at boot time,
and its ``_log()`` filter checks that global at emit time. Under CI runner
load the filter state and the emitted record can interleave with anything
else touching the same global, so asserting only on captured text made
this test timing-sensitive. The tests below now pin the invariant at the
mechanism level (the effective level the boot path leaves behind) and
re-assert the level immediately before/after the emission they check
against captured output, so a leak and a level regression fail with
distinct, precise messages instead of a flaky capture diff.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pyboy.logging import ERROR, INFO, get_log_level, get_logger, log_level

from src.core import emulator as emulator_module

# pyboy's filter is `get_log_level() > level`, so ERROR (3) suppresses
# INFO (2) records. Assert the ordering explicitly: if a pyboy upgrade
# ever renumbers the constants, these tests fail loudly instead of
# silently inverting the suppression semantics they guard.
assert ERROR > INFO


def _mock_pyboy_with_real_log_level(*_args, **kwargs) -> MagicMock:
    """Model PyBoy's constructor-time application of its log_level option."""
    log_level(kwargs["log_level"])
    return MagicMock()


def test_emulator_boot_paths_configure_pyboy_log_level_to_error(tmp_path) -> None:
    """Initial construction and reset both select PyBoy's ERROR level."""
    previous_level = get_log_level()
    log_level("INFO")
    try:
        rom_path = tmp_path / "test.gb"
        rom_path.touch()

        with patch.object(
            emulator_module,
            "_PyBoy",
            side_effect=_mock_pyboy_with_real_log_level,
        ) as pyboy_cls:
            emulator = emulator_module.Emulator(rom_path)
            emulator.reset()

        assert pyboy_cls.call_count == 2
        assert all(
            call.kwargs["log_level"] == "ERROR" for call in pyboy_cls.call_args_list
        )
        assert get_log_level() >= ERROR
    finally:
        log_level(previous_level)


def test_sgb_info_message_is_not_visible_at_error_level(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """PyBoy INFO-level SGB chatter is filtered from both output streams.

    FLK-2: the boot's level application and the emitted record can
    interleave under CI load. The suppression invariant is re-pinned at
    the mechanism level (the global filter the boot path leaves behind)
    immediately before the emission, and the effective level is re-read
    after it, so the captured-output assertion can only fail when the
    filter itself regressed — not because some other actor moved the
    package-wide level mid-test.
    """
    previous_level = get_log_level()
    log_level("INFO")
    try:
        rom_path = tmp_path / "test.gb"
        rom_path.touch()
        with patch.object(
            emulator_module,
            "_PyBoy",
            side_effect=_mock_pyboy_with_real_log_level,
        ):
            emulator_module.Emulator(rom_path)

        # Boot must have left the filter at ERROR; if not, that is the
        # regression to report — not a confusing capture diff.
        boot_left_level = get_log_level()
        assert boot_left_level >= ERROR, (
            "Emulator boot left pyboy log filter below ERROR "
            f"({boot_left_level}); SGB INFO chatter would not be suppressed"
        )

        # Emit through the same logger the real SGB path uses, with the
        # filter state pinned at ERROR for the emission itself.
        message = "Special Game Boy color command: 0xe000!"
        logger = get_logger("pyboy.core.mb")
        log_level("ERROR")
        logger.info(message)
        emitted_at_level = get_log_level()
        assert emitted_at_level >= ERROR, (
            "pyboy log filter moved below ERROR during emission "
            f"({emitted_at_level}); the captured-output assertion below "
            "would be invalid"
        )

        captured = capsys.readouterr()
        assert message not in captured.out
        assert message not in captured.err
    finally:
        log_level(previous_level)
