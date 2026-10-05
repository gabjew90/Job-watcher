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
   His "submit" also covers the site's own confirm-before-submit dialog
   (e.g. Meta's "Submit anyway" after its AI qualification pre-check), so
   ask for approval of both in the same review: describe any such dialog
   or pre-check warning you already see, and say "submit" will confirm it.
2. **Never invent an answer.** If a question is not covered by
   `answers.md` or the resume, leave it, list it in the review, and ask.
   Add his answer to `answers.md` when he says it is a standing answer.
3. **Voluntary demographic questions**: use `answers.md`; where it says
   "ask", leave the question unanswered and say so in the review.
4. **Accounts**: if the site needs an account (Workday, iCIMS, Taleo),
   ask before creating one. Never write a password into this repo or into
   a commit; ask him to enter it or to keep it in his password manager.
5. **Gmail**: he has allowed reading his Gmail for (a) verification codes
   and (b) confirmation emails for applications just submitted (owner,
   2026-10-03). Search only for mail from the site being applied to, in
   the last hour (e.g. `(<company> OR <ats domain>) newer_than:1h
   in:anywhere`), and read nothing else.
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
   This is his running record of everything applied for (owner,
   2026-10-03): log every attempt, including ones not submitted (he
   declined, CAPTCHA, spam flag, account needed, posting closed), and add
   a new row when the status changes rather than leaving it out. When he
   asks what he has applied for, answer from this file.

## With Claude in Chrome (preferred)
When Claude runs on Gabriel's computer with access to his Chrome (the
Claude in Chrome extension, from Claude Code with `--chrome` or from the
Claude desktop app), use his Chrome instead of `form.py`: open the
application page in a tab, upload the newest `resume/GabrielJew_YYYYMM.pdf`
from this repo's folder, fill the form from `answers.md`, and send him a
screenshot plus the list of answers. Every rule above still applies: submit
only after his "submit", ask about anything `answers.md` does not cover,
and stop at a CAPTCHA or spam flag for him to handle. Run `git pull` in the
repo folder first so the answers and resume are current.

Lessons from 2026-10-03 (Meta):
- **Window size first.** A small Chrome window switches sites to their
  mobile layout, where floating panels (Meta's AI recruiting chat) cover
  the Submit button. Before filling, check `innerWidth` with
  `javascript_tool`; if it is under about 1200, call `resize_window`
  (1400x900) and close chat or assistant panels.
- **Check the window is not minimized before starting** (diagnosed
  2026-10-03). The extension works in its own tab group, which can sit in
  a separate Chrome window from the one he uses. When that window is
  minimized, `outerWidth`/`outerHeight` read 0 and `visibilityState` is
  "hidden": Chrome stops painting, so screenshots time out (CDP
  `Page.captureScreenshot`) and coordinate/ref clicks silently miss.
  `resize_window` reports success but cannot restore a minimized window.
  So, first thing: read `({outerWidth, outerHeight, vis:
  document.visibilityState})` with `javascript_tool`; if the size is 0,
  stop and ask him to restore that Chrome window (click it in the taskbar)
  and keep it un-minimized while the application runs. Do not guess at
  other causes. Until he does, element `.click()` via `javascript_tool` is
  acceptable for non-committing controls (cookie banners, menus, "Apply"),
  never for Submit. Never zoom the page with CSS to fit a screenshot.
- **Before clicking Submit**, confirm the button is the topmost element at
  its center (`document.elementFromPoint` on its bounding box). If
  something covers it, close that first.
- **Sites may add a confirm step after Submit** (Meta: a "Submit
  application" dialog with "Submit anyway"; responsive pages render
  duplicate buttons, so click the one that is visible and topmost).
  Nothing is sent until that step is confirmed.
- **Confirm the result two ways** before reporting or logging: the page's
  thank-you text, and a confirmation email (rule 5). If neither appears,
  find out why (covered button, confirm dialog, validation error) before
  clicking Submit again, so nothing is sent twice.

## Fallback: Playwright browser (2026-10-05)
If the Chrome tab cannot be used (it reports a 0x0 size and `find`,
`file_upload` or screenshots fail) and the site needs no login, use the
Playwright plugin (`mcp__plugin_playwright_playwright__*`) instead of
waiting on him. It runs its own visible Chromium on his computer and
network. Flow: `browser_navigate` to the form; click the upload button
(`browser_click`), then `browser_file_upload` with the resume path; set
plain fields with `browser_evaluate`; use `browser_type` (slowly) plus a
click on the suggestion for type-ahead boxes (Lever location); read every
value back; `browser_take_screenshot` with `fullPage` into
`.playwright-mcp/` (gitignored; the only folder it may write to) and send
it. All rules above still apply. Sites that need his login (Workday)
stay in his Chrome.

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
- **Meta** (metacareers.com): no account needed (the Career Profile
  account is optional; leave its password fields empty). Resume upload
  autofills name, email, phone and location; check them. Asks which office
  locations (select all, per answers.md). Submit opens an AI pre-check
  dialog; confirm with the visible "Submit anyway".
- **Greenhouse / Lever**: usually no account; demographic questions are
  dropdowns (`select`). Lever (Intersect): plain HTML form; custom
  questions are `cards[<id>][fieldN]` and the DEI survey is
  `surveysResponses[...]`; LinkedIn can be required (he says enter
  "n/a"); fetch the posting page (URL without `/apply`) for the pay range
  and requirements.
- **Workday** (most utilities, Fluence, AEP, Talen, Vantage): requires an
  account and email verification; ask first (rule 4). Flow: Apply ->
  "Autofill with Resume" -> Create Account/Sign In (he enters the
  password himself) -> 7 steps: My Information, My Experience,
  Application Questions, Voluntary Disclosures, Review. The page has a
  hidden "for robots only" website field: never fill it.
  Lessons (Vantage, 2026-10-03):
  - Resume autofill truncates titles (drops ", Grid-Scale BESS"),
    shortens schools ("University of California" for UC Davis) and can
    glue the next resume section onto the last job's description. Fix
    all of it on the first pass through My Experience.
  - **Never go Back to My Experience after saving it.** On a revisit,
    Workday keeps only the entries whose text changed in that visit and
    drops the rest. If you must, delete every work entry and re-add all
    of them fresh from the resume in one visit, then confirm the count
    on Review.
  - Dropdowns: open, then pick with arrow keys + Enter (a mouse click can
    land on the wrong option), and read every dropdown back afterwards.
  - Before asking for "submit", read the whole Review page back
    (job count, titles, dates, answers), not just screenshots.
