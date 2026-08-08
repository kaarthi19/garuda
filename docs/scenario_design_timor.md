# Designing Timor scenarios — what to run, and what is void before you run it

A scenario that cannot express the effect you are testing does not return "no
effect". It returns **nothing, dressed as no effect** — and a null result is the
easiest thing in the world to publish by accident. This page is the
pre-registration gate for the Timor / NTT work: read it before designing a run,
and check any new scenario against the [void register](#the-void-register) below.

Companion pages: [`coordination_findings_timor.md`](coordination_findings_timor.md)
(what has been measured), [`ntt_data_integration.md`](ntt_data_integration.md)
(where the data comes from), [`sensitivity.md`](sensitivity.md) (the sweep
harness).

## The three paths a scenario can take

| Path | Tool | Use it for | Watch out for |
|---|---|---|---|
| **Batch** | `scenario_*.yml` → `generate_jobs.py` / `generate_jobs_local.py` | scenario × island × year × clean grids; HPC submission | Only keys in `PASSTHROUGH_KEYS` reach `config.json`. A key outside that list is **silently dropped** and the run solves at the model default. |
| **Sweeps** | `tools/sensitivity.py` | price ladders, 2-D grids, robustness ranges | Every axis is a **multiplier on the base**. A multiplier on a zero base is zero — the harness now refuses that rather than reporting a fake flat line. |
| **Single run** | `tools/launcher.py` | acceptance runs, smoke tests | Validates schema and previews problem size first; use `--run-tag` so repeat runs do not overwrite each other. |

All three now carry `run_tag`. Without it, runs that differ **only** by config
keys share one results directory and overwrite each other — which silently turns
an eight-point ladder into one run reported eight times.

## The void register

Each of these produces a result that looks like a finding and is not one. They
are **void, not null**: the model cannot express the effect being tested.

| # | Scenario | Why it is void |
|---|---|---|
| **N1** | Any export or sales scenario on `timor` / `timor_era5` as shipped | `demand_z1 = 0` for all 1344 h, no grid storage, `vGEN ≥ 0` ⇒ the balance forces `Σ export ≤ Σ import` every hour. You are measuring village↔village sharing, not sales. **Fix:** build a market dataset (`build_grid_demand.py`). |
| **N2** | A free "anchor plant" added to the grid `generators.csv` at `import_price = 59` | Village self-build at ~$46/MWh strictly dominates buying from a *free* plant at $59/MWh. The result is decided by the import tariff, not by the plant. |
| **N3** | `clean: clean` on Timor at `policy_scope: "grid"` | The grid RE share is renewable grid generation over *zero* grid demand — undefined, not 0. The model now **errors** with this explanation rather than constraining a NaN; use `policy_scope: "system"` (its denominator includes site demand) or give the grid a load. |
| **N4** | Any CO₂ cap on Timor off the shipped `co2_limits` | The placeholder is 3,000,000 t against roughly 75,000 tCO₂/yr of actual village emissions — about **40× slack**, so the cap cannot bind. Measure `CO2_Emissions_Village` on a reference run and set the cap from it. |
| **N5** | `export_price > 0` on any zero-grid-demand dataset | Worse than void — it **fabricates** margin. See [the wash trade](#the-wash-trade) below. |
| **N6** | An RE-share floor on synthetic `timor` | Already ~98 % RE; any policy-plausible floor is slack by construction. |
| **N7** | Cluster aggregation coarser than kecamatan without raising `village_storage_max_mwh` | The 208 MWh cap is **per unit**. An island-scale cluster needs several hundred MWh, so the cap silently manufactures the conclusion "sharing is worse". |
| **N8** | Any shared-plant scenario while site generation costs are linear | Village generation cost is perfectly linear and identical across all 780 villages — one 2X MW plant costs exactly what two X MW plants cost. "Is a shared plant cheaper?" is then a tautology with the answer "no", regardless of geography. |

**N8 has a corollary worth stating plainly.** The only lumpy, size-independent
cost in the model is the **interconnection**. Summed over 780 villages it exceeds
the entire standalone system cost. *Sharing the wire is the real question;
sharing the plant is not a question the model can currently answer.*

## The wash trade

**Do not set `export_price > import_price` on a dataset whose grid zone has no
load.** With no grid demand the balance forces `Σ export ≤ Σ import`, so a pair of
villages can transact with **zero physical generation**: A imports 1 MWh at
`import_price`, B exports 1 MWh at `export_price`, and the system books
`export_price − import_price` per MWh of pure accounting margin — bounded only by
the aggregate interconnection cap, which on `timor` is ~183 MW. At a high enough
tariff that is hundreds of millions of dollars a year of fabricated value that
would dominate every other term and read as a spectacular finding.

**The model now refuses the fabricating configuration.** Setting
`export_price > import_price` on a dataset whose weighted grid demand is zero
raises an error naming all three ways out, rather than solving and returning a
number. Verified on `timor_belu` (`export_price: 150`), which errors instead of
booking margin.

The three ways out, in order of preference:

1. **Give the grid a real load first** (`build_grid_demand.py`), and set the
   tariff from displaced marginal cost rather than by hand.
2. **Constrain exports to own generation** — set `export_backed_by_generation:
   true`, which adds `vVIL_EXPORT[t,v] ≤ Σ (that site's renewable generation at t)`.
   This is the rule any real feed-in contract imposes anyway, and it makes the
   trade structurally impossible rather than merely unattractive.

   Off by default, and **it is not cheap**. It adds one row per hour × site
   (~1.05 M on the 780-village case), and it makes the LP markedly harder in
   practice, not just larger: on `timor_belu` (81 villages) the same dispatch went
   from ~4.5 minutes to over 34 minutes on HiGHS without converging, the dual
   simplex grinding through a highly degenerate problem. Budget for Gurobi, or use
   defence 1 or 3 at full scale.

   Demonstrated on `timor_demo` at `export_price: 40` (dispatch, so site solar has
   no existing capacity and renewable generation is zero):

   | `export_backed_by_generation` | site exports | site RE generation | export revenue |
   |---|---:|---:|---:|
   | `false` | 12.29 MWh | 0.00 GWh | **$491.45** |
   | `true` | 0.00 MWh | 0.00 GWh | $0.00 |

   Without it, the sites export — and are paid — while generating no renewable
   energy at all.
3. **Keep `export_price ≤ import_price`.** `run_model.jl` warns when you do not,
   but a warning describes your result rather than preventing it.

Do **not** reach for a per-hour, per-village mutual-exclusion binary: on Timor
that is over a million binaries.

## Decarbonisation scenarios: check the constraint can bind

Two accounting defects made every Timor decarbonisation scenario void until
recently; both are fixed, and the lesson generalises.

- **Village CO₂ was reported as exactly 0** while 780 diesels burned fuel, because
  the emissions expression summed only over `VIL_UC` — the `Commit=1` subset — and
  every real Timor village diesel is `Commit=0`. A CO₂ cap on the site layer
  therefore constrained an empty set. It now covers all site generators
  (`timor_belu`: 0 → **54,067 tCO₂/yr**). `timor_demo` never showed the bug,
  because its village diesel happens to be `Commit=1` — which is exactly why a
  demo dataset is not a substitute for the real structure.
- **The grid RE share was `NaN`** — renewable grid generation over *zero* grid
  demand. It now reports `NaN` deliberately (the ratio is undefined, and 0 % would
  read as "the grid runs on fossil"), the model no longer builds NaN coefficients,
  and a `clean` run at grid scope fails with an explanation. Use
  `policy_scope: "system"`, whose denominator includes site demand, or give the
  grid a load.

Before running any policy ladder, **measure first**: take
`CO2_Emissions_Village` from a reference run and set the cap from it. The shipped
`co2_limits` of 3,000,000 t is roughly 40× actual village emissions — slack by
construction (N4).

## An open semantics question

The grid is currently a **hybrid** and it is worth deciding which it should be
before attributing any coordination value that finally appears.

A village import today is *physically generated at the zone* — the grid burns
fuel and pays `eVariableCostsGrid` (~$197/MWh at the diesel margin) — **and** the
village is charged a flat `import_price` of $59/MWh on top. The same MWh is
therefore costed twice, at about $256/MWh in total. Meanwhile an export at
`export_price = 0` earns nothing, so an inter-village transfer carries a one-sided
deadweight charge.

Two coherent readings, and they are not equivalent:

- **External market.** `import_price` is the price of energy from outside the
  modelled system. Then the zone should not *also* generate it.
- **Physical bus.** The zone generates the energy and `import_price` is a network
  tariff. Then it should be a wheeling charge, not an energy price — and it should
  probably be symmetric.

**Partly settled, for the Timor case.** The shipped Timor scenario files now set
`import_price: 0`, on the reasoning that the system-optimal deliverable should not
charge a transfer on top of a resource cost it already counts. That removes the
one-sided charge from the default runs. The model's own default is unchanged at
59.0, so nothing outside this case moves, and
an `import_price` sweep (`tools/sensitivity.py`) measures the axis so the choice is
measured rather than assumed.

What remains open is the symmetric question: if the grid is a physical bus, should
an *export* earn the zonal marginal cost automatically rather than needing
`export_price`? Under a central-planner objective it effectively does once the bus
carries load — which is why the export study needs `timor__market` and not a
tariff.

Until the A5 sweep is run, read "coordination value is ~0 on Timor" as having
**two** candidate explanations: genuine solar synchrony plus cheap storage, or the
one-sided transfer charge that was in force when it was measured.

## Sequencing

Roughly in dependency order. The first three are cheap and make everything after
them interpretable:

1. **Bound it before you model it.** Make interconnection free
   (`--param connection_cost=0`) and measure the saving. That is the ceiling on
   coordination value at *any* connection cost, because cost is monotone. If the
   ceiling is negligible, no amount of extra machinery will find value beneath it.
2. **Run the negative control every time.** A scenario that should produce exactly
   zero (no buyer, no price) is the only reliable way to catch a wash trade or a
   sign error before it reaches a headline.
3. **Check the constraint can bind** before running a policy ladder — measure
   actual emissions and set the cap from them.
4. **Then** the substantive questions: does a grid load alone change the village
   plan; what does the supply curve look like against a tariff; which villages
   clear and at what interconnection cost; does real weather change the answer.

Two habits throughout, both learned the hard way here:

- **Report the achieved MIP gap**, never the permitted `mipgap`. A 1 % tolerance
  permits a large absolute gap at island scale; citing it proves nothing about the
  run you actually did. Treat differences below ~$100 as numerical noise.
- **Re-solve a frozen baseline** (`tools/regression_gate.sh`) around any change to
  shared model or reporting code, so you can tell a reporting fix from a physics
  change. Update the baseline deliberately, with the reason, never to turn a red
  gate green.
