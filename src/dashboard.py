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
<p class="meta">{count} postings tracked · generated {generated} UTC</p>
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


def generate(state: dict) -> None:
    records = sorted(state.values(), key=lambda r: r.get("first_seen", ""), reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(_PAGE.format(
        count=len(records),
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        rows="\n".join(_row(r) for r in records),
    ))
