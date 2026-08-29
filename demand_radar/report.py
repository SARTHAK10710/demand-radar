"""Report — render the run's findings for humans and for machines.

Four renderers off one result set:
  * console   — a scannable terminal summary
  * markdown  — a shareable report file
  * html      — a styled, self-contained page (the live-demo artifact)
  * json      — the full structured result for downstream use
"""

from __future__ import annotations

import html as _html
import json
import os
from typing import Any

from .config import Config
from .models import Lead, Segment

BAR = "█"


def _bar(score: float, width: int = 20) -> str:
    filled = int(round(score * width))
    return BAR * filled + "·" * (width - filled)


# ---------------------------------------------------------------- console ---
def render_console(config: Config, segments: list[Segment], leads: list[Lead],
                   meta: dict[str, Any]) -> str:
    L: list[str] = []
    L.append("")
    L.append("═" * 72)
    L.append(f"  DEMAND RADAR — {config.product}")
    L.append("═" * 72)
    L.append(f"  mode: {meta['mode']}   posts analysed: {meta['total_posts']}   "
             f"relevant: {meta['relevant_posts']}   unsegmented: {meta.get('unsegmented', 0)}   "
             f"sources: {len(config.sources)}")
    if meta["mode"] == "live":
        L.append(f"  model: {meta['model']}")
    L.append("")

    L.append("  CANDIDATE SEGMENTS (ranked)")
    L.append("  " + "-" * 68)
    L.append(f"  {'#':<2} {'segment':<16} {'vol':>4} {'score':>6}  "
             f"{'demand':<22} pay/look/browse")
    for seg in segments:
        ib = seg.intent_breakdown
        mix = f"{ib.get('paying',0)}/{ib.get('looking',0)}/{ib.get('browsing',0)}"
        L.append(f"  {seg.rank:<2} {seg.name[:16]:<16} {seg.volume:>4} "
                 f"{seg.total_score:>6.2f}  {_bar(seg.total_score)}  {mix}")
    L.append("")

    bh = segments[0] if segments else None
    if bh:
        L.append("  ★ RECOMMENDED BEACHHEAD: " + bh.name.upper())
        L.append("  " + "-" * 68)
        L.append(f"    volume {bh.volume}  |  intent {bh.intent_score:.2f}  |  "
                 f"competition {bh.competition:.2f}  |  score {bh.total_score:.2f}")
        if bh.top_pains:
            L.append("    top pains: " + ", ".join(f"{p} ({n})" for p, n in bh.top_pains[:4]))
        if bh.top_use_cases:
            L.append("    top use cases: " + ", ".join(f"{u} ({n})" for u, n in bh.top_use_cases[:4]))
        L.append("")

    if leads:
        L.append(f"  SCORED LEAD LIST — top {len(leads)} in {bh.name if bh else ''}")
        L.append("  " + "-" * 68)
        for i, lead in enumerate(leads, 1):
            L.append(f"  {i:>2}. [{lead.lead_score:.2f}] {lead.handle}  "
                     f"({lead.classified.intent})  {lead.classified.post.source}")
            L.append(f"      pain: {lead.classified.pain}")
            L.append(f"      “{lead.quote}”")
            L.append(f"      ✉ {lead.outreach}")
            L.append("")

    L.append("═" * 72)
    return "\n".join(L)


