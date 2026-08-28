"""Claude triage: score new postings for fit, then draft resumes for top hits.

Runs headless Claude Code (`claude -p`), authenticated in CI via the
CLAUDE_CODE_OAUTH_TOKEN repo secret (minted with `claude setup-token`) —
subscription usage, no API key. Scoring uses Haiku; resume drafts use
Sonnet (rare, and writing quality matters there).

Cost hygiene: the whole step is skipped when there are no new postings,
scoring is batched (CHUNK jobs per call), and drafting is disabled until
experience_library.md stops being a template.
"""
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

log = logging.getLogger(__name__)

PROFILE = Path("profile.md")
LIBRARY = Path("experience_library.md")
DRAFTS_DIR = Path("drafts")
CHUNK = 40
SCORE_MODEL = "haiku"
DRAFT_MODEL = "sonnet"

SCORE_PROMPT = """You are a job-fit triage assistant. Score each posting below for fit
against this candidate profile:

{profile}
{feedback}

Return ONLY a JSON array, no prose, one object per posting:
{{"job_id": "...", "score": 0-100, "rationale": "one sentence",
  "seniority_match": true/false, "pay": "...", "work_mode": "..."}}

score = overall fit (domain AND seniority). seniority_match = false when the
role is below (or far above) director/senior-PM level, e.g. technician,
junior, or pure IC engineering roles — those must also score below 40.

pay = the salary/compensation range exactly as stated in the posting text,
compact (e.g. "$153,000–$180,000/yr"); "" if the posting doesn't state pay.
work_mode = "onsite", "hybrid", or "remote" ONLY if the posting says so or
it is unambiguous; "" otherwise. Never guess either field.

Postings:
{postings}"""

DRAFT_PROMPT = """Draft a tailored one-page resume in Markdown for this job posting.

HARD RULES:
- Draw ONLY from the experience library below. Never invent metrics, skills,
  employers, dates, or accomplishments that are not written there.
- If the library lacks material for a section, write "TODO: <what's missing>"
  instead of filling it in.
- Tailor emphasis and ordering to the posting; do not fabricate relevance.
- Output ONLY the resume markdown, no commentary.

JOB POSTING:
{job}

EXPERIENCE LIBRARY:
{library}"""


def available() -> bool:
    return shutil.which("claude") is not None


def _run_claude(prompt: str, model: str) -> str:
    result = subprocess.run(
        ["claude", "-p", "--model", model, "--output-format", "json"],
        input=prompt, capture_output=True, text=True, timeout=900,
    )
    if result.returncode != 0:
        hint = ("" if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
                else " (CLAUDE_CODE_OAUTH_TOKEN is not set — add it as a repo "
                     "secret, see README)")
        raise RuntimeError(
            f"claude exited {result.returncode}{hint}: "
            f"{(result.stderr or result.stdout)[-500:]}")
    payload = json.loads(result.stdout)
    if payload.get("is_error"):
        raise RuntimeError(f"claude error result: {str(payload.get('result'))[:500]}")
    return payload["result"]


def _parse_json(text: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON array in response: {text[:200]}")
    return json.loads(text[start:end + 1])


def score(new_jobs: list[Job], feedback_text: str = "") -> dict[str, dict]:
    """Return {job_id: {score, rationale, seniority_match, pay, work_mode}}."""
    if not new_jobs:
        return {}
    if not available():
        log.warning("claude CLI not found; skipping triage.")
        return {}
    profile = PROFILE.read_text()
    feedback = (f"\nThe candidate has given feedback on past results — honor it "
                f"and generalize from the reasons given:\n{feedback_text}\n"
                if feedback_text.strip() else "")
    results: dict[str, dict] = {}
    for i in range(0, len(new_jobs), CHUNK):
        chunk = new_jobs[i:i + CHUNK]
        postings = "\n\n".join(
            f"job_id: {j.job_id}\ntitle: {j.title}\ncompany: {j.company}\n"
            f"location: {j.location}\ndescription: {j.description[:1500]}"
            for j in chunk
        )
        try:
            raw = _run_claude(
                SCORE_PROMPT.format(profile=profile, feedback=feedback,
                                    postings=postings), SCORE_MODEL)
            for item in _parse_json(raw):
                mode = str(item.get("work_mode", "")).lower()
                results[str(item["job_id"])] = {
                    "score": int(item["score"]),
                    "rationale": str(item.get("rationale", "")),
                    "seniority_match": bool(item.get("seniority_match", False)),
                    "pay": str(item.get("pay", "") or ""),
                    "work_mode": mode if mode in ("onsite", "hybrid", "remote") else "",
                }
            log.info("Triage chunk %d-%d scored (%d results)",
                     i + 1, i + len(chunk), len(results))
        except Exception as e:  # noqa: BLE001 - a failed chunk shouldn't kill the run
            log.warning("TRIAGE FAILURE on chunk %d-%d: %s", i + 1, i + len(chunk), e)
    return results


def library_ready() -> bool:
    return LIBRARY.exists() and "STATUS: TEMPLATE" not in LIBRARY.read_text()


def draft_resumes(new_jobs: list[Job], scores: dict[str, dict], threshold: int) -> list[Path]:
    top = [j for j in new_jobs
           if scores.get(j.job_id, {}).get("score", 0) >= threshold]
    if not top:
        return []
    if not library_ready():
        log.info("%d posting(s) above threshold, but experience_library.md is "
                 "still a template — skipping resume drafts.", len(top))
        return []
    library = LIBRARY.read_text()
    DRAFTS_DIR.mkdir(exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    written = []
    for job in top:
        job_text = (f"title: {job.title}\ncompany: {job.company}\n"
                    f"location: {job.location}\nurl: {job.url}\n"
                    f"description: {job.description[:4000]}")
        try:
            resume = _run_claude(
                DRAFT_PROMPT.format(job=job_text, library=library), DRAFT_MODEL)
            resume = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", resume.strip(), flags=re.S)
            slug = re.sub(r"[^a-z0-9]+", "-", f"{job.company}-{job.title}".lower()).strip("-")[:80]
            path = DRAFTS_DIR / f"{date}-{slug}.md"
            path.write_text(f"<!-- {job.title} @ {job.company} — {job.url} -->\n\n{resume}\n")
            written.append(path)
            log.info("Drafted resume: %s", path)
        except Exception as e:  # noqa: BLE001
            log.warning("DRAFT FAILURE for %s @ %s: %s", job.title, job.company, e)
    return written
