# Job feedback & preferences

<!-- PLACEMENT RULE: this file holds CORRECTIONS from mis-scored postings,
each citing its GitHub issue and shipping an eval case for that issue
(enforced by eval_runner). The durable fit thesis and band definitions
live in profile.md. New entries are written in band vocabulary
(top / strong / possible / weak / misfit), not numeric scores. -->

Free-form notes that steer the daily scoring — this whole file is shown to
the scorer, so explain *why* and it will generalize. Lines starting with
`hide:` also hard-hide matching jobs (substring match on "title @ company",
case-insensitive) — they vanish from the dashboard and never appear in
digests, no LLM involved.

You can also file feedback from your phone: tap "feedback" on any dashboard
row — it opens pre-filled with how the posting was scored. Keep the issue
open while the preference should apply; close it to retire it.

## Active rules

- calibration: judge seniority from the DESCRIBED SCOPE, not the title
  alone. Read the description: owning strategy/programs/regions,
  cross-functional leadership, or executive-facing accountability reads
  senior even under a flat title ("Energy Manager" at Meta/Google/Amazon);
  stated pay ~$180k+ is a corroborating senior signal. Reserve
  seniority_match=false for roles whose described duties are genuinely
  junior, early-career, or trade-level. A flat-titled senior role with
  strong domain fit bands strong or top on its merits.
  (from Meta "Energy Manager, Power Delivery" — $202-273k, excellent
  domain fit, wrongly capped weak by title-based seniority)

hide: Staff Network Production Engineer @ Crusoe
hide: BESS Solutions Engineer @ EnerSys
hide: Underground Transmission Designer @ Westwood
hide: Lead Controls & Firmware Engineer @ Exowatt
hide: Solution Engineer - Structural Design @ Neara

- less-like: hands-on network/IT infrastructure engineering roles (network
  production engineer, site reliability, deployment engineering) — wrong
  field even at energy/datacenter companies. (from issue #19)
- less-like: deep technical design IC roles (transmission line designers,
  CAD/design engineers, protection & controls designers) — too far from
  product/strategy/commercial scope; score below 45. (from issue #21)
- calibration: commercial negotiation-LEAD roles (strategic negotiator,
  deal lead, PPA origination negotiator) should score 55-70, not 85+ —
  my negotiation experience is supporting/technical, not deal-lead.
  (from issue #22, re: Google Data Center Energy Strategic Negotiator)
- calibration: hardware/equipment development or equipment-procurement
  LEAD roles (e.g. power delivery equipment lead) score 55-65 — no direct
  equipment-development experience; product/strategy framing required for
  higher. (from issue #24, re: Anthropic Global Power Delivery Equipment
  Lead)
- more-like: product manager roles centered on BATTERY customer/product
  strategy are top fits (80+) — direct skillset match, even via staffing
  firms. (from issue #26, re: Product Manager – Battery Customer Strategy
  Lead)
- calibration: controls/firmware/embedded engineering and structural
  design engineering roles are out of skillset — below 35 even at
  mission-pure energy companies. (from issues #25, #28)
- calibration: technical interconnection STUDY/consulting roles at
  engineering firms (performing power-system studies, load flow, short
  circuit) should score 50-60 — too deep-technical. Interconnection
  strategy / program / product / hosting-capacity-platform roles remain
  high fits. (from issue #23, re: Sargent & Lundy Senior Grid
  Interconnection Consultant)

