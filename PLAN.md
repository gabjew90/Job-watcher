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

## Phases

- **Phase 1 (this)**: config, jobspy source, filter/dedupe/state, GitHub Issue
  digest, Pages dashboard, daily Actions workflow. Pause for review of a local
  sample run.
- **Phase 2**: hyperscaler direct fetchers (Microsoft, Amazon, Google, Meta)
  + ATS board fetchers for a curated company list in config.
- **Phase 3**: Claude triage + `experience_library.md` + resume drafting to
  `drafts/`, wired into the same daily workflow.

## Hard rules

- Resume drafts draw ONLY from `experience_library.md`; never invent metrics,
  skills, employers, or accomplishments. Insufficient library → TODO note.
- Per-source try/except: one broken endpoint never kills the run; failures
  logged visibly in Actions output.
- No secrets in code. `CLAUDE_CODE_OAUTH_TOKEN` as repo secret; the issue
  digest uses the workflow's own `GITHUB_TOKEN`.
