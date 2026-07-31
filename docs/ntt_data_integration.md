# NTT → Model: Timor village-solar data integration

This document explains, for our partner, exactly how three Indonesian source
workbooks become **modeling-ready inputs** for the Timor village-solar
capacity-expansion study — what each file contributes, how the fishing
**calculator** spreadsheet was reimplemented as a Python program, and every
assumption and unit conversion made along the way.

Everything lives in the `tools/ntt/` Python package. English copies of the three
workbooks are in `data_indonesia/source_ntt/english/`.

---

## 1. Scope and the three source files

**Study scope: Timor island — four kabupaten:** Kupang, Timor Tengah Selatan,
Timor Tengah Utara, Belu (**780 villages**). Each village is modelled
individually as one node on a single shared Timor grid; whether a village
*connects* to that grid (and can then export surplus solar to supplement others)
or stays a **standalone islanded microgrid** is a decision the optimiser makes.

| File | English name | Contributes |
|------|--------------|-------------|
| `Data potensi desa.xlsx` | Village Potential Data | Per-village **households & electrification** (on PLN / non-PLN / unelectrified) and **economic sector** → demand scale + archetype. |
| `NTT_Data_Desa.xlsx` | NTT Village Dataset | Per-village **solar resource (GHI)** + **lat/long** → solar capacity factor + interconnection distance. |
| `Kalkulator … KDKMP_v6.xlsx` | Fishing-Village Calculator | The **fishing archetype calculator** — demand, equipment sizing, investment, revenue. Reimplemented as `tools/ntt/calculators/fishing.py`. |

---

## 2. The pipeline

```
 Data potensi desa.xlsx ─┐
                         ├─►  sources.py  ──►  Village records  ──►  calculators/<archetype>.py
 NTT_Data_Desa.xlsx ─────┘     (join + filter      (households,        (demand, sizing, costs)
                                to 4 kabupaten,      GHI, archetype)            │
                                assign archetype)                               ▼
 KDKMP workbook ──►  fishing.py (one of ~10 calculators)        build_timor.py  ──►  model-ready CSVs
                                                                                     (data_indonesia/2030/timor/)
```

Module layout (`tools/ntt/`):

| File | Role |
|------|------|
| `sources.py` | Read + normalise + join the two data workbooks; filter to the four kabupaten; assign each village an archetype. |
| `archetypes.py` | The archetype registry, keyword-assignment rules, and shared load/solar profile shapes. |
| `calculators/base.py` | The `Calculator` contract every archetype implements (`demand → sizing → costs → revenue`). |
| `calculators/fishing.py` | **KDKMP workbook translated to Python** (validated — §5). |
| `calculators/<9 others>.py` | Stub programs for the other nine archetypes (inherit the residential default until their workbooks arrive). |
| `costs.py` | IDR → annualised USD/MW-yr conversion (§4). |
| `build_timor.py` | Orchestrator: villages × calculators → the CSV dataset + manifest. |
| `translate_workbooks.py` | English copies of the three workbooks. |

Run it:
```bash
python -m tools.ntt.translate_workbooks --src-dir <folder-with-3-xlsx>
python -m tools.ntt.build_timor        --src-dir <folder-with-3-xlsx> [--kabupaten belu]
python -m pytest tests/test_fishing_calculator.py     # validate the calculator
```

---

## 3. Archetypes (one calculator per archetype)

A village's **archetype** is its dominant economic activity; each archetype has
(eventually) its own calculator program. Assignment is driven by the *specific*
agricultural subsector and commodity — **not** the umbrella sector text
"Pertanian, kehutanan, dan perikanan", which contains the words *fisheries* and
*forestry* and would otherwise mis-tag almost every village.

**Timor distribution (780 villages):**

| Archetype | Villages | Calculator status |
|-----------|---------:|-------------------|
| Food crops (rice / maize) | 621 | stub → default recipe |
| Trade / retail / services | 61 | stub |
| Horticulture | 46 | stub |
| Livestock | 15 | stub |
| Government / services | 15 | stub |
| Plantation / estate crops | 14 | stub |
| **Fishing** | 7 | **implemented (KDKMP)** |
| Manufacturing | 1 | stub |

