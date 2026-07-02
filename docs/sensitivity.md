# Sensitivity sweeps

`tools/sensitivity.py` answers the question every reviewer asks after seeing a
plan: **how robust is it to the inputs you are least sure about?** It perturbs
the uncertain parameters around a base case, solves each variant through the
normal pipeline, and reports how the headline numbers move.

```bash
# fuel price +30%, demand +10%, solar CF −15% — one-at-a-time (base + 3 runs):
python tools/sensitivity.py run --island timor_demo --year 2030 \
    --scenario gridvillage --param fuel=1.3 --param demand=1.1 --param solar_cf=0.85

# ranges instead of single points, every combination (--full-grid):
python tools/sensitivity.py run --island timor_demo --year 2030 --scenario gridvillage \
    --param fuel=0.8,1.2 --param demand=0.9,1.1 --full-grid
```

## Axes

All perturbations are **multipliers on the base value**.

| Axis | What it scales | How |
|---|---|---|
| `fuel` | `fuels_data.csv::Cost_per_MMBtu`, every fuel (the `None` fuel stays 0) | dataset variant |
| `demand` | every zonal `demand_z*` and site `demand_*` electricity column (heat untouched) | dataset variant |
| `solar_cf` | every solar resource's availability column, grid and site layers, clipped to [0, 1] | dataset variant |
| `import_price` | the `import_price` config value | config only |
| `export_price` | the `export_price` config value | config only |

**Dataset variants are honest datasets.** Each one is a full copy of the base
folder at `data_indonesia/<year>/<island>__<tag>/` (e.g. `timor_demo__fuel1.3`)
with only the relevant columns scaled — it passes `validate_schema.py` (the
harness checks before solving), any tool can inspect it, and every variant
result is a first-class run under
`results/<scenario>_<island>__<tag>_<year>_<clean>/` (reportable with
`tools/report.py`, comparable with `tools/coordination_value.py`). Variants are
derived artifacts and gitignored (`data_indonesia/*/*__*/`); delete them freely
and re-run to regenerate.

## Plan shapes

- **One-at-a-time** (default): base + one run per non-1.0 multiplier — isolates
  each axis's effect. `--param fuel=0.8,1.2 --param demand=1.1` → 4 runs.
- **`--full-grid`**: the cartesian product, with 1.0 implicitly added to every
  axis so partial combinations are covered. The same params → 6 runs. Counts
  grow fast; the run list is printed before solving.

Runs default to the licence-free path (LP-relaxed expansion on HiGHS, same as
the demo walkthrough); `--exact-uc` / `--solver gurobi` for the MILP.
`--engine dispatch` sweeps operations-only. `--keep-going` drops a failed run
from the summary instead of aborting the sweep.

## Output

`results/sensitivity_<scenario>_<island>_<year>_<clean>/`:

- **`sensitivity_results.csv`** — one row per run: the multipliers applied and
  the headline metrics (total cost, CO₂, both RE shares, grid/village unserved
  energy, villages connected, village solar built).
- **`sensitivity_results.md`** — the full table plus, per metric, the base
  value, the min–max range across the sweep, and which run moved it furthest —
  a text tornado. Metrics are annualised the same way as
  `tools/coordination_value.py` (whose loader it reuses).

## Reading it honestly

A sweep quantifies *parametric* sensitivity around one scenario — it is not a
probability distribution over futures, and multipliers inherit every structural
assumption of the base case (single year, representative periods, the
[documented limitations](../MODEL.md)). Its policy value is the simple kind:
"the plan's cost moves ±X % when fuel moves ±20 %, and the connect-vs-island
decisions do / do not flip" — stated with the runs attached so anyone can check.
