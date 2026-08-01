# Figure plan — Timor village-solar results

**Single valid results source for everything in §1:** `/home/pwrlabadmin/garuda/.claude/worktrees/repo-orientation-sync-bd6b46/results/village_timor_2030_reference/` (A1a village, coordination OFF). It is a pure LP — `timor` has no `Commit==1` village units — so there is no MIP gap and no incumbent caveat on this leg.

**Blocked directories confirmed empty (0 files) as of this pass:** `results/gridvillage_timor_2030_reference__mip1e4/`, `results/gridvillage_timor__marketfix_2030_reference/`, `results/village_timor__marketfix_2030_reference/`. `results/gridvillage_timor_2030_reference/` is populated but is the provably-suboptimal A1a-ON incumbent ($69.545469 M against a feasible $69.134350 M — a negative coordination value, impossible by dominance).

---

## 0. Build this first: `tools/village_cost_attribution.py`

Nine of the figures below need per-village annualised cost, which **no result CSV contains**. I re-derived and verified it this pass; ship it as a tool so the numbers are reproducible rather than pasted.

```
generators: cost = Change_in_MW.clip(0)*Inv_Cost_per_MWyr
                 + Total_MW*Fixed_OM_Cost_per_MWyr
                 + Electricity_GWh*1000*(Var_OM_Cost_per_MWh
                                         + Heat_Rate_MMBTU_per_MWh*fuel_price)
storage:    cost = Change_in_Storage_MWh.clip(0)*Inv_Cost_per_MWhyr
                 + Total_Storage_MWh*Fixed_OM_Cost_per_MWhyr
```
Join `site_generator_results.csv::ID` and `site_storage_results.csv::ID` to `village_generators.csv::R_ID`; diesel fuel price `18.0 $/MMBtu` from `fuels_data.csv`. **Beware the merge:** both `site_storage_results.csv` and `village_generators.csv` carry a `Village` column — merge on `ID`/`R_ID` and suffix, or the groupby key vanishes.

Verified this session: reconstruction = **$69,134,350.4310** against reported `Total_Costs` = **$69,134,350.4310** (residual $4.7e-6, i.e. 12 s.f.). Component split, all measured:

| Component | $M/yr | Share |
|---|---|---|
| Battery **energy** (MWh) | 35.6002 | 51.5% |
| Solar (inv + FOM) | 25.2364 | 36.5% |
| Battery **power** (MW, inv + FOM) | 4.6042 | 6.7% |
| Diesel fuel + VOM | 3.2974 | 4.8% |
| Battery throughput VOM | 0.2763 | 0.4% |
| Diesel fixed O&M | 0.1198 | 0.2% |

Note the reallocation: `cost_results.csv` books battery **power** inside `Fixed_Costs_Village` ($29.9604 M) alongside solar. Read naively, that file says "solar = $29.96 M, storage = $35.60 M". The truth is solar $25.24 M, storage $40.20 M (58.2%). Every cost figure must show the reallocation explicitly.

---

## 1. Ready now

Ranked by value per unit of effort. All columns named exactly as they appear on disk.

### F1 — Where the money goes: a storage programme with solar attached
- **Question:** What are we buying, and which line item do we negotiate hardest on?
- **Chart:** Single horizontal stacked bar, $M/yr, six segments in the table above, with the two battery segments bracketed and labelled "storage: $40.20 M/yr = 58.2%".
- **Columns:** `cost_results.csv::{Total_Costs, Fixed_Costs_Village, Fixed_Costs_Village_Storage, Variable_Costs_Village}` for the closure check; the §0 reconstruction for the split; `village_generators.csv::{Inv_Cost_per_MWyr, Inv_Cost_per_MWhyr, Fixed_OM_Cost_per_MWyr, Fixed_OM_Cost_per_MWhyr}`.
- **Earns its slot:** overturns the default assumption that a solar programme is a solar procurement. A 20% battery cost reduction is worth $8.0 M/yr; the same cut on solar is worth $5.0 M/yr. Cheapest figure in the set and the most directly actionable.
- **Must carry:** the caption line reconciling $46/MWh solar LCOE against $127.47/MWh delivered (measured mean; median $127.69), or a sceptic finds the gap first. Battery power capex is not one number — it ranges $9,173–$30,001/MW-yr across rows.

### F2 — One recipe for 780 villages
- **Question:** Do we need 780 bespoke designs, or one standard kit?
- **Chart:** Two narrow histograms + a "kit" schematic panel.
- **Measured this session (use these, not the lens figures):** solar per MW of village peak — median **2.957**, IQR 2.895–2.993, min 2.748, max 4.473. Storage duration — mean **5.5579 h**, s.d. 0.0358, IQR 5.5611–5.5616, min 5.180, max 5.562. Island totals 360.701 MW solar, 148.514 MW battery power, 825.085 MWh battery energy.
- **Columns:** `site_generator_results.csv::{Village, technology, Total_MW}`; `site_storage_results.csv::{Village, Total_Storage_MWh}`; `timor_villages_manifest.csv::{Village, peak_mw}` (**not** `village_solar_potential.csv::peak_mw` — the two differ, mean 0.1566 vs 0.1644).
- **Earns its slot:** converts a 780-village planning problem into a catalogue with a sizing rule. Most programme-relevant result in the run and invisible in every system-level table.
- **Must carry:** the tightness is substantially manufactured by the inputs — one solar profile family, GHI spanning only 4.908–5.952 kWh/m²/day, 621 of 780 villages on a single demand archetype. The honest claim is "given these archetypes and this resource data, one design is optimal everywhere". And 5.56 h is a continuous optimum, not a product: commercial BESS ship in 2 h and 4 h blocks.

