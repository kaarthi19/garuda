# Grid candidate costs: overnight capex is being charged annually

**Status: evidenced, not fixed.** This is a data-provenance question against the
upstream source, not something to patch in place — the values are deliberately
preserved upstream numbers ([`DATA_PROVENANCE.md`](../data_indonesia/DATA_PROVENANCE.md):30:
*"No demand, cost, or network numbers have been altered"*). It affects **all eight
shipped island datasets** and therefore every capacity-expansion result the
platform has produced on them.

Found 2026-08-01 while investigating why the `timor__market` grid built zero
renewables. Discovery path is in [`RUN_LOG.md`](../RUN_LOG.md).

---

## The claim

`generators.csv::Inv_Cost_per_MWyr` is documented as
*"$/MW-yr — Annualised investment cost"* ([`data_indonesia/README.md`](../data_indonesia/README.md):74),
and `build_model!` charges it once per modelled year. In all eight island
datasets the column instead holds what appears to be **overnight capex**, so the
optimiser pays the full capital cost of a renewable plant *every year of its
life*. Renewables are consequently ~9× overpriced and are never built.

## Evidence

### 1. The magnitudes are capex, against three independent published sources

| Column value | Read as $/kW | Published installed capex | Verdict |
|---|---|---|---|
| solar `Inv_Cost_per_MWyr` = 560,000 | **$560/kW** | IRENA 2024 global weighted average **$691/kW** | plausible capex |
| wind `Inv_Cost_per_MWyr` = 1,280,000 | **$1,280/kW** | IRENA 2024 global weighted average **$1,041/kW** | plausible capex |
| battery `Inv_Cost_per_MWhyr` = 578,000 | **$578/kWh** | NREL ATB 2024 4-h BESS **$334/kWh**; market installed range **$150–250/kWh** | high, same order |

As *annual* costs these are not defensible: $560,000/MW-yr is **81 % of a solar
plant's entire installed cost, every year**; wind at $1,280,000/MW-yr is **123 %
annually**.

### 2. The LCOE cross-check

| | implied LCOE | published |
|---|---|---|
| dataset **as the model reads it** | solar **$394/MWh**, wind **$3,346/MWh** | — |
| IRENA 2024 global weighted average | — | solar **$43/MWh**, onshore wind **$34/MWh** |
| garuda's own **village** pipeline | solar **~$46/MWh** | matches IRENA |
| dataset capex **after annualisation** | solar **$42.7/MWh** | within ~1 % of IRENA |

The village layer — which annualises properly through
[`tools/ntt/costs.py`](../tools/ntt/costs.py) — already agrees with the global
benchmark. Applying the same treatment to the grid column reproduces the
benchmark almost exactly. That is the strongest single piece of evidence.

### 3. The internal arithmetic

The village pipeline takes `solar_idr_per_kwp = 8,600,000` Rp/kWp
([`calculators/base.py`](../tools/ntt/calculators/base.py):98, KDKMP partner
workbook), which at `FX_RATE = 16,000` is **$537,500/MW of overnight capex**, and
annualises it to **$59,215/MW-yr**. The grid column holds **$560,000/MW-yr**.

Those are the same quantity, one annualised and one not. Observed ratio
560,000 / 59,215 = **9.46×**; 1 / CRF(10 %, 25 yr) = **9.08×**.

### 4. What it does to results

On `timor__market` (A1b), with 7,422 MW of wind and solar headroom offered:

- **0 MW of wind or solar built.** `Grid_REShare = 0.0`
- Grid served from **124 MW existing coal** at a $12.88/MWh marginal cost
- `CO2_Emissions_Grid` = **766,069 tCO₂/yr**, against a village layer emitting 12,865

Any "coordination value" measured on that dataset is villages substituting
imported coal for their own solar — an artifact of the cost units, not a finding.

## Second, independent defect: grid battery power is free

`battery` candidates carry `Inv_Cost_per_MWyr = 0` with `Inv_Cost_per_MWhyr`
priced, in all eight island datasets. This is precisely the defect
[`DATA_PROVENANCE.md`](../data_indonesia/DATA_PROVENANCE.md):46 records diagnosing
and fixing for the **village** layer (`0 → 30001 $/MW-yr`) — *"battery power was
free while battery energy was priced, so the optimiser bought unlimited
charge/discharge MW against a priced MWh build"*. The fix was never applied to the
grid layer.

It produces a physically meaningless device. In the A1b `village` solve the grid
battery came out at **511 MW of power and 0.0 MWh of energy**
(`storage_results.csv::Total_Storage_MWh = 0.0`): free power, priced energy, so
buy unlimited power and no storage.

## Third issue, unrelated to cost: the wind capacity factor

Wind candidates in `timor__market` have a mean capacity factor of **0.045**.
Real onshore wind runs 0.25–0.45, and IRENA's $34/MWh LCOE implies 0.30+. Even
correctly annualised, wind stays uneconomic in this dataset for this separate
reason. Not investigated further here.