# --------------------------------------------------------------- markdown ---
def render_markdown(config: Config, segments: list[Segment], leads: list[Lead],
                    meta: dict[str, Any]) -> str:
    M: list[str] = []
    M.append(f"# Demand Radar — {config.product}\n")
    M.append(f"> Ran in **{meta['mode']}** mode over **{meta['total_posts']}** posts "
             f"(**{meta['relevant_posts']}** relevant, {meta.get('unsegmented', 0)} unsegmented) "
             f"from **{len(config.sources)}** sources"
             + (f", classified with `{meta['model']}`." if meta['mode'] == 'live' else ".")
             + f"  \n> _{meta['run_at']}_\n")

    bh = segments[0] if segments else None
    if bh:
        M.append(f"## ★ Recommended beachhead: **{bh.name}**\n")
        M.append(f"The strongest, least-contested demand sits with **{bh.name}** "
                 f"(score **{bh.total_score:.2f}**): {bh.volume} signals, "
                 f"intent {bh.intent_score:.2f}, competition {bh.competition:.2f}.\n")

    M.append("## Candidate segments (ranked)\n")
    M.append("| # | Segment | Volume | Paying | Looking | Browsing | Intent | Comp. | Score |")
    M.append("|--:|---------|-------:|-------:|--------:|---------:|-------:|------:|------:|")
    for s in segments:
        ib = s.intent_breakdown
        M.append(f"| {s.rank} | {s.name} | {s.volume} | {ib.get('paying',0)} | "
                 f"{ib.get('looking',0)} | {ib.get('browsing',0)} | {s.intent_score:.2f} | "
                 f"{s.competition:.2f} | **{s.total_score:.2f}** |")
    M.append("")

    if bh:
        M.append(f"## Inside the beachhead: {bh.name}\n")
        if bh.top_pains:
            M.append("**Top pains**\n")
            for p, n in bh.top_pains:
                M.append(f"- {p} — {n}")
            M.append("")
        if bh.top_use_cases:
            M.append("**Top use cases**\n")
            for u, n in bh.top_use_cases:
                M.append(f"- {u} — {n}")
            M.append("")

    if leads:
        M.append(f"## Scored lead list — top {len(leads)}\n")
        for i, lead in enumerate(leads, 1):
            M.append(f"### {i}. {lead.handle} · score {lead.lead_score:.2f} · "
                     f"{lead.classified.intent}\n")
            M.append(f"- **Source:** {lead.classified.post.source}"
                     + (f" — [link]({lead.classified.post.url})" if lead.classified.post.url else ""))
            M.append(f"- **Pain:** {lead.classified.pain}")
            M.append(f"- **In their words:** “{lead.quote}”")
            M.append(f"- **Drafted first message** _({lead.outreach_method})_:\n")
            M.append(f"  > {lead.outreach}\n")

    M.append("---\n")
    M.append("_I derived this ICP from real demand signals rather than asserting it: "
             "mined the sources, classified each signal, clustered into segments, sized "
             "each, and ranked to a beachhead — then drafted outreach for its top leads._")
    return "\n".join(M)