### F3 — Diesel does not disappear; it shrinks to a 3% insurance policy
- **Question:** Does going solar mean scrapping the gensets?
- **Chart:** Two panels — before/after diesel capacity columns, and a 100%-stacked energy bar.
- **Verified:** diesel `Start_MW` 134.3455 → `Total_MW` **6.6558** (−95.0%); diesel 16.738 GWh vs solar 577.484 GWh, i.e. **2.82%** of generation. Battery discharge 276.331 GWh is deliberately excluded from the denominator — state the denominator on the figure.
- **Columns:** `site_generator_results.csv::{technology, Total_MW, Start_MW, Change_in_MW, Electricity_GWh}`.
- **Earns its slot:** pre-empts the standard misreading with a counter-intuitive operational fact — fuel logistics shrinks ~40×, the maintenance footprint does not shrink at all.
- **Must carry:** the 6.66 MW residual is a continuous variable spread across 780 sites (median ~6 kW), not a procurable genset size.

### F4 — Land never binds: maximum utilisation is 9.4%
- **Question:** Will land acquisition hold this programme up?
- **Chart:** Log-log scatter, built solar MW against the **enforced** ceiling, with 1:1 and 10×/100×/1000× iso-headroom diagonals; inset ECDF of utilisation.
- **Columns:** `village_generators.csv::Max_Cap_MW` for the solar rows — **this is the enforced ceiling**, verified `np.allclose` identical to `village_solar_land.csv::developable_MW` (read with `comment='#'`, three header lines). Median 233.6 MW, min 2.84, max 1,449.8. `site_generator_results.csv::{Village, technology, Total_MW}`.
- **Verified utilisation:** median **0.155%**, max **9.44%**, zero villages above 10%.
- **Earns its slot:** kills a whole category of objection, and tells the GIS team that further land refinement changes no answer.
- **Do not use `village_solar_potential.csv::solar_cap_MW`.** It is a different GIS vintage (median 3,246.8 MW, ~14× larger, correlation 0.15 with the enforced column) and using it inflates the headroom claim by an order of magnitude. This is the single easiest mis-join in the dataset.
- **Must carry:** 153 villages have `source=fallback` and an imputed ceiling (Village 1 = 233.60 MW at `developable_km2 = 0.0`) — draw them hollow. The ceiling is physical area only at 50 MWp/km² within 10 km, excluding "Settlement Area"; it says nothing about ownership or adat claims.

### F5 — The wire costs more than the village system it would supply
- **Question:** Is public money better spent on transmission to villages, or on the villages themselves?
- **Chart:** Log-log scatter, annual connection cost against reconstructed standalone system cost, with a 1:1 diagonal; marginal histogram of the ratio.
- **Verified this session:** **295 of 780** villages sit above the 1:1 line (wire > entire local system). Median ratio **0.762**. Connecting all 780 = **$40.888 M/yr** against a $69.134 M/yr village system — **59%**.
- **Columns:** `village_connection.csv::{Village, Cost_per_yr, Max_Connect_MW}`; §0 reconstruction; `village_solar_potential.csv::{Village, hubdist_km, kabupaten}`.
- **Earns its slot:** answers the grid-extension-versus-DG capital question with per-village evidence and without touching any degenerate or suboptimal output.
- **Correction to the lens draft:** the claim "all 780 have connection costs so this figure does not suffer the coordinate gap" is **false**. Exactly **153** rows carry the imputed flat `Cost_per_yr = $27,514` (the `tools/connection_cost.py --default-km 10` default, and also the 25th percentile of the distribution). Draw them as open glyphs and report the count both ways: **295 of 780 overall, 285 of the 627 with measured distances**. Do not colour by `hubdist_km` — it is null for those 153.
- **Must carry:** this is a cost comparison, not a benefit comparison — pair with F10. And the per-village radial charge captures no shared-trunk economies, which is a genuine reason it overstates the case against interconnection.

### F6 — No kabupaten is left behind: cost per household is flat
- **Question:** Will electrifying TTS cost my constituents more than Kupang?
- **Chart:** Horizontal strip plot, one row per kabupaten, one jittered dot per village, box overlay, island median rule.
- **Verified medians ($/household-yr):** KUPANG **157.26** (n=228), TTU **158.73** (n=193), TTS **158.87** (n=278), BELU **159.48** (n=81). Island: min 148.11, median **158.48**, 95th 161.67, max 217.82. Spread across kabupaten medians: **1.4%**.
- **Columns:** §0 reconstruction ÷ `timor_villages_manifest.csv::households`; `village_solar_potential.csv::{kabupaten, archetype, desa}`.
- **Earns its slot:** defuses the distributional fight and supports a single national tariff rather than district-differentiated support.
- **Must carry:** flatness is largely inherited from the demand model — 7 of 8 archetypes carry a literal-constant 1,241 kWh/household/yr. Label the right-tail outliers (TESABELA $217.8, AKLE $206.5, TABLOLONG $206.4 — all fishing, all Kupang) with their **$/MWh** as well: they cost more per household but less per MWh (~$103 against a $127.69 median), so a per-household-only view would wrongly brand them inefficient.

