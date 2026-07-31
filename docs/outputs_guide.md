# Outputs Guide

Each job writes `results/<scenario>_<island>_<year>_<clean>/`.

**On annualisation — every energy column is now annual.** Costs (`$M/yr`),
emissions, RE shares, generation (`GWh`, `Electricity_GWh`), imports and exports,
transmission flows and all `Total_NSE_MWh` columns are annual figures:
`result_extraction_function.jl` weights every rep-period sum by `sample_weight`
(`Sub_Weights[p] / Timesteps_per_Rep_Period`), the same weighting the objective
already applied to costs. Power columns — `Peak_*_MW`, `Max_NSE_MW`, `Total_MW`,
capacities — are instantaneous and deliberately unweighted.

> **Changed behaviour.** These columns used to be raw sums over the modelled
> hours, i.e. *the sample, not the year*. On Timor that under-reported annual
> energy by **6.518×** (8760/1344); on a dataset with non-uniform `Sub_Weights`
> such as maluku, whose per-hour weights range 1.0–15.04, there was no single
> correction factor at all and even the generation *mix* (`Percent_GWh`) was
> distorted. Any figure taken from these columns before this change needs
> re-deriving — do not compare old and new result CSVs directly.

Multiplying by `8760 / (Rep_Periods × Timesteps_per_Rep_Period)` is therefore no
longer needed, and doing it now double-counts. `tools/coordination_value.py`
still applies its own annualisation to the CSVs it reads — see the note there.

## File-by-file

> The decentralised-node result tables use the canonical **`site_`** prefix
> regardless of the input spelling (`village_`/`ip_`/`site_` are accepted input
> aliases — see `functions/site_aliases.jl`). Each row still carries the
> internal `Village` ID column. A dispatch run additionally writes
> `site_reliability_results.csv` (per-site NSE / LOLE / peak shortage).

**`generator_results.csv`** (grid) / **`site_generator_results.csv`** —
one row per unit: `Total_MW` (optimised capacity), `Start_MW` (existing),
`Change_in_MW` (build > 0, retire < 0), `GWh`/`Electricity_GWh` (representative-
period generation — annualise per the note above). Site rows carry the `Village`
ID.

**`storage_results.csv`** / **`site_storage_results.csv`** — energy
capacity per storage unit: `Total_Storage_MWh`, `Change_in_Storage_MWh`.
Pair with the power capacity row in the generator results to get duration
(MWh ÷ MW).

**`site_import_results.csv`** — per site: `Total_Import_MWh`,
`Peak_Import_MW`. Nonzero only in `grid*` scenarios.

**`nse_results.csv`** / **`site_nse_results.csv`** — non-served energy by
segment × zone (or site): `Total_NSE_MWh`, `NSE_Percent_of_Demand`,
`Max_NSE_MW`. The reliability outcome.

**`cost_results.csv`** — single-row $M breakdown:
`Total_Costs`, `Fixed_Costs_Generation/Storage/Transmission` (grid),
`Fixed_Costs_Village`, `Fixed_Costs_Village_Storage`,
`Variable_Costs_Grid/Village`, `NSE_Costs`, `VILNSECosts`, `VILNSEHeatCosts`,
`Grid_Import_Costs`, `Village_Export_Revenue` (feed-in earnings, 0 unless the
`export_price` config key is set; already subtracted inside `Total_Costs`),
`StartCostsGrid`, `StartCostsVIL`.

**`clean_energy_results.csv`** — `CO2_Emissions` (total), `_Grid`, `_Village`,
`Grid_REShare` (grid generation only — village solar excluded) and
`System_REShare` (grid + village generation over grid + village electricity
demand). Both shares are always reported; which one the `clean` constraints
enforce depends on the `policy_scope` config key (default `"grid"`). Annual.

**`site_connection_results.csv`** (grid* scenarios) — per site: `Connected`
(the co-optimised interconnection decision), `Total_Import_MWh`,
`Total_Export_MWh`. Exports are **unremunerated by default** (see `MODEL.md`):
at `export_price = 0` a nonzero `Total_Export_MWh` is a degenerate free spill of
surplus solar (curtailing would cost the same) — do not interpret it
economically. With `export_price` set, exports are revenue-driven and earn
`Village_Export_Revenue` in `cost_results.csv`. Under `relax_uc` the connect
binary is LP-relaxed, so `Connected` can be fractional (a village paying 1 % of
the connection cost for 1 % of the capacity); the exact-UC MILP forces a 0/1
decision.

**`transmission_results.csv`** — per corridor: existing, optimised, and change
in transfer capacity. `Change_in_Transfer_Capacity > 0` is grid reinforcement.

## Headline metrics for the village study

Comparing a standalone run (`village_…`) against a coordinated run
(`gridvillage_…`) on the same island/year. **`tools/coordination_value.py`
computes this whole table for you** (with correct annualisation and consistency
guards); the columns below document what it reports.

| Concept-note metric | Computation |
|---------------------|-------------|
| System cost saving from coordination | `Total_Costs(village) − Total_Costs(gridvillage)` (both annual) |
| Avoided grid reinforcement | Δ `Fixed_Costs_Transmission`, and per-line Δ in `transmission_results.csv` |
| Diesel displacement | Δ `GWh` over diesel rows in both generator files (rep-period sums — annualise per the note above); fuel burn = GWh × heat rate |
| Emissions reduction | Δ `CO2_Emissions` (annual) |
| Optimal battery sizing | `site_storage_results.csv` MWh with paired MW from `site_generator_results.csv` |
| Reliability improvement | Δ `Total_NSE_MWh` (dispatch: `site_reliability_results.csv`, annual; expansion: `site_nse_results.csv`, rep-period sum) |

```python
import pandas as pd
base = "results/{}_timor_demo_2030_reference/cost_results.csv"
standalone  = pd.read_csv(base.format("village")).iloc[0]
coordinated = pd.read_csv(base.format("gridvillage")).iloc[0]
print("coordination saving ($M):", standalone.Total_Costs - coordinated.Total_Costs)
```

## Caveats

- `Start_Storage_MWh` is populated from `Existing_Cap_MW` (not `_MWh`) — a
  legacy quirk; existing-storage baselines in the storage files are only
  meaningful when power and energy capacity coincide.
- Hourly dispatch traces are not written by default; the model solves them but
  `result_extraction_function.jl` exports aggregates only (representative-period
  sums for energy, annual for costs/emissions — see the annualisation note above).
