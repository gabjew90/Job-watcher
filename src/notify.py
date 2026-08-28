"""Notification: post the day's new postings as a GitHub Issue.

Uses the workflow's own GITHUB_TOKEN — no extra secrets. Locally (no token)
the digest is just printed.
"""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from .models import Job

log = logging.getLogger(__name__)


AGGREGATOR_SOURCES = {"indeed", "glassdoor", "zip_recruiter", "google"}


def coverage_suggestions(seen: dict, config: dict) -> list[str]:
    """Companies whose postings score >=70 but reach us only via aggregators
    — candidates for a direct board. Suggested once, the day the company
    first crosses the bar."""
    from datetime import datetime, timezone
    from .util import company_key
    direct = {company_key(e.get("company", ""))
              for key in ("ats_boards", "workday_boards", "successfactors_boards")
              for e in config.get(key, [])}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    by_company: dict[str, list[dict]] = {}
    for r in seen.values():
        if r.get("active", True) and r.get("company"):
            by_company.setdefault(r["company"], []).append(r)
    out = []
    for company, recs in by_company.items():
        if company_key(company) in direct:
            continue
        if not all(r.get("source") in AGGREGATOR_SOURCES for r in recs):
            continue
        best = max(recs, key=lambda r: r.get("score") or 0)
        if (best.get("score") or 0) >= 70 and best.get("first_seen") == today:
            out.append(f"**{company}** (top {best['score']}: "
                       f"{_esc(best.get('title', ''), 55)})")
    return out[:6]


def _esc(text: str, limit: int = 0) -> str:
    text = (text or "").replace("|", "\\|").replace("\n", " ").strip()
    return text[:limit] + "…" if limit and len(text) > limit else text


def build_digest(new_jobs: list[Job], scores: dict[str, dict], drafts: list[Path],
                 health_summary: list[dict] | None = None,
                 closed_recs: list[dict] | None = None,
                 digest_floor: int = 40,
                 suggestions: list[str] | None = None,
                 audit_recs: list[dict] | None = None) -> str:
    def sort_key(j: Job):
        # Band desc, priority flag, posted date desc — deterministic
        # within-band ordering, no sub-band precision implied.
        return (-(scores.get(j.job_id, {}).get("score", -1)), not j.priority,
                _rev_date(j.date_posted))

    def _rev_date(d: str) -> str:
        return "".join(chr(255 - ord(c)) for c in (d or "0000-00-00"))

    lines = []
    if drafts:
        repo = os.environ.get("GITHUB_REPOSITORY", "gabjew90/Job-watcher")
        branch = os.environ.get("GITHUB_REF_NAME", "claude/brainstorm-approach-8qukjx")
        lines.append("## 📄 Resume drafts ready\n")
        lines += [f"- [{p.name}](https://github.com/{repo}/blob/{branch}/{p})"
                  for p in drafts]
        lines.append("")
    # Digest floor: don't itemize clear misfits, just count them.
    visible = [j for j in new_jobs
               if scores.get(j.job_id) is None
               or scores[j.job_id]["score"] >= digest_floor]
    omitted = len(new_jobs) - len(visible)
    if visible:
        lines.append("| Fit | Role | Company | Location | Mode | Pay | Posted |")
        lines.append("|--:|---|---|---|---|---|---|")
        for j in sorted(visible, key=sort_key):
            s = scores.get(j.job_id)
            score = f"**{s.get('band') or s['score']}**" if s else "–"
            star = " ⭐" if j.priority else ""
            rationale = (f"<br><sub>{_esc(s['rationale'], 160)}</sub>"
                         if s and s.get("rationale") else "")
            lines.append(
                f"| {score}{star} | [{_esc(j.title, 70)}]({j.url}){rationale} "
                f"| {_esc(j.company)} | {_esc(j.location, 40)} "
                f"| {j.work_mode} | {_esc(j.pay, 45)} | {j.date_posted} |")
    if omitted:
        lines.append(f"\n_{omitted} low-fit posting{'s' if omitted != 1 else ''} "
                     f"(score < {digest_floor}) omitted; clear misfits are "
                     f"auto-archived._")
    if not scores and new_jobs:
        lines.append("\n_Unscored run (triage unavailable)._")
    if closed_recs:
        lines.append("\n## 🚫 Closed since last run\n")
        by_score = sorted(closed_recs, key=lambda r: -(r.get("score") or -1))
        for r in by_score[:30]:
            score = f"{r['score']} · " if r.get("score") is not None else ""
            lines.append(f"- ~~{_esc(r.get('title', ''), 70)}~~ — {_esc(r.get('company', ''))} ({score}first seen {r.get('first_seen', '?')})")
        if len(closed_recs) > 30:
            lines.append(f"- …and {len(closed_recs) - 30} more")
    if audit_recs:
        lines.append("\n## 🧪 Weekly archive audit\n")
        lines.append("Random sample of auto-archived postings — check any the "
                     "filter got WRONG and file feedback on them:")
        for r in audit_recs:
            lines.append(f"- [ ] {r.get('band', r.get('score', '?'))}: "
                         f"[{_esc(r.get('title', ''), 60)}]({r.get('url', '')}) — "
                         f"{_esc(r.get('company', ''))}"
                         f"<br><sub>{_esc(r.get('rationale', ''), 140)}</sub>")
    if suggestions:
        lines.append("\n## 🔭 Coverage suggestions\n")
        lines.append("High scorers from companies we only see via aggregators "
                     "— name one in chat to get its direct board probed:")
        lines += [f"- {s}" for s in suggestions]
    unhealthy = [s for s in health_summary or [] if s["status"] != "ok"]
    if unhealthy:
        lines.append("\n## ⚠️ Source issues\n")
        for s in unhealthy:
            detail = s["error"] or "returned 0 results"
            lines.append(f"- `{s['source']}`: {s['status']} ({detail[:120]}) — "
                         f"last results {s['last_results'] or 'never'}")
    lines.append("\n---\n_Dashboard: see the GitHub Pages site for full history._")
    return "\n".join(lines)




def post_issue(new_jobs: list[Job], scores: dict[str, dict] | None = None,
               drafts: list[Path] | None = None,
               health_summary: list[dict] | None = None,
               closed_recs: list[dict] | None = None,
               digest_floor: int = 40,
               suggestions: list[str] | None = None,
               audit_recs: list[dict] | None = None) -> None:
    scores = scores or {}
    drafts = drafts or []
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"Job watch {date}: {len(new_jobs)} new posting{'s' if len(new_jobs) != 1 else ''}"
    if scores:
        top = max(scores.values(), key=lambda s: s["score"])
        title += f" (top score {top['score']})"
    if closed_recs:
        title += f", {len(closed_recs)} closed"
    body = build_digest(new_jobs, scores, drafts, health_summary, closed_recs,
                        digest_floor, suggestions, audit_recs)

    if not token or not repo:
        log.info("No GITHUB_TOKEN/GITHUB_REPOSITORY; printing digest instead.\n\n%s\n%s", title, body)
        return

    resp = requests.post(
        f"https://api.github.com/repos/{repo}/issues",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={"title": title, "body": body, "labels": ["job-digest"]},
        timeout=30,
    )
    if resp.status_code == 201:
        log.info("Posted digest issue: %s", resp.json().get("html_url"))
    else:
        log.warning("Failed to post issue (%s): %s", resp.status_code, resp.text[:500])
