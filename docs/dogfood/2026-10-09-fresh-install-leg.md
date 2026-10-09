# Dogfood Run 2026-10-09 — Fresh-Install Substitute Leg + Perf Re-check

## Promise
"An autonomous Pokémon player: cron_runner.py boots PyBoy from a checkpoint, reads state
from RAM, and asks an LLM (JEV) only for game decisions."

## What this run did
The two previous dogfood runs (09-26, 09-29) never proved the fresh-install leg because
las-bunker-03 was unreachable. This run attempted the leg again:

- las-bunker-03 (100.69.3.13): still offline — tailscale "offline, last seen 5d ago",
  ssh connect timeout, ping 100% loss. Same wall as DOGFOOD-INSTALL-001 / GAP-051.
- Substitute: ephemeral agent **994226a6 on bunker-las-02** (bunkerd active).
  One spawn attempt failed at stage `slice-limits` ("containment landing did not
  converge within 5 reads: memory.swap.max = max, want 0"); the retry succeeded —
  first-failure observed once, worth knowing if you spawn on las-02.

## Install results (bare Debian agent, no toolchains, non-root)
| Step | Result |
|---|---|
| git clone github.com/wojons/ai_plays_poke (fresh agent) | OK, HEAD b998880, ~13s |
| `python3 -m venv .venv && pip install -r requirements.txt` | **INSTALL_SECONDS=43**, zero apt prereqs needed |
| `cron_runner.py --dry-run` | exits 1 with the intended honest failure (ROM missing, actionable fix message) — dry-run contract works on a clean machine |
| `pip install pyboy` (2.8.1) + `PyBoy("missing.gb")` | import + constructor both reach the ROM check → **emulator layer boots with NO system prereqs** (pysdl2-dll wheel covers SDL2) |

Conclusion: the "bare Debian may need undocumented apt packages" clause of GAP-051 is
answered — it does not. Filed as **GAP-058**. Still unproven: the full RUN leg on the
bunker (needs a legal ROM + a real API key — out of scope for the lane). The agent was
destroyed after the run.

## Perf (local, real run)
`time python3 cron_runner.py --run-id dogfood1009 --cycles 5 --boot-state data/boot.state`
- cold: **8.09s** (user 1.63s / sys 0.18s), warm: **8.31s** — ~1.6-1.7 s/cycle including
  3 JEV escalations. Dry-run: 0.73s. Comfortably fast; **no PERF row filed** — a win
  nobody can feel is not a finding (consistent with the 09-29 run's conclusion).

## Real-use observations (run output)
- autonomy 3/5 (3 JEV escalations), 4 distinct tiles this run (last run: 3) — the
  DF-USE-1 treadmill remains open but marginally better.
- Recurring line on every run: `[MEM] save items skipped: no public item reader` —
  the save-item memory feature silently no-ops with an opaque jargon message. Minor
  UX friction, not filed separately (covered by the autonomy/objective rows already
  on the board).

## Artifacts
- Board row GAP-058 (commit bf76274)
- dogfood-log.md entry appended
- No code changes; agent destroyed; nothing left on the bunker
