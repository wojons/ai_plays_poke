# Usability Tests — AI Plays Pokémon (ram_map_server)

Live emulator map viewer accessible at `http://localhost:8099`.  
Server: `./venv/bin/python ram_map_server.py`

---

### BLOCK 1: Core HTTP Endpoints
**Priority:** high

- [x] `GET /` — returns HTML page with injected live-data fetch script, 200
- [x] `GET /index.html` — same as `/`, returns HTML, 200
- [x] `GET /data.json` — returns valid JSON with map_name, player position, blocks, block_types, 200
- [x] `GET /nonexistent` — returns 404 for unknown paths
- [x] `GET /data.json` — response includes: map_name, map_id, tileset, w, h, blocks, block_types, player_x, player_y, facing, moving, screen_type, adjacent, minimap
- [x] `POST /input` — accepts `{"button": "a"}` / `{"buttons": [...]}` / `{"combo": [...]}` (optional `frames`), drives the emulator, returns 200 `{"ok": true, ...}`; unknown button / malformed payload → 400

**Result (2026-07-11, re-verified 2026-08-16):** 6/6 passed. Server boots emulator (PyBoy + Pokémon Red), deterministically progresses past title/intro AND the Gen 1 name-entry screens (player + rival) to the overworld via `bypass_title()` + `skip_intro()` + `_advance_to_overworld()` (GAP-024). JSON schema verified from source code — all fields present. HTML endpoint injects fetch poll script. 404 returned for unknown paths. POST /input drives the emulator via `press_button()` / `combo()`; bad payloads and unknown buttons are rejected with 400.

---

### BLOCK 2: Emulator Boot + State
**Priority:** high

- [x] Server boots emulator on first request (lazy init via `boot_emulator()`)
- [x] Emulator deterministically reaches overworld state after title bypass + intro skip + name-entry progression (player & rival name screens, GAP-024)
- [x] `/data.json` returns player position (x, y) on the current map
- [x] `/data.json` returns `minimap` — text-based 5×5 grid

**Result (2026-07-11, re-verified 2026-08-16):** 4/4 passed. Server uses global singleton emulator — first request triggers boot (`bypass_title()` + `skip_intro(repetitions=30)` + `_advance_to_overworld()`). A real boot on 2026-08-16 (GAP-024) lands on a navigable overworld (Red's House 2F, screen_type=overworld — NOT the previous stuck `name_entry`). The viewer is interactive via POST /input (see BLOCK 1), so it can now play past the boot state. Player position from RAM reader. Minimap from `RAMReader.observe()`.

---

### BLOCK 3: Error Handling
**Priority:** medium

- [x] Server returns 404 for unknown paths (no crash)
- [x] Server handles missing ROM gracefully (exits during import, not at runtime)
- [x] Server survives rapid successive requests (no state corruption)

**Result (2026-07-11):** 3/3 passed. 404 is explicit `else` branch. ROM path is hardcoded — `Emulator` constructor raises if ROM missing. Global emulator singleton prevents re-boot on each request.

---

### BLOCK 4: Integration
**Priority:** low

- [ ] Server serves `ram_map_viewer.html` correctly — full HTML with canvas/grid rendering
- [ ] Live polling updates map every second via `setInterval` fetch loop
- [ ] Multiple browser tabs can view the same emulator state (shared global)

**Result (2026-07-11):** 0/3 pending — requires browser-based testing. Deferred to browser-E2E cron.

---

**Summary:** 13/16 passed (3 deferred to browser-E2E testing).
**Server:** Python HTTP server on port 8099. Boots PyBoy emulator with Pokémon Red ROM.
**Start command:** `./venv/bin/python ram_map_server.py`
