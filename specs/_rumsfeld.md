# Rumsfeld matrix — with mandatory sinks

## Known knowns (verified → `_facts.md`)
- Two perception channels must agree cell-for-cell; today their grid definitions disagree (FACT-05/06/07)
- Bridge: loopback, token, 13 ops (FACT-01/02)
- Decision core: JEV every cycle, LLM on escalation; thresholds 0.50/0.40 (FACT-09)
- Vision: ×6 LANCZOS cap 1024; prompt wording moves agreement 32 points (FACT-11/13)
- People identification measured unreliable, anchoring on one answer (FACT-14)
- Console: 13 panels, self-refreshing, token-less on a tailnet (FACT-15/25)

## Known unknowns (→ open-question register)
- Q-01: does `long_run.py`'s silent `'jev'` fallback ever run in practice, or is the mode always set by the lane? Probe: grep cron.sh / scheduler prompts for AIPP_DECISION_MODE. Blocking: yes for ARM-2 acceptance.
- Q-02: does the foreman decline P3/P4 rows by prompt rule or by model judgement? Probe: read one dry-tick transcript. Blocking: no.
- Q-03: what is the people-identification failure rate on a larger frame set (3 frames is not a rate)? Probe: extend probe to 10 saves. Blocking: no, but blocks trusting vision people output.

## Unknown unknowns (→ measurement task or design decision + falsifier)
- U-01 *(assumption inversion)*: "RAM is ground truth for position" — if the RAM reader's screen origin is wrong by one row, every verdict row is wrong. Falsifier: compare the arrow cell against two known save positions. → DESIGN: single shared grid module; one writer (VISION-GRID-UNIFY, filed).
- U-02 *(scale extremes)*: 100× decision rate (hybrid mode every frame) — does the bridge serialisation hold? Falsifier: soak test with 60 decisions/min for 10 min.
- U-03 *(day-one state)*: fresh clone, no cache, no vision reading — the console shows "(nothing yet)" but auto-vision's first trigger needs a state change. What does a day-one operator see? → measurement task.
- U-04 *(unexpressible failure)*: when the vision call fails, does the verdict record "vision unavailable" or silently compare against a stale reading? → measurement; changes the verdict schema if silent.

## Unknown knowns (operator constraints → explicit normative statement)
- N-01: the operator plays the console with his own hands; the agent must not drive the bridge during an operator session (FACT-26). Normative: agent runs require the operator to yield, or live mode off.
- N-02: thresholds 0.50/0.40 must not change silently (operator ruling).
- N-03: no story content in prompts — prompts describe HOW the game works, never the story (operator ruling).
