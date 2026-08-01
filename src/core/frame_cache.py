"""Persistent screenshot frame cache with UUID references.

Dedup strategy for vision-capable controllers (Luna via OpenRouter):

- Every screenshot is md5-hashed. The hash is the lookup key.
- First time a frame is seen: send the image to the model, store an
  entry {uuid, hash, seen_count, first_seen_cycle, last_seen_cycle,
  map_name, screen} and persist it to disk.
- Any later cycle that produces the SAME hash (standing still, dialog
  open, battle idle, re-walking the same map tile, looping game flow)
  does NOT re-send the image bytes. Instead the controller prompt gets
  a short text reference: "SCREEN REF <uuid> — this exact frame was
  sent before (seen N times); assume identical visuals."

This cuts image token spend on repeated frames — 91 raw screenshots in
a test run collapsed to 24 unique frames — and the cache survives
across runs (JSON on disk), so revisiting a map in a later session
also hits.

Eviction: LRU by last_seen_cycle, capped at MAX_ENTRIES (1000).
"""

from __future__ import annotations

import hashlib
import json
import uuid as _uuid
from pathlib import Path
from typing import Any


class FrameCache:
    """Hash → UUID frame cache with LRU eviction and disk persistence."""

    MAX_ENTRIES = 1000

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._by_hash: dict[str, dict[str, Any]] = {}  # md5 → entry
        self._by_uuid: dict[str, dict[str, Any]] = {}  # uuid → entry
        self._seq = 0
        self._load()

    # ── Persistence ────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text())
                self._by_hash = data.get("by_hash", {})
                self._by_uuid = data.get("by_uuid", {})
                self._seq = data.get("seq", 0)
        except (json.JSONDecodeError, OSError, ValueError):
            # Corrupt or unreadable cache — start fresh rather than crash
            self._by_hash = {}
            self._by_uuid = {}
            self._seq = 0

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "by_hash": self._by_hash,
                "by_uuid": self._by_uuid,
                "seq": self._seq,
            }
            self._path.write_text(json.dumps(payload))
        except OSError:
            pass  # cache is best-effort; never crash the game loop

    # ── Lookup / registration ──────────────────────────────────────

    @staticmethod
    def hash_frame(frame_bytes: bytes) -> str:
        """Return the md5 hex digest for raw screenshot bytes."""
        return hashlib.md5(frame_bytes).hexdigest()

    def lookup(self, frame_hash: str) -> dict[str, Any] | None:
        """Return the cached entry for *frame_hash*, or None on miss."""
        return self._by_hash.get(frame_hash)

    def register(
        self,
        frame_hash: str,
        cycle: int,
        map_name: str = "",
        screen: str = "",
    ) -> dict[str, Any]:
        """Store a new frame; returns the created entry (with uuid)."""
        self._seq += 1
        entry = {
            "uuid": _uuid.uuid4().hex[:12],
            "hash": frame_hash,
            "seen_count": 1,
            "first_seen_cycle": cycle,
            "last_seen_cycle": cycle,
            "map_name": map_name,
            "screen": screen,
        }
        self._by_hash[frame_hash] = entry
        self._by_uuid[entry["uuid"]] = entry
        self._evict()
        return entry

    def touch(self, entry: dict[str, Any], cycle: int) -> None:
        """Mark an existing entry as seen again (bump recency + count)."""
        entry["seen_count"] = int(entry.get("seen_count", 0)) + 1
        entry["last_seen_cycle"] = cycle
        entry["map_name"] = entry.get("map_name", "")
        # Move to end of LRU order by re-inserting in by_hash
        self._by_hash[entry["hash"]] = entry

    # ── Eviction ───────────────────────────────────────────────────

    def _evict(self) -> None:
        """Drop oldest entries (by last_seen_cycle) past MAX_ENTRIES."""
        if len(self._by_hash) <= self.MAX_ENTRIES:
            return
        # Sort by last_seen_cycle ascending, evict the oldest
        oldest = sorted(
            self._by_hash.values(),
            key=lambda e: int(e.get("last_seen_cycle", 0)),
        )
        for entry in oldest[: len(self._by_hash) - self.MAX_ENTRIES]:
            self._by_hash.pop(entry["hash"], None)
            self._by_uuid.pop(entry["uuid"], None)

    # ── Stats ──────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._by_hash)

    @property
    def total_seen(self) -> int:
        """Total reference count across all entries (hits + registrations)."""
        return sum(int(e.get("seen_count", 1)) for e in self._by_hash.values())

    @property
    def unique_frames(self) -> int:
        return len(self._by_hash)

    def stats(self) -> dict[str, Any]:
        return {
            "cached_frames": self.unique_frames,
            "total_references": self.total_seen,
            "max_entries": self.MAX_ENTRIES,
            "path": str(self._path),
        }
