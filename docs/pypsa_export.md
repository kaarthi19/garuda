# PyPSA export (Phase 4 — interoperability)

Garuda's data core can be handed to [PyPSA](https://pypsa.org), the established
open-source power-system framework, instead of competing with it. `tools/export_pypsa.py`
translates a zonal input folder into a `pypsa.Network`; `tools/validate_pypsa_parity.py`
checks that the translated network reproduces the garuda dispatch engine.

```bash
# build a network and write it to netCDF
python tools/export_pypsa.py data_indonesia/2030/sulawesi --mode dispatch --netcdf sulawesi.nc

# or in Python
from tools.export_pypsa import build_network
n = build_network("data_indonesia/2030/maluku", mode="dispatch")
n.optimize(solver_name="highs")
```

## The mapping

| garuda | PyPSA | notes |
|---|---|---|
| zone (`Z`, `zones.csv`) | `Bus` | one bus per zone; named `zone_<i>_<name>` |
| zonal demand (`demand_z<i>`) | `Load` | hourly `p_set` over the snapshots |
| transmission line (`network.csv`) | `Link` | **bidirectional, lossless** (`p_min_pu=-1`), `p_nom=Line_Max_Flow_MW` |
| generator, VRE (`generators.csv`) | `Generator` | `marginal_cost = Var_OM + fuel·heat_rate`; VRE gets the variability profile as `p_max_pu` |
| storage (`STOR≥1`) | `StorageUnit` | `max_hours = MWh/MW`, store/dispatch efficiencies, cyclic SOC |
| NSE segment (`Demand_Segment`) | `Generator` (carrier `load_shedding`) | one per segment×zone; `marginal_cost = VOLL·cost`, `p_nom·p_max_pu = NSE_Max·demand` |
| representative periods (`Sub_Weights`) | `snapshots` + `snapshot_weightings` | `objective = W[p]/H` (Σ = 8760 h); `stores = 1 h` |

### Why links, not lines

garuda's network is a **transport model**: the demand balance nets
`Σ_l incidence[l,z]·FLOW[t,l]` with `FLOW ∈ [−T_CAP, T_CAP]`, and the DC-power-flow
(susceptance / voltage-angle) block in `functions/optimizer.jl` is commented out.
A PyPSA `Line` would impose Kirchhoff's voltage law (angle constraints); a
bidirectional `Link` reproduces garuda's free transport up to the thermal limit
exactly. The incidence sign sets the direction: power leaves the `+1` zone
(`bus0`) and enters the `−1` zone (`bus1`).

## Two modes

- **`dispatch`** (default) — capacity is fixed to the existing fleet
  (`New_Build==1` candidates → 0 MW), mirroring `functions/dispatch_engine.jl`.
  This is the path validated for parity below.
- **`expansion`** — new-build units are extendable to `Max_Cap_MW` at their
  investment cost, so you can run a PyPSA capacity expansion. This is a
  faithful-as-possible translation, **not** bit-parity with garuda's UC-MILP.

## Known fidelity gaps

These are the deliberate boundaries of the translation (the roadmap's "scope the
lossy parts"):

1. **Transport vs KVL.** Lines are transport links, not angle-constrained lines;
   `Line_Loss_Percentage` is not modelled (garuda's balance is lossless).
2. **Unit commitment.** Exported generators are continuous — no binary
   commitment, minimum up/down time, or start-up cost. This matches garuda's
   default LP-relaxed dispatch (`relax_uc=true`), where the minimum-power
   constraint is non-binding; it does not capture an exact UC (MILP) dispatch.
3. **Storage discharge.** garuda caps storage *charging* at the power rating but
   not discharging (only by available energy); PyPSA caps both. Immaterial on the
   shipped datasets, where every battery is a `New_Build` candidate (0 MW in
   dispatch).
4. **Representative-period storage.** garuda makes each storage SOC cyclic
   *within* each representative period; the export concatenates the periods and
   makes SOC cyclic over the whole horizon (the standard simplification). Only
   affects `expansion` mode.

## Scope

v1 exports the **grid (zonal) layer** — buses, lines, generators, loads, storage,
snapshots. The decentralised **village/site layer** (`village_*` / `ip_*` files)
is a separate sub-problem in the source model and is **out of scope** here. In the
grid-off scenarios (`base`, `village`) the grid balance carries no village
import/export terms, so the grid-zone dispatch is independent of the village
layer — which is why a `base`-scenario run is the clean parity reference.

## Parity validation

`tools/validate_pypsa_parity.py` solves the exported `dispatch` network on HiGHS
and compares per-zone unserved energy against the garuda dispatch engine's
`reliability_results.csv`:

```bash
# 1) garuda reference (Julia): a base-scenario dispatch run
julia --project=. run_model.jl --config maluku_dispatch.json     # engine=dispatch
# 2) check the PyPSA export reproduces it
python tools/validate_pypsa_parity.py data_indonesia/2030/maluku \
    --reference results/base_maluku_2030_reference
```

The pass/fail metric is the **system-total** unserved energy. With a uniform
non-served-energy price and a connected lossless transport network the LP is
*degenerate* in which connected zone bears a given shortfall (generation can be
reshuffled over the zero-cost links), so the per-zone split is not unique — it is
reported for information but never used to pass or fail.

Measured parity (existing-fleet dispatch, LP on HiGHS both sides):

| case | zones · links | garuda total unserved | PyPSA total unserved | rel. Δ |
|---|---|---|---|---|
| maluku (2030, base) | 1 · 0 | 205 997.3 MWh (12.418 %) | 205 997.3 MWh (12.418 %) | 0.0000 % |
| sulawesi grid-only (2030, base) | 6 · 18 | 2 394 733.6 MWh (9.225 %) | 2 394 733.6 MWh (9.225 %) | 0.0000 % |

Both match to the decimal. maluku validates the generator / storage / NSE /
snapshot-weighting translation; the multi-zone case additionally validates the
inter-zone links (their per-line capacities and bus0/bus1 directions match
garuda's fixed `T_CAP` exactly).

### Reproducing the multi-zone case

The multi-zone reference must be a **grid-only** dataset (villages decouple from
the grid in `base`, but they bloat the garuda LP). Recreate the fixture by copying
just the six grid files out of a multi-zone island:

```bash
FX=data_indonesia/2030/sulawesi_gridonly; mkdir -p $FX
for f in generators demand generators_variability fuels_data network zones; do
  cp data_indonesia/2030/sulawesi/$f.csv $FX/; done
julia --project=. run_model.jl --config sulawesi_gridonly_dispatch.json   # engine=dispatch
python tools/validate_pypsa_parity.py $FX --reference results/base_sulawesi_gridonly_2030_reference
```
