# Dogfood Integration Report — 2026-09-29 (ai-plays-poke-dogfood lane)

## Promise tested
"A user can run autonomous Pokémon gameplay with `cron_runner.py` — RAM reader supplies state instantly and free, LLM is spent only on decisions, JEV escalates to the teacher when state is insufficient."

## Real use (control host, repo venv)
- `./.venv/bin/python cron_runner.py --dry-run` — 0.88s, exit 0, validates ROM + boot state + keys.
- `./.venv/bin/python cron_runner.py --run-id df0929 --cycles 5` — **9s wall**, 16 actions, autonomy 5/5 real decisions / 0 fallback, 1 JEV escalation (insufficient_state 0.35) that produced a teacher patch applied in-game (`map_topology_resolved_by_rom`).

## Performance
Headline operation (5-cycle run): warm 9s (~1.8s/cycle). Cycle 1 6.6s (one 6.1s LLM call), cycles 2–5 ~0.3s each (cache-hot). Cold-start behavior was already covered by PERF-1..5; nothing here is slow enough to justify a new profile. No perf row filed.

## Install leg (fresh machine, bunker-las-03, agent 814077be, destroyed after)
- `git clone https://github.com/wojons/ai_plays_poke.git` — 13s, HEAD d5a4a6d.
- `python3 -m venv .venv && pip install -r requirements.txt` — 53s, zero system deps on Debian/Python 3.13.
- Documented smoke check (`cron_runner.py --dry-run`) — **exit 1, by design**: ROM not in repo (good error message pointing to the user's own dump), keys not set. Install path itself works; first-run prerequisites are only discoverable via the dry-run error → DF-USE-2.

## What works vs 2026-09-26 run
- DF-JEV-1 (JEV not wired) — fixed in real use: escalation fired, patch consumed.
- DF-JEV-2 (teacher burns token budget) — teacher call succeeded this run.

## New findings filed (board, no dupes, 190→193 rows)
- DF-USE-1 (P1): autonomy 5/5 but distinct_tiles=3 — the instrument counts decisions, not progress (treadmill masking).
- DF-USE-2 (P2): README quickstart omits ROM + API-key prerequisites.
- DF-USE-3 (P3): frame-cache save prints counts, never size/eviction policy.
