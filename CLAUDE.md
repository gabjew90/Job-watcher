# Working on this repo

- **Code review at every milestone (owner, 2026-10-01).** Before merging a
  feature, a fix, or a batch of related changes, run the `code-review`
  skill on the diff (`/code-review high`), fix every confirmed finding,
  re-run `python -m pytest -q tests`, and only then merge. Say in the PR
  what the review found and what was fixed.
- **Shared code.** `src/` is shared with gabjew90/Jess-job-board. Port fixes
  there too, keeping the shared files identical; only `REPO` in
  `src/dashboard.py` and each repo's config and owner files differ.
- **Owner-curated files.** `profile.md`, `feedback.md` and
  `.claude/skills/apply-job/answers.md` change only on the owner's word. A
  `feedback.md` rule that cites an issue needs an eval case in
  `eval/cases.json` (enforced by `src/eval_runner.py`).
- **Verify against live data.** Check claims about postings, boards and
  scores against `state/`, the live pages, and the code before acting.
- **Resume.** `resume/` holds the canonical resume versions
  (`GabrielJew_YYYYMM`); the newest is the source of truth.
