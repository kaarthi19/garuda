# A sub-national, open-source planning platform for Indonesia's energy transition
### Capability note for [IESR / ESDM–BAPPENAS / development partners]

*Draft for discussion — [author], [affiliation], 2026-06*

---

## The opportunity

Indonesia's energy transition turns on decisions that are set nationally but land
sub-nationally: the **100 GW solar** ambition, the **JETP** power-sector emissions
ceiling, and universal electrification all have to be delivered island by island,
zone by zone, and — for the hardest-to-reach demand — village by village. Two
questions decide whether plans move: **what to build where and by when** (the
least-cost pathway), and **how decentralised and grid options coordinate** (whether
a community is served most cheaply by village solar-plus-storage, by extending the
grid, or by both). National and utility plans answer the first only at the
grid/province level and rarely address the second at all — yet that is exactly where
the 100 GW programme and the eastern-Indonesia electrification challenge live.

This note describes a capacity-expansion + dispatch platform built to answer those
questions at **sub-national, down-to-the-site resolution**, as a **transparent,
stakeholder-operable** complement to existing national planning — not a replacement
for it.

## What the platform provides

**1. Sub-national, site-level resolution (the differentiator).**
The model resolves Indonesia as islands → grid **zones** → individual **village /
industrial sites**, each with its own demand, renewable resource, and distance to
the grid. It can separate, e.g., the hundreds of villages within a single Timor
*kabupaten*, or the province-level zones inside Sulawesi — heterogeneity that
country- or grid-level models average away. *This is the lead capability.*

**2. Decentralised–grid co-optimisation (the 100 GW question).**
For each site the model co-optimises village solar + storage + existing diesel
against grid extension and reinforcement, and reports the **coordination value**:
grid build avoided, diesel displaced, reliability gained, and the least-cost split
between islanding and interconnection. This is the decision rural electrification
and the 100 GW programme actually face, and it is invisible to a grid-only model.

**3. One data core, several analysis modes.**
The same zonal dataset drives capacity-expansion pathways, **dispatch / reliability**
screening, a **no-solve emissions / cost / RE screen** (instant, no solver, for rapid
what-ifs), renewable **resource & siting** assessment, and **export to open tools**
(e.g. PyPSA). Stakeholders match the analysis to the question instead of running one
heavy model for everything.

**4. Open-source, transparent, reproducible.**
The platform runs on the open **HiGHS** solver — no commercial licence — so any
ministry, developer, or researcher can run and audit it. Results are
byte-reproducible, with an internal verification guarantee: every change is
cross-checked against the reference model's objective, and any future
fast-solver decomposition is held to a *measured* optimality gap rather than an
assumed one. An auditable model also surfaces and corrects errors that proprietary
tools hide — work on this platform has already found and fixed two modelling bugs
in the inherited code. For plans that several institutions must trust, transparency
is a political asset and reduces dependence on proprietary, consultant-run tools.

## How it fits the existing landscape

- **Complements** national and utility planning (PLN's **RUPTL**, the national
  **RUKN**) by adding sub-national zonal and site resolution and the
  decentralised-coordination view those plans do not carry; where scopes overlap,
  results can be **cross-validated** rather than duplicated.
- **Complements** the IESR / UCSD 100 GW solar analysis and academic system
  modelling by sitting closer to the siting-and-coordination decision — zone by
  zone, site by site, auditable.
- An **open-source complement** to proprietary tools (PLEXOS and similar), and
  interoperable with open frameworks (PyPSA) via export.

## Honest readiness and the work to get there

The platform is built on an **established capacity-expansion + unit-commitment model**
(the IESR / UCSD 100 GW village-solar study, with a worked **Timor / NTT** case) and
carries **zonal datasets for all major islands** — Sumatra, Java–Bali, Kalimantan,
Sulawesi, Maluku, North Maluku, Nusa Tenggara, Papua — for 2030 and 2035. The
modelling core is validated by exact reproduction of the source study; the *platform*
layer (the parts that make it broadly usable) is in active development. To be
decision-grade it needs, in priority order:

1. **Open-source runnability** — HiGHS as the default solver, so the tool needs no
   commercial licence to run end-to-end. *(In progress; the headline enabler for
   stakeholder use.)*
2. **Published data provenance** — replace research-grade inputs with official
   sources (PLN RUPTL inter-zonal limits and generation data, ESDM / RUKN demand) per
   zone, turning resolution into credibility.
3. **Input validation, the analysis engines, and non-expert reporting** — a schema
   validator that catches bad inputs before a solve, the dispatch/reliability and
   no-solve screening engines, and auto-generated reports with maps and headline
   metrics.
4. **Validation against an authoritative reference** — reproduce and explain a
   published island or national plan before extending.

These are data, validation, and engineering tasks on a working modelling core — not
a model redesign — and are well-suited to partner-supported, locally-hosted
development.

## Proposed first step

A scoped demonstration on Indonesia's own terms: take the **Timor / NTT case** and
show (a) the per-village least-cost electrification mix and (b) the coordination
value the model exposes — how much grid reinforcement and diesel are avoided when
village solar and grid expansion are planned *together* — alongside a per-zone cost
and emissions breakdown. One deliverable shows what the sub-national, site-level
layer adds to the 100 GW and electrification discussion.

We propose a short scoping conversation with [IESR / ESDM–BAPPENAS / development
partners] to define that demonstration and the data-access path.

---

*Methodology: linear capacity-expansion with unit-commitment dispatch, solved on the
open-source HiGHS solver (Gurobi optional); a sub-national zonal network with
village / industrial-site nodes co-optimised against grid expansion, priced
non-served energy, and policy constraints (a JETP-style CO₂ cap and renewable-share
floor). Outputs include per-zone and per-site capacity, generation, cost, emissions
and reliability, plus the decentralised–grid coordination value and interconnection
decisions.*
