"""Generate the static dashboard (docs/index.html) from state, for GitHub Pages."""
import html
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("docs/index.html")

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Watcher</title>
<style>
  :root {{ color-scheme: light dark; --border: #8884; }}
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 72rem; padding: 0 1rem; }}
  h1 {{ font-size: 1.4rem; }} .meta {{ opacity: .7; font-size: .85rem; }}
  input {{ padding: .4rem .6rem; margin: .8rem 0; width: 16rem; max-width: 100%; }}
  .tablewrap {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: .45rem .6rem; border-bottom: 1px solid var(--border); }}
  th {{ cursor: pointer; white-space: nowrap; user-select: none; }}
  tr.priority td:first-child::before {{ content: "⭐ "; }}
  a {{ color: inherit; }}
</style>
</head>
<body>
<h1>Job Watcher</h1>
<p class="meta">{count} postings tracked · last refresh: <span id="upd" data-ts="{generated_iso}">{generated} UTC</span></p>
<input id="q" type="search" placeholder="Filter…" oninput="filt()">
<div class="tablewrap">
<table id="t">
<thead><tr>
  <th onclick="sortBy(0)">Title</th><th onclick="sortBy(1)">Company</th>
  <th onclick="sortBy(2)">Location</th><th onclick="sortBy(3)">Source</th>
  <th onclick="sortBy(4)">First seen</th><th onclick="sortBy(5, true)">Score</th>
</tr></thead>
<tbody>
{rows}
</tbody>
</table>
</div>
<h2 style="font-size:1.1rem;margin-top:2rem">Source health</h2>
<div class="tablewrap">
<table>
<thead><tr><th>Source</th><th>Status</th><th>Results</th><th>Last results</th><th>Error</th></tr></thead>
<tbody>
{health_rows}
</tbody>
</table>
</div>
<script>
let dir = -1, col = 4;
function sortBy(c, numeric) {{
  dir = (c === col) ? -dir : (numeric ? -1 : 1); col = c;
  const tb = document.querySelector("#t tbody");
  [...tb.rows].sort((a, b) => {{
    const x = a.cells[c].innerText, y = b.cells[c].innerText;
    return numeric ? dir * ((parseFloat(x) || -1) - (parseFloat(y) || -1))
                   : dir * x.localeCompare(y);
  }}).forEach(r => tb.appendChild(r));
}}
function filt() {{
  const q = document.getElementById("q").value.toLowerCase();
  for (const r of document.querySelectorAll("#t tbody tr"))
    r.style.display = r.innerText.toLowerCase().includes(q) ? "" : "none";
}}
sortBy(4); dir = -1; sortBy(4);
function ago() {{
  const el = document.getElementById("upd");
  const ts = new Date(el.dataset.ts);
  const mins = Math.max(0, Math.round((Date.now() - ts) / 60000));
  const rel = mins < 1 ? "just now" : mins < 60 ? `${{mins}} min ago`
    : mins < 2880 ? `${{Math.round(mins / 60)}} h ago` : `${{Math.round(mins / 1440)}} days ago`;
  el.textContent = ts.toLocaleString(undefined, {{dateStyle: "medium", timeStyle: "short"}}) + ` (${{rel}})`;
  el.style.color = mins > 2160 ? "#d33" : "";  // red if stale >36h — a daily run was missed
}}
ago(); setInterval(ago, 30000);
</script>
</body>
</html>
"""


def _row(rec: dict) -> str:
    cls = ' class="priority"' if rec.get("priority") else ""
    e = lambda s: html.escape(str(s or ""))
    score = rec.get("score")
    score_cell = f'<td title="{e(rec.get("rationale"))}">{score}</td>' if score is not None else "<td></td>"
    return (
        f'<tr{cls}><td><a href="{e(rec.get("url"))}" target="_blank">{e(rec.get("title"))}</a></td>'
        f'<td>{e(rec.get("company"))}</td><td>{e(rec.get("location"))}</td>'
        f'<td>{e(rec.get("source"))}</td><td>{e(rec.get("first_seen"))}</td>{score_cell}</tr>'
    )


_STATUS_ICON = {"ok": "✅", "empty": "⚠️", "failed": "❌"}


def _health_row(s: dict) -> str:
    e = lambda v: html.escape(str(v or ""))
    return (
        f'<tr><td>{e(s["source"])}</td>'
        f'<td>{_STATUS_ICON.get(s["status"], "?")} {e(s["status"])}</td>'
        f'<td>{s["count"]}</td><td>{e(s["last_results"] or "never")}</td>'
        f'<td>{e(s["error"])}</td></tr>'
    )


def generate(state: dict, health_summary: list[dict] | None = None) -> None:
    records = sorted(state.values(), key=lambda r: r.get("first_seen", ""), reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    OUT.write_text(_PAGE.format(
        count=len(records),
        generated=now.strftime("%Y-%m-%d %H:%M"),
        generated_iso=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        rows="\n".join(_row(r) for r in records),
        health_rows="\n".join(_health_row(s) for s in health_summary or []),
    ))
