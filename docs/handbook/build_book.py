#!/usr/bin/env python3
"""Build the AI-Plays-Poke handbook set from one manifest.

The book is data: every sheet's address (part, page id, figure codes) is assigned here, in one
place, before a line of prose. Sheets import the house style from sheet_style.py; none carries its
own CSS. Each sheet is rendered and fit-checked on its own; the set is then merged with pdfunite
and verified by page count and folio grep.

Every printed number comes from specs/_facts.md or was grepped from the code on 2026-11-11. Where
a figure carries a count, the caption stamps the measurement date (a snapshot is not a state).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sheet_style import DOC_NO, PART, page, para, print_pdf  # noqa: E402

OUT = Path(__file__).parent
SHEETS: list[dict] = []


def lower_band(
    num: str, table_num: str, caption: str, rows, notice=None, card=None
) -> str:
    r = "".join(f'<tr><td>{k}</td><td class="v">{v}</td></tr>' for k, v in rows)
    n = (
        f'<div class="notice"><span class="tag">{notice[0]}</span><p>{notice[1]}</p></div>'
        if notice
        else ""
    )
    c = ""
    if card:
        lis = "".join(
            f"<li><span></span><span>{line}</span></li>"
            if line.startswith("√")
            else f"<li><span>{i + 1}</span><span>{line}</span></li>"
            for i, line in enumerate(card[1])
        )
        c = f'<div class="card"><div class="bar"><span>{card[0]}</span><span>OPERATOR</span></div><ol>{lis}</ol></div>'
    return (
        f'<div class="lower"><div><section class="para"><div class="num">{num}</div>'
        f"<div><h2>PERFORMANCE AND DESIGN DATA.</h2></div></section>"
        f'<div class="tcap">{table_num}. {caption}</div>'
        f"<table><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>{r}</tbody></table>"
        f"</div><div>{n}{c}</div></div>"
    )


def fig(svg: str, num: str, title: str) -> str:
    # Full code in the span: "Figure 1.1-1." — the sheet_style splitter would cut at the first dot.
    return f'<figure>{svg}<figcaption><span class="n">{num}.</span>{title}</figcaption></figure>'


# ════════════════════════════════ 1 SYSTEM OVERVIEW ════════════════════════════════
HERO_OVERVIEW = """
<svg viewBox="0 0 180 64" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Full system architecture">
  <rect class="panel" x="34" y="3" width="66" height="27"/>
  <text class="lbl-s" x="36" y="6.2">OPERATOR CONSOLE - :8899</text>
  <rect class="box" x="38" y="9" width="28" height="12"/>
  <text class="lbl" x="52" y="13.6" text-anchor="middle">VERDICT</text>
  <text class="lbl-s" x="52" y="16.6" text-anchor="middle">RAM VS VISION</text>
  <rect class="box" x="70" y="9" width="26" height="12"/>
  <text class="lbl" x="83" y="13.6" text-anchor="middle">CONTROLS</text>
  <text class="lbl-s" x="83" y="16.6" text-anchor="middle">25 OF 26 IDS</text>
  <rect class="box" x="4" y="9" width="24" height="12"/>
  <text class="lbl" x="16" y="13.6" text-anchor="middle">OPERATOR</text>
  <text class="lbl-s" x="16" y="16.6" text-anchor="middle">TAILNET, NO AUTH</text>
  <line class="wa" x1="28" y1="15" x2="37.6" y2="15"/>
  <text class="lbl-s" x="28.6" y="13.4">LOOKS</text>
  <line class="wa" x1="100.4" y1="15" x2="113.6" y2="24"/>
  <text class="lbl-s" x="101.4" y="13.4">DRIVES</text>
  <rect class="box" x="114" y="24" width="28" height="14"/>
  <text class="lbl" x="128" y="29.6" text-anchor="middle">BRIDGE</text>
  <text class="lbl-s" x="128" y="32.8" text-anchor="middle">TOKEN :8770</text>
  <g>
    <rect class="of" x="152" y="22" width="18" height="20" rx="2"/>
    <ellipse class="o" cx="161" cy="22" rx="9" ry="2.6"/>
    <text class="lbl" x="161" y="47" text-anchor="middle">EMULATOR</text>
  </g>
  <line class="wa" x1="142" y1="29" x2="151.6" y2="29"/>
  <text class="lbl-s" x="142.6" y="27.4">STEP</text>
  <line class="wa" x1="152" y1="38" x2="142.4" y2="33"/>
  <text class="lbl-s" x="144" y="41.6">FRAME</text>
  <rect class="box" x="34" y="38" width="30" height="12"/>
  <text class="lbl" x="49" y="42.6" text-anchor="middle">RAM READER</text>
  <text class="lbl-s" x="49" y="45.6" text-anchor="middle">10 X 9 GRID</text>
  <rect class="gap" x="70" y="38" width="30" height="12"/>
  <text class="lbl" x="85" y="42.6" text-anchor="middle">VISION MODEL</text>
  <text class="lbl-s" x="85" y="45.6" text-anchor="middle">9 X 9 GRID (R-001)</text>
  <rect class="panel" x="66" y="35" width="38" height="17"/>
  <text class="lbl-s" x="68" y="54.6">OPENROUTER</text>
  <line class="wa" x1="114" y1="31" x2="103.6" y2="43.4"/>
  <line class="wa" x1="49" y1="38" x2="47.6" y2="30.4"/>
  <text class="lbl-s" x="30.4" y="35.4">GRID</text>
  <rect class="box" x="114" y="44" width="28" height="14"/>
  <text class="lbl" x="128" y="48.6" text-anchor="middle">JEV + LLM</text>
  <text class="lbl-s" x="128" y="51.6" text-anchor="middle">MODE SELECTED</text>
  <line class="wa" x1="128" y1="44" x2="128" y2="38.4"/>
  <line class="wa" x1="114" y1="51" x2="90" y2="57"/>
  <line class="w" x1="90" y1="57" x2="44" y2="57"/>
  <line class="wa" x1="44" y1="57" x2="44" y2="50.4"/>
  <text class="lbl-s" x="92" y="60.6">PRESS - STEP BACK THROUGH THE BRIDGE</text>
  <rect class="panel" x="152" y="48" width="26" height="12"/>
  <text class="lbl-s" x="154" y="51.2">FLEET BUILDS</text>
  <text class="lbl-s" x="154" y="54.2">AND VERIFIES</text>
  <line class="wa" x1="165" y1="48" x2="163" y2="42.4"/>
  <text class="code" x="178.6" y="63.4" text-anchor="end">AIP-101A</text>
