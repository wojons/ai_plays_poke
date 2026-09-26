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
    labels: list[str] | None = None,
    confidence: float | None = None,
    evidence: dict[str, Any] | None = None,
    applies_when: dict[str, Any] | None = None,
) -> str:
    """Store a memory and return its UUID."""
    if not key.startswith("/"):
        key = "/" + key

    data_dir = _ensure_namespace(namespace)
    memory_id = str(uuid.uuid4())

    record: dict[str, Any] = {
        "id": memory_id,
        "key": key,
        "domain": domain,
        "attributes": attributes,
        "embedding_text": embedding_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
    }
    if labels is not None:
        record["labels"] = labels
    if confidence is not None:
        record["confidence"] = confidence
    if evidence is not None:
        record["evidence"] = evidence
    if applies_when is not None:
        record["applies_when"] = applies_when

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
    labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Query memories by key, prefix, domain, or labels.

    Label filters use AND semantics: every requested label must match an exact
    string in the record's labels list or equal the record's domain, which is
    treated as an implicit label.
    """
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
                    if labels is not None:
                        record_labels = record.get("labels", [])
                        if not isinstance(record_labels, list):
                            record_labels = []
                        if not all(
                            label == record.get("domain") or label in record_labels
                            for label in labels
                        ):
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


def get(
    key: str,
    namespace: str = "pokemon-global",
) -> dict[str, Any] | None:
    """Read the most recent active memory with this exact key."""
    if not key.startswith("/"):
        key = "/" + key
    results = recall(key=key, namespace=namespace, limit=1)
    return results[0] if results else None


def search(
    text: str,
    namespace: str = "pokemon-global",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Content search across memory bodies (embedding_text + attributes).

    Unlike recall() (which matches key prefixes), search() finds facts by
    what they SAY — for deep, nested discovery.
    """
    data_dir = _ensure_namespace(namespace)
    results: list[dict[str, Any]] = []
    needle = text.lower()

    if not data_dir.exists():
        return results

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
                    haystack = (
                        str(record.get("embedding_text", ""))
                        + " "
                        + str(record.get("attributes", {}))
                    ).lower()
                    if needle in haystack:
                        results.append(record)
                        if len(results) >= limit:
                            return results
        except Exception:
            continue

    return results