> Note for the partner: Timor is overwhelmingly a **food-crop (maize/rice)**
> region — fishing is only 7 villages. The fishing calculator is the worked
> template; the highest-value next calculators to translate are **food crops**
> and **horticulture/livestock**. The canonical list of ten archetypes and their
> calculators should be confirmed with the partner. Until a dedicated calculator
> exists, an archetype uses the residential-only default recipe (households ×
> 3.4 kWh/day + solar/battery sizing), so its productive load is **not yet
> represented**.

---

## 4. Unit conversion: IDR capex → annualised USD/MW-yr

The model wants annualised investment in **USD/MW-year** (and USD/MWh-year for
storage energy); the calculators give overnight capital in **Rp/kWp** (or
Rp/kWh). `tools/ntt/costs.py` is the single conversion point:

```
usd_per_mw   = (idr_per_kw / FX_RATE) * 1000
crf          = r (1+r)^n / ((1+r)^n − 1)            # capital recovery factor
inv_per_mwyr = usd_per_mw * crf
```

Defaults (all overridable): `FX_RATE = 16,000 Rp/USD`, discount rate `r = 0.10`,
lifetimes solar 25 yr / battery 12 yr / diesel 15 yr / grid 30 yr. Fixed O&M is
taken as a fraction of overnight capex (solar/battery ≈ 2 %/yr). These reproduce
the magnitudes already in `tools/make_timor_demo.py` (solar ≈ $75k/MW-yr,
battery ≈ $30k/MW-yr power + $18k/MWh-yr energy).

---

## 5. Field-by-field mapping

**`Data potensi desa.xlsx` → village roster, demand scale, archetype**

| Source column | English | Use |
|---------------|---------|-----|
| `NAMA_KAB / KEC / DESA` | Regency / District / Village | identity, join key, kabupaten filter |
| `nama_subsektor_pertanian`, `NAMA_KOMODITAS` | Agri subsector / commodity | **archetype assignment** |
| `nama_lapangan_usaha` | Umbrella sector | archetype only for non-agriculture rows |
| `jml_kel_listrik_pln` + `_nonpln` + `_tanpa_listrik` | households (PLN / non-PLN / none) | total households `KK` → residential demand |

**`NTT_Data_Desa.xlsx` → solar resource & location**

| Source column | English | Use |
|---------------|---------|-----|
| `GHI Rata-rata (kWh/m²/hari)` | Average GHI | **solar capacity factor** (peak-sun-hours = GHI × performance ratio 0.80) |
| `Longitude`, `Latitude` | coordinates | interconnection distance, spatial reporting |

Join on normalised `(Regency, District, Village)`, with a `(Regency, Village)`
fallback for district-spelling mismatches. Of 780 Timor villages, **627 match a
GHI record directly**; the other 153 fall back to their **kabupaten-mean GHI**
(flagged `ghi_matched = False` in the manifest).

**KDKMP workbook → the fishing calculator** — see
[`docs/calculators/fishing_KDKMP.md`](calculators/fishing_KDKMP.md) for the
sheet-by-sheet translation and validation table.

---

## 6. How villages are represented in the model

`build_timor.py` writes, into `data_indonesia/<year>/<name>/`:

- **`village_generators.csv`** — per village (all `Zone=1`): an **existing diesel**
  (`New_Build=0`, `Commit=0`, sized to ≈1.1× village peak, capital sunk, fuel
  ≈ $18/MMBtu — the incumbent solar competes against); a **candidate solar PV**
  (`New_Build=1`, GHI-scaled); a **candidate battery** (`New_Build=1, STOR=1`).
- **`village_demand.csv`** — per-village hourly load: residential (households ×
  3.4 kWh/day) + the archetype's productive load, shaped by an hour-of-day curve
  and scaled so the series integrates to the annual total.
- **`village_demandheat.csv`** — zeros (electricity-only).
- **`village_generators_variability.csv`** — each village's solar profile scaled
  to its own GHI; diesel/battery flat 1.0.
- **`village_connection.csv`** — per-village interconnection cost (`Cost_per_yr`)
  and capacity cap (`Max_Connect_MW`): the price of connecting to the shared
  Timor grid, from a fixed tap cost + a distance-to-centroid MV-feeder cost,
  annualised. This is what the model's connect-vs-island decision weighs.