### F7 — Energy and CO₂ balance closes to solver precision
- **Question:** Does supply equal demand plus losses in the reported results?
- **Chart:** Horizontal waterfall with a magnified residual inset; second small panel for the CO₂ identity.
- **Terms:** solar +577.484 GWh, diesel +16.738, demand −544.075, battery round-trip loss −50.147 (computed as `276.331 × (1/0.92² − 1)`), NSE −3.8e-8, residual ≈ **−2.5e-11 GWh** (−25 µWh). CO₂: `16,738.2 MWh × 10.5 MMBtu/MWh × 0.0732 tCO₂/MMBtu = 12,864.96 t` against `clean_energy_results.csv::CO2_Emissions_Village = 12,864.96078`.
- **Columns:** `site_generator_results.csv::Electricity_GWh`; `site_nse_results.csv::Total_NSE_MWh`; `village_demand.csv` annualised at 1095/168; `village_generators.csv::{Eff_Up, Eff_Down, Heat_Rate_MMBTU_per_MWh}`; `fuels_data.csv::CO2_content_tons_per_MMBtu`; `clean_energy_results.csv`.
- **Earns its slot:** validates four separate places a modelling error hides (round-trip efficiency, `sample_weight` annualisation, the fuel/heat-rate join, the emissions factor) in one picture. Appendix slide 1.
- **Must carry:** closure proves internal consistency, not correctness. The battery-loss term is *inferred* from discharge, not read from a charge column — there isn't one. The 3.8e-8 MWh NSE is a solver tolerance artifact, not a reliability finding.

### F8 — Realised output tracks the resource: a positional-mapping validator
- **Question:** Did each village's solar generator get its own profile, or has a column mis-mapping gone undetected?
- **Chart:** Scatter of realised CF against available CF, 1:1 line plus a fitted `y = 0.9845x` line; residual strip against village index in file order.
- **Columns:** `village_generators_variability.csv` (2,341 columns; **column 1 dropped unconditionally**, profile column *g* belongs to `R_ID` *g*, names ignored — `input_data.jl:72`); `village_generators.csv::{R_ID, technology}`; `site_generator_results.csv::{Total_MW, Electricity_GWh}` for realised CF = `Electricity_GWh*1000/(Total_MW*8760)`; `timor_villages_manifest.csv::{ghi, ghi_matched}` for colour.
- **Reference numbers:** available CF 0.1636–0.1984, realised 0.1611–0.1953, implied uniform curtailment ~1.55%, `corr(available, realised) = 0.9999982`, `corr(GHI, available CF) ≈ 1.0`.
- **Earns its slot:** the only figure that validates the input plumbing rather than the output arithmetic — and this codebase's variability files are positional, where a generator past the last column silently becomes firm capacity at 1.0 availability.
- **Must carry:** it detects a mis-*mapping*, not a mis-*scaled* profile common to all villages. 153 villages have `ghi_matched = False` — distinct marker.

### F9 — How little the optimiser actually decided
- **Question:** Are these 780 design decisions, or one rule applied 780 times?
- **Chart:** Three stacked histograms whose x-axes span the **engineering** range a reader would expect, not the observed range — each collapses to an invisible spike, with a 50×-magnified inset showing the real spread. Refusing to zoom is the message.
- **Panels:** storage duration on a 0–12 h axis (5% 5.5608, 95% 5.5618); solar MW per GWh/yr on 0–2 (median 0.667); retained diesel as a fraction of existing nameplate on 0–1 (essentially 4.94% everywhere).
- **Columns:** `site_generator_results.csv`, `site_storage_results.csv`, `timor_villages_manifest.csv::{annual_kwh, diesel_mw}`.
- **Earns its slot:** sets the ceiling on how hard every other per-village figure may be pushed. Pairs directly with F2 as its methodological counterweight.
- **Must carry:** near-uniform ratios are the *correct* answer to near-identical problems; this argues for honest framing, not for abandoning site-level modelling. Verify the 4.94% diesel panel against `village_generators.csv::Min_Power_MW` before captioning it — it may be a commitment floor, not an economic choice.

### F10 — Coordination value on `timor` is a bound, not a bar
- **Question:** What is coordination worth, and how much of that did the solver actually resolve?
- **Chart:** Horizontal interval chart on one $M/yr axis zoomed to 68.9–69.7. Four rows:
  1. `village` exact LP optimum, point at **69.134350** ("pure LP, no binaries, no MIP gap").
  2. `gridvillage` root LP relaxation, left bracket at **68.967491** ("lower bound on the ON optimum").
  3. The implied coordination-value interval **[$0, $166,859]/yr** — left edge a hard stop labelled "zero by dominance: fixing all 780 `vVIL_CONNECT` to 0 reproduces row 1 exactly and is feasible for the ON problem".
  4. In a warning hue and drawn **wider than row 3**: the ±$690,000 that `mipgap 0.01` permits on a $69 M objective, with the incumbent 69.545469 plotted inside it, cross-hatched INVALID, annotated "provably suboptimal by ≥ $411,118; achieved gap 0.8311%".
