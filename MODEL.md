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
| `G` | Grid generators; partitioned into `UC` (`Commit=1`, binary commitment) and `ED` (economic dispatch), and `OLD`/`NEW` (existing vs candidate) |
| `STOR`, `VRE` | Grid storage / variable-renewable subsets |
| `S` | Demand-curtailment (NSE) segments |
| `VIL` | Villages; `VIL_G`, `VIL_UC`, `VIL_ED`, `VIL_STOR`, `VIL_NEW`, `VIL_OLD` mirror the grid subsets |

Each hour `t` carries `sample_weight[t] = Sub_Weights[p]/Timesteps_per_Rep_Period`
(= 168 in the shipped datasets), scaling representative-period operations to
annual quantities.

## Decision variables (optimizer.jl 16–111)

**Grid investment** — `vCAP[g]` total power capacity; `vNEW_CAP_*`/`vRET_CAP_*`
new-build and retirement for ED and UC units; `vE_CAP[g]` storage energy
capacity with new/retire components; `vT_CAP[l]`, `vNEW_T_CAP[l]`,
`vRET_T_CAP[l]` transmission. New-build bounded by `Max_Cap_MW` when positive
(42–53).

**Grid operations** — `vGEN[t,g]`, `vCHARGE[t,g]`, `vSOC[t,g]`, `vNSE[t,s,z]`,
`vFLOW[t,l]`; binaries `vCOMMIT/vSTART/vSHUT[t,g∈UC]` (36–38).

**Village** — mirrored: `vVIL_CAP`, `vVIL_E_CAP` (+ new/retire),
`vVIL_GEN`, `vVIL_GEN_HEAT`, `vVIL_CHARGE`, `vVIL_SOC`, `vVIL_NSE`,
`vVIL_NSE_HEAT`, binaries `vVIL_COMMIT/START/SHUT`; and, in `Grid` scenarios,
the interconnection block `vVIL_IMPORT`, `vVIL_EXPORT`, and the connection
binary `vVIL_CONNECT[vil]` (89–107), with import and export each capped by
`village_connect_max × vVIL_CONNECT`. New-build onsite capacity is bounded by the
per-village `Max_Cap_MW` land/resource ceiling when positive (109–125); new
village storage energy is bounded per unit by `village_storage_max_mwh`.

`vVIL_EXPORT` supplies the zonal balance (132–140) and is debited from the
village balance in `Grid` scenarios (341–364), but it carries **no revenue term
in the objective** — so it is only ever a free spill path for surplus that would
otherwise be curtailed, and is 0 in every shipped reference run. Non-`Grid`
scenarios omit the export term entirely (374–398). A feed-in / export-tariff
term is a known follow-up.

## Constraints

**Zonal power balance** (117–136): for each `t, z` —
generation + NSE − storage charging − demand − line flows (incidence `z<i>` ∈
{+1, −1}) − village imports + village exports of villages in zone `z` (via
`village_zone`) = 0. Transport flow model; the DC power-flow variant is commented
out (203–206).

**Capacity limits** (142–169): `vGEN ≤ variability×vCAP` for ED;
`vGEN ≤ Existing_Cap×vCOMMIT` and `vGEN ≥ Min_Power×Existing_Cap×vCOMMIT` for
UC (note: UC unit size is `Existing_Cap_MW`, so UC new-build adds copies of the
existing unit size); charge ≤ power capacity and SOC ≤ energy capacity for
storage; `vNSE ≤ NSE_Max×demand` per segment; |flow| ≤ `vT_CAP`.

**Capacity accounting** (171–201): total = existing − retired (OLD) or = new
build (NEW), for power, storage energy, and transmission
(`vT_CAP = Line_Max_Flow + vNEW_T_CAP − vRET_T_CAP`, expansion bounded by
`Line_Max_Reinforcement_MW`).

**Ramping** (209–258): up/down limits as fractions of capacity; for UC units
the start/shut terms allow jumps to/from `Min_Power`. Each constraint has a
wrap-around twin linking the first and last hour of each representative period.

