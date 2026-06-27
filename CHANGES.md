# Garuda — Development Log

**Garuda** is an open-source, stakeholder-facing **zonal energy-transition
platform for Indonesia**. It is being built on the zonal power-system model
inherited from `village-indonesia-100gw`, evolving that research model into a
layered platform:

- **Layer A — Data Core:** the zonal model itself (zones, transmission,
  generators, demand, RE resource, sites, fuels, costs) as a standalone,
  validated, documented asset — engine-agnostic.
- **Layer B — Engines:** capacity expansion (inherited), dispatch/reliability,
  no-solve accounting, RE resource & siting, and open-format (PyPSA) export.
- **Layer C — Experience:** a thin guided on-ramp (validation + auto-reports).

Design rules: engines never own the data; the experience layer never wires
straight to the optimizer. Open-source-first (HiGHS default; Gurobi optional).

**This file is the authoritative, chronological record** of every change made
while building the platform. Each entry says *what*, *why*, and *how to verify*.

---

## Phase 0 — Stand up the platform repo + name the data core

### 0.1 Snapshot-fork from `village-indonesia-100gw` — 2026-06-26

Created `garuda` as a **clean snapshot-fork** (no upstream git history) of
`village-indonesia-100gw` at commit
`1096aa48ff5829e7679a1252b2b84a2b79d07750` (`1096aa4`, *"Add GIS solar-land
resource assessment; wire per-village solar caps"*).

**Why a fork rather than changes in place or a branch.** The source repo is an
active research project; the platform must develop in complete separation and
will diverge architecturally (de-monolithing the optimizer, multiple engines).
`village-indonesia-100gw` is left **untouched**; future data/model fixes there
flow into garuda only by deliberate cherry-pick. Once the data core stabilises,
the shared model may be factored into a Julia package both repos can use
(deferred decision).

**Copied in:** `functions/`, `tools/`, `data_indonesia/`, `docs/`, `templates/`,
`tests/`, `scenario_*.yml`, `generate_jobs*.py`, `run_model.jl`, `bootstrap.jl`,
`Project.toml`, `Manifest.toml`, `README.md`, `MODEL.md`, `LICENSE`.

**Excluded:** `.git` (garuda has its own), `jobs/` and `results/` (run artifacts
— now gitignored), `.claude` and `.DS_Store` (local cruft), `__pycache__/`,
`*.pyc`, `*.log`.

**Command:**
```bash
rsync -a --exclude='.git' --exclude='jobs' --exclude='results' \
  --exclude='.claude' --exclude='.DS_Store' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='*.log' \
  .../village-indonesia-100gw/ .../garuda/
```

**Also:** added `jobs/` and `results/` to `.gitignore`; added a
provenance/status banner to `README.md` pointing here.

**Verify:** the next step reproduces a known result from the source repo
*before* any code change, proving the fork behaves identically (Phase 0.5).

### 0.2 `ZonalSystem` data-core type + `build_system()` — 2026-06-26

Introduced the **Layer A data-core type** so every engine dispatches on one
named, documented contract instead of an anonymous NamedTuple.

**New file `functions/zonal_system.jl`:**
- `struct ZonalSystem` wraps the loader's data; `Base.getproperty` forwards field
  access to the wrapped NamedTuple, so existing engine code (`inputs.G`,
  `inputs.demand`, …) is unchanged. The raw NamedTuple stays available as
  `sys.data`.
- `build_system(filepath)::ZonalSystem` — a drop-in for `input_data` on the solve
  path.

**`functions/function_compiler.jl`:** includes `zonal_system.jl` and loads via
`build_system(filepath)` instead of `input_data(filepath)` (the variable is still
`inputs`, so `optimizer.jl` / `result_extraction_function.jl` are untouched).

**Why a forwarding wrapper, not a flat 48-field struct:** zero risk of field
drift, nothing to keep in sync, identical property access guaranteed. Verified
safe first: a grep showed no NamedTuple-specific use of `inputs` in `functions/`,
and `input_data` / `capacity_expansion` each have exactly one caller
(`function_compiler.jl`).

**Verified (no solver needed):** `julia --project=. /tmp/verify_zonal.jl` →
*"ZonalSystem forwards all 48 fields by identity; build_system matches
input_data"* on the `timor_demo` dataset. End-to-end solve reproduction is done
in Phase 0.5.

`input_data` itself is left intact (the Layer A loader); `ZonalSystem` is purely
additive.

### 0.3 `site` vocabulary with `village_*` / `ip_*` aliases — 2026-06-26

Made **`site`** the canonical platform term for a decentralised node within a
zone, while accepting the two inherited spellings so both dataset families load
unchanged: `village_*` / `Village` (100 GW village-solar study) and `ip_*` /
`Industrial_Park` (captive-industrial study). New datasets can use the canonical
`site_*` / `Site` / `demand_site<i>` spelling.

**New file `functions/site_aliases.jl`:** `resolve_site_csv(dir, base)`
(site_→village_→ip_ filename resolution), `site_id_col(df)`
(Site|Village|Industrial_Park), `site_demand_col(df, i)`
(demand_site|village|ip`<i>`).

**`functions/input_data.jl`:** six I/O-boundary edits route the site tables
(generators, demand, demandheat, generators_variability, connection) through the
resolver, and normalise the site-ID column back to the internal name `Village`.
Because `optimizer.jl` indexes site demand **positionally** (`village_demand[t,
vil]`) and only references the ID column as `.Village`, nothing downstream
changes — the returned `ZonalSystem` is identical regardless of spelling.

**Scope:** this is the *accommodation* for captive (deferred): the alias
mechanism is in place and unit-tested on the `ip_*` / `Industrial_Park` spelling,
but full captive-dataset ingestion (extra IP metadata columns) remains Phase 6.

**Verified (no solver):** `/tmp/verify_site_aliases.jl` builds a `site_*`-spelled
copy of `timor_demo` and asserts it loads byte-identically to the `village_*`
original (VIL / VIL_G / VIL_STOR, village_zone, demand & variability matrices, and
the derived Var_Cost / CO2_Rate / Start_Cost columns all equal); the ZonalSystem
forwarding regression still passes.

### 0.4 Read `zones.csv` into `zone_names` — 2026-06-26

`zones.csv` (present for multi-zone islands: jawa_bali, kalimantan, sulawesi,
sumatera) was authored but **never read** — the model knew zones only as
integers. Added `functions/zones.jl::read_zone_names(path)` and wired it into
`input_data`, so the loaded `ZonalSystem` now carries
`zone_names :: Dict{Int,String}` (zone integer → human-readable name). Empty when
`zones.csv` is absent (e.g. single-zone / `timor_demo`). This feeds readable
reports and named buses on open-format export.

The reader is tolerant of the real schema: a `province,zone` layout with a
`z`-prefixed label (`z1` → `1`), a header BOM, and `province` / `zone_name` /
`name` / `system` spellings of the name column.

**`data_indonesia/README.md`:** updated the `zones.csv` row (no longer "never
read by the code").

**Verified (no solver):** `/tmp/verify_zones.jl` — sulawesi yields 6 names with
every modelled zone covered (`1 => north_sulawesi`, `2 => gorontalo`,
`3 => central_sulawesi`, …); `timor_demo` loads with an empty map; a missing file
→ empty map. The site-alias and ZonalSystem-forwarding (now 49 fields)
regressions still pass.

### 0.5 End-to-end verification — Phase 0 reproduces the import byte-for-byte — 2026-06-26

Definitive proof the data-core refactor changes no results.

- **Byte-identical solves.** Solved `timor_demo` `village` + `gridvillage`
  (Gurobi, academic licence) on the refactored branch and on the pristine `main`
  import. Objectives match exactly — village `2.366093688239e7` ($23.6609369M),
  gridvillage `2.355655499305e7` ($23.5565550M) — and `diff -rq` over every
  result CSV reports no differences.
- **Layer A regression test** consolidated into `tests/verify_data_core.jl` (no
  solver): 12 checks across ZonalSystem forwarding (49 fields), the
  site_/village_/ip_ alias path (a synthesised `site_*` copy loads identically),
  and zones.csv → zone_names. All pass.
- **Inherited suite:** `tests/test_fishing_calculator.py` → 4 passed.

**Phase 0 complete.** The platform repo stands as a clean fork with a named,
documented, alias-tolerant Layer A data core, provably behaviour-preserving.
Work landed on branch `phase-0-data-core`.

---

## Fixes — model correctness (branch `fix-commit-state-leak`, 2026-06-26)

Two latent bugs surfaced during the Benders-feasibility analysis (both inherited
from `village-100gw@1096aa4`; flagged for village-100gw and captive-2025).

### F1. Commitment state leaked across representative periods

`cCommitState` (grid) and `cVILCommitState` (village) ran the commitment
recursion `vCOMMIT[t+1] == vCOMMIT[t] + vSTART[t+1] − vSHUT[t+1]` over the full
horizon (`inputs.T_red`), threading commitment from each representative week into
the next — unlike SOC/ramps, which are period-cyclic via a `…Wrap` on `START`.
Representative weeks are independent samples, so this spuriously coupled them.
Fixed to mirror SOC/ramps: recursion on `INTERIOR` (`t-1`) + new
`cCommitStateWrap` / `cVILCommitStateWrap` on `START` (wrap to
`t+hours_per_period-1`), so each representative period is cyclic and independent.

**Re-baselines results where commitment binds** (the new values are the
physically correct ones; the direction varies):

| case | before (buggy) | after (fixed) | Δ |
|---|---|---|---|
| timor_demo village | 23.6609M | 23.5769M | −0.36% |
| timor_demo gridvillage | 23.55655M | 23.55655M | 0 (non-binding) |
| maluku base | 87.786M | 88.012M | +0.26% |

On maluku, the buggy version let thermal commitment carry across representative
weeks, under-counting start-ups and making the island look ~0.26% **cheaper** than
reality. `87.786M` matches the prior published maluku figure — the corrected value
is `88.012M`. (`commit d05cfa0`.)

### F2. Grid-only scenarios crashed on missing site `Max_Cap_MW`

The empty `village_generators` fallback (built when a dataset has no site
generators — `base`/`grid`/`nocoal` on grid-only islands) lacked a `Max_Cap_MW`
column, which `optimizer.jl` indexes; this threw *"column :Max_Cap_MW not found"*
before the solve. Added `Max_Cap_MW = Float64[]` to the fallback; maluku base now
solves. (`commit 594befb`.)

**Verified (absolute paths):** timor_demo (village + gridvillage) and maluku base
solve to optimality; `tests/verify_data_core.jl` (12 checks) still passes. Branch
`fix-commit-state-leak`, not yet merged to main.

> Process note: an earlier verification of these fixes accidentally ran in the
> `village-100gw` working tree (shell cwd), not garuda. village-100gw was restored
> to untouched; all model runs now use absolute paths.

---

## Decision — Benders decomposition (deferred)

Verified by a multi-agent feasibility analysis (see the roadmap). Conclusions:
exact Benders can preserve precision, but "exact + open-source + fast" is
pick-two. **Decisions:** precision bar = **relaxed-UC Benders on HiGHS with the
UC integrality gap measured empirically** (not bit-exact integer monolith);
**deferred** until after the `build_model!` extraction (Phase 2) + a scaling
assessment (the binding dimension at scale is *sites*, not time, so period-
decomposition may be the wrong axis). Prerequisites: the F1 commit-state fix
(done) and `build_model!`. The inherited `benders_decomposition.jl` is a broken
reference (scalar-floor cut, dropped policy constraints) — not a starting point.

---

## Phase 1 — Open & safe (HiGHS default + schema validator)

### 1.1 Pluggable solver — HiGHS default, Gurobi optional — 2026-06-26

The model hardcoded `Model(Gurobi.Optimizer)`. Added `functions/solver.jl`
`make_solver(solver; mipgap, time_limit)` mapping each solver's attributes (HiGHS
`mip_rel_gap`/`time_limit`; Gurobi `MIPGap`/`TimeLimit`/`Crossover`). Threaded a
`solver` parameter through `capacity_expansion` → `function_compiler` →
`run_model.jl`, selected by a config key `"solver": "highs"|"gurobi"` (default
**highs**). `using Gurobi` is now conditional (imported only when requested);
`preflight.jl`'s `validate_gurobi` → `validate_solver`; `bootstrap.jl` validates
HiGHS — so **a fresh setup needs no commercial licence**. HiGHS added to
Project/Manifest.

**Verified:**
- **Gurobi opt-in** (`"solver":"gurobi"`): timor_demo village solves in ~5 s to
  23.5769M — exact match to the post-fix baseline; the conditional import works.
- **HiGHS default**: solves to optimality, but the unit-commitment MILP is *hard*
  for it — timor_demo village took **~27 min** (vs Gurobi ~5 s) and returned
  **23.734M** at the 1% gap (within tolerance, but 0.67% above Gurobi's 23.5769M,
  because both stop at 1% gap yet find different incumbents).

**Implication (important):** HiGHS delivers the strategic goal — *license-free
runnability* — but is impractical for the full UC-MILP at scale. It is the right
default for small/demo cases, the no-solve screening engine, and the coming
dispatch/LP engines (LPs are fast on HiGHS); **Gurobi remains the fast path for
full UC capacity-expansion runs.** This empirically confirms the Benders analysis:
open-source scalability for this model needs UC *relaxation*, not just a solver
swap. The default MIP gap is unchanged (1%) for both solvers.

### 1.2 Python schema validator — 2026-06-26

New `tools/validate_schema.py`: validates an input folder before a solve —
required files; **R_ID consecutive from 1** (used as an array index);
**variability rows = T**; **Sub_Weights sum = 8760**; **zone IDs align** across
generators/demand/network; network incidence ∈ {−1,0,1}; **fuel referential
integrity**; site-demand columns (site_/village_/ip_ aliases). Standalone
(`python tools/validate_schema.py <dir>`) or imported.

`preflight.jl` shells out to it (best-effort): **blocks** on confirmed data errors
(exit 1), **skips with a warning** if python/pandas is unavailable (exit 3) so a
pure-Julia setup is never blocked; `GARUDA_PYTHON` / `GARUDA_SKIP_VALIDATION`
override. **Verified:** passes on timor_demo / sulawesi / maluku / timor_belu;
catches a broken copy (R_ID gap, unknown fuel, Sub_Weights 8860≠8760, 1343≠1344
rows); preflight blocks bad data and skips gracefully without pandas.

Phase 1 lands on branch `phase-1-open-safe`.

---

## Phase 2 — Keystone: extract `build_model!` from the optimizer

### 2.1 Split build vs solve — 2026-06-26

`capacity_expansion` was a single 783-line function that created the solver,
declared every variable / constraint / expression / objective, solved, and
returned. Split into:
- **`build_model!(CE, inputs, flags…)`** — declares everything on a passed-in
  model and returns the variable/expression references the extractor reads. **No
  solve.** This is the shared model definition every engine can reuse.
- **`capacity_expansion(…; solver)`** — thin wrapper: `make_solver` →
  `build_model!` → `optimize!` → status → `merge(refs, (cost = objective_value(CE),))`.

Verified safe first by grep: `mipgap`/`solver` appear only in the wrapper, never
in the body; one `optimize!`, one `return`. The result extractor reads via
`value.(solution.X)` on the returned refs, so the split is transparent to it.

**Why this is the keystone:** prerequisite for the dispatch/reliability engine
(build, then *fix* capacity instead of solving for it) and for a precision-safe
Benders (master + subproblem from one source of truth — exactly what the dead
`benders_decomposition.jl` got wrong by hand-duplicating the model).

**Verified byte-identical (Gurobi):** timor_demo village 23.5769M, gridvillage
23.5566M, maluku base 88.0122M — all three exact to the Phase-1 baseline.

Phase 2 lands on branch `phase-2-build-model`.

---

## Phase 3 — Engines

### 3.1 No-solve screening engine — 2026-06-26

New `tools/screening.py`: a **solver-free** per-zone screen — a merit-order
dispatch of the *existing* fleet (VRE must-take at availability, thermal stacked
cheapest-first; storage & transmission ignored) over the representative hours.
Reports per-zone annual demand, RE share, emissions, operating cost and unserved
energy. Runs on a laptop with only Python + pandas/numpy — **no Julia, no solver,
no licence**. Excludes new-build candidates (`New_Build==1`, matching the loader's
`OLD` set), which in some datasets carry a "potential" `Existing_Cap_MW`.

**Validated:** on maluku the screen's existing-fleet emissions (890 ktCO₂) land
within ~5% of the solved capacity-expansion result (850 ktCO₂) — the intended
order-of-magnitude check. timor_demo (village diesel) → 414 ktCO₂, ~2% RE,
sensible. Multi-zone sulawesi reports per-zone; transmission is ignored, so
import-reliant zones show high unserved (a documented screening limitation).

The first Phase-3 engine and the cleanest "anyone-can-run-it" surface — no solver
at all. Lands on branch `phase-3-engines`.

### 3.2 Dispatch / reliability engine — 2026-06-26

New `functions/dispatch_engine.jl`. `dispatch_only()` reuses the **same model
definition** as capacity expansion (`build_model!` — the Phase 2 keystone payoff)
but **fixes capacity to the existing fleet** (`JuMP.fix`; `New_Build==1`
candidates → 0), so it solves only the operational problem: how a given fleet runs
and where it falls short. Non-served energy is the slack, so the problem is
**always feasible** — an undersized fleet reports a shortage instead of going
infeasible.

`relax_uc = true` (default) relaxes the unit-commitment binaries to [0,1] → a pure
**LP that HiGHS solves fast** (the open-source payoff: the UC-MILP took ~27 min,
this LP solves in seconds–minutes). `relax_uc = false` keeps exact UC (MILP).

`reliability_results()` writes per-zone (and per-village) **Total NSE, NSE % of
demand, LOLE** (sample-weighted shortage hours/yr) and **peak shortage** to
`reliability_results.csv`. Wired via an `engine` config key
(`"expansion"` | `"dispatch"`) + `relax_uc` through `function_compiler` /
`run_model.jl`.

**Validated:** dispatch solved as an LP on HiGHS for timor_demo + maluku, and the
**dispatch and screening engines independently agree** — maluku existing-fleet
unserved 12.417% (dispatch) vs 12.42% (screening 3.1), 206 GWh both ways, which
cross-validates both. maluku's existing fleet is short ~78% of the year (LOLE
6,790 h, peak 69.7 MW) — so the engine correctly reports shortage rather than
expanding; timor_demo's adequate fleet → 0 shortage. Capacity-fixing confirmed (no
spurious build). Lands on branch `phase-3-engines`.

