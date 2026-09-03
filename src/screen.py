"""Title screen: a cheap model pass over NEW postings before the keyword
filter has the last word.

The keyword filter is a recall-first gate — historically 71% of what it
passed was banded weak/misfit by the full scorer, and what it rejected was
never seen by anyone. This pass judges title + company + location for every
posting not yet in state, in one batched call per ~120 titles:

- a KEEP rescues a posting the keyword filter rejected (flat titles at
  target-domain employers, "Senior Director, Development" at a developer)
- a DROP removes a posting the keyword filter passed (technicians and
  junior engineers with "electrical" in the title)

Only obvious misfits are dropped; ambiguity keeps, because the full scorer
reads the description next. Drops are remembered in state/screened_out.json
so a title is judged once, not every run. Without the claude CLI (local
runs), the keyword filter's decision stands unchanged.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import filters, triage
from .models import Job

log = logging.getLogger(__name__)

FILE = Path("state/screened_out.json")
RETENTION_DAYS = 60
CHUNK = 120
SCREEN_MODEL = os.environ.get("JOBWATCH_SCREEN_MODEL", "claude-haiku-4-5-20251001")

PROMPT = """You are screening job postings for a candidate, using ONLY each posting's
title, company and location (no description is available at this stage).

{profile}

Decide keep or drop for each posting:
- KEEP anything plausibly a director / senior PM / principal / head-of /
  senior strategy, product, development, procurement or investment role in
  energy, power, grid, interconnection, battery storage, datacenter
  infrastructure, energy finance, or AI applied to energy.
- KEEP when the title is ambiguous but the company operates in those
  industries: a flat "Program Manager" or "Development Manager" at a
  datacenter, storage, utility or energy company may be senior in scope.
- DROP only clear misfits: trades, field, technician, construction crew and
  O&M roles; junior, entry-level, intern; hands-on individual-contributor
  engineering (design, firmware, software, network, RTL, validation);
  quota-carrying sales; HR, recruiting, legal, accounting, admin; and roles
  in unrelated industries.
When in doubt, keep — a later pass reads the full description.

Return ONLY a JSON array, no prose, one object per posting:
[{{"job_id": "...", "keep": true}}, ...]

Postings (job_id | title | company | location):
{postings}"""


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load() -> dict:
    if FILE.exists():
        return json.loads(FILE.read_text())
    return {}


def save(screened: dict) -> None:
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    screened = {k: v for k, v in screened.items() if v >= cutoff}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(screened, indent=0, sort_keys=True) + "\n")


def judge(jobs: list[Job]) -> dict[str, bool]:
    """{job_id: keep} for every posting a chunk returned; a failed chunk's
    postings are simply absent and fall back to the keyword decision."""
    if not jobs or not triage.available():
        return {}
    profile = triage.PROFILE.read_text()
    verdicts: dict[str, bool] = {}
    for i in range(0, len(jobs), CHUNK):
        chunk = jobs[i:i + CHUNK]
        postings = "\n".join(
            f"{j.job_id} | {j.title[:90]} | {j.company[:40]} | {j.location[:40]}"
            for j in chunk)
        try:
            raw = triage._run_claude(PROMPT.format(profile=profile, postings=postings),
                                     SCREEN_MODEL)
            for item in triage._parse_json(raw):
                if "job_id" in item and "keep" in item:
                    verdicts[str(item["job_id"])] = bool(item["keep"])
        except Exception as e:  # noqa: BLE001 - keyword filter stands for this chunk
            log.warning("SCREEN FAILURE on chunk %d-%d: %s", i + 1, i + len(chunk), e)
    return verdicts


def apply(raw: list[Job], kept: list[Job], seen: dict, config: dict
          ) -> tuple[list[Job], list[Job], dict]:
    """Reconcile the keyword filter's output with title-screen verdicts for
    postings not yet tracked. Returns (kept, rejected, stats); `rejected`
    is what was turned away before scoring this run (screen drops, or the
    keyword rejects when the screen is unavailable) for the weekly audit.
    """
    screened = load()
    kept_ids = {j.job_id for j in kept}
    candidates = [j for j in raw
                  if j.job_id not in seen and j.job_id not in screened
                  and not filters.is_excluded(j, config["title_exclusions"])]
    # Dedupe by identity: the same req arrives from several sources.
    unseen = list({j.job_id: j for j in candidates}.values())
    verdicts = judge(unseen)
    stats = {"screened": len(verdicts), "rescued": 0, "dropped": 0,
             "available": bool(verdicts) or not unseen}
    if not verdicts:
        rejected = [j for j in unseen if j.job_id not in kept_ids]
        return kept, rejected, stats

    drop_ids, rescued = set(), []
    for j in unseen:
        keep = verdicts.get(j.job_id)
        if keep is None:
            continue  # chunk failed: keyword decision stands
        if keep and j.job_id not in kept_ids:
            j.priority = filters.is_priority(j, config["priority_topics"])
            rescued.append(j)
            kept_ids.add(j.job_id)
        elif not keep:
            drop_ids.add(j.job_id)
            screened[j.job_id] = _today()
    stats["rescued"] = len(rescued)
    stats["dropped"] = sum(1 for j in kept if j.job_id in drop_ids)
    kept = [j for j in kept if j.job_id not in drop_ids] + rescued
    rejected = [j for j in unseen if j.job_id in drop_ids]
    save(screened)
    log.info("Title screen: %d judged, %d rescued past the keyword filter, "
             "%d keyword passes dropped", stats["screened"], stats["rescued"],
             stats["dropped"])
    return kept, rejected, stats
