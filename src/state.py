"""Seen-postings state: dedupe across runs, committed to the repo as JSON."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Job

STATE_FILE = Path("state/seen_jobs.json")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


def prune(state: dict, retention_days: int) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    return {k: v for k, v in state.items() if v.get("first_seen", "9999") >= cutoff}


def split_new(jobs: list[Job], state: dict) -> list[Job]:
    """Return only jobs not already in state, and record them in state.

    State stores metadata (not descriptions) so the dashboard can render
    history without bloating the file.
    """
    new = []
    for job in jobs:
        if job.job_id in state:
            # Backfill fields added after this record was first stored.
            rec = state[job.job_id]
            for field, value in (("date_posted", job.date_posted),
                                 ("pay", job.pay), ("work_mode", job.work_mode)):
                if value and not rec.get(field):
                    rec[field] = value
            continue
        state[job.job_id] = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "url": job.url,
            "source": job.source,
            "priority": job.priority,
            "first_seen": _today(),
            "date_posted": job.date_posted,
            "pay": job.pay,
            "work_mode": job.work_mode,
        }
        new.append(job)
    return new