### 3.3 RE resource & siting engine — 2026-06-26

New `tools/re_resource.py` + `docs/re_resource.md`. Promotes the existing GIS
siting pipeline (`dem_slope` → `candidate_land` → `resource_siting` →
`ntt/solar_potential`, which bake developable-MW ceilings into the generator
tables) into a **consumable per-zone / per-site product**: developable solar/wind
capacity (MW) = `max(Existing_Cap_MW, Max_Cap_MW)` over VRE units, capacity-
weighted mean CF from the variability profiles, and annual energy potential (GWh).
Python + pandas/numpy only — no Julia, no solver, no GIS stack.

**Verified:** maluku zone 1 → solar 2,614 MW (CF 0.14, 3,156 GWh), wind 3,188 MW
(CF 0.03) — sum + CFs check out against the raw data; sulawesi per-zone and
per-(captive-industrial)-site, where the land-based ceilings are correctly huge (a
single nickel-smelter site shows ~278 GW of *sitable* solar — a non-binding
guardrail, clearly labelled). The site path also exercises the `village_*` alias on
real industrial-park data.

**Phase 3 complete:** three engines on one data core — screening (no solver),
dispatch/reliability (fast LP), RE-resource (resource view) — plus the inherited
capacity-expansion MILP.

---

## Phase 4 — Interoperability (PyPSA export)

