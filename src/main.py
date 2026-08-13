"""Daily pipeline: scrape → filter → dedupe → persist → dashboard → notify."""
import json
import logging
from pathlib import Path

from . import dashboard, filters, notify, state as state_mod
from .sources import jobspy_source

log = logging.getLogger(__name__)

LATEST_RUN = Path("data/latest_run.json")
DESCRIPTION_CAP = 2000  # chars kept per job for the triage step


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = json.loads(Path("config.json").read_text())

    raw = jobspy_source.fetch(config)
    log.info("Fetched %d raw postings", len(raw))

    kept = filters.apply_filters(raw, config)
    log.info("%d postings after relevance filter/exclusions", len(kept))

    seen = state_mod.load()
    new_jobs = state_mod.split_new(kept, seen)
    seen = state_mod.prune(seen, config.get("state_retention_days", 180))
    state_mod.save(seen)
    log.info("%d NEW postings (%d tracked total)", len(new_jobs), len(seen))

    # Full records (with capped descriptions) for the Phase 3 triage step.
    LATEST_RUN.parent.mkdir(parents=True, exist_ok=True)
    LATEST_RUN.write_text(json.dumps(
        [{**j.to_dict(), "description": j.description[:DESCRIPTION_CAP]} for j in new_jobs],
        indent=1,
    ) + "\n")

    dashboard.generate(seen)

    if new_jobs:
        notify.post_issue(new_jobs)
    else:
        log.info("No new postings; skipping notification.")


if __name__ == "__main__":
    main()
