"""One-shot RED evidence: the pre-BENCH-1 parser undercounts the llm arm.

Run against the committed ctrlwin fixture shape: run_base1_baseline counts
decisions only from rows carrying a non-null missing_class, so a pure-LLM log
(controller decisions, no escalations) reads as decisions=0 beside autonomy
decisions_total=3 — exactly the hole in data/baselines/ctrlwin_llm_2026-09-27
.json (decisions: 0, llm_decisions_total: 12). BENCH-1's parser closes it.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import run_base1_baseline  # noqa: E402
import benchmark_llm_vs_jev as bench  # noqa: E402

rows = [
    {
        "cycle": 1,
        "plan": ["UP"],
        "intent": "walk",
        "jev_answered": False,
        "escalated": False,
        "missing_class": None,
        "map_name": "Pallet Town",
    },
    {
        "cycle": 2,
        "plan": ["UP"],
        "intent": "walk",
        "jev_answered": False,
        "escalated": False,
        "missing_class": None,
        "map_name": "Pallet Town",
    },
    {
        "cycle": 3,
        "plan": ["LEFT"],
        "intent": "walk",
        "jev_answered": False,
        "escalated": False,
        "missing_class": None,
        "map_name": "Route 1",
    },
    {
        "event": "run_autonomy",
        "decisions_total": 3,
        "jev_answered": 0,
        "escalated": 0,
        "autonomy_ratio": 0.0,
        "decision_mode": "llm",
        "teacher_escalations": {"count": 0, "improved": 0},
    },
]

with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "run_llm.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    old = run_base1_baseline.episode_metrics_from_log(p)
    new = bench.episode_metrics_from_log(p)
    print(
        f"BASE-1 (pre-BENCH-1) parser: decisions={old['decisions']}  "
        f"(autonomy decisions_total={old['autonomy']['decisions_total']})"
    )
    print(
        f"BENCH-1 parser:              decisions={new['decisions']}  "
        f"real={new['real_decisions']} transitions={len(new['map_transitions'])}"
    )
    assert old["decisions"] == 0, "expected the OLD parser to undercount llm logs"
    assert new["decisions"] == 3, "the BENCH-1 parser must count controller rows"
    print(
        "EVIDENCE OK: undercount reproduced against the old parser, "
        "closed by the new one"
    )