- **Columns:** the two `cost_results.csv::Total_Costs`; `RUN_LOG.md` ledger for the root bound `6.896749080623e+07` and achieved gap.
- **Earns its slot:** row 4 visibly swallowing row 3 says in one glance that the permitted tolerance is ~4× the entire quantity being measured. It is the study's headline, it is a null, and this form makes the null unarguable instead of apologetic.
- **Must carry:** the upper bound is an LP relaxation, label it "at most". The bracket is only valid for plain `timor`, where `demand_z1 = 0` for all 1344 hours and no grid load can absorb a village export — so the ceiling is close to structural, not an empirical finding about Timor. Never quote a percentage off the truncated axis.

### F11 — Two diversity factors: villages cannot trade with each other, but can with the grid

**Rescoped 2026-08-01.** The original version showed only the within-village null
and concluded "there is nothing to trade". That over-generalises: it is true of
village↔village trade and **false** of village↔grid trade. Showing one side alone
argues the study's own conclusion out of existence. The contrast *is* the figure.

- **Question:** Coordination with *whom*? Is the ~0 result a property of Timor, or only of village-to-village pairing?
- **Chart:** Two panels, shared framing, one number each.
  - **(a) Within villages — no diversity.** Pairwise-correlation histogram over all C(780,2) = **303,810** pairs, for peak-normalised load shape and for solar CF, both spiking at +1. Annotate the diversity factor.
  - **(b) Villages vs grid — strong diversity.** The two aggregate profiles overlaid on a representative week (village aggregate, grid `demand_z1`), showing the peaks falling in different hours; annotate correlation and the peak saving.
- **Verified numbers (measured this session — use these):**

  | | within villages | village vs grid |
  |---|---|---|
  | diversity factor | **1.0000000** | **1.475208** |
  | correlation | solar CF min = mean = **1.000000**; load shape mean 0.9969 | **−0.8081** |
  | peaks | Σ peaks = coincident = **128.237931 MW**, only **2** distinct peak hours across 780 villages | village hour **690** (128.24 MW, LF 0.484) vs grid hour **407** (124.10 MW, LF 0.627) |
  | combining the two | no saving — sum equals coincident | 252.34 → **171.05 MW**, a **81.29 MW** peak reduction |

- **Columns:** `data_indonesia/2030/timor/village_demand.csv::demand_village1..780` (1344 rows; per-village max, per-hour sum, per-village argmax); `village_generators_variability.csv` solar columns (positional — drop column 1, profile column *g* belongs to R_ID *g*); `data_indonesia/2030/timor__marketfix/demand.csv::demand_z1` for the grid profile. Note the 516 "distinct" solar profiles are distinct in *amplitude only* — every pairwise correlation is 1.000000, so they share one shape.
- **Earns its slot:** it is the only figure that explains *why* the numbers came out as they did, and it converts a weak empirical null into a precise structural statement with a constructive second half. Panel (a) says village-to-village coordination could not have paid on this data — arithmetic, not economics. Panel (b) says the grid is a genuine counterparty and the market runs are worth the compute. It also pre-empts the sharpest question in the room ("so is coordination worthless?") with "not with each other; possibly with the grid, and here is the test we ran".
- **Must carry:**
  - Panel (a) is a property of how archetype profiles were **synthesised**, not an empirical finding about Timorese villages. 621 of 780 sit on a single demand archetype and GHI spans only 4.908–5.952 kWh/m²/day.
  - 1344 hours from 8 representative weeks cannot express weather-driven decorrelation *even in principle*, so panel (a) is partly a temporal-aggregation artifact. Real spatial decorrelation needs the ERA5 build.
  - Panel (b)'s grid series is **derived**, not measured — `build_grid_demand.py --share 0.42` from the NTT zone-2 series, net of village load. The anti-correlation is inherited from that source and should be labelled as such, not presented as an independent observation about Timor.
  - State peak-normalisation on panel (a)'s axis.

### F12 — The same optimum, two different answers about who traded
- **Question:** Can per-village import/export figures be published from these runs?
- **Chart:** Paired dumbbell, **8 rows** (4 `timor_demo` villages × import/export), one segment per row joining the Gurobi value to the HiGHS value. Segment length is the disagreement.
- **Numbers:** village 4 import 971.6 vs 662.9 MWh (46.6% apart), export **308.7 vs 0.0 MWh**; village 3 is a zero-zero control. `Total_Costs = 26.377413257` on both, identical to 11+ s.f. — print that at axis-label size, boxed, above the panel.
- **Columns:** `results/gridvillage_timor_demo_2030_reference__washgb/site_connection_results.csv::{ID, Connected, Total_Import_MWh, Total_Export_MWh}` and the `__washhi` twin; both `cost_results.csv::Total_Costs`.
- **Earns its slot:** kills the most seductive wrong figure in the study (a per-village trade map) using the study's own numbers, before a reviewer discovers the degeneracy independently.
- **Must carry:** at `import_price = export_price = 0` the trade variables carry zero objective coefficient, so the optimum is a **face** and the allocation is unidentified. Because that is structural, it applies *a fortiori* at 780 sites — no 780-village demonstration is needed or wanted. Label n = 4. Do **not** merge the `arb0`/`arb59` pair into this panel: that is a real price response, a different effect. Frame as "the allocation is arbitrary", never "the model is unreliable" — build columns are fully determined.