## Suspected, not confirmed: `Max_Cap_MW` on storage rows

The A1b `village` solve reports the battery building **469 MW of new capacity
against `Max_Cap_MW = 42.0`**. [`optimizer.jl`](../functions/optimizer.jl):49–50
does `set_upper_bound(vNEW_CAP_ED[g], Max_Cap_MW[g])` for `ED_NEW` rows with a
positive cap, so either storage power is carried by a variable that escapes that
bound, or the extractor reports something other than power MW for `STOR` rows.
Needs a focused check before any capacity figure from a storage row is trusted.

---

## Re-derivation, for the sensitivity variants only

Two derived datasets exist for testing the hypothesis —
`data_indonesia/2030/timor__marketfix` (costs only) and `timor__marketfixnf`
(costs plus the 24 candidate fossil rows zeroed). Both are gitignored and
schema-valid. **They are sensitivity cases, not corrections**: they encode an
inference about the upstream units.

| item | capex used | life | source of life | CRF @10 % | annualised |
|---|---|---|---|---|---|
| solar | $560,000/MW (dataset) | 25 yr | `costs.py::LIFETIME_YEARS` | 0.11017 | **$61,694/MW-yr** |
| wind | $1,280,000/MW (dataset) | 30 yr | NREL ATB asset life | 0.10608 | **$135,781/MW-yr** |
| battery power | **$379,000/MW (NREL ATB)** | 15 yr | NREL ATB Li-ion | 0.13147 | **$49,829/MW-yr** |
| battery energy | $578,000/MWh (dataset) | 15 yr | NREL ATB Li-ion | 0.13147 | **$75,992/MWh-yr** |

Discount rate 10 % real from `costs.py::DISCOUNT_RATE`. Where the dataset carries
a capex it is kept and only annualised — the study's own cost view is preserved
and only the units are changed. Battery **power** is the one exception: the
dataset has no value to annualise, so NREL ATB's $379/kW power component is
brought in.

**Caveats that keep these out of any headline.**

- Battery life 15 yr (NREL) conflicts with `costs.py`'s **12 yr**, so grid and
  village batteries would be annualised on different lifetimes.
- The 10 % real discount rate is garuda's village-pipeline assumption, not a
  published grid-planning WACC (NREL ATB uses ~7.1 % after-tax).
- `costs.py` is the **NTT distributed** pipeline. Borrowing its rate and lifetimes
  for utility plant across an island grid is a transfer that nobody has sanctioned.
- The capex reading is an inference. No source document states the upstream intent.

## What should happen

1. **Confirm the units against the upstream source** — the Power-Lab / 100 GW-study
   snapshot `42c222f` and `data-indonesia-2025`. That decides whether this is a
   mislabelled column, a lost conversion step, or intended behaviour.
2. **Fix grid battery power regardless.** Free power against priced energy is
   indefensible on any reading of the other columns, and it is already documented
   as a defect for the village layer.
   > **Necessary but not sufficient — the price was never the binding problem.**
   > Setting `Inv_Cost_per_MWyr = 49,829` in `timor__marketfix` changed nothing:
   > that term is summed over `ED_NEW`, and the `battery_candidate` rows ship
   > `Commit = 2` while the loader built `ED` as `Commit == 0`, so they were in
   > neither `UC` nor `ED`. The rows carried **no capacity constraint of any
   > kind** — `Max_Cap_MW` unapplied, `vGEN` uncapped by `cMaxPowerED`, and the
   > power block charged $0 no matter what the CSV said. `timor__marketfix` still
   > reported a 517 MW battery against its own 42 MW `Max_Cap_MW`. The loader is
   > fixed on `claude/upbeat-elion-1b2bd2` (`ED` = complement of `UC`), pinned by
   > `tests/verify_capacity_accounting.jl`. **The marketfix variants must be
   > re-solved on the fixed model before their costs tell you anything** — until
   > then they measure a free battery, not a repriced one.
3. **Treat every published capacity-expansion result on the eight island datasets
   as provisional** until (1) is resolved. Dispatch-only results are unaffected —
   investment costs do not enter a fixed-capacity solve.
4. Re-run A1b only after (1). Numbers from the variants above would carry an
   unsourced assumption into a headline.

## Sources

- [IRENA, *Renewable Power Generation Costs in 2024* (summary)](https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2025/Jul/IRENA_TEC_RPGC_in_2024_Summary_2025.pdf)
- [pv magazine — global average solar LCOE $0.043/kWh in 2024](https://www.pv-magazine.com/2025/07/23/global-average-solar-lcoe-stood-at-0-043-kwh-in-2024-says-irena/)
- [NREL, *Cost Projections for Utility-Scale Battery Storage: 2025 Update*](https://docs.nrel.gov/docs/fy25osti/93281.pdf)
- [NREL ATB 2024 — Utility-Scale Battery Storage](https://atb.nrel.gov/electricity/2024b/utility-scale_battery_storage)
