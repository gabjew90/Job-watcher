"""One-off: recompute the work mode of open Indeed records with the
tightened rules (2026-10-23). jobspy's is_remote is a bare keyword match,
so "remote diagnostics" and the like made on-site roles read remote. Indeed
postings stop being re-fetched once they age out of the search window, so
the backlog is read here: Indeed's job API returns each posting's tags
(employers' own work-setting tags: "Remote", "Hybrid work", "In-person")
and description. The description decides, through util.infer_work_mode
(arrangement phrasing only); a tag fills in when the description says
nothing, since Indeed's tags can contradict the text ("In-person" on a
posting "open to remote candidates anywhere within the United States"). Modes the scorer read (work_mode_by "triage") are
left alone. Run from the repo root; commit state/seen_jobs.json after.

    python -m scripts.recheck_indeed_work_mode [--dry-run]
"""
import logging
import sys
import time
from collections import Counter

import requests

from src import expiry, state as state_mod
from src.util import infer_work_mode

log = logging.getLogger("work-mode")
QUERY = ("query J($keys: [ID!]!) { jobData(input: {jobKeys: $keys}) { results { job {"
         " key title location { formatted { long } } attributes { label }"
         " description { text } } } } }")
BATCH = 50


def tag_mode(labels: list[str]) -> str:
    low = {label.strip().lower() for label in labels}
    if any(label.startswith("hybrid") for label in low):
        return "hybrid"
    if any(label == "remote" or label.startswith("remote ") or label == "work from home"
           for label in low):
        return "remote"
    if low & {"in-person", "in person", "on-site", "onsite"}:
        return "onsite"
    return ""


def fetch(keys: list[str]) -> dict[str, dict]:
    from jobspy.indeed.constant import api_headers  # noqa: PLC0415 - optional dep
    out = {}
    for i in range(0, len(keys), BATCH):
        resp = requests.post(expiry.INDEED_API, json={"query": QUERY,
                             "variables": {"keys": keys[i:i + BATCH]}},
                             headers={**api_headers, "indeed-co": "US"}, timeout=60)
        resp.raise_for_status()
        for result in resp.json()["data"]["jobData"]["results"]:
            if result.get("job"):
                out[result["job"]["key"]] = result["job"]
        time.sleep(0.5)
    return out


def main(dry_run: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    seen = state_mod.load()
    recs = {}
    for rec in seen.values():
        m = expiry.INDEED_KEY.search(rec.get("url", ""))
        if (m and rec.get("source") == "indeed" and rec.get("active", True)
                and rec.get("work_mode_by") != "triage"):
            recs.setdefault(m.group(1), []).append(rec)
    jobs = fetch(sorted(recs))
    moves = Counter()
    for key, job in jobs.items():
        labels = [a.get("label", "") for a in job.get("attributes") or []]
        mode = infer_work_mode(
            job.get("title", ""), (job.get("location") or {}).get("formatted", {}).get("long", ""),
            (job.get("description") or {}).get("text", "")) or tag_mode(labels)
        for rec in recs[key]:
            old = rec.get("work_mode", "")
            if old != mode:
                moves[(old or "-", mode or "-")] += 1
                if not dry_run:
                    rec.update(work_mode=mode, work_mode_by="fetch" if mode else "")
    log.info("%d open Indeed records, %d answered: changes %s", len(recs), len(jobs),
             dict(moves.most_common()))
    if not dry_run and moves:
        state_mod.save(seen)


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
