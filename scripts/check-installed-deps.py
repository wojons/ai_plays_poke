#!/usr/bin/env python3
"""Check that the *installed* packages satisfy a requirements file's floors.

`pip list --outdated` answers "is anything behind the latest release?", which is a
different question from "does this environment satisfy what we declared?" —
transitive packages nobody pins are `outdated` forever and matter not at all,
while a direct dependency installed below its declared floor (fastapi 0.143.0
against `fastapi>=0.162.0`) is a real drift that no scan reports as such.

This script answers the second question, per interpreter, with no network access
and no pip dependency (`importlib.metadata` reads the dist-info already on disk).
It is the one-command witness used by the DEPS rows and by
`docs/dependency_reconcile_20261026.md`.

Usage:
    ./venv/bin/python scripts/check-installed-deps.py requirements.txt
    ./.venv/bin/python scripts/check-installed-deps.py requirements-dev.txt

Exit codes: 0 = every requirement satisfied, 1 = drift/missing, 2 = usage error.

Version comparison uses `packaging` when it is importable (full PEP 440) and
falls back to a local numeric-tuple comparator for the simple `>=`/`>`/`<=`/`<`/
`==` floors this repo declares. The fallback exists because a minimalist runtime
venv may not ship `packaging`; it is not a general-purpose PEP 440 parser.
"""

from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError, version

_SPEC_RE = re.compile(r"^(>=|<=|==|!=|>|<)\s*([0-9][^,\s]*)$")


def _split_req(line: str) -> tuple[str, str] | None:
    """Split one requirement line into (name, specifier string)."""
    line = line.split(";", 1)[0].strip()  # drop environment markers
    if not line or line.startswith(("-", "#")):
        return None
    match = re.match(r"^([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*(.*)$", line)
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def _read_requirements(path: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            parsed = _split_req(raw.split("#", 1)[0].strip() if "#" in raw else raw)
            if parsed is not None:
                out.append(parsed)
    return out


def _numeric(part: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", part)
    return tuple(int(n) for n in nums) or (0,)


def _fallback_contains(specifier: str, installed: str) -> bool:
    """Minimal comparator for >=, >, <=, <, == over dotted numeric versions."""
    for clause in [c.strip() for c in specifier.split(",") if c.strip()]:
        match = _SPEC_RE.match(clause)
        if not match:
            continue  # unparseable clause: do not invent a violation
        op, want = match.groups()
        have_t, want_t = _numeric(installed), _numeric(want)
        width = max(len(have_t), len(want_t))
        have_t += (0,) * (width - len(have_t))
        want_t += (0,) * (width - len(want_t))
        checks = {
            ">=": have_t >= want_t,
            ">": have_t > want_t,
            "<=": have_t <= want_t,
            "<": have_t < want_t,
            "==": have_t == want_t,
            "!=": have_t != want_t,
        }
        if not checks[op]:
            return False
    return True


def satisfied(specifier: str, installed: str) -> bool:
    if not specifier:
        return True
    try:
        from packaging.requirements import Requirement
    except ImportError:
        return _fallback_contains(specifier, installed)
    return Requirement(f"x{specifier}").specifier.contains(installed, prereleases=True)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    exit_code = 0
    for path in argv[1:]:
        print(f"=== {path} (interpreter: {sys.version.split()[0]}) ===")
        failures = 0
        checked = 0
        for name, spec in _read_requirements(path):
            checked += 1
            try:
                installed = version(name)
            except PackageNotFoundError:
                failures += 1
                print(f"FAIL  {name:<28} MISSING            required {spec or '(any)'}")
                continue
            if satisfied(spec, installed):
                print(f"OK    {name:<28} {installed:<18} satisfies {spec or '(any)'}")
            else:
                failures += 1
                print(f"FAIL  {name:<28} {installed:<18} required {spec}")
        print(f"\n{checked} requirements checked, {failures} failing\n")
        if failures:
            exit_code = 1
    if exit_code == 0:
        print("RESULT: PASS — installed versions satisfy every declared floor")
    else:
        print("RESULT: FAIL — reconcile the environment (pip install -r <file>)")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
