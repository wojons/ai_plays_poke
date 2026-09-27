# Verdict: CTRL-WIN

**Task:** Measure the controller path head-to-head vs the locked S0 jev baseline
**Evaluated:** 2026-09-27T14:29:23.013242
**Result:** ✗ FAIL

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✗ **tier2**
  - INCOMPLETE
  ✗ A CTRL-WIN artifact exists under data/baselines/ recording decision-mode llm runs from the same S0 boot state (same cycles/episode count as BASE-1) with escalations-per-map-transition compared against the BASE-1 jev numbers; the comparison is written to the board row. Falsifier: no llm-mode artifact or no comparison against BASE-1.: Artifact half is satisfied: data/baselines/ctrlwin_llm_2026-09-27.json exists with conditions.decision_mode='llm', boot_state_sha256='a74ca90bf1b2616f4e97cf17b8b76554bec10f54bd7ad5808660f596a8bf0962' (identical to BASE-1 control data/baselines/base1_control_2026-09-27.json), cycles_per_episode=5 and episodes=5 (identical to BASE-1), and a ctrl_win_comparison block comparing against BASE-1 jev numbers (baseline: 7 escalations/25 decisions/0 map_transitions; ctrlwin: 0 escalations/12 llm decisions/0 transitions; escalations_per_map_transition=null in both arms). BUT the required 'comparison is written to the board row' is unmet: .coding-hermes/board/tasks.jsonl:133 still shows the CTRL-WIN row as "status": "pending" with no comparison field — grep for 'escalations_per_map_transition' or 'ctrl_win_comparison' in tasks.jsonl returns zero hits, and events.jsonl has no CTRL-WIN completion event (only notes at lines 293-294). The comparison lives only inside the artifact JSON, never in the board row, so the criterion's explicit board-row requirement fails.
The llm-mode artifact and BASE-1 comparison exist in data/baselines/ctrlwin_llm_2026-09-27.json, but the comparison was never written to the board row (tasks.jsonl CTRL-WIN still 'pending', no comparison field), so the criterion is not fully met.

## Summary

Judge Result: CTRL-WIN

Stage tier1: PASS
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: FAIL
  INCOMPLETE
  ✗ A CTRL-WIN artifact exists under data/baselines/ recording decision-mode llm runs from the same S0 boot state (same cycles/episode count as BASE-1) with escalations-per-map-transition compared against the BASE-1 jev numbers; the comparison is written to the board row. Falsifier: no llm-mode artifact or no comparison against BASE-1.: Artifact half is satisfied: data/baselines/ctrlwin_llm_2026-09-27.json exists with conditions.decision_mode='llm', boot_state_sha256='a74ca90bf1b2616f4e97cf17b8b76554bec10f54bd7ad5808660f596a8bf0962' (identical to BASE-1 control data/baselines/base1_control_2026-09-27.json), cycles_per_episode=5 and episodes=5 (identical to BASE-1), and a ctrl_win_comparison block comparing against BASE-1 jev numbers (baseline: 7 escalations/25 decisions/0 map_transitions; ctrlwin: 0 escalations/12 llm decisions/0 transitions; escalations_per_map_transition=null in both arms). BUT the required 'comparison is written to the board row' is unmet: .coding-hermes/board/tasks.jsonl:133 still shows the CTRL-WIN row as "status": "pending" with no comparison field — grep for 'escalations_per_map_transition' or 'ctrl_win_comparison' in tasks.jsonl returns zero hits, and events.jsonl has no CTRL-WIN completion event (only notes at lines 293-294). The comparison lives only inside the artifact JSON, never in the board row, so the criterion's explicit board-row requirement fails.
The llm-mode artifact and BASE-1 comparison exist in data/baselines/ctrlwin_llm_2026-09-27.json, but the comparison was never written to the board row (tasks.jsonl CTRL-WIN still 'pending', no comparison field), so the criterion is not fully met.

Overall: FAIL ✗