</svg>"""

SHEETS.append(
    dict(
        file="aipp-1-1",
        tab="OVR",
        part_no="1",
        title="SYSTEM OVERVIEW",
        body=(
            para(
                "1.1.1",
                "INTRODUCTION.",
                "AI-PLAYS-POKE is an agent that plays POKEMON BLUE by understanding each room. It "
                "perceives through two channels, RAM and a vision model, that must agree cell for cell "
                "in one grid and one legend; JEV decides most cycles and hands the state to a reasoning "
                "model only when it cannot decide (figure 1.1-1).",
            )
            + fig(
                HERO_OVERVIEW,
                "Figure 1.1-1",
                "The System As Built, With The Vision Grid Defect Dotted",
            )
            + para(
                "1.1.2",
                "FUNCTIONAL DESCRIPTION.",
                "The emulator advances only when the bridge delivers inputs, so a live ticker stands "
                "in for a paused hand-held. The operator watches and drives through the console; the "
                "agent runs through the same bridge, and the two never drive at once. The fleet "
                "builds, tests and releases the agent; the board and the judge keep its work honest.",
            )
            + para(
                "1.1.2.1",
                "State Of The Goal.",
                "The September run reached VIRIDIAN CITY in 28 episodes. The October 27 run stopped "
                "the morning it started: 4 episodes, the last inside RED'S HOUSE 1F. The machine has "
                "improved; the game has not advanced since (measured 2026-11-11).",
                changebar=True,
                flush=True,
            )
            + lower_band(
                "1.1.3",
                "Table 1.1-1",
                "Where The Goal Stands",
                [
                    ("Goal, set by operator", "way past PALLET TOWN in 2 months"),
                    ("Sept run (28 eps)", "VIRIDIAN CITY reached"),
                    ("Oct 27 run", "4 eps, RED'S HOUSE 1F, then stopped"),
                    ("Last game action", "2026-10-27 08:49"),
                    ("Console position", "PALLET TOWN 5,6 down"),
                    ("Version", "v1.1.0 published 2026-11-04"),
                ],
                notice=(
                    "WARNING",
                    "THE CONSOLE HAS NO AUTHENTICATION. ANYTHING ON THE TAILNET "
                    "CAN DRIVE THE EMULATOR AND SPEND MODEL QUOTA.",
                ),
                card=(
                    "START A RUN",
                    [
                        "BRIDGE - verify health op",
                        "LIVE - set OFF",
                        "MODE - pick JEV/LLM/HYBRID",
                        "√ LOG - mode echoed at run head",
                        "RUN - cron_runner --cycles 20",
                        "√ VERDICT - agree/conflict shown",
                    ],
                ),
            )
        ),
        foot="SYSTEM OVERVIEW",
        page_id="1.1-1",
    )
)

# ════════════════════════════════ 2 EMULATOR BRIDGE ════════════════════════════════
OPS_SVG = """
<svg viewBox="0 0 180 60" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Bridge operation dispatch">
  <rect class="box" x="6" y="6" width="30" height="12"/>
  <text class="lbl" x="21" y="10.6" text-anchor="middle">CALLER</text>
  <text class="lbl-s" x="21" y="13.6" text-anchor="middle">TOKEN HEADER</text>
  <line class="wa" x1="36" y1="12" x2="57.6" y2="12"/>
  <text class="lbl-s" x="38" y="10.4">TOKEN CHECK</text>
  <rect class="box" x="58" y="6" width="26" height="12"/>
  <text class="lbl" x="71" y="10.6" text-anchor="middle">GUARD</text>
  <text class="lbl-s" x="71" y="13.6" text-anchor="middle">REFUSE ALL</text>
  <line class="w" x1="84" y1="12" x2="96" y2="12"/>
  <text class="lbl-s" x="85" y="10.4">13 OPS</text>
  <g class="lbl-s">
    <text x="100" y="10.6">health  observe  press</text>
    <text x="100" y="14.2">step  save  load  frame</text>
    <text x="100" y="17.8">raw  pause  resume</text>
    <text x="100" y="21.4">list_saves  reset  goal</text>
  </g>
  <line class="wa" x1="96" y1="12" x2="96" y2="23"/>
  <rect class="box" x="58" y="26" width="68" height="12"/>
  <text class="lbl" x="92" y="30.6" text-anchor="middle">SERIALISED GAME ACCESS</text>
  <text class="lbl-s" x="92" y="33.6" text-anchor="middle">ONE CALL AT A TIME - BOUND CONCURRENCY</text>
  <line class="wa" x1="92" y1="38" x2="92" y2="45.6"/>
  <text class="lbl-s" x="93" y="44">EVERYTHING WAITS ITS TURN</text>
  <rect class="of" x="60" y="46" width="20" height="10" rx="2"/>
  <ellipse class="o" cx="70" cy="46" rx="10" ry="2.4"/>
  <text class="lbl" x="70" y="60.4" text-anchor="middle" transform="translate(0,-2)">EMULATOR</text>
  <line class="wa" x1="21" y1="18" x2="21" y2="50"/>
  <line class="w" x1="21" y1="50" x2="59.6" y2="51"/>
  <text class="lbl-s" x="22" y="24">RESPONSES RETURN THE SAME PATH</text>
  <text class="code" x="178.6" y="59.4" text-anchor="end">AIP-201A</text>
</svg>"""

SHEETS.append(
    dict(
        file="aipp-2-1",
        tab="BRG",
        part_no="2",
        title="EMULATOR BRIDGE",
        body=(
            para(
                "2.1.1",
                "INTRODUCTION.",
                "The bridge is the only path to the emulator. It binds loopback only, refuses every "
                "request that does not carry its token, and exposes thirteen operations. A session "
                "without the token cannot talk to the emulator at all (figure 2.1-1).",
            )
            + fig(
                OPS_SVG,
                "Figure 2.1-1",
                "Token Gate, Operation Dispatch, Serialised Game Access",
            )
            + para(
                "2.1.2",
                "FUNCTIONAL DESCRIPTION.",
                "Every caller presents the token; the guard compares it in constant time and refuses "
                "the rest. Operations are line-delimited requests on one socket or single commands. "
                "Game access is serialised: one call at a time, so a console viewer and an agent "
                "cycle queue rather than corrupt the emulator.",
            )
            + para(
                "2.1.2.1",
                "Serialisation.",
                "An unbounded thread per connection once drove the host to load 1016. The bound now "
                "caps concurrency and Game access is a lock, so one slow frame makes everything wait "
                "its turn rather than fight.",
                flush=True,
            )
            + lower_band(
                "2.1.3",
                "Table 2.1-1",
                "Bridge Data",
                [
                    ("Listen", "127.0.0.1:8770, loopback only"),
                    ("Auth", "token, compare_digest"),
                    ("Operations", "13 (health ... goal)"),
                    ("Frame, native", "160 x 144 px, about 2.7 kB"),
                    ("Frame when degraded", "412 B blank - restart bridge"),
                    ("Step speed, measured", "120 frames in 6 ms"),
                    ("Capacity used at 60 fps", "about 0.3 percent"),
                ],
                notice=(
                    "CAUTION",
                    "TWO DRIVERS ON ONE BRIDGE FIGHT. STOP THE CONSOLE LIVE "
                    "TICKER BEFORE AN AGENT RUN.",
                ),
            )
        ),
        foot="EMULATOR BRIDGE",
        page_id="2.1-1",
    )
)

# ════════════════════════════════ 3 RAM READER ════════════════════════════════
GRID_SVG = """
<svg viewBox="0 0 180 58" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Tile grid anatomy">
  <text class="lbl-s" x="10" y="8">LIVE READING - PALLET TOWN, 5,6 FACING DOWN</text>
  <g class="mono">
    <text x="10" y="16">...BBBB...</text>
    <text x="10" y="20">...BBBB...</text>
    <text x="10" y="24">..1BDBB...</text>
    <text x="10" y="28">....&#8595;.....</text>
    <text x="10" y="32">..........</text>
    <text x="10" y="36">.........B</text>
    <text x="10" y="40">...BBB2..B</text>
    <text x="10" y="44">.........B</text>
    <text x="10" y="48">.........B</text>
  </g>
  <line class="ld" x1="30" y1="29.5" x2="44" y2="29.5"/>
  <text class="lbl-s" x="45" y="30.2">PLAYER - ARROW ROW 3, COL 4</text>
  <line class="ld" x1="30" y1="23.5" x2="44" y2="21"/>
  <text class="lbl-s" x="45" y="21.8">SPRITES 1 AND 2 FROM 0xC100</text>
  <line class="ld" x1="30" y1="15.5" x2="44" y2="13"/>
  <text class="lbl-s" x="45" y="13.8">WALLS - TERRAIN, 83.6 PROCENT AGREES WITH ROM</text>
  <rect class="box" x="118" y="10" width="54" height="34"/>
  <text class="lbl" x="145" y="15" text-anchor="middle">SYMBOL SET</text>
  <g class="mono">
    <text x="122" y="21">.  floor, walkable</text>
    <text x="122" y="25">B  blocking</text>
    <text x="122" y="29">G grass   W water</text>
    <text x="122" y="33">D doorway N person</text>
    <text x="122" y="37">$ real, unnamed</text>
    <text x="122" y="41">? cannot see</text>
  </g>
  <text class="lbl-s" x="10" y="54.4">ONE GRID, ONE SYMBOL SET, ONE LEGEND - THE LAW THE CODE MUST OBEY</text>
  <text class="code" x="178.6" y="57.4" text-anchor="end">AIP-301A</text>