### 4.1 Zonal model → PyPSA network — 2026-06-27

New `tools/export_pypsa.py` (`build_network(folder, mode)`): translates a zonal
input folder into a `pypsa.Network`, so the data core can feed the established
open-source framework instead of competing with it. Mapping: zone → **Bus**,
zonal demand → **Load**, transmission line → **bidirectional lossless Link**
(`p_nom = Line_Max_Flow_MW`, `p_min_pu = -1`), generator/VRE → **Generator**
(`marginal_cost = Var_OM + fuel·heat_rate`, availability profile as `p_max_pu`),
storage → **StorageUnit**, each NSE segment → a per-zone **load-shedding
Generator** (`marginal_cost = VOLL·cost`, `p_nom·p_max_pu = NSE_Max·demand`), and
the representative periods → **snapshots** with `snapshot_weightings.objective =
W[p]/H` (Σ = 8760 h) and `stores = 1 h`. Two modes: `dispatch` (existing fleet
fixed, the validated path) and `expansion` (new-build extendable, best-effort).
Python + pypsa; pypsa imported lazily. See `docs/pypsa_export.md`.

**Why links, not lines.** garuda's network is a *transport* model — the demand
balance nets `Σ_l incidence[l,z]·FLOW` with `FLOW ∈ [−T_CAP, T_CAP]` and the
DC-power-flow (susceptance/angle) block in `optimizer.jl` is commented out. A
PyPSA `Line` would impose Kirchhoff's voltage law; a bidirectional `Link`
reproduces garuda's free transport up to the thermal limit. The incidence sign
sets the direction (power leaves the `+1` zone = `bus0`).

