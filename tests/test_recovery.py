"""Unit tests for blocked-direction recovery logic in cron_runner.py.

The recovery logic tracks consecutive same-direction button presses and
triggers checkpoint rollback after a threshold. These tests verify the
pure-function behavior without needing an emulator or ROM.
"""
from __future__ import annotations


# ── Constants matching cron_runner.py ─────────────────────────────────────
MAX_SAME_DIRECTION = 5
_DIRECTIONS = {"UP", "DOWN", "LEFT", "RIGHT"}


# ── Pure functions extracted from cron_runner.py ──────────────────────────

def _track_direction(
    button: str,
    same_dir: str | None,
    same_dir_count: int,
) -> tuple[str | None, int]:
    """Track consecutive same-direction button presses.

    Mirrors the logic in cron_runner.py lines ~489-498.

    Args:
        button: The pressed button (e.g., "UP", "DOWN", "A", "B")
        same_dir: Currently tracked direction (or None)
        same_dir_count: Consecutive count for current direction

    Returns:
        (new_same_dir, new_same_dir_count)
    """
    if button in _DIRECTIONS:
        if button == same_dir:
            return (same_dir, same_dir_count + 1)
        else:
            return (button, 1)
    else:
        return (None, 0)


def _should_recover(
    same_dir_count: int,
    last_saved_slot: int | None,
) -> tuple[bool, str]:
    """Determine if blocked-direction recovery should fire.

    Args:
        same_dir_count: Consecutive same-direction presses
        last_saved_slot: Slot number of most recent checkpoint (or None)

    Returns:
        (should_rollback, reason_string)
    """
    if same_dir_count >= MAX_SAME_DIRECTION:
        if last_saved_slot is not None:
            return (True, f"load slot {last_saved_slot}")
        else:
            return (False, "no checkpoint available")
    return (False, "")


# ── Tests ─────────────────────────────────────────────────────────────────


class TestDirectionTracking:
    """Pure function tests for _track_direction."""

    def test_first_direction_sets_tracking(self) -> None:
        sd, count = _track_direction("DOWN", None, 0)
        assert sd == "DOWN"
        assert count == 1

    def test_same_direction_increments(self) -> None:
        sd, count = _track_direction("DOWN", "DOWN", 3)
        assert sd == "DOWN"
        assert count == 4

    def test_different_direction_resets(self) -> None:
        sd, count = _track_direction("LEFT", "DOWN", 5)
        assert sd == "LEFT"
        assert count == 1

    def test_non_direction_resets_tracking(self) -> None:
        sd, count = _track_direction("A", "DOWN", 4)
        assert sd is None
        assert count == 0

    def test_b_button_resets(self) -> None:
        sd, count = _track_direction("B", "UP", 3)
        assert sd is None
        assert count == 0

    def test_start_button_resets(self) -> None:
        sd, count = _track_direction("START", "LEFT", 6)
        assert sd is None
        assert count == 0

    def test_sequence_of_same_directions(self) -> None:
        """5 DOWN presses in a row should reach count 5."""
        sd, count = None, 0
        for _ in range(5):
            sd, count = _track_direction("DOWN", sd, count)
        assert sd == "DOWN"
        assert count == 5

    def test_mixed_directions_dont_accumulate(self) -> None:
        """DOWN, DOWN, LEFT, DOWN should NOT accumulate DOWN to 4."""
        sd, count = None, 0
        sd, count = _track_direction("DOWN", sd, count)   # DOWN x1
        sd, count = _track_direction("DOWN", sd, count)   # DOWN x2
        sd, count = _track_direction("LEFT", sd, count)   # LEFT x1 (resets)
        sd, count = _track_direction("DOWN", sd, count)   # DOWN x1 (resets)
        assert count == 1  # Not 4

    def test_interleaved_a_press_resets(self) -> None:
        """DOWN, DOWN, A, DOWN should reset to DOWN x1."""
        sd, count = None, 0
        sd, count = _track_direction("DOWN", sd, count)
        sd, count = _track_direction("DOWN", sd, count)
        sd, count = _track_direction("A", sd, count)
        assert sd is None
        assert count == 0
        sd, count = _track_direction("DOWN", sd, count)
        assert count == 1

    def test_twelve_consecutive_downs(self) -> None:
        """Full CART_STEPS=12 of DOWN should reach count 12."""
        sd, count = None, 0
        for _ in range(12):
            sd, count = _track_direction("DOWN", sd, count)
        assert sd == "DOWN"
        assert count == 12

    def test_all_four_directions_work(self) -> None:
        for direction in ("UP", "DOWN", "LEFT", "RIGHT"):
            sd, count = _track_direction(direction, None, 0)
            assert sd == direction
            assert count == 1
            sd2, count2 = _track_direction(direction, sd, count)
            assert count2 == 2


