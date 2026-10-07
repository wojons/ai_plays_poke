"""BASE-REPIN guard: the tracked default boot state must match its pinned md5.

long_run checkpoints once re-saved ``data/boot.state`` mid-run, silently moving
its md5 away from what the baseline artifacts documented (BASE-REPIN). This
test makes that drift loud: any change to the default checkpoint without an
explicit re-pin commit fails here before a run boots from the wrong state.
"""

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = REPO_ROOT / "data" / "baselines" / "boot_state_pin.json"
BOOT_STATE_PATH = REPO_ROOT / "data" / "boot.state"


def test_boot_state_matches_pin():
    assert PIN_PATH.is_file(), f"md5 pin missing: {PIN_PATH}"
    pin = json.loads(PIN_PATH.read_text())
    assert pin["file"] == "data/boot.state"
    assert BOOT_STATE_PATH.is_file(), f"default boot state missing: {BOOT_STATE_PATH}"
    digest = hashlib.md5(
        BOOT_STATE_PATH.read_bytes(), usedforsecurity=False
    ).hexdigest()
    assert digest == pin["md5"], (
        f"data/boot.state md5 drifted: expected {pin['md5']}, found {digest}. "
        "A run re-saved the default checkpoint. Restore from "
        "data/baselines/base-1_boot.state or explicitly re-pin with evidence."
    )


def test_known_good_baseline_survives():
    baseline = REPO_ROOT / "data" / "baselines" / "base-1_boot.state"
    assert baseline.is_file(), f"known-good baseline missing: {baseline}"
    digest = hashlib.md5(baseline.read_bytes(), usedforsecurity=False).hexdigest()
    assert digest == "81e4ec4e8d1b62002bc78f619c5fc79c", (
        f"base-1_boot.state moved ({digest}) — the documented baseline is gone "
        "and future baselines would cite an md5 that no longer exists on disk."
    )