**Fidelity gaps (documented, deliberate):** transport not KVL (lines lossless, no
`Line_Loss_Percentage`); no unit commitment (continuous generators — matches the
default LP-relaxed dispatch, not an exact UC/MILP or start costs); whole-horizon
cyclic storage rather than per-representative-period; storage discharge capped at
`p_nom` (garuda caps only charge). Scope: the **grid (zonal) layer**; the
village/site layer is out of scope (it decouples from the grid in grid-off
scenarios).

**One translation bug found and fixed during validation:** garuda applies the
hourly availability profile (`cMaxPowerED`) to *every* economic-dispatch unit
(`Commit==0`) — VRE **and** derated thermal (≈30 % of sulawesi thermal columns
sit at 0.5, not 1.0). The first cut keyed `p_max_pu` on the VRE flag and so
over-stated derated thermal availability; keying it on `Commit` instead made the
multi-zone total match exactly (below).

### 4.2 Dispatch-parity validation — 2026-06-27

New `tools/validate_pypsa_parity.py`: solves the exported `dispatch` network on
HiGHS and compares **system-total unserved energy** against the garuda dispatch
engine's `reliability_results.csv`. The system total is the well-defined metric —
with a uniform NSE price and a connected lossless network the LP is *degenerate*
in *which* connected zone bears a shortfall, so per-zone unserved is reported but
not asserted.

