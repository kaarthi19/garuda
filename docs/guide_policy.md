# Policy guide

*For government and development-partner stakeholders: what Garuda answers, how to
read a result, and what to be careful about — no modelling background assumed.*

You do not need to run the model to use this guide; it explains how to interpret a
Garuda report and where the tool fits. To commission a run, an analyst can follow
[`guide_analyst.md`](guide_analyst.md) and hand you the auto-generated report.

## What Garuda is — and isn't

Garuda is a **site-resolution coordination layer** for Indonesia's power system.
It resolves the country as **islands → grid zones → individual village /
industrial sites** and, in one model, co-optimises the *distributed* decision
(village solar + storage + diesel, or an industrial park's captive power) **with**
the zonal grid's expansion and hour-by-hour operation.

It is deliberately **not** another national system-planning tool. It complements
the layers already well served:

- **System / regional models** (PLN's RUPTL, the national RUKN, TransitionZero's
  Scenario Builder) decide the GW-scale, transmission-level pathway. Garuda goes a
  layer deeper, to the site, and **exports to PyPSA** so the two can be
  cross-checked rather than duplicated.
- **Electrification tools** (World Bank GEP / OnSSET) choose grid vs mini-grid vs
  stand-alone *per community*. Garuda adds what they omit — co-optimising those
  site choices against grid generation and dispatch.

The defensible claim is narrow: Garuda answers *what to build where, how a fleet
operates, and the coordination value between distributed and grid solutions* — at
a resolution national models average away.

## The questions it answers

- The least-cost mix per site: islanded solar+storage+diesel, grid extension, or
  both — and the **coordination value** (grid reinforcement and diesel avoided when
  the two are planned *together* rather than separately).
- Per-zone capacity, generation, cost, emissions, and **reliability** (where and
  how often the fleet falls short).
- How a transition pathway changes under a **clean** policy (a CO₂ cap and a
  renewable-share floor) versus a reference case.

## Reading a report — the headline metrics

The auto-report ([`experience_layer.md`](experience_layer.md)) leads with:

| Metric | Plain meaning |
|---|---|
| **Total system cost (M$/yr)** | annualised cost of the modelled system — the number to compare *across scenarios*, not in absolute terms |
| **CO₂ emissions (ktCO₂/yr)** | annual power-sector emissions in scope |
| **Grid RE share (%)** | share of grid generation from resources flagged renewable (read with care — see caveats) |
| **Annual demand / Energy served (GWh)** | electricity demanded vs actually met |
| **Unserved energy (GWh) and share (%)** | reliability shortfall — energy demand the fleet could **not** meet |

The single most useful comparison is **two scenarios side by side** on the same
island and year — e.g. `village` (everyone islanded) vs `gridvillage`
(coordinated). The *difference* in cost, emissions, reinforcement and unserved
energy is the policy-relevant result, not any one absolute figure.

## Scenario language, in plain terms

- **village / captive** — communities or industrial parks stand alone.
- **gridvillage / gridcaptive** — they are coordinated with the grid (the
  100 GW-programme question). The gap to the standalone case is the coordination
  benefit.
- **reference vs clean** — `clean` imposes a JETP-style CO₂ cap and a minimum
  renewable share; `reference` does not. Comparing them shows the cost and build
  implications of the policy.

## What to be careful about

A model is a decision aid, not an oracle. Before quoting a number:

1. **Data provenance is research-grade.** The inputs are credible but not yet
   replaced with official PLN/ESDM/RUKN figures per zone and site. Treat results as
   *directional and comparative* until provenance is upgraded — this is the top
   item on the path to decision-grade use.
2. **A representative-week sample, not a full year.** The model runs on sampled
   representative periods weighted to a year — robust for annual totals, not for
   any specific date.
3. **Reliability numbers are optimistic by default.** The fast open-source dispatch
   relaxes some thermal-plant operating limits, so unserved energy is a lower-ish
   estimate where those bind.
4. **The "RE share" can be mislabelled.** It follows a per-unit renewable flag in
   the data, and in places some existing fossil units carry that flag — which can
   inflate the figure. Cross-check against the generation mix in the same report.
5. **Costs are comparative.** Use cost differences between scenarios; the absolute
   M$/yr depends on modelling scope.

## Open, auditable, reproducible

Garuda runs on the open-source **HiGHS** solver — no commercial licence — so any
ministry, developer or researcher can run and audit it, and results are
byte-reproducible. An auditable model also surfaces errors proprietary tools hide
(this work has already found and corrected modelling bugs in the inherited code).
For a plan several institutions must trust, that transparency is itself a feature.