</svg>"""

SHEETS.append(
    dict(
        file="aipp-3-1",
        tab="RAM",
        part_no="3",
        title="RAM READER",
        body=(
            para(
                "3.1.1",
                "INTRODUCTION.",
                "The RAM reader is System One's eye. It reads the emulator memory directly: map, "
                "player tile, facing, party, collision, and the sprite state table. It renders the "
                "room as a 10 by 9 tile grid with the player's facing arrow in his own cell "
                "(figure 3.1-1).",
            )
            + fig(
                GRID_SVG,
                "Figure 3.1-1",
                "The Live Tile Grid And Its Legend, With Measured Cells",
            )
            + para(
                "3.1.2",
                "FUNCTIONAL DESCRIPTION.",
                "Terrain comes from the ROM tile table; sprites come from wSpriteStateData1 at "
                "address C100, sixteen records of sixteen bytes, the player in slot zero. Facing "
                "renders as an arrow. The grid is the reference the vision channel is judged "
                "against, and its own terrain labels measured 83.6 percent against ROM collision.",
            )
            + para(
                "3.1.2.1",
                "Reference, Not Truth.",
                "The reader is a reference, not an oracle. Sprite meaning, dialogue and menus are "
                "invisible to it. A verdict disagreement is a finding to investigate, never a "
                "reason to overwrite one channel with the other.",
                flush=True,
            )
            + lower_band(
                "3.1.3",
                "Table 3.1-1",
                "Reader Data",
                [
                    ("Grid", "10 cols x 9 rows, arrow in player cell"),
                    ("Cell", "16 px, origin measured on screen"),
                    ("Sprite table", "0xC100, 16 x 16 bytes"),
                    ("Player slot", "0, excluded from people probes"),
                    ("Terrain vs ROM", "83.6 percent agreement"),
                    ("Cost per read", "free, every cycle"),
                ],
                card=(
                    "TAKE A READING",
                    [
                        "BRIDGE - verify health",
                        "STATE - read /api/state",
                        "√ GRID - 9 rows of 10",
                        "ARROW - confirm facing",
                    ],
                ),
            )
        ),
        foot="RAM READER",
        page_id="3.1-1",
    )
)

# ════════════════════════════════ 4 VISION CHANNEL ════════════════════════════════
VISION_SVG = """
<svg viewBox="0 0 180 56" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Vision pipeline and measured prompt effect">
  <text class="lbl-s" x="6" y="8">PIPELINE</text>
  <rect class="box" x="6" y="11" width="26" height="12"/>
  <text class="lbl" x="19" y="15.6" text-anchor="middle">FRAME</text>
  <text class="lbl-s" x="19" y="18.6" text-anchor="middle">160 X 144</text>
  <line class="wa" x1="32" y1="17" x2="43.6" y2="17"/>
  <rect class="box" x="44" y="11" width="30" height="12"/>
  <text class="lbl" x="59" y="15.6" text-anchor="middle">X6 LANCZOS</text>
  <text class="lbl-s" x="59" y="18.6" text-anchor="middle">CAP 1024 PX</text>
  <line class="wa" x1="74" y1="17" x2="85.6" y2="17"/>
  <text class="lbl-s" x="74.6" y="15.4">960 X 864</text>
  <rect class="box" x="86" y="11" width="30" height="12"/>
  <text class="lbl" x="101" y="15.6" text-anchor="middle">MODEL</text>
  <text class="lbl-s" x="101" y="18.6" text-anchor="middle">PER MODE</text>
  <line class="wa" x1="116" y1="17" x2="127.6" y2="17"/>
  <rect class="box" x="128" y="11" width="30" height="12"/>
  <text class="lbl" x="143" y="15.6" text-anchor="middle">PARSE</text>
  <text class="lbl-s" x="143" y="18.6" text-anchor="middle">FENCES OUT</text>
  <text class="lbl-s" x="6" y="30">MEASURED PROMPT EFFECT - ONE FROZEN IMAGE, ONE MODEL (2026-10-01)</text>
  <g class="lbl-s">
    <text x="6" y="36">TERSE PROMPT            68.9 PC AGREEMENT    0   PC UNKNOWN</text>
    <text x="6" y="40">CONSOLE PROMPT          36.7 PC              41  PC UNKNOWN</text>
    <text x="6" y="44">HEDGE PARAGRAPH OUT     54.4 PC              4   PC UNKNOWN</text>
  </g>
  <line class="wa" x1="118" y1="38" x2="96" y2="38"/>
  <text class="lbl-s" x="119.4" y="39">THE HEDGING CLAUSE</text>
  <text class="lbl-s" x="119.4" y="42.2">COST 32 POINTS</text>
  <text class="lbl-s" x="6" y="52.4">A TRUTHFUL ? IS WORTH MORE THAN A WRONG CHARACTER - BUT 41 PERCENT ? IS A REFUSAL, NOT HONESTY</text>
  <text class="code" x="178.6" y="55.4" text-anchor="end">AIP-401A</text>
