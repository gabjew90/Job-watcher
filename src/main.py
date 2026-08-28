"""Daily pipeline: scrape → filter → dedupe → persist → dashboard → notify."""
import json
import logging
from pathlib import Path

from . import dashboard, draft_requests, expiry, feedback, filters, health, notify, state as state_mod, triage
from .sources import ats_boards, hyperscalers, jobspy_source, successfactors, workday

log = logging.getLogger(__name__)

LATEST_RUN = Path("data/latest_run.json")
DESCRIPTION_CAP = 2000  # chars kept per job for the triage step


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = json.loads(Path("config.json").read_text())

    raw = (jobspy_source.fetch(config) + hyperscalers.fetch(config)
           + ats_boards.fetch(config) + workday.fetch(config)
           + successfactors.fetch(config))
    log.info("Fetched %d raw postings", len(raw))
    health.save_run()
    for s in health.summary():
        if s["status"] != "ok":
            log.warning("SOURCE HEALTH %s: %s (last results: %s)",
                        s["source"], s["status"], s["last_results"] or "never")

    kept = filters.apply_filters(raw, config)
    log.info("%d postings after relevance filter/exclusions", len(kept))

    fb = feedback.load()
    kept = [j for j in kept if not feedback.matches(j, fb["hide"])]

    seen = state_mod.load()
    feedback.sweep_state(seen, fb["hide"])
    closed_recs = expiry.sweep(seen, raw, config)
    new_jobs = state_mod.split_new(kept, seen)
    seen = state_mod.prune(seen, config.get("state_retention_days", 180))
    log.info("%d NEW postings (%d tracked total)", len(new_jobs), len(seen))

    # Full records (with capped descriptions), for inspection/debugging.
    LATEST_RUN.parent.mkdir(parents=True, exist_ok=True)
    LATEST_RUN.write_text(json.dumps(
        [{**j.to_dict(), "description": j.description[:DESCRIPTION_CAP]} for j in new_jobs],
        indent=1,
    ) + "\n")

    scores = triage.score(new_jobs, fb["text"])
    for job in new_jobs:
        s = scores.get(job.job_id)
        if not s:
            continue
        rec = seen.get(job.job_id)
        if rec is not None:
            rec.update({k: s[k] for k in ("score", "rationale", "seniority_match")})
        # LLM-extracted pay/mode fill gaps only — structured API fields win.
        for field in ("pay", "work_mode"):
            if s.get(field) and not getattr(job, field):
                setattr(job, field, s[field])
                if rec is not None and not rec.get(field):
                    rec[field] = s[field]
    state_mod.save(seen)

    # Drafting is on-demand only: the dashboard's ✍️ link files a
    # draft-request issue; no auto-drafting by score.
    drafts = draft_requests.process(raw, seen, config)

    dashboard.generate(seen, health.summary(),
                       config.get("dashboard_max_rows", 500))

    if new_jobs or closed_recs:
        notify.post_issue(new_jobs, scores, drafts, health.summary(), closed_recs)
    else:
        log.info("No new or closed postings; skipping notification.")


if __name__ == "__main__":
    main()
