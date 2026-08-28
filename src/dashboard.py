"""Generate the static dashboard (docs/index.html) from state, for GitHub Pages."""
import html
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

REPO = "gabjew90/Job-watcher"
FEEDBACK_BODY = ("Action: hide | more-like | less-like\n"
                 "Why: \n\n"
                 "(pick one action, say why — the reason steers future scoring; "
                 "'hide' also removes it from the dashboard on the next run)")

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
  tr.closed {{ opacity: .45; }}
  tr.closed td:first-child a {{ text-decoration: line-through; }}
  label {{ font-size: .85rem; margin-left: .8rem; user-select: none; }}
  a {{ color: inherit; }}
</style>
</head>
<body>
<h1>Job Watcher</h1>
<p class="meta">{active_count} active · {closed_count} closed · last refresh: <span id="upd" data-ts="{generated_iso}">{generated} UTC</span></p>
<input id="q" type="search" placeholder="Filter…" oninput="applyVis()"><label><input id="sc" type="checkbox" onchange="applyVis()"> show closed</label>
<div class="tablewrap">
<table id="t">
<thead><tr>
  <th onclick="sortBy(0)">Title</th><th onclick="sortBy(1)">Company</th>
  <th onclick="sortBy(2)">Location</th><th onclick="sortBy(3)">Mode</th>
  <th onclick="sortBy(4)">Pay</th><th onclick="sortBy(5)">Posted</th>
  <th onclick="sortBy(6)">First seen</th><th onclick="sortBy(7, true)">Score</th>
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
let dir = -1, col = 6;
function sortBy(c, numeric) {{
  dir = (c === col) ? -dir : (numeric ? -1 : 1); col = c;
  const tb = document.querySelector("#t tbody");
  [...tb.rows].sort((a, b) => {{
    const x = a.cells[c].innerText, y = b.cells[c].innerText;
    return numeric ? dir * ((parseFloat(x) || -1) - (parseFloat(y) || -1))
                   : dir * x.localeCompare(y);
  }}).forEach(r => tb.appendChild(r));
}}
function applyVis() {{
  const q = document.getElementById("q").value.toLowerCase();
  const showClosed = document.getElementById("sc").checked;
  for (const r of document.querySelectorAll("#t tbody tr")) {{
    const hideClosed = r.classList.contains("closed") && !showClosed;
    r.style.display = !hideClosed && r.innerText.toLowerCase().includes(q) ? "" : "none";
  }}
}}
function defaultSort() {{
  // Newest first by posted date (falling back to first-seen), score breaks ties.
  const tb = document.querySelector("#t tbody");
  [...tb.rows].sort((a, b) => {{
    const d = r => r.cells[5].innerText.trim() || r.cells[6].innerText.trim().slice(0, 10);
    const cmp = d(b).localeCompare(d(a));
    if (cmp) return cmp;
    return (parseFloat(b.cells[7].innerText) || -1) - (parseFloat(a.cells[7].innerText) || -1);
  }}).forEach(r => tb.appendChild(r));
  col = 5; dir = -1;
}}
defaultSort(); applyVis();
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
    classes = (["priority"] if rec.get("priority") else []) + (
        [] if rec.get("active", True) else ["closed"])
    cls = f' class="{" ".join(classes)}"' if classes else ""
    e = lambda s: html.escape(str(s or ""))
    score = rec.get("score")
    score_cell = f'<td title="{e(rec.get("rationale"))}">{score}</td>' if score is not None else "<td></td>"
    mode = {"onsite": "🏢 onsite", "hybrid": "🔀 hybrid", "remote": "🏠 remote"}.get(
        rec.get("work_mode", ""), "")
    first_seen = rec.get("first_seen", "")
    if not rec.get("active", True):
        first_seen += f' <small>(closed {rec.get("closed", "")})</small>'
    ref = quote(rec.get("title", "")[:80] + " @ " + rec.get("company", ""))
    fb_url = (f"https://github.com/{REPO}/issues/new?labels=feedback"
              f"&title={quote('feedback: ')}{ref}&body={quote(FEEDBACK_BODY)}")
    draft_url = (f"https://github.com/{REPO}/issues/new?labels=draft-request"
                 f"&title={quote('draft: ')}{ref}"
                 f"&body={quote('Requested from dashboard. Optional: add emphasis notes here.')}")
    return (
        f'<tr{cls}><td><a href="{e(rec.get("url"))}" target="_blank">{e(rec.get("title"))}</a>'
        f'<br><small>{e(rec.get("source"))} · <a href="{fb_url}" target="_blank">feedback</a>'
        f' · <a href="{draft_url}" target="_blank">✍️ draft</a></small></td>'
        f'<td>{e(rec.get("company"))}</td><td>{e(rec.get("location"))}</td>'
        f'<td>{mode}</td><td>{e(rec.get("pay"))}</td>'
        f'<td>{e(rec.get("date_posted"))}</td><td>{first_seen}</td>{score_cell}</tr>'
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


def _select_rows(state: dict, max_rows: int) -> tuple[list[dict], int, int]:
    """Top-N active by score, but everything from the last 7 days always
    shows; closed rows capped to the 100 most recent. State keeps the rest."""
    active = [r for r in state.values() if r.get("active", True)]
    closed = [r for r in state.values() if not r.get("active", True)]
    fresh_cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    fresh = [r for r in active if r.get("first_seen", "") >= fresh_cutoff]
    backlog = sorted((r for r in active if r.get("first_seen", "") < fresh_cutoff),
                     key=lambda r: -(r.get("score") or -1))
    shown = fresh + backlog[:max(0, max_rows - len(fresh))]
    closed_shown = sorted(closed, key=lambda r: str(r.get("closed", "")), reverse=True)[:100]
    return shown + closed_shown, len(active), len(closed)


def generate(state: dict, health_summary: list[dict] | None = None,
             max_rows: int = 500) -> None:
    selected, active, closed = _select_rows(state, max_rows)
    records = sorted(selected, key=lambda r: r.get("first_seen", ""), reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shown_active = sum(1 for r in records if r.get("active", True))
    now = datetime.now(timezone.utc)
    OUT.write_text(_PAGE.format(
        active_count=(f"top {shown_active} of {active}"
                      if shown_active < active else str(active)),
        closed_count=closed,
        generated=now.strftime("%Y-%m-%d %H:%M"),
        generated_iso=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        rows="\n".join(_row(r) for r in records),
        health_rows="\n".join(_health_row(s) for s in health_summary or []),
    ))