# ------------------------------------------------------------------- html ---
_HTML_CSS = """
:root{
  --bg:#eef1f5; --surface:#ffffff; --surface-2:#f6f8fb; --ink:#0f172a; --muted:#5b6675;
  --border:#e3e8ee; --accent:#16a34a; --accent-2:#22c55e; --accent-ink:#ffffff;
  --pay:#c2660c; --pay-bg:#fbeadb; --look:#2563eb; --look-bg:#e6edfd;
  --browse:#6b7280; --browse-bg:#eef1f4; --ring-track:#e3e8ee; --link:#1668d6;
  --shadow:0 1px 2px rgba(15,23,42,.05), 0 10px 30px rgba(15,23,42,.06);
  --verdict-bg:linear-gradient(135deg,#eafaf0,#ffffff); --verdict-border:#bfe9cd;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0b0f14; --surface:#141a22; --surface-2:#0f151c; --ink:#e6edf3; --muted:#93a1b1;
    --border:#232c37; --accent:#2ea043; --accent-2:#3fb950; --accent-ink:#04140a;
    --pay:#f0883e; --pay-bg:#3a230f; --look:#58a6ff; --look-bg:#132a45;
    --browse:#8b98a5; --browse-bg:#20262e; --ring-track:#232c37; --link:#58a6ff;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 12px 34px rgba(0,0,0,.35);
    --verdict-bg:linear-gradient(135deg,#10251a,#0f151c); --verdict-border:#1f6f3a;
  }
}
:root[data-theme="dark"]{
  --bg:#0b0f14; --surface:#141a22; --surface-2:#0f151c; --ink:#e6edf3; --muted:#93a1b1;
  --border:#232c37; --accent:#2ea043; --accent-2:#3fb950; --accent-ink:#04140a;
  --pay:#f0883e; --pay-bg:#3a230f; --look:#58a6ff; --look-bg:#132a45;
  --browse:#8b98a5; --browse-bg:#20262e; --ring-track:#232c37; --link:#58a6ff;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 12px 34px rgba(0,0,0,.35);
  --verdict-bg:linear-gradient(135deg,#10251a,#0f151c); --verdict-border:#1f6f3a;
}
*{box-sizing:border-box;}
body{margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;}
.wrap{max-width:1040px; margin:0 auto; padding:28px 22px 72px;}
.top{display:flex; align-items:center; justify-content:space-between; margin-bottom:26px;}
.brand{font-weight:800; letter-spacing:-.01em; display:flex; align-items:center; gap:9px;}
.brand-sub{color:var(--muted); font-weight:600;}
.dot{width:11px; height:11px; border-radius:50%; background:var(--accent);}
.toggle{background:var(--surface); color:var(--ink); border:1px solid var(--border);
  border-radius:999px; padding:7px 13px; font:inherit; font-size:13px; font-weight:600;
  cursor:pointer; box-shadow:var(--shadow);}
.toggle:hover{border-color:var(--accent);}
h1{font-size:32px; line-height:1.15; letter-spacing:-.02em; margin:0 0 6px;}
.lede{color:var(--muted); margin:0 0 16px; font-size:16px;}
.meta{display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px;}
.chip{background:var(--surface); border:1px solid var(--border); border-radius:999px;
  padding:4px 11px; font-size:12.5px; color:var(--muted);}
.chip b{color:var(--ink); font-weight:700;}
.chip.ts{margin-left:auto;}
h3{font-size:12.5px; letter-spacing:.09em; text-transform:uppercase; color:var(--muted);
  margin:36px 0 13px; display:flex; align-items:center; gap:9px;}
h3 i{width:16px; height:2px; background:var(--accent); border-radius:2px; display:inline-block;}
.cap{text-transform:capitalize;}
.verdict{display:flex; gap:22px; align-items:center; background:var(--verdict-bg);
  border:1px solid var(--verdict-border); border-radius:18px; padding:22px 24px;
  margin:26px 0 6px; box-shadow:var(--shadow);}
.ring{position:relative; width:92px; height:92px; border-radius:50%; flex:none;
  background:conic-gradient(var(--accent) calc(var(--p)*1%), var(--ring-track) 0);
  display:grid; place-items:center;}
.ring::before{content:""; position:absolute; inset:10px; border-radius:50%; background:var(--surface);}
.ring span{position:relative; font-weight:800; font-size:22px; letter-spacing:-.02em;}
.verdict-body{min-width:0;}
.verdict .label{color:var(--accent); font-weight:800; font-size:11.5px;
  letter-spacing:.08em; text-transform:uppercase;}
.verdict h2{margin:4px 0 4px; font-size:27px; text-transform:capitalize; letter-spacing:-.01em;}
.verdict p{margin:0 0 12px; color:var(--muted);}
.stats{display:flex; gap:10px; flex-wrap:wrap;}
.stat{background:var(--surface); border:1px solid var(--border); border-radius:12px;
  padding:8px 13px; display:flex; flex-direction:column; min-width:96px;}
.stat .k{font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.05em;}
.stat .v{font-size:19px; font-weight:800; letter-spacing:-.01em;}
.table-wrap{overflow-x:auto; border-radius:14px; box-shadow:var(--shadow);}
table{width:100%; border-collapse:collapse; background:var(--surface);
  border:1px solid var(--border); border-radius:14px; overflow:hidden; min-width:560px;}
th,td{text-align:left; padding:13px 15px; border-bottom:1px solid var(--border);}
th{font-size:11px; letter-spacing:.05em; text-transform:uppercase; color:var(--muted);
  background:var(--surface-2);}
tbody tr:last-child td{border-bottom:none;}
tbody tr:hover{background:var(--surface-2);}
.segrow.winner{background:var(--surface-2); background:color-mix(in srgb, var(--accent) 9%, var(--surface));}
.rank{width:44px;}
.rankbadge{display:inline-grid; place-items:center; width:24px; height:24px; border-radius:8px;
  background:var(--surface-2); border:1px solid var(--border); font-size:12px; font-weight:700;
  color:var(--muted);}
.segrow.winner .rankbadge{background:var(--accent); color:var(--accent-ink); border-color:var(--accent);}
.segname{font-weight:700; text-transform:capitalize; white-space:nowrap;}
.star{color:var(--accent); margin-left:6px;}
.num{font-variant-numeric:tabular-nums;}
.scorecell{min-width:190px;}
.track{position:relative; background:var(--surface-2); border:1px solid var(--border);
  border-radius:999px; height:9px; overflow:hidden;}
.fill{position:absolute; inset:0 auto 0 0; border-radius:999px;
  background:linear-gradient(90deg, var(--accent), var(--accent-2));}
.scorelabel{font-size:12.5px; font-weight:700; font-variant-numeric:tabular-nums;
  display:inline-block; margin-top:4px;}
.pill{display:inline-block; min-width:26px; text-align:center; padding:2px 8px; border-radius:999px;
  font-size:12px; font-weight:700; font-variant-numeric:tabular-nums;}
.pill.pay{color:var(--pay); background:var(--pay-bg);}
.pill.look{color:var(--look); background:var(--look-bg);}
.pill.browse{color:var(--browse); background:var(--browse-bg);}
.cols{display:grid; grid-template-columns:1fr 1fr; gap:14px;}
.card{background:var(--surface); border:1px solid var(--border); border-radius:14px;
  padding:16px 18px; box-shadow:var(--shadow);}
.card-h{font-weight:700; margin-bottom:8px;}
.card ul{list-style:none; margin:0; padding:0;}
.card li{display:flex; justify-content:space-between; gap:12px; padding:7px 0;
  border-bottom:1px dashed var(--border); text-transform:capitalize;}
.card li:last-child{border-bottom:none;}
.cnt{color:var(--muted); font-variant-numeric:tabular-nums; font-weight:700;}
.lead{background:var(--surface); border:1px solid var(--border); border-radius:14px;
  padding:16px 18px; margin-bottom:12px; box-shadow:var(--shadow);}
.lead-head{display:flex; align-items:center; gap:10px; flex-wrap:wrap; font-size:13px;}
.avatar{width:28px; height:28px; border-radius:50%; display:grid; place-items:center;
  background:var(--surface-2); background:color-mix(in srgb, var(--accent) 16%, var(--surface));
  color:var(--accent); font-weight:800; font-size:13px; border:1px solid var(--border);}
.lead-author{font-weight:800;}
.lead-score{color:var(--muted);}
.lead-src{margin-left:auto;}
.lead-src a{color:var(--link); text-decoration:none; font-weight:600;}
.lead-src a:hover{text-decoration:underline;}
.badge{font-size:10.5px; padding:2px 9px; border-radius:999px; font-weight:800;
  text-transform:uppercase; letter-spacing:.04em;}
.intent-paying{color:var(--pay); background:var(--pay-bg);}
.intent-looking{color:var(--look); background:var(--look-bg);}
.intent-browsing{color:var(--browse); background:var(--browse-bg);}
.lead-pain{margin:11px 0 8px; color:var(--ink);}
.tag{font-size:10.5px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted);
  border:1px solid var(--border); border-radius:6px; padding:1px 6px; margin-right:4px;}
blockquote{margin:0 0 11px; padding:8px 14px; border-left:3px solid var(--border);
  color:var(--muted); font-style:italic;}
.outreach{background:var(--surface-2); border:1px solid var(--border); border-radius:10px;
  padding:11px 13px;}
.outreach-top{display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted);
  margin-bottom:6px;}
.outreach-top .ico{color:var(--accent);}
.method{text-transform:uppercase; font-size:10.5px; letter-spacing:.04em;}
.copy{margin-left:auto; background:var(--surface); color:var(--ink); border:1px solid var(--border);
  border-radius:7px; padding:3px 10px; font:inherit; font-size:12px; font-weight:600; cursor:pointer;}
.copy:hover{border-color:var(--accent);}
.copy.ok{color:var(--accent-ink); background:var(--accent); border-color:var(--accent);}
.msg{color:var(--ink);}
.muted{color:var(--muted);}
footer{margin-top:44px; border-top:1px solid var(--border); padding-top:20px; color:var(--muted);}
.stepper{display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-size:12px;
  text-transform:uppercase; letter-spacing:.05em; margin-bottom:12px;}
.stepper span{background:var(--surface); border:1px solid var(--border); border-radius:999px;
  padding:4px 11px; font-weight:700; color:var(--ink);}
.stepper b{color:var(--accent);}
footer p{margin:0; font-size:13.5px; font-style:italic;}
@media (max-width:720px){
  .cols{grid-template-columns:1fr;}
  h1{font-size:26px;}
  .verdict{flex-direction:column; align-items:flex-start;}
  .chip.ts{margin-left:0;}
}
"""

