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


def build_digest(new_jobs: list[Job], scores: dict[str, dict], drafts: list[Path],
                 health_summary: list[dict] | None = None) -> str:
    def sort_key(j: Job):
        return -(scores.get(j.job_id, {}).get("score", -1))

    starred = sorted([j for j in new_jobs if j.priority], key=sort_key)
    rest = sorted([j for j in new_jobs if not j.priority], key=sort_key)
    lines = []
    if drafts:
        lines.append("## 📄 Resume drafts ready\n")
        lines += [f"- `{p}`" for p in drafts]
        lines.append("")
    if starred:
        lines.append("## ⭐ Priority topics\n")
        lines += [_line(j, scores) for j in starred]
        lines.append("")
    if rest:
        lines.append("## New postings\n")
        lines += [_line(j, scores) for j in rest]
    if not scores and new_jobs:
        lines.append("\n_Unscored run (triage unavailable)._")
    unhealthy = [s for s in health_summary or [] if s["status"] != "ok"]
    if unhealthy:
        lines.append("\n## ⚠️ Source issues\n")
        for s in unhealthy:
            detail = s["error"] or "returned 0 results"
            lines.append(f"- `{s['source']}`: {s['status']} ({detail[:120]}) — "
                         f"last results {s['last_results'] or 'never'}")
    lines.append("\n---\n_Dashboard: see the GitHub Pages site for full history._")
    return "\n".join(lines)


def _line(job: Job, scores: dict[str, dict]) -> str:
    s = scores.get(job.job_id)
    prefix = f"**{s['score']}** · " if s else ""
    extras = "".join(
        f" · {x}" for x in (job.work_mode, job.pay and f"💰 {job.pay}",
                            job.date_posted and f"posted {job.date_posted}") if x)
    line = (f"- {prefix}[{job.title}]({job.url}) — **{job.company}** · "
            f"{job.location} · _{job.source}_{extras}")
    if s and s.get("rationale"):
        line += f"\n  - {s['rationale']}"
    return line


def post_issue(new_jobs: list[Job], scores: dict[str, dict] | None = None,
               drafts: list[Path] | None = None,
               health_summary: list[dict] | None = None) -> None:
    scores = scores or {}
    drafts = drafts or []
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"Job watch {date}: {len(new_jobs)} new posting{'s' if len(new_jobs) != 1 else ''}"
    if scores:
        top = max(scores.values(), key=lambda s: s["score"])
        title += f" (top score {top['score']})"
    body = build_digest(new_jobs, scores, drafts, health_summary)

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
