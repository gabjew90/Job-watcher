"""One-off: close the SuccessFactors postings that were removed but still
answer 200 with the site's job-details shell (PG&E and NextEra, found
2026-10-02). The old probe only knew the /errorpage/ redirect, so these
stayed open; the sweep's "most of a source dead at once" guard would hold
back the backlog, so it is cleared here. Run from the repo root after
pulling the latest state; commit state/seen_jobs.json afterwards.

    python -m scripts.close_successfactors_shells [--dry-run]

A posting closes only when the new probe says it is gone AND the site's own
search for its title no longer lists its requisition number.
"""
import json
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from src import expiry, state as state_mod
from src.util import HEADERS

log = logging.getLogger("sf-shells")
STATE = Path("state/seen_jobs.json")
REQ_ID = re.compile(r"/(\d{6,})/?$")


def listed_by_search(url: str, title: str) -> bool | None:
    """Whether the site's search for the title lists this posting's
    requisition number; None when the search cannot be read."""
    m = REQ_ID.search(urlparse(url).path)
    if not m:
        return None
    try:
        resp = requests.get(f"https://{urlparse(url).netloc}/search/",
                            params={"q": title}, headers=HEADERS, timeout=20)
    except requests.RequestException:
        return None
    if resp.status_code != 200 or "/job/" not in resp.text:
        return None  # no results at all reads the same as a broken search
    return m.group(1) in resp.text


def main(dry_run: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    seen = json.loads(STATE.read_text())
    recs = {jid: r for jid, r in seen.items()
            if r.get("active", True) and r.get("source") == "successfactors"}
    closed = kept = unknown = 0
    for jid, rec in recs.items():
        time.sleep(0.3)
        if expiry._successfactors_alive(rec.get("url", "")) is not False:
            kept += 1
            continue
        listed = listed_by_search(rec["url"], rec.get("title", ""))
        if listed is not False:
            unknown += 1
            log.info("Left open (search %s): %s @ %s", listed, rec.get("title"), rec.get("company"))
            continue
        closed += 1
        log.info("Closing: %s @ %s", rec.get("title"), rec.get("company"))
        if not dry_run:
            expiry._close(rec)
    log.info("%d checked: %d closed, %d open, %d left open on an unreadable search",
             len(recs), closed, kept, unknown)
    if not dry_run and closed:
        state_mod.save(seen)


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
