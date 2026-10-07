#!/usr/bin/env python3
"""Backfill historical episode summaries into DuckBrain.

The script reads ``cron_logs/*_episodes.jsonl``, groups every valid row by
``run_id``, and upserts one deterministic summary per run into the
``pokemon-global`` namespace. It also writes a bounded last-ten index and the
three mechanics records consumed by the run-start memory prompt.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_BASE_URL = "http://127.0.0.1:3000"
DEFAULT_NAMESPACE = "pokemon-global"
DEFAULT_TOKEN = Path.home() / ".duckbrain" / "foreman-status.token"
SAVE_CURRENT_PREFIX = "/game/save/current"
RUNS_PREFIX = "/game/runs/"
INDEX_KEY = "/game/runs/index"

MECHANICS = {
    "/game/mechanics/controls": (
        "Game Boy controls verified in cron_runner.py and src/core/tools.py: "
        "UP, DOWN, LEFT, and RIGHT move or navigate; A interacts with adjacent "
        "objects, NPCs, and doors and confirms selections; B cancels; START opens "
        "the menu; SELECT is an available button."
    ),
    "/game/mechanics/menus": (
        "Menu controls verified in cron_runner.py and src/core/tools.py: use the "
        "directional buttons to move the cursor, A to select or confirm, and B to "
        "cancel or back out. In battle, B also dismisses pending text before the "
        "command menu is actionable."
    ),
    "/game/mechanics/battle": (
        "Generation I battle facts verified in src/core/tools.py: the command menu "
        "is a 2x2 grid with FIGHT and BAG on the top row and PKMN and RUN on the "
        "bottom row. FIGHT opens up to four move slots; BAG uses an item; PKMN "
        "switches party slots; RUN can flee wild battles but trainer battles ignore it."
    ),
}


class BackfillError(RuntimeError):
    """Raised when input or DuckBrain operations cannot be completed safely."""


class DuckBrainClient:
    """Small authenticated HTTP client for the DuckBrain memory API."""

    def __init__(self, base_url: str, namespace: str, token: str) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise BackfillError("DuckBrain base URL must use http:// or https://")
        self.base_url = base_url.rstrip("/")
        self.namespace = namespace
        self.token = token

    def _url(self, path: str, query: dict[str, Any] | None = None) -> str:
        params = {"namespace": self.namespace}
        if query:
            params.update(query)
        return f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 -- base URL validated in __init__.
            self._url(path, query),
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self.token,
            },
        )
        try:
            # Constructor validation restricts the base URL to HTTP(S).
            with urllib.request.urlopen(  # noqa: S310  # nosec B310
                request, timeout=60
            ) as response:
                raw = response.read()
                payload = json.loads(raw) if raw else {}
                return response.status, payload
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"error": raw.decode("utf-8", errors="replace")}
            return exc.code, payload
        except urllib.error.URLError as exc:
            raise BackfillError(f"DuckBrain request failed: {exc}") from exc

    def get_key(self, key: str) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(key.lstrip("/"), safe="/")
        status, payload = self.request("GET", f"/api/memories/key/{encoded}")
        if status == 404:
            return None
        if status != 200:
            raise BackfillError(
                f"GET {key} returned HTTP {status}: {error_text(payload)}"
            )
        return payload

    def list_prefix(self, prefix: str, limit: int = 200) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            status, payload = self.request(
                "GET",
                "/api/memories",
                query={"prefix": prefix, "limit": limit, "offset": offset},
            )
            if status != 200:
                raise BackfillError(
                    f"GET prefix {prefix} returned HTTP {status}: {error_text(payload)}"
                )
            page = payload.get("items")
            if not isinstance(page, list):
                raise BackfillError("DuckBrain list response has no items array")
            items.extend(item for item in page if isinstance(item, dict))
            if not payload.get("hasMore"):
                break
            next_offset = payload.get("nextOffset")
            if not isinstance(next_offset, int) or next_offset <= offset:
                raise BackfillError("DuckBrain returned an invalid pagination offset")
            offset = next_offset
        return items

    def upsert(self, key: str, domain: str, content: str) -> str:
        existing = self.get_key(key)
        if existing is None:
            status, payload = self.request(
                "POST",
                "/api/memories",
                body={"key": key, "domain": domain, "content": content},
            )
            if status != 201:
                raise BackfillError(
                    f"POST {key} returned HTTP {status}: {error_text(payload)}"
                )
            return "created"

        if existing.get("domain") != domain:
            raise BackfillError(
                f"refusing to overwrite {key}: existing domain "
                f"{existing.get('domain')!r} != {domain!r}"
            )
        if existing.get("content") == content:
            return "unchanged"

        memory_id = existing.get("id")
        if not isinstance(memory_id, str) or not memory_id:
            raise BackfillError(f"existing memory {key} has no id")
        encoded_id = urllib.parse.quote(memory_id, safe="")
        status, payload = self.request(
            "PUT",
            f"/api/memories/{encoded_id}",
            body={"content": content},
        )
        if status != 200:
            raise BackfillError(
                f"PUT {key} returned HTTP {status}: {error_text(payload)}"
            )
        return "updated"


def error_text(payload: dict[str, Any]) -> str:
    """Return a compact API error without exposing request credentials."""
    return str(payload.get("error") or payload.get("message") or payload)[:300]


def candidate_token_files(preferred: Path) -> list[Path]:
    """Return the preferred token first, then other DuckBrain token files."""
    token_dir = preferred.parent
    paths = [preferred]
    if token_dir.is_dir():
        paths.extend(
            sorted(path for path in token_dir.glob("*.token") if path != preferred)
        )
    return paths


def find_working_token(
    base_url: str, namespace: str, preferred: Path
) -> tuple[str, Path]:
    """Probe read access and return the first accepted token without printing it."""
    failures: list[str] = []
    for path in candidate_token_files(preferred):
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            failures.append(f"{path.name}: {exc}")
            continue
        if not token:
            failures.append(f"{path.name}: empty")
            continue
        client = DuckBrainClient(base_url, namespace, token)
        status, payload = client.request(
            "GET",
            "/api/memories",
            query={"prefix": SAVE_CURRENT_PREFIX, "limit": 1},
        )
        if status == 200:
            return token, path
        failures.append(f"{path.name}: HTTP {status} {error_text(payload)}")
    raise BackfillError("no DuckBrain token was accepted; " + "; ".join(failures))


def load_episode_rows(
    log_dir: Path,
) -> tuple[list[Path], dict[str, list[dict[str, Any]]]]:
    """Load valid per-episode summary rows and group them by run id."""
    paths = sorted(log_dir.glob("*_episodes.jsonl"))
    if not paths:
        raise BackfillError(f"no *_episodes.jsonl files found under {log_dir}")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            raise BackfillError(f"cannot read {path}: {exc}") from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BackfillError(
                    f"invalid JSON at {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise BackfillError(f"non-object JSON at {path}:{line_number}")
            run_id = row.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip():
                raise BackfillError(f"missing run_id at {path}:{line_number}")
            copied = dict(row)
            copied["_source_file"] = str(path)
            grouped[run_id].append(copied)
    return paths, dict(grouped)


def numeric_total(rows: Iterable[dict[str, Any]], field: str) -> int | float:
    """Sum int/float values while rejecting booleans as numbers."""
    values = [row.get(field) for row in rows]
    numbers = [
        value
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    total = sum(numbers)
    return (
        round(total, 6) if any(isinstance(value, float) for value in numbers) else total
    )


def unique_values(values: Iterable[Any]) -> list[Any]:
    """Deduplicate JSON-compatible values while preserving encounter order."""
    output: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if marker not in seen:
            seen.add(marker)
            output.append(value)
    return output


def parse_content(content: Any) -> Any:
    """Decode JSON content when possible; preserve plain text otherwise."""
    if not isinstance(content, str):
        return content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content


def recursively_find_run_ids(value: Any) -> set[str]:
    """Find explicit run_id values in nested save/current records."""
    found: set[str] = set()
    if isinstance(value, dict):
        run_id = value.get("run_id")
        if isinstance(run_id, str) and run_id:
            found.add(run_id)
        for nested in value.values():
            found.update(recursively_find_run_ids(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(recursively_find_run_ids(nested))
    return found


def match_save_records(
    records: list[dict[str, Any]], run_ids: set[str]
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Associate save/current records with matching run ids without deleting them."""
    matched: dict[str, list[dict[str, Any]]] = defaultdict(list)
    folded = 0
    for record in records:
        key = str(record.get("key") or "")
        content = parse_content(record.get("content"))
        attributes = record.get("attributes")
        discovered = recursively_find_run_ids(content)
        discovered.update(recursively_find_run_ids(attributes))
        discovered.update(run_id for run_id in run_ids if run_id in key)
        for run_id in sorted(discovered & run_ids):
            matched[run_id].append(
                {
                    "key": key,
                    "content": content,
                    "attributes": attributes if isinstance(attributes, dict) else {},
                    "timestamp": record.get("timestamp"),
                }
            )
            folded += 1
    return dict(matched), folded