**Validated (existing-fleet LP dispatch, HiGHS both sides):**

| case | zones · links | garuda total unserved | PyPSA total unserved | rel. Δ |
|---|---|---|---|---|
| maluku (base) | 1 · 0 | 205 997.3 MWh (12.418 %) | 205 997.3 MWh (12.418 %) | 0.0000 % |
| sulawesi grid-only (base) | 6 · 18 | 2 394 733.6 MWh (9.225 %) | 2 394 733.6 MWh (9.225 %) | 0.0000 % |

Both match to the decimal. maluku (single-zone, fleet pinned at capacity)
validates the generator/storage/NSE/snapshot-weighting translation; the
multi-zone grid-only sulawesi case additionally validates the inter-zone links —
their per-line capacities and `bus0/bus1` directions equal garuda's fixed `T_CAP`
exactly. The multi-zone reference uses a **grid-only** fixture (the six grid CSVs
of sulawesi, villages omitted — villages decouple from the grid in `base` but
bloat the garuda LP); recreate it per `docs/pypsa_export.md`. The maluku case is
reproducible from shipped data with no fixture.

> Process note: the village-laden sulawesi `base` dispatch is a large LP (slow on
> HiGHS); the grid-only fixture solves in ~40 s and is the right parity reference
> for the grid-only export.

