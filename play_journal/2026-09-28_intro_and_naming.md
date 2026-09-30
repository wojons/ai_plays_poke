# AI Plays Pokémon — Session Journal

**Session:** live bridge session (`scripts/game_bridge.py`, port 8770, loopback + token)
**Date:** 2026-09-28
**ROM:** `data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb`
**Mode:** cold boot (`--boot-state skip`), human-in-the-loop (operator watching frames)
**Frames:** `play_frames/` (144 png) · **Save-states:** `play_states/`

Every line below carries the frame filename it was read from. Nothing here is from memory:
a claim without a frame reference is not a fact yet.

---

## 1. Goal

**Immediate:** leave the bedroom (`Red's House 2F`) — the first frame where the game
asks "what do you do?" instead of "press A".
**Session goal:** play the game *with understanding*, demonstrating that the agent can be
taught the world by observation.
**Project goal (standing):** complete Pokémon Blue autonomously, with no assistance beyond
its own tools — and the human learns the method well enough to write the prompts and
rebuild the harness.

---

## 2. Checklist — completed (proven, with frames)

- [x] Cold boot to title — `--boot-state skip`; `SCREEN: title`, `PARTY: 0`
- [x] Identify the cartridge — **"Pokémon" / "Blue Version"**, Blastoise-vs-Red art,
      `©'95.'96.'98 GAME FREAK inc.` (title frame)
- [x] Bypass title → menu. **30-frame START hold works; 5 frames does nothing**
      (`emulator.bypass_title()` = `press_button("start", frames=30)` + `wait(90)`)
- [x] SRAM trap found — a bare boot silently inherits `data/rom/*.gb.ram` (32,768 B),
      which is why a "blank" run reported `PARTY: 1 (Charmander)`. `dist1_episodes.py:47`
      snapshots/restores it per episode.
- [x] `NEW GAME` selected (DOWN → A) — **it wipes the SRAM**: `PARTY: 1 (Charmander)` →
      `PARTY: 0 (None)`; map → Red's House 2F (id 38)
- [x] Oak's opening speech paged through (transcript in §4)
- [x] **Player name entered = `HERMES`** — grid navigation + 6 `A` presses + `ED`
- [x] **Rival name entered = `CLAWED`** — same mechanism; 3 stray `A`s typed `AAA`,
      fixed with `B` ×3
- [x] Intro completed → **overworld, first playable frame** (`NOW_START.png`)
- [x] Milestone checkpoint saved — `play_states/aipp_name_hermes_20260928.state` (167,677 B)

## 3. Checklist — pending