_HTML_JS = """
(function(){
  var root=document.documentElement;
  function prefDark(){ return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; }
  function current(){ return root.getAttribute('data-theme') || (prefDark()?'dark':'light'); }
  function label(t){ return t==='dark' ? '\\u2600 Light' : '\\u263e Dark'; }
  function apply(t){ root.setAttribute('data-theme',t); try{ localStorage.setItem('dr-theme',t); }catch(e){}
    var b=document.getElementById('themebtn'); if(b) b.textContent=label(t); }
  try{ var saved=localStorage.getItem('dr-theme'); if(saved) root.setAttribute('data-theme',saved); }catch(e){}
  var btn=document.getElementById('themebtn');
  if(btn){ btn.textContent=label(current());
    btn.addEventListener('click', function(){ apply(current()==='dark'?'light':'dark'); }); }
  document.querySelectorAll('.copy').forEach(function(b){
    b.addEventListener('click', function(){
      var box=b.closest('.outreach'); var msg=box ? box.querySelector('.msg').textContent : '';
      function done(){ var o=b.textContent; b.textContent='Copied'; b.classList.add('ok');
        setTimeout(function(){ b.textContent=o; b.classList.remove('ok'); },1200); }
      if(navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(msg).then(done, done); }
      else { done(); }
    });
  });
})();
"""