- **Shared grid backstop** — a minimal single-zone grid (`generators.csv` with one
  PLN diesel, zero separate grid demand, plus `demand.csv`,
  `generators_variability.csv`, `fuels_data.csv`, single-zone `network.csv`) so
  the bus can **supply** village imports and the model can exercise the grid
  scenario. It cannot **absorb** village exports for their own sake: `vGEN >= 0`
  means a generator cannot sink power, this dataset has no grid storage (the
  `STOR` set is empty), and `demand_z1` is 0 for all 1344 hours — so the zonal
  balance forces `Σ village export ≤ Σ village import` every hour. Village↔village
  sharing is fully representable; village→grid **sales** are not. Add a grid load
  first (§6a).
- **`timor_villages_manifest.csv`** — village → kabupaten / archetype / GHI /
  households / coords / demand, for re-joining results.

**Model changes that make sharing possible (implemented in `functions/`):**
village **export** to the grid bus (`vVIL_EXPORT`, a sink in the village balance
and a source in the zone balance), and a per-village binary **grid-connection**
decision (`vVIL_CONNECT`) that gates import/export against the interconnection
cost from `village_connection.csv` (added to the objective). Village diesel is
kept `Commit=0` so the only binaries are the connection decisions. Results add
`site_connection_results.csv` (per-site `Connected` + import/export MWh)
and `transmission_flow_results.csv`.

**Verified (Belu, 81 villages, `gridvillage`):** the model builds and solves to
optimality. With the first-pass interconnection costs, **0 villages connect**
(standalone solar+battery beats interconnection — a sensible result). With
connection made cheap, **18/81 connect and surplus solar flows village→bus→village
(export = import, balanced)** — confirming the sharing mechanism end-to-end. How
many villages connect is sensitive to the interconnection-cost calibration and
to village heterogeneity (GHI/demand diversity); tune `village_connection.csv`
for the study.

---

## 6a. Giving the grid bus a real load (`build_grid_demand.py`)

`timor` ships `demand_z1 = 0` for all 1344 hours. That is deliberate and it is
fine for the coordination question, but it makes any **export** question
unanswerable: with no grid load, no grid storage and `vGEN ≥ 0`, the zonal
balance forces `Σ village export ≤ Σ village import` in every hour. A run on
plain `timor` with `export_price > 0` measures a data artifact — village↔village
sharing — not village→grid sales.

```bash
# inspect the derivation (writes nothing)
python -m tools.ntt.build_grid_demand --share 0.42

# build the market dataset
python -m tools.ntt.build_grid_demand --share 0.42 \
    --out-dataset timor__market --fleet rescale
```

**Where the load comes from.** `nusa_tenggara` is the only committed dataset
covering NTT, and its **zone 2 is East Nusa Tenggara** — the province Timor sits
in. The donor ships no `zones.csv`, so the zone identity is read from
`generators.csv::Province` (`east_nusa_tenggara` → zone 2), overridable with
`--donor-zone`.

**Annualisation must use the donor's own `Sub_Weights`.** They are non-uniform
(2022, 505, 168, 2527, 1516, 842, 337, 843 hours; the target's are a uniform
1095), so the two annualisations disagree:

| | GWh/yr |
|---|---:|
| donor zone 2, **weighted** (correct) | **2,919** |
| donor zone 2, equal-weight (wrong, +2.9 %) | 3,003 |

**The derivation**, at the default `--share 0.42`:

| Step | Value |
|---|---:|
| donor zone 2, weighted | 2,919 GWh/yr, peak 419 MW, LF 0.82 |
| × Timor share 42 % → gross Timor system | 1,226 GWh/yr, peak 176 MW |
| − village load (already separate nodes) | 544 GWh/yr |
| **= `demand_z1`** | **682 GWh/yr, peak 124 MW, LF 0.63** |

The share is an assumption sitting in front of the headline: 0.42 is PLN's
Sistem Timor peak (131 MW) over NTT's (296.6 MW), bracketed by 0.33 (population
share) and 0.47. At 0.42 the implied growth from Timor's actual 131 MW in 2025 is
+6.1 %/yr, consistent with Flores at 8.26 %/yr.

**Two things the tool is careful about.**

