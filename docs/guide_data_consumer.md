# Data-consumer guide

*For developers and data engineers who want Garuda's **zonal data** as an asset —
to load it, validate it, transform it, or export it — without necessarily running
the optimiser.*

Garuda's design rule is that the data is an engine-agnostic asset: engines never
own it, and you can consume it directly. This guide is the on-ramp; the
column-by-column dictionary lives in
[`../data_indonesia/README.md`](../data_indonesia/README.md).

## The shape of the data

The model resolves Indonesia as **islands → grid `zones` → decentralised `sites`**.
One folder per `data_indonesia/<year>/<island>/` holds a flat set of CSVs:

| File | What it is |
|---|---|
| `generators.csv` | grid-side generators + storage (one row per unit) |
| `demand.csv` | system settings, the representative-period **time structure**, and hourly zonal demand (`demand_z<i>`) |
| `generators_variability.csv` | hourly availability factor per generator (VRE profiles; 1.0 for firm) |
| `fuels_data.csv` | fuel price + CO₂ content |
| `network.csv` | transmission paths (grid scenarios), with a ±1 zone-incidence matrix |
| `zones.csv` | zone integer → human name (multi-zone islands) |
| `<site>_generators.csv`, `<site>_demand.csv`, … | the decentralised **site** layer (see vocabulary below) |

## Two ways to consume it

**1. Pure Python (no Julia, no solver).** Every table is a plain CSV; the
no-solver engines read them directly with pandas/numpy. Mirror their reader to
avoid two gotchas — a leading BOM, and the literal fuel `"None"`:

```python
import pandas as pd
def read(p): return pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
gens = read("data_indonesia/2030/sulawesi/generators.csv")
```

See `tools/screening.py` and `tools/re_resource.py` for worked examples.

**2. The Julia data core.** `build_system(folder)` returns a `ZonalSystem` — a
named, documented wrapper over the loaded tables and the derived sets
(`G`, `Z`, `VRE`, `STOR`, `T`, `sample_weight`, `zone_names`, …):

```julia
include("functions/function_compiler.jl")
sys = build_system("data_indonesia/2030/sulawesi")   # sys.G, sys.demand, sys.Z, …
```

## The site vocabulary (a key generality)

A **site** is a decentralised demand+generation node within a zone. Three input
spellings are accepted, resolved at load time (`functions/site_aliases.jl`):

| spelling | study lineage |
|---|---|
| `site_*` / `Site` | canonical (new datasets) |
| `village_*` / `Village` | 100 GW village-solar study |
| `ip_*` / `Industrial_Park` | captive-industrial study (`data_indonesia/captive/`) |

The loader normalises any of them, so the same code path handles all three.
**Result files always use the canonical `site_*` names.**

## The time-structure gotcha

`demand.csv` is **not** 8760 hourly rows — it is `Rep_Periods × Timesteps_per_Rep_Period`
representative hours (commonly 8 × 168 = 1344). `Sub_Weights` gives the hours each
period represents (Σ = 8760), so the annualising weight per hour is
`sample_weight[t] = Sub_Weights[p] / Timesteps_per_Rep_Period`. **The weights are
not uniform across periods**, so a per-hour quantity cannot be annualised by a
single ×(8760/T) factor — weight each hour. (This is why the report anchors annual
figures on the input demand; see [`experience_layer.md`](experience_layer.md).)

## Validate before you trust

```bash
python tools/validate_schema.py data_indonesia/2030/<island>
```

Catches R_ID gaps, wrong row counts, misaligned zones, a `Sub_Weights` sum that
doesn't annualise, unknown fuels, and bad network incidence — the structural
errors that otherwise surface as a cryptic crash mid-solve. It is also importable
(`from tools.validate_schema import validate_dataset`).

## Export to an established framework

Hand the zonal network to **PyPSA** instead of re-implementing it:

```bash
python tools/export_pypsa.py data_indonesia/2030/sulawesi --netcdf sulawesi.nc
```

Dispatch parity against the native engine is validated within a configurable
tolerance (default 1 %) on the system total — and matches to 0.0000 % on the
tested cases; see [`pypsa_export.md`](pypsa_export.md).

## Bringing your own data

To add a region, follow [`new_region_guide.md`](new_region_guide.md): create the
folder, populate the CSVs (canonical `site_*` spelling), and validate. The schema
contract is the dictionary in [`../data_indonesia/README.md`](../data_indonesia/README.md).
