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

