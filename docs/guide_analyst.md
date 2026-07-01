# Analyst guide

*For modellers and researchers running analyses — choosing an engine, a scenario,
and a solver, and reading the results.*

Garuda exposes **one zonal data core** to several **engines**, each matched to a
different question and compute budget. Start here, then drill into
[`MODEL.md`](../MODEL.md) (formulation) and [`outputs_guide.md`](outputs_guide.md)
(results).

## Pick the engine that fits the question

| Engine | Question | Cost | How to run |
|---|---|---|---|
| **Screening** | Where does this zone stand today? (emissions, RE share, reliability gap of the *existing* fleet) | none — arithmetic | `python tools/screening.py <folder>` |
| **RE resource** | What renewable headroom does a zone/site have? | none | `python tools/re_resource.py <folder>` |
| **Dispatch / reliability** | How does a *given* fleet run, and where does it fall short? (hourly dispatch, LOLE, shortage) | LP — fast | config `"engine":"dispatch"` |
| **Capacity expansion** | What is the least-cost fleet to *build*? | MILP | `run_model.jl` (default) |

The first two run on a laptop with only Python (no Julia, no solver). The latter
two share **one model definition** (`build_model!`), so dispatch and expansion are
guaranteed consistent — dispatch just fixes capacity to the existing fleet and (by
default) relaxes unit commitment to a fast LP.

## The fastest path: the launcher

```bash
python tools/launcher.py --island maluku --year 2030 --scenario base \
    --clean reference --engine dispatch          # validate + preview + scaffold
python tools/launcher.py … --run                 # …then launch run_model.jl
```

It validates the inputs, previews the scenario size (zones, generators, sites,
representative hours) with a runtime estimate, scaffolds `config.json`, and
optionally launches. See [`experience_layer.md`](experience_layer.md).

## Scenarios and the clean flag

The `scenario` sets two toggles — whether the **grid** is active and whether the
**site** layer is built (`functions/preflight.jl::scenario_settings`):

| scenario | grid | sites | note |
|---|---|---|---|
| `base` | off | off | grid zones only, islanded sites |
| `grid` | on | off | grid only, interconnected |
| `village` / `captive` | off | on | sites only (islanded microgrids / IPs) |
| `gridvillage` / `gridcaptive` | on | on | **co-optimised** — the coordination case |
| `nocoal` | on | off | grid scenario, no-coal variant (restricts onsite generation to renewables) |
| `highimportprice` | on | on | sensitivity on the site grid-import price |

`clean` is `reference` (no policy constraint) or `clean` (applies a CO₂ cap and a
renewable-share floor). The `village`/`gridvillage` pair on the same island/year is
the headline comparison — its delta is the **coordination value**
([`village_adaptation.md`](village_adaptation.md), [`outputs_guide.md`](outputs_guide.md)).

## Solver and unit-commitment fidelity

- **HiGHS** (default) — open-source, no licence. Excellent for the LP engines
  (screening, dispatch) and small/medium MILPs; **slow on the full UC-MILP** at
  scale (a `timor_demo` expansion took ~27 min vs ~5 s on Gurobi).
- **Gurobi** (`"solver":"gurobi"`) — the fast path for full capacity expansion;
  needs a (free academic) licence.
- **`"relax_uc"`** LP-relaxes the commitment binaries. It is the **dispatch**
  default (a fast operational LP) and can also be set on **expansion**
  (`"engine":"expansion","relax_uc":true`): the build problem becomes an LP that
  solves in **seconds on HiGHS** — within **~0.8 %** of the exact MILP cost on
  `timor_demo` (a measured lower bound; the relaxed fleet is optimistic where
  commitment binds). This is the highest-leverage open-source-fast path; a faster
  *MILP* solver only matters when you need exact UC. Default **off** for expansion
  (decision-grade); set `relax_uc:false` to force the exact MILP in dispatch too.

The launcher writes the config — the required keys (`island`, `year`, `scenario`,
`clean`, `CO235reduction`, `BAUCO2emissions`, `CO2_limit`) plus `engine`, `solver`,
`relax_uc` and `mipgap` (0.01). `run_model.jl` accepts three further keys, read
with a default when absent (the launcher does **not** scaffold these — add them by
hand if needed): `RE_limit` (0.34), `import_price` (59.0),
`village_storage_max_mwh` (208.0).

## Reading results

Each run writes `results/<scenario>_<island>_<year>_<clean>/`. Generate a
shareable summary:

```bash
python tools/report.py results/gridvillage_timor_demo_2030_reference   # HTML + PDF
```

Full file/column reference: [`outputs_guide.md`](outputs_guide.md). Site tables use
the canonical `site_*` names; a dispatch run adds `*_reliability_results.csv`.

## Cross-tool validation

Export to PyPSA and re-solve to cross-check, or to run PyPSA's own analyses:
`python tools/validate_pypsa_parity.py <folder> --reference <results_dir>`
([`pypsa_export.md`](pypsa_export.md)).

## Caveats that change interpretation

- **Representative periods.** Results are over `Rep_Periods × Timesteps` sampled
  hours, annualised by non-uniform `Sub_Weights` — not a chronological 8760.
- **Dispatch is optimistic.** The LP relaxation (and the PyPSA export) omit
  start-up costs and minimum up/down time, so reported unserved energy is a
  lower-ish bound where commitment binds. Use `relax_uc:false` for an exact (slow)
  UC dispatch.
- **MIP gap.** Expansion stops at a 1 % optimality gap by default — two solvers can
  return different incumbents within tolerance.
- **Trust the data, not just the model.** Inputs are research-grade; flags can
  carry surprises (e.g. some existing diesel/gas units are tagged `RE=1` in places,
  inflating the reported RE share). Sanity-check headline numbers against the
  no-solver screen before quoting them.
