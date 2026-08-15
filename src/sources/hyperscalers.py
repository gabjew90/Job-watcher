"""Direct fetchers for hyperscaler career sites (undocumented JSON endpoints).

These break when the sites redesign. Each fetcher keeps its URL/params at the
top so they're easy to update — see README "Fixing a broken fetcher" for the
DevTools workflow. Verified working 2026-08:

- Microsoft: Eightfold-powered site at apply.careers.microsoft.com
  (the old gcsservices.careers.microsoft.com host is dead — stale cert).
  Search results carry no descriptions, so filtering is title-based.
- Amazon: classic amazon.jobs search.json.
- Google: server-rendered careers page; job data lives in the second
  AF_initDataCallback ('ds:1') script blob.
- Meta: disabled by default — metacareers.com returns 400 to datacenter IPs
  and its GraphQL API needs session tokens. Enable in config to try anyway.
"""
import json
import logging
import re
import time

import requests

from .. import health
from ..models import Job
from ..util import HEADERS, strip_html

log = logging.getLogger(__name__)

MICROSOFT_URL = "https://apply.careers.microsoft.com/api/pcsx/search"
AMAZON_URL = "https://www.amazon.jobs/en/search.json"
GOOGLE_URL = "https://www.google.com/about/careers/applications/jobs/results/"
META_URL = "https://www.metacareers.com/jobs"
RESULTS_PER_TERM = 20


def fetch_microsoft(term: str) -> list[Job]:
    resp = requests.get(MICROSOFT_URL, headers=HEADERS, timeout=30, params={
        "domain": "microsoft.com",
        "query": term,
        "location": "United States",
        "num": RESULTS_PER_TERM,
    })
    resp.raise_for_status()
    jobs = []
    for pos in resp.json()["data"]["positions"]:
        locations = pos.get("locations") or [""]
        # positionUrl comes back as a relative path (/careers/job/<id>)
        url = pos.get("positionUrl") or f"/careers/job/{pos['id']}"
        if url.startswith("/"):
            url = "https://apply.careers.microsoft.com" + url
        jobs.append(Job(
            title=pos.get("name", ""),
            company="Microsoft",
            location=locations[0] + (f" (+{len(locations) - 1} more)" if len(locations) > 1 else ""),
            url=url,
            source="microsoft",
        ))
    return jobs


def fetch_amazon(term: str) -> list[Job]:
    resp = requests.get(AMAZON_URL, headers=HEADERS, timeout=30, params={
        "base_query": term,
        "result_limit": RESULTS_PER_TERM,
        "offset": 0,
        "normalized_country_code[]": "USA",
    })
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("jobs") or []:
        jobs.append(Job(
            title=j.get("title", ""),
            company="Amazon",
            location=j.get("normalized_location") or j.get("location", ""),
            url="https://www.amazon.jobs" + j.get("job_path", ""),
            source="amazon",
            description=strip_html(
                (j.get("description") or j.get("description_short") or "")
                + " " + (j.get("basic_qualifications") or "")
            ),
            date_posted=j.get("posted_date", ""),
        ))
    return jobs


def fetch_google(term: str) -> list[Job]:
    resp = requests.get(GOOGLE_URL, headers=HEADERS, timeout=30, params={
        "q": f'"{term}"',
        "location": "United States",
    })
    resp.raise_for_status()
    # Job list lives in the AF_initDataCallback blob keyed 'ds:1'. Each entry:
    # [id, title, apply_url, [_, responsibilities_html], [_, quals_html],
    #  _, _, company, _, [[location, ...], ...], ...]
    jobs = []
    for blob in re.findall(r"AF_initDataCallback\((\{.*?\})\);", resp.text, re.S):
        if "'ds:1'" not in blob and '"ds:1"' not in blob:
            continue
        m = re.search(r"data:(\[.*\]), sideChannel", blob, re.S)
        if not m:
            continue
        for entry in json.loads(m.group(1))[0] or []:
            try:
                locations = ", ".join(loc[0] for loc in (entry[9] or [])[:3])
                desc = strip_html(str((entry[3] or [None, ""])[1]) + " " + str((entry[4] or [None, ""])[1]))
                jobs.append(Job(
                    title=str(entry[1]),
                    company=str(entry[7] or "Google"),
                    location=locations,
                    url=f"https://www.google.com/about/careers/applications/jobs/results/{entry[0]}",
                    source="google-careers",
                    description=desc,
                ))
            except (IndexError, TypeError) as e:
                log.debug("google entry parse skip: %s", e)
    return jobs


def fetch_meta(term: str) -> list[Job]:
    resp = requests.get(META_URL, headers=HEADERS, timeout=30, params={"q": term})
    resp.raise_for_status()
    # Best effort: job cards appear as {"id":"...","title":"..."} pairs in
    # embedded script JSON on the search page.
    jobs = []
    for job_id, title in set(re.findall(r'\{"id":"(\d+)","title":"([^"]+)"', resp.text)):
        jobs.append(Job(
            title=title,
            company="Meta",
            location="",
            url=f"https://www.metacareers.com/jobs/{job_id}",
            source="meta",
        ))
    return jobs


FETCHERS = {
    "microsoft": fetch_microsoft,
    "amazon": fetch_amazon,
    "google": fetch_google,
    "meta": fetch_meta,
}


def fetch(config: dict) -> list[Job]:
    enabled = config.get("hyperscalers", {})
    jobs: list[Job] = []
    for name, fetcher in FETCHERS.items():
        if not enabled.get(name):
            continue
        for term in config["search_terms"]:
            try:
                got = fetcher(term)
                jobs.extend(got)
                log.info("%s / %r: %d results", name, term, len(got))
                health.record(name, ok=True, count=len(got))
            except Exception as e:  # noqa: BLE001 - per-source isolation by design
                log.warning("SOURCE FAILURE %s / %r: %s", name, term, e)
                health.record(name, ok=False, error=e)
            time.sleep(1)
    return jobs
