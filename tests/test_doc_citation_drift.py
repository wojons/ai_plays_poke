"""DOC-028 — citation drift guard for docs ``file:line`` code citations.

Walks every ``file:line`` code citation in ``docs/observability-spec.md`` and
``docs/api/cron_runner.md`` and asserts each cited anchor still resolves
against the CURRENT tree: the cited line(s) still contain a symbol named on
the same doc line, or sit inside the span of a function the doc names
(function spans resolved with ``ast`` — sources are parsed, never imported,
so no numpy/cv2 dependency and no network).

Declaration lines honored (docs/observability-spec.md) — located by text, not
by number, so the guard survives doc edits above them:

- Line 3: ``audit history retained`` — the page's status banner.
- Line 13: ``Citations inside the 2026-11-03 body (§0–§3) are audit history
  measured on that day's tree; the dated UPDATE blocks are the ones that
  resolve against the current tree.`` → the §0–§3 body is skipped EXCEPT
  contiguous ``>``-blockquote UPDATE blocks (first line matches
  ``**UPDATE YYYY-MM-DD``), which are checked.
- Line 92: ``The text below is kept verbatim so the audit history stays
  checkable`` — confirms the §0 body skip.
- Lines 15–24: the DOC-027 re-derivation paragraph self-declares its offset
  arithmetic ``**superseded**`` (``+45 lines at :122, +3 at :48, ...`` are
  quoted historical residue, not live citations) → skipped verbatim.
- ``docs/api/cron_runner.md`` declares no history body → walked in full.

Symbol semantics (per the board row): a citation passes when ANY code symbol
named on the same doc line (backticked span identifier of ≥4 chars) appears
in the cited window, or the window overlaps the span of a function named on
the line. A doc line naming no symbol fails closed. Bare ``:N`` continuation
refs bind to the nearest code-file mention on the same line, else the most
recent resolved mention earlier in the doc (linear carry, matching the docs'
own "file carried from the previous mention" convention); a bind whose
anchor overflows the bound file's length falls back to the linear carry.

KNOWN DRIFT BASELINE (read this before "fixing" the guard): the DOC-027
re-derivation was cut against ``f3d7774`` (2026-11-17). Later commits
(``bcc61b68``, ``0f9d6477``, ``73c8faaa``) moved ``cron_runner.py`` and
``src/dashboard/main.py``, so a set of pre-existing anchors already drifts
TODAY (measured 2026-11-22). Editing the docs is outside this guard's
test-only scope, so ``KNOWN_DRIFT`` records each such citation with evidence
instead of hiding it. The ratchet bites in BOTH directions: any citation
that drifts and is NOT in ``KNOWN_DRIFT`` fails the suite, and any
``KNOWN_DRIFT`` entry whose citation resolves again (i.e. the docs were
refreshed) fails the suite until the entry is removed. Goal state:
``KNOWN_DRIFT`` shrinks to empty.

Negative proof: point ``PTP_DOCS_ROOT`` at a scratch docs tree whose product
checkout has a cited anchor moved — the guard must fail (see
``test_guard_bites_when_cited_anchor_moves`` for the in-CI version).
Runtime budget: < 5 s, stdlib only.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = Path(os.environ.get("PTP_DOCS_ROOT", str(REPO_ROOT / "docs")))
PRODUCT_ROOT = DOCS_ROOT.parent  # the spec itself: "docs/'s parent"

# Docs walked by this guard.
DOCS = ("observability-spec.md", "api/cron_runner.md")

# The file a bare ":N" continuation ref binds to when every linear candidate
# (same-line mention, then the most recent earlier mention) overflows. This is
# DECLARED per doc, not inferred: both pages state their own subject —
# observability-spec.md §4.3 heads its bare-ref table with
# "Path and flag (`cron_runner.py`)" and its re-derivation note names
# cron_runner.py first; api/cron_runner.md documents cron_runner.py itself.
SUBJECT_FILE = {
    "observability-spec.md": "cron_runner.py",
    "api/cron_runner.md": "cron_runner.py",
}

# Commits that moved cited files AFTER the DOC-027 re-derivation (f3d7774).
POST_REDERIVATION_MOVERS = {
    "cron_runner.py": ("bcc61b68", "0f9d6477"),
    "src/dashboard/main.py": ("73c8faaa",),
    "tests/test_dashboard.py": ("73c8faaa",),
}

# Source files the checked citations point at — copied into the sabotage
# scratch tree by the bite test so the scratch audit mirrors the real one.
CITED_SOURCES = (
    "cron_runner.py",
    "src/dashboard/main.py",
    "src/observability/metrics.py",
    "scripts/game_bridge.py",
    "src/core/ai_client.py",
    "src/core/logger.py",
    "web_viewer.py",
    "tests/test_dashboard.py",
    "requirements.txt",
    "pyproject.toml",
)

_PRUNE_DIRS = {
    ".venv",
    "venv",
    ".git",
    "node_modules",
    ".vfs",
    "cron_logs",
    "__pycache__",
    ".pytest_cache",
    "game_saves",
}

# A code-file mention, with or without a line anchor.
_MENTION_RE = re.compile(r"(?:[\w.-]+/)*[\w.-]+\.(?:py|toml|txt)")
# A mention WITH a line anchor (explicit file:line citation).
_CITATION_RE = re.compile(
    r"(?P<ref>(?:[\w.-]+/)*[\w.-]+\.(?:py|toml|txt)):(?P<start>\d+)"
    r"(?:-(?P<end>\d+))?"
)
# A bare continuation ref ":N" / ":N-M" (file carried from a nearby mention).
# Not preceded by a word char, '.', '-' or ':'; '/' IS allowed (the docs
# write ":593/:607"), and URLs stay excluded because their ':' follows a
# word char ("127.0.0.1:8000").
_BARE_REF_RE = re.compile(r"(?<![A-Za-z0-9_.:\->]):(?P<start>\d+)(?:-(?P<end>\d+))?")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`", re.S)  # spans may cross a newline
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_UPDATE_BLOCK_RE = re.compile(r"\*\*UPDATE \d{4}-\d{2}-\d{2}")


def _d(doc_lines: list[int], hint: str, note: str = "") -> dict[str, object]:
    """Baseline entry: doc lines citing the drifted anchor, a re-derivation
    hint (old f3d7774 line content located in today's tree), and — only for
    intact-but-unverifiable anchors — a note."""
    entry: dict[str, object] = {"doc_lines": doc_lines, "hint": hint}
    if note:
        entry["note"] = note
    return entry


# Measured against the tree on 2026-11-22. Every entry below FAILS the audit
# today; hints were derived mechanically from f3d7774 content. Entries MUST be
# removed (not relaxed) the moment the docs refresh re-derives their anchors —
# the stale-entry check enforces that.
KNOWN_DRIFT: dict[tuple[str, str, int, int], dict[str, object]] = {
    ("api/cron_runner.md", "cron_runner.py", 7792, 7800): _d(
        [149],
        "f3d7774:7792 ('parser.add_argument(') now at :8289",
    ),  # moved by bcc61b68+0f9d6477
    ("api/cron_runner.md", "cron_runner.py", 8110, 8115): _d(
        [391],
        "f3d7774:8110 ('R.mode_models = resolve_mode_models(') now at :8624",
    ),  # moved by bcc61b68+0f9d6477
    ("api/cron_runner.md", "cron_runner.py", 9229, 9229): _d(
        [391],
        "f3d7774:9229 ('\"decision_model\": S.R.decision_model,') now at :9754",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "src/dashboard/main.py", 35, 35): _d(
        [176],
        "f3d7774:35 ('from prometheus_client import CONTENT_TYPE_LATEST, REGISTR') now at :36",
    ),  # moved by 73c8faaa
    ("observability-spec.md", "src/core/ai_client.py", 109, 118): _d(
        [995],
        "109-118",
        note="anchor INTACT (ai_client.py unchanged since f3d7774): :109-118 is the log_api_call signature; the doc's symbol `cost_usd` does not appear in the source at all (the parameter is `cost`) — spelling mismatch, not drift",
    ),
    ("observability-spec.md", "src/dashboard/main.py", 119, 119): _d(
        [54],
        "f3d7774:119 ('_observability_metrics.set_runner_up(\"dashboard\")') now at :126",
    ),  # moved by 73c8faaa
    ("observability-spec.md", "tests/test_dashboard.py", 122, 122): _d(
        [1001],
        "f3d7774:122 ('assert client.get(\"/metrics\").status_code == 401') now at :203,596",
    ),  # moved by 73c8faaa
    ("observability-spec.md", "src/dashboard/main.py", 228, 228): _d(
        [1006],
        "f3d7774:228 ('total_cost = 0.0') now at :303",
    ),  # moved by 73c8faaa
    ("observability-spec.md", "src/dashboard/main.py", 359, 369): _d(
        [40],
        "f3d7774:359 ('async def prometheus_metrics() -> Response:') now at :443",
    ),  # moved by 73c8faaa
    ("observability-spec.md", "src/dashboard/main.py", 370, 370): _d(
        [43],
        "f3d7774:370 ('@app.get(\"/metrics\")') now at :454",
    ),  # moved by 73c8faaa
    ("observability-spec.md", "src/dashboard/main.py", 370, 376): _d(
        [163],
        "f3d7774:370 ('@app.get(\"/metrics\")') now at :454",
    ),  # moved by 73c8faaa
    ("observability-spec.md", "tests/test_dashboard.py", 489, 492): _d(
        [458],
        "f3d7774:489 ('assert client.get(\"/metrics\").status_code in (401, 403)') now at :570",
    ),  # moved by 73c8faaa
    ("observability-spec.md", "scripts/game_bridge.py", 657, 657): _d(
        [77],
        "657",
        note='anchor INTACT (game_bridge.py unchanged since f3d7774): :657 is the accept-loop busy rejection (`observe_bridge_request("none", "busy")`), but the doc line names no backticked code symbol for it — unverifiable, verified manually 2026-11-22',
    ),
    ("observability-spec.md", "cron_runner.py", 2247, 2247): _d(
        [389],
        "f3d7774:2247 ('tile_y = int(spatial_desc.get(\"player_tile_y\", 99))') now at :2755",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 2267, 2267): _d(
        [389],
        "f3d7774:2267 ('def _cycle_frame_hash(screenshot: np.ndarray) -> str:') now at :2775",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5154, 5158): _d(
        [636],
        "f3d7774:5154 ('_TEXTFILE_COUNTER_PATTERN = re.compile(') now at :5671",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5157, 5158): _d(
        [706],
        "f3d7774:5157 ('_TEXTFILE_COUNTER_PATTERN = re.compile(') now at :5671",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5174, 5174): _d(
        [602],
        "f3d7774:5174 ('_TEXTFILE_PROGRESS_FAMILIES: dict[str, tuple[str, str]] = ') now at :5688",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5177, 5177): _d(
        [606],
        "f3d7774:5177 ('\"Map transitions observed across cron runs.\",') now at :5691",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5181, 5181): _d(
        [609],
        "f3d7774:5181 ('\"Decision rows that repeated or revisited an already-seen ') now at :5695",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5186, 5186): _d(
        [611],
        "f3d7774:5186 ('),') now at :292,306,454",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5190, 5190): _d(
        [615],
        "f3d7774:5190 ('),') now at :292,306,454",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5194, 5194): _d(
        [618],
        "f3d7774:5194 ('),') now at :292,306,454",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5217, 5217): _d(
        [633],
        "f3d7774:5217 ('if match is None:') now at :5731",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5250, 5250): _d(
        [530, 538],
        "f3d7774:5250 ('target_dir.mkdir(parents=True, exist_ok=True)') now at :5764",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5259, 5259): _d(
        [685],
        "f3d7774:5259 ('accumulated[outcome] += 1') now at :5773",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5260, 5260): _d(
        [586],
        "no content at f3d7774:5260 in cron_runner.py",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5262, 5265): _d(
        [587, 588, 589],
        "f3d7774:5262 ('\"# HELP aipp_run_completed_total Completed cron runs by ou') now at :5776",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5265, 5268): _d(
        [706],
        'f3d7774:5265 (\'for label in ("completed", "error", "gave_up"):\') now at :5779',
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5269, 5269): _d(
        [591],
        "f3d7774:5269 ('lines.extend(') now at :5783,5799",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5270, 5270): _d(
        [592],
        "f3d7774:5270 ('[') now at :1498,5784,5800",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5272, 5272): _d(
        [594],
        "f3d7774:5272 ('\"# TYPE aipp_run_last_run_duration_seconds gauge\",') now at :5786",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5273, 5273): _d(
        [595],
        "f3d7774:5273 ('f\"aipp_run_last_run_duration_seconds {float(duration_s):g}') now at :5787",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5275, 5275): _d(
        [597],
        "f3d7774:5275 ('\"# TYPE aipp_run_last_decisions_total gauge\",') now at :5789",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5276, 5277): _d(
        [598],
        "f3d7774:5276 ('f\"aipp_run_last_decisions_total {int(autonomy.get(\\'decisio') now at :5790",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5280, 5281): _d(
        [601],
        "f3d7774:5280 ('f\"{int(autonomy.get(\\'map_transitions_observed\\', 0))}\",') now at :5794",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5285, 5285): _d(
        [600],
        "f3d7774:5285 ('lines.extend(') now at :5783,5799",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5286, 5286): _d(
        [601],
        "f3d7774:5286 ('[') now at :1498,5784,5800",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5298, 5298): _d(
        [610],
        "f3d7774:5298 ('return float(value) if isinstance(value, (int, float)) els') now at :5812",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5299, 5299): _d(
        [617],
        "no content at f3d7774:5299 in cron_runner.py",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5302, 5302): _d(
        [613],
        "f3d7774:5302 ('outcome_label = run_outcome_label(outcome)') now at :5816",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5305, 5305): _d(
        [604],
        "f3d7774:5305 ('improved = min(max(0.0, _num(teacher_block.get(\"improved\")') now at :5819",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5307, 5307): _d(
        [607, 708],
        "f3d7774:5307 ('\"aipp_map_transitions_total\": {') now at :5821",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5309, 5309): _d(
        [610],
        "f3d7774:5309 ('},') now at :1864,1886,2524",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5310, 5310): _d(
        [708],
        'f3d7774:5310 (\'"aipp_backtrack_events_total": {(): _num(autonomy.get("bac\') now at :5824',
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5312, 5312): _d(
        [613],
        'f3d7774:5312 (\'(("mode", mode_label),): _num(autonomy.get("decisions_tota\') now at :5826',
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5313, 5313): _d(
        [614],
        "f3d7774:5313 ('},') now at :1864,1886,2524",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5315, 5315): _d(
        [617],
        'f3d7774:5315 (\'(("improved", "true"),): improved,\') now at :5829',
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5315, 5316): _d(
        [707],
        'f3d7774:5315 (\'(("improved", "true"),): improved,\') now at :5829',
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5317, 5317): _d(
        [620],
        "f3d7774:5317 ('},') now at :1864,1886,2524",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5321, 5321): _d(
        [602, 608, 611, 615, 618],
        "f3d7774:5321 ('},') now at :1864,1886,2524",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5322, 5322): _d(
        [603, 606, 609, 612, 616, 619],
        "f3d7774:5322 ('}') now at :170,214,219",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5332, 5332): _d(
        [604, 607, 610, 613, 614, 617, 620],
        "f3d7774:5332 ('merged[key] = merged.get(key, 0.0) + delta') now at :5846",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5338, 5338): _d(
        [640, 644, 688],
        "f3d7774:5338 ('os.replace(temporary, target)') now at :5852",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5341, 5341): _d(
        [671],
        "f3d7774:5341 ('safe_print(f\"[TEXTFILE] {run_id} failed: {exc}\")') now at :5855",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 5345, 5345): _d(
        [55, 381],
        "f3d7774:5345 ('def _publish_run_metrics(') now at :5859",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 7792, 7800): _d(
        [528],
        "f3d7774:7792 ('parser.add_argument(') now at :8289",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 7934, 7934): _d(
        [54],
        "f3d7774:7934 ('set_runner_up(\"cron\", True)') now at :8448",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 7963, 7971): _d(
        [661],
        "f3d7774:7963 ('_write_textfile_record(') now at :8477",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 7963, 7963): _d(
        [669, 692, 706, 716],
        "f3d7774:7963 ('_write_textfile_record(') now at :8477,11472",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 7964, 7964): _d(
        [529],
        "f3d7774:7964 ('getattr(args, \"textfile_dir\", DEFAULT_TEXTFILE_DIR),') now at :8478",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 7975, 7975): _d(
        [55, 381, 661],
        "f3d7774:7975 ('_publish_run_metrics(\"error\", duration_s, autonomy, teache') now at :8489",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 7976, 7976): _d(
        [662],
        "f3d7774:7976 ('raise') now at :8490",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 8383, 8383): _d(
        [529],
        "f3d7774:8383 ('S.textfile_dir = args.textfile_dir') now at :8897",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 8581, 8581): _d(
        [50, 380],
        "f3d7774:8581 ('observe_cycle(mode, pipeline_name)') now at :9097",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 8585, 8585): _d(
        [74],
        "f3d7774:8585 ('_publish_data_growth_metrics()') now at :9101,11487",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 8614, 8614): _d(
        [392],
        "f3d7774:8614 ('def _cycle_capture(S, cycle):') now at :9130",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 8635, 8635): _d(
        [393],
        "f3d7774:8635 ('def _cycle_observe(S, screenshot, frame_hash):') now at :9151",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 8680, 8680): _d(
        [72, 393, 1021],
        "f3d7774:8680 ('def _track_emulator_integrity(S, frame_hash, patch_data) -') now at :9196",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 8728, 8728): _d(
        [74],
        "f3d7774:8728 ('def _publish_data_growth_metrics(') now at :9244",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 8941, 8941): _d(
        [390],
        "f3d7774:8941 ('written_keys=S._world_memory_written_keys,') now at :9457",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 8993, 8993): _d(
        [393],
        "f3d7774:8993 ('def _cycle_header(S, cycle):') now at :9509",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 9311, 9311): _d(
        [51, 380],
        "f3d7774:9311 ('observe_decision_seconds(DECISION_MODE or \"unknown\", pipel') now at :9836",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 9318, 9318): _d(
        [390, 1018],
        "f3d7774:9318 ('def _ow_track_stuck(S, patch_data, st):') now at :9843",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 10520, 10530): _d(
        [651, 683],
        "f3d7774:10520 ('_write_autonomy_row(') now at :11457",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 10531, 10531): _d(
        [652],
        "f3d7774:10531 ('_write_degradation_row(log_file, S.run_id, autonomy)') now at :11468",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 10532, 10534): _d(
        [653],
        'f3d7774:10532 (\'outcome = "gave_up" if getattr(S, "_gave_up", False) else \') now at :11469',
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 10535, 10543): _d(
        [654],
        "f3d7774:10535 ('_write_textfile_record(') now at :8477",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 10535, 10535): _d(
        [669, 692, 706, 716],
        "f3d7774:10535 ('_write_textfile_record(') now at :8477,11472",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 10536, 10536): _d(
        [529],
        "f3d7774:10536 ('getattr(S, \"textfile_dir\", DEFAULT_TEXTFILE_DIR),') now at :11473",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 10546, 10546): _d(
        [55, 381, 655],
        "f3d7774:10546 ('_publish_run_metrics(outcome, duration_s, autonomy, teache') now at :11483",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 10547, 10547): _d(
        [656],
        "f3d7774:10547 ('log_file.close()') now at :11484",
    ),  # moved by bcc61b68+0f9d6477
    ("observability-spec.md", "cron_runner.py", 10550, 10550): _d(
        [74],
        "f3d7774:10550 ('_publish_data_growth_metrics()') now at :9101,11487",
    ),  # moved by bcc61b68+0f9d6477
}


# ── doc parsing ──────────────────────────────────────────────────────────


def _checked_mask(lines: list[str], doc_name: str) -> list[bool]:
    """Per-line mask: True = the guard audits citations on that line."""
    mask = [True] * len(lines)
    if doc_name != "observability-spec.md":
        return mask

    def locate(snippet: str) -> int:
        for i, line in enumerate(lines):
            if snippet in line:
                return i
        raise AssertionError(f"declaration marker not found: {snippet!r}")

    # Skip the self-declared superseded re-derivation paragraph (lines 15–24).
    note_start = locate("**Citation re-derivation")
    note_end = locate("Product repo:")
    for i in range(note_start, note_end):
        mask[i] = False

    # Skip the declared §0–§3 audit-history body (line 13), except dated
    # UPDATE blockquotes, which line 13 says resolve against the current tree.
    h_start = locate("## 0. ")
    h_end = locate("## 4. ")
    i = h_start
    while i < h_end:
        if lines[i].lstrip().startswith(">"):
            j = i
            while j < h_end and lines[j].lstrip().startswith(">"):
                j += 1
            is_update = bool(_UPDATE_BLOCK_RE.search(lines[i]))
            for k in range(i, j):
                mask[k] = is_update
            i = j
        else:
            mask[i] = False
            i += 1
    return mask


def _block_bounds(lines: list[str], i: int) -> tuple[int, int]:
    """Contiguous blockquote run (or non-blank paragraph) containing line i."""
    if lines[i].lstrip().startswith(">"):
        a = i
        while a > 0 and lines[a - 1].lstrip().startswith(">"):
            a -= 1
        b = i
        while b + 1 < len(lines) and lines[b + 1].lstrip().startswith(">"):
            b += 1
    else:
        a = i
        while a > 0 and lines[a - 1].strip():
            a -= 1
        b = i
        while b + 1 < len(lines) and lines[b + 1].strip():
            b += 1
    return a, b


def _code_tokens(text: str, dotall: bool = False) -> set[str]:
    """Code symbols named in ``text``: identifiers (≥4 chars) in backticks."""
    tokens: set[str] = set()
    pattern = _BACKTICK_SPAN_RE if dotall else _BACKTICK_RE
    for m in pattern.finditer(text):
        tokens.update(_IDENT_RE.findall(m.group(1)))
    return tokens


def _line_tokens(lines: list[str], i: int, fence: bool = False) -> set[str]:
    """Symbols named on doc line i, escalating to its block when the line
    names no code symbol beyond file-path fragments (e.g. a line that only
    says ``(``requirements.txt:49`, ``pyproject.toml:30`)`` — the family it
    means is named elsewhere in the same block)."""
    raw = lines[i]
    if fence:
        # inside a ``` fence the whole line is code — read identifiers raw
        tokens = set(_IDENT_RE.findall(raw))
    else:
        tokens = _code_tokens(raw)
        if raw.count("`") % 2 == 1:
            # an unclosed inline span: the pair closes on a later line of the
            # same block (e.g. `...outcome =
            # "send_failed"`) — re-read spans block-wide
            a, b = _block_bounds(lines, i)
            tokens |= _code_tokens("\n".join(lines[a : b + 1]), dotall=True)
    mention_tokens: set[str] = set()
    for m in _MENTION_RE.finditer(raw):
        mention_tokens.update(_IDENT_RE.findall(m.group(0)))
    if tokens and tokens.issubset(mention_tokens):
        tokens = set()
    if not tokens:
        a, b = _block_bounds(lines, i)
        for k in range(a, b + 1):
            tokens.update(_code_tokens(lines[k]))
    return tokens


def _symbol_in_window(token: str, window: str) -> bool:
    """Tolerant containment: exact, case-insensitive, or a run of ≥2
    consecutive underscore components (``aipp_runlog_last_write_timestamp``
    matches the ``_RUNLOG_LAST_WRITE`` the page anchors on)."""
    if token in window or token.lower() in window.lower():
        return True
    win = window.upper()
    comps = [c.upper() for c in token.split("_") if c]
    if len(comps) < 2:
        return False
    for n in range(len(comps) - 1, 1, -1):
        for s in range(len(comps) - n + 1):
            if "_".join(comps[s : s + n]) in win:
                return True
    return False


# ── the walk ─────────────────────────────────────────────────────────────


@dataclass
class CitationCheck:
    doc: str
    doc_line: int
    target: str  # repo-relative target the ref was bound to
    start: int
    end: int
    ok: bool
    evidence: str
    tokens: frozenset[str]

    @property
    def key(self) -> tuple[str, str, int, int]:
        return (self.doc, self.target, self.start, self.end)

    def describe(self) -> str:
        span = f"{self.start}-{self.end}" if self.end != self.start else str(self.start)
        return f"{self.doc}:{self.doc_line} -> {self.target}:{span} [{self.evidence}]"


class _Auditor:
    """Walks one docs tree + product checkout pair, with per-run caches."""

    def __init__(self, docs_root: Path, product_root: Path) -> None:
        self.docs_root = docs_root
        self.product_root = product_root
        self._resolve_cache: dict[str, Path | None] = {}
        self._file_lines: dict[str, list[str]] = {}
        self._fn_spans: dict[str, dict[str, list[tuple[int, int]]]] = {}
        self._trees: dict[str, ast.Module | None] = {}
        self._stmt_idx: dict[str, dict[int, tuple[int, int]]] = {}

    # -- cached source access ------------------------------------------------

    def _lines_of(self, rel_target: str) -> list[str]:
        cached = self._file_lines.get(rel_target)
        if cached is None:
            path = self.product_root / rel_target
            try:
                cached = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                cached = []
            self._file_lines[rel_target] = cached
        return cached

    def _function_spans(self, rel_target: str) -> dict[str, list[tuple[int, int]]]:
        spans = self._fn_spans.get(rel_target)
        if spans is None:
            spans = {}
            tree = self._ast_tree(rel_target)
            if tree is not None:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        end = node.end_lineno or node.lineno
                        spans.setdefault(node.name, []).append((node.lineno, end))
            self._fn_spans[rel_target] = spans
        return spans

    def _statement_span(self, rel_target: str, lineno: int) -> tuple[int, int]:
        """Tightest ast statement containing ``lineno`` — the docs anchor
        statement STARTS (``metrics.py:132`` = the ``_EMULATOR_DESYNC =
        _metric(`` line) with the family string a couple of lines below."""
        index = self._stmt_index(rel_target)
        return index.get(lineno, (lineno, lineno))

    def _stmt_index(self, rel_target: str) -> dict[int, tuple[int, int]]:
        """line → tightest containing statement span, built once per file."""
        index = self._stmt_idx.get(rel_target)
        if index is None:
            index = {}
            tree = self._ast_tree(rel_target)
            if tree is not None:
                for node in ast.walk(tree):
                    if isinstance(node, ast.stmt):
                        start = node.lineno
                        end = node.end_lineno or node.lineno
                        for n in range(start, end + 1):
                            prev = index.get(n)
                            if prev is None or (end - start) < (prev[1] - prev[0]):
                                index[n] = (start, end)
            self._stmt_idx[rel_target] = index
        return index

    def _ast_tree(self, rel_target: str):
        if rel_target not in self._trees:
            try:
                source = (self.product_root / rel_target).read_text(encoding="utf-8")
                self._trees[rel_target] = ast.parse(source)
            except (OSError, SyntaxError, ValueError):
                self._trees[rel_target] = None
        return self._trees[rel_target]

    def _resolve(self, ref: str) -> str | None:
        """Resolve a doc mention (path or bare basename) to repo-relative path."""
        if ref in self._resolve_cache:
            hit = self._resolve_cache[ref]
            return hit.relative_to(self.product_root).as_posix() if hit else None
        resolved: Path | None = None
        direct = self.product_root / ref
        if direct.is_file():
            resolved = direct
        elif "/" not in ref:
            for base in ("src", "scripts", "tests"):
                root = self.product_root / base
                if not root.is_dir():
                    continue
                for path in sorted(root.rglob(ref)):
                    if _PRUNE_DIRS.isdisjoint(path.parts):
                        resolved = path
                        break
                if resolved is not None:
                    break
        self._resolve_cache[ref] = resolved
        return resolved.relative_to(self.product_root).as_posix() if resolved else None

    # -- citation checking ---------------------------------------------------

    def _check(
        self,
        lines: list[str],
        i: int,
        doc_name: str,
        target: str,
        start: int,
        end: int,
        overflow: bool = False,
        fence: bool = False,
    ) -> CitationCheck:
        tokens = _line_tokens(lines, i, fence=fence)
        evidence = "no named symbol in the cited window"
        ok = False
        if overflow:
            evidence = "anchor overflows the bound file (stale line number)"
        elif not tokens:
            evidence = "no code symbol named on the doc line"
        else:
            file_lines = self._lines_of(target)
            window = "\n".join(file_lines[start - 1 : end])
            hit = sorted(t for t in tokens if _symbol_in_window(t, window))
            if not hit and not target.endswith((".toml", ".txt")):
                # statement-start anchors: widen to the ast statement that
                # contains the anchor line (never for data files — no ast)
                stmt_start, stmt_end = self._statement_span(target, start)
                if (stmt_start, stmt_end) != (start, start):
                    window = "\n".join(file_lines[stmt_start - 1 : stmt_end])
                    hit = sorted(t for t in tokens if _symbol_in_window(t, window))
            if hit:
                ok = True
                evidence = f"symbol {hit[0]!r} present in window"
            else:
                for name in sorted(tokens):
                    for fn_start, fn_end in self._function_spans(target).get(name, ()):
                        if max(start, fn_start) <= min(end, fn_end):
                            ok = True
                            evidence = (
                                f"window inside span of {name}() ({fn_start}-{fn_end})"
                            )
                            break
                    if ok:
                        break
        return CitationCheck(
            doc=doc_name,
            doc_line=i + 1,
            target=target,
            start=start,
            end=end,
            ok=ok,
            evidence=evidence,
            tokens=frozenset(tokens),
        )

    def audit(self, doc_name: str) -> list[CitationCheck]:
        doc_path = self.docs_root / doc_name
        assert doc_path.is_file(), f"doc missing: {doc_path}"
        lines = doc_path.read_text(encoding="utf-8").splitlines()
        mask = _checked_mask(lines, doc_name)

        # pass 1 — the declared subject file is the overflow fallback for
        # bare ":N" refs (see SUBJECT_FILE).
        subject = SUBJECT_FILE.get(doc_name)
        if subject is not None:
            resolved_subject = self._resolve(subject)

        carry: str | None = None  # last resolved code-file mention
        in_fence = False
        checks: list[CitationCheck] = []
        for i, line in enumerate(lines):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
            prev_carry = carry  # carry as of the END of the previous line
            mentions: list[tuple[int, str]] = []
            for m in _MENTION_RE.finditer(line):
                rel = self._resolve(m.group(0))
                if rel is not None:
                    mentions.append((m.start(), rel))
                    carry = rel

            if not mask[i]:
                continue

            explicit = list(_CITATION_RE.finditer(line))
            for m in explicit:
                target = self._resolve(m.group("ref"))
                if target is None:
                    continue  # quoted command / prose path, not a live citation
                start = int(m.group("start"))
                end = int(m.group("end") or m.group("start"))
                checks.append(
                    self._check(lines, i, doc_name, target, start, end, fence=in_fence)
                )

            for m in _BARE_REF_RE.finditer(line):
                if any(s <= m.start() < e for s, e in (x.span() for x in explicit)):
                    continue  # the ":N" of an explicit file:N citation
                start = int(m.group("start"))
                end = int(m.group("end") or m.group("start"))
                before = [t for pos, t in mentions if pos < m.start()]
                after = [t for pos, t in mentions if pos >= m.start()]
                ordered: list[str] = []
                for cand in (
                    *before[-1:],
                    *after[:1],
                    prev_carry,
                    resolved_subject if subject is not None else None,
                ):
                    if cand is not None and cand not in ordered:
                        ordered.append(cand)
                if not ordered:
                    continue
                in_range = [
                    cand
                    for cand in ordered
                    if start <= len(self._lines_of(cand))
                    or end <= len(self._lines_of(cand))
                ]
                if in_range:
                    checks.append(
                        self._check(
                            lines, i, doc_name, in_range[0], start, end, fence=in_fence
                        )
                    )
                else:
                    # every candidate overflows: bind deterministically to the
                    # first so the drift is still recorded
                    checks.append(
                        self._check(
                            lines,
                            i,
                            doc_name,
                            ordered[0],
                            start,
                            end,
                            overflow=True,
                            fence=in_fence,
                        )
                    )
        return checks


def _format_failures(failures: list[CitationCheck], limit: int = 30) -> str:
    shown = failures[:limit]
    body = "\n".join(f"  - {c.describe()}" for c in shown)
    more = "" if len(failures) <= limit else f"\n  ... and {len(failures) - limit} more"
    return (
        f"{len(failures)} doc citation(s) no longer resolve against the tree "
        f"(the docs present them as current; they are NOT in KNOWN_DRIFT). "
        f"Either the source moved under the docs — re-derive the anchor — or, "
        f"if this is the known pre-DOC-028-refresh drift, add the key to "
        f"KNOWN_DRIFT with evidence.\n{body}{more}"
    )


def _audit_with_baseline(
    doc_name: str,
) -> tuple[list[CitationCheck], list[CitationCheck], list[tuple[str, str, int, int]]]:
    """Returns (all checks, unbaselined failures, stale baseline keys)."""
    checks = _Auditor(DOCS_ROOT, PRODUCT_ROOT).audit(doc_name)
    failures = [c for c in checks if not c.ok and c.key not in KNOWN_DRIFT]
    still_failing = {c.key for c in checks if not c.ok}
    stale = [k for k in KNOWN_DRIFT if k[0] == doc_name and k not in still_failing]
    return checks, failures, stale


# ── tests ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("doc_name", list(DOCS))
def test_doc_citations_resolve(doc_name: str):
    checks, failures, stale = _audit_with_baseline(doc_name)
    assert checks, "walker found no citations — regex or region logic broke"
    assert not failures, _format_failures(failures)
    assert not stale, (
        f"KNOWN_DRIFT entries for {doc_name} no longer fail — the docs were "
        f"refreshed; shrink the baseline: {stale}"
    )


def test_declared_history_regions_are_skipped():
    lines = (
        (DOCS_ROOT / "observability-spec.md").read_text(encoding="utf-8").splitlines()
    )
    mask = _checked_mask(lines, "observability-spec.md")

    def idx(snippet: str) -> int:
        for i, line in enumerate(lines):
            if snippet in line:
                return i
        raise AssertionError(f"marker not found: {snippet!r}")

    # Declared history (line 13): §0–§3 bodies skipped…
    assert not mask[idx("the reply sat inside")]  # §3.3 audit-day table row
    assert not mask[idx("kept verbatim so the audit history stays checkable")]
    assert not mask[idx("wrapper (cron_runner.py:18-23)")]  # §1.4 audit body
    # …except dated UPDATE blockquotes, which resolve against the current tree.
    assert mask[idx("now sits at `src/dashboard/main.py:370-376`")]
    assert mask[idx("**UPDATE 2026-11-17:** this section is still accurate")]
    # The self-declared superseded offset note (lines 15–24) is skipped.
    assert not mask[idx("+4 at :8585")]
    # The top UPDATE block (current tree) is checked.
    assert mask[idx("| metrics.py:19 |")]
    # §4 onward is checked.
    assert mask[idx("`DEFAULT_TEXTFILE_DIR` | :55")]

    # cron_runner.md declares no history body → walked in full.
    cr_lines = (
        (DOCS_ROOT / "api/cron_runner.md").read_text(encoding="utf-8").splitlines()
    )
    assert all(_checked_mask(cr_lines, "cron_runner.md"))


def test_guard_bites_when_cited_anchor_moves(tmp_path: Path):
    """Negative proof: moving one cited anchor must produce a NEW failure."""
    scratch_docs = tmp_path / "docs"
    shutil.copytree(DOCS_ROOT, scratch_docs)
    scratch_root = tmp_path
    for rel in CITED_SOURCES:
        src = PRODUCT_ROOT / rel
        if src.is_file():
            dst = scratch_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # Premise: the byte-identical scratch tree audits clean (⊆ baseline).
    pre_checks = _Auditor(scratch_docs, scratch_root).audit("api/cron_runner.md")
    pre_failures = [c for c in pre_checks if not c.ok and c.key not in KNOWN_DRIFT]
    assert not pre_failures, _format_failures(pre_failures)
    pre_fail_keys = {c.key for c in pre_checks if not c.ok}

    # Sabotage: push cron_runner.py's DEFAULT_TEXTFILE_DIR (cited at :55 by
    # both docs) 20 lines down with padding comments. Lives and dies inside
    # tmp_path — never committed.
    cr = scratch_root / "cron_runner.py"
    cr_lines = cr.read_text(encoding="utf-8").splitlines(keepends=True)
    anchor = next(
        i for i, line in enumerate(cr_lines) if line.startswith("DEFAULT_TEXTFILE_DIR")
    )
    cr_lines[anchor:anchor] = [
        f"# DOC-028 sabotage padding {n}: the anchor below used to sit here\n"
        for n in range(20)
    ]
    cr.write_text("".join(cr_lines), encoding="utf-8")

    post_checks = _Auditor(scratch_docs, scratch_root).audit("api/cron_runner.md")
    new_failures = [
        c
        for c in post_checks
        if not c.ok and c.key not in pre_fail_keys and c.key not in KNOWN_DRIFT
    ]
    sabotaged = [
        f
        for f in new_failures
        if f.target == "cron_runner.py"
        and f.start == 55
        and "DEFAULT_TEXTFILE_DIR" in f.tokens
    ]
    assert sabotaged, (
        "the guard did NOT bite on a 20-line anchor move — new failures: "
        + ("; ".join(f.describe() for f in new_failures[:10]) or "none at all")
    )
