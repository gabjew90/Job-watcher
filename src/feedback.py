"""User feedback on specific jobs/patterns, from two places:

1. feedback.md in the repo — the curated preference file.
2. Open GitHub issues labeled `feedback` — created from the dashboard's
   per-row "feedback" link (mobile-friendly). Requires GITHUB_TOKEN, so
   issue feedback applies on workflow runs; local runs use feedback.md only.

Everything is injected verbatim into the triage scoring prompt so scores
adapt to the stated "why". Additionally, hide directives are applied
deterministically (no LLM involved):
- in feedback.md: a line like      hide: transmission planning @ ICF
- in a feedback issue: a body line  Action: hide
  (the job reference comes from the issue title "feedback: <title> @ <co>")

A hide target matches any job whose "<title> @ <company>" contains every
comma-free token group (case-insensitive substring on the whole string).
Hidden jobs are dropped before triage/digest and marked inactive in state.
"""
import logging
import os
import re
from pathlib import Path

import requests

from .models import Job

log = logging.getLogger(__name__)

FILE = Path("feedback.md")


def _issue_entries() -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return []
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{repo}/issues",
            params={"labels": "feedback", "state": "open", "per_page": 50},
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json"},
            timeout=30,
        )
        resp.raise_for_status()
        return [{"title": i.get("title", ""), "body": i.get("body") or ""}
                for i in resp.json()]
    except Exception as e:  # noqa: BLE001
        log.warning("feedback issue fetch failed: %s", e)
        return []


def load() -> dict:
    """Return {"text": prompt block, "hide": [substring, ...]}."""
    parts: list[str] = []
    hide: list[str] = []

    if FILE.exists():
        # HTML comments hold inert examples — never parse or forward them.
        md = re.sub(r"<!--.*?-->", "", FILE.read_text(), flags=re.S).strip()
        parts.append(md)
        for line in md.splitlines():
            m = re.match(r"\s*[-*]?\s*hide:\s*(.+)", line, re.I)
            if m:
                hide.append(m.group(1).strip())

    for issue in _issue_entries():
        parts.append(f"[issue] {issue['title']}\n{issue['body']}".strip())
        if re.search(r"^\s*Action:\s*hide\b", issue["body"], re.I | re.M):
            target = re.sub(r"^feedback:\s*", "", issue["title"], flags=re.I).strip()
            if target:
                hide.append(target)

    return {"text": "\n\n".join(p for p in parts if p), "hide": hide}


def _match_one(target: str, title: str, company: str) -> bool:
    target = target.lower().strip()
    title, company = title.lower(), company.lower()
    if "@" in target:
        # "some title words @ company" — both halves match independently,
        # so shorthand works ("transmission planning @ icf").
        t, c = target.rsplit("@", 1)
        return t.strip() in title and c.strip() in company
    return target in f"{title} @ {company}"


def matches(job: Job, hide: list[str]) -> bool:
    return any(_match_one(h, job.title, job.company) for h in hide)


def sweep_state(seen: dict, hide: list[str]) -> int:
    """Mark already-tracked matching records hidden/inactive."""
    n = 0
    for rec in seen.values():
        if rec.get("hidden") or not hide:
            continue
        if any(_match_one(h, rec.get("title", ""), rec.get("company", ""))
               for h in hide):
            rec["hidden"] = True
            rec["active"] = False
            rec.setdefault("closed", "hidden")
            n += 1
    if n:
        log.info("Feedback: hid %d tracked postings", n)
    return n
