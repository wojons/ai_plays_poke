"""Regression tests for PyBoy boot-log suppression."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pyboy.logging import ERROR, get_log_level, get_logger, log_level

from src.core import emulator as emulator_module


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
    """PyBoy INFO-level SGB chatter is filtered from both output streams."""
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

        message = "Special Game Boy color command: 0xe000!"
        get_logger("pyboy.core.mb").info(message)

        captured = capsys.readouterr()
        assert message not in captured.out
        assert message not in captured.err
    finally:
        log_level(previous_level)
