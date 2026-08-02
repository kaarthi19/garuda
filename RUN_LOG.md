# Run log — Timor study

A working notebook: every change made to the repo for this study, and every model
run executed, with the numbers. Append to it; do not rewrite history. Newest
session at the top of [Sessions](#sessions), newest run at the bottom of the
[Run ledger](#run-ledger) so the ledger reads chronologically.

The authoritative *plan* is [`docs/run_plan_timor.md`](docs/run_plan_timor.md).
This file records what actually happened against it.

---

## Machine

Verified 2026-07-31 on `pwrlabadmin@garuda`. Re-verify if anything moves.

| | |
|---|---|
| CPU / RAM | 72 cores, 187 GB |
| Julia | 1.12.6 (`~/.juliaup/bin/julia`) — matches the `Manifest.toml` pin |
| Gurobi | **Works at full size.** Licence `TYPE=ACADEMIC VERSION=13`, expires 2027-02-26 |
| Gurobi binding | Julia uses the **bundled `Gurobi_jll` v13.0.0 artifact**, *not* the local `/opt/gurobi1101` (v11) install. No `GUROBI_HOME` or `LD_LIBRARY_PATH` needed — contrary to `hpc_handoff.md`, which was written for a cluster |
| Scheduler | **No SLURM.** `sbatch`/`squeue` absent, so `generate_jobs.py --submit` is unusable here; use `generate_jobs_local.py` |
| Python | 3.12.3 with pandas, numpy, click, pyyaml, **pytest 9.1.1**. Only `python3` exists — **every `python ` command in the run plan fails as written** |
| Measured solve time | 780-village exact-UC expansion: **~25 min for the root relaxation alone** (build ~10 min, presolve 173 s, barrier ~750 s, crossover still running at 1170 s), zero B&B nodes. Budget **60–90 min/solve**, not the docs' 30 |
| Measured memory | **52–53 GB per 780-village job.** Parallel width is **2**, not 72 — and the two contend on memory bandwidth. Gurobi self-limits to 32 threads |
| ERA5 data | **Present** at `/home/pwrlabadmin/village-indonesia-100gw/solar_era5/village_solar_cf_hourly.csv` (85 MB, joins 780/780). The plan's "Blocked" ERA5 rows are wrong here |
| `regression_gate.sh check` | **18 min**, not the documented ~6 |

Gurobi size-limit check (a trivial LP would pass even under the size-limited
fallback, so this was tested above the ~2000-var threshold):

```
LP   n=20000 vars      -> OPTIMAL
MILP n=5000 binaries   -> OPTIMAL
```

---

## Sessions

### 2026-07-31 — orientation, sync, plan revision

**Repo synced.** `claude/repo-orientation-sync-bd6b46` fast-forwarded to
`origin/main` in two steps: `33f57c7 → 827d5b1` (17 commits), then
`827d5b1 → 951da7c` (8 commits). All seven remote feature branches were already
merged; nothing pending.

Two incoming changes that alter interpretation, not just code:

- `dfca595` set Timor's `import_price` to **0** — a tariff is a transfer, not a
  resource cost, and the objective already charges `eVariableCostsGrid` for what
  the grid burns to serve an import.
- `d2f2879` flagged the published coordination ceiling as **conditional on that
  tariff**. The "coordination value ≈ 0" null may have been partly an artifact of
  a one-sided $59/MWh charge on inter-village transfers.

**Changes made this session**

| # | Change | File(s) | Tracked? |
|---|---|---|---|
| 1 | Wrote agent context file — architecture map, commands, verified gotchas | `CLAUDE.md` (in the **main checkout**, symlinked into the worktree) | No — `.git/info/exclude` |
| 2 | **A1 split into A1a + A1b; C1 promoted into group A** | [`docs/run_plan_timor.md`](docs/run_plan_timor.md) | Yes, uncommitted |
| 3 | Market-dataset build moved from a group-C prerequisite to a group-A one | [`docs/run_plan_timor.md`](docs/run_plan_timor.md) | Yes, uncommitted |
| 4 | Disambiguated downstream `A1` references to `A1a` (A2, A4, B1) | [`docs/run_plan_timor.md`](docs/run_plan_timor.md) | Yes, uncommitted |
| 5 | "Highest-priority run" updated to four jobs across both datasets | [`hpc_handoff.md`](hpc_handoff.md) | Yes, uncommitted |
| 6 | This file | `RUN_LOG.md` | Yes, uncommitted |

**Why change 2.** Group A ran only on plain `timor`, where `demand_z1 = 0` for all
1344 hours and the grid zone is a single 122.131 MW PLN diesel (`Max_Cap_MW = 0`)
serving no load. Against a village layer of 780 sites, 544.1 GWh/yr, 128.2 MW
coincident peak — figures reconciled against the dataset, matching
`coordination_findings_timor.md`. On that dataset a village can *import* (at the
diesel margin, ~$197/MWh) but cannot *sell*: no load absorbs it, the grid zone has
no storage, and `vGEN ≥ 0` stops the diesel absorbing power, so the balance forces
`Σ export ≤ Σ import` hourly.

The connection decision is therefore biased against connecting by construction —
the largest economic reason to connect is not representable. "0 of 780 connect" is
close to structural on that dataset rather than a finding about Timor. A1b
(formerly C1, on `timor__market`: 682 GWh/yr, 124 MW peak) restores a buyer, and
the pair brackets the answer — A1a understates connection value, A1b overstates
cheap supply via NTT-wide RE potential (~4,290 MW wind, ~3,132 MW solar against a
124 MW peak) that sets the marginal price.

**Findings raised (not fixed here)**

| Finding | Status |
|---|---|
| **jawa_bali zone/demand mismatch.** `demand_cols` are selected in `unique(generators.Zone)` order (`input_data.jl:63`) but `optimizer.jl:187` indexes `demand[t,z]` positionally by zone number, while `dispatch_engine.jl:83` indexes by *name*. jawa_bali has `Z = [1,2,3,4,6,7,5]`, so zones 5/6/7 solve against the wrong load series | Confirmed; spun off to a separate session |
| `tools/launcher.py --engine expansion` silently LP-relaxes: `--relax-uc` is `default=True` regardless of engine (`launcher.py:133`) | Open |
| `data_indonesia/captive/2035/papua/ip_demand.csv` has no `Voll` column; `input_data.jl:199` reads `.Voll[1]`, so that folder cannot load | Open |
| `vRET_CAP_UC` declared without `>= 0` (`optimizer.jl:26`); via `cCapOldUC` a negative retirement lets a UC unit exceed nameplate with no investment charge | Open, latent |

**No model runs executed this session.** The run ledger below is empty.

---

## Run ledger

One row per solve. `results/<scenario>_<island>_<year>_<clean>[__<tag>]/`.

**No study runs yet.** The rows below are *probe* solves executed during plan
verification on 2026-07-31 to measure timings and reproduce suspected traps. All
carry a `run_tag`, so none occupies a study-run folder.

### Study runs

| # | Date | Plan ID | Island | Scenario | Solver | `Total_Costs` ($M/yr) | Gap | Wall | Notes |
|---|---|---|---|---|---|---|---|---|---|
| **1** | 07-31 | **A1a** | timor | `village` | gurobi | **69.13435** | **n/a — pure LP** | **11 m 20 s** | Barrier, 27 iters / 85 s. Objective `6.91343504e+07` |
| **2** | 07-31 | **A1b** | timor__market | `village` | gurobi | **86.41227** | **0.1682 %** (±~$145k) | ~18 min | MILP, not an LP — see correction below. Grid NSE cost $11,503 ≈ 5.75 MWh/yr on 682 GWh, sanity gate **passes** |
| **3** | 07-31 | **A1a** | timor | `gridvillage` | gurobi | **69.545469** | **0.8311 %** ⚠ **INVALID** | 43 m 11 s | 780 binaries. Explored **1 node**, 822,771 simplex iters. `Connected = 41/780`. **Provably suboptimal — do not use** |

### Provisional: coordination value on `timor__market` is **≥ $18.69 M/yr**

From A1b `gridvillage`'s solver log at 4512 s (run still in progress, gap 36.2 %):

| | $M/yr | source |
|---|---|---|
| `village` true optimum | ∈ [86.26695, 86.41227] | best bound / best objective, gap 0.1682 % |
| `gridvillage` incumbent (feasible ⇒ upper bound on its optimum) | ≤ 67.57456 | `H 0 0 6.757456e+07` |
| **⇒ coordination value ≥** | **18.69239** | `86.26695 − 67.57456` |

**≈ 21.7 % of the system, and rigorously bounded below** — arithmetically it can
only grow as the incumbent improves. Contrast A1a on the zero-load dataset, where
the same quantity is bounded *above* by $166,859 (0.24 %).

**CORRECTION (2026-08-01) — what that number actually is.** An earlier version of
this entry attributed it to villages importing from "a grid with 84 real
generators". That was wrong on both counts, and the real mechanism changes how the
result must be reported.

`timor__market`'s `generators.csv` has 84 rows, but only **4 are existing** —
157 MW coal (3 units) + 122.1 MW diesel = 279.1 MW. The other **80 are expansion
candidates** carrying **9,113.8 MW** of headroom against a **124.1 MW** peak
(≈73×), of which 4,290 MW is wind and 3,132 MW solar. That is NTT-*wide* potential
scaled by `--share 0.42`, exactly the limitation `docs/run_plan_timor.md` flags for
group C.

What the grid *actually built and ran* in the A1b `village` solve:

| | |
|---|---|
| New capacity built | **469 MW of battery — and nothing else** |
| Operating fleet | 511 MW battery, **124 MW coal**, 2.04 MW diesel |
| Wind / solar built | **0 MW**, from 7,422 MW of headroom |
| `Grid_REShare` | **0.0** |
| `CO2_Emissions_Grid` | **766,069 tCO₂/yr** |

So the grid is a **coal-plus-battery system with zero renewables**, and the
coordination value is villages substituting **imported coal** for their own
solar + storage. Village emissions are 12,865 tCO₂/yr islanded; the grid they
would connect to emits 766,069 tCO₂/yr — **60× more**.

The $18.69 M bound is arithmetically sound but it is **coal-substitution value,
not a decarbonisation result**. It must never be quoted as "coordination is worth
21.7 % of the system" without that mechanism attached.

**Plausibility concern about `timor__market` itself, before any of this is
published:** the solve built 469 MW of new battery to serve a 124.1 MW peak (a
511 MW fleet, ~4× peak) while building none of 7,422 MW of available wind and
solar. Coal + battery beating all renewables at every point on that supply curve
suggests the transplanted candidate costs, not Timor. Check the candidate
`Inv_Cost_per_MWyr` values against the coal fuel price before treating any
`timor__market` number as a finding.

> **RESOLVED — and it was not the costs.** The battery MW figures above (469
> built / 511 operating, and 475 / 517 on `timor__marketfix`) are the symptom of
> a *model* defect, not a cost-data one. The loader partitioned grid generators
> with `Commit == 1` (UC) and `Commit == 0` (ED); every `battery_candidate` row
> ships `Commit = 2`, so it fell out of **both** sets and acquired no capacity
> constraint at all — no `cCapNew`, so `Max_Cap_MW` never bound; no
> `cMaxPowerED`, so discharge was uncapped; and `Inv_Cost_per_MWyr` is summed
> over `ED_NEW`, so the power block was charged **exactly $0**. That is why
> `timor__marketfix` — which *did* set `Inv_Cost_per_MWyr = 49,829` — still
> reported 517 MW against a 42 MW `Max_Cap_MW`: the new price was never applied
> to anything. The reported MW was the true solved `vCAP`, so the extractor was
> right and the model was wrong.
>
> Fixed on `claude/upbeat-elion-1b2bd2` (`ED` is now the complement of `UC`), with
> `tests/verify_capacity_accounting.jl` pinning it. **Every capacity-expansion
> result in this log that involved a grid battery is superseded and must be
> re-solved** — that is A1b `village`/`gridvillage` on `timor__market`,
> `timor__marketfix` and `timor__marketfixnf`. Dispatch-only rows are unaffected:
> `dispatch_only()` pins `CAP` for every `g ∈ G`, which masked the defect (and is
> why the regression gate never saw it). The cost-vintage question above is still
> open and still worth answering — it just is not what produced these MW.

A1a's contrast still stands and still vindicates running both pairs — but the
honest statement is "a zero-load grid cannot show coordination value at all, and
the market dataset as built answers a coal question", not "coordination is worth
two orders of magnitude more".

### ⚠ A1a `gridvillage` at `mipgap 0.01` returned a provably suboptimal answer

| | $M/yr |
|---|---|
| `village` (OFF, exact LP) | 69.134350 |
| `gridvillage` (ON, MILP incumbent) | 69.545469 |
| apparent coordination value | **−411,118 $/yr** |

**A negative coordination value is impossible.** `gridvillage` strictly dominates
`village`: setting all 780 `vVIL_CONNECT` to 0 reproduces the islanded solution
exactly, at $69.134350 M, and costs nothing extra (connection cost is only
incurred when connected; with no connections the grid serves nothing and
generates nothing). That point is feasible for the ON problem, so

```
true gridvillage optimum  <=  69.134350  <  69.545469 = reported incumbent
```

The run is therefore **suboptimal by at least $411,118**, while reporting
`Optimal solution found (tolerance 1.00e-02)` and exiting 0.

What the solver actually did: `Explored 1 nodes (822771 simplex iterations) in
1913.23 seconds`, then stopped the instant `gap 0.8311 %` fell under the 1 %
tolerance — having never found the all-islanded solution. Best bound
`6.896749080623e+07` (the unchanged root LP), best objective
`6.954546888537e+07`.

**True coordination value is bounded to `[0, 166859] $/yr`** — non-negative by
dominance, and at most `village − LP bound = 69.134350 − 68.967491`.

The incumbent's structure shows the failure directly: connecting 41 villages cut
village-layer costs by $378,098 (Fixed_Village −124,130, Fixed_Village_Storage
−219,829, Variable_Village −34,139) but added ~$754k of connection cost plus
$34,734 of grid cost — a net loss the solver should have rejected by simply not
connecting.

**`Connected = 41 of 780` is also an artifact** and must not be quoted against the
published "0 of 780". It is a property of a suboptimal incumbent, not of the
optimum.

**Consequence:** every downstream run that differences against A1a — A3, A5, B1 —
inherits this. None should be run at `mipgap 0.01`. The queued `mip1e4` re-run is
now the load-bearing measurement, not a refinement.

Timing note: 43 min at 0.01 with a single node explored, on a root LP of ~800 s.
1e-4 will need real branching, but the root is cheap, so it is plausibly
affordable.

**Cross-check: the two `village` legs decompose exactly.** The village-layer terms
are identical to 6 d.p. across both datasets — Fixed_Village 29.960413,
Fixed_Village_Storage 35.600186, Variable_Village 3.573751 — which is correct,
since `village` sets `Grid = false` and islanded villages cannot see grid load.
The whole difference is the added grid system:

```
A1b − A1a = 86.412272 − 69.134350 = 17.277922
grid terms = 5.084219 (Fixed_Gen) + 12.182200 (Var_Grid) + 0.011503 (NSE)
           = 17.277922      exact to 6 d.p.
```

So serving `timor__market`'s 682.1 GWh/yr costs **$17.28 M/yr (~$25/MWh)**, and the
village layer is provably untouched between the two. Strong internal consistency.

### Finding: at `mipgap: 0.01` the coordination value is unresolvable

`gridvillage` on `timor` is the only leg with binaries — Gurobi reports
**780 integer (780 binary)**, the `vVIL_CONNECT` variables, against 18.9 M
continuous. Its root LP relaxation solved to **$68.9674908 M/yr**
(barrier, 62 iters, 796 s).

That bound brackets the whole question:

| | $M/yr |
|---|---|
| `village` (exact LP) | 69.134350 |
| `gridvillage` root LP bound (lower bound on its optimum) | 68.967491 |
| **⇒ coordination value ≤** | **0.166859 → $166,859/yr** |
| `mipgap: 0.01` tolerance on a $69 M objective | **± ~690,000** |

**The entire meaningful range is ~4× smaller than the permitted gap.** The MILP may
terminate at any incumbent within 1 % of the bound — anywhere in
$68.967 M–$69.657 M — and print "solved successfully". Whatever coordination value
comes out of this run is therefore *not* a measurement; it is wherever
branch-and-bound happened to stop.

This is blocker B1 from the briefing, now quantified on real numbers rather than
inferred. It also confirms the fix is tractable: 780 binaries with an LP relaxation
in 796 s is a small MIP by any standard, so `mipgap: 1e-4` (±$6,900) is plausibly
affordable and would resolve a $2,569 effect. **Decide before A3/A5**, which
difference against these numbers and inherit the same tolerance.

**A1a `village` cost breakdown** ($M/yr): Fixed_Village 29.960413,
Fixed_Village_Storage 35.600186, Variable_Village 3.573751; everything else 0.
Grid-side costs are all zero, as expected with `Grid = false`.

Against the published $64.63141317 M/yr on the same scenario: **+$4.50 M/yr**.
Directionally what `f3d054b` predicted — village battery *power* went from free to
$30,001/MW-yr, and `Fixed_Costs_Village_Storage` is now the single largest term at
$35.60 M/yr. The published number is not reproducible on current data by design.

### Finding: "exact UC" is vacuous on plain `timor` — but NOT on `timor__market`

**Correction (logged 19:45):** an earlier version of this entry said the finding
covered "the Timor datasets" and recorded run #2 as a pure LP. Both were wrong.
It holds for plain `timor` only.

| Dataset | Grid gens | `Commit` values | # `Commit==1` | Consequence |
|---|---|---|---|---|
| `timor` | 1 | `[0]` | **0** | no UC binaries; `village` leg is a pure LP |
| `timor__market` | 84 | `[0, 1, 2]` | **30** | real UC units; **every** leg is a MILP |

So the transplanted market fleet reintroduces unit commitment. Run #2 (`village`
on `timor__market`) was a MILP that terminated at **gap 0.1682 %**
(best objective `8.641227246518e+07`, best bound `8.626695029517e+07`) — matching
its `cost_results.csv` to 11 s.f., which is how the mistake was caught. Its
$86.41227 M therefore carries roughly **±$145k**, and the derived "$17.28 M/yr to
serve 682 GWh" inherits that. The A1a↔A1b cost decomposition still balances to
6 d.p., because the village-layer terms are common to both.

Note `Commit = 2` appears in `timor__market`'s fleet. The loader tests
`Commit .== 1`, so those rows are **not** UC units — the sentinel behaves as
documented, but any filter written against a 0/1 assumption would be wrong here.

`timor`'s `generators.csv` (1 row) and `village_generators.csv` (2,340 rows) are
**`Commit = 0` throughout** — zero UC units. So there are no unit-commitment
binaries to relax, and `relax_uc: false` has no effect on this data. Gurobi's log
confirms it: no `Variable types` line, no root relaxation, no nodes explored, no
gap — just `Barrier solved model in 27 iterations`, then `Optimal objective`.

Consequences, in order of importance:

1. **The `village` leg is a pure LP solved exactly** (barrier, ~1e-8), not a MILP
   at 1 % tolerance. Its $69.13435 M/yr is precise. The `mipgap` blocker does
   **not** apply to it.
2. **The blocker is now precisely located:** only `gridvillage` carries binaries —
   the 780 `vVIL_CONNECT` variables. The coordination value is
   `village` (exact) − `gridvillage` (≤1 % gap ≈ $690k), so the tolerance concern
   is entirely on the ON leg.
3. **Tightening `mipgap` now looks tractable**, which it did not before: only 780
   binaries, and the LP relaxation solves in 85 s. Re-running `gridvillage` at
   e.g. `mipgap: 1e-4` is plausibly affordable and would make a $2,569 effect
   resolvable. Decide this before A3/A5, which difference against these numbers.
4. **The premise behind "Gurobi is effectively mandatory" is weaker than stated.**
   That claim rests on an exact-UC MILP that does not exist here. HiGHS was
   measured slow on this model, so Gurobi is still the right choice — but for LP
   barrier performance, not for MILP.

The 11-minute wall is also mostly model build: ~10 min JuMP construction against
85 s of solving, on a presolved 11.9 M × 8.9 M problem.

### 2026-08-01 — `time_limit` config key added; cost-corrected A1b launched

**New config key `time_limit`** (seconds, default 259200 = 3 days = the previous
`make_solver` default, so omitting it is a strict no-op). Threaded through all
eight sites: `run_model.jl` (read + validate + forward), `function_compiler.jl`
(kwarg + both engine forwards), `capacity_expansion` and `dispatch_only`
(signature + `make_solver` call), and `PASSTHROUGH_KEYS` in both job generators.
Documented in [README.md](README.md); guarded by
`test_time_limit_is_threaded_from_config_to_make_solver`. Suite 105 → **106**.

**Why it was needed.** The two market `gridvillage` legs are not expected to close
their gap (the uncorrected one sat at 36.2 % after 2 h 32 m without leaving the
root). Bounding them with an OS `timeout` **destroys the result CSVs**, which are
exactly where the per-village build and trade data lives. A *solver* time limit
terminates gracefully instead: `optimizer.jl:921` prints "reached the time limit"
and then extracts results from the incumbent as normal.

Verified end-to-end on `timor_demo` at `time_limit: 20.0`, `mipgap: 1e-9`:

```
Time limit reached
Best objective 2.359041715759e+07, best bound 2.338583755809e+07, gap 0.8672%
Capacity expansion reached the time limit (MILP, exact UC).
  -> 14 result CSVs written, Total_Costs = 23.590417157590704
```

A feasible incumbent is a real plan — every village's build in it is genuine, it
is simply not proven optimal. Always quote the **achieved** gap beside it.

**Overnight batch launched.** All four cost-corrected A1b solves use
`time_limit: 28800` (8 h) with a 9 h OS backstop, so Gurobi always stops
gracefully first. Concurrency is gated on ≥75 GB free: measured peaks are 51.9 GB
(timor) and 58.3 GB (market, *at the root*), so 187 GB allows **2 concurrent
market solves**, not 4 — four would need 232 GB and be OOM-killed as a bare
`exit -9`.

### 2026-08-01 (cont.) — DMO coal, leg-1 kill, and the third suboptimal incumbent

**Coal price corrected to the DMO cap** in both derived market datasets:
`Cost_per_MMBtu` 1.423 → **2.94** ($70/t at 6,000 kcal/kg GAR, the electricity-
sector cap unchanged since 2018; conversion 23.81 MMBtu/t). Marginal cost of the
existing PLTUs moves $12.88 → $26.49/MWh. The dataset's own `coal_captive` row
($3.846/MMBtu) was already *above* DMO — the grid coal price was internally
inconsistent, not just low. The cheap-coal `marketfix` village result is
preserved at `results/village_timor__marketfix_2030_reference__cheapcoal`.

**Timor's coal is real and existing, not new.** The three market-dataset PLTUs
(Kupang FTP-1 33 MW, Timor-1 100 MW, Atambua 24 MW) carry `New_Build = -1`
(existing) and sit on Timor. Plain `timor`'s single 122 MW diesel omits them.

**Leg 1 (A1a `gridvillage` @ 1e-4) killed at user request** after 83 min: still
node 0, incumbent stuck at the same suboptimal $69.545469 M, log silent 44 min
inside a node LP. Log preserved (`jobs/mip1e4_timor/solve_KILLED_at_root.log`).
What survives: **coordination value on plain `timor` ∈ [0, $166,859]/yr** — the
dominance argument and the root bound need no further compute.

| # | Plan ID | Island / scenario | `Total_Costs` | Gap | Wall | Status |
|---|---|---|---|---|---|---|
| 4 | A1b′ | marketfix / `village` (coal $1.423) | 86.66406 | 0.6351 % | 17 m | superseded (`__cheapcoal`) |
| 5 | A1b′ | marketfix / `village` (DMO) | **97.04169** | 0.2358 % | 17 m | ⚠ **suboptimal ≥ $155,582** (see below) |
| 6 | A1b′ | marketfixnf / `village` (DMO) | **96.88611** | 0.9500 % | 19 m | valid; also bounds #5 |
| 7 | A1b′ | marketfix / `gridvillage` (DMO) | running | — | — | root LP → ~$59.27 M |
| 8 | A1b′ | marketfixnf / `gridvillage` (DMO) | running | — | — | root LP in progress |

**DMO effect (run 4 → 5): +$10.38 M/yr, of which +$10.44 M is the grid fuel
bill.** Pure price pass-through: coal generation fell only ~1.2 %,
`Grid_REShare` stayed **0.0000**. With corrected RE costs *and* DMO coal, the
grid still builds no renewables — existing coal at $26.49/MWh marginal beats new
solar at $42.70/MWh all-in because its capex is sunk. Structural, and now
defensible: the levers that change it are policy (carbon price, retirement
schedule, RE mandate), not data fixes.

**Third provably-suboptimal `mipgap 0.01` incumbent.** `marketfixnf` is a strict
restriction of `marketfix` (verified: only `New_Build`/`Max_Cap_MW` differ, on
the 24 fossil-candidate rows; no headroom larger; fuel prices identical), so
`fix_optimum ≤ nf_optimum ≤ 96.88611`. Run 5 reported 97.04169 — **suboptimal by
≥ $155,582 while printing "Optimal solution found"**. Pattern now: A1a-ON,
A1b-ON (uncorrected), and run 5. Every within-tolerance incumbent on this
formulation needs a dominance cross-check before use.

**Corollary: barring new fossil is free.** The restricted system costs no more
(96.886 < 97.042); the grid was not going to build gas/CCGT/diesel anyway.

**The OFF-side village story is bulletproof across every dataset variant.**
Per-village builds in the `village` scenario are **bit-identical** across plain
`timor`, `marketfix`, and `marketfixnf`: 360.701 MW solar, 148.514 MW battery,
6.656 MW diesel; 0 of 2,340 rows differ (max delta 0.00e+00). Islanded villages
cannot see the grid, so every grid-side correction leaves them untouched — the
baseline figure set (F1–F4, F6) is robust to all of it, and the $155k
suboptimality in run 5 is purely grid-side churn.

### 2026-08-01 (cont.) — sibling session finds the real storage defect: `Commit = 2` escapes both engine sets

The spawned storage-bug session (branch `claude/upbeat-elion-1b2bd2`) found the
root cause, and it is a **model** defect, not a reporting one. Verified
independently in this worktree: `input_data.jl:269/272` builds `UC = Commit .== 1`
and `ED = Commit .== 0`, so the market battery row (`Commit = 2`, R_ID 84) is in
**neither** set. Consequences: `Max_Cap_MW` never applied, no `cMaxPower*`
constraint, and the power-investment charge (summed over `ED_NEW`) is $0
regardless of the CSV price. The 517 MW "battery" was a free, unconstrained
resource. My earlier inference that "~7.3 MW was charged, the objective is
self-consistent" was wrong — the $0.365 M delta came from elsewhere.

**Contaminated:** every `timor__market*` result (runs 2, 4, 5, 6, both in-flight
gridvillage legs, and the killed uncorrected A1b). The DMO fuel-bill delta
(+$10.4 M) is directionally plausible but its absolute totals are not credible.
**Unaffected:** everything on plain `timor` — both its files are `Commit = 0`
throughout (verified), so A1a, the diversity findings, and the bounds figure's
village↔village row all stand.

Fix exists on `claude/upbeat-elion-1b2bd2` (`ED` = complement of `UC`, pinned by
`tests/verify_capacity_accounting.jl`); market runs must be re-solved on it.

### 2026-08-01 06:26 — kill, commit, cherry-pick, relaunch on the fixed model

Both free-battery gridvillage solves killed (logs preserved as
`jobs/mf_*/solve_freebatt_KILLED.log`). Pending work landed as five commits
(`1204def` time_limit, `47deb16` sensitivity --lp-method, `036d8d5` village
tools, `e985809` scenario files, `d459592` docs/run log), then the
capacity-accounting fix cherry-picked cleanly from the sibling branch
(`d3f1b0c` → `ED = setdiff(G, UC)`, `VIL_ED = setdiff(VIL_G, VIL_UC)`, plus an
`ED_RAMP = ED minus STOR` set so storage entering ED does not inherit thermal
ramps).

Verified after the pick: `tests/verify_capacity_accounting.jl` — all checks
passed; pytest **116 passed**; all four datasets (`timor`, `timor__diverse`,
`timor__marketfix`, `timor__marketfixnf`) pass the stricter validator, which
now accepts `Commit = 2` as a handled sentinel rather than a hole.

Contaminated village results preserved as `…__freebatt`; all four market legs
relaunched at 06:26:35 on the fixed model (Gurobi, `lp_method 2`,
`time_limit 28800`, memory-gated). **On this model the battery row is finally
real:** in `ED`, capped at its 42 MW `Max_Cap_MW`, power priced at
$49,829/MW-yr. Every previous market number measured a free unlimited battery;
these are the first that do not.

### 2026-08-01 18:45 — first fixed-model batch: one good leg, two failure modes, two retractions

**Ledger (fixed model, DMO coal):**

| # | Island / scenario | `Total_Costs` | Gap | Status |
|---|---|---|---|---|
| 9 | marketfix / `village` | **102.74861** | 0.8237 % | **valid — the OFF anchor** |
| 10 | marketfixnf / `village` | 99.89870 | 0.9674 % | ⚠ invalid — see nf error below (`__freefossil`) |
| 11 | marketfix / `gridvillage` | 2431.60185 | **97.54 %** | ⚠ trivial all-NSE incumbent (`__trivialinc`) |
| 12 | marketfixnf / `gridvillage` | 2431.60185 | 97.54 % | ⚠ both defects (`__freefossil`) |

**Free battery quantified (OFF side):** run 5 (free battery) 97.04169 → run 9
(real battery) **102.74861** = **+$5.71 M/yr**, far outside the combined ~$1.7 M
gap tolerance. The free unlimited grid battery was worth ~$5.7 M/yr to the
islanded-villages case alone.

**Retraction — my `nf` construction error.** The 24 "zeroed" fossil candidates
all carry nonzero *potential* `Existing_Cap_MW` (1,037.4 MW, all `Commit = 1`).
Setting `New_Build = 0` made them **free existing plant**, not banned plant —
2 of them operate in run 10. `nf` was therefore never a restriction of `fix`,
and two earlier claims fall with it: "marketfix village suboptimal ≥ $155,582"
(the freebatt-era cross-check) and "barring new fossil is free". Also noted:
`Max_Cap_MW = 0` cannot ban a candidate either — optimizer.jl:45–50 bounds only
rows with `Max_Cap_MW > 0`, so zero means **unbounded**. Rebuilt correctly:
`New_Build = 1`, `Max_Cap_MW = 0.001` (a 1 kW cap; rows cannot be deleted —
R_ID must stay 1..N positional). Now provably a restriction: only `Max_Cap_MW`
differs from fix, never larger. Schema valid.

**Gridvillage failure mode and its fix.** Both 8 h runs ended at node 1 —
root LP 79 min, then ~6.7 h of cuts/heuristics that never found a usable
incumbent; the only feasible point at termination was the all-NSE plan Gurobi
seeds (2431.6 = 1226 GWh × Voll $2,000, split grid 1352.7 / village 1078.8).
`time_limit` behaved exactly as designed; the incumbent was just worthless.
Fixed in `7d79305`: `capacity_expansion` now warm-starts `vVIL_CONNECT = 0`
(all-islanded is always feasible), so the incumbent is at worst the OFF cost
instead of all-unserved. Smoke-verified on timor_demo: "User MIP start produced
solution with objective 2.44161e+07 (14.61s)".

**Relaunched 18:45:04** (`jobs/sched_rerun.sh`): nf village (rebuilt dataset),
then both gridvillage legs with the warm start, 8 h caps. Run 9 stands and is
not re-run.

### 2026-08-01 18:53 — `exact_connect`: relax the UC, keep the wire decisions binary

Answering "can we relax the commit variables on the village side": the village
layer has **no** commit binaries on these datasets (`Commit = 0` throughout) —
all ~121k UC binaries belong to the 30 grid thermal units. The tractability play
is therefore: relax the grid UC, keep the 780 `vVIL_CONNECT` binaries exact.
Plain `relax_uc` cannot do that — `UC_BINARIES` includes `:vVIL_CONNECT`, so it
also relaxes the wire decision (fractional connect = fractional wire cost for
full trade benefit, and `Connected` becomes `round(Int, x)` of a fraction).

New config key **`exact_connect`** (`7d81cee`, default false = strict no-op):
with `relax_uc`, relaxes `setdiff(UC_BINARIES, (:vVIL_CONNECT,))`. Smoke-verified
on timor_demo: "Variable types: 174799 continuous, **4 integer (4 binary)**",
warm start loaded, `Connected` integral. Threaded through all eight sites,
README row added, passthrough guard green, suite 116.

**Relaunched 18:53:18** (`jobs/sched_ucrelax.sh`, tag `ucrelax`): all four legs
at `relax_uc + exact_connect`. The `village` legs become pure LPs (exact, fast);
the `gridvillage` legs become 780-binary MILPs with the warm start — the A1a
shape that is known to branch. The exact-UC gridvillage attempts stand down;
their root bounds (59.906 / 59.832 $M) remain valid exact-problem lower bounds.
The exact nf `village` anchor (launched 18:45) continues alongside.

**Caveat to carry on every `ucrelax` number:** UC relaxed ⇒ operations
optimistic by the measured ~0.8 % (tools/uc_relaxation_gap.jl); the optimism
appears in *both* legs of a coordination pair, so it largely cancels in the
delta; the who-connects decision is exact.

### 2026-08-01 21:07 — the coordination value gets a proven floor

Both `ucrelax` gridvillage legs solved their root LP (**59.90591 $M**, identical
across fix and nf) and then found the **same improving incumbent**:
`H 0 0 8.415450e+07` — a feasible coordinated plan at **$84.1545 M/yr**, down
from the $101.718 M warm start. With OFF an exact LP at 101.71759, the
coordination value on the market case is now rigorously bracketed:

| | $M/yr |
|---|---|
| OFF (islanded, exact LP) | 101.71759 |
| ON incumbent (feasible) | ≤ 84.15450 |
| ON root bound | ≥ 59.90591 |
| **coordination value** | **∈ [17.563, 41.812]** |

**≥ $17.6 M/yr proven — ~17 % of the islanded system** — on the fully corrected
model: capacity-accounting fix in, real battery (42 MW cap, priced power), DMO
coal, corrected RE costs, exact wire decisions. The bound can only improve as
B&B continues. fix and nf finding bit-identical incumbents also extends the
"banning new fossil is free" result to the ON side.

Earlier `village` legs (ucrelax): both **101.71759, `Optimal objective`** —
identical to 9 s.f., confirming the fossil ban costs exactly $0 in the OFF case
and that the exact-UC fix/nf delta ($104,540) was gap noise. Relaxed OFF sits
1.0–1.1 % below the exact incumbents, consistent with the measured ~0.8 % UC
optimism plus their gaps, and respects the exact runs' lower bounds.

Bounds figure regenerated with the new anchors
([tools/plot_coordination_bounds.py](tools/plot_coordination_bounds.py) —
freebatt-era anchors removed, treatment labelled `ucrelax` on the footer);
`MKT_ON_INC` is the log incumbent and is auto-replaced by `cost_results.csv`
when the runs land.

### 2026-08-02 02:00 — NodeMethod experiment armed; 2-week aggregation planned

**"More CPU" is not available — nothing is capped.** Verified: no `gurobi.env`,
no `Threads` parameter, Gurobi already permits 32 threads; the ucrelax legs use
**~2 cores** because dual-simplex node LPs are inherently serial (barrier phases
used ~9). Amdahl, not starvation.

**Armed** (`jobs/queue_ucrelax2.sh`, pid 2263349): after the ucrelax caps fire
(~03:17/03:24), rerun both gridvillage legs with `gurobi.env` = `NodeMethod 2`
(barrier node LPs — the parallel algorithm) + `MIPFocus 3` (push the bound),
warm-started, tag `ucrelax2`, 8 h caps. Tonight's ucrelax results stay intact.
The env file is created by the queue and removed on exit; no unrelated solves
should launch while it is active.

**Tomorrow, if the gap remains wide:** build a 2-week temporally-aggregated
variant (energy-preserving `Sub_Weights` rescale) — node LPs ~4× smaller, tree
actually explores — then **fix-and-verify**: fix the winning 780-binary connect
pattern on the full 8-week model and solve the resulting LP once (~80 min).
The final number then carries no aggregation caveat: it is the exact
full-resolution cost of a concrete plan, i.e. a true incumbent.

### 2026-08-02 02:30 — 2-week datasets prepped ahead of schedule, validated end to end

Built with the new [`tools/make_reduced_weeks.py`](tools/make_reduced_weeks.py)
(uncommitted; tests + commit packaging tomorrow): `timor__marketfix2w` and
`timor__marketfixnf2w`, both schema-valid.

**Selection** (deterministic, printed by the tool): the synthetic solar repeats
weekly — all 8 weeks share mean CF 0.1847 to 4 d.p. — so the stress criterion
fell back from min-solar to **peak-demand week** (week 7, 145.33 MW mean).
Representative week 0 chosen from the *opposite side* of the all-weeks mean, a
constraint added after the first build produced a +2.29 % energy residual (two
above-mean weeks cannot convexly reproduce annual energy). Weights 7,109/1,651
from the 2×2 hours+energy solve.

**Verification chain:** annual electric energy preserved to **+0.0002 %**
(integer `Sub_Weights` rounding); schema valid; and a full end-to-end solve —
the 2w `village` LP returns **$101.72300 M/yr** against the 8-week anchor's
$101.71759 M, a **0.005 %** difference. The reduced model reproduces the full
OFF economics almost exactly.

Standing caveat (in the tool docstring): the 2w variant is for **finding** the
connection pattern; quote only fix-and-verify numbers (fix the 780 binaries on
the full dataset, solve the LP once, ~80 min).

### 2026-08-02 02:33 — 2w batch launched; NodeMethod experiment stood down

User call: go straight to the 2-week path. The armed `ucrelax2` (NodeMethod 2)
queue was disarmed *before* it could write `gurobi.env` — its env file would
have applied to any solve launched from the repo root, contaminating the 2w
runs with experiment parameters. No env file was ever created; the ucr2 configs
remain in `jobs/` if the experiment is wanted later.

Launched (`jobs/sched_w2.sh`): `w2_nf_village` (completes the 2w OFF pair),
then `w2_fix_gridvillage` and `w2_nf_gridvillage` — all at **`mipgap 0.001`**
(±~$100k on a ~$100 M objective, affordable at 1/4 model size and the right
tolerance for a coordination delta in the tens of $M), warm-started, 4 h solver
caps, 5 h OS backstops. Running alongside the finishing ucrelax legs (caps
~03:17/03:24), which still deliver the full-model incumbent CSVs.

**Next after these land:** fix-and-verify — fix the 2w winner's 780
`vVIL_CONNECT` values on the full 8-week dataset, solve once as an LP, and
quote that number. The fixing mechanism does not exist yet (a small
`connect_pattern` config key or start-file hook); build it tomorrow.

### 2026-08-02 03:21 — the coordinated plan is coal substitution; carbon-neutral pair launched

**`ucr_marketfix_gridvillage` terminated at its 8 h cap** and wrote full CSVs:
final `Best objective 8.415449851127e+07, bound 5.990591381732e+07, gap
28.8144 %`. The $84.154 M incumbent's structure (village_build_summary):

| | islanded (OFF) | coordinated incumbent (ON) |
|---|---|---|
| Connected | 0 (by construction) | **746 of 780** |
| village solar | 360.70 MW | **39.34 MW** (−89 %) |
| village battery power | 148.51 MW | 31.21 MW |
| net grid→village supply | 0 | ~484 GWh/yr |
| new grid build | — | **none** |
| system CO₂ | ~753 kt/yr | **~1,102 kt/yr (+46 %)** |

**The ≥$17.6 M/yr coordination value at DMO prices is coal-substitution value**:
connect nearly everyone to the existing coal fleet's headroom, dismantle ~90 %
of the village solar build. "0 of 780 connect" (published) reverses to 746/780
once the grid has load, corrected costs, and a real battery — but the
cost-optimal plan is the *opposite* of a solar programme. Caveats: incumbent at
28.8 % gap (floor stands, pattern may shift); UC relaxed both legs; gross trade
churn partly degenerate at 0/0 prices (quote net flows only).

**Carbon-neutral coordination pair launched 03:26** (`jobs/sched_w2clean.sh`):
`timor__marketfix2w`, `clean`, `policy_scope: "system"`, **CO2_limit = 656,500 t**
(measured 2w islanded 653,278 + 0.5 % headroom), **RE_limit = 0.48** (measured
0.4872 − margin), relax_uc + exact_connect, warm start, mipgap 0.01, 4 h caps.
The question: what is coordination worth when it may neither out-emit nor be
less renewable than islanding? 2w OFF anchors used for the cap are themselves
measured (this section's table), closing the A4→D1 dependency the run plan
required.

### Reporting convention — one number, gap acknowledged (user decision, 2026-08-02)

Headline coordination values are quoted as a **single number computed from the
best feasible plan** (OFF − ON incumbent), annotated with the **achieved** gap:

> Coordination value: **$X M/yr** (from the best plan found; solver gap Y % —
> the true optimum may be higher, so this figure can only understate).

Rationale: the incumbent end of the bracket is a real, implementable plan; the
bound end is a hypothetical. Because the ON incumbent only improves, the quoted
number is conservative by construction. Bounds/interval presentation moves to
the appendix as the audit trail. Consistent with the house rule: achieved gap,
never the permitted `mipgap`.

### 2026-08-02 06:44 — 2w reference finals; figure pipeline shipped

**2w reference pair complete** (time-limited at their 4 h caps):

| leg | `Total_Costs` | achieved gap |
|---|---|---|
| w2_fix gridvillage | **83.03142** | 26.3251 % |
| w2_nf gridvillage | **83.03142** (identical to 8 s.f.) | 27.8142 % |

**One-number headline (per convention): 2w coordination = 101.72300 − 83.03142 =
$18.69 M/yr (gap 26.3 %, conservative)** — within 6 % of the full model's
$17.56 M/yr (gap 28.8 %). Cross-scale pattern agreement is strong: 2w connects
**733/780** with 40.4 MW village solar vs the full model's 746/780 with 39.3 MW.
The aggregation reproduces both the economics and the plan structure.

**Figure pipeline shipped** — five scripts, all reviewer-verified SHIP:
`plot_headline_coordination.py` (one-number convention; row 3 auto-upgrades when
the clean leg lands, floor parsed live from its log), `plot_cost_stack.py` (F1),
`plot_recipe_and_diesel.py` (F2+F3), `plot_diversity_panels.py` (F11; the
reviewer pass also identified the 1.8 % histogram tail as exactly the 5,411
fishing-archetype pairs), `plot_village_map.py` (F14; 627 of 780 locatable —
153 villages, 31.1 % of households, modelled but unmappable). Every must-carry
caveat from the figure plan is printed on the figures themselves.

Remaining in flight: `w2c_gridvillage` (carbon-neutral ON), cap ~07:30.

### Probe runs (verification, 2026-07-31)

| # | Date | Purpose | Island | Scenario | UC | Solver | `run_tag` | Result | Wall |
|---|---|---|---|---|---|---|---|---|---|
| P1 | 07-31 | pipeline smoke | timor_demo | gridvillage | exact | gurobi | `exactgb` | all 16 CSVs written | **79 s** |
| P2 | 07-31 | solver cross-check | timor_demo | gridvillage | exact | highs | `exacthi` | costs agree to 11 s.f. | — |
| P3 | 07-31 | shape smoke | timor_belu | gridvillage | relaxed | gurobi | `n3probe` | barrier converged, root bound 8.79196309e+06 | **96 s** |
| P4–P6 | 07-31 | regression gate | maluku, timor_demo, timor_belu | — | relaxed | highs | `reggate` | `REGRESSION_GATE_OK: 71 metric(s) unchanged` | **18 min** |
| P7 | 07-31 | wash-trade repro | timor_demo | gridvillage | exact | gurobi | `arb59` | import 59 / export 40 → village exported **12.3 MWh** | — |
| P8 | 07-31 | wash-trade repro | timor_demo | gridvillage | exact | gurobi | `arb0` | import **0** / export 40 → same village exported **1,324.8 MWh** (126×), cost $120k lower, exit 0 | — |
| P9–P10 | 07-31 | HiGHS/Gurobi degeneracy | timor_demo | gridvillage | exact | both | `washgb`,`washhi` | costs identical to 11 s.f.; per-village import differs **47 %**, export 308.7 vs 0.0 MWh | — |
| P11 | 07-31 | grid-only probe | timor__market | base | relaxed | highs | `gridonlyprobe` | **killed at 23 GB / 12.5 min** — site layer loads regardless of scenario | — |

Datasets built during verification (all gitignored):
`timor__diverse`, `timor__market`, `timor__era5`, `timor__market_era5`.
`timor__market` reported 682.1 GWh/yr, 124.1 MW peak, LF 0.63, schema OK.

### What to record per run

From [`hpc_handoff.md`](hpc_handoff.md), plus the two standing rules from
[`docs/scenario_design_timor.md`](docs/scenario_design_timor.md):

- `Total_Costs` from `cost_results.csv` (annual, $M)
- `Connected` count from `site_connection_results.csv`
- **the achieved MIP gap** from the solver log — never the permitted `mipgap`,
  which at 0.01 allows a ~$646k gap on a $64.6 M objective
- wall time and peak memory (the 780-village MILP high-water mark has never been
  profiled — read it off the first run before sizing anything concurrent)
- export runs: `Village_Export_Revenue`, `Total_Export_MWh`
- `clean` runs: `CO2_Emissions_Village`, and which `policy_scope` was used

Treat cost differences below **~$100** on a $64 M system as numerical noise.
All energy columns are already **annual** — the extractor applies the
representative-period sample weights; do not multiply by 8760/1344.

### Traps that make a run silently wrong

1. A scenario-YAML key outside `PASSTHROUGH_KEYS` (both `generate_jobs.py` and
   `generate_jobs_local.py`) never reaches `config.json`. The model solves at its
   default and the result CSVs look entirely normal.
2. Runs differing *only* by config keys share one results folder and overwrite
   each other unless `run_tag` is set. `sensitivity.py` sets it; hand-written
   configs do not.
3. Sweep axes are **multipliers on the base**, so `--param export_price=2` with a
   base of 0 gives 0. Pass a non-zero base (`--export-price 40`).
4. Nothing on plain `timor` can answer an export question (see above).
5. `tools/launcher.py` LP-relaxes expansion runs by default — use `run_model.jl`
   directly, or the job generators, for anything decision-grade.

---

## Verification before trusting any result

```bash
python3 -m pytest tests -q                    # solver-free
julia --project=. tests/verify_data_core.jl   # prints DATA_CORE_OK
tools/regression_gate.sh check                # 71 metrics, 3 cases, ~6 min
```

Note the gate's coverage boundary: all three cases hardcode `engine: dispatch`,
`relax_uc: true`, `solver: highs`, `clean: reference`, so it cannot see a
regression in capacity expansion, exact UC, or any `clean` policy constraint —
which is most of what this study exercises. Its cases are maluku, timor_demo and
timor_belu; `timor` itself is not covered.

| Date | `pytest` | `verify_data_core.jl` | `regression_gate.sh check` |
|---|---|---|---|
| 2026-07-31 | **104 passed**, 2.5 s | **`DATA_CORE_OK`** | `REGRESSION_GATE_OK`, 71 metrics unchanged, 18 min (run during verification) |

### 2026-07-31 — stage 0–2 authorised and started

**S2 scenario-YAML edits applied** (`scenario_timor.yml`, `scenario_timor_market.yml`):
added `solver: gurobi`, `lp_method: 2`, `relax_uc: false`, and an explicit
`export_price: 0.0`; changed the market file's `lp_method: -1` → `2`. Without the
solver key both files silently fall back to HiGHS, measured at >6.5 h on this
model without converging.

`tests/test_config_passthrough.py` stayed green (14 passed), and the generated
`jobs/village_timor_2030_reference/config.json` was checked key-by-key before the
solve was allowed to proceed — all six of `solver`, `lp_method`, `relax_uc`,
`import_price`, `export_price`, `mipgap` present and correct.

**Both authorised stages run at `import_price = 0` and `export_price = 0`.** The
trade variables therefore carry zero objective coefficient and the optimum is a
face, not a point. Costs, capacities and connection counts are well-determined;
**per-village trade volumes from stages 1 and 2 must not be published.**

Stage 1 (A1a) launched 18:57:20. Solver confirmed live: `Method = 2`,
`MIPGap 0.01`, `Crossover 0`, academic licence. Note `TimeLimit` is 259200 s
(3 days) and a timed-out run still exits 0 — the log must be grepped for
`reached the time limit` before any result is trusted.

**Prep for stages 4–6** (done while stage 1 solved):

| Change | File | Why |
|---|---|---|
| Added `--lp-method` (default `-1`, behaviour unchanged) and emitted `lp_method` from `base_config()` | [`tools/sensitivity.py`](tools/sensitivity.py) | `base_config()` omitted it entirely, so **every sweep ran at Gurobi `Method=-1` while its reference run used `Method=2`**. Not just ~9 min/solve slower — A3 is *differenced* against A1a, and on an optimum we know is degenerate at 0/0 prices two algorithms can return different vertices of the same optimal face. Stages 4–5 must pass `--lp-method 2` |
| Extracted `build_parser()` out of `main()` | [`tools/sensitivity.py`](tools/sensitivity.py) | Makes the flag surface and its defaults assertable without invoking a sweep |
| Added `test_base_config_carries_lp_method` | [`tests/test_sensitivity.py`](tests/test_sensitivity.py) | Pins the default at `-1`, pins `--lp-method 2` reaching the config, and asserts `lp_method` is in `PASSTHROUGH_KEYS`. Suite 104 → **105 passed** |
| New scenario file | [`scenario_timor_diverse.yml`](scenario_timor_diverse.yml) | Stage 6 (B1). `island_params` and `co2_limits` **must** carry the derived island name or `generate_jobs_local.py` aborts. Passes the passthrough guard; `timor__diverse` schema validated OK |

Commands for stages 4–6, corrected against the real parser (the plan's own
versions omit `--import-price 0`, over-count A5 by one point, and use `python`,
which does not exist here):

```bash
# Stage 4 — A3 ceiling. The mv is REQUIRED: the sweep's untagged base otherwise
# overwrites A1a's gridvillage results folder.
mv results/gridvillage_timor_2030_reference results/A1a_gridvillage
python3 tools/sensitivity.py run --island timor --year 2030 --scenario gridvillage \
    --solver gurobi --exact-uc --lp-method 2 --import-price 0 \
    --param connection_cost=0 --keep-going

# Stage 5 — A5 tariff sweep. 4 solves, not 5: build_plan() drops the x1.0 point
# as identical to base.
python3 tools/sensitivity.py run --island timor --year 2030 --scenario gridvillage \
    --solver gurobi --exact-uc --lp-method 2 \
    --import-price 59 --param import_price=0,0.5,1.5 --keep-going

# Stage 6 — B1 diversity.
python3 generate_jobs_local.py -s scenario_timor_diverse.yml -r run_model.jl \
    -o jobs --no-bootstrap
```
