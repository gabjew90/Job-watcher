"""Scoring regression eval: scores the frozen case set with the CURRENT
prompt + rubric + feedback and grades each case against its labeled band.

Run: python -m src.eval_runner        (needs claude CLI auth)
CI runs it on any change to profile.md, feedback.md, or src/triage.py, and
it should be run before any backlog re-score.

Grading: exact band = PASS; adjacent band = WARN (passes, noted);
two or more bands off, or any top<->misfit confusion = FAIL (exit 1).
Also enforces the rules-have-cases invariant: feedback.md scoring rules
(calibration/more-like/less-like) must not outnumber feedback-sourced
eval cases.
"""
import json
import re
import sys
from pathlib import Path

from . import feedback, triage
from .models import Job

CASES = Path("eval/cases.json")


def main() -> int:
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
    print(f"\n{len(jobs)} cases: {len(jobs) - fails - warns} pass, "
          f"{warns} warn, {fails} fail")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