class TestRecoveryDecision:
    """Tests for _should_recover — the checkpoint-rollback trigger."""

    def test_below_threshold_no_recovery(self) -> None:
        should, reason = _should_recover(4, 0)
        assert not should
        assert reason == ""

    def test_at_threshold_with_checkpoint_triggers(self) -> None:
        should, reason = _should_recover(5, 2)
        assert should
        assert "load slot 2" in reason

    def test_above_threshold_with_checkpoint_triggers(self) -> None:
        should, reason = _should_recover(10, 3)
        assert should
        assert "load slot 3" in reason

    def test_at_threshold_no_checkpoint_blocks(self) -> None:
        """If _last_saved_slot is None, recovery should NOT fire."""
        should, reason = _should_recover(5, None)
        assert not should
        assert "no checkpoint" in reason

    def test_above_threshold_no_checkpoint_still_blocks(self) -> None:
        should, reason = _should_recover(12, None)
        assert not should
        assert "no checkpoint" in reason

    def test_count_zero_never_recovers(self) -> None:
        should, reason = _should_recover(0, 0)
        assert not should

    def test_count_one_never_recovers(self) -> None:
        should, reason = _should_recover(1, 0)
        assert not should


class TestEndToEndSequence:
    """Full sequences simulating cron_runner.py cartographer loop behavior."""

    def test_full_cart_steps_with_interleaved_a(self) -> None:
        """Simulate 12 steps where controller presses DOWN but occasionally
        A for interactions. Recovery should NOT fire because A resets count."""
        sd, count = None, 0
        last_slot: int | None = 0

        buttons = [
            "DOWN", "DOWN", "A", "DOWN", "DOWN", "A",
            "DOWN", "DOWN", "A", "DOWN", "DOWN", "A",
        ]
        recovered = False
        for btn in buttons:
            sd, count = _track_direction(btn, sd, count)
            should, reason = _should_recover(count, last_slot)
            if should:
                recovered = True
                break

        assert not recovered, (
            "Recovery should NOT fire with interleaved A presses "
            f"(final count={count})"
        )

    def test_full_cart_steps_all_down_with_checkpoint(self) -> None:
        """12 consecutive DOWNs with checkpoint available — recovery fires."""
        sd, count = None, 0
        last_slot: int | None = 0

        recovered = False
        for _ in range(12):
            sd, count = _track_direction("DOWN", sd, count)
            should, reason = _should_recover(count, last_slot)
            if should:
                recovered = True
                break

        assert recovered, (
            "Recovery SHOULD fire after 5+ consecutive DOWNs "
            f"with checkpoint (final count={count})"
        )

    def test_full_cart_steps_all_down_no_checkpoint(self) -> None:
        """12 consecutive DOWNs but NO checkpoint — recovery blocks."""
        sd, count = None, 0
        last_slot: int | None = None  # No checkpoint saved!

        recovered = False
        warned = False
        for _ in range(12):
            sd, count = _track_direction("DOWN", sd, count)
            should, reason = _should_recover(count, last_slot)
            if should:
                recovered = True
                break
            if count >= MAX_SAME_DIRECTION:
                warned = True  # We'd see the warning print in real code

        assert not recovered, (
            "Recovery should NOT fire without a checkpoint"
        )
        assert warned, (
            "Should have reached warning threshold "
            f"(count={count}, MAX={MAX_SAME_DIRECTION})"
        )

    def test_recovery_reset_after_rollback(self) -> None:
        """After recovery loads checkpoint, tracking resets and a new
        sequence of DOWNs should fire again."""
        sd, count = None, 0
        last_slot: int | None = 0

        # First sequence: 5 DOWNs → recovery
        for i in range(5):
            sd, count = _track_direction("DOWN", sd, count)
        assert _should_recover(count, last_slot)[0]

        # Simulate rollback: direction tracking resets
        sd, count = None, 0

        # Second sequence: 5 DOWNs → recovery again
        for i in range(5):
            sd, count = _track_direction("DOWN", sd, count)
        assert _should_recover(count, last_slot)[0]

    def test_direction_switch_resets_count_correctly(self) -> None:
        """Switching from DOWN to UP resets count to 1 (not 0)."""
        sd, count = _track_direction("DOWN", None, 0)   # DOWN x1
        sd, count = _track_direction("DOWN", sd, count)  # DOWN x2
        sd, count = _track_direction("DOWN", sd, count)  # DOWN x3
        sd, count = _track_direction("UP", sd, count)    # UP x1 (reset)
        assert count == 1
        sd, count = _track_direction("UP", sd, count)    # UP x2
        assert count == 2