### F13 — Demand-model provenance (the figure four findings depend on)
- **Question:** Where does the homogeneity in F2, F6, F9 and F11 actually come from?
- **Chart:** Single panel — archetype counts (rice 621, trade 61, horticulture 46, fishing 7, …), the per-household demand constant (1,241 kWh/hh-yr for 7 of 8 archetypes; fishing 1,607), and the 8 normalised load shapes overlaid.
- **Columns:** `village_solar_potential.csv::{Village, archetype}`; `timor_villages_manifest.csv::{households, annual_kwh}`; `village_demand.csv` for the shapes.
- **Earns its slot:** one upstream fact drives four headline findings and no proposed figure showed it. Publishing it lets the audience discount those findings correctly rather than over-reading them, and it justifies the `timor__diverse` run in the same frame. Cheap to build, high defensive value.

### F14 — Orientation map: where the villages are, and the third that isn't
- **Question:** Which villages can be drawn at all, and what share of demand is invisible?
- **Chart:** Point map in EPSG:32751 (`tools/figlib.py::METRIC`), dot area ∝ households, fill = cost per household on a ramp anchored at **[140, 220]** (not [0, max]); histogram strip in the corner with the $158.48 median marked. Coastline via `figlib.timor_land()` (NTT province polygon, network-fetched and cached), clipped to `figlib.TIMOR_BBOX`.
- **Columns:** `village_solar_potential.csv::{Village, kabupaten, kecamatan, desa, households, lat, lon, sited, hub_name}` — **lowercase `lat`/`lon`**, and null for 153 rows; §0 reconstruction; `village_solar_land.csv::source`.
- **Mandatory on-panel block, not a caption:** "627 of 780 shown. The 153 without coordinates are 19.6% of villages, **31.1% of households**, ~31% of cost — modelled and fully costed, but unlocatable." Show them as a grouped stack of grey squares beside the map (KUPANG 62, TTS 56, TTU 25, BELU 10) so absence is a visible object. `figlib.village_gdf()` does `dropna(subset=["lat","lon"])`, so every previously rendered Timor map already has this hole.
- **Earns its slot:** orientation figure that earns the right to show the rest, and it converts a silent data defect into the study's first honest exhibit.
- **Do not fill kabupaten polygons** — no admin-2 boundary layer ships; the only shipped GeoJSON is province-level. Label kabupaten as text with halos.

---

## 2. Ready when the overnight runs land

### Needs `results/gridvillage_timor_2030_reference__mip1e4/` (currently 0 files)

**F15 — Solver convergence trace.** Incumbent and best bound against wall-clock from the Gurobi log, with the [$0, $166,859] bracket drawn as a horizontal band. The moment the gap narrows below the effect is the moment the study's central question becomes answerable. Costs nothing beyond parsing a log that will exist anyway, and it permanently retires the A1a incumbent by showing where it stopped. *This is the highest-value pending figure.*

**F16 — Coordination footprint, redrawn.** Identity-line scatter, solar MW ON against OFF, log-log, 45° line drawn first. In the current pair, 739 of 780 sit on the line to |Δ| < 1e-6 MW (median 6.1e-11) and 41 break off (−1.1824 to +1.7698 MW). Render the 739 as one dense hairline labelled with the count; the marginal residual histogram on a symlog axis makes the two-population structure unmissable. **Redraw only when mip1e4 lands** — the 41 are where branch-and-bound stopped, and every one of them is expected to move. Prefer this form over a diverging map (see §3).

**F17 — Detectability floor.** Small standalone panel stating the numerical resolution: per-village ON-vs-OFF differences below ~1e-6 MW are not measurable by a run pair of this kind (observed 1e-10 to 1e-11 across 739 villages). This is the cleanest defence against a reviewer who suspects the null is a precision artifact, and it lets readers calibrate every per-village delta figure. Buildable today from the existing pair as a *methods* statement; re-measure on mip1e4.

**F18 — Per-village connection break-even.** Scatter of `Cost_per_yr` against avoided village-layer cost, with a y = x break-even diagonal. **Do not build from the current incumbent** — and note the arithmetic error in the circulating draft: the avoided side is *three* terms, not one. Measured from the two `cost_results.csv`: `Fixed_Costs_Village` −$124,130.62, `Fixed_Costs_Village_Storage` −$219,828.72, `Variable_Costs_Village` −$34,138.84 = **$378,098.18 avoided**, against $754,482 of wire, plus $34,735 of added grid cost, bridging to **exactly −$411,118.45** — the known suboptimality, to the cent. Until mip1e4 lands, only the *aggregate* bridge is defensible, and it is a solver diagnostic, not an economic claim.

### Needs the cost-corrected market solves (`village_timor__marketfix`, `gridvillage_timor__marketfix` — both 0 files)

