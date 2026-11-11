# Modules

### MOD-01 — Emulator bridge
flow: FLOW-01
owns: the ONLY write path to emulator state; op dispatch (13 ops, FACT-02)
does-not-own: which buttons to press; what the state means
inputs: token-authenticated commands (loopback 8770)
outputs: frames, observations, save slots
failure modes: unauthenticated caller → refuse; serial contention → queue (bound concurrency 640476c); video degradation after long stepping → restart (FACT-17)
invariants: loopback only; token on every request (FACT-01)
observability: health op; batch time last_ms

### MOD-02 — RAM reader (System One's eyes)
flow: FLOW-01
owns: tile grid render (10×9, FACT-03), collision, party, sprite state (0xC100, FACT-04)
does-not-own: what a sprite MEANS (person vs object); the vision grid definition (should own it — see VISION-GRID-UNIFY)
failure modes: wrong screen origin → every cell wrong (U-01, measured FACT-07)
observability: grid in /api/state every cycle

### MOD-03 — Vision channel
flow: FLOW-01
owns: frame upscale (×6 LANCZOS cap 1024, FACT-11), model selection (FACT-12), grid parse, people probe
does-not-own: the RAM grid; the decision
failure modes: model hallucination → invented scenes (FACT-13/14); prompt hedging → 41% unknown (FACT-13); anchoring on one answer (FACT-14)
invariants: answer with the measured prompt (terse); never overlay grid on pixels
observability: tokens in/out, finish reason, age (PERCEPT-1)

### MOD-04 — Decision core (JEV + LLM)
flow: FLOW-01
owns: decision_mode resolution (FACT-08), thresholds (0.50/0.40, FACT-09), escalation to state repair
does-not-own: perception; the emulator
failure modes: hardcoded default arm (FACT-10) → agent loops in Pallet Town; teacher never called at scale → escalation path unexercised
invariants: mode explicit; M6 byte-compat; thresholds operator-fixed
observability: episode log rows (decisions, escalations, teacher calls)

### MOD-05 — Operator console
flow: FLOW-02
owns: 13 panels, controls with ids (FACT-24), SSE refresh (FACT-25), strict-bool toggles (FACT-16)
does-not-own: emulator truth; the board
failure modes: panel blank on error → fixed (500 body); bridge starvation → cache + rate cuts
invariants: nothing hidden; panels self-refresh (INV-6)

### MOD-06 — Fleet build-and-verify
flow: FLOW-03
owns: board rows, foreman ticks, QA batteries (bunker), releng cuts, DuckBrain narration
does-not-own: game logic
failure modes: admission waiver on unworkable rows → idle spin (SCHED-GAP-NODRAIN); judge 402; disk admission
observability: scheduler.db ticks; Prometheus metrics
