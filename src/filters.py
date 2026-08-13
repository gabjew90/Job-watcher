"""Relevance filter, title exclusions, and priority-topic flagging."""
from .models import Job


def _text(job: Job) -> str:
    return f"{job.title} {job.description}".lower()


def is_relevant(job: Job, keywords: list[str]) -> bool:
    text = _text(job)
    return any(k.lower() in text for k in keywords)


def is_excluded(job: Job, exclusions: list[str]) -> bool:
    title = job.title.lower()
    return any(e.lower() in title for e in exclusions)


def is_priority(job: Job, topics: list[str]) -> bool:
    text = _text(job)
    return any(t.lower() in text for t in topics)


def apply_filters(jobs: list[Job], config: dict) -> list[Job]:
    kept = []
    for job in jobs:
        if is_excluded(job, config["title_exclusions"]):
            continue
        if not is_relevant(job, config["keyword_filter"]):
            continue
        job.priority = is_priority(job, config["priority_topics"])
        kept.append(job)
    return kept