---

## Phase 5 — Experience layer

### 5.1 Guided launcher — `tools/launcher.py` — 2026-06-27

A non-expert on-ramp for a single run: **validate** (reuses
`validate_schema.validate_dataset`, the same checks that gate `preflight.jl`) →
**preview** (zones, generators with UC/VRE/storage counts, transmission lines, the
`P×H=T` representative structure, an order-of-magnitude variable count, and a
runtime estimate anchored on measured timings) → **scaffold** a `config.json` with
the right keys for `run_model.jl` (incl. `engine`, `relax_uc`, `solver`) →
optionally `--run` (shells out to `julia … run_model.jl`, exactly as a human
would; it never wires into the optimizer). Python + pandas.

**Verify:** `python tools/launcher.py --island maluku --year 2030 --scenario base
--clean reference --engine dispatch` previews 1 zone / 73 generators / 1344 steps
and writes a valid config; the same on sulawesi `gridvillage` reports 6 zones / 278
generators / 18 lines and flags the HiGHS UC-MILP as slow at that scale.

### 5.2 Auto-report — `tools/report.py` — 2026-06-27

Turns a scenario's result CSVs into one shareable **HTML** (self-contained,
base64-embedded matplotlib charts) **and a PDF**. Headline metrics (system cost,
CO₂, RE share, annual demand, energy served, unserved energy + share), charts
(generation mix, installed capacity, cost breakdown, per-zone reliability) and
tables, all degrading gracefully when a CSV is absent. PDF via **weasyprint** when
importable, otherwise matplotlib **`PdfPages`** — so a PDF is always produced with
no native (Cairo/Pango) dependency.