**Commitment** (260–303): min up/down times via rolling sums of `vSTART`/
`vSHUT`; commitment-state recursion `vCOMMIT[t+1] = vCOMMIT[t] + vSTART − vSHUT`;
commit/start/shut bounded by installed units (`vCAP/Existing_Cap`).

**Storage SOC** (271–279): `vSOC[t] = vSOC[t−1] + Eff_Up×vCHARGE −
vGEN/Eff_Down`, with periodic wrap inside each representative period.

**Village blocks** (307–536): structurally identical, per village:

- *Heat balance* (309–314): UC-unit heat output + heat NSE = heat demand.
- *Electricity balance* (316–380): generators allowed to serve village demand
  depend on the scenario — `VIL_UC` only (no `VillageBuild`), all `VIL_G`
  (`VillageBuild`), or `VIL_ED`-only (`NoCoal`); plus `vVIL_IMPORT` minus
  `vVIL_EXPORT` when `Grid` is active; minus storage charging.
- Capacity, ramping, commitment, and SOC mirror the grid (382–536).

**Policy constraints** (539–572):

- CO₂ cap on grid emissions: `eCO2EmissionsGrid ≤ CO2_limit` (active in
  `clean` runs).
- 2035 village-emissions cut: `eCO2EmissionsVIL ≤ 0.65×BAU` when
  `CO235reduction`.
- RE share: weighted RE-flagged grid generation ≥ `RE_limit` × total grid
  demand (active in `clean` runs). **Grid-only**: village generation is in
  neither numerator nor denominator.

## Objective (574–687)

Minimise total annual cost:

```
  fixed costs:    Σ FOM×vCAP + Σ Inv×vNEW_CAP            (grid + village, power & storage energy)
+ transmission:   Σ (FOM + reinforcement cost)×vT_CAP
+ variable costs: Σ_t w_t × VarCost_g × vGEN             (VarCost = VOM + fuel×heat-rate)
+ start-up costs: Σ_t w_t × StartCost × vSTART × unit size
+ imports:        Σ_t w_t × ImportPrice × vVIL_IMPORT    (Grid scenarios)
+ interconnect:   Σ village_connect_cost × vVIL_CONNECT  (Grid scenarios; annualised)
+ reliability:    Σ_t w_t × (VOLL×segment cost) × NSE    (grid, village, village heat)
```

Village exports carry no objective term (no feed-in revenue). The interconnection
cost `eVILConnectCost` is what the coordinated (`gridvillage`) run trades against
avoided village generation/storage — the source of the coordination value.

Emission rates and variable costs are precomputed per generator in
`input_data.jl` (87–104) from `fuels_data.csv`.

## Solver settings (`functions/solver.jl`)

**HiGHS by default** (open-source, no licence) — `mip_rel_gap = mipgap` (config
key, default 0.01). **Gurobi optional** (`"solver":"gurobi"`), imported only when
requested, for the fast MILP path on large instances; there `MIPGap = mipgap`,
`TimeLimit` 72 h, `Crossover 0`.

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

- **Grid-only policy scope** — the CO₂ cap and RE-share floor apply to grid
  generation only; village generation is outside both (avoids double-counting,
  but a village can run on diesel without touching the grid target).
- **Unpriced village exports** — `vVIL_EXPORT` is modelled but earns no revenue,
  so surplus solar is spilled rather than sold to the grid.
- **Flat import price** — `import_price` is a single $/MWh; the per-village
  distance to the grid (`hubdist_km`, computed by the siting pipeline) is not yet
  used to derive a distance-based extension cost.
- **Single-year snapshots** — 2030 and 2035 are solved independently; no vintage
  linkage, retirement-by-age, or learning curves across years.
- **No reserve constraints** — adequacy is represented only by priced non-served
  energy, not an explicit reserve margin.
- **Representative-period sums in result extraction** — energy columns in the
  generator / NSE / import result CSVs are sums over representative hours, not
  annualised; costs, emissions, and the dispatch reliability tables are annual.
  See `docs/outputs_guide.md`.
