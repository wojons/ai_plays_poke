"""
Lightweight DuckBrain client for AI Plays Pokémon.

Reads/writes directly to DuckBrain's JSONL storage — no MCP/HTTP needed.
Each namespace is a directory under ~/duckbrain/namespaces/<name>/data/.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DUCKBRAIN_ROOT = Path(os.path.expanduser("~/duckbrain/namespaces"))


def _ensure_namespace(ns: str) -> Path:
    """Create namespace directory if needed, return data dir path."""
    data_dir = DUCKBRAIN_ROOT / ns / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def remember(
    key: str,
    domain: str,
    attributes: dict[str, Any],
    embedding_text: str,
    namespace: str = "pokemon-global",
) -> str:
    """Store a memory and return its UUID."""
    if not key.startswith("/"):
        key = "/" + key

    data_dir = _ensure_namespace(namespace)
    memory_id = str(uuid.uuid4())

    record = {
        "id": memory_id,
        "key": key,
        "domain": domain,
        "attributes": attributes,
        "embedding_text": embedding_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
    }

    # Append to today's JSONL file
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    jsonl_path = data_dir / f"memories-{today}.jsonl"
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(record) + "\n")

    return memory_id


def recall(
    key: str | None = None,
    key_prefix: str | None = None,
    domain: str | None = None,
    limit: int = 10,
    namespace: str = "pokemon-global",
) -> list[dict[str, Any]]:
    """Query memories by key, prefix, or domain."""
    data_dir = _ensure_namespace(namespace)
    results: list[dict[str, Any]] = []

    if not data_dir.exists():
        return results

    # Read all JSONL files (newest first)
    jsonl_files = sorted(data_dir.glob("memories-*.jsonl"), reverse=True)
    for jsonl_path in jsonl_files:
        try:
            with open(jsonl_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Skip tombstones
                    if record.get("status") == "deleted":
                        continue

                    # Filter
                    if key and record.get("key") != key:
                        continue
                    if key_prefix and not record.get("key", "").startswith(key_prefix):
                        continue
                    if domain and record.get("domain") != domain:
                        continue

                    results.append(record)
                    if len(results) >= limit:
                        return results
        except Exception:
            continue

    return results


def list_keys(
    prefix: str = "/",
    namespace: str = "pokemon-global",
    limit: int = 50,
) -> list[str]:
    """List unique keys under a prefix."""
    data_dir = _ensure_namespace(namespace)
    keys: set[str] = set()

    if not data_dir.exists():
        return []

    jsonl_files = sorted(data_dir.glob("memories-*.jsonl"), reverse=True)
    for jsonl_path in jsonl_files:
        try:
            with open(jsonl_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if record.get("status") == "deleted":
                        continue

                    k = record.get("key", "")
                    if k.startswith(prefix):
                        keys.add(k)
                    if len(keys) >= limit:
                        return sorted(keys)
        except Exception:
            continue

    return sorted(keys)