- [ ] Leave the bedroom (find the stairs / the exit gap in the floor)
- [ ] Interact with room objects (TV, bed, plant) — read what the game says about each
- [ ] Leave the house (1F → outside)
- [ ] Reach Oak's Lab (the canonical measured boot `base-1_boot.state` is Pallet Town)
- [ ] Get the starter Pokémon
- [ ] First rival battle
- [ ] First wild encounter — battle loop
- [ ] Route 1 → Viridian City (the previous run's ceiling: HOLD at ep028)

---

## 4. Intro dialogue — transcript read off the pixels, in order

| # | page text (verbatim) | frame |
|---|---|---|
| 1 | `Welcome to the` / `world of POKéMON!` + `▼` | ANIM series |
| 2 | `My name is OAK!` / `People ca…` | `P8_now_4x.png` |
| 3 | `This world is` / `inhabited by` | `P9_now_4x.png` |
| 4 | `creatures   called` / `POKéMON!` | `P10_now_4x.png` |
| 5 | `For some people,` / `POKéMON are` | `P11_now_4x.png` |
| 6 | `POKéMON are` / `pets. Others use` | `P12_now_4x.png` |
| 7 | `Myself...` + `▼` | `P13_now_4x.png` |
| 8 | `First, what is` / `your name?` | `NAME_SCREEN_4x.png` |
| — | **NAME menu** `►NEW NAME / BLUE / GARY / JOHN` (cursor on NEW NAME) | `NAME2_4x.png` |
| — | **name grid** `YOUR NAME?` (5×9) — typed `HERMES`, `ED` | `GRID1_4x.png`, `T2_field_6x.png` |
| 9 | `Right! So your` / `name is HERMES!` + `▼` | `SUBMIT1_4x.png` |
| 10 | `This is my grand-` / `son. He's been` | `NEXT2_4x.png` |
| 11 | `son. He's been` / `your rival since` | `DIAG_after_A_4x.png` |
| — | **RIVAL menu** (sig 13.6% dark) then **grid** `RIVAL's NAME?` | `CARE_4.png` |
| — | typed `CLAWED`, `ED` (after clearing stray `AAA` with `B`) | `RIVAL_typed_field_6x.png` |
| 12 | `That's right! I` / `remember now! His▼` | `RIVAL_submitted_4x.png` |
| 13 | `remember now! His` / `name is CLAWED!` | `PG_1_4x.png` |
| 14 | `HERMES!` + `▼` (sprite changes to the **capped** player) | `PG_2_4x.png` |
| 15 | `Your very own` / `POKéMON legend is▼` | `PG_3_4x.png` |
| 16 | `POKéMON legend is` / `about to unfold!` | `PG_4_4x.png` |
| 17 | `A world of dreams` / `and adventures` + `▼` | `PG_5_4x.png` |
| 18 | `and adventures` / `with POKéMON` + `▼` | `PG_6_4x.png` |
| 19 | `with POKéMON` / `awaits! Let's go!` | `PG_7_4x.png` |
| 20 | *(blank — fade, 0.0% dark)* | `PG_8.png` |
| 21 | **OVERWORLD** — bedroom, no text box | `NOW_START_4x.png` |

Caveat on the table: rows 5/6 and 10/11 are the *same page* read at two points; the text
animates in, so an early read is clipped. Rows read mid-animation are marked by the clipped
word. Only settled frames were treated as final.

---

## 5. Facts from the game world itself (things the game told us)

| fact | evidence |
|---|---|
| Cartridge = Pokémon **Blue Version** | title frame text |
| Player's name is **HERMES** | game's own sentence: `Right! So your name is HERMES!` |
| Rival's name is **CLAWED** | game's own sentence: `His name is CLAWED!` |
| Oak introduces himself by name — `My name is OAK!` | `P8_now_4x.png` **(no assuming: he said it)** |
| The world is inhabited by creatures called `POKéMON` | `P10_now_4x.png` |
| The rival is Oak's grandson | `This is my grand-son.` — `NEXT2_4x.png` |
| Rival has been the player's rival "since…" | `your rival since` — `DIAG_after_A_4x.png` |
| Zone name: `Red's House 2F` (id 38), tileset 4, 4×4 | reader `map_name` |
| Player position at first playable frame: tile `(3,6)`, facing `up` | reader `player_*` |
| Room contains: a TV/console (top, left of centre), a bed (left wall), a potted plant (right, below centre) | `NOW_START_4x.png` |
| No NPC, no item ball, no door visible in the first frame | `NOW_START_4x.png` |

---

## 6. How the controls actually behave (measured, not assumed)

| control | measured behaviour | evidence |
|---|---|---|
| `LEFT`/`RIGHT` on the name grid | move horizontally and **wrap around inside the row** (9 presses from `A` returns byte-identical to `A`) | `MV_0` vs `MV_9` md5 `954119d991` identical |
| `UP`/`DOWN` on the name grid | move vertically, **column preserved** | `A` (r1c1) → DOWN×2 → `S` (r3c1) — `DOWN_2_4x.png` |
| `A` on the grid | **types** the highlighted character into the field | `H` landed: `T1_H_field_6x.png` |
| `A` on `ED` | **submits** the name | screen flipped `name_entry` → `dialog`; game echoed the name |
| `B` on the grid | **backspaces** | field `AAA` → `AA` (`RIVAL_B1_field_6x.png`) |
| `START` on the title | needs a **30-frame hold**; 5 frames does nothing | `emulator.bypass_title()`; measured byte-identical frame at 5 |
| `START` during intro dialogue | **nothing** | `DIAG_after_START.png` byte-identical to before |
| `A` during dialogue | advances a page | pages 1→21 walked with `A` |
| left `I` → `J`? | **no** — it wraps to the same row's first cell | md5 identity above |
| name grid geometry | 5 rows × 9 cols; row3 = `S T U V W X Y Z` (8 letters) | `RIVAL_cleared_4x.png` |
| name field capacity | 7 slots | underscore count on the empty grid |

---

## 7. Reader defects measured this session (the agent's own view)

All measured on the live frame, same instant as the pixels.

| # | defect | frame | pixel truth |
|---|---|---|---|
| 1 | main `NAME` menu → `result=dialog`, `menu_items=[]` | `NAME2_4x.png` | a 4-option menu: NEW NAME / BLUE / GARY / JOHN |
| 2 | `keyboard_grid` **truncated to 2 of 5 rows** (`A–I`, `J–R`) | `GRID1_4x.png` | 5 rows incl. `S–Z`, symbols, and **`ED`** |
| 3 | `name_field` = constant `\xd5\xd6…\xdf` (not a live field) | every grid frame | empty field; then `HERMES`; then `AAA` |
| 4 | `text_content` = the **same constant** during the speech | `P8`–`P13` | different text on every page |
| 5 | **no player-name or rival-name field exists at all** | — | the game typed and echoed two names |
| 6 | the game's own confirmations (`HERMES!`, `name is CLAWED!`) appear nowhere | `PG_1`, `PG_2` | plainly on screen |
| 7 | cursor move → `state_changed: False` | earlier menu test | visible `▼` cursor moved |

**Consequence:** the decision path is RAM-only. On the three screens where the game asks a
question (menu, cursor, name entry), the agent is shown a wrong or empty picture. Defect #2
specifically means an agent driving from RAM **cannot reach `ED`** — it cannot complete a
name entry at all.

---

## 8. Open questions (do not guess these)

1. Does `A` during dialogue *skip the typing animation* and *also* advance the page, or does
   the first press only finish the animation? *(The 12-press no-op stretch on
   `NEXT2`/`NEXT3` suggests animation-finishing presses don't advance.)*
2. Exact page count of Oak's speech (did any page get skipped by double-advance?).
3. Where the bedroom exit is — stairs, doorway, or a gap (not visible in frame 1).
4. Whether `SELECT` does anything on the name grid (untested) — `lower case` suggests a case
   toggle that is probably not `SELECT`, but I have not tested it either way.
5. Does the grid's row 3 truly have 9 cells (8 letters + a blank), or 8?

---

## 9. Next actions (one at a time, image before and after each)

1. Walk down/around the bedroom to find the exit — send frame before and after each move.
2. On finding a text prompt or object, read it with the frame-stability rule before concluding.
3. Record each step here with its frame, then push the ledger to DuckBrain (`pokemon-global`).
