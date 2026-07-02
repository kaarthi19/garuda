# Coordination value

`tools/coordination_value.py` turns Garuda's headline claim into a one-command
artifact: the **coordination value** — the system cost, diesel, emissions and
unserved energy avoided when village solar+storage+diesel and the zonal grid are
planned *together* rather than separately.

Before this tool, the comparison meant running two scenarios and diffing result
CSVs by hand — error-prone, and easy to compare the wrong pair (e.g. an expansion
run against a dispatch run). The tool computes the whole table, annualises the
representative-period energy columns correctly, and refuses invalid pairs.

## Definition

> **Coordination value = `Total_Costs(reference) − Total_Costs(coordinated)`**,
> in M$/yr, for the same island, year, clean case, engine and solver settings.

The coordinated (`gridvillage`) model's feasible set contains the standalone one
— a village can always decline to connect at zero extra cost — so the value is
**non-negative for optimal same-engine pairs**, up to the solver gap.

**What it is not.** Not a welfare or benefit–cost measure (no tariffs, no
distributional effects); not carbon-priced (reference runs carry no CO₂ price);
it excludes distribution-network detail below the modelled village
interconnection. Under `relax_uc` both plans are LP lower bounds (measured UC gap
≈0.8 %), so a value below ~1 % of total cost is indistinguishable from zero. A
dispatch-engine pair measures operations-only value (no new build).

**Two `relax_uc` reading notes.** (1) The connect binary is LP-relaxed along with
the UC binaries, so a village can connect *fractionally* (pay 1 % of the cost for
1 % of the capacity); the "villages grid-connected" row counts `Connected > 0.5`,
and `--exact-uc` forces the true 0/1 decision. (2) The comparison is only
meaningful if the reference dataset carries real connection costs
(`village_connection.csv`, derived from `hubdist_km` by
`tools/connection_cost.py`) — with the file absent, connection is **free**, every
village connects, and the coordination value is overstated.

## Usage

```bash
# compare two runs you already have (any standalone vs a gridvillage run):
python tools/coordination_value.py compare \
    results/village_timor_demo_2030_reference \
    results/gridvillage_timor_demo_2030_reference

# or scaffold + solve both scenarios on HiGHS (licence-free), then compare:
python tools/coordination_value.py run --island timor_demo --year 2030 --pair village
```

`run` mode reuses `tools/launcher.py` to solve the `--pair` scenario (default
`village`) and `gridvillage` with the LP-relaxed expansion engine (fast on
HiGHS), moving any existing results directory aside first (`--keep-existing` to
opt out). `--exact-uc` switches to the exact MILP (use Gurobi on an HPC for
that); `--solver gurobi` selects it.

## Guards

- **Pair validity** — refuses (exit 2) if the two runs differ in island, year,
  clean case, or **engine**. The engine check reads each run's
  `results/<name>.config.json` sidecar, or infers dispatch from a fresh
  `reliability_results.csv`; it is what catches a stale expansion-vs-dispatch
  pair. `--allow-mismatch` downgrades these to warnings.
- **Scenario sanity** — warns if the reference scenario is not one of
  `base/grid/village/captive` or the coordinated one is not
  `gridvillage/gridcaptive`.
- **Missing site layer** — grid-only and base runs write header-only site tables;
  the tool treats them as zeros and notes it.
- **Sign check** — a coordinated plan that costs *more* than the reference is
  flagged (settings mismatch or a non-optimal solve).

## Outputs

A console table plus, in the coordinated run's directory (or `--out`):

- `coordination_value.csv` — `Metric, Unit, Reference, Coordinated,
  Delta_Ref_minus_Coord`.
- `coordination_value.md` — the headline sentence, the table, and the caveats.

Rows cover total and component costs, CO₂, grid/village diesel generation, grid
and village unserved energy (and loss-of-load hours for dispatch pairs), plus the
"where the money moved" structural rows: transmission reinforcement, village
solar and battery built, and villages grid-connected. Energy columns that are
representative-period sums are annualised with the `8760 / (Rep_Periods ×
Timesteps)` factor from the input `demand.csv` (exact for uniform `Sub_Weights`,
approximate otherwise — see [`outputs_guide.md`](outputs_guide.md)).
