# Handoff brief — Timor solar runs on HPC

*Copy this whole file to the HPC agent. It is self-contained: everything below is
either in the repo or stated here. Local note, not tracked in git.*

---

## What you are running

`garuda` — a Julia/JuMP capacity-expansion and dispatch model of Indonesia's power
system, resolved to individual villages. The question is whether Timor's 780
villages are better off interconnected or as standalone solar+storage+diesel
microgrids, and whether they could profitably supply the grid.

- Repo: `https://github.com/kaarthi19/garuda`, branch `main`
- The authoritative run list is **`docs/run_plan_timor.md`** in the repo. Follow it
  in order — groups A → B → C → D. Do not skip group A.
- Before designing anything not in that plan, read **`docs/scenario_design_timor.md`**,
  which lists eight scenario families that are **void** — the model cannot express
  the effect, so they return a confident-looking null.

## Setup

```bash
git clone https://github.com/kaarthi19/garuda && cd garuda
pip install pandas numpy click pyyaml pytest
julia --project=. -e 'using Pkg; Pkg.instantiate()'   # ON A LOGIN NODE, once
python -m pytest tests -q                              # expect 95 passed
```

Then confirm the model itself is intact before spending cluster time:

```bash
julia --project=. tests/verify_data_core.jl            # DATA_CORE_OK
tools/regression_gate.sh check                         # 71 metrics unchanged
```

`regression_gate.sh check` takes ~6 min and solves three real cases. If it does
not print `REGRESSION_GATE_OK`, stop and report — something in the environment
differs from the reference.

## Solver

**Gurobi is effectively mandatory at 780 villages.** Measured: HiGHS ran the
780-village model for **6.5 hours without converging**; Gurobi does a scenario in
~30 min. Set in every config:

```json
{"solver": "gurobi", "relax_uc": false, "lp_method": 2, "mipgap": 0.01}
```

`lp_method: 2` selects barrier. On this model Gurobi's automatic choice spends the
root solve in concurrent mode and itself reports ~535 s per solve as avoidable.

`GRB_LICENSE_FILE` (or your site's equivalent) must be visible **on the compute
node**, not just the login node.

## Submitting

There is **no submit script in the repo** — `generate_jobs.py` defaults to
`submit_test.sb`, which does not exist. Write one for your cluster; it needs to
load Julia + Gurobi, `cd` into the job directory, and run:

```bash
julia --project=<repo> <repo>/run_model.jl --config config.json
```

Then:

```bash
python generate_jobs.py --scenarios-file scenario_timor.yml \
    --submit-script <yours>.sb --output-root jobs --submit
```

**Walltime**, from measurements (memory was never profiled — run one job and read
the actual high-water mark before sizing an array):

| Workload | Solver | Observed |
|---|---|---|
| 780-village expansion MILP | Gurobi `lp_method 2` | ~30 min/scenario |
| 780-village dispatch LP | HiGHS | >6.5 h, no convergence — **do not** |
| 81-village dispatch LP | HiGHS | ~4.5 min |
| grid-only market dispatch | HiGHS | 2.8 s |

**Sweeps are serial.** `tools/sensitivity.py` solves each point in-process, one
after another — a 5-point ladder at ~30 min/point is one **~2.5 h job**, not five
parallel ones. Either size the walltime for the whole ladder or split the points
into separate `run_tag`ed jobs.

## Five things that will silently produce a wrong answer

These are not hypothetical; each one has already happened in this codebase.

1. **A scenario-YAML key outside `PASSTHROUGH_KEYS` is silently dropped.** The
   job's `config.json` never carries it, the model solves at its default, and the
   result CSVs look completely normal. If you add a key to a YAML, check it
   appears in `PASSTHROUGH_KEYS` in `generate_jobs.py`.
2. **Runs differing only by config keys overwrite each other.** They share one
   results folder unless you set `run_tag`. An eight-point ladder becomes one run
   reported eight times. `sensitivity.py` sets it for you; hand-written configs do
   not.
3. **Sweep axes are multipliers on the base value.** `--param export_price=2` with
   a base of 0 gives 0. Always pass a non-zero base (`--export-price 40`). The
   harness now refuses a zero base rather than reporting a flat fake.
4. **Nothing on plain `timor` can answer an export question.** `demand_z1 = 0` for
   all 1344 hours, so the balance forces `Σ export ≤ Σ import` every hour. Build
   `timor__market` first (one command, in the run plan). A result from plain
   `timor` with `export_price > 0` is a data artifact.
5. **Report the achieved MIP gap, not `mipgap`.** A 1 % tolerance permits a ~$646k
   gap on this model; citing the tolerance proves nothing about the run you did.
   Grep the solver log for the achieved gap and record it with every result.
   Treat cost differences below **~$100** as numerical noise.

## What to report back per run

- `Total_Costs` from `cost_results.csv` (annual, $M)
- `Connected` count from `site_connection_results.csv`
- **the achieved MIP gap** from the solver log
- wall time and peak memory
- for export runs: `Village_Export_Revenue`, `Total_Export_MWh`
- for `clean` runs: `CO2_Emissions_Village`, and which `policy_scope` was used

All energy columns in the result CSVs are **annual** — the extractor applies the
representative-period sample weights. Do not multiply by 8760/1344; that was
required before a recent fix and now double-counts.

## Highest-priority run

**Group A1** in the run plan — now **four** jobs, ~30 min each, not two:

- **A1a** — `village` and `gridvillage` on `timor` at full interconnection cost.
- **A1b** — the same pair on `timor__market`, which has real grid load. Build it
  first: `python -m tools.ntt.build_grid_demand --share 0.42 --out-dataset
  timor__market --fleet rescale` (seconds, gitignored).

Both, by default. A1a re-measures the one published claim that current data could
overturn — "0 of 780 villages connect", measured on older connection costs and on
*free* battery power; both changed, and both push toward connecting.

A1a alone is not enough to publish. On plain `timor`, `demand_z1 = 0` for all
1344 hours and the grid zone is a single 122 MW diesel serving nobody, so a
village has nothing to sell — the largest economic reason to connect is not
representable, and the connection decision is biased against connecting by
construction. A1b restores a buyer. Report the pair; A1a understates connection
value and A1b overstates cheap supply, so together they bracket it.

## Known blocked

Anything on `timor_era5` — the ~87 MB ERA5 capacity-factor file is not in the repo
(gitignored, regenerable with a CDS account). The wiring tool is committed and
tested; it just needs the data. This blocks the real-weather × market run, which
was the highest-value run in the original design.
