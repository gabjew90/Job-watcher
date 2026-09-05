"""On-demand resume drafting, driven by GitHub issues.

The dashboard's ✍️ link on each row opens a pre-filled issue titled
"draft: <title> @ <company>" labeled `draft-request`, with the posting URL
in a hidden HTML comment. Each run:

1. reads open draft-request issues (workflow GITHUB_TOKEN), skipping any
   labeled `draft-failed` (a broken request is a one-shot, not a 6-hourly
   retry; remove the label to retry),
2. matches each to a tracked posting: by URL, then by company + title,
   then by title prefix (issue titles are cut at 80 chars),
3. fetches the posting page for a description when this run's fetch did
   not carry one (JS-rendered and Indeed pages yield nothing; the draft is
   then title-only and the comment says so),
4. drafts via resume.draft (plain-prose style contract, fabrication guard,
   ATS coverage, one-page DOCX + PDF + Markdown twin),
5. comments the files, lead role, ATS coverage, gaps and any guard or
   style notes on the issue, and closes it.

Anything the requester typed in the issue body (besides the placeholder)
is passed to the drafter as emphasis notes. No auto-drafting by score.
"""
import logging
import os
import re

import requests

from . import resume
from .models import Job
from .util import HEADERS, company_key, role_excerpt, strip_html, title_key

log = logging.getLogger(__name__)

API = "https://api.github.com"
PLACEHOLDER = "Requested from dashboard. Optional: add emphasis notes here."
FAILED_LABEL = "draft-failed"
NOTES_CAP = 1500


def _gh(token: str) -> dict:
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"}