**F19 — The market dataset before the fix: a ~9× cost error that built zero renewables.** Paired ranked dot plot, log x, candidate headroom against built capacity by technology, with a VOID band. Of 9,113.8 MW of headroom (wind 4,290.3, solar 3,131.8) the grid built **469 MW of battery and zero renewables**, operating 124 MW of coal for 813.2 GWh, `Grid_REShare = 0.0`, `CO2_Emissions_Grid = 766,069 t/yr` against village 12,865 t. ~~The fingerprint — a 511 MW battery serving a 124 MW peak, with `Total_Storage_MWh = 0.0` because `Inv_Cost_per_MWyr = 0` and `Inv_Cost_per_MWhyr = 578,000` — is decisive independent evidence for the defect.~~
  - 🔴 **The battery fingerprint has been re-attributed and must be cut from this figure.** The 511 MW (and the 517 MW on `timor__marketfix`) was **not** caused by the zero power cost. It was a capacity-accounting defect in the loader: `battery_candidate` rows ship `Commit = 2`, and `ED` was built as `Commit == 0`, so the row fell out of both `UC` and `ED` and got **no capacity constraint at all** — `Max_Cap_MW` unapplied, discharge uncapped, and `Inv_Cost_per_MWyr` uncharged because that term sums over `ED_NEW`. Decisive: `timor__marketfix` *did* carry `Inv_Cost_per_MWyr = 49,829` and still reported 517 MW against a 42 MW cap for $0. Pricing the power block could not have fixed it. Fixed on `claude/upbeat-elion-1b2bd2`; `tests/verify_capacity_accounting.jl` pins it. **The `zero renewables` half of F19 stands only once the marketfix legs are re-solved on the fixed model** — a battery with free unbounded power out-competes every renewable candidate, so the renewables-vs-battery comparison is contaminated by the same defect.
  - **Publishable today as a pure retraction/diagnostic** with no coordination-value number attached, *and* with no battery-MW claim. Left panel (the `timor__market` → `timor__marketfix` cost dumbbells: solar 560,000 → 61,694, wind 1,280,000 → 135,781, battery power 0 → 49,829 $/MW-yr, thermal rows unmoved) is input-side and buildable now.
  - **The $18.69 M/yr coordination bound must not appear on any slide until both marketfix legs solve.** Its gridvillage leg never left the root node at a 36.2% achieved gap, and both legs use the defective cost table. Quote the achieved gap, never the permitted `mipgap`.

**F20 — Cost-vintage reconciliation bridge, $64.631 M → $69.134 M.** Short waterfall from the published `docs/coordination_findings_timor.md` baseline to the on-disk run, itemised by input change (village battery power cost $0 → $30,001/MW-yr is the dominant term, ~+$4.50 M/yr). **Buildable today and blocking** — every figure in every lens is exposed to this inconsistency, and a reviewer who has read the doc will open with it. Resolve it before anything ships; until then no deck may mix a doc-sourced ratio with a run-sourced level.

### Input-side only, no solve exists (label as such)

**F21 — Two levers that would change the answer.** `timor` solar-CF pairwise correlation (a delta spike at 1.00000) against `timor__era5` (min pairwise 0.96958, 1st pct 0.97459); load diversity factor 1.000 against `timor__diverse` 1.254. Both datasets exist on disk (gitignored but present); **neither has a result folder**. Ends the deck on "here is the run that would settle it". State explicitly that the sign and magnitude of the output effect are unknown, that 0.97 is still extremely high, and that `timor__marketfix` is described in its own scenario file as "a sensitivity dataset, not a corrected one" — carry that wording verbatim.

---

## 3. Do not build / do not show