- **Double counting.** The 780 villages are already modelled as their own nodes
  *and* they sit inside the provincial total, so village load is netted out hour
  by hour: `demand_z1[t] = share × donor_z2[t] − Σ village demand[t]`. At 0.42 six
  of 1344 hours net slightly below zero (village load exceeds Timor's share of
  the provincial load in those hours — an artifact of differencing a top-down
  provincial forecast against a bottom-up household build-up); they are clipped
  to 0, which adds 0.24 GWh/yr, and both numbers are printed. The clipped hours
  disappear at `--share 0.47`.
- **The donor's calendar weeks differ.** Donor weeks are 24, 3, 4, 45, 8, 46, 39,
  5; the target's are 2, 9, 16, 24, 32, 40, 46, 52. The hourly shape is carried
  across position-for-position and rescaled so the gross annual is exact under the
  *target's* weights. This transplants load **shape, not season** — defensible for
  NTT's weakly seasonal load, but it is an assumption.

**`--fleet` is mandatory when writing a dataset.** `timor/generators.csv` is one
non-expandable 122 MW diesel. Write ~124 MW of grid peak against it and the
balance closes on segment-1 non-served energy at
`Voll × Max_Demand_Curtailment` = **$2,000/MWh**, which values every exported
village MWh at scarcity — garbage that reads as a spectacular business case. So:

- `--fleet rescale` transplants the donor zone's fleet onto the Timor bus.
  **Existing** units are allocated by name (`--existing named`, the default):
  `pltu_kupang_ftp1`, `pltu_timor_1` and `pltu_atambua` are physically on Timor and
  carried at 100 % (157 MW); `pltu_ende_ftp1`, `pltu_alor` and `pltu_rote_ndao` are
  on other islands in the same province and dropped. `--existing rescale` instead
  gives Timor `--share` of every plant. **Candidates** are scaled by `--share`.
- `--fleet none` keeps the base fleet and prints the warning above.

Two donor-data traps the tool handles, both worth knowing if you write another
transplant:

- **Fuel prices disagree between the datasets.** `nusa_tenggara` prices diesel at
  **$0.5659/MMBtu**; `timor` prices it at **$18/MMBtu** (the NTT field number
  behind the ~$197/MWh grid-diesel marginal cost). `--fuel-source target` (the
  default) keeps the target's prices and adds only the fuels it lacks (coal, gas,
  biomass, biogas); `--fuel-source donor` takes the donor table wholesale and
  **replaces** the diesel price. Getting this wrong moves grid diesel from
  ~$197/MWh to ~$14/MWh and decides the export result by itself.
- **`generators_variability.csv` maps to generators by POSITION, not by name.**
  `input_data.jl` drops the first column and indexes the rest by `R_ID`, padding
  missing trailing columns with 1.0. The donor repeats 26 resource names
  (`plts_sumba` nine times), so its CSV has duplicate headers and its column names
  stop matching its own generator order from position 9 on. A by-name lookup
  silently wires the wrong profile onto a unit.

**Known limitation.** The transplanted candidate set carries NTT-*wide*
renewable potential scaled by `--share`, not Timor-sited potential: at 0.42 that
is 4,290 MW of wind and 3,132 MW of solar against a 124 MW peak. Most of it will
never be built, but it does set the marginal price. Use `--drop-tech wind` (and
inspect the printed candidate-by-technology table) when that matters, and treat
the grid-side new-build costs as a swept parameter rather than a given.

---

## 7. Known assumptions & gaps (read before citing results)

- **Hourly profiles are synthesized.** No measured load or irradiance time series
  exists in the source. Solar = a clear-sky bell shape scaled to each village's
  GHI; demand = an archetype hour-of-day shape scaled to the annual total. Real
  metered profiles would replace these.
- **Costs depend on the FX / discount / lifetime assumptions in §4.**
- **Diesel sized to peak** as the existing baseline (no per-village genset
  inventory in the data).
- **153 villages use kabupaten-mean GHI** (no direct GHI match).
- **9 of 10 archetypes use the residential-only default recipe** — their
  productive load is a placeholder until their calculators are supplied.
- **Interconnection cost is a first-pass model** (fixed tap + distance × per-km),
  to be tuned so the connect-vs-island split is realistic.
