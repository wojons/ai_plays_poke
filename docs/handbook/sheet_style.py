"""House style for the AI-Plays-Poke handbook set.

One module owns the look so every sheet is part of the same document: the CSS, the page wrapper
with its running head and stamped foot, the cover, and the print call. Sheets import from here;
none of them carries its own stylesheet (measured failure: ad-hoc stylesheets produce an artifact
worse than the document they join).

Facts flow one way: sheets print claims from specs/_facts.md and the code. A number that exists
only in a figure caption is an unverified claim wearing a uniform.
"""

from __future__ import annotations

import subprocess

DOC_NO = "AP1A-03"
PROGRAM = "AI-PLAYS-POKE OPERATIONS HANDBOOK"
PART = "SYSTEMS DATA"
BASIC_DATE = "24 September 2026"

CSS = """
  @font-face { font-family: "Routed Gothic"; src: url("fonts/routed-gothic.ttf"); unicode-range: U+0000-0030, U+0032-FFFF; }
  @font-face { font-family: "Routed Gothic Narrow"; src: url("fonts/routed-gothic-narrow.ttf"); unicode-range: U+0000-0030, U+0032-FFFF; }
  @font-face { font-family: "Routed Gothic"; src: local("Helvetica Neue"), local("HelveticaNeue"), local("Arial"); unicode-range: U+0031; }
  @font-face { font-family: "Routed Gothic Narrow"; src: local("Helvetica Neue"), local("HelveticaNeue"), local("Arial"); unicode-range: U+0031; }
  @font-face { font-family: "Letter Gothic"; src: url("fonts/LetterGothicCode-R.ttf"); font-weight: 400; }
  @font-face { font-family: "Letter Gothic"; src: url("fonts/LetterGothicCode-B.ttf"); font-weight: 700; }

  @page { size: A4; margin: 0; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: #8a8a86; }
  body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  @media print { html, body { background: none; } }

  :root { --ink:#000; --paper:#fbfaf5; --type:"Iowan Old Style","Iowan",Georgia,serif;
          --leroy:"Routed Gothic Narrow","Routed Gothic",sans-serif; --selectric:"Letter Gothic","Courier",monospace; }
  @media print { :root { --paper:#ffffff; } }

  .page { position:relative; width:210mm; height:297mm; margin:0 auto; padding:9mm 15mm 0 16mm;
          background:var(--paper); color:var(--ink); font-family:var(--type); font-size:8pt;
          line-height:1.33; letter-spacing:0.055em; overflow:hidden; }

  .head { text-align:center; line-height:1.25; }
  .head .doc { font-weight:700; font-size:8.6pt; letter-spacing:0.06em; }
  .head .title { font-weight:700; font-size:8.6pt; letter-spacing:0.08em; }
  .head .part { margin-top:2.2mm; font-size:8.2pt; letter-spacing:0.1em; }
  .rule { height:0; border-top:1.5pt solid var(--ink); margin:1.4mm -2mm 0; }

  .foot { position:absolute; left:16mm; right:15mm; bottom:8mm; }
  .foot .rule { margin:0 -2mm 1.6mm; }
  .foot .sub { text-align:center; letter-spacing:0.1em; font-size:8.2pt; }
  .foot .line { display:flex; align-items:baseline; justify-content:space-between; margin-top:2.2mm; font-size:8.2pt; }
  .foot .fill { display:inline-block; border-bottom:0.6pt solid var(--ink); text-align:center; padding:0 1mm; font-size:8.8pt; letter-spacing:0.03em; }

  .opener { text-align:center; letter-spacing:0.12em; margin:3.4mm 0 2mm; line-height:1.6; }

  .para { display:grid; grid-template-columns:19mm 1fr; position:relative; }
  .para .num { letter-spacing:0.08em; }
  .para h2, .para h3 { margin:0 0 0.8mm; font:inherit; font-weight:400; letter-spacing:0.08em; }
  .para h3 { text-decoration:underline; text-underline-offset:1.6pt; text-decoration-thickness:0.5pt; letter-spacing:0.06em; }
  .para p { margin:0 0 1mm; text-indent:9mm; text-align:left; }
  .para p.flush { text-indent:0; }
  .changebar { position:absolute; left:-9mm; width:1.3mm; background:var(--ink); }
  .nowrap { white-space:nowrap; }

  figure { margin:1.6mm 0 0; }
  figure svg { display:block; width:100%; height:auto; }
  figcaption { text-align:center; margin-top:0.6mm; letter-spacing:0.07em; }
  figcaption .n { margin-right:3mm; }

  svg text { font-family:var(--leroy); fill:var(--ink); letter-spacing:0.04px; }
  svg .o { fill:none; stroke:var(--ink); stroke-width:0.42; stroke-linejoin:round; stroke-linecap:round; }
  svg .of { fill:var(--paper); stroke:var(--ink); stroke-width:0.42; stroke-linejoin:round; }
  svg .t { fill:none; stroke:var(--ink); stroke-width:0.17; stroke-linecap:round; }
  svg .hid { fill:none; stroke:var(--ink); stroke-width:0.22; stroke-dasharray:1.3 0.7; }
  svg .cl { fill:none; stroke:var(--ink); stroke-width:0.16; stroke-dasharray:5 0.8 0.9 0.8; }
  svg .cut { fill:none; stroke:var(--ink); stroke-width:0.5; stroke-dasharray:5 1 1 1; }
  svg .ld { fill:none; stroke:var(--ink); stroke-width:0.16; marker-end:url(#nh-leader); }
  svg .dim { fill:none; stroke:var(--ink); stroke-width:0.16; marker-start:url(#nh-dim); }
  svg .w { fill:none; stroke:var(--ink); stroke-width:0.3; stroke-linejoin:round; }
  svg .wa { fill:none; stroke:var(--ink); stroke-width:0.3; stroke-linejoin:round; marker-end:url(#nh-arrow); }
  svg .box { fill:var(--paper); stroke:var(--ink); stroke-width:0.45; }
  svg .panel { fill:none; stroke:var(--ink); stroke-width:0.3; stroke-dasharray:2 1; }
  svg .ev { fill:none; stroke:var(--ink); stroke-width:0.18; stroke-dasharray:1 0.7; }
  svg .vid { fill:url(#nh-hatch); stroke:var(--ink); stroke-width:0.35; }
  svg .aud { fill:var(--paper); stroke:var(--ink); stroke-width:0.35; }
  svg .gap { fill:var(--paper); stroke:var(--ink); stroke-width:0.35; stroke-dasharray:0.6 0.5; }
  svg .grain { fill:url(#nh-dots); stroke:var(--ink); stroke-width:0.35; }
  svg .dot { fill:var(--ink); }
  svg .lbl { font-size:2.35px; }
  svg .lbl-s { font-size:2.05px; }
  svg .lbl-b { font-size:2.5px; font-family:"Routed Gothic",sans-serif; }
  svg .code { font-size:2.4px; font-family:"Routed Gothic",sans-serif; }
  svg .mono, svg .mono-t { font-family:"Letter Gothic","Courier",monospace; }
  svg .mono { font-size:2.0px; }

  .lower { display:grid; grid-template-columns:1fr 64mm; column-gap:6mm; margin-top:2.8mm; }
  .tcap { text-align:center; letter-spacing:0.07em; margin:0 0 0.8mm; }
  table { width:100%; border-collapse:collapse; font-size:7.3pt; line-height:1.2; }
  th, td { border:0.6pt solid var(--ink); padding:0.35mm 1.6mm; text-align:left; vertical-align:top; font-weight:400; }
  thead th { text-align:center; letter-spacing:0.1em; padding:0.5mm 1.6mm; }
  td.v { white-space:nowrap; }

  .notice { text-align:left; margin-bottom:1.8mm; }
  .notice .tag { display:block; text-align:center; letter-spacing:0.18em; font-weight:700; text-decoration:underline;
                 text-underline-offset:1.6pt; text-decoration-thickness:0.6pt; margin-bottom:0.8mm; }
  .notice p { margin:0; font-size:7.4pt; line-height:1.28; }

  .card { border:0.8pt solid var(--ink); font-family:var(--selectric); font-size:7.1pt; line-height:1.3; letter-spacing:0; }
  .card .bar { background:var(--ink); color:var(--paper); font-weight:700; padding:0.5mm 1.8mm; display:flex; justify-content:space-between; }
  .card ol { list-style:none; margin:0; padding:0.8mm 1.8mm 1mm; }
  .card li { display:grid; grid-template-columns:3.2mm 1fr; white-space:pre; }

  .tab { position:absolute; right:0; top:112mm; width:8.5mm; height:17mm; background:var(--ink); color:var(--paper);
         font-family:"Routed Gothic",sans-serif; font-size:8pt; letter-spacing:0.08em; display:flex; align-items:center; justify-content:center; }
"""

