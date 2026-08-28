# Job feedback & preferences

Free-form notes that steer the daily scoring — this whole file is shown to
the scorer, so explain *why* and it will generalize. Lines starting with
`hide:` also hard-hide matching jobs (substring match on "title @ company",
case-insensitive) — they vanish from the dashboard and never appear in
digests, no LLM involved.

You can also file feedback from your phone: tap "feedback" on any dashboard
row — it opens a pre-filled GitHub issue. Keep the issue open while the
preference should apply; close it to retire it.

## Active rules

hide: Staff Network Production Engineer @ Crusoe
hide: BESS Solutions Engineer @ EnerSys
hide: Underground Transmission Designer @ Westwood

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
- calibration: technical interconnection STUDY/consulting roles at
  engineering firms (performing power-system studies, load flow, short
  circuit) should score 50-60 — too deep-technical. Interconnection
  strategy / program / product / hosting-capacity-platform roles remain
  high fits. (from issue #23, re: Sargent & Lundy Senior Grid
  Interconnection Consultant)

## Examples (delete these, they're inert until you write real ones)

<!--
hide: Transmission Planning Engineer @ ICF

- less-like: pure IC engineering roles even in the right domain — I'm
  targeting director/senior-PM scope, not hands-on design work.
- more-like: Senior Director, Energy Systems @ Vantage Data Centers —
  director scope, datacenter operator, energy systems ownership, remote.
- Roles at battery OEMs competing with my current employer are fine to
  show but score them a bit lower; conflict-of-interest concerns.
-->