def _notes(body: str) -> str:
    """The requester's own words: placeholder and hidden comments removed."""
    text = re.sub(r"<!--.*?-->", "", body or "", flags=re.S)
    text = text.replace(PLACEHOLDER, "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:NOTES_CAP]


def _posting_url(body: str) -> str:
    m = re.search(r"<!--\s*url:\s*(\S+?)\s*-->", body or "")
    return m.group(1) if m else ""


def _find_job(title: str, company: str, raw_jobs: list[Job], seen: dict,
              url: str = "") -> Job | None:
    """Fresh fetch first (it has descriptions), then the state record."""
    if url:
        for j in raw_jobs:
            if j.url == url:
                return j
        for r in seen.values():
            if r.get("url") == url:
                return _from_record(r)
    want = (company_key(company), title_key(title))
    for j in raw_jobs:
        if (company_key(j.company), title_key(j.title)) == want:
            return j
    for r in seen.values():
        if (company_key(r.get("company", "")), title_key(r.get("title", ""))) == want:
            return _from_record(r)
    # Issue titles are cut at 80 chars by the dashboard link.
    prefix = title_key(title)
    if len(prefix) >= 12:
        for j in raw_jobs:
            if company_key(j.company) == want[0] and title_key(j.title).startswith(prefix):
                return j
        for r in seen.values():
            if (company_key(r.get("company", "")) == want[0]
                    and title_key(r.get("title", "")).startswith(prefix)):
                return _from_record(r)
    return None


def _from_record(r: dict) -> Job:
    return Job(title=r["title"], company=r["company"], location=r.get("location", ""),
               url=r.get("url", ""), source=r.get("source", ""))


def _fetch_description(url: str) -> str:
    """Best effort. Server-rendered postings come back; JS-rendered pages
    and aggregators that block datacenter IPs come back empty."""
    if not url:
        return ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
            return ""
        text = strip_html(resp.text)
        return role_excerpt(text, 6000) if len(text) > 500 else ""
    except Exception as e:  # noqa: BLE001
        log.debug("description fetch failed for %s: %s", url, e)
        return ""


def process(raw_jobs: list[Job], seen: dict, config: dict) -> list:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        log.info("No GITHUB_TOKEN; skipping draft requests.")
        return []
    resp = requests.get(f"{API}/repos/{repo}/issues",
                        params={"labels": "draft-request", "state": "open",
                                "per_page": 20},
                        headers=_gh(token), timeout=30)
    resp.raise_for_status()
    written = []
    branch = os.environ.get("GITHUB_REF_NAME", "claude/brainstorm-approach-8qukjx")
    library = resume.LIBRARY.read_text() if resume.LIBRARY.exists() else ""
    for issue in resp.json():
        if any(lb.get("name") == FAILED_LABEL for lb in issue.get("labels") or []):
            continue
        m = re.match(r"draft:\s*(.+?)\s*@\s*(.+)", issue.get("title", ""), re.I)
        if not m:
            continue
        title, company = m.group(1), m.group(2)
        number = issue["number"]
        body = issue.get("body") or ""
        if not library:
            _comment(token, repo, number, "experience_library.md is missing; nothing to draft from.")
            continue
        job = _find_job(title, company, raw_jobs, seen, url=_posting_url(body))
        if job is None:
            _comment(token, repo, number,
                     "Couldn't match this posting to a tracked job. It may have closed. "
                     "Ask in the repo if it should exist.")
            continue
        if not (job.description or "").strip():
            job.description = _fetch_description(job.url)
        try:
            result = resume.draft(job, library, _notes(body), config)
        except Exception as e:  # noqa: BLE001 - one bad request never kills the run
            log.warning("DRAFT FAILURE for %s @ %s: %s", title, company, e)
            _comment(token, repo, number,
                     f"Draft failed: {str(e)[:300]}. See the Actions log for this run. "
                     f"Remove the `{FAILED_LABEL}` label to retry.")
            _label(token, repo, number, FAILED_LABEL)
            continue
        written += [p for p in (result.pdf_path, result.docx_path, result.md_path) if p]
        _comment(token, repo, number, _format_comment(result, repo, branch))
        _close(token, repo, number)
        log.info("Drafted resume: %s", result.docx_path)
    return written


def _format_comment(r: resume.DraftResult, repo: str, branch: str) -> str:
    def link(p):
        return f"[{p.name}](https://github.com/{repo}/blob/{branch}/{p})"

    files = " · ".join(link(p) for p in (r.pdf_path, r.docx_path, r.md_path) if p)
    lines = [f"Draft ready: {files}",
             f"Lead role: {r.lead_role or '(not recognized)'} · {r.word_count} words"
             + (f" · {r.pages} page" + ("s" if r.pages != 1 else "") if r.pages else "")]
    if r.title_only:
        lines.append("Drafted from the title and company only: the posting text was not "
                     "available this run, so the ATS check was skipped.")
    if r.keywords:
        lines.append(f"\n**ATS coverage: {len(r.covered)}/{len(r.keywords)}**"
                     + (f". Missing: {', '.join(r.missing)}" if r.missing else ""))
        lines += [f"  - {n}" for n in r.revision_notes]

    def section(title, items):
        if items:
            lines.append(f"\n**{title}**")
            lines.extend(f"- {i}" for i in items)

    section("Gaps (must-haves the library can't evidence)", r.gaps)
    section("Also unsupported (nice-to-have)", r.omitted_requirements)
    section("Removed by the fabrication guard", r.guard_removals)
    section("Style (fixed in code)", r.auto_fixes)
    section("Style (still flagged)", r.style_flags)
    section("Trimmed to fit one page", r.trimmed)
    if r.pages and r.pages > 1:
        lines.append(f"\nStill {r.pages} pages after trimming; shorten by hand.")
    return "\n".join(lines)


def _comment(token: str, repo: str, number: int, text: str) -> None:
    body = f"{text}\n\n---\n_Generated by [Claude Code](https://claude.ai/code)_"
    requests.post(f"{API}/repos/{repo}/issues/{number}/comments",
                  json={"body": body}, headers=_gh(token), timeout=30)


def _close(token: str, repo: str, number: int) -> None:
    requests.patch(f"{API}/repos/{repo}/issues/{number}",
                   json={"state": "closed"}, headers=_gh(token), timeout=30)


def _label(token: str, repo: str, number: int, label: str) -> None:
    requests.post(f"{API}/repos/{repo}/issues/{number}/labels",
                  json={"labels": [label]}, headers=_gh(token), timeout=30)