</svg>"""

SHEETS.append(
    dict(
        file="aipp-4-1",
        tab="VIS",
        part_no="4",
        title="VISION CHANNEL",
        body=(
            para(
                "4.1.1",
                "INTRODUCTION.",
                "The vision channel describes the screen the way the RAM reader describes the room: "
                "one character per cell. It is the only channel that can name what a thing is - a "
                "person, a doorway, grass - and the only channel that hallucinates (figure 4.1-1).",
            )
            + fig(
                VISION_SVG,
                "Figure 4.1-1",
                "Pipeline And The Measured Effect Of Prompt Wording",
            )
            + para(
                "4.1.2",
                "FUNCTIONAL DESCRIPTION.",
                "The frame is enlarged six times with LANCZOS smoothing, capped at 1024 pixels, and "
                "sent to the configured model with a terse grid prompt. The reply is parsed through "
                "code fences, clamped to nine rows of ten characters, and compared against the RAM "
                "grid. Model, provider and prompt are measured variables, not tastes.",
            )
            + para(
                "4.1.2.1",
                "Models Are Multi-Possible.",
                "AIPP_VISION_MODELS carries an ordered list; the default served model is "
                "GPT-4O-MINI at 2.4 seconds and 25k tokens. KIMI K3, 2.8 trillion parameters, "
                "measured 62.2 percent at 97 seconds - bigger and newer was worse.",
                flush=True,
            )
            + lower_band(
                "4.1.3",
                "Table 4.1-1",
                "Vision Data",
                [
                    ("Default model", "openai/gpt-4o-mini"),
                    ("Reading time", "2.4-4 s"),
                    ("Tokens per read", "about 25k in, 34-100 out"),
                    ("Best cell agreement", "72.2 percent, terse prompt"),
                    ("Structure agreement", "scored on non-floor cells"),
                    ("People: frames correct", "1 of 3 (fails 66.7 pc)"),
                    ("People: anchoring", "same wrong answer on 2 of 3"),
                ],
                notice=(
                    "CAUTION",
                    "A READING THAT CANNOT ANSWER USES ? - BUT 41 PERCENT ? IS A "
                    "REFUSAL. RETUNE THE PROMPT, NOT THE MODEL.",
                ),
            )
        ),
        foot="VISION CHANNEL",
        page_id="4.1-1",
    )
)

# ════════════════════════════════ 5 DECISION CORE ════════════════════════════════
CYCLE_SVG = """
<svg viewBox="0 0 180 54" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Decision cycle timeline with escalation lane">
  <line class="w" x1="8" y1="10" x2="172" y2="10"/>
  <text class="lbl-s" x="6" y="6.4">ONE CYCLE OF THE AGENT</text>
  <g class="t">
    <line x1="20" y1="8.5" x2="20" y2="11.5"/><line x1="40" y1="8.5" x2="40" y2="11.5"/>
    <line x1="60" y1="8.5" x2="60" y2="11.5"/><line x1="80" y1="8.5" x2="80" y2="11.5"/>
    <line x1="100" y1="8.5" x2="100" y2="11.5"/><line x1="120" y1="8.5" x2="120" y2="11.5"/>
    <line x1="140" y1="8.5" x2="140" y2="11.5"/><line x1="160" y1="8.5" x2="160" y2="11.5"/>
  </g>
  <rect class="aud" x="14" y="16" width="34" height="9"/>
  <text class="lbl-s" x="31" y="21.8" text-anchor="middle">PERCEIVE - RAM</text>
  <rect class="aud" x="52" y="16" width="34" height="9"/>
  <text class="lbl-s" x="69" y="21.8" text-anchor="middle">PERCEIVE - VISION</text>
  <rect class="aud" x="90" y="16" width="30" height="9"/>
  <text class="lbl-s" x="105" y="21.8" text-anchor="middle">JEV DECIDES</text>
  <rect class="aud" x="124" y="16" width="26" height="9"/>
  <text class="lbl-s" x="137" y="21.8" text-anchor="middle">ACT</text>
  <line class="ev" x1="120" y1="25" x2="120" y2="40"/>
  <text class="lbl-s" x="121" y="29.4">CONF &lt; 0.50</text>
  <text class="lbl-s" x="121" y="32.8">OR AMBIG &gt; 0.40</text>
  <rect class="gap" x="90" y="40" width="60" height="9"/>
  <text class="lbl-s" x="120" y="45.8" text-anchor="middle">LLM REPAIRS THE STATE - NEVER THE ACTION</text>
  <text class="lbl-s" x="6" y="36.8">THE ESCALATION LANE IS UNEXERCISED AT SCALE:</text>
  <text class="lbl-s" x="6" y="40.4">0 TEACHER CALLS IN 757 DECISIONS</text>
  <text class="lbl-s" x="6" y="50.4">MODES: JEV / LLM / HYBRID - EXPLICIT, NEVER A SILENT DEFAULT</text>
  <text class="code" x="178.6" y="53.4" text-anchor="end">AIP-601A</text>