def _initial(name: str) -> str:
    for ch in name:
        if ch.isalnum():
            return ch.upper()
    return "?"


def render_html(config: Config, segments: list[Segment], leads: list[Lead],
                meta: dict[str, Any]) -> str:
    e = _html.escape
    bh = segments[0] if segments else None

    seg_rows = []
    for s in segments:
        ib = s.intent_breakdown
        pct = int(round(s.total_score * 100))
        winner = " winner" if s.rank == 1 else ""
        star = '<span class="star">★</span>' if s.rank == 1 else ""
        seg_rows.append(f"""
      <tr class="segrow{winner}">
        <td class="rank"><span class="rankbadge">{s.rank}</span></td>
        <td class="segname">{e(s.name)}{star}</td>
        <td class="num">{s.volume}</td>
        <td class="scorecell">
          <div class="track"><div class="fill" style="width:{pct}%"></div></div>
          <span class="scorelabel">{s.total_score:.2f}</span>
        </td>
        <td class="mix">
          <span class="pill pay" title="paying">{ib.get('paying',0)}</span>
          <span class="pill look" title="looking">{ib.get('looking',0)}</span>
          <span class="pill browse" title="browsing">{ib.get('browsing',0)}</span>
        </td>
        <td class="num">{s.competition:.2f}</td>
      </tr>""")

    lead_cards = []
    for i, lead in enumerate(leads, 1):
        src = e(lead.classified.post.source)
        link = (f'<a href="{e(lead.classified.post.url)}" target="_blank" rel="noopener">{src} ↗</a>'
                if lead.classified.post.url else src)
        lead_cards.append(f"""
      <div class="lead">
        <div class="lead-head">
          <span class="avatar">{e(_initial(lead.author))}</span>
          <span class="lead-author">{e(lead.handle)}</span>
          <span class="badge intent-{e(lead.classified.intent)}">{e(lead.classified.intent)}</span>
          <span class="lead-score">score {lead.lead_score:.2f}</span>
          <span class="lead-src">{link}</span>
        </div>
        <div class="lead-pain"><span class="tag">pain</span> {e(lead.classified.pain)}</div>
        <blockquote>{e(lead.quote)}</blockquote>
        <div class="outreach">
          <div class="outreach-top"><span class="ico">✉</span> Drafted first message
            <span class="method">{e(lead.outreach_method)}</span>
            <button class="copy" type="button">Copy</button></div>
          <div class="msg">{e(lead.outreach)}</div>
        </div>
      </div>""")

    pains = "".join(f"<li><span>{e(p)}</span><span class='cnt'>{n}</span></li>"
                    for p, n in (bh.top_pains if bh else []))
    usecases = "".join(f"<li><span>{e(u)}</span><span class='cnt'>{n}</span></li>"
                       for u, n in (bh.top_use_cases if bh else []))

    model_chip = (f'<span class="chip">model <b>{e(meta["model"])}</b></span>'
                  if meta["mode"] == "live" else "")

    verdict_html = ""
    if bh:
        bh_pct = int(round(bh.total_score * 100))
        verdict_html = f"""
  <section class="verdict">
    <div class="ring" style="--p:{bh_pct}"><span>{bh.total_score:.2f}</span></div>
    <div class="verdict-body">
      <div class="label">★ Recommended beachhead</div>
      <h2>{e(bh.name)}</h2>
      <p>The strongest, least-contested demand sits here — start with <b>{e(bh.name)}</b>.</p>
      <div class="stats">
        <div class="stat"><span class="k">signals</span><span class="v">{bh.volume}</span></div>
        <div class="stat"><span class="k">already paying</span><span class="v">{bh.intent_breakdown.get('paying',0)}</span></div>
        <div class="stat"><span class="k">intent</span><span class="v">{bh.intent_score:.2f}</span></div>
        <div class="stat"><span class="k">competition</span><span class="v">{bh.competition:.2f}</span></div>
      </div>
    </div>
  </section>"""

    beachhead_detail = ""
    if bh:
        beachhead_detail = f"""
  <h3><i></i>Inside the beachhead — <span class="cap">{e(bh.name)}</span></h3>
  <div class="cols">
    <div class="card"><div class="card-h">Top pains</div><ul>{pains}</ul></div>
    <div class="card"><div class="card-h">Top use cases</div><ul>{usecases}</ul></div>
  </div>"""

    leads_html = ("".join(lead_cards) if lead_cards
                  else "<p class='muted'>No leads produced.</p>")
    leads_title = f" — top {len(leads)}" if leads else ""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Demand Radar — {e(config.name)}</title>
