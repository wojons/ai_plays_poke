# Verdict: PERF-6

**Task:** FrameCache LRU heap eviction
**Evaluated:** 2026-10-13T00:45:13.937037
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✗ lint: scanners: nice=nice -n 10
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: scanners: nice=nice -n 10
- ✓ **tier2**
  - COMPLETE
  ✓ FrameCache eviction uses a min-heap instead of full-cache sort; correctness (touch/eviction ordering, persistence) proven by full pytest suite; hyperfine re-measure in-repo shows the heap candidate at least 2x faster than baseline at N=5000.: Min-heap: src/core/frame_cache.py:26 imports heapq; :48-58 builds _lru_heap + heapq.heapify on load; :123 heappush in register; :140 heappush in touch; :149 heappop in _evict with lazy stale-entry invalidation (:152-157). Baseline f9d3e91^:src/core/frame_cache.py:120 used sorted() full-cache sort (confirmed via git show). Correctness: `./.venv/bin/pytest -q --tb=short -p no:cacheprovider -n 4` => '4483 passed, 14 skipped in 56.64s', 0 FAILED/ERROR; tests/test_frame_cache.py 14 passed incl. test_touch_updates_lru_ordering, test_lru_eviction_picks_oldest_entry, test_lru_eviction_preserves_registration_order_for_equal_cycles, test_lru_eviction_skips_stale_heap_entries, test_loaded_cache_rebuilds_lru_order_for_eviction, test_persistence_across_instances, test_cache_size_stays_bounded_at_max_entries. Hyperfine: in-repo artifact benchmarks/perf6_frame_cache_after.json (heap mean 0.0583s, 20 runs, exit 0) + harness scripts/bench_frame_cache.py (commit 16f7a69); my independent hyperfine re-measure: baseline 282.9ms vs heap 52.7ms => '5.37 ± 0.91 times faster' (>=2x required).
FrameCache now uses a lazy-invalidated min-heap (heapq) instead of a full-cache sort, the full pytest suite passes (4483 passed, 14 skipped, 0 failed) with all 14 frame_cache correctness tests green, and an in-repo hyperfine re-measure shows the heap candidate 5.37x faster than baseline at N=5000.

## Summary

Judge Result: PERF-6

Stage tier1: FAIL
    ✗ lint: scanners: nice=nice -n 10
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: scanners: nice=nice -n 10

Stage tier2: PASS
  COMPLETE
  ✓ FrameCache eviction uses a min-heap instead of full-cache sort; correctness (touch/eviction ordering, persistence) proven by full pytest suite; hyperfine re-measure in-repo shows the heap candidate at least 2x faster than baseline at N=5000.: Min-heap: src/core/frame_cache.py:26 imports heapq; :48-58 builds _lru_heap + heapq.heapify on load; :123 heappush in register; :140 heappush in touch; :149 heappop in _evict with lazy stale-entry invalidation (:152-157). Baseline f9d3e91^:src/core/frame_cache.py:120 used sorted() full-cache sort (confirmed via git show). Correctness: `./.venv/bin/pytest -q --tb=short -p no:cacheprovider -n 4` => '4483 passed, 14 skipped in 56.64s', 0 FAILED/ERROR; tests/test_frame_cache.py 14 passed incl. test_touch_updates_lru_ordering, test_lru_eviction_picks_oldest_entry, test_lru_eviction_preserves_registration_order_for_equal_cycles, test_lru_eviction_skips_stale_heap_entries, test_loaded_cache_rebuilds_lru_order_for_eviction, test_persistence_across_instances, test_cache_size_stays_bounded_at_max_entries. Hyperfine: in-repo artifact benchmarks/perf6_frame_cache_after.json (heap mean 0.0583s, 20 runs, exit 0) + harness scripts/bench_frame_cache.py (commit 16f7a69); my independent hyperfine re-measure: baseline 282.9ms vs heap 52.7ms => '5.37 ± 0.91 times faster' (>=2x required).
FrameCache now uses a lazy-invalidated min-heap (heapq) instead of a full-cache sort, the full pytest suite passes (4483 passed, 14 skipped, 0 failed) with all 14 frame_cache correctness tests green, and an in-repo hyperfine re-measure shows the heap candidate 5.37x faster than baseline at N=5000.

Overall: FAIL ✗
