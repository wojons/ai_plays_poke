#!/usr/bin/env python3
"""Side-by-side gameplay metrics for two battle-telemetry runs, one segment.

Contract: ``specs/contracts/battle-telemetry.md``. Row: BTL-COMPARE-1.
The engine lives in ``src/core/battle_run_compare.py``; this script only parses
arguments, drives it and prints what it produced.

What it does
------------
1. Reads ``/game/battle/<run_id>/manifest`` for each of the two runs — nothing
   else about a run is touched until the manifest's own index entries have been
   filtered (contract §5.2).
2. Applies E1..E6 (map, opponent species, opponent level band, encounter id,
   turn window, battle type) to those index entries, opens ONLY the surviving
   partitions and refines per record (E8).
3. Prints the side-by-side table (both models named), the partitions read and
   excluded with the key that excluded each, the store the numbers came from,
   the gaps, and a spot check that re-reads one summed record from disk.

Exit codes: 0 a table was printed, 1 no comparable data (named in the output),
2 bad arguments.

Data availability, stated honestly: this tool reports what the STORE contains.
If you point it at runs materialized from fixtures, the numbers are fixture
numbers and ``--note`` must say so — see ``--note``'s help text. Generating new
game runs is out of this script's scope; it never presses a button.

Examples:

    ./venv/bin/python scripts/compare_battle_runs.py \\
        --run-a 20261117_090000 --run-b 20261117_093000 \\
        --map "Viridian Forest" --opponent Weedle --level-lo 3 --level-hi 3 \\
        --battle-type wild
    ./venv/bin/python scripts/compare_battle_runs.py --census
    ./venv/bin/python scripts/compare_battle_runs.py --run-a A --run-b B --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.battle_run_compare import (  # noqa: E402
    DEFAULT_DATA_NOTE,
    NOT_DERIVABLE,
    ComparisonError,
    ComparisonReport,
    Segment,
    compare_runs,
    store_census,
)
from src.core.battle_telemetry_store import (  # noqa: E402
    DEFAULT_NAMESPACE,
    BattleTelemetryStore,
)

_NOT_DERIVABLE_NOTE = (
    "unlabeled: every number in this table comes from stored events; nothing "
    "here proves the runs were real game runs. Pass --note with the label the "
    "store actually represents (e.g. --note fixture) before quoting it."
)


# ── parser ──────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compare_battle_runs.py",
        description=(
            "Compare two battle-telemetry runs on one game segment: damage "
            "dealt vs taken, overkill, turns, hits/whiffs, wild-vs-trainer and "
            "per-level efficiency — read only from the keyed partitions of the "
            "pokemon-battle telemetry store."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Selection follows specs/contracts/battle-telemetry.md §5.2: the "
            "run manifests are read first and every exclusion is decided from "
            "a manifest entry, so an excluded partition is never opened.\n\n"
            + DEFAULT_DATA_NOTE
        ),
    )
    parser.add_argument("--run-a", metavar="ID", help="first run_id")
    parser.add_argument("--run-b", metavar="ID", help="second run_id")
    parser.add_argument(
        "--map",
        dest="map_name",
        default=None,
        metavar="NAME",
        help="E1: exact manifest map name (e.g. 'Viridian Forest')",
    )
    parser.add_argument(
        "--opponent",
        default=None,
        metavar="SPECIES",
        help="E2: exact opponent species (e.g. Weedle)",
    )
    parser.add_argument(
        "--level-lo", type=int, default=None, metavar="N", help="E3: band low"
    )
    parser.add_argument(
        "--level-hi", type=int, default=None, metavar="N", help="E3: band high"
    )
    parser.add_argument(
        "--battle-type",
        default=None,
        choices=("wild", "trainer", "unknown"),
        help="E6: battle type",
    )
    parser.add_argument(
        "--turn-lo", type=int, default=None, metavar="N", help="E5/E8: turn low"
    )
    parser.add_argument(
        "--turn-hi", type=int, default=None, metavar="N", help="E8: turn high"
    )
    parser.add_argument(
        "--encounter-id",
        action="append",
        default=[],
        metavar="epEEE-encCCC",
        help="E4: restrict to one encounter id (repeatable)",
    )
    parser.add_argument(
        "--store-root",
        default=None,
        metavar="DIR",
        help="directory holding <namespace>/data (default: DUCKBRAIN_ROOT)",
    )
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        metavar="NS",
        help=f"telemetry namespace (default: {DEFAULT_NAMESPACE})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the whole report as JSON instead of the text table",
    )
    parser.add_argument(
        "--census",
        action="store_true",
        help="only report what the store holds, then exit",
    )
    parser.add_argument(
        "--spot-check",
        default="a",
        choices=("a", "b", "none"),
        help="which run's damage figure to re-read from its raw record",
    )
    parser.add_argument(
        "--note",
        default=_NOT_DERIVABLE_NOTE,
        metavar="TEXT",
        help=(
            "provenance label printed with the table; must state whether the "
            "runs are real game runs or fixture events"
        ),
    )
    return parser


def build_segment(args: argparse.Namespace) -> Segment:
    return Segment(
        map_name=args.map_name,
        opponent_species=args.opponent,
        level_lo=args.level_lo,
        level_hi=args.level_hi,
        battle_type=args.battle_type,
        turn_lo=args.turn_lo,
        turn_hi=args.turn_hi,
        encounter_ids=tuple(args.encounter_id or ()),
    )


# ── output ──────────────────────────────────────────────────────────────────


def render_spot_check(report: ComparisonReport, which: str) -> list[str]:
    """Re-read one summed damage record and print it verbatim."""
    if which == "none":
        return []
    metrics = report.run_a if which == "a" else report.run_b
    label = "run A" if which == "a" else "run B"
    lines = [
        f"SPOT CHECK — {label} ({metrics.run_id}, {metrics.model_label}):",
    ]
    try:
        check = report.spot_check_damage(which)
    except ComparisonError as exc:
        lines.append(f"  no damage figure to trace: {exc}")
        return lines
    lines.append(
        f"  damage_dealt_total={metrics.damage_dealt_total} includes "
        f"{check.ref.ref} = {check.ref.damage} HP"
    )
    lines.append(f"  {check.summary}")
    lines.append("  raw record: " + json.dumps(dict(check.raw), sort_keys=True))
    return lines


def render_not_derivable() -> list[str]:
    lines = ["NOT DERIVABLE FROM THE RECORD SHAPE:"]
    for metric, reason in NOT_DERIVABLE.items():
        lines.append(f"  - {metric}: {reason}")
    return lines


def run(args: argparse.Namespace) -> int:
    root = Path(args.store_root).expanduser() if args.store_root else None
    try:
        store = BattleTelemetryStore(namespace=args.namespace, root=root)
    except (OSError, ValueError) as exc:
        print(f"compare_battle_runs: {exc}", file=sys.stderr)
        return 2

    if args.census:
        census = store_census(store)
        print(census.summary())
        for run_id in census.run_ids:
            state = "manifest" if run_id in census.runs_with_manifest else "NO manifest"
            count = sum(1 for name in census.event_files if run_id in name)
            print(f"  {run_id}: {count} partition file(s), {state}")
        return 0

    if not args.run_a or not args.run_b:
        print(
            "compare_battle_runs: --run-a and --run-b are required (or use --census)",
            file=sys.stderr,
        )
        return 2
    try:
        segment = build_segment(args)
    except ComparisonError as exc:
        print(f"compare_battle_runs: {exc}", file=sys.stderr)
        return 2

    try:
        report = compare_runs(
            args.run_a,
            args.run_b,
            segment,
            store=store,
            data_note=args.note,
        )
    except ComparisonError as exc:
        print(f"compare_battle_runs: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload: dict[str, Any] = report.to_dict()
        if args.spot_check != "none":
            try:
                check = report.spot_check_damage(args.spot_check)
            except ComparisonError:
                payload["spot_check"] = None
            else:
                payload["spot_check"] = {
                    "metric": check.metric,
                    "run_id": check.run_id,
                    "model_label": check.model_label,
                    "raw_ref": check.ref.ref,
                    "identity": check.ref.identity,
                    "damage": check.ref.damage,
                    "matches": check.matches,
                    "raw": dict(check.raw),
                }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return 0 if report.comparable else 1

    print(report.render())
    print("")
    for line in render_spot_check(report, args.spot_check):
        print(line)
    if args.spot_check != "none":
        print("")
    for line in render_not_derivable():
        print(line)
    return 0 if report.comparable else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
