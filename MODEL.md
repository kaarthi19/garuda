# Model Formulation

The model is a single-year capacity-expansion and unit-commitment MILP that
co-optimises an island grid and a set of village systems. This document states
the formulation as implemented in `functions/optimizer.jl`
(`capacity_expansion`), with line references for each block. Notation follows
the code.

## Sets (built in `functions/input_data.jl`)

| Set | Meaning |
|-----|---------|
| `T` | Hours across all representative periods (e.g. 8×168 = 1,344); `START`/`INTERIOR` split period-first hours from the rest |
| `Z` | Grid zones; `L` transmission corridors |
| `G` | Grid generators; **partitioned** into `UC` (`Commit=1`, binary commitment) and `ED` (everything else — economic dispatch), and `OLD`/`NEW` (existing vs candidate) |
| `STOR`, `VRE` | Grid storage / variable-renewable subsets |
| `ED_RAMP` | `ED` minus `STOR` — the units the thermal ramp limits apply to |
| `S` | Demand-curtailment (NSE) segments |
| `VIL` | Villages; `VIL_G`, `VIL_UC`, `VIL_ED`, `VIL_STOR`, `VIL_NEW`, `VIL_OLD` mirror the grid subsets |

Each hour `t` carries `sample_weight[t] = Sub_Weights[p]/Timesteps_per_Rep_Period`
(= 168 in the shipped datasets), scaling representative-period operations to
annual quantities.

## Decision variables (optimizer.jl 7–135)

**Grid investment** — `vCAP[g]` total power capacity; `vNEW_CAP_*`/`vRET_CAP_*`
new-build and retirement for ED and UC units; `vE_CAP[g]` storage energy
capacity with new/retire components; `vT_CAP[l]`, `vNEW_T_CAP[l]`,
`vRET_T_CAP[l]` transmission. New-build bounded by `Max_Cap_MW` when positive
(36–42).

**Grid operations** — `vGEN[t,g]`, `vCHARGE[t,g]`, `vSOC[t,g]`, `vNSE[t,s,z]`,
`vFLOW[t,l]`; binaries `vCOMMIT/vSTART/vSHUT[t,g∈UC]` (30–32).

**Village** — mirrored: `vVIL_CAP`, `vVIL_E_CAP` (+ new/retire),
`vVIL_GEN`, `vVIL_GEN_HEAT`, `vVIL_CHARGE`, `vVIL_SOC`, `vVIL_NSE`,
`vVIL_NSE_HEAT`, binaries `vVIL_COMMIT/START/SHUT`; and, in `Grid` scenarios,
the interconnection block `vVIL_IMPORT`, `vVIL_EXPORT`, and the connection
binary `vVIL_CONNECT[vil]` (89–106), with import and export each capped by
`village_connect_max × vVIL_CONNECT`. New-build onsite capacity is bounded by the
per-village `Max_Cap_MW` land/resource ceiling when positive (108–119); new
village storage energy is bounded per unit by `village_storage_max_mwh` (121–123).

Site storage power and energy are **co-optimised independently** by default, so
the built duration floats to whatever the dispatch wants. Setting the
`battery_duration_h` config key (> 0) adds `cVILStorDuration` (125–135),
`vVIL_E_CAP = battery_duration_h × vVIL_CAP` over new site storage — a
fixed-duration battery product, which is what makes the power capex
(`Inv_Cost_per_MWyr`) bind the energy build. `0` (the default) omits the
constraint entirely.

`vVIL_EXPORT` supplies the zonal balance (140–148) and is debited from the
village balance in `Grid` scenarios (346–377). **By default it earns nothing**
(`export_price = 0`, the config default) — a free spill path for surplus that
would otherwise be curtailed, 0 in every shipped reference run. Setting the
`export_price` config key ($/MWh) adds a feed-in revenue term to the objective,
making surplus export an economic choice bounded per village by the
interconnection cap; keep it ≤ `import_price` or import→re-export arbitrage
becomes profitable (`run_model.jl` warns). Non-`Grid` scenarios omit the export
term entirely (379–408).

**Exports are not tied to generation by default.** `vVIL_EXPORT` is bounded only
by the interconnection cap, so on a dataset whose grid zone has no load — where
the zonal balance forces `Σ export ≤ Σ import` — a *pair* of sites can transact
with no physical generation at all, booking `export_price − import_price` per MWh
of pure accounting margin. `build_model!` **refuses** that configuration
(`export_price > import_price` **and** zero weighted grid demand). Setting
`export_backed_by_generation = true` adds `cVILExportBacked`,
`vVIL_EXPORT[t,v] ≤ Σ vVIL_GEN[t,g]` over that site's RE-flagged units, which
makes the trade structurally impossible; it is off by default because it adds a
row per hour × site.

