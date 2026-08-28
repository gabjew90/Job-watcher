"""Daily pipeline: scrape → filter → dedupe → persist → dashboard → notify."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import dashboard, draft_requests, expiry, feedback, filters, health, notify, state as state_mod, triage
from .models import Job
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

    # Rescue records left unscored by previously failed triage chunks:
    # they'd otherwise never be scored again (score() only sees new jobs).
    new_ids = {j.job_id for j in new_jobs}
    desc_by_id = {j.job_id: j.description for j in raw if j.description}
    rescue_jobs = [
        Job(title=seen[jid]["title"], company=seen[jid]["company"],
            location=seen[jid]["location"], url=seen[jid]["url"],
            source=seen[jid]["source"], description=desc_by_id.get(jid, ""))
        for jid in state_mod.unscored_active(seen, new_ids)
    ]
    if rescue_jobs:
        log.warning("Rescuing %d previously unscored records (failed chunks)",
                    len(rescue_jobs))

    to_score = new_jobs + rescue_jobs
    scores = triage.score(to_score, fb["text"])
    fingerprint = triage.scoring_fingerprint(fb["text"])
    # Clear misfits (score < 25) are auto-archived: they stay in state for
    # dedupe but never occupy the dashboard or future attention.
    archive_floor = config.get("auto_archive_below", 25)
    for job in to_score:
        s = scores.get(job.job_id)
        if not s:
            continue
        # Seniority coupling is enforced here, not in the prompt: a
        # seniority mismatch caps the band at weak whatever the model said.
        if not s["seniority_match"] and triage.BAND_ORDER.index(s["band"]) > 1:
            log.info("Seniority cap: %r %s -> weak", job.title[:45], s["band"])
            s["band"] = "weak"
            s["score"] = triage.BAND_SCORE["weak"]
        rec = seen.get(job.job_id)
        if rec is not None:
            rec.update({k: s[k] for k in ("band", "score", "rationale",
                                          "seniority_match")})
            rec["scoring_fingerprint"] = fingerprint
            if s["score"] < archive_floor:
                rec["active"] = False
                rec["closed"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                rec["lowscore"] = True
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
        # Digest floor never sits below the archive floor.
        digest_floor = max(config.get("digest_min_score", 40), archive_floor)
        suggestions = notify.coverage_suggestions(seen, config)
        notify.post_issue(new_jobs, scores, drafts, health.summary(), closed_recs,
                          digest_floor, suggestions)
    else:
        log.info("No new or closed postings; skipping notification.")


if __name__ == "__main__":
    main()
