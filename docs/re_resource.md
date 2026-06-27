# RE resource & siting engine

Surfaces the **developable renewable potential** of a zonal dataset — per zone and
per site — as a consumable product for developers and planners. It is the
*resource view* of the platform's analysis engines, alongside the no-solve
screening engine (`tools/screening.py`) and the dispatch/reliability engine
(`functions/dispatch_engine.jl`).

## What it produces

```
python tools/re_resource.py data_indonesia/2030/maluku
python tools/re_resource.py <folder> --csv re_resource_maluku.csv
```

Per zone (and per site, for village / industrial-park datasets) it reports:

- **Developable solar / wind capacity (MW)** — the sited ceiling
  (`max(Existing_Cap_MW, Max_Cap_MW)` over VRE units, classified solar vs wind)
- **Mean capacity factor** — capacity-weighted, from the hourly variability profiles
- **Annual energy potential (GWh)** = MW × CF × 8760

> ⚠️ **Developable MW is the GIS land-based ceiling** (suitable land × PV density),
> so it is often very large and **non-binding** — e.g. a single Sulawesi
> industrial site shows ~278 GW of *sitable* solar. It answers *"how much is
> physically possible on suitable land,"* not *"what's economic to build."* The
> capacity-expansion engine decides the latter; this number tells a developer the
> headroom. Runs on Python + pandas/numpy alone — no Julia, no solver, no GIS stack.

## The siting pipeline (upstream)

The developable-MW ceilings are produced by the GIS pipeline, which writes them
into the generator tables (`Max_Cap_MW`, and existing capacity for built units):

| Step | Tool | Does |
|------|------|------|
| 1 | `tools/dem_slope.py` | download Copernicus GLO-30 DEM for a bbox, compute slope |
| 2 | `tools/candidate_land.py` | overlay land cover × slope ≤ 15° × ~62 MW/km² → candidate-solar polygons (`.gpkg`) |
| 3 | `tools/resource_siting.py` | buffer candidate `solar_MW` within R km of each site (`village_solar_capacity()`) |
| 4 | `tools/ntt/solar_potential.py` | write per-site solar `Max_Cap_MW` into the generator table |

Capacity-factor profiles come from `tools/solar_resource_era5.py` (ERA5 reanalysis)
or `tools/solar_resource_geodata.py` (QGIS rasters). Steps 1–4 need
geopandas/rasterio and external GIS data (the DEM / land-cover layers live outside
the repo); **`re_resource.py` needs none of that** — it reads the caps the pipeline
has already baked into the dataset.

## How it fits

```
  GIS siting pipeline  ──writes Max_Cap_MW──►  zonal dataset  ──►  re_resource.py
  (dem/land/buffer/CF)                          (Layer A core)      (this summary)
```

The RE-resource engine answers *what renewable headroom a zone or site has*; the
**screening** engine says *where the existing fleet stands*; the **dispatch** and
**capacity-expansion** engines say *what to run and what to build*. Four views,
one zonal data core.