## Constraints

**Zonal power balance** (138–161): for each `t, z` —
generation + NSE − storage charging − demand − line flows (incidence `z<i>` ∈
{+1, −1}) − village imports + village exports of villages in zone `z` (via
`village_zone`) = 0. Transport flow model; the DC power-flow variant is commented
out (225–228).

**Capacity limits** (164–191): `vGEN ≤ variability×vCAP` for ED;
`vGEN ≤ Existing_Cap×vCOMMIT` and `vGEN ≥ Min_Power×Existing_Cap×vCOMMIT` for
UC (note: UC unit size is `Existing_Cap_MW`, so UC new-build adds copies of the
existing unit size); charge ≤ power capacity and SOC ≤ energy capacity for
storage; `vNSE ≤ NSE_Max×demand` per segment; |flow| ≤ `vT_CAP`.

**Capacity accounting** (194–223): total = existing − retired (OLD) or = new
build (NEW), for power, storage energy, and transmission
(`vT_CAP = Line_Max_Flow + vNEW_T_CAP − vRET_T_CAP`, expansion bounded by
`Line_Max_Reinforcement_MW`).

`UC` and `ED` must partition `G`: a generator in neither gets no capacity
constraint and no max-power constraint, so its `vCAP` floats free — `Max_Cap_MW`
unapplied, `Inv_Cost_per_MWyr` uncharged (that term sums over `ED_NEW`/`UC_NEW`),
and `vGEN` uncapped. `ED` is therefore the *complement* of `UC`, not
`Commit == 0`: `Commit` carries sentinels beyond `{0,1}` (battery candidates are
all `Commit = 2`) and testing for 0 orphaned every one of them. Pinned by
`tests/verify_capacity_accounting.jl`; the regression gate cannot see it, because
its cases are dispatch-only and `dispatch_only()` pins `CAP` for every `g ∈ G`.

**Ramping** (231–281): up/down limits as fractions of capacity, applied to
`ED_RAMP` (= `ED` − `STOR`) and `UC`; for UC units the start/shut terms allow
jumps to/from `Min_Power`. Each constraint has a wrap-around twin linking the
first and last hour of each representative period. **Storage is exempt**: these
constraints bound `vGEN` alone and say nothing about `vCHARGE`, so they never
limited the charge↔discharge swing that actually matters for a battery. Storage
power is bounded by `cMaxPowerED` and `cMaxCharge` (both `≤ vCAP`) and its energy
by `cMaxSOC`; a genuine storage ramp limit would bound `d(vGEN − vCHARGE)/dt` and
is not modelled.

**Commitment** (282–292, 307–332): min up/down times via rolling sums of
`vSTART`/`vSHUT`; commitment-state recursion
`vCOMMIT[t+1] = vCOMMIT[t] + vSTART − vSHUT`; commit/start/shut bounded by
installed units (`vCAP/Existing_Cap`).

**Storage SOC** (293–303): `vSOC[t] = vSOC[t−1] + Eff_Up×vCHARGE −
vGEN/Eff_Down`, with periodic wrap inside each representative period.

**Village blocks** (336–570): structurally identical, per village:

- *Heat balance* (338–343): UC-unit heat output + heat NSE = heat demand.
- *Electricity balance* (346–408): generators allowed to serve village demand
  depend on the scenario — `VIL_UC` only (no `VillageBuild`), all `VIL_G`
  (`VillageBuild`), or `VIL_ED`-only (`NoCoal`); plus `vVIL_IMPORT` minus
  `vVIL_EXPORT` when `Grid` is active; minus storage charging.
- Capacity, ramping, commitment, and SOC mirror the grid (411–570).

**Policy constraints** (575–631), scoped by the `policy_scope` config key
(default `"grid"` — the shipped-reference behaviour):

- CO₂ cap (active in `clean` runs): `eCO2EmissionsGrid ≤ CO2_limit` under
  `"grid"` scope; `eCO2EmissionsGrid + eCO2EmissionsVIL ≤ CO2_limit` under
  `"system"` scope.
- 2035 village-emissions cut: `eCO2EmissionsVIL ≤ 0.65×BAU` when
  `CO235reduction` (either scope).
- RE share (active in `clean` runs): under `"grid"` scope, weighted RE-flagged
  grid generation ≥ `RE_limit` × total grid demand — village generation is in
  neither numerator nor denominator. Under `"system"` scope, RE-flagged village
  generation joins the numerator and village electricity demand the denominator
  (village heat is out of scope either way). Both share expressions are always
  built and reported (`Grid_REShare`, `System_REShare` in
  `clean_energy_results.csv`); only the constrained one depends on the scope.

