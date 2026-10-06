README.md imports audit (README-9 closure evidence, tick 2026-10-06-20-23-23):

Live imports of cron_runner.py, verified against the module graph this tick:

  $ grep -n "^from src" cron_runner.py
  706:from src.core import jev_client
  707:from src.core import state_projection
  708:from src.core.prompt_loader import load_system_prompt
  709:from src.core.tools import execute_tool_call

The README Architecture Overview (README.md#architecture-overview) is written against
exactly this set: boot -> RAM state projection (state_projection / StateWindow) ->
jev decision (jev_client, system1/system2 hybrid) -> execute_tool_call -> JSONL
decision rows + DuckBrain. GOAP, tri-tier memory and the vision/OCR pipeline appear
in NO import of the live entrypoint and are labeled SPEC-DRIVEN / design-only.

ch:trace row=README-9 spec=README.md#architecture-overview witness=path@origin:cron_runner.py:706-709 commit=4f3d260