| Figure | Verdict | Reason |
|---|---|---|
| **Storage-anomaly map sourced from the gridvillage run** ("seven coastal villages build 5× the storage", 33 h) | **Rebuild, don't drop** | The 33 h is an artifact. Six of the seven fishing villages (IDs 13, 15, 17, 221, 222, 291) are among the 41 connected and their storage *triples* in that incumbent (village 13: 2.4635 → 7.9651 MWh). On the valid run the same quantity is **10.1 h against a 6.72 h baseline (1.51×)**, which the 22%-cheaper battery row (`Inv_Cost_per_MWhyr` 32,104 vs 41,277 on exactly 7 rows) genuinely explains. Rebuild from `village_timor_2030_reference`, drop "five times" and "33 h". Village 279 is the control: fishing, same cheap row, does not connect, identical in both runs. |
| **"The 41 villages that connect are a peri-urban ring" — nearest-neighbour clustering test, p < 0.005** | **Wait for mip1e4** | Runs a formal spatial statistic on a set that exists only because branch-and-bound terminated at `mipgap 0.01`. Attaching a p-value to a suboptimal incumbent's binary vector is the most credibility-damaging move available. It also names the ring as a utility shortlist, and 11 of the 41 cannot be drawn. Published finding elsewhere is 0 of 780. |
| **"Atambua's twelve" — named-village zoom panel with desa names, households, connection costs, micro-bars** | **Drop** | Named, project-grade specificity from the invalid run; exactly what survives being screenshotted and exactly what a counterpart will act on. Structurally broken too: ATAMBUA town is one of the 153 unsited villages, so the catchment's largest load is absent from a panel whose purpose is local credibility. Rebuild post-mip1e4, or rebuild now as a pure input-side panel (households, hub distance, connection cost, archetype) with no model output and no connect/island distinction. |
| **Diverging map of ON-minus-OFF build deltas across the island** | **Wait** | Every non-grey pixel is expected to move on re-solve. The publishable half is the null (739 welded to the diagonal), and F16's identity-line scatter encodes it correctly; a map of 739 grey rings and 41 coloured dots invites reading the 41 as the finding. |
| **Paired 780-village Gurobi/HiGHS trade maps** | **Drop** | The second 780-village solve does not exist, and rendering an arbitrary quantity at full resolution to prove it is arbitrary is the wrong form — one panel will be cropped out. Use F12's 8-row dumbbell. |
| **"Coordination is worth ≥ $18.7 M/yr" bound chart** | **Wait** | Root-node incumbent at 36.2% gap presented as a bound worth 21.7% of system cost, on a contaminated cost table, from an empty results directory. Use F19's retraction framing instead. |
| **Slope/dumbbell chart of OFF vs ON total cost on a truncated axis** | **Replace, permanently** | Wrong form even after a clean re-solve — it renders a point estimate for a quantity that is bounded, not measured. F10's bounds chart is the correct grammar. Its draft also mixed a $64.63 M-vintage ratio with a $69.13 M-vintage level (see F20). |
| **"Islanding is a distance decision" scatter coloured by Connected** | **Recolour** | Geometry is fine and input-side; the colour encoding is the artifact 41, and the figure reads economic meaning into "5 inversions" that are where the solver stopped. Publish with the connect/island colouring removed as a pure screening curve (connection cost per MWh spans $0.87–$722), 153 imputed villages as open glyphs. |
| **Diesel-status-quo vs modelled-optimum paired bar** | **Restructure or drop** | It places a hand-computed counterfactual and a solved optimum on the same axis as two bars of the same kind, and is explicitly designed to survive being screenshotted — the condition under which the "counterfactual, not solved" label is lost. The 134.35 MW legacy fleet is not surveyed: `round(peak_mw × 1.1, 4)` at `tools/ntt/calculators/base.py:122`. If built: outline/hatch the counterfactual bar so the distinction survives cropping, put the label *inside* the bar, state the $18/MMBtu unsubsidised price and show the subsidised-price saving as a second bracket, note that no stranding cost is charged for the 95% of diesel retired, and fix the split — the "$3.57 M diesel" segment actually contains $0.276 M of battery VOM (diesel is $3.297 M + $0.120 M fixed). |
| **Any per-village import/export map, ranking or histogram on `timor`** | **Never** | Zero objective coefficient on the trade variables; the allocation is unidentified. F12 is the figure that says so. |
| **Unserved-energy map, "left behind" figure** | **Never** | `site_nse_results.csv::Total_NSE_MWh` sums to 3.79e-8 MWh on the village run and exactly 0.0 on gridvillage. Nobody is left behind in the model; the honest exclusion figure is F14 (evidence gaps), not energy. |
| **Any heat figure** | **Impossible** | `village_demandheat.csv` sums to exactly 0, so `site_heat_generator_results.csv` has zero data rows in every run. |
| **Any hourly figure — dispatch stack, load-duration curve, SOC trace, hourly heatmap** | **Impossible** | `result_extraction_function.jl:308–321` writes 14 aggregate CSVs and nothing time-resolved. An average-day chart can be built from *inputs* × built capacity (see §5), but no dispatch output exists. |
| **Kabupaten choropleth of anything** | **Impossible/wrong** | No admin-2 boundary layer ships. And area-based encoding inverts the story — TTS is large and rural, Kupang small and dense. Use proportional symbols. |
| **`NSE_Percent_of_Demand`, `generator_results::Percent_MW` on any timor dataset** | **Never** | Denominator is grid demand, which is identically 0. Both are Inf/NaN. |
| **Small multiples by archetype; 780-bar bar charts; dual-axis MW/MWh charts; pie of the 15 cost columns** | **Avoid** | Archetypes differ only in n for 7 of 8 (constant 1,241 kWh/hh-yr). ECDFs beat 780 bars. MW and MWh differ in `sample_weight` annualisation, so a shared axis invites exactly the wrong mental arithmetic. And a pie of `cost_results.csv` is a wrong-by-construction 100% claim — the connection term is not a column in that file (it is `Total_Costs` minus the other 14, = $754,482 on the gridvillage run). |

---

## 4. Recommended 6-figure partner sequence