## Objective (633–770)

Minimise total annual cost:

```
  fixed costs:    Σ FOM×vCAP + Σ Inv×vNEW_CAP            (grid + village, power & storage energy)
+ transmission:   Σ (FOM + reinforcement cost)×vT_CAP
+ variable costs: Σ_t w_t × VarCost_g × vGEN             (VarCost = VOM + fuel×heat-rate)
+ start-up costs: Σ_t w_t × StartCost × vSTART × unit size
+ imports:        Σ_t w_t × ImportPrice × vVIL_IMPORT    (Grid scenarios)
+ interconnect:   Σ village_connect_cost × vVIL_CONNECT  (Grid scenarios; annualised)
− export revenue: Σ_t w_t × export_price × vVIL_EXPORT   (Grid scenarios; 0 by default)
+ reliability:    Σ_t w_t × (VOLL×segment cost) × NSE    (grid, village, village heat)
```

Village exports earn revenue only when `export_price > 0` (config key; default 0
preserves the unremunerated-spill behaviour of the shipped references). The
interconnection cost `eVILConnectCost` is what the coordinated (`gridvillage`)
run trades against avoided village generation/storage — the source of the
coordination value; a feed-in price shifts that trade in favour of connecting.

Emission rates and variable costs are precomputed per generator in
`input_data.jl` (87–104) from `fuels_data.csv`.

## Solver settings (`functions/solver.jl`)

**HiGHS by default** (open-source, no licence) — `mip_rel_gap = mipgap` (config
key, default 0.01). **Gurobi optional** (`"solver":"gurobi"`), imported only when
requested, for the fast MILP path on large instances; there `MIPGap = mipgap`,
`TimeLimit` 72 h, `Crossover 0`.

`lp_method` (config key, default `-1` = automatic) sets Gurobi's `Method` — the
LP algorithm used for the root relaxation and the node LPs (`0` primal simplex,
`1` dual simplex, `2` barrier, `3`–`5` concurrent variants). At `-1` nothing is
set, so it is a strict no-op. It matters at island scale: on the 780-village
Timor expansion MILP, Gurobi's automatic choice runs the root LP concurrently
and reports ~535 s of "concurrent spin time … can be avoided by choosing
Method=3"; `"lp_method": 2` (barrier) removes that overhead. There is no HiGHS
analogue — under HiGHS the key is ignored and `run_model.jl` says so.

`relax_uc` (config key) LP-relaxes the unit-commitment binaries
(`vCOMMIT/START/SHUT`, grid and village) to `[0,1]` via `_relax_binaries!`,
turning the MILP into an LP that HiGHS solves in seconds — default **on** for the
dispatch engine, **off** (exact MILP) for expansion. On `timor_demo` the relaxed
expansion LP is ~0.8 % below the exact MILP cost (a measured lower bound;
reproduce with `tools/uc_relaxation_gap.jl`).

An optional Benders decomposition (`functions/benders_decomposition.jl`, an
inherited stub, not loaded) would split investment (master) from dispatch
(subproblem) for very large instances.

## Known formulation limitations

Flagged for follow-up:

- **Grid-only policy scope by default** — the CO₂ cap and RE-share floor apply
  to grid generation only unless `policy_scope: "system"` is set (avoids
  double-counting by default, but a village can run on diesel without touching
  the grid target; the system scope closes that gap).
- **Village exports unpriced by default** — `vVIL_EXPORT` earns revenue only
  when the `export_price` config key is set; at the default 0, surplus solar is
  spilled rather than sold. No shipped scenario sets a feed-in price (there is
  no official tariff to anchor it to yet).
- **Flat import *energy* price** — `import_price` is a single $/MWh with no
  time-of-day or tariff structure. (The interconnection *capex* side is
  distance-based: `village_connection.csv::Cost_per_yr` is derived from each
  village's `hubdist_km` — see `tools/connection_cost.py` — and datasets without
  the file fall back to free connection.)
- **Single-year snapshots** — 2030 and 2035 are solved independently; no vintage
  linkage, retirement-by-age, or learning curves across years.
- **No reserve constraints** — adequacy is represented only by priced non-served
  energy, not an explicit reserve margin.
- **Result energy columns are annualised** — `result_extraction_function.jl`
  weights every rep-period energy sum by `sample_weight`, so generation, imports,
  exports, flows and unserved energy are annual, consistent with costs and
  emissions. Power columns (peaks, capacities) stay instantaneous. See
  `docs/outputs_guide.md`; this changed, and older result CSVs are not comparable.