**A units subtlety it gets right.** The source result CSVs mix *annualised*
quantities (cost, CO₂, RE, `reliability_results`) with *representative-period
sums* (`generator_results.GWh`, `nse_results`); since `Sub_Weights` are **not
uniform**, a summed generation column can't be annualised after the fact. The
report therefore anchors annual demand/served/unserved-share on the **input**
`demand.csv` (auto-located at `data_indonesia/<year>/<island>`), takes annual
unserved from the sample-weighted `reliability_results`, and labels the
generation-mix chart as a representative-period sum — rather than mixing units
(an early cut reported a 47.9 % "unserved share" where the true annual figure is
12.4 %; now correct).

**Verify:** `python tools/report.py results/base_maluku_2030_reference` →
`report.html` + `report.pdf` with demand 1 658.9 GWh, served 1 452.9, unserved
206.0 (12.4 %); `tools/report.py results/gridvillage_timor_demo_2030_reference`
renders an expansion run with the village layer present. See
`docs/experience_layer.md`.

---

## Phase 6 — Generalize & document

### 6.A Site generality — captive-industrial datasets as first-class — 2026-06-28

Made the decentralised **site** layer fully general so a captive-industrial
(`ip_*`) dataset loads, runs and reports exactly like the village (`village_*`)
data, validated against the real **`Power-Lab/data-indonesia-2025`** release.

**Finding — the loader already generalises.** `input_data` ingested the real
captive datasets (e.g. sumatera: 9 zones, 488 grid generators, **19 industrial
parks**, 222 site generators) through the existing `site_aliases.jl` resolver
**unchanged** — the ~25 extra IP metadata columns (`plant_owner`, `latitude`,
`commodity`, …) are simply not selected, and the modelling columns load
identically. So the Phase 0.3 "full captive ingestion remains Phase 6" caveat was
already satisfied at the loader; the real gaps were plumbing.

**Changes:**
- **`functions/preflight.jl`** — `validate_input_files` was hardcoded to require
  `village_*.csv`; it now resolves the required *site* tables through any
  `site_/village_/ip_` spelling (`_input_present`), so a captive (`ip_`) dataset
  passes preflight. `expected_input_files` lists the canonical `site_` names.
- **Canonical `site_` output naming** — `result_extraction_function.jl` and
  `dispatch_engine.jl` now write `site_generator_results.csv`,
  `site_storage_results.csv`, `site_import_results.csv`,
  `site_connection_results.csv`, `site_nse_results.csv`,
  `site_nse_heat_results.csv`, `site_heat_generator_results.csv` and
  `site_reliability_results.csv` (was `village_*`), regardless of input spelling.
  Docs updated (`outputs_guide.md`, `ntt_data_integration.md`).
- **`tools/launcher.py`** — the scenario preview now reports the site layer
  (`N site(s) · M site generator(s)`) and folds site generators into the
  problem-size estimate.

**Verified:**
- `input_data` loads di2025 sumatera (19 parks) and north_maluku (4 parks) with
  no code changes.
- A captive run (`scenario=captive`, north_maluku) **passes preflight** with only
  `ip_*` site files present (the old hardcoded `village_*` check would have
  blocked it) and reaches the solver.
- `validate_schema.py` and `launcher.py` both accept the captive dataset; the
  launcher preview shows `4 site(s) · 71 site generator(s)`.
- A `gridvillage` dispatch on `timor_demo` writes the full `site_*` result set
  (incl. `site_reliability_results.csv`) and **no** `village_*` files; the
  auto-report renders correctly off the renamed outputs.
- `tests/verify_data_core.jl` — all 12 data-core checks still pass.

> Note: the captive **solve** is heavy for HiGHS (the IP-laden LP is large and
> degenerate, like the village-laden cases) — full end-to-end runs on
> sumatera/jawa_bali want Gurobi or a long background HiGHS job. Ingestion,
> preflight and output naming are validated independently of solve time.

> Scope: the canonical `site_` rename covers result **filenames** (and the
> extractor's return keys); the internal per-row ID column stays `Village`.
> Bringing a captive dataset into the repo as a committed first-class case
> (sumatera/jawa_bali) and the audience guides / `ZonalPowerModel.jl` package
> remain the rest of Phase 6.