</svg>"""

SHEETS.append(
    dict(
        file="aipp-5-1",
        tab="DEC",
        part_no="5",
        title="DECISION CORE",
        body=(
            para(
                "5.1.1",
                "INTRODUCTION.",
                "JEV is System One: it answers every cycle and says when it cannot. The LLM is System "
                "Two: it repairs the agent's state on escalation and never presses a button. The two "
                "are modes of one core, selected explicitly, never inherited silently (figure 5.1-1).",
            )
            + fig(
                CYCLE_SVG, "Figure 5.1-1", "One Cycle, With The Escalation Lane Dotted"
            )
            + para(
                "5.1.2",
                "FUNCTIONAL DESCRIPTION.",
                "The mode resolves from AIPP_DECISION_MODE, then CRON_DECISION_MODE, by exact "
                "spelling; legacy spellings stay byte-identical in the episode log so old runs stay "
                "comparable. Thresholds are operator-fixed: hand off below 0.50 confidence or above "
                "0.40 ambiguity.",
            )
            + para(
                "5.1.2.1",
                "The Default That Cannot Walk.",
                "The shipped default, JEV alone, left PALLET TOWN in 0 of 5 tries; the pure LLM did "
                "6 of 6. A run launched without an explicit mode must refuse, not degrade to the arm "
                "that cannot leave town.",
                flush=True,
            )
            + lower_band(
                "5.1.3",
                "Table 5.1-1",
                "Decision Data",
                [
                    ("Modes", "jev / llm / hybrid, explicit"),
                    ("Env", "AIPP > CRON > refuse"),
                    ("Handoff confidence", "0.50"),
                    ("Handoff ambiguity", "0.40"),
                    ("Sept run", "757 decisions, 6 escalations"),
                    ("Teacher calls", "0 in 757 - path unexercised"),
                    ("Legacy spelling", "byte-identical (M6)"),
                ],
                notice=(
                    "CAUTION",
                    "A SILENT DEFAULT ARM IS A RUN THAT WALKS INTO A WALL ALL "
                    "DAY. REFUSE WITHOUT A MODE.",
                ),
            )
        ),
        foot="DECISION CORE",
        page_id="5.1-1",
    )
)

# ════════════════════════════════ 6 OPERATOR CONSOLE ════════════════════════════════
CONSOLE_SVG = """
<svg viewBox="0 0 180 56" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Console panel layout">
  <rect class="panel" x="4" y="4" width="172" height="48"/>
  <text class="lbl-s" x="6" y="7.2">:8899 - 13 PANELS - NO AUTH (TAILNET TRUST)</text>
  <rect class="box" x="8" y="11" width="30" height="16"/>
  <text class="lbl" x="23" y="15.6" text-anchor="middle">GAME</text>
  <text class="lbl-s" x="23" y="18.6" text-anchor="middle">200 MS REFRESH</text>
  <rect class="box" x="42" y="11" width="30" height="16"/>
  <text class="lbl" x="57" y="15.6" text-anchor="middle">RAM GRID</text>
  <text class="lbl-s" x="57" y="18.6" text-anchor="middle">9 X 10</text>
  <rect class="box" x="76" y="11" width="30" height="16"/>
  <text class="lbl" x="91" y="15.6" text-anchor="middle">VISION</text>
  <text class="lbl-s" x="91" y="18.6" text-anchor="middle">AGE, NO CALL</text>
  <rect class="box" x="110" y="11" width="30" height="16"/>
  <text class="lbl" x="125" y="15.6" text-anchor="middle">VERDICT</text>
  <text class="lbl-s" x="125" y="18.6" text-anchor="middle">CELL COMPARE</text>
  <rect class="box" x="144" y="11" width="28" height="16"/>
  <text class="lbl" x="158" y="15.6" text-anchor="middle">EVENTS</text>
  <text class="lbl-s" x="158" y="18.6" text-anchor="middle">COMMENTABLE</text>
  <rect class="box" x="8" y="31" width="30" height="14"/>
  <text class="lbl" x="23" y="35.6" text-anchor="middle">CONTROLS</text>
  <text class="lbl-s" x="23" y="38.6" text-anchor="middle">PAD - A/B - START</text>
  <rect class="box" x="42" y="31" width="30" height="14"/>
  <text class="lbl" x="57" y="35.6" text-anchor="middle">LIVE + AUTO</text>
  <text class="lbl-s" x="57" y="38.6" text-anchor="middle">STRICT BOOL</text>
  <rect class="box" x="76" y="31" width="30" height="14"/>
  <text class="lbl" x="91" y="35.6" text-anchor="middle">NOTES + TASKS</text>
  <text class="lbl-s" x="91" y="38.6" text-anchor="middle">PERSISTENT</text>
  <rect class="box" x="110" y="31" width="30" height="14"/>
  <text class="lbl" x="125" y="35.6" text-anchor="middle">DUCKBRAIN</text>
  <text class="lbl-s" x="125" y="38.6" text-anchor="middle">MEMORY SEARCH</text>
  <rect class="box" x="144" y="31" width="28" height="14"/>
  <text class="lbl" x="158" y="35.6" text-anchor="middle">TOOLS</text>
  <text class="lbl-s" x="158" y="38.6" text-anchor="middle">13+13+5+14</text>
  <line class="ld" x1="96" y1="27.4" x2="96" y2="30.4"/>
  <text class="lbl-s" x="8" y="49.4">PANELS REFRESH ON THEIR OWN: IMAGE 5 TIMES A SECOND, VISION AGE EVERY 10 S, STATE OVER SSE - NOTHING HIDES</text>
  <text class="code" x="174.6" y="53.4" text-anchor="end">AIP-701A</text>
</svg>"""

SHEETS.append(
    dict(
        file="aipp-6-1",
        tab="CON",
        part_no="6",
        title="OPERATOR CONSOLE",
        body=(
            para(
                "6.1.1",
                "INTRODUCTION.",
                "The console is the operator's eyes and hands: thirteen panels, the live game, the two "
                "grids, their verdict, and every control with a name derived from what it does. It "
                "drives the same bridge the agent drives (figure 6.1-1).",
            )
            + fig(CONSOLE_SVG, "Figure 6.1-1", "Panel Layout And The Refresh Law")
            + para(
                "6.1.2",
                "FUNCTIONAL DESCRIPTION.",
                "The game image refetches five times a second while the world runs; the vision panel "
                "ticks its age every ten seconds without spending a model call; state arrives over "
                "server-sent events. A failure answers a 500 body instead of dropping the socket, so "
                "no panel ever blanks.",
            )
            + para(
                "6.1.2.1",
                "Honest Input.",
                "Toggles read real booleans only: TRUE/FALSE/1/0/YES/NO/ON/OFF. Anything else leaves "
                "the state unchanged - a malformed request once switched the world on and blanked "
                "the video minutes later.",
                flush=True,
            )
            + lower_band(
                "6.1.3",
                "Table 6.1-1",
                "Console Data",
                [
                    ("Listen", ":8899, CONSOLE_PORT"),
                    ("Panels", "13"),
                    ("Controls", "26, 25 with stable ids"),
                    ("Image refresh", "200 ms while live"),
                    ("Vision age tick", "10 s, no model call"),
                    ("Tool surface", "13 bridge + 13 api + 5 mem + 14 cli"),
                    ("Auth", "none - tailnet only"),
                ],
                notice=(
                    "WARNING",
                    "THE CONSOLE IS UNAUTHENTICATED AND CAN DRIVE THE EMULATOR "
                    "AND SPEND QUOTA. EXPOSE IT ON THE TAILNET ONLY.",
                ),
                card=(
                    "RECOVER A BLANK PICTURE",
                    [
                        "SYMPTOM - frame 412 bytes",
                        "LIVE - set OFF",
                        "BRIDGE - restart service",
                        "√ FRAME - about 2.7 kB again",
                        "VISION - ask now",
                    ],
                ),
            )
        ),
        foot="OPERATOR CONSOLE",
        page_id="6.1-1",
    )
)

# ════════════════════════════════ 7 FLEET LOOP ════════════════════════════════
FLEET_SVG = """
<svg viewBox="0 0 180 58" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Fleet sequence from scheduler to judge">
  <text class="lbl-s" x="6" y="8">ONE BUILD CYCLE, LEFT TO RIGHT</text>
  <rect class="box" x="6" y="12" width="30" height="12"/>
  <text class="lbl" x="21" y="16.6" text-anchor="middle">SCHEDULER</text>
  <text class="lbl-s" x="21" y="19.6" text-anchor="middle">ADMIT BY TASKS</text>
  <line class="wa" x1="36" y1="18" x2="47.6" y2="18"/>
  <rect class="box" x="48" y="12" width="30" height="12"/>
  <text class="lbl" x="63" y="16.6" text-anchor="middle">FOREMAN</text>
  <text class="lbl-s" x="63" y="19.6" text-anchor="middle">ONE ROW PER TICK</text>
  <line class="wa" x1="78" y1="18" x2="89.6" y2="18"/>
  <rect class="box" x="90" y="12" width="30" height="12"/>
  <text class="lbl" x="105" y="16.6" text-anchor="middle">WORKER</text>
  <text class="lbl-s" x="105" y="19.6" text-anchor="middle">IMPLEMENTS</text>
  <line class="wa" x1="120" y1="18" x2="131.6" y2="18"/>
  <rect class="box" x="132" y="12" width="26" height="12"/>
  <text class="lbl" x="145" y="16.6" text-anchor="middle">JUDGE</text>
  <text class="lbl-s" x="145" y="19.6" text-anchor="middle">EVIDENCE</text>
  <line class="wa" x1="158" y1="18" x2="167" y2="18"/>
  <line class="wa" x1="167" y1="18" x2="167" y2="34"/>
  <line class="wa" x1="167" y1="34" x2="24.4" y2="34"/>
  <rect class="box" x="48" y="30" width="52" height="10"/>
  <text class="lbl" x="74" y="34.6" text-anchor="middle">BOARD - 357 ROWS, EVENTS, VERDICTS</text>
  <text class="lbl-s" x="6" y="42.4">THE DRAIN DEFECT: THE WAIVER COUNTS BLOCKED ROWS AS WORK</text>
  <g class="lbl-s">
    <text x="6" y="48">MEASURED 6 H: 42 DRY TICKS, 8.3M TOKENS, 0 COMMITS - THIS LANE</text>
    <text x="6" y="51.6">FLEET-WIDE: DAGGER 71 - WARPFS 47 - DUCKBRAIN 42 - CRIER 26</text>
  </g>
  <rect class="gap" x="118" y="44" width="56" height="9"/>
  <text class="lbl-s" x="146" y="47.2" text-anchor="middle">FIX FILED:</text>
  <text class="lbl-s" x="146" y="50.2" text-anchor="middle">SCHED-GAP-NODRAIN (P1)</text>
  <text class="code" x="178.6" y="57.4" text-anchor="end">AIP-801A</text>
