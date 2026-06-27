# Garuda documentation

Index of the documentation for **Garuda** — the sub-national, open-source
energy-transition platform for Indonesia. New here? Start with the
[project overview](../README.md).

## Start here

| Doc | What it covers |
|-----|----------------|
| [../README.md](../README.md) | What Garuda is, the four analysis engines, and a quick start |
| [environment_setup.md](environment_setup.md) | Julia / Python setup, and the optional Gurobi licence |

## Inputs & data

| Doc | What it covers |
|-----|----------------|
| [../data_indonesia/README.md](../data_indonesia/README.md) | Input data dictionary — every CSV, column by column |
| [new_region_guide.md](new_region_guide.md) | Add a new island / region to the model |
| [ntt_data_integration.md](ntt_data_integration.md) | The NTT / Timor data pipeline (source workbooks → model inputs) |

## Modelling & results

| Doc | What it covers |
|-----|----------------|
| [../MODEL.md](../MODEL.md) | The optimisation formulation (capacity expansion + dispatch), cross-referenced to the code |
| [village_adaptation.md](village_adaptation.md) | Site (village / industrial) modelling and scenario semantics |
| [outputs_guide.md](outputs_guide.md) | Result files, columns, and headline metrics |
| [pypsa_export.md](pypsa_export.md) | Export the zonal network to PyPSA + dispatch-parity validation (Phase 4) |
| [experience_layer.md](experience_layer.md) | The guided run launcher and the HTML/PDF auto-report (Phase 5) |

## Renewable resource & siting

| Doc | What it covers |
|-----|----------------|
| [re_resource.md](re_resource.md) | The RE-resource engine + the GIS siting pipeline behind it |
| [resource_siting.md](resource_siting.md) | Candidate-land screening → per-site developable MW |
| [solar_resource_era5.md](solar_resource_era5.md) | Solar capacity factors from ERA5 reanalysis |
| [solar_resource_geodata.md](solar_resource_geodata.md) | Solar capacity factors from QGIS rasters |
| [calculators/](calculators/) | Sectoral demand calculators (per-archetype load profiles) |

## Development

| Doc | What it covers |
|-----|----------------|
| [../CHANGES.md](../CHANGES.md) | Development log — every change, with its verification |
