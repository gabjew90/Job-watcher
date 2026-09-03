# Job Watcher — Architecture Plan

Agreed 2026-08-13 after brainstorm. Deviations from the original reference
prompt (ScottCoffin/Job_Scraper reproduction) are intentional and noted.

## Goal

Daily monitor for director/senior-PM roles in data center energy, energy
infrastructure, data center flexibility, and grid interconnection —
hyperscalers plus the surrounding BESS / datacenter-power ecosystem.
Discovery, scoring, and resume drafting only. No LinkedIn scraping, no
auto-applying.

## Pipeline

```
sources (jobspy | hyperscaler APIs | ATS boards)
  → normalize to a common Job record
  → keyword relevance filter + title exclusions + priority-topic flagging
  → dedupe against state/seen_jobs.json
  → new jobs: GitHub Issue digest + docs/ dashboard (GitHub Pages)
  → Claude triage (score 0-100, rationale, seniority check)
  → resume drafts for scores ≥ threshold, from experience_library.md only
```

## Decisions log

| Decision | Choice | Why |
|---|---|---|
| Scraping | jobspy + hyperscaler JSON endpoints + **ATS board APIs** (Greenhouse/Lever/Ashby) | Glassdoor/ZipRecruiter often block Actions IPs; ATS APIs are stable JSON and precisely target the ecosystem companies |
| State | JSON (`state/seen_jobs.json`), not SQLite | Diffable, mergeable, no binary blobs in git; pruned at 180 days |
| Notifications | **GitHub Issue digest** (not Discord) | Zero extra secrets, GitHub app push + email built in, browsable archive |
| Dashboard | Static HTML in `docs/`, served by GitHub Pages | Real URL, regenerated each run |
| LLM | **Headless Claude Code on Max subscription OAuth token** (`CLAUDE_CODE_OAUTH_TOKEN` secret), not the pay-per-token API | Zero incremental cost; mint with `claude setup-token` |
| Workflows | One daily workflow (scrape → triage → draft → commit → notify) | Two workflows adds coordination for no benefit at this scale |
| Cost control | Skip LLM step entirely when zero new postings; batch all new postings in one prompt | |
| Scoring model (2026-09) | **Sonnet** for banding (was Haiku); Haiku for the new title screen | 71% of keyword-filter passes were banded weak/misfit and 70% failed seniority — the calibration rules are judgment calls; volume is ~50 postings/run so the stronger model is cheap. Eval gates the switch |
| Title screen (2026-09) | Haiku pass over NEW postings' title+company before the keyword gate is final: rescues flat titles at target employers, drops obvious misfits; drops remembered 60 days; Monday digest samples the rejects | Keyword filter was recall-first with unmeasured false negatives; a judged pre-pass both raises recall and cuts the junk the full scorer paid for |
| JS-rendered careers sites (2026-09) | Fetch the vendor JSON endpoint behind the page (Radancy/HiBob/ADP/Jibe in `career_sites.py`); a headless browser is a **discovery tool only** (`scripts/probe_careers_site.js`), never part of the daily run | Every such site is fed by a plain JSON call; capturing it once is cheaper and more robust than rendering in CI, and full-list feeds get exact expiry like ATS boards |

## Phases

- **Phase 1 — DONE**: config, jobspy source, filter/dedupe/state, GitHub Issue
  digest, Pages dashboard, daily Actions workflow. Live-validated; filters
  tightened to two-tier (title keywords vs. description phrases) after the
  first real run showed description-boilerplate noise.
- **Phase 2 — DONE**: hyperscaler direct fetchers (Microsoft via Eightfold
  pcsx API, Amazon search.json, Google careers embedded JSON; Meta written
  but disabled — blocks datacenter IPs) + ATS board fetchers
  (Greenhouse/Lever/Ashby) for the curated company list in config.
- **Phase 3 — DONE**: Claude triage (`src/triage.py`, headless `claude -p`,
  Haiku scoring / Sonnet drafting) + `profile.md` + `experience_library.md`
  template + resume drafting to `drafts/`, wired into the daily workflow.
  Live-validated: 162/166 postings scored in 5 batched calls; drafting
  correctly held off while the library is a template.

## Hard rules

- Resume drafts draw ONLY from `experience_library.md`; never invent metrics,
  skills, employers, or accomplishments. Insufficient library → TODO note.
- Per-source try/except: one broken endpoint never kills the run; failures
  logged visibly in Actions output.
- No secrets in code. `CLAUDE_CODE_OAUTH_TOKEN` as repo secret; the issue
  digest uses the workflow's own `GITHUB_TOKEN`.
