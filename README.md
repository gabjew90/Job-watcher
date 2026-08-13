# Job Watcher

Daily monitor for director/senior-PM roles in **data center energy, energy
infrastructure, data center flexibility, and grid interconnection** —
hyperscalers and the surrounding BESS / datacenter-power ecosystem.

Scrapes job boards daily via GitHub Actions, filters and dedupes, posts new
postings as a GitHub Issue digest, and renders a dashboard on GitHub Pages.
Claude triage + tailored resume drafting arrive in Phase 3 (see `PLAN.md`).

## How it works

```
jobspy (Indeed/Glassdoor/ZipRecruiter/Google)   ← Phase 2 adds hyperscaler + ATS-board fetchers
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

## Notes

- Glassdoor/ZipRecruiter sometimes block GitHub Actions IPs; each
  (site, search-term) pair is isolated, so partial failures only shrink
  coverage for a day. Failures show as `SOURCE FAILURE` warnings in the
  Actions log.
- No LinkedIn scraping. No auto-applying. Discovery, scoring, and drafting
  only.
