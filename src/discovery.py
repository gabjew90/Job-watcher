"""Automatic direct-board discovery for companies that keep producing good roles.

Aggregator copies expire independently, carry no descriptions, and bury
postings. So when a company repeatedly surfaces strong/top-band roles but
we only see it through Indeed, this module tries to find its ATS board and
wires it into config.json.

VERIFICATION IS MANDATORY. Slug guessing is treacherous — "galaxy" is a
security installer, not Galaxy Digital; "hive" is a SaaS vendor, not HIVE
Digital. A candidate board is accepted only if it actually contains a role
we already know that company posted. A wrong guess fails that test and is
discarded, so a bad slug costs nothing but a request.
"""
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .util import HEADERS, company_key, title_key

log = logging.getLogger(__name__)

ATTEMPTS_FILE = Path("state/discovery_attempts.json")
RETRY_DAYS = 30
# Each probe is ~12 cheap requests; attempts are recorded so a company
# is retried only after RETRY_DAYS. A backlog works itself off in days.
MAX_PER_RUN = 8
STRONG_SCORE = 75

PROBES = {
    "greenhouse": ("https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                   lambda d: [j.get("title", "") for j in d.get("jobs") or []]),
    "lever": ("https://api.lever.co/v0/postings/{slug}?mode=json",
              lambda d: [j.get("text", "") for j in d or []]),
    "ashby": ("https://api.ashbyhq.com/posting-api/job-board/{slug}",
              lambda d: [j.get("title", "") for j in d.get("jobs") or []]),
}


def slug_variants(company: str) -> list[str]:
    base = re.sub(r"[^a-z0-9 ]", "", company.lower())
    base = re.sub(r"\b(inc|llc|corp|corporation|company|ltd|co|holdings|group)\b",
                  "", base).strip()
    words = base.split()
    if not words:
        return []
    joined = "".join(words)
    out = [joined, "-".join(words), words[0]]
    if len(words) > 1:
        out.append("".join(words[:2]))
    # drop single generic words that would collide with unrelated boards
    return [s for s in dict.fromkeys(out)
            if len(s) > 3 and s not in {"energy", "power", "data", "grid", "clean"}]


def _titles_match(board_titles: list[str], known: list[str]) -> bool:
    """A board is the right company only if it carries a role we already saw
    that company post. Token overlap absorbs Sr./Senior-style differences."""
    known_keys = {title_key(t) for t in known}
    known_tokens = [set(re.findall(r"[a-z]{3,}", t.lower())) for t in known]
    for bt in board_titles:
        if title_key(bt) in known_keys:
            return True
        bt_tokens = set(re.findall(r"[a-z]{3,}", bt.lower()))
        for kt in known_tokens:
            if kt and bt_tokens and len(kt & bt_tokens) / min(len(kt), len(bt_tokens)) >= 0.7:
                return True
    return False


def discover(company: str, known_titles: list[str]) -> dict | None:
    for slug in slug_variants(company):
        for provider, (url, extract) in PROBES.items():
            try:
                time.sleep(0.25)
                resp = requests.get(url.format(slug=slug), headers=HEADERS, timeout=12)
                if resp.status_code != 200:
                    continue
                titles = extract(resp.json())
                if not titles:
                    continue
                if _titles_match(titles, known_titles):
                    log.info("Discovered %s board for %s: %s (%d postings)",
                             provider, company, slug, len(titles))
                    return {"provider": provider, "board": slug, "company": company}
                log.debug("board %s:%s exists but is a different company", provider, slug)
            except Exception as e:  # noqa: BLE001
                log.debug("probe %s:%s failed: %s", provider, slug, e)
    return None


def _load_attempts() -> dict:
    if ATTEMPTS_FILE.exists():
        return json.loads(ATTEMPTS_FILE.read_text())
    return {}


def run(seen: dict, config: dict) -> list[dict]:
    """Probe boards for aggregator-only companies with strong/top roles.
    Returns config entries to add (caller persists them)."""
    from .state import AGGREGATOR_SOURCES
    direct = {company_key(e.get("company", ""))
              for key in ("ats_boards", "workday_boards", "successfactors_boards",
                          "career_sites")
              for e in config.get(key, [])}
    attempts = _load_attempts()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETRY_DAYS)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    by_company: dict[str, list[dict]] = {}
    for r in seen.values():
        if r.get("active", True) and r.get("company"):
            by_company.setdefault(r["company"], []).append(r)

    candidates = []
    for company, recs in by_company.items():
        if company_key(company) in direct:
            continue
        if not all(r.get("source") in AGGREGATOR_SOURCES for r in recs):
            continue
        if attempts.get(company_key(company), "") > cutoff:
            continue  # probed recently, nothing found
        strong = [r for r in recs if (r.get("score") or 0) >= STRONG_SCORE]
        if strong:
            # Best role first, not most roles: a single top-band posting is
            # as worth wiring up as six strong ones, and the big employers
            # that dominate a volume sort rarely use a standard ATS.
            candidates.append((max(r["score"] for r in strong), len(strong),
                               company, [r["title"] for r in recs]))
    candidates.sort(reverse=True)

    found = []
    for _, _, company, titles in candidates[:MAX_PER_RUN]:
        entry = discover(company, titles)
        attempts[company_key(company)] = today
        if entry:
            found.append(entry)
    ATTEMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ATTEMPTS_FILE.write_text(json.dumps(attempts, indent=1, sort_keys=True) + "\n")
    return found
