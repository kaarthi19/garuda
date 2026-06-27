# Experience layer (Phase 5)

A thin, non-expert on-ramp over the data core and engines — kept deliberately
small (no web app). Two tools: a **guided launcher** and an **auto-report
generator**. Both run on Python + pandas (the report also needs matplotlib /
jinja2); neither wires straight to the optimizer.

## Launcher — `tools/launcher.py`

Validate, preview, and scaffold a single run.

```bash
# validate + preview only (no run)
python tools/launcher.py --island maluku --year 2030 --scenario base --clean reference --engine dispatch

# scaffold a config and launch the fast LP dispatch on HiGHS
python tools/launcher.py --island maluku --year 2030 --scenario base \
    --clean reference --engine dispatch --run
```

Three steps:

1. **Schema validation** — reuses `tools/validate_schema.py::validate_dataset`,
   so the same checks that gate `preflight.jl` run up front. Errors abort (pass
   `--force` to proceed anyway); warnings are shown.
2. **Scenario preview** — zones, generators (UC / VRE / storage counts),
   transmission lines, the representative-period structure (`P × H = T` hourly
   steps), an order-of-magnitude primal-variable count, and a **runtime estimate**
   anchored on measured timings (LP-relaxed dispatch is seconds–minutes on HiGHS;
   the UC-MILP capacity expansion is fast on Gurobi but hard for HiGHS at scale).
3. **Config** — writes a `config.json` with the right keys for `run_model.jl`
   (including `engine`, `relax_uc`, `solver`). With `--run`, it shells out to
   `julia --project=. run_model.jl --config …` exactly as a human would.

Key flags: `--engine {expansion,dispatch}`, `--solver {highs,gurobi}`,
`--exact-uc` (keep the UC MILP in dispatch), `--co2-limit` / `--bau` (clean runs),
`--force`, `--run`.

## Auto-report — `tools/report.py`

Turn a finished scenario's result CSVs into one shareable **HTML** file and a
**PDF**.

```bash
python tools/report.py results/base_maluku_2030_reference            # writes report.html + report.pdf
python tools/report.py results/gridvillage_timor_demo_2030_reference --open
```

It reads whatever result CSVs are present (`cost_results`,
`clean_energy_results`, `generator_results`, `reliability_results`, …) and
renders:

- **Headline metrics** — total system cost (M$), CO₂ (ktCO₂), grid RE share,
  annual demand, energy served, and (for dispatch runs) unserved energy and its
  share of demand.
- **Charts** — generation mix and installed capacity by technology, a cost
  breakdown, and (multi-zone dispatch) per-zone reliability shortfall.
- **Tables** — per-zone reliability and a capacity/generation summary by
  technology.

### A units subtlety it gets right

The source result CSVs mix **annualised** quantities (cost, CO₂, RE share,
`reliability_results`) with **representative-period sums** (`generator_results.GWh`,
`nse_results`). Because `Sub_Weights` are **not uniform** across periods, a summed
generation column can't be annualised after the fact. So the report:

- anchors annual demand / served / unserved-share on the **input** `demand.csv`
  (auto-located at `data_indonesia/<year>/<island>`, or `--input-folder`), which
  carries the weights and yields the exact yearly demand;
- takes annual unserved energy from the sample-weighted `reliability_results`;
- labels the generation-mix chart as a **representative-period** sum (not
  annualised), to avoid implying a yearly figure it cannot derive.

If the input folder isn't found, the annual-demand-anchored cards are omitted
rather than shown wrong.

### PDF engine

The PDF uses **weasyprint** when it's importable (it renders the same HTML for
visual fidelity) and otherwise falls back to **matplotlib `PdfPages`** — so a PDF
is always produced with no extra system dependencies (no Cairo/Pango needed).
