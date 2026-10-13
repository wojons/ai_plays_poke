# Verdict: PERF-6

**Task:** FrameCache LRU heap eviction
**Evaluated:** 2026-10-13T01:02:14.365126
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
  ✓ tests: scanners: nice=nice -n 10
- ✓ **tier2**
  - COMPLETE
  ✓ FrameCache eviction uses a min-heap instead of full-cache sort; correctness (touch/eviction ordering, persistence) proven by full pytest suite; hyperfine re-measure in-repo shows the heap candidate at least 2x faster than baseline at N=5000.: Min-heap: src/core/frame_cache.py imports heapq, builds self._lru_heap via heapq.heapify in __init__, uses heapq.heappush in register()/touch(), and _evict() uses heapq.heappop with lazy invalidation (checks last_seen_cycle + order); git show f9d3e91 diff confirms removal of the old `sorted(self._by_hash.values(), key=lambda e: int(e.get('last_seen_cycle',0)))` full-cache sort. Correctness: tests/test_frame_cache.py 14/14 PASSED (touch ordering, eviction ordering, equal-cycle tie-break, stale-heap skip, persistence across instances, loaded-cache rebuild, bounded size). Full suite: `.venv/bin/python -m pytest tests/ -k 'not benchmark' -q` => '4433 passed, 14 skipped, 50 deselected in 214.48s', 0 failed. Hyperfine re-measure at N=5000: `hyperfine --warmup 3 --runs 20 <baseline> <heap>` => baseline 317.2 ms ± 64.0 ms vs heap 50.7 ms ± 1.4 ms, '6.25 ± 1.27 times faster' (>=2x). In-repo artifacts: scripts/bench_frame_cache.py harness + benchmarks/perf6_frame_cache_after.json (heap mean 0.058s); baseline figure documented in commit f9d3e91 (291.6 ms vs 111.1 ms, 2.62x).
FrameCache now evicts via a lazy-invalidated min-heap (heapq) replacing the full-cache sort, with 14/14 frame-cache tests and the full suite (4433 passed, 0 failed) green and a fresh hyperfine re-measure showing the heap 6.25x faster than baseline at N=5000.

## Summary

Judge Result: PERF-6

Stage tier1: FAIL
  WARNING: coverage is secrets+lint+tests — secrets did not run (skipped at runtime — secrets: timed out after 120s (step budget)); run `gitreins guard` for the full gate
    ✓ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
  ✓ tests: scanners: nice=nice -n 10

Stage tier2: PASS
  COMPLETE
  ✓ FrameCache eviction uses a min-heap instead of full-cache sort; correctness (touch/eviction ordering, persistence) proven by full pytest suite; hyperfine re-measure in-repo shows the heap candidate at least 2x faster than baseline at N=5000.: Min-heap: src/core/frame_cache.py imports heapq, builds self._lru_heap via heapq.heapify in __init__, uses heapq.heappush in register()/touch(), and _evict() uses heapq.heappop with lazy invalidation (checks last_seen_cycle + order); git show f9d3e91 diff confirms removal of the old `sorted(self._by_hash.values(), key=lambda e: int(e.get('last_seen_cycle',0)))` full-cache sort. Correctness: tests/test_frame_cache.py 14/14 PASSED (touch ordering, eviction ordering, equal-cycle tie-break, stale-heap skip, persistence across instances, loaded-cache rebuild, bounded size). Full suite: `.venv/bin/python -m pytest tests/ -k 'not benchmark' -q` => '4433 passed, 14 skipped, 50 deselected in 214.48s', 0 failed. Hyperfine re-measure at N=5000: `hyperfine --warmup 3 --runs 20 <baseline> <heap>` => baseline 317.2 ms ± 64.0 ms vs heap 50.7 ms ± 1.4 ms, '6.25 ± 1.27 times faster' (>=2x). In-repo artifacts: scripts/bench_frame_cache.py harness + benchmarks/perf6_frame_cache_after.json (heap mean 0.058s); baseline figure documented in commit f9d3e91 (291.6 ms vs 111.1 ms, 2.62x).
FrameCache now evicts via a lazy-invalidated min-heap (heapq) replacing the full-cache sort, with 14/14 frame-cache tests and the full suite (4433 passed, 0 failed) green and a fresh hyperfine re-measure showing the heap 6.25x faster than baseline at N=5000.

Overall: FAIL ✗
