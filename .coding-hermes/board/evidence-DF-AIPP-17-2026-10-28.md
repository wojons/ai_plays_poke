# DF-AIPP-17 — closeout evidence (2026-10-28, planner-residual arm)

Tick: ai-plays-poke-foreman-2026-10-28-16-41-22
Implementation commit: c2f19195570965c95529c4f829cc1c4bc00448cb (pushed to origin/main)

ch:trace row=DF-AIPP-17 spec=cron_runner.py#memory-navigation-planner wave=serial test=tests/test_navigation_dead_end_route.py doc=none:commit-message prompt=/tmp/df17-brief-planner-route.txt evidence=cron_logs/run_df17plan2.jsonl witness=live:cron_logs/run_df17plan2.jsonl verdict=none:tier2-async commit=c2f19195570965c95529c4f829cc1c4bc00448cb memory=none:foreman-writes

STATUS: complete (AC1 close arm; AC2/AC3 landed 2026-10-28 at 146197f)
TIER: T2 (15 focused tests passed; full suite 4557 passed 14 skipped, mypy clean, ruff clean; live 80-cycle jev witness run_df17plan2: navigation_transition OUT of map 37 at cycle 46 — 12 cycles after re-entry, window 20; guard rows 9 all outcome=declined, zero rewrites)
EVIDENCE: commit c2f19195570965c95529c4f829cc1c4bc00448cb + cron_logs/run_df17plan2.jsonl (gitignored runtime artifact — values quoted here are durable) + cron_logs/run_df17plan1.jsonl (mid-fix probe)

## What landed (c2f1919, worker deepseek-v4-flash@deepseek-foreman, worktree wt/DF-AIPP-17)

- _memory_escape_candidates: dead-end maps search escapes through the run's OWN proven edges to visited maps (door = recorded arrival tile, press = opposite of crossing direction), restricted to NAVIGATION_OBJECTIVE_SEQUENCE maps, ordered by ladder step then recency. Unvisited routes still outrank escapes.
- Hold guard stands down for planner-authored escapes (outcome=skipped with escape_destination + memory_route_key); collision-aware decline from 146197f preserved for model-authored plans.
- arrival_tile settle window (ARRIVAL_TILE_SETTLE_READS=10/FRAMES=20): wCurMap flips one frame before the warp rewrites wXCoord/wYCoord, so the transition-cycle read stored the SOURCE tile ((5,5) instead of the 1F door mat (2,7)); _settle_arrival_tile burns a bounded poll and _path_memory_write prefers the settled tile.
- Direction-lock recovery counts progress, not presses: a press that changed the tile resets the counter (pre-fix it fired one tile short of the door mat and rotated the escape away).
- Escape payload carries route_kind/derivation/destination_visited/objective_gateway so an escape is never read as new-ground progress; autonomy summary counts memory_navigation_escapes separately.
- Tests: tests/test_navigation_dead_end_route.py — 15 cases. Red-proof: 7/11 original cases fail against 4324837's cron_runner.py.

## AC verification (foreman re-ran every probe from the JSONL)

- AC1: run_df17plan2 (80 cycles, jev, data/boot.state, 64/64 API success, 0 transport failures): Pallet Town->1F c3, 1F->2F c32 (route_tiles through door tile (5,6) and stair tile (7,2)), 2F->1F c34, 12 memory-nav escape cycles to door tile (2,7), 1F->Pallet Town c46. Pre-fix (run_df17fixa at 146197f): 1 transition total, tiles alternating (3,6)/(3,7), never left map 37.
- AC2 (from 146197f + this commit): run_df17plan2 navigation_hold_guard rows = 9, all outcome=declined (no plan rewrites); escape rows carry route_kind=dead_end_escape (cycles 34-45, 48-49, 56+ in df17plan1).
- AC3 (from 146197f): navigation_dead_end dedicated event exists; zero fired in df17plan2 (no trapped tile remained).

## Gates

- Full suite (worktree, at c2f1919): 4557 passed / 14 skipped in 219s, exit 0.
- mypy cron_runner.py: Success, no issues. ruff check + format: clean.
- Focused: tests/test_navigation_dead_end_route.py 15 passed in 0.05s.
- Merge: ff-only 29d9ca2..c2f1919 on main; pushed; origin/main parity 0 (rev-list count 0).

## Residual (reported, not hidden)

After the first successful exit the model path (jev/teacher) walks straight back into the house from the door mat: run_df17plan2 cycles 46-80 oscillate 1F<->Pallet Town (13 round trips). This is a model-policy flap, NOT the planner trap this row describes — every transition is now reachable and the guard never rewrites a legal plan. Candidate fix (refuse a model press that re-crosses the edge just taken when its destination is not an objective-ladder map) is a product policy change, left to a follow-up row.

## gitreins

- Task DF-AIPP-17-R2 (planner arm) created + started 16:54Z, completed 17:47:36Z (tier2 judge async; verdict lands in .gitreins/history/2026-10-28/).
- Prior arm guard fix: task DF-AIPP-17 complete, judges a893f872 (FAIL/INCOMPLETE -> fixed) and 50659f68 (AC2/AC3 PASS, AC1 open -> this commit closes it).
