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
    entry = c2.lookup(h)
    assert entry is not None
    assert entry["map_name"] == "Oak's Lab"
    assert c2.size == 1


def test_loaded_cache_rebuilds_lru_order_for_eviction(cache_path: Path) -> None:
    class TinyCache(FrameCache):
        MAX_ENTRIES = 2

    first = TinyCache(cache_path)
    oldest_hash = first.hash_frame(b"oldest")
    middle_hash = first.hash_frame(b"middle")
    first.register(oldest_hash, cycle=10)
    first.register(middle_hash, cycle=20)
    first.save()

    loaded = TinyCache(cache_path)
    newest_hash = loaded.hash_frame(b"newest")
    loaded.register(newest_hash, cycle=30)

    assert loaded.lookup(oldest_hash) is None
    assert loaded.lookup(middle_hash) is not None
    assert loaded.lookup(newest_hash) is not None


def test_corrupt_cache_starts_fresh(cache_path: Path) -> None:
    cache_path.write_text("{not valid json!!!")
    cache = FrameCache(cache_path)
    assert cache.size == 0
    assert cache.lookup("anything") is None


def test_lru_eviction_picks_oldest_entry(cache_path: Path) -> None:
    class TinyCache(FrameCache):
        MAX_ENTRIES = 2

    tiny = TinyCache(cache_path)
    oldest_hash = tiny.hash_frame(b"oldest")
    middle_hash = tiny.hash_frame(b"middle")
    newest_hash = tiny.hash_frame(b"newest")

    tiny.register(oldest_hash, cycle=10)
    tiny.register(middle_hash, cycle=20)
    tiny.register(newest_hash, cycle=30)

    assert tiny.lookup(oldest_hash) is None
    assert tiny.lookup(middle_hash) is not None
    assert tiny.lookup(newest_hash) is not None


def test_lru_eviction_preserves_registration_order_for_equal_cycles(
    cache_path: Path,
) -> None:
    class TinyCache(FrameCache):
        MAX_ENTRIES = 2

    tiny = TinyCache(cache_path)
    first_hash = "f" * 32
    second_hash = "0" * 32
    newest_hash = "a" * 32

    tiny.register(first_hash, cycle=10)
    tiny.register(second_hash, cycle=10)
    tiny.register(newest_hash, cycle=20)

    assert tiny.lookup(first_hash) is None
    assert tiny.lookup(second_hash) is not None
    assert tiny.lookup(newest_hash) is not None


def test_touch_updates_lru_ordering(cache_path: Path) -> None:
    class TinyCache(FrameCache):
        MAX_ENTRIES = 2

    tiny = TinyCache(cache_path)
    first_hash = tiny.hash_frame(b"first")
    second_hash = tiny.hash_frame(b"second")
    touched_entry = tiny.register(first_hash, cycle=10)
    tiny.register(second_hash, cycle=20)

    tiny.touch(touched_entry, cycle=30)
    tiny.register(tiny.hash_frame(b"newest"), cycle=40)

    assert tiny.lookup(first_hash) is not None
    assert tiny.lookup(second_hash) is None


def test_lru_eviction_skips_stale_heap_entries(cache_path: Path) -> None:
    class TinyCache(FrameCache):
        MAX_ENTRIES = 2

    tiny = TinyCache(cache_path)
    first_hash = tiny.hash_frame(b"first")
    second_hash = tiny.hash_frame(b"second")
    touched_entry = tiny.register(first_hash, cycle=10)
    tiny.register(second_hash, cycle=20)

    tiny.touch(touched_entry, cycle=30)
    lru_heap = getattr(tiny, "_lru_heap")
    assert any(
        timestamp_key[0] == 10 and frame_hash == first_hash
        for timestamp_key, frame_hash in lru_heap
    )

    newest_hash = tiny.hash_frame(b"newest")
    tiny.register(newest_hash, cycle=40)

    assert tiny.lookup(first_hash) is not None
    assert tiny.lookup(second_hash) is None
    assert tiny.lookup(newest_hash) is not None


def test_cache_size_stays_bounded_at_max_entries(cache_path: Path) -> None:
    cache = FrameCache(cache_path)

    for cycle in range(FrameCache.MAX_ENTRIES + 25):
        cache.register(cache.hash_frame(f"frame-{cycle}".encode()), cycle=cycle)
        assert cache.size <= FrameCache.MAX_ENTRIES

    assert cache.size == FrameCache.MAX_ENTRIES
    assert cache.lookup(cache.hash_frame(b"frame-0")) is None
    assert cache.lookup(cache.hash_frame(b"frame-1024")) is not None


def test_stats_report(cache_path: Path) -> None:
    cache = FrameCache(cache_path)
    h = cache.hash_frame(b"stats-frame")
    cache.register(h, cycle=1)
    entry = cache.lookup(h)
    assert entry is not None
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