DEFS = """
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
  <marker id="nh-leader" viewBox="0 0 6 4" refX="5.6" refY="2" markerWidth="2.1" markerHeight="1.05" markerUnits="userSpaceOnUse" orient="auto" preserveAspectRatio="none"><path d="M0,0 L6,2 L0,4 Z" fill="#000"/></marker>
  <marker id="nh-arrow" viewBox="0 0 6 4" refX="5.6" refY="2" markerWidth="2.4" markerHeight="1.3" markerUnits="userSpaceOnUse" orient="auto" preserveAspectRatio="none"><path d="M0,0 L6,2 L0,4 Z" fill="#000"/></marker>
  <marker id="nh-dim" viewBox="0 0 6 4" refX="0" refY="2" markerWidth="2.2" markerHeight="0.95" markerUnits="userSpaceOnUse" orient="auto" preserveAspectRatio="none"><path d="M6,0 L0,2 L6,4 Z" fill="#000"/></marker>
  <pattern id="nh-hatch" width="1.1" height="1.1" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="1.1" stroke="#000" stroke-width="0.2"/></pattern>
  <pattern id="nh-bp" width="1.4" height="1.4" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><rect width="0.7" height="1.4" fill="#000"/></pattern>
  <pattern id="nh-dots" width="1.3" height="1.3" patternUnits="userSpaceOnUse"><circle cx="0.32" cy="0.32" r="0.15" fill="#000"/><circle cx="0.97" cy="0.97" r="0.15" fill="#000"/></pattern>
</defs></svg>
"""

