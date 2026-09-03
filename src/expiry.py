"""Mark tracked postings as closed so the dashboard doesn't link to dead jobs.

Three tiers, by how reliably each source can be checked:

1. Full-list sources (greenhouse/lever/ashby boards; radancy/hibob/adp
   careers sites): every run fetches the employer's FULL posting list, so a
   tracked posting missing from today's snapshot is closed. Exact and free.
   Skipped for a provider if any of its boards failed to fetch this run
   (otherwise an outage would mass-expire jobs).
2. Microsoft: the careers SPA serves expired jobs with HTTP 200 and no
   status field anywhere, but the pcsx search API indexes only open
   positions — searching for a job's display ID is an exact liveness test.
   (Two requests per posting: position id → display_job_id → search.)
3. Everything else (indeed, amazon, google-careers, ...): no reliable
   probe, so postings auto-close after `assume_expired_days` (default 30).
   If a job is actually still open it stays visible on the source site and
   in dedupe state — it just drops off the dashboard's active view.

Closed records stay in state for dedupe; they never re-alert.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from . import health
from .models import Job
from .util import HEADERS, group_key

log = logging.getLogger(__name__)

# Sources whose fetchers return the complete posting list every run.
ATS_PROVIDERS = ("greenhouse", "lever", "ashby", "radancy", "hibob", "adp")
MS_JOB_API = "https://apply.careers.microsoft.com/api/apply/v2/jobs/{pid}"
MS_SEARCH_API = "https://apply.careers.microsoft.com/api/pcsx/search"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _close(rec: dict) -> None:
    rec["active"] = False
    rec["closed"] = _today()


def _healthy_ats_providers() -> set[str]:
    """Providers whose boards ALL fetched cleanly this run."""
    by_provider: dict[str, list[bool]] = {}
    for source, entry in health._current.items():
        provider = source.split(":")[0]
        if provider in ATS_PROVIDERS:
            by_provider.setdefault(provider, []).append(entry["ok"])
    return {p for p, oks in by_provider.items() if oks and all(oks)}


def _google_alive(url: str, title: str) -> bool | None:
    """Dead Google postings still return 200 with a generic page; a live one
    embeds the job title in the server-rendered HTML."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 404:
            return False
        if resp.status_code != 200 or len(title) < 8:
            return None
        return title[:25].lower() in resp.text.lower()
    except Exception as e:  # noqa: BLE001
        log.debug("google liveness check failed for %s: %s", url, e)
        return None


def _microsoft_alive(url: str) -> bool | None:
    """True/False when determinable, None on any doubt."""
    try:
        pid = url.rstrip("/").split("/")[-1]
        job = requests.get(MS_JOB_API.format(pid=pid),
                           params={"domain": "microsoft.com"},
                           headers=HEADERS, timeout=20).json()
        display_id = str(job.get("display_job_id") or "")
        if not display_id:
            return None
        time.sleep(0.3)
        found = requests.get(MS_SEARCH_API,
                             params={"domain": "microsoft.com",
                                     "query": display_id, "num": 5},
                             headers=HEADERS, timeout=20).json()
        positions = found.get("data", {}).get("positions", [])
        return any(str(p.get("displayJobId")) == display_id for p in positions)
    except Exception as e:  # noqa: BLE001
        log.debug("microsoft liveness check failed for %s: %s", url, e)
        return None


def sweep(seen: dict, raw_jobs: list[Job], config: dict) -> list[dict]:
    """Mark closed postings inactive in-place. Returns the records closed."""
    closed: list[dict] = []
    present = {j.job_id for j in raw_jobs}
    present_groups = {group_key(j.company, j.title) for j in raw_jobs}
    healthy = _healthy_ats_providers()
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=config.get("assume_expired_days", 30))
              ).strftime("%Y-%m-%d")

    ms_checked = 0
    for job_id, rec in seen.items():
        if not rec.get("active", True):
            continue
        source = rec.get("source", "")
        if source in ATS_PROVIDERS:
            if (source in healthy and job_id not in present
                    and group_key(rec.get("company", ""),
                                  rec.get("title", "")) not in present_groups):
                _close(rec)
                closed.append(rec)
        elif source == "microsoft":
            time.sleep(0.3)
            alive = _microsoft_alive(rec.get("url", ""))
            ms_checked += 1
            if alive is False:
                _close(rec)
                closed.append(rec)
        elif source == "google-careers":
            time.sleep(0.3)
            if _google_alive(rec.get("url", ""), rec.get("title", "")) is False:
                _close(rec)
                closed.append(rec)
        # Age from date_posted when known: a posting found late (company
        # watch uses a wider window) shouldn't get a full retention period
        # counted from discovery.
        elif min(rec.get("date_posted") or "9999",
                 rec.get("first_seen", "9999")) < cutoff:
            _close(rec)
            closed.append(rec)

    if closed:
        log.info("Expiry sweep: closed %d postings (%d Microsoft probed)",
                 len(closed), ms_checked)
    return closed