</svg>"""

SHEETS.append(
    dict(
        file="aipp-7-1",
        tab="FLT",
        part_no="7",
        title="FLEET BUILD-AND-VERIFY",
        body=(
            para(
                "7.1.1",
                "INTRODUCTION.",
                "The fleet builds and verifies the agent: a scheduler admits a foreman by board work, "
                "the foreman dispatches one worker per tick, a judge grades the evidence, and the "
                "board remembers. Nothing lands on a claim (figure 7.1-1).",
            )
            + fig(
                FLEET_SVG,
                "Figure 7.1-1",
                "Scheduler To Judge To Board, With The Idle-Spin Defect Dotted",
            )
            + para(
                "7.1.2",
                "FUNCTIONAL DESCRIPTION.",
                "The lane's admission mode is tasks: a non-empty board waives the six-hour cooldown "
                "pin. Workers run in worktrees with their own environments; guards run at commit; "
                "releases are cut only on owner authorisation. Verification receipts and verdicts "
                "land beside the code they grade.",
            )
            + para(
                "7.1.2.1",
                "Idle Spin, Measured.",
                "Drained must mean no WORKABLE row. It currently means no open row: blocked and "
                "dep-gated rows waived the cooldown and produced 42 dry ticks in six hours on this "
                "lane alone - 8.3 million input tokens for nothing.",
                flush=True,
            )
            + lower_band(
                "7.1.3",
                "Table 7.1-1",
                "Fleet Data",
                [
                    ("Board", "357 rows, JSONL, git-backed"),
                    ("This project, complete", "339 of 357"),
                    ("Blocked", "2 (owner-gated, dep-gated)"),
                    ("Pending, real work", "16 incl. ARM-2, VIS-MODEL-1"),
                    ("Dry ticks, 6 h", "42 (8.3M tokens)"),
                    ("Commits since 09-28", "60 by 2026-10-01"),
                ],
                notice=(
                    "CAUTION",
                    "A BOARD THAT LOOKS NON-EMPTY KEEPS A TASKS LANE SPINNING. "
                    "MARK BLOCKED ROWS BLOCKED.",
                ),
            )
        ),
        foot="FLEET BUILD-AND-VERIFY",
        page_id="7.1-1",
    )
)

# ════════════════════════════════ 8 MONITORING AND RELEASE ════════════════════════════════
MON_SVG = """
<svg viewBox="0 0 180 52" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Observability and release surfaces">
  <text class="lbl-s" x="6" y="8">WHAT WATCHES THE AGENT</text>
  <rect class="box" x="6" y="12" width="34" height="12"/>
  <text class="lbl" x="23" y="16.6" text-anchor="middle">PROMETHEUS</text>
  <text class="lbl-s" x="23" y="19.6" text-anchor="middle">/METRICS/PROMETHEUS</text>
  <rect class="box" x="46" y="12" width="34" height="12"/>
  <text class="lbl" x="63" y="16.6" text-anchor="middle">NODE EXPORTER</text>
  <text class="lbl-s" x="63" y="19.6" text-anchor="middle">TEXTFILE RECORD</text>
  <rect class="box" x="86" y="12" width="34" height="12"/>
  <text class="lbl" x="103" y="16.6" text-anchor="middle">DUCKBRAIN</text>
  <text class="lbl-s" x="103" y="19.6" text-anchor="middle">NARRATION KEYS</text>
  <rect class="box" x="126" y="12" width="30" height="12"/>
  <text class="lbl" x="141" y="16.6" text-anchor="middle">SCHEDULER</text>
  <text class="lbl-s" x="141" y="19.6" text-anchor="middle">TICKS + COSTS</text>
  <line class="w" x1="40" y1="18" x2="46" y2="18"/>
  <line class="w" x1="80" y1="18" x2="86" y2="18"/>
  <line class="w" x1="120" y1="18" x2="126" y2="18"/>
  <text class="lbl-s" x="6" y="32">RELEASE STATE (2026-11-04)</text>
  <g class="lbl-s">
    <text x="6" y="38">v1.0.0 AND v1.1.0 TAGGED - v1.1.0 PUBLISHED: WHEEL 360028 B, SDIST 792763 B</text>
    <text x="6" y="41.6">WHEEL PACKAGING FIXED (SRC INTACT) - RELEASE CHECK RC 0</text>
  </g>
  <rect class="gap" x="6" y="44" width="150" height="6"/>
  <text class="lbl-s" x="8" y="48.6">OPEN: JUDGE TIER-2 BLOCKED BY 402 BILLING - QA BATTERIES WERE DISK-BLOCKED, NOW 40 PC FREE</text>
  <text class="code" x="178.6" y="51.4" text-anchor="end">AIP-901A</text>
