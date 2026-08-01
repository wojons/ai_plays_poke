"""Tests for the persistent FrameCache (screenshot UUID dedup)."""

import json
from pathlib import Path

import pytest

from src.core.frame_cache import FrameCache


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    return tmp_path / "frame_cache.json"


def test_hash_frame_is_stable(cache_path: Path) -> None:
    cache = FrameCache(cache_path)
    h1 = cache.hash_frame(b"\x00\x01\x02")
    h2 = cache.hash_frame(b"\x00\x01\x02")
    h3 = cache.hash_frame(b"\x00\x01\x03")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 32  # md5 hex


def test_register_and_lookup(cache_path: Path) -> None:
    cache = FrameCache(cache_path)
    h = cache.hash_frame(b"frame-data")
    entry = cache.register(h, cycle=1, map_name="Pallet Town", screen="overworld")
    assert entry["uuid"]
    assert len(entry["uuid"]) == 12
    assert entry["seen_count"] == 1
    assert entry["map_name"] == "Pallet Town"

    found = cache.lookup(h)
    assert found is not None
    assert found["uuid"] == entry["uuid"]


def test_touch_increments_seen_count(cache_path: Path) -> None:
    cache = FrameCache(cache_path)
    h = cache.hash_frame(b"frame-data")
    entry = cache.register(h, cycle=1)
    assert entry["seen_count"] == 1
    cache.touch(entry, cycle=2)
    assert entry["seen_count"] == 2
    assert entry["last_seen_cycle"] == 2


def test_miss_returns_none(cache_path: Path) -> None:
    cache = FrameCache(cache_path)
    assert cache.lookup(cache.hash_frame(b"never-seen")) is None


def test_persistence_across_instances(cache_path: Path) -> None:
    c1 = FrameCache(cache_path)
    h = c1.hash_frame(b"persistent-frame")
    c1.register(h, cycle=1, map_name="Oak's Lab")
    c1.save()

    c2 = FrameCache(cache_path)  # fresh instance, same path
    assert c2.lookup(h) is not None
    assert c2.lookup(h)["map_name"] == "Oak's Lab"
    assert c2.size == 1


def test_corrupt_cache_starts_fresh(cache_path: Path) -> None:
    cache_path.write_text("{not valid json!!!")
    cache = FrameCache(cache_path)
    assert cache.size == 0
    assert cache.lookup("anything") is None


def test_lru_eviction_keeps_newest(cache_path: Path) -> None:
    cache = FrameCache(cache_path)
    # Bypass MAX_ENTRIES via a tiny subclass to test eviction cheaply
    class TinyCache(FrameCache):
        MAX_ENTRIES = 3

    tiny = TinyCache(cache_path)
    for i in range(5):
        h = tiny.hash_frame(f"frame-{i}".encode())
        tiny.register(h, cycle=i)
    assert tiny.size == 3
    # Oldest two (frame-0, frame-1) evicted
    assert tiny.lookup(tiny.hash_frame(b"frame-0")) is None
    assert tiny.lookup(tiny.hash_frame(b"frame-4")) is not None
    # Touching an old entry keeps it alive (LRU recency)
    old_h = tiny.hash_frame(b"frame-2")
    old_entry = tiny.lookup(old_h)
    assert old_entry is not None
    tiny.touch(old_entry, cycle=99)
    for i in range(5, 7):
        tiny.register(tiny.hash_frame(f"frame-{i}".encode()), cycle=i)
    # frame-3 should be evicted next; frame-2 was touched → still present
    assert tiny.lookup(tiny.hash_frame(b"frame-3")) is None
    assert tiny.lookup(old_h) is not None


def test_stats_report(cache_path: Path) -> None:
    cache = FrameCache(cache_path)
    h = cache.hash_frame(b"stats-frame")
    cache.register(h, cycle=1)
    entry = cache.lookup(h)
    cache.touch(entry, cycle=2)
    stats = cache.stats()
    assert stats["cached_frames"] == 1
    assert stats["total_references"] == 2
    assert stats["max_entries"] == FrameCache.MAX_ENTRIES


def test_disk_payload_shape(cache_path: Path) -> None:
    cache = FrameCache(cache_path)
    cache.register(cache.hash_frame(b"shape"), cycle=1)
    cache.save()
    payload = json.loads(cache_path.read_text())
    assert set(payload) == {"by_hash", "by_uuid", "seq"}