<style>{_HTML_CSS}</style></head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand"><span class="dot"></span> Demand Radar <span class="brand-sub">· derived ICP</span></div>
    <button id="themebtn" class="toggle" type="button">☾ Dark</button>
  </header>

  <h1>{e(config.product)}</h1>
  <p class="lede">Candidate segments mined from real demand, sized and ranked to a beachhead.</p>
  <div class="meta">
    <span class="chip">mode <b>{e(meta['mode'])}</b></span>
    <span class="chip">posts <b>{meta['total_posts']}</b></span>
    <span class="chip">relevant <b>{meta['relevant_posts']}</b></span>
    <span class="chip">unsegmented <b>{meta.get('unsegmented', 0)}</b></span>
    <span class="chip">sources <b>{len(config.sources)}</b></span>
    {model_chip}
    <span class="chip ts">{e(meta['run_at'])}</span>
  </div>
{verdict_html}
  <h3><i></i>Candidate segments (ranked)</h3>
  <div class="table-wrap">
  <table>
    <thead><tr><th>#</th><th>Segment</th><th>Vol</th><th>Composite score</th>
      <th>pay · look · browse</th><th>Comp.</th></tr></thead>
    <tbody>{''.join(seg_rows)}</tbody>
  </table>
  </div>
{beachhead_detail}
  <h3><i></i>Scored lead list{leads_title}</h3>
  {leads_html}

  <footer>
    <div class="stepper">
      <span>ingest</span><b>→</b><span>classify</span><b>→</b><span>cluster</span><b>→</b>
      <span>size</span><b>→</b><span>rank</span><b>→</b><span>outreach</span>
    </div>
    <p>ICP <b>derived</b> from real demand signals rather than asserted — mined the sources,
      classified each signal, clustered into segments, sized each, ranked to a beachhead,
      and drafted outreach for its top leads.</p>
  </footer>
</div>
<script>{_HTML_JS}</script>
</body></html>"""


# ------------------------------------------------------------- write all ---
def write_outputs(outdir: str, config: Config, segments: list[Segment],
                  leads: list[Lead], meta: dict[str, Any]) -> dict[str, str]:
    os.makedirs(outdir, exist_ok=True)
    slug = config.name or "run"
    paths = {
        "markdown": os.path.join(outdir, f"{slug}_report.md"),
        "html": os.path.join(outdir, f"{slug}_report.html"),
        "json": os.path.join(outdir, f"{slug}_results.json"),
    }
    with open(paths["markdown"], "w", encoding="utf-8") as f:
        f.write(render_markdown(config, segments, leads, meta))
    with open(paths["html"], "w", encoding="utf-8") as f:
        f.write(render_html(config, segments, leads, meta))
    with open(paths["json"], "w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": meta,
                "product": config.product,
                "segments": [s.to_dict() for s in segments],
                "leads": [l.to_dict() for l in leads],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    return paths
