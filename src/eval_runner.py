"""Regression evals for the two model gates, run against the CURRENT
prompts, rubric and feedback.

Run: python -m src.eval_runner              (both; needs claude CLI auth)
     python -m src.eval_runner scoring|screen    (one)

SCORING (eval/cases.json) scores each case and grades the FINAL band —
triage.score() now applies the code-side policy (the seniority cap), so
this grades the band production would store, not an intermediate one.
Exact band = PASS; adjacent = WARN; two or more bands off, or any
top<->misfit confusion = FAIL. Also enforces the rules-have-cases
invariant: every issue a feedback.md rule cites needs an eval case.

SCREEN (eval/screen_cases.json) runs the title screen over cases drawn
from postings it dropped in production that the full scorer then banded.
The errors are not symmetrical: keeping a posting that should drop costs
one Sonnet scoring (WARN), dropping one that should keep loses the role
outright (FAIL). The screen is the only gate with no second chance.

CI runs both on any change to profile.md, feedback.md, src/triage.py,
src/screen.py or eval/, and both should be run before a backlog re-score.
"""
import json
import re
import sys
from pathlib import Path

from . import feedback, screen, triage
from .models import Job

CASES = Path("eval/cases.json")
SCREEN_CASES = Path("eval/screen_cases.json")


def run_scoring() -> int:
    data = json.loads(CASES.read_text())["cases"]
    # Per-issue invariant: every issue a feedback.md rule cites must be
    # covered by an eval case citing the same issue. No aggregate counting,
    # no grandfathering.
    fb_text = re.sub(r"<!--.*?-->", "", Path("feedback.md").read_text(), flags=re.S)
    rule_issues = set(re.findall(r"#(\d+)", fb_text))
    case_issues = set()
    for c in data:
        case_issues.update(re.findall(r"#(\d+)", c["reason"]))
    uncovered = sorted(rule_issues - case_issues, key=int)
    if uncovered:
        print("FAIL invariant: feedback.md rules cite issues with no eval case: "
              + ", ".join(f"#{n}" for n in uncovered))
        return 1

    jobs, expect = [], {}
    for c in data:
        j = Job(title=c["title"], company=c["company"], location=c["location"],
                url="https://example.com/eval", source="eval",
                description=c["description"])
        jobs.append(j)
        expect[j.job_id] = c
    results = triage.score(jobs, feedback.load()["text"])

    order = triage.BAND_ORDER
    fails = warns = 0
    for j in jobs:
        c = expect[j.job_id]
        got = results.get(j.job_id, {}).get("band")
        if got is None:
            print(f"FAIL {c['id']}: no result returned")
            fails += 1
            continue
        want = c["expected_band"]
        gap = abs(order.index(got) - order.index(want))
        extreme = {got, want} == {"top", "misfit"}
        if got == want:
            print(f"PASS {c['id']}: {got}")
        elif gap == 1 and not extreme:
            print(f"WARN {c['id']}: got {got}, want {want} (adjacent)")
            warns += 1
        else:
            print(f"FAIL {c['id']}: got {got}, want {want} — {c['reason']}")
            fails += 1
    print(f"\n{len(jobs)} scoring cases: {len(jobs) - fails - warns} pass, "
          f"{warns} warn, {fails} fail")
    return 1 if fails else 0


SCREEN_PASSES = 2


def run_screen() -> int:
    """Grade the title screen over SCREEN_PASSES independent judgements.

    A missed keep is a FAIL: the screen decides before any description is
    read and remembers the drop, so nothing downstream recovers the
    posting. Production gets exactly one judgement, so a case the screen
    keeps only sometimes is a role it will sometimes lose — the keep has
    to hold in every pass. An over-keep costs one scoring call, so it
    warns, and warns on a majority rather than a single stray.
    """
    data = json.loads(SCREEN_CASES.read_text())["cases"]
    jobs, expect = [], {}
    for c in data:
        j = Job(title=c["title"], company=c["company"], location=c["location"],
                url="https://example.com/screen-eval", source="eval", description="")
        jobs.append(j)
        expect[j.job_id] = c

    passes = []
    for n in range(SCREEN_PASSES):
        verdicts = screen.judge(jobs)
        if not verdicts:
            print(f"FAIL: the screen returned no verdicts on pass {n + 1} "
                  f"(claude CLI unavailable?)")
            return 1
        passes.append(verdicts)

    fails = warns = 0
    for j in jobs:
        c = expect[j.job_id]
        got = [p.get(j.job_id) for p in passes]
        kept = sum(1 for g in got if g is True)
        tally = f"{kept}/{SCREEN_PASSES} kept"
        if c["expected_keep"]:
            if kept == SCREEN_PASSES:
                print(f"PASS {c['id']}: keep ({tally})")
            else:
                print(f"FAIL {c['id']}: dropped, should keep ({tally}) — {c['reason']}")
                fails += 1
        else:
            if kept * 2 > SCREEN_PASSES:
                print(f"WARN {c['id']}: kept, should drop ({tally}) — {c['reason']}")
                warns += 1
            else:
                print(f"PASS {c['id']}: drop ({tally})")
    print(f"\n{len(jobs)} screen cases over {SCREEN_PASSES} passes: "
          f"{len(jobs) - fails - warns} pass, {warns} warn (over-keep), "
          f"{fails} fail (missed keep)")
    return 1 if fails else 0


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    rc = 0
    if which in ("both", "scoring"):
        print("== scoring eval ==")
        rc |= run_scoring()
    if which in ("both", "screen"):
        print("\n== screen eval ==")
        rc |= run_screen()
    return rc


if __name__ == "__main__":
    sys.exit(main())