| # | Figure | Argument it advances |
|---|---|---|
| 1 | **F14** — orientation map + the 153 | "Here is the problem, and here is what we cannot see." Establishes the denominator and plants the coordinate gap honestly, before any result. Earns the right to show the rest. |
| 2 | **F2** — one recipe for 780 villages | "This is a procurement, not a network plan." The single most programme-relevant result: ~2.96× peak in solar, 5.56 h of storage, everywhere. Converts 780 planning problems into a catalogue with a sizing rule. |
| 3 | **F1** — where the money goes | "And the thing to negotiate is the battery, not the panel." Storage is 58.2% of annual cost; 20% off batteries is worth $8.0 M/yr. Also lands the $46 vs $127/MWh reconciliation before a sceptic finds it. |
| 4 | **F5** — the wire costs more than the system | "So spend the capital on villages, not feeders." 295 of 780 villages where the connection alone exceeds their whole local system; wiring all 780 = 59% of the programme cost before a kWh flows. |
| 5 | **F10** — coordination value as a bound | "And here is the measured case for that, stated as what we actually know." [$0, $166,859]/yr, under 0.24% of system cost, with the solver's permitted tolerance drawn four times wider than the answer. A credible zero, plus the reason the re-run matters. |
| 6 | **F11** — two diversity factors | "Villages cannot trade with each other — diversity factor 1.0000000, every village short in the same hour. But they are strongly complementary to the grid: correlation −0.8081, diversity 1.475, an 81 MW peak saving." Converts the null from an empirical accident into a structural statement AND names the counterparty that could still make coordination pay. |

**Hold in the appendix, ready to deploy on challenge:** F7 (balance closure) answers "is the model right"; F4 (land) answers "you ignored land"; F13 (demand provenance) answers "your villages are all the same"; F12 (degeneracy) answers "which villages export"; F6 (equity) answers "will my district pay more"; F3 (diesel) answers the operations question. F9 is the one to volunteer unprompted to a technical reviewer.

---

## 5. Honest ways to show the null and the uncertainty

The study has a null headline and a time-limited incumbent. Five rules and four missing exhibits.

**Rules.**

1. **A null is a bound, never a bar.** Two bars showing $69.134 M and $69.545 M report a *negative* coordination value, which dominance forbids. Report [$0, $166,859]/yr with the left edge anchored by the constructive argument (fixing all 780 `vVIL_CONNECT` to 0 reproduces the OFF solution exactly and is feasible for the ON problem) and the right edge labelled "at most". F10.
2. **Draw the tolerance wider than the effect, deliberately.** The visual disproportion between the ±$690,000 that `mipgap 0.01` permits and the [$0, $166,859] bracket *is* the argument for the re-run. It converts an embarrassing result into the strongest methodological statement available.
3. **Always print the achieved gap, never the permitted `mipgap`** — repo convention, and it is what distinguishes 0.8311% (a real termination) from 36.2% (a root node).
4. **Render a zero as data, not as an absent bar.** "739 of 780 villages welded to the identity line, Σ|Δ annual fixed cost| = $0.012/yr on a $69.1 M system" is a positive, verifiable observation with a magnitude. An empty bar is nothing. F16/F17.
5. **Give the null a mechanism, and a counterparty.** "Coordination didn't pay" is weak and contestable. "Village-to-village coordination could not have paid, because the diversity factor is 1.0000000 and every village is short in the same hour" is a checkable structural claim. Do not stop there: the same arithmetic shows villages ARE complementary to the grid (r = −0.8081, diversity 1.475, 81.29 MW of peak saving), so the null is scoped to one pairing rather than to coordination as such. Presenting only the within-village half argues the study's own remaining question out of existence. F11 → F21.

**Missing exhibits, in priority order.**

- **Caveat-to-figure dependency matrix.** Rows = the six known caveats, columns = the figures actually shipped, cells = clean / caveated / blocked. Highest-value missing artefact in the whole set: it shows at a glance that the input-side figures (F4, F5, F11, F13, F14) are immune to all six while every gridvillage-derived figure fails caveat 2, it makes the review reproducible, and it forces the deck to declare which figures are internal-only.
- **Run-status board.** Dataset × scenario, cell state = solved exact / solved at achieved gap X% / running / not started / void per caveat 4, with the achieved gap printed. Six of nineteen result directories are empty and three lenses independently rediscovered that in prose. This slide prevents the recurring failure where a figure is designed against a run that does not exist, and it is the honest answer to "when will you know".
- **Sensitivity tornado on the headline $69.13 M/yr.** Nothing in 47 proposed figures quantifies how much the answer moves under the assumptions the audience will actually challenge: diesel at $18/MMBtu unsubsidised; battery energy capex (already varying $32,104–$41,277/MWh-yr across shipped rows); 1344 representative hours vs 8760; the archetype demand model; ERA5 vs synthetic solar profiles (the existing sensitivity moves system cost $70.88 M → $73.61 M and diesel 2.9% → 16.9% of load). Its absence is conspicuous — this is the standard expected way to show uncertainty.
- **"Figures we did not draw, and why."** Four decisions — no per-village trade map, no unserved-energy map, no heat figure, no kabupaten choropleth — each with its one-line reason and the measured evidence (3.79e-8 MWh of NSE; zero heat rows; no admin-2 layer; zero objective coefficient on trade). Collectively stronger evidence of rigour than most of the positive figures, and currently these decisions live only in prose that will never reach the partner meeting.

**Two smaller ones worth the effort if time allows.** (a) A band on F6 reflecting the battery-capex range, to show the equity result survives input uncertainty — it should, because the flatness is driven by demand-model homogeneity, not cost precision, and showing that is much stronger than asserting it. (b) A worst-representative-day panel beside any mean-day chart: storage is 58% of system cost and 5.56 h is the most quotable spec number in the deck, so the day that actually sizes storage is load-bearing — and showing it also exposes whether 8 representative weeks can express a multi-day low-resource event at all, which is the honest limit on the whole storage result.