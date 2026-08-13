# Job Watcher

Daily monitor for director/senior-PM roles in **data center energy, energy
infrastructure, data center flexibility, and grid interconnection** —
hyperscalers and the surrounding BESS / datacenter-power ecosystem.

Scrapes job boards daily via GitHub Actions, filters and dedupes, posts new
postings as a GitHub Issue digest, and renders a dashboard on GitHub Pages.
Claude triage + tailored resume drafting arrive in Phase 3 (see `PLAN.md`).

## How it works

```
jobspy (Indeed/Glassdoor/ZipRecruiter/Google Jobs)
hyperscaler APIs (Microsoft/Amazon/Google careers; Meta off by default)
ATS boards (Greenhouse/Lever/Ashby — curated ecosystem companies)
  → keyword filter + title exclusions + priority-topic ⭐
  → dedupe vs state/seen_jobs.json  (committed each run)
  → GitHub Issue digest + docs/index.html dashboard
```

- **Schedule**: daily at 14:13 UTC (`.github/workflows/daily.yml`), plus
  manual runs via the Actions tab (`workflow_dispatch`).
- **Notifications**: each run with new postings opens a GitHub Issue labeled
  `job-digest`. Watch the repo (or install the GitHub mobile app) to get
  push/email notifications. No extra secrets needed.
- **State**: `state/seen_jobs.json`, pruned after 180 days, so only
  never-before-seen postings surface.

## Setup

1. **Enable GitHub Pages**: repo Settings → Pages → deploy from branch,
   folder `/docs`. The dashboard then lives at
   `https://<user>.github.io/Job-watcher/`.
2. **Tune `config.json`**: search terms, keyword filter, title exclusions,
   priority topics, sites, retention.
3. That's it for Phase 1 — the issue digest uses the workflow's own
   `GITHUB_TOKEN`.

### Phase 3 (upcoming) will additionally need

- `CLAUDE_CODE_OAUTH_TOKEN` repo secret — mint locally with
  `claude setup-token` (uses your Claude subscription; no API key billing).
- `experience_library.md` filled in (template will be provided).

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

Without `GITHUB_TOKEN` set, the digest is printed to stdout instead of
posted. `data/latest_run.json` holds the current run's new postings with
descriptions (input for the triage step).

## Adding / fixing sources

**ATS boards** (most reliable source — stable public JSON): add an entry to
`ats_boards` in `config.json`. Find a company's board slug from its careers
page URL, or probe:

```
https://boards-api.greenhouse.io/v1/boards/<slug>/jobs
https://api.lever.co/v0/postings/<slug>?mode=json
https://api.ashbyhq.com/posting-api/job-board/<slug>
```

**Fixing a broken hyperscaler fetcher** (they use undocumented endpoints
that move when sites redesign): open the career site's search page in a
browser, DevTools → Network tab → filter XHR/Fetch, run a search, and find
the request returning job JSON. Copy its URL and params into the matching
fetcher at the top of `src/sources/hyperscalers.py`. Verified endpoints as
of 2026-08 are noted there — e.g. Microsoft moved from
`gcsservices.careers.microsoft.com` to the Eightfold-powered
`apply.careers.microsoft.com/api/pcsx/search` in 2026.

## Notes

- Glassdoor/ZipRecruiter block datacenter IPs (Cloudflare) — expect
  `SOURCE FAILURE` warnings for them on most runs; each (site, search-term)
  pair is isolated so the rest of the run is unaffected. Meta similarly
  rejects non-residential traffic, so its fetcher ships disabled
  (`hyperscalers.meta` in config).
- Microsoft search results carry no descriptions, so Microsoft jobs are
  filtered on title keywords only.
- No LinkedIn scraping. No auto-applying. Discovery, scoring, and drafting
  only.