</svg>"""

SHEETS.append(
    dict(
        file="aipp-8-1",
        tab="MON",
        part_no="8",
        title="MONITORING AND RELEASE",
        body=(
            para(
                "8.1.1",
                "INTRODUCTION.",
                "The agent is observed from four directions: Prometheus metrics on the dashboard, a "
                "node_exporter record from the cron lane, narration keys in DuckBrain, and the "
                "scheduler's own tick and cost ledger (figure 8.1-1).",
            )
            + fig(
                MON_SVG, "Figure 8.1-1", "Observability Surfaces And The Release State"
            )
            + para(
                "8.1.2",
                "FUNCTIONAL DESCRIPTION.",
                "Version 1.1.0 is the first published release: the tag fires its own CI, the wheel "
                "installs with the source package intact, and the version surfaces agree. Cuts "
                "require owner authorisation; the releng lane audits readiness each sweep.",
            )
            + para(
                "8.1.2.1",
                "Cost Truth.",
                "Costs are counted from the scheduler's session ledger by base URL and model, never "
                "from a billing label that a gateway restart can restamp.",
                flush=True,
            )
            + lower_band(
                "8.1.3",
                "Table 8.1-1",
                "Release Data",
                [
                    ("Version", "1.1.0, pyproject + CHANGELOG agree"),
                    ("Wheel", "360,028 bytes, src intact"),
                    ("sdist", "792,763 bytes"),
                    ("Tag CI", "success on the tag commit"),
                    ("Judge tier 2", "blocked, 402 billing"),
                    ("QA batteries", "disk was 98 pc, now 40 pc"),
                ],
                notice=(
                    "CAUTION",
                    "AN INSTALLED WHEEL FROM v1.0.0 OR v1.1.0 BEFORE THE FIX IS "
                    "NOT USABLE. REBUILD AFTER 70c272b.",
                ),
            )
        ),
        foot="MONITORING AND RELEASE",
        page_id="8.1-1",
    )
)


# ════════════════════════════════ 9 FLIGHT DATA FILE ════════════════════════════════
def fdf_sheet() -> str:
    body = (
        para(
            "9.1.1",
            "INTRODUCTION.",
            "This part collects the operator procedures. Each control is named as placarded on the "
            "console; each verification line starts with a check. Nothing here requires editing a "
            "file.",
        )
        + '<div class="lower" style="grid-template-columns:1fr 1fr; margin-top:2.8mm">'
        + '<div><div class="card"><div class="bar"><span>START A RUN</span><span>OPERATOR</span></div><ol>'
        + "".join(
            f"<li><span>{i + 1}</span><span>{l}</span></li>"
            if not l.startswith("√")
            else f"<li><span></span><span>{l}</span></li>"
            for i, l in enumerate(
                [
                    "BRIDGE - verify health op",
                    "LIVE - set OFF",
                    "MODE - pick JEV/LLM/HYBRID",
                    "√ LOG - mode echoed at run head",
                    "RUN - cron_runner --cycles 20",
                    "VISION - ask now (25k tok)",
                    "√ VERDICT - agree/conflict",
                ]
            )
        )
        + "</ol></div></div>"
        + '<div><div class="card"><div class="bar"><span>RECOVER VIDEO</span><span>OPERATOR</span></div><ol>'
        + "".join(
            f"<li><span>{i + 1}</span><span>{l}</span></li>"
            if not l.startswith("√")
            else f"<li><span></span><span>{l}</span></li>"
            for i, l in enumerate(
                [
                    "SYMPTOM - frame 412 bytes",
                    "LIVE - set OFF",
                    "BRIDGE - restart service",
                    "√ FRAME - about 2.7 kB again",
                    "√ STATE - tile unchanged",
                ]
            )
        )
        + "</ol></div></div>"
        + '<div><div class="card" style="margin-top:2mm"><div class="bar"><span>TAKE A READING</span><span>OPERATOR</span></div><ol>'
        + "".join(
            f"<li><span>{i + 1}</span><span>{l}</span></li>"
            if not l.startswith("√")
            else f"<li><span></span><span>{l}</span></li>"
            for i, l in enumerate(
                [
                    "VISION - ask now",
                    "√ VMETA - tokens + finish",
                    "√ GRID - 9 rows of 10",
                    "VERDICT - read conflicts",
                    "NOTE - record the finding",
                ]
            )
        )
        + "</ol></div></div>"
        + '<div><div class="card" style="margin-top:2mm"><div class="bar"><span>END A SESSION</span><span>OPERATOR</span></div><ol>'
        + "".join(
            f"<li><span>{i + 1}</span><span>{l}</span></li>"
            if not l.startswith("√")
            else f"<li><span></span><span>{l}</span></li>"
            for i, l in enumerate(
                [
                    "RUN - let the cycle end",
                    "LIVE - set OFF if left on",
                    "SAVE - bridge save slot",
                    "√ SAVES - list shows the slot",
                    "NOTE - what you saw",
                ]
            )
        )
        + "</ol></div></div>"
        + "</div>"
        + para(
            "9.1.2",
            "RULES THAT GOVERN EVERY PROCEDURE.",
            "Never drive the emulator from two places at once. Never let a run start without an "
            "explicit mode. A finding is a board row, not a memory.",
        )
    )
    return body


SHEETS.append(
    dict(
        file="aipp-9-1",
        tab="FDF",
        part_no="9",
        title="FLIGHT DATA FILE",
        body=fdf_sheet(),
        foot="FLIGHT DATA FILE",
        page_id="9.1-1",
    )
)


# ════════════════════════════════ COVER ════════════════════════════════
def cover_sheet() -> str:
    # Content ONLY - page() already supplies the .page wrapper, the running head and the footer.
    return f"""
  <div style="margin-top:12mm; text-align:center; letter-spacing:0.14em; line-height:1.7">
    <div style="font-size:15pt; letter-spacing:0.16em">AI-PLAYS-POKE</div>
    <div style="margin-top:3mm; font-size:9pt">AN AGENT THAT PLAYS POKEMON BLUE BY UNDERSTANDING</div>
    <div style="margin-top:1mm; font-size:8pt">TWO PERCEPTION CHANNELS - ONE GRID - DIFFED EVERY FRAME</div>
  </div>
  <div style="margin:8mm auto 0; width:132mm">
    <div class="rule"></div>
    <p style="text-indent:0; margin:3mm 0 0">
      This handbook describes the system as built and measured: the emulator bridge, the RAM
      reader, the vision channel, the decision core, the operator console, the fleet that builds
      and verifies it, and what watches it. Every number was taken from the code or measured on
      the live system; the ledger behind it is <span class="nowrap">specs/_facts.md</span>.
    </p>
    <p style="text-indent:0">
      The set states its own defects where it measured them: the one-row grid offset (R-001), the
      idle-spin admission waiver, the people-identification failure rate. A page that hides a
      measured defect is marketing, not a handbook.
    </p>
    <div class="rule" style="margin-top:4mm"></div>
    <table style="margin-top:2mm">
      <tbody>
        <tr><td>Document</td><td class="v">{DOC_NO}, Issue 1</td></tr>
        <tr><td>Scope</td><td class="v">the agent, its perception, its console, its fleet</td></tr>
        <tr><td>The one number</td><td class="v">72.2 pc cell agreement, best measured</td></tr>
        <tr><td>Readers</td><td class="v">worker, judge, operator</td></tr>
        <tr><td>Basic date</td><td class="v">24 September 2026</td></tr>
        <tr><td>Change date</td><td class="v">11 November 2026</td></tr>
        <tr><td>Sheets</td><td class="v">9 plus this cover</td></tr>
      </tbody>
    </table>
  </div>"""


SHEETS.insert(
    0,
    dict(
        file="aipp-0-cover",
        tab="AIP",
        part_no="0",
        title="COVER",
        body=cover_sheet(),
        foot="AI-PLAYS-POKE",
        page_id="COVER",
    ),
)


def main() -> None:
    # Second pass of substance: measured paragraphs per sheet, injected before the lower band.
    EXTRA = {
        "aipp-1-1": [
            (
                "1.1.2.2",
                "The Fleet Around It.",
                "Ten lanes serve this project: a foreman at priority 10 on a six-hour pin, plus qa, "
                "sync, releng, docs, readme, review, perf and their satellites. Since September 28 the "
                "foreman has landed 60 commits; the board holds 357 rows, 339 complete. The lanes share "
                "this host and its free-model quota with the emulator.",
            ),
            (
                "1.1.2.3",
                "What Is Deliberately Absent.",
                "No story modelling, no scripted walk tables, no voice control. The agent must win by "
                "understanding; everything else is scaffolding and is described only as it serves that.",
            ),
        ],
        "aipp-2-1": [
            (
                "2.1.2.2",
                "One Socket Or One Command.",
                "A live session speaks line-delimited requests on one socket; everything else sends "
                "single commands. When one Game call stopped answering it held the bridge for 25 "
                "seconds and every panel starved; the bound now makes one slow frame cost itself only.",
            ),
            (
                "2.1.2.3",
                "Revocation.",
                "The bridge refuses to boot without a token file, so it cannot start naked by "
                "accident. Revoke by killing the process and deleting the token; enable per session.",
            ),
        ],
        "aipp-3-1": [
            (
                "3.1.2.2",
                "What The Reader Cannot See.",
                "Text, menus, dialogue and name entry are invisible to RAM. A sprite's meaning is not "
                "in memory either. An out-of-range cell answers walkable, so read the code before "
                "trusting a verdict row that says the way is clear.",
            ),
            (
                "3.1.2.3",
                "Cost.",
                "The read is free and runs every cycle, which is exactly why it is the reference "
                "channel and the vision model is the guest that must justify its 25,000 tokens.",
            ),
        ],
        "aipp-4-1": [
            (
                "4.1.2.2",
                "People Are A Different Task.",
                "The people probe scored exact sprite cells against wSpriteStateData1: one frame in "
                "three correct, and the model answered girl at cell 1,4 on all three frames including "
                "the two where no girl stands there. It anchors. Constrain the question to "
                "RAM-predicted cells or do not trust the answer.",
            ),
            (
                "4.1.2.3",
                "Cost Discipline.",
                "A reading costs about 25,000 input tokens. The auto trigger reads on movement or "
                "scene change only; the 120-second idle timer was removed on 2026-10-01 after it "
                "generated readings around the clock for nothing.",
            ),
        ],
        "aipp-5-1": [
            (
                "5.1.2.2",
                "Evidence From The September Run.",
                "757 decisions across 28 episodes, 6 escalations. Autonomy 0.99 counts decisions not "
                "escalated; participation 0.99 counts cycles answered. They agree here only because "
                "the teacher was never called. They are different numbers and are reported separately.",
            ),
            (
                "5.1.2.3",
                "What JEV Cannot Decide.",
                "Map topology. All six escalations clustered on the Route 1 to Viridian transition, "
                "and episode 28 crossed it unaided. The next run must cross a boundary it has never "
                "seen, or the number proves nothing new.",
            ),
        ],
        "aipp-6-1": [
            (
                "6.1.2.2",
                "Naming Is Load-Bearing.",
                "Seventeen controls carried no id until 2026-10-01, which is why the mobile tap-size "
                "defect stood for weeks: nothing could select them. The duplicate-id check must read "
                "the whole page, not only the controls - a button and a panel once both claimed vision.",
            ),
            (
                "6.1.2.3",
                "Chat.",
                "The chat box posts into the agent's own session. One probe used the wrong field name, "
                "read an empty-error reply, and nearly reported the wire broken. Verify the field "
                "before blaming the wire.",
            ),
        ],
        "aipp-7-1": [
            (
                "7.1.2.2",
                "What A Good Tick Is.",
                "A tick that reports nothing changed, honestly, in one line, is a good tick. A tick "
                "that re-audits finished work is a wasted one. The foreman prompt says so; the "
                "admission loop must not fight it by re-admitting every three minutes.",
            ),
            (
                "7.1.2.3",
                "The Judge.",
                "Tier 1 runs secrets, static analysis and tests; tier 2 grades the evidence. Judge "
                "runs have been refused with a 402 billing fault, and a gate whose judge never sat is "
                "recorded DEGRADED, never PASS.",
            ),
        ],
        "aipp-8-1": [
            (
                "8.1.2.2",
                "What The Numbers Must Never Do.",
                "A cost read from a billing label lies after a gateway restart; count by base URL and "
                "session ledger instead. A lazy all-floor answer must never win a cell-match metric: "
                "score the cells that carry meaning, the walls and doors and sprites.",
            ),
        ],
    }
    extra_fdf = (
        '<div class="lower" style="grid-template-columns:1fr 1fr; margin-top:2mm">'
        '<div><div class="card"><div class="bar"><span>FILE A FINDING</span><span>OPERATOR</span></div><ol>'
        + "".join(
            f"<li><span>{i + 1}</span><span>{l}</span></li>"
            for i, l in enumerate(
                [
                    "FINDING - name the row",
                    "EVIDENCE - command + output",
                    "BOARD - append, never chat",
                    "√ VALIDATE - boardctl ok",
                ]
            )
        )
        + "</ol></div></div>"
        + '<div><div class="card"><div class="bar"><span>RELEASE A CUT</span><span>OPERATOR</span></div><ol>'
        + "".join(
            f"<li><span>{i + 1}</span><span>{l}</span></li>"
            for i, l in enumerate(
                [
                    "AUTH - owner says cut",
                    "CHECK - release_check rc 0",
                    "TAG - annotated, on main",
                    "√ CI - green on the tag",
                    "√ ASSETS - wheel installs",
                ]
            )
        )
        + "</ol></div></div></div>"
    )

    pdfs = []
    for s in SHEETS:
        body = s["body"]
        for ex in EXTRA.get(s["file"], []):
            body = body.replace(
                '<div class="lower">',
                para(ex[0], ex[1], ex[2]) + '<div class="lower">',
                1,
            )
        if s["file"] == "aipp-9-1":
            body = (
                body.replace("<footer", extra_fdf + "<footer", 1)
                if False
                else body + extra_fdf
            )
        html = page(
            doc_no=DOC_NO,
            part=PART,
            tab=s["tab"],
            opener=f"PART {s['part_no']} &nbsp;&nbsp;&middot;&nbsp;&nbsp; SHEET {s['page_id']}<br>{s['title']}",
            body=body,
            foot_sub=s["foot"],
            page_id=s["page_id"],
        )
        p = OUT / f"{s['file']}.html"
        p.write_text(html)
        pdf, fit = print_pdf(str(p))
        print(f"  {s['file']:14s} {fit}")
        pdfs.append(pdf)
    merged = OUT / "aipp-handbook.pdf"
    r = subprocess.run(["pdfunite", *pdfs, str(merged)], capture_output=True, text=True)
    if r.returncode != 0:
        print("pdfunite failed:", r.stderr[:300])
        sys.exit(2)
    print(f"merged: {merged}")
    # verify the rendered artifact: page count + folios present
    chk = subprocess.run(
        [
            "uv",
            "run",
            "--no-project",
            "--with",
            "pymupdf",
            "python",
            "-c",
            f"""
import fitz
d = fitz.open("{merged}")
print("pages:", d.page_count)
missing_folio = [i + 1 for i, pg in enumerate(d) if "Change Date" not in pg.get_text()]
print("sheets missing footer:", missing_folio or "none")
""",
        ],
        capture_output=True,
        text=True,
    )
    print(chk.stdout.strip() or chk.stderr[:400])


if __name__ == "__main__":
    main()
