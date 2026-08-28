# Job Watcher

Daily monitor for director/senior-PM roles in **data center energy, energy
infrastructure, data center flexibility, and grid interconnection** —
hyperscalers and the surrounding BESS / datacenter-power ecosystem.

Scrapes job boards daily via GitHub Actions, filters and dedupes, scores
each new posting for fit with Claude, drafts tailored resumes for top hits,
posts a GitHub Issue digest, and renders a dashboard on GitHub Pages.

## How it works

```
jobspy (Indeed/Glassdoor/ZipRecruiter/Google Jobs)
hyperscaler APIs (Microsoft/Amazon/Google careers; Meta off by default)
ATS boards (Greenhouse/Lever/Ashby — curated ecosystem companies)
  → keyword filter + title exclusions + priority-topic ⭐
  → dedupe vs state/seen_jobs.json  (committed each run)
  → Claude triage: 0-100 fit score vs profile.md (Haiku, batched)
  → resume drafts for scores ≥ 75, from experience_library.md only (Sonnet)
  → GitHub Issue digest (sorted by score) + docs/index.html dashboard
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
2. **Add the triage secret**: run `claude setup-token` on your own machine
   (requires a Claude subscription), then save the token as a repo secret
   named `CLAUDE_CODE_OAUTH_TOKEN` (Settings → Secrets and variables →
   Actions). No API key billing — triage runs on your subscription. Without
   the secret, runs still work; digests are just unscored.
3. **Fill in `experience_library.md`** — resume drafting stays disabled
   until its `STATUS: TEMPLATE` line is deleted. Drafts land in `drafts/`,
   committed by the workflow, and draw ONLY from the library (hard rule in
   the prompt: no invented metrics, skills, employers, or accomplishments —
   gaps become TODO notes).
4. **Tune `config.json`**: search terms, keyword filter, title exclusions,
   priority topics, ATS boards, resume threshold, retention. `profile.md`
   is what postings are scored against — keep it current.

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
- Microsoft search results carry no descriptions, so each Microsoft job's
  full description is fetched from the per-job API (cached per run).
- Amazon pay ranges are NOT capturable: amazon.jobs renders them via a
  JavaScript widget from an internal API — they appear in no fetchable
  text (search API, page HTML, or per-job JSON). Amazon rows show blank
  pay by design; check the posting page.
- Posting liveness: ATS boards are snapshot-diffed exactly; Microsoft and
  Google postings are probed individually each run; other sources
  auto-close after `assume_expired_days`.
- No LinkedIn scraping. No auto-applying. Discovery, scoring, and drafting
  only.