def row_timestamp(row: dict[str, Any]) -> str:
    value = row.get("at") or row.get("timestamp") or ""
    return str(value)


def outcome_for(rows: list[dict[str, Any]], errors: list[Any]) -> str:
    """Derive a compact, deterministic outcome label from episode evidence."""
    exit_codes = [row.get("exit_code") for row in rows]
    if any(isinstance(code, int) and code != 0 for code in exit_codes):
        return "failed"
    if any(row.get("goal_achieved") is True for row in rows):
        return "goal_achieved"
    completed_flags = [row.get("run_completed") for row in rows]
    if completed_flags and all(flag is False for flag in completed_flags):
        return "incomplete"
    if errors:
        return "completed_with_errors"
    if any(row.get("degraded") is True or row.get("state_ok") is False for row in rows):
        return "completed_degraded"
    return "completed"


def build_summary(
    run_id: str,
    rows: list[dict[str, Any]],
    save_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Distill all rows sharing one run id into one stable summary document."""
    ordered = sorted(rows, key=row_timestamp)
    maps_seen = unique_values(
        map_name
        for row in ordered
        for map_name in (row.get("maps_seen") or [])
        if isinstance(map_name, str) and map_name
    )
    map_sequence = [
        entry
        for row in ordered
        for entry in (row.get("map_sequence") or [])
        if isinstance(entry, (str, dict))
    ]
    final_maps = [row.get("final_map") for row in ordered if row.get("final_map")]
    errors = [
        error
        for row in ordered
        for error in (row.get("errors") or [])
        if error not in (None, "")
    ]

    autonomy_rows = [
        row["autonomy"] for row in ordered if isinstance(row.get("autonomy"), dict)
    ]
    decisions_total = sum(
        int(autonomy.get("decisions_total") or 0) for autonomy in autonomy_rows
    )
    if not autonomy_rows:
        decisions_total = int(numeric_total(ordered, "decisions"))
    jev_answered = int(numeric_total(ordered, "jev_answered"))
    escalated = int(numeric_total(ordered, "escalated"))
    autonomy = {
        "decisions_total": decisions_total,
        "jev_answered": jev_answered,
        "escalated": escalated,
        "autonomy_ratio": (
            round(jev_answered / decisions_total, 6) if decisions_total else 0.0
        ),
        "decision_modes": unique_values(
            value
            for row in ordered
            for value in [
                row.get("decision_mode_log"),
                (
                    (row.get("autonomy") or {}).get("decision_mode")
                    if isinstance(row.get("autonomy"), dict)
                    else None
                ),
            ]
            if isinstance(value, str) and value
        ),
        "degraded": any(
            row.get("degraded") is True
            or (
                isinstance(row.get("autonomy"), dict)
                and row["autonomy"].get("degraded") is True
            )
            for row in ordered
        ),
    }

    summary = {
        "run_id": run_id,
        "date": row_timestamp(ordered[-1]) if ordered else "",
        "first_date": row_timestamp(ordered[0]) if ordered else "",
        "episode_rows": len(ordered),
        "episodes": unique_values(
            row.get("episode") for row in ordered if row.get("episode") is not None
        ),
        "source_files": unique_values(row["_source_file"] for row in ordered),
        "exit_codes": unique_values(
            row.get("exit_code") for row in ordered if row.get("exit_code") is not None
        ),
        "outcome": outcome_for(ordered, errors),
        "wall_time_s": numeric_total(
            [
                {"value": row.get("wall_time_s", row.get("duration_s"))}
                for row in ordered
            ],
            "value",
        ),
        "cycles": int(numeric_total(ordered, "cycles")),
        "decisions": int(numeric_total(ordered, "decisions")),
        "jev_answered": jev_answered,
        "escalated": escalated,
        "autonomy": autonomy,
        "map_sequence": map_sequence,
        "maps_seen": maps_seen,
        "final_map": final_maps[-1] if final_maps else None,
        "errors": errors,
        "save_current": save_records,
    }
    return summary


def json_content(value: Any) -> str:
    """Encode deterministic JSON content for idempotent comparisons."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_index(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the ten latest runs in the compact required index shape."""
    latest = sorted(
        summaries,
        key=lambda summary: (str(summary.get("date") or ""), summary["run_id"]),
        reverse=True,
    )[:10]
    return [
        {
            "run_id": summary["run_id"],
            "date": summary["date"],
            "outcome": summary["outcome"],
            "final_map": summary["final_map"],
            "autonomy": summary["autonomy"],
        }
        for summary in latest
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN)
    parser.add_argument("--log-dir", type=Path, default=Path("cron_logs"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and report without writing memories",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        paths, grouped = load_episode_rows(args.log_dir)
        token, token_path = find_working_token(
            args.base_url, args.namespace, args.token_file
        )
        client = DuckBrainClient(args.base_url, args.namespace, token)
        save_records = client.list_prefix(SAVE_CURRENT_PREFIX)
        matched_saves, folded_count = match_save_records(save_records, set(grouped))
        summaries = [
            build_summary(run_id, rows, matched_saves.get(run_id, []))
            for run_id, rows in sorted(grouped.items())
        ]
        index = build_index(summaries)

        print(f"DuckBrain auth: accepted {token_path.name}")
        print(f"Episode JSONL files scanned: {len(paths)}")
        print(f"Runs found: {len(summaries)}")
        print(f"save/current records listed: {len(save_records)}")
        print(f"save/current folded count: {folded_count}")

        if args.dry_run:
            print("Summaries written: 0 (dry run)")
            print("Index written: 0 (dry run)")
            print("Mechanics written: 0 (dry run)")
            return 0

        states: dict[str, int] = defaultdict(int)
        for summary in summaries:
            key = f"{RUNS_PREFIX}{summary['run_id']}/summary"
            states[client.upsert(key, "event", json_content(summary))] += 1
        index_state = client.upsert(INDEX_KEY, "event", json_content(index))
        mechanic_states = [
            client.upsert(key, "concept", content) for key, content in MECHANICS.items()
        ]

        print(f"Summaries written: {len(summaries)}")
        print(
            "Summary upserts: "
            + ", ".join(f"{name}={states[name]}" for name in sorted(states))
        )
        print(f"Index written: 1 ({index_state}, entries={len(index)})")
        print(f"Mechanics written: {len(MECHANICS)} ({', '.join(mechanic_states)})")
        return 0
    except (BackfillError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
