# Timor run plan — what to submit, in what order, and what proves it worked

The companion to [`scenario_design_timor.md`](scenario_design_timor.md), which says
what is *worth* running and what is **void**. This page says what to actually
submit, with the exact config for each run and the number that decides whether it
succeeded. Runs are grouped A–D by dependency; **do not skip group A**.

Every run below is a `config.json` for `run_model.jl`, produced either by a
scenario YAML through `generate_jobs.py` (discrete runs) or by
`tools/sensitivity.py` (ladders and grids). See
[Submitting on HPC](#submitting-on-hpc) at the end.

**Two standing rules, from `scenario_design_timor.md`:**
report the **achieved** MIP gap, never the permitted `mipgap`; and treat
differences below **~$100** on a $64 M system as numerical noise.

---

## Group A — acceptance and controls (run first, they are cheap)

Nothing in B–D is interpretable until these pass.

### A0 — port acceptance *(optional, historical)*

Reproduces the pre-port reference number, confirming the model is the same one
that produced the published EXP-001..005 results.

**This must be run at commit `f3d054b^`, not on `main`.** `f3d054b` priced village
battery power (`Inv_Cost_per_MWyr` 0 → 30001), which deliberately moves every
Timor number. On current `main` this run will **not** reproduce 64.63141317, and
that is correct behaviour, not a failure.

| | |
|---|---|
| scenario / island | `village` / `timor`, 2030, `reference` |
| config | `solver: gurobi`, `relax_uc: false`, `lp_method: 2`, `mipgap: 0.01` |
| **pass** | `Total_Costs` = **64.63141317** |
| fail | anything else — stop and find out why before trusting later runs |

### A1 — the new reference pair *(the headline re-measurement)*

The one published claim that current data could overturn. "0 of 780 connect at
full interconnection cost" was measured on the old connection costs **and** on
free battery power. Both changed, and **both push toward connecting**:
interconnection is now roughly half as expensive, and islanding is more expensive
because battery power costs money.

| | |
|---|---|
| scenarios | `village` **and** `gridvillage` / `timor`, 2030, `reference` |
| file | `scenario_timor.yml` (already carries the OFF/ON pair) |
| config | `solver: gurobi`, `relax_uc: false`, `lp_method: 2`, `mipgap: 0.01` |
| runs | 2 |
| **record** | `Total_Costs` for both; `Connected` count in `site_connection_results.csv`; the achieved gap from the solver log |
| coordination value | `Total_Costs(village) − Total_Costs(gridvillage)` — or run `tools/coordination_value.py compare` on the two folders |

These two numbers become the numbers of record. Everything downstream is quoted
against them.

### A2 — negative control *(run this every time, not once)*

A run that must produce exactly zero. It is the only reliable way to catch a sign
error or a fabricated trade before it reaches a headline.

| | |
|---|---|
| scenario / island | `gridvillage` / `timor`, 2030, `reference` |
| config | as A1, plus `export_price: 0` (the default) |
| **pass** | `Village_Export_Revenue` = **exactly 0** in `cost_results.csv` |
| also | export = import to 4 d.p. across `site_connection_results.csv` — the signature of a zero-grid-demand dataset |

A1's `gridvillage` run satisfies A2; you do not need a separate submission unless
you change the export machinery.

### A3 — the ceiling *(cheapest possible bound on the whole question)*

Make interconnection free. Whatever the coordinated plan saves when the wire costs
nothing, it can never save more at any positive cost, because cost is monotone.
If this is negligible, no later run will find value beneath it.

```bash
python tools/sensitivity.py run --island timor --year 2030 --scenario gridvillage \
    --solver gurobi --exact-uc --param connection_cost=0
```

| | |
|---|---|
| runs | 2 (base + the free-connection variant), serial in one job |
| **record** | the delta against the base — the previous measurement was **$2,569/yr on a $64.6 M system (0.004 %)** |
| interpretation | this is an upper bound, not an estimate |

### A4 — measure village emissions *(prerequisite for group D)*

The shipped `co2_limits` of 3,000,000 t is roughly **40× slack** against actual
village emissions, so a cap set from it cannot bind (N4). Until `f3d054b`'s
sibling fix landed, `CO2_Emissions_Village` also reported a hard **0**, so this
number could not be measured at all. It can now.

| | |
|---|---|
| source | `clean_energy_results.csv::CO2_Emissions_Village` from A1's `village` run |
| **use it** | set `island_params` / `co2_limits` in the scenario YAML from this, not from the placeholder |
| sanity | on `timor_belu` (81 villages) the measured figure is 54,067 tCO₂/yr |

### A5 — import-price sweep *(may move the headline; run it before publishing one)*

`import_price` is the $/MWh a site pays for an imported MWh. **The shipped Timor
scenario files now set it to 0, deliberately**, and this run measures what that
choice is worth.

The objective already contains `eVariableCostsGrid` — the fuel and O&M the grid
burns to generate whatever a site imports, because the zonal balance forces it to.
`import_price` adds `eGridImportCosts` **on top**, so a non-zero value charges the
same MWh twice: at Timor's diesel margin that is ~$197/MWh of real resource cost
plus the tariff, ~$256/MWh in total. A tariff is a **transfer**, not a resource
cost; it belongs in a merchant framing, and the agreed deliverable is
system-optimal.

The old default of 59.0 is also an *industrial* tariff. PLN household rates are
roughly **$26/MWh** on the subsidised lifeline and **~$90/MWh** non-subsidised —
59 is neither.

**Why this may change the answer.** With a non-zero import price and no offsetting
export credit, every inter-village transfer carried a one-sided deadweight charge.
That is one of the two candidate explanations for the measured "coordination value
is ~0" — the other being solar synchrony plus cheap storage — and no run has
separated them. If coordination value rises materially at `import_price = 0`, the
published null was partly an artifact of the tariff rather than a fact about
Timor.

```bash
# 0, $29.5, $59, $88.5 — the axis is a multiplier, so pass a non-zero base
python tools/sensitivity.py run --island timor --year 2030 --scenario gridvillage \
    --solver gurobi --exact-uc \
    --import-price 59 --param import_price=0,0.5,1,1.5
```

| | |
|---|---|
| runs | 5 (base + 4), serial in one job |
| **record** | coordination value at each point, and `Total_Import_MWh` summed over sites |
| **the comparison that matters** | the value at multiplier 0 against multiplier 1. A large gap means the tariff, not the physics, was suppressing coordination |
| pair with | A3 (free connection) — both at once is the true ceiling |
| note | the model's default is still 59.0; only the Timor scenario files set 0. Nothing outside this case changes |

---

## Group B — coordination on current data

### B1 — load-shape diversity counterfactual

Tests whether "coordination is worth ~0" follows from the villages being
load-shape clones. Half of them are moved to a midday peak, energy-preserving per
representative period, so only *when* the load falls changes.

```bash
python -m tools.ntt.make_diverse_demand --dataset data_indonesia/2030/timor
# -> data_indonesia/2030/timor__diverse
```

Then A1's pair again with `islands: [timor__diverse]`.

| | |
|---|---|
| runs | 2 (+ the dataset build, seconds) |
| **compare against** | A1. The previous measurement found trade *fell* with diversity (2.5 MWh vs 7.75 MWh), which is hard to explain by solar synchrony alone |
| note | `timor__diverse` is a derived dataset and gitignored; regenerate rather than copy |

---

## Group C — the export / market question

**Prerequisite for every run in this group.** Build the market dataset first; it
takes seconds and is gitignored, so build it on the cluster:

```bash
python -m tools.ntt.build_grid_demand --share 0.42 \
    --out-dataset timor__market --fleet rescale
```

Expect: 682 GWh/yr of grid demand, 124 MW peak, schema valid.
**A run on plain `timor` cannot answer any export question** — with `demand_z1 = 0`
the balance forces `Σ export ≤ Σ import` in every hour (N1).

> **Known limitation, flagged before you read any result.** The transplanted
> candidate set carries NTT-*wide* renewable potential scaled by the share:
> ~4,290 MW of wind and ~3,132 MW of solar against a 124 MW peak. Most is never
> built, but it *sets the marginal price*, which is exactly what an export study
> reads. Consider `--drop-tech wind`, and report which variant you used.

### C1 — buyer, no price

Does a grid load *alone* change the village plan, with no tariff at all? Under a
central-planner objective an exported MWh is already valued at zonal marginal cost
once the bus has load, so this is the honest system-value question.

| | |
|---|---|
| scenarios | `village` and `gridvillage` / `timor__market` |
| file | `scenario_timor_market.yml` (already carries the pair) |
| config | `solver: gurobi`, `relax_uc: false`, `lp_method: 2`, `export_price: 0` |
| runs | 2 |
| **sanity gate** | grid `Total_NSE_MWh` ≈ 0. If not, the fleet is wrong and every later number is scarcity-priced at ~$2,000/MWh. (A grid-only dispatch of this dataset has already been verified at NSE = 0.000000.) |
| **compare against** | A1 — the delta is the effect of giving the grid a load |

### C2 — export-price ladder on the market dataset

The supply curve. **The axis is a multiplier on the base**, so pass a non-zero
`--export-price` or every point is 0; the harness refuses a zero base rather than
reporting a flat fake.

```bash
python tools/sensitivity.py run --island timor__market --year 2030 \
    --scenario gridvillage --solver gurobi --exact-uc \
    --export-price 40 --param export_price=0.5,1,1.5,2
# -> $20, $40, $60, $80 /MWh
```

| | |
|---|---|
| runs | 5 (base + 4), **serial in one process** — size the walltime accordingly |
| **record** | `Village_Export_Revenue`, `Total_Export_MWh`, `Connected` count, `site_solar_built_mw` per point |
| caution | points above `import_price` (59) trigger the arbitrage warning; see C3 |

### C3 — the same ladder on plain `timor` **(mandatory, not optional)**

Raising `export_price` does two things at once: it creates a buyer *and* it
removes the one-sided $59/MWh charge on inter-village transfers. **C2 − C3
separates them.** Without C3, any effect found in C2 cannot be attributed.

```bash
python tools/sensitivity.py run --island timor --year 2030 \
    --scenario gridvillage --solver gurobi --exact-uc \
    --export-price 40 --param export_price=0.5,1,1.5
# -> $20, $40, $60  ... but see the cap below
```

> **Keep every point ≤ 59 $/MWh here, or set `export_backed_by_generation: true`.**
> On a zero-grid-demand dataset, `export_price > import_price` lets two villages
> transact at a profit while generating nothing. The model **refuses to solve**
> that configuration — an error, by design, not a crash. The $60 point above will
> therefore fail unless you enable the backing constraint.

### C4 — interconnection cap sweep

Interconnection is sized at 1.5 × each village's **own** peak, leaving a mean of
~0.07 MW of export headroom. A village cannot sell much however much solar it
builds, so an export result at the shipped cap measures a *sizing assumption*
rather than economics.

```bash
python tools/sensitivity.py run --island timor__market --year 2030 \
    --scenario gridvillage --solver gurobi --exact-uc \
    --export-price 40 --param connect_cap=3.33,13.33
# -> effective 5x and 20x own peak
```

| | |
|---|---|
| runs | 3, each on its own dataset variant |
| **caveat to report** | `Cost_per_yr` depends only on distance, not MW, so scaling the cap alone buys capacity for free. Pair with C5 before reading it as a business case |

### C5 — who clears: connection cost × export price

```bash
python tools/sensitivity.py run --island timor__market --year 2030 \
    --scenario gridvillage --solver gurobi --exact-uc \
    --export-price 40 --param connection_cost=0,0.5,1 --param export_price=1,2 \
    --full-grid
```

| | |
|---|---|
| runs | up to 9 | 
| **record** | per-village `Connected` — expect "only the near-grid ones"; join to `village_solar_potential.csv::hubdist_km` to get the distance cutoff |

### C6 — merchant storage

```bash
python tools/sensitivity.py run --island timor__market --year 2030 \
    --scenario gridvillage --solver gurobi --exact-uc \
    --export-price 40 --battery-duration-h 4 \
    --param battery_duration_h=0.5,1,1.5 --param export_price=1,2 --full-grid
# -> 2 h / 4 h / 6 h  x  $40 / $80
```

Keep `export_price ≤ import_price` or `run_model.jl`'s arbitrage warning is
describing your result rather than warning about it.

---

## Group D — policy scope

### D1 — does counting village RE toward the cap create grid-side demand?

**Blocked until A4.** Set `co2_limits` from measured emissions first, or the cap
is ~40× slack and the run reports "the constraint costs nothing" as an artifact.

| | |
|---|---|
| scenario / island | `gridvillage` / `timor__market`, `clean` |
| config | `policy_scope: "system"`, `co2_limits` from A4, `RE_limit` as required |
| control | the same run at `policy_scope: "grid"` |
| **note** | a `clean` run at `"grid"` scope on plain `timor` now **errors by design** — the grid RE share is renewable generation over *zero* grid demand, which is undefined (N3) |

---

## Blocked — do not schedule

| Run | Blocked on |
|---|---|
| Anything on `timor_era5` (incl. the real-weather × market run, the highest-value run in the original plan) | the ~87 MB ERA5 capacity-factor file, which is gitignored and not in the repo. `tools/ntt/wire_era5_solar.py` is committed and tested; it needs `solar_era5/village_solar_cf_hourly.csv` plus a village points file to build the dataset |
| The simultaneous-stressor gate (`battery_duration_h=4` **and** free connection **and** ERA5) | same |
| Spatial-correlation dose sweep | no tooling built for it |

---

## Submitting on HPC

### Resource expectations

Measured on this work, not guessed. **Memory was never profiled** — run one job
first and read the actual high-water mark before sizing an array.

| Workload | Solver | Observed |
|---|---|---|
| 780-village expansion MILP | Gurobi, `lp_method: 2` | ~30 min/scenario (~37 min at `lp_method: -1`) |
| 780-village dispatch LP | HiGHS | **>6.5 h without converging — do not** |
| 81-village dispatch LP | HiGHS | ~4.5 min |
| 81-village dispatch + `export_backed_by_generation` | HiGHS | **>34 min without converging** |
| grid-only market dispatch (84 units) | HiGHS | 2.8 s |

**Gurobi is effectively mandatory at 780 villages.** Set `lp_method: 2`; on this
model Gurobi's automatic choice spends its root solve in concurrent mode and
reports ~535 s per solve as avoidable.

**Sweeps are serial.** `tools/sensitivity.py` solves each point in-process, one
after another. A 5-point ladder at ~30 min/point is a **~2.5 h single job**, not
five parallel ones. Either size the walltime for the whole ladder, or split the
points into separate `run_tag`ed jobs and combine afterwards.

### Discrete runs

```bash
python generate_jobs.py \
    --scenarios-file scenario_timor.yml \
    --submit-script <your-submit-script>.sb \
    --output-root jobs --submit
```

This writes one `jobs/<name>/config.json` per island × year × scenario × clean,
symlinks the submit script into each, and `sbatch`es it.

**The repo ships no submit script.** `generate_jobs.py` defaults to
`submit_test.sb`, which does not exist, so `--submit-script` must point at one you
provide. It needs to: load Julia (and Gurobi), `cd` into the job directory, and run

```bash
julia --project=<repo> <repo>/run_model.jl --config config.json
```

with a walltime from the table above and `GRB_LICENSE_FILE` (or your site's
equivalent) visible to the compute node. Instantiate the Julia project **once on a
login node** (`julia --project=. -e 'using Pkg; Pkg.instantiate()'`) before
submitting an array — concurrent first-time instantiation from many jobs races on
the shared depot.

### Two things that will bite

1. **Every optional key must be in `PASSTHROUGH_KEYS`.** A scenario YAML key
   outside that list is silently dropped: the job's `config.json` never carries
   it, the model solves at its default, and the result CSVs look entirely normal.
   A test enforces this for the shipped YAMLs; it cannot cover one you write on
   the cluster.
2. **Use `run_tag` for anything that differs only by config.** Without it, runs
   that share an island/year/scenario/clean write to the *same* results folder and
   overwrite each other — an eight-point ladder becomes one run reported eight
   times. `sensitivity.py` sets it automatically; hand-written configs do not.

### After a change to shared code

```bash
tools/regression_gate.sh check
```

71 metrics across three cases must come back unchanged. If they moved
legitimately, re-capture the baseline **in the same commit, with the reason** —
never to turn a red gate green.