FIT_CHECK = """
<script>
  document.fonts.ready.then(() => {
    const page = document.querySelector('.page')
    const foot = page.querySelector('.foot')
    let bottom = 0
    for (const el of page.children) {
      if (el === foot || el.classList.contains('tab')) continue
      bottom = Math.max(bottom, el.getBoundingClientRect().bottom)
    }
    const free = (foot.getBoundingClientRect().top - bottom) * 25.4 / 96
    document.documentElement.dataset.fit = free >= 0 ? `ok, ${free.toFixed(1)} mm free above the footer` : `OVERFLOW by ${(-free).toFixed(1)} mm`
  })
</script>
"""


def page(
    *,
    doc_no: str,
    part: str,
    tab: str,
    opener: str,
    body: str,
    foot_sub: str,
    page_id: str,
    change_date: str = "11 November 2026",
) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{doc_no} {PROGRAM}, page {page_id}</title>
<style>{CSS}</style></head>
<body>
{DEFS}
<div class="page">
  <header class="head">
    <div class="doc">{doc_no}</div>
    <div class="title">{PROGRAM}</div>
    <div class="part">{part}</div>
    <div class="rule"></div>
  </header>
  <div class="tab">{tab}</div>
  <div class="opener">{opener}</div>
  {body}
  <footer class="foot">
    <div class="rule"></div>
    <div class="sub">{foot_sub}</div>
    <div class="line">
      <span>Mission <span class="fill" style="width:20mm">&nbsp;</span></span>
      <span>Basic Date <span class="fill" style="width:34mm">{BASIC_DATE}</span></span>
      <span>Change Date <span class="fill" style="width:34mm">{change_date}</span></span>
      <span>Page <span class="fill" style="width:18mm">{page_id}</span></span>
    </div>
  </footer>
</div>
{FIT_CHECK}
</body></html>"""


def para(
    num: str, heading: str, text: str, changebar: bool = False, flush: bool = False
) -> str:
    bar = (
        '<div class="changebar" style="top:0.4mm; height:6.8mm"></div>'
        if changebar
        else ""
    )
    cls = ' class="flush"' if flush else ""
    htag = (
        "h3"
        if heading[0].islower()
        or ". " in heading[:40]
        and heading.split(".")[0][0].islower()
        else "h2"
    )
    return f'<section class="para">{bar}<div class="num">{num}</div><div><{htag}>{heading}</{htag}><p{cls}>{text}</p></div></section>'


def figure(svg: str, caption: str, code: str) -> str:
    return f'<figure>{svg}<figcaption><span class="n">{caption.split(".")[0]}.</span>{caption.split(".", 1)[1].strip()}</figcaption></figure>'


def lower(
    table_caption: str,
    table_rows: list[tuple[str, str]],
    notice: tuple[str, str] | None,
    card: tuple[str, list[str]] | None,
    table_num: str,
) -> str:
    rows = "".join(
        f'<tr><td>{k}</td><td class="v">{v}</td></tr>' for k, v in table_rows
    )
    left = (
        '<section class="para"><div class="num">2.x.3</div><div><h2>PERFORMANCE AND DESIGN DATA.</h2></div></section>'
        if False
        else ""
    )
    notice_html = ""
    if notice:
        notice_html = f'<div class="notice"><span class="tag">{notice[0]}</span><p>{notice[1]}</p></div>'
    card_html = ""
    if card:
        lis = "".join(
            f"<li><span>{i + 1}</span><span>{line}</span></li>"
            if not line.startswith("√")
            else f"<li><span></span><span>{line}</span></li>"
            for i, line in enumerate(card[1])
        )
        card_html = (
            f'<div class="card"><div class="bar"><span>{card[0]}</span><span>OPERATOR</span></div>'
            f"<ol>{lis}</ol></div>"
        )
    return (
        f'<div class="lower"><div><section class="para"><div class="num">x.3</div>'
        f"<div><h2>PERFORMANCE AND DESIGN DATA.</h2></div></section>"
        f'<div class="tcap">{table_num}. {table_caption}</div>'
        f"<table><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>{rows}</tbody></table>"
        f"</div><div>{notice_html}{card_html}</div></div>"
    )


def print_pdf(html_path: str) -> tuple[str, str]:
    """Render one sheet; returns (pdf_path, fit_line). Raises on overflow."""
    out = subprocess.run(
        ["sh", "/home/kara/.hermes/skills/nasa-handbook/scripts/render.sh", html_path],
        capture_output=True,
        text=True,
    )
    pdf = html_path.replace(".html", ".pdf")
    fit = ""
    for line in (out.stdout + out.stderr).splitlines():
        if line.startswith("fit:"):
            fit = line
    if "OVERFLOW" in fit:
        raise RuntimeError(f"{html_path}: {fit}")
    return pdf, fit
