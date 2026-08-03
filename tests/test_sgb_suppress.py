"""
Regression tests for cron_runner._SGBSuppress (GAMEPLAY-LEAK-001).

The original filter thread wrote non-SGB lines back through the
``sys.stderr`` file object, whose fd was already dup2'd to the class's own
pipe — re-entering the pipe and looping forever while growing an unbounded
``_buf`` (70-100 MB/s during battle cycles, killing runs at ~50 GB).
It also split lines at 4096-byte read boundaries, so truncated
``Unimplemented SGB`` fragments bypassed the filter and fed the loop.

NOTE: tests write to fd 2 directly (``os.write``) because pytest replaces
``sys.stderr`` with its capture object, which never reaches the dup2'd pipe.
"""

from __future__ import annotations

import os
import time

from cron_runner import _SGBSuppress


def _wait_for(pred, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_sgb_suppress_buf_bounded_under_flood() -> None:
    """Flooding fd 2 must not grow _buf past the cap (no feedback loop)."""
    with _SGBSuppress() as s:
        payload = b"GB: Unimplemented SGB command: 0F\n" * 50000
        payload += b"normal stderr line\n" * 50000
        os.write(2, payload)
        assert _wait_for(lambda: len(s._buf) > 0)
        time.sleep(0.5)
        assert len(s._buf) <= s._MAX_BUF_LINES, (
            f"_buf grew to {len(s._buf)} lines — feedback loop regression"
        )


def test_sgb_suppress_drops_sgb_noise_keeps_normal() -> None:
    """SGB lines are dropped; normal lines pass through to real stderr."""
    with _SGBSuppress() as s:
        os.write(2, b"GB: Unimplemented SGB command: 0F\nkeep me\n")
        assert _wait_for(lambda: any("keep me" in line for line in s._buf))
        assert all("Unimplemented SGB" not in line for line in s._buf), (
            "SGB noise leaked into _buf"
        )
