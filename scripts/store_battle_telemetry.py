#!/usr/bin/env python3
"""Store contract-shaped battle telemetry through the partitioned writer.

Contract: ``specs/contracts/battle-telemetry.md``. Row: BTL-STORE-1.
The writer lives in ``src/core/battle_telemetry_store.py``; this script only
parses contract records, groups them per encounter and drives the store.

Input: one or more JSONL files of contract records — the output of
``scripts/capture_battle_telemetry.py`` is exactly this shape (one record per
line, §3.1 + §3.2 fields). ``-`` reads stdin.

What a write run does:

1. Loads every record, groups them by ``(run_id, episode, encounter_id)``.
2. Calls ``BattleTelemetryStore.append_encounter`` per group: the §3.3 rules are
   enforced there, the §4.2 caps split an over-long encounter into the next
   ``enc<CCC>`` partition, and a re-write of the same encounter is skipped
   instead of duplicated.
3. Writes the single §4.3 manifest per run through the DuckBrain client.

``--verify`` runs the §7.1 partition checker (a superset: it also runs N7
against the manifests through the same client) and prints its verdict.

Exit codes: 0 success / verified, 1 verification violation, 2 bad input.

Examples:

    ./venv/bin/python scripts/store_battle_telemetry.py \\
        --records /tmp/battle.jsonl --print-manifest
    ./venv/bin/python scripts/store_battle_telemetry.py --verify
    ./venv/bin/python scripts/store_battle_telemetry.py --verify \\
        --store-root /tmp/battle-root
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core import duckbrain_client  # noqa: E402
from src.core.battle_telemetry_store import (  # noqa: E402
    DEFAULT_NAMESPACE,
    MANIFEST_KEY_PREFIX,
    MAX_BYTES_PER_FILE,
    MAX_RECORDS_PER_FILE,
    REQUIRED_KEYS,
    BattleTelemetryStore,
    TelemetryStoreError,
    client_root,
)

#: §3.1 encounter id shape; also the filename's ep/enc segment.
_ENCOUNTER_ID = re.compile(r"^ep(\d{3})-enc(\d{3})$")

#: §7.1's filename pattern, spelled out here so the checker is independent of
#: the store's own parser (a shared regex would hide a store-side regression).
_CHECK_NAME = re.compile(r"^battle-([A-Za-z0-9_]+)-ep(\d{3})-enc(\d{3})\.jsonl$")


# ── input ───────────────────────────────────────────────────────────────────


def load_records(paths: Sequence[str]) -> list[dict[str, Any]]:
    """Read contract records from JSONL files (``-`` = stdin)."""
    records: list[dict[str, Any]] = []
    for spec in paths:
        if spec == "-":
            text = sys.stdin.read()
            source = "<stdin>"
        else:
            path = Path(spec)
            text = path.read_text(encoding="utf-8")
            source = str(path)
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{number} is not JSON ({exc})") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"{source}:{number} is not a JSON object")
            records.append(parsed)
    return records


def group_records(
    records: Iterable[Mapping[str, Any]],
) -> list[tuple[str, int, int, list[dict[str, Any]]]]:
    """Group records per encounter, in first-appearance order."""
    groups: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for raw in records:
        record = dict(raw)
        run_id = record.get("run_id")
        encounter_id = record.get("encounter_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("a record carries no run_id (§3.1 requires it)")
        if not isinstance(encounter_id, str):
            raise ValueError(f"record in run {run_id} carries no encounter_id")
        match = _ENCOUNTER_ID.match(encounter_id)
        if match is None:
            raise ValueError(
                f"encounter_id {encounter_id!r} does not match ep<EEE>-enc<CCC>"
            )
        episode = int(match.group(1))
        ordinal = int(match.group(2))
        groups.setdefault((run_id, episode, ordinal), []).append(record)
    return [
        (run_id, episode, ordinal, group)
        for (run_id, episode, ordinal), group in groups.items()
    ]


# ── write mode ──────────────────────────────────────────────────────────────


def run_write(args: argparse.Namespace) -> int:
    try:
        records = load_records(args.records)
        groups = group_records(records)
    except (OSError, ValueError) as exc:
        print(f"store_battle_telemetry: {exc}", file=sys.stderr)
        return 2
    if not groups:
        print("store_battle_telemetry: no records to store", file=sys.stderr)
        return 2
    if args.run_id is not None:
        stray = sorted({run for run, _ep, _o, _g in groups if run != args.run_id})
        if stray:
            print(
                f"store_battle_telemetry: --run-id {args.run_id} but records name "
                f"{stray}",
                file=sys.stderr,
            )
            return 2
    if args.episode is not None:
        stray_episodes = sorted(
            {episode for _r, episode, _o, _g in groups if episode != args.episode}
        )
        if stray_episodes:
            print(
                f"store_battle_telemetry: --episode {args.episode} but records name "
                f"{stray_episodes}",
                file=sys.stderr,
            )
            return 2

    root = Path(args.store_root).expanduser() if args.store_root else None
    store = BattleTelemetryStore(
        namespace=args.namespace,
        root=root,
        decision_arm=args.decision_arm,
        model_decision=args.model_decision,
        model_vision=args.model_vision,
        provider=args.provider,
    )

    summary: dict[str, Any] = {
        "namespace": store.namespace,
        "root": str(store.root),
        "encounters": [],
        "written": 0,
        "skipped": 0,
        "dropped": 0,
    }
    try:
        for run_id, episode, ordinal, group in groups:
            result = store.append_encounter(
                group,
                run_id=run_id,
                episode=episode,
                encounter_ordinal=ordinal,
                map_name=args.map,
                battle_type=args.battle_type,
                outcome=args.encounter_outcome,
            )
            summary["written"] += result.written
            summary["skipped"] += result.skipped
            summary["dropped"] += result.dropped
            summary["encounters"].append(
                {
                    "encounter_ids": list(result.encounter_ids),
                    "files": list(result.files),
                    "written": result.written,
                    "skipped": result.skipped,
                    "dropped": result.dropped,
                }
            )
        manifests = {}
        for run_id in dict.fromkeys(run for run, _e, _o, _g in groups):
            write = store.write_manifest(run_id=run_id)
            manifests[run_id] = {
                "key": write.key,
                "written": write.written,
                "index": len(write.attributes["index"]),
                "encounters_total": write.attributes["encounters_total"],
                "dropped_records": write.attributes["dropped_records"],
                "truncated": write.attributes["truncated"],
            }
    except TelemetryStoreError as exc:
        # The record was refused (R1/R3/R4/R5/R6) and counted on the store; the
        # manifest still lands so the loss is visible rather than silent.
        for run_id in dict.fromkeys(run for run, _e, _o, _g in groups):
            store.write_manifest(run_id=run_id)
        print(f"store_battle_telemetry: refused: {exc}", file=sys.stderr)
        print(
            json.dumps(
                {"dropped_records": store.dropped_records, "status": "refused"},
                default=str,
            ),
            file=sys.stderr,
        )
        return 2

    summary["manifests"] = manifests
    summary["dropped_records"] = store.dropped_records
    if args.print_manifest:
        for run_id in manifests:
            manifest = store.read_manifest(run_id)
            print(json.dumps(manifest, default=str, sort_keys=True))
    else:
        print(json.dumps(summary, default=str, sort_keys=True))
    return 0


# ── verify mode (§7.1, plus N7) ─────────────────────────────────────────────


def _stray_repo_telemetry(repo_root: Path) -> list[str]:
    """N1/N8 — no telemetry file may live inside the repo tree."""
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--", "*battle*.jsonl"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    return [path for path in completed.stdout.split("\0") if path]


def verify(root: Path, namespace: str, repo_root: Path) -> int:
    """The §7.1 paste-and-run check, parameterised by store root, plus N7."""
    bad: list[str] = []
    for stray in _stray_repo_telemetry(repo_root):
        bad.append(f"N1: telemetry inside the repo: {stray}")

    data_root = root / namespace / "data"
    if data_root.is_dir():
        for path in sorted(data_root.iterdir()):
            if not path.is_file():
                continue
            is_event = path.name.startswith("battle-") and path.suffix == ".jsonl"
            is_memory = path.name.startswith("memories-") and path.suffix == ".jsonl"
            if not (is_event or is_memory):
                bad.append(f"N1/N8: unexpected file in telemetry root: {path.name}")
        for path in sorted(data_root.glob("memories-*.jsonl")):
            for number, line in enumerate(
                [text for text in path.read_text().splitlines() if text.strip()], 1
            ):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    bad.append(f"N9: {path.name}:{number} is not JSON ({exc})")
                    continue
                if not str(record.get("key", "")).startswith(MANIFEST_KEY_PREFIX):
                    bad.append(
                        f"N9: {path.name}:{number} carries a non-manifest key "
                        f"{record.get('key')!r}"
                    )

    files = sorted(data_root.glob("battle-*.jsonl")) if data_root.is_dir() else []
    total = 0
    if not files:
        print(
            f"NO_TELEMETRY_FILES: {data_root} holds no battle-*.jsonl yet — "
            "N2..N6 are vacuously satisfied"
        )
        print("STRAY_IN_REPO: none" if not bad else "STRAY_IN_REPO: " + "; ".join(bad))
        return _manifest_verdict(root, namespace, bad)

    for path in files:
        match = _CHECK_NAME.match(path.name)
        if match is None:
            bad.append(f"N2: {path.name} does not parse to run_id+episode+encounter_id")
            continue
        run_id, episode, ordinal = (
            match.group(1),
            int(match.group(2)),
            int(match.group(3)),
        )
        expected = f"ep{episode:03d}-enc{ordinal:03d}"
        size = path.stat().st_size
        if size > MAX_BYTES_PER_FILE:
            bad.append(f"N4: {path.name} is {size} B > {MAX_BYTES_PER_FILE}")
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        if len(lines) > MAX_RECORDS_PER_FILE:
            bad.append(
                f"N3: {path.name} has {len(lines)} records > {MAX_RECORDS_PER_FILE}"
            )
        for number, line in enumerate(lines, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                bad.append(f"N6: {path.name}:{number} is not JSON ({exc})")
                continue
            missing = [key for key in REQUIRED_KEYS if key not in record]
            if missing:
                bad.append(f"N6: {path.name}:{number} missing {missing}")
            if record.get("run_id") != run_id:
                bad.append(
                    f"N6: {path.name}:{number} run_id {record.get('run_id')!r} != "
                    f"path {run_id!r}"
                )
            if record.get("encounter_id") != expected:
                bad.append(
                    f"N6: {path.name}:{number} encounter_id "
                    f"{record.get('encounter_id')!r} != {expected!r}"
                )
        total += len(lines)

    if bad:
        print(f"BATTLE_TELEMETRY_PARTITION: FAIL ({len(bad)} violations)")
        for item in bad:
            print("  -", item)
        return 1
    print(
        f"BATTLE_TELEMETRY_PARTITION: PASS ({len(files)} files, {total} records, "
        f"cap {MAX_RECORDS_PER_FILE} rec / {MAX_BYTES_PER_FILE} B)"
    )
    return _manifest_verdict(root, namespace, bad)


def _manifest_verdict(root: Path, namespace: str, bad: list[str]) -> int:
    """N7 — one bounded manifest per run, read back through the client."""
    if bad:
        return 1
    data_root = root / namespace / "data"
    if not data_root.is_dir():
        print("MANIFEST_RULE: PASS (no namespace data dir yet — vacuous pass)")
        return 0
    with client_root(root):
        manifests = duckbrain_client.recall(
            key_prefix=MANIFEST_KEY_PREFIX, namespace=namespace, limit=1000
        )
    flagged = 0
    for record in manifests:
        attributes = record.get("attributes", {})
        index = attributes.get("index", [])
        total = int(attributes.get("encounters_total", 0))
        if index and len(index) < total and not attributes.get("truncated"):
            print(
                f"N7 FAIL {attributes.get('run_id')}: {len(index)} of {total} "
                "and truncated!=true"
            )
            flagged += 1
        if len(index) > 1000:
            print(f"N7 FAIL {attributes.get('run_id')}: index {len(index)} > 1000")
            flagged += 1
    if flagged:
        return 1
    print(
        f"MANIFEST_RULE: PASS ({len(manifests)} manifest record(s); "
        "0 is a vacuous pass)"
    )
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="store_battle_telemetry.py",
        description=(
            "Append contract-shaped battle-telemetry records to partitioned "
            "DuckBrain files and write the per-run manifest. No emulator, no "
            "network: a store run reads JSONL and writes files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Field names, partitioning, caps and the validation rules come from "
            "specs/contracts/battle-telemetry.md."
        ),
    )
    parser.add_argument(
        "--records",
        action="append",
        default=[],
        metavar="PATH",
        help="JSONL of contract records (repeatable; '-' reads stdin)",
    )
    parser.add_argument(
        "--store-root",
        default=None,
        metavar="DIR",
        help="directory holding <namespace>/data (default: the client's DUCKBRAIN_ROOT)",
    )
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        metavar="NS",
        help=f"telemetry namespace (default: {DEFAULT_NAMESPACE})",
    )
    parser.add_argument("--run-id", default=None, metavar="ID")
    parser.add_argument("--episode", type=int, default=None, metavar="N")
    parser.add_argument("--decision-arm", default=None, metavar="LABEL")
    parser.add_argument("--model-decision", default=None, metavar="MODEL")
    parser.add_argument("--model-vision", default=None, metavar="MODEL")
    parser.add_argument("--provider", default=None, metavar="PROVIDER")
    parser.add_argument(
        "--map",
        default=None,
        metavar="NAME",
        help="assert the encounter's map (must agree with every record)",
    )
    parser.add_argument(
        "--battle-type",
        default=None,
        metavar="TYPE",
        help="assert wild|trainer|unknown (must agree with every record)",
    )
    parser.add_argument(
        "--encounter-outcome",
        default=None,
        metavar="OUTCOME",
        help="stamp won|lost|fled|caught|unknown on the manifest entry",
    )
    parser.add_argument(
        "--print-manifest",
        action="store_true",
        help="print the manifest record(s) read back through the client",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="run the contract §7.1 partition check (plus N7) and exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verify:
        root = (
            Path(args.store_root).expanduser()
            if args.store_root
            else Path(duckbrain_client.DUCKBRAIN_ROOT)
        )
        return verify(root, args.namespace, REPO_ROOT)

    if not args.records:
        parser.error("--records is required unless --verify is given")
    return run_write(args)


if __name__ == "__main__":
    raise SystemExit(main())
