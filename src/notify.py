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


def _esc(text: str, limit: int = 0) -> str:
    text = (text or "").replace("|", "\\|").replace("\n", " ").strip()
    return text[:limit] + "…" if limit and len(text) > limit else text


def build_digest(new_jobs: list[Job], scores: dict[str, dict], drafts: list[Path],
                 health_summary: list[dict] | None = None,
                 closed_recs: list[dict] | None = None) -> str:
    def sort_key(j: Job):
        return (-(scores.get(j.job_id, {}).get("score", -1)), not j.priority)

    lines = []
    if drafts:
        repo = os.environ.get("GITHUB_REPOSITORY", "gabjew90/Job-watcher")
        branch = os.environ.get("GITHUB_REF_NAME", "claude/brainstorm-approach-8qukjx")
        lines.append("## 📄 Resume drafts ready\n")
        lines += [f"- [{p.name}](https://github.com/{repo}/blob/{branch}/{p})"
                  for p in drafts]
        lines.append("")
    if new_jobs:
        lines.append("| Score | Role | Company | Location | Mode | Pay | Posted |")
        lines.append("|--:|---|---|---|---|---|---|")
        for j in sorted(new_jobs, key=sort_key):
            s = scores.get(j.job_id)
            score = f"**{s['score']}**" if s else "–"
            star = " ⭐" if j.priority else ""
            rationale = (f"<br><sub>{_esc(s['rationale'], 160)}</sub>"
                         if s and s.get("rationale") else "")
            lines.append(
                f"| {score}{star} | [{_esc(j.title, 70)}]({j.url}){rationale} "
                f"| {_esc(j.company)} | {_esc(j.location, 40)} "
                f"| {j.work_mode} | {_esc(j.pay, 45)} | {j.date_posted} |")
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
               closed_recs: list[dict] | None = None) -> None:
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
    body = build_digest(new_jobs, scores, drafts, health_summary, closed_recs)

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
