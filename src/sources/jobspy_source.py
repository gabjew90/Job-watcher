"""jobspy source: Indeed, Glassdoor, ZipRecruiter, Google Jobs.

Each (site, term) pair is fetched independently so one blocked or broken
site never kills the run. Failures are logged loudly for the Actions log.
"""
import logging
import time

import pandas as pd
from jobspy import scrape_jobs

from .. import health
from ..models import Job

log = logging.getLogger(__name__)


def _s(value) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    return str(value)


def fetch(config: dict) -> list[Job]:
    jobs: list[Job] = []
    for term in config["search_terms"]:
        for site in config["sites"]:
            try:
                df = scrape_jobs(
                    site_name=[site],
                    search_term=term,
                    google_search_term=f"{term} jobs",
                    location=config.get("location", "United States"),
                    results_wanted=config.get("results_per_term", 25),
                    hours_old=config.get("hours_old", 72),
                    country_indeed="USA",
                    verbose=0,
                )
                for _, row in df.iterrows():
                    jobs.append(Job(
                        title=_s(row.get("title")),
                        company=_s(row.get("company")),
                        location=_s(row.get("location")),
                        url=_s(row.get("job_url")),
                        source=_s(row.get("site")) or site,
                        description=_s(row.get("description")),
                        date_posted=_s(row.get("date_posted")),
                    ))
                log.info("jobspy %s / %r: %d results", site, term, len(df))
                health.record(f"jobspy:{site}", ok=True, count=len(df))
            except Exception as e:  # noqa: BLE001 - per-source isolation by design
                log.warning("SOURCE FAILURE jobspy %s / %r: %s", site, term, e)
                health.record(f"jobspy:{site}", ok=False, error=e)
            time.sleep(1)
    return jobs
