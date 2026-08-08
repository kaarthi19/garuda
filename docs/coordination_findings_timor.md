# Coordination value on the full Timor case — the measured result

[`demo_walkthrough.md`](demo_walkthrough.md) closes by naming the open question:
the four-village demo shows a coordination value of ~0, and the interesting
version of the question — hundreds of real villages, some a few hundred metres
from a substation and some tens of kilometres away — is the Phase-1
demonstration. This is that measurement. (Measured on the shipped dataset:
substation distance `hubdist_km` has a median of **20.4 km**, min 0.56 km, max
61.9 km, over the 627 of 780 villages that carry coordinates.)

**The result: on 780 real Timor villages, the island-wide coordination value is
at most $2,569/yr — 0.004 % of a $64.6 M/yr system — and at full interconnection
cost no village connects at all.** A zero is a finding, not a failed run. But it
is a zero about a *specific* question, and the scope matters more than the number;
see [Reading it honestly](#reading-it-honestly).

## The question, precisely

Does interconnecting Timor's 780 villages (`gridvillage`) beat leaving each as a
standalone solar + storage + diesel microgrid (`village`)?

| | |
|---|---|
| Case | Timor: 780 villages across 4 kabupaten (TTS 278, Kupang 228, TTU 193, Belu 81), 1344 h (8 representative weeks), 2030, `reference` |
| Village demand | 436,995 households, **544 GWh/yr** weighted, coincident peak 128.2 MW (LF 48 %) |
| Village solar | ~$46/MWh LCOE ($69,965/MW-yr all-in at CF 0.175) |
| Interconnection | `village_connection.csv`, from `hubdist_km`: median $45,184/yr, min **$2,493/yr**, max $165,088/yr |
| Village size | mean peak 0.164 MW, median 0.118 MW |
| Solver | Gurobi, exact UC MILP (`relax_uc: false`) |

## What was measured

Five experiments. All solved to proven optimality (see
[Optimality](#optimality-is-not-in-question)).

| # | Lever | Result |
|---|---|---|
| 1 | Baseline, interconnection at full cost | OFF = ON = **$64.63141317 M/yr**; **0 of 780 connect** |
| 2 | Interconnection made **free** (`connection_cost=0`) | saves **$2,568.8/yr = 0.004 %**; all 780 connect but only **7.75 MWh** is traded island-wide, all year |
| 3 | Half the villages moved to a **midday** load peak | free-connection saving falls to **$418.98/yr = 0.0007 %**; **2.5 MWh** traded — *less* than the homogeneous case |
| 4 | Per-village **GIS solar land caps** (174–4692 MW) | **non-binding** (village peak ~0.16 MW); identical to #1 to 10 s.f.; 0 of 780 |
| 5 | 2×2: {synthetic, ERA5 solar} × {OFF, ON}, all with a costed 4 h battery | synthetic **$70.88216508 M**, diesel 2.9 % of load; ERA5 **$73.61193330 M**, diesel 16.9 %; coordination ≈0 in both, 0 of 780 |

Reproduce #2 and #3 as one command each:

```bash
# free interconnection — the upper bound on coordination value
python tools/sensitivity.py run --island timor --year 2030 --scenario gridvillage \
    --solver gurobi --exact-uc --param connection_cost=0

# the load-shape-diversity counterfactual
python -m tools.ntt.make_diverse_demand --dataset data_indonesia/2030/timor
```

## Why the ceiling holds at any connection cost

The `$2,569/yr` figure is more robust than it looks, and it does not depend on the
interconnection cost data being right:

1. In the `village` (OFF) run, `village_connection.csv` is read but its values
   **never enter the objective** — `eVILConnectCost` is hard-zero when
   `Grid = false`. And experiment #2 zeroes them outright. So the $2,569/yr is
   measured in a world where connecting is free.
2. `gridvillage` cost is monotone non-decreasing in `Cost_per_yr`. Charging
   anything for interconnection can only make the coordinated plan worse.

So **$2,569/yr is an upper bound on the island-wide coordination value at any
interconnection cost** — *at the import price those runs used*, see the caveat
below. For scale: garuda's *cheapest single* village interconnection is
**$2,493/yr**. The entire island-wide benefit of coordinating 780 villages is
worth about one village's cheapest connection.

> ### The ceiling is conditional on a tariff that should not have been there
>
> Every one of these runs charged `import_price = 59 $/MWh` on each MWh a village
> imported. In a single central-planner cost minimisation that is hard to justify,
> for two reasons that compound:
>
> - **On this dataset the charge has no offsetting resource cost at all.** With
>   `demand_z1 = 0`, export must equal import, so the grid's generation *nets to
>   zero* when villages trade with each other. The $59 was a pure penalty on
>   inter-village sharing — the exact behaviour being measured — not a cost of
>   anything.
> - **Where the grid does generate** (a dataset with real grid load), the fuel and
>   O&M are already in the objective as `eVariableCostsGrid`. A tariff on top
>   counts the same MWh twice.
>
> $59 is also an **industrial** tariff; PLN household rates are roughly $26/MWh on
> the subsidised lifeline and ~$90/MWh non-subsidised.
>
> **What this means for the number above.** The ceiling was measured with
> connection made free but the transfer charge still in force, so it bounds
> coordination value *under that tariff*, not in general. The monotonicity
> argument in `Cost_per_yr` still holds — the tariff is a separate axis it says
> nothing about. The Timor scenario files now set `import_price: 0`, and
> an `import_price` sweep (`tools/sensitivity.py`) measures it.
>
> **Do not quote the "one village's cheapest connection" line without this caveat**
> until A5 has run. If coordination value rises materially at `import_price = 0`,
> the published null was in part an artifact of the tariff rather than a fact about
> Timor's geography.

## The result that is not zero

Experiment #5's real finding is about **reliability**, not coordination. Holding
everything else fixed and swapping synthetic clear-sky solar for real ERA5 solar:

| | synthetic | ERA5 |
|---|---:|---:|
| Diesel share of village load | 2.9 % | **16.9 %** |
| Firm diesel capacity | 6.7 MW | **24.7 MW** |
| System cost | $70.88 M/yr | $73.61 M/yr (**+$2.7 M**) |

Non-served energy is **0** in every run. The synthetic profile was hiding diesel's
true backup role: with real weather, diesel is doing 6× more work. Anyone sizing
village systems on a clear-sky profile is under-building backup.

## Optimality is not in question

Configs set `mipgap: 0.01`, which *permits* a $646k gap on a $64.6 M objective —
easily enough to hide a coordination result. It did not: every `gridvillage` solver
log reports `best bound == best objective` to 13 significant digits, **achieved
gap 0.0000 %**. The permitted tolerance was never used.

Two habits follow, and they apply to any future run here:

- **Report the achieved gap**, not the permitted one. Citing `mipgap` proves
  nothing about the run you did.
- **Treat differences below ~$100 as numerical noise.** Experiment #1's $0.09 and
  #5's $0.05 gaps between OFF and ON are indistinguishable from zero; #2's $2,569
  and #3's $419 are real.

## Reading it honestly

**This measured village↔village sharing, not village→grid sales.** In the `timor`
dataset `demand_z1 = 0` for all 1344 hours, and the grid bus has no storage, so
the zonal balance forces `Σ village export ≤ Σ village import` in every hour
(confirmed empirically: export = import to 4 d.p.). Coordination here could only
ever mean one village's surplus serving another's deficit. It says **nothing**
about whether villages could profitably sell into the Timor grid — that question
needs a grid load first
([`ntt_data_integration.md` §6a](ntt_data_integration.md#6a-giving-the-grid-bus-a-real-load-build_grid_demandpy)),
and asking it on plain `timor` measures a data artifact.

**"Why zero" is still under-determined.** Two mechanisms are entangled and were
never separated:

1. **Solar synchrony plus cheap storage** — every village's PV peaks together, so
   there is little to trade, and a battery is cheaper than a wire.
2. **A one-sided transfer tax** — `eGridImportCosts` charges the importing village
   $59/MWh with no offsetting export credit at `export_price = 0`, while the grid
   must physically generate the imported MWh (charged again in
   `eVariableCostsGrid`). Inter-village transfers are penalised twice by
   construction.

Experiment #3 is suggestive — adding load diversity made trade *fall*, which is
hard to explain by synchrony alone — but it is not decisive. Mechanism 2 is now
directly testable rather than merely suspected: set `import_price` to 0 and
re-measure with an `import_price` sweep. **Do not publish
solar synchrony as the cause** until a sweep of `export_price` on plain `timor`
separates the two (raising `export_price` removes the tax without creating a
buyer, so the difference against the same sweep on a dataset *with* grid load
isolates each effect).

**The stressors were never applied together.** The free-connection runs (#2, #3)
exist only on the synthetic-solar, free-battery dataset. There is no
free-connection run on the ERA5 or costed-battery datasets. The headline claim
rests on that gap being immaterial; one run closes it.

**Numbers you should not quote directly:**

- **The energy and emissions figures above were read off the *old* reporting
  path, and two defects in it have since been fixed.** Both were reporting bugs,
  not physics — no cost or capacity result moved — but they change what the CSVs
  say, so old and new result folders are not directly comparable:
  - Energy columns were raw sums over the 1344 modelled hours, i.e. the sample
    rather than the year — **6.518× low on Timor**. They are now weighted by
    `sample_weight` and are annual. (On a non-uniform-weight dataset like maluku
    the correction is 6.473×, and no single factor could have produced it.)
  - `CO2_Emissions_Village` was identically **0** because it summed only over
    `VIL_UC`, the `Commit=1` subset — and every real Timor village diesel is
    `Commit=0`. It now covers all site generators. Measured on `timor_belu`: 0 →
    **54,067 tCO₂/yr**, which matches generation × heat rate × fuel carbon content
    to the tonne.
  - `Grid_REShare` was `NaN` (renewable grid generation over *zero* grid demand).
    It still reports `NaN` — the ratio genuinely is undefined here — but the model
    no longer builds NaN coefficients from it, and a `clean` run at grid scope now
    fails with an explanation instead of handing the solver nonsense.
- **Experiments #1–#5 predate two changes in this repo.** They were run against
  an older `village_connection.csv` (median $95,822/yr vs today's $45,184) and
  before village battery **power** was priced (`Inv_Cost_per_MWyr` 0 → 30001
  $/MW-yr; see the modification log in
  [`DATA_PROVENANCE.md`](../data_indonesia/DATA_PROVENANCE.md)). The $2,569/yr
  ceiling is invariant to both, for the reasons above. **"0 of 780 connect at full
  cost" is not**, and both changes push against it: interconnection is now roughly
  half as expensive, and islanding is now more expensive because battery power
  costs money. Both make connecting more attractive, so this is the one statement
  that must be re-measured on current data before it is published. Two runs
  (`village` and `gridvillage` at full cost, Gurobi, exact UC) settle it.

## What this does not say

- Not that interconnection is worthless in general — Timor's villages are small
  (mean peak 0.16 MW), similar, and far apart (median 17 km). A denser, more
  heterogeneous system is a different question.
- Not that grid extension is the wrong policy — this compares *coordinated
  planning* against *islanded planning*, not electrification against no
  electrification.
- Not a welfare result. See the scope limits in
  [`coordination_value.md`](coordination_value.md#definition).

## Related

- [`coordination_value.md`](coordination_value.md) — the tool and the definition.
- [`sensitivity.md`](sensitivity.md) — the `connection_cost` and `connect_cap` axes
  used above.
- [`ntt_data_integration.md`](ntt_data_integration.md) — where the Timor dataset
  comes from, and how to give the grid bus a real load.
- [`solar_resource_era5.md`](solar_resource_era5.md) — the ERA5 solar profiles
  behind experiment #5, and their resolution caveat.
