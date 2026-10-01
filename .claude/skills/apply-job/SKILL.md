---
name: apply-job
description: Apply to a job for Gabriel using his canonical resume and standard answers. Use when he says "apply to <job>", pastes a posting or application URL, or asks to apply to a role from the job-watcher digest or dashboard. Fills the employer's application form in a browser, shows him a screenshot, and submits only after he says "submit".
---

# Apply to a job

Fill an employer's application form with Gabriel's resume and answers,
show him exactly what will be sent, and submit only on his explicit
approval.

## Inputs (paths from the Job-watcher repo root)
- `.claude/skills/apply-job/answers.md`: his confirmed answers. The only
  source for form answers.
- `resume/`: canonical resume versions, named `GabrielJew_YYYYMM`; use the
  newest. The only source for work history, titles, dates and education.
- `.claude/skills/apply-job/form.py`: the browser helper (one Chromium kept
  open between steps, so the form that was reviewed is the one submitted).
- `applications/log.md`: one line per application.

## Rules
1. **Never submit without approval.** Before submitting, send a full-page
   screenshot of the filled form and a list of every answer given, then
   stop. Submit only after he replies "submit" (or clearly approves) for
   that application. Approval for one application never covers another.
2. **Never invent an answer.** If a question is not covered by
   `answers.md` or the resume, leave it, list it in the review, and ask.
   Add his answer to `answers.md` when he says it is a standing answer.
3. **Voluntary demographic questions**: use `answers.md`; where it says
   "ask", leave the question unanswered and say so in the review.
4. **Accounts**: if the site needs an account (Workday, iCIMS, Taleo),
   ask before creating one. Never write a password into this repo or into
   a commit; ask him to enter it or to keep it in his password manager.
5. **Verification codes**: he has allowed reading his Gmail for them.
   Search only for the code from the site being applied to, sent in the
   last 15 minutes (e.g. Gmail search `from:<ats or company domain>
   newer_than:1h`), use it, and read nothing else.
6. **CAPTCHA or spam flag**: do not try to defeat one. Tell him and stop.
7. Do not write a cover letter or free-text essay unless he asks; if one
   is required, draft it from the resume only and include it in the review.

## Steps
1. **Find the form.** From the posting URL, open the application page
   (Ashby: append `/application`; Greenhouse and Lever: the posting page
   holds the form). If the job came from the job-watcher, prefer the
   employer link over an Indeed link.
2. **Start the browser** (cloud container): trust the proxy CA once, then
   start Chromium:
   ```bash
   certutil -A -d sql:$HOME/.pki/nssdb -n ccr-agent-proxy -t "C,," -i /root/.ccr/agent-proxy-ca.crt   # needs libnss3-tools
   python .claude/skills/apply-job/form.py start
   python .claude/skills/apply-job/form.py open "<application url>"
   ```
3. **Read the form**: `python .claude/skills/apply-job/form.py inspect` lists every field
   with its question, type, options and a selector.
4. **Plan the answers** in a JSON plan (see `form.py` for actions:
   `fill`, `check`, `select`, `upload`, `type` for type-ahead boxes,
   `choose` for Yes/No buttons by question text). Upload the resume file;
   do not retype the resume into fields an upload already filled, but
   check what autofill put there and correct it.
5. **Fill and check**: `python .claude/skills/apply-job/form.py fill plan.json`, then
   `inspect` again and a screenshot (`shot review.png`). Every required
   field must be filled or listed as a question for him.
6. **Review**: send him the screenshot plus a short list: answers given,
   fields left blank and why, questions for him. Then stop and wait.
7. **Submit** after approval: `python .claude/skills/apply-job/form.py click "Submit Application"`
   (use the button's own text), then `text` and a screenshot to confirm the
   site's thank-you message. If a verification code is requested, follow
   rule 5. Report the outcome plainly, including any error the site shows.
8. **Log** it in `applications/log.md`: date, company, title, URL,
   submitted or not, and anything he should follow up on. Commit and push.

## Where to run it
Run the skill in Claude Code on Gabriel's own computer, so the browser uses
his network. From the cloud container, the browser is an automated
Chromium behind a proxy on a data-center address, and spam filters block
the submission: Ashby rejected the 2026-10-01 Crusoe application as
"flagged as possible spam" after the form was filled correctly. In the
cloud, fill and review only; if a site flags the submission, stop, tell
him, and do not retry around the filter (repeated attempts can get his
email flagged). On his computer, start the browser with a visible window
(`HEADLESS=0`) when a site is strict.

## Site notes
- **Ashby** (Crusoe, many AI-infrastructure startups): no account. Yes/No
  questions are buttons (`choose`); location questions are type-ahead
  (`type`). Has an "Autofill from resume" box; ignore it and use the
  Resume upload field.
- **Greenhouse / Lever**: usually no account; demographic questions are
  dropdowns (`select`).
- **Workday** (most utilities, Fluence, AEP, Talen): requires an account
  and email verification; ask first (rule 4).
