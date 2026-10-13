#!/usr/bin/env python3
"""PERF-6 benchmark harness: FrameCache registration throughput at N=5000.

Usage: .venv/bin/python scripts/bench_frame_cache.py [N]
Prints a single elapsed-seconds figure for N unique registrations with
MAX_ENTRIES=1000, suitable for hyperfine comparison against the baseline.
"""
import sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.core.frame_cache import FrameCache  # noqa: E402

def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    t0 = time.perf_counter()
    cache = FrameCache(path=":memory:")
    for i in range(n):
        cache.register(f"{i:08x}" * 8, cycle=i)
    print(f"elapsed={time.perf_counter() - t0:.6f}s n={n}")

if __name__ == "__main__":
    main()
