"""Notification: post the day's new postings as a GitHub Issue.

Uses the workflow's own GITHUB_TOKEN — no extra secrets. Locally (no token)
the digest is just printed.
"""
import logging
import os
from datetime import datetime, timezone

import requests

from .models import Job

log = logging.getLogger(__name__)


def build_digest(new_jobs: list[Job]) -> str:
    starred = [j for j in new_jobs if j.priority]
    rest = [j for j in new_jobs if not j.priority]
    lines = []
    if starred:
        lines.append("## ⭐ Priority topics\n")
        lines += [_line(j) for j in starred]
        lines.append("")
    if rest:
        lines.append("## New postings\n")
        lines += [_line(j) for j in rest]
    lines.append("\n---\n_Dashboard: see the GitHub Pages site for full history._")
    return "\n".join(lines)


def _line(job: Job) -> str:
    return f"- [{job.title}]({job.url}) — **{job.company}** · {job.location} · _{job.source}_"


def post_issue(new_jobs: list[Job]) -> None:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"Job watch {date}: {len(new_jobs)} new posting{'s' if len(new_jobs) != 1 else ''}"
    body = build_digest(new_jobs)

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
