# Demo walkthrough — Garuda on a laptop, HiGHS only

A ~10-minute sequence that runs the whole platform on the open-source **HiGHS**
solver — **no commercial licence** — on the small synthetic Timor case
(`timor_demo`, 4 villages, 2 zones). It is the demonstration to run for a
funder's technical partners before any wider commitment: every step below was
executed on a laptop and the runtimes are what was observed.

> Gurobi is **not** needed for anything here. It is an optional fast path for the
> exact unit-commitment MILP at full scale, which belongs on an HPC — see the
> note at the end.

## Setup (once)

```bash
pip install pandas numpy click pyyaml       # Python engines + tools
pip install matplotlib jinja2               # for the report's charts + PDF
julia --project=. bootstrap.jl              # installs Julia deps, checks HiGHS
```

The first Julia solve of a session pays a one-time precompile (a minute or two);
every solve after that is fast. All timings below are warm.

## 1. Instant screen — no solver (~0.5 s)

```bash
python tools/screening.py data_indonesia/2030/timor_demo
```

Merit-order arithmetic on the existing fleet: per-zone demand, renewable share,
emissions, operating cost, unserved energy. Runs on any laptop with Python.

## 2. Renewable resource & siting — no solver (~0.5 s)

```bash
python tools/re_resource.py data_indonesia/2030/timor_demo
```

Per-zone and per-site developable solar/wind MW, capacity factor and annual
potential — the ceilings the model builds against. The GIS pipeline behind these
numbers, and the Timor figures, are in
[`case_study_timor.md`](case_study_timor.md).

## 3. Solve a coordinated scenario — dispatch LP on HiGHS (~20 s)

```bash
python tools/launcher.py --island timor_demo --year 2030 --scenario gridvillage \
    --clean reference --engine dispatch --run
```

The launcher validates the inputs, previews the problem size, scaffolds the
config, and runs the LP-relaxed dispatch on HiGHS. The solve itself is **under a
second**; the ~20 s is Julia startup and first-call compilation. Results land in
`results/gridvillage_timor_demo_2030_reference/`.

## 4. Turn results into a shareable report (~1 s)

```bash
python tools/report.py results/gridvillage_timor_demo_2030_reference
```

Writes a self-contained `report.html` (and `report.pdf` if matplotlib/jinja2 are
installed): headline metrics, generation/capacity/cost charts, per-zone
reliability. This is the artifact to hand a non-modeller.

## 5. The coordination value — the headline number (~1–2 min)

```bash
python tools/coordination_value.py run --island timor_demo --year 2030 --pair village
```

Solves the standalone (`village`) and coordinated (`gridvillage`) scenarios with
the LP-relaxed **expansion** engine on HiGHS and reports the delta: system cost,
diesel, emissions and unserved energy avoided by planning village solar and the
grid together, plus how many villages connect. Writes `coordination_value.csv`
and `coordination_value.md` into the coordinated run's directory. See
[`coordination_value.md`](coordination_value.md) for the metric definitions and
caveats.

> **Read the result honestly.** Each demo village carries a stylised distance to
> the nearest substation (wini 3 km → raijua 90 km), priced into its annual
> connection cost (`village_connection.csv`, ~$9k/yr → ~$240k/yr). At these
> distances and demo costs the model keeps **all four villages islanded** —
> solar+storage beats grid imports plus an MV feeder — so the coordination value
> is ~0, and the per-village *decision* (and the price at which it would flip) is
> the real output. For contrast: with the connection file removed (connection
> free — the old default), all four villages connect and the value looks bigger;
> the distance pricing is what makes the number defensible rather than
> optimistic. The interesting version of this question — hundreds of real
> villages, some MW-scale and half a kilometre from a substation (real Timor:
> 780 villages, median 17 km, min 0.6 km) — is exactly the Phase-1
> demonstration proposed in the concept note.

## What needs more than a laptop

- **Exact unit-commitment expansion (MILP) at full island scale.** HiGHS can do
  it but is slow; the fast path is Gurobi on an HPC. Batch/HPC job generation is
  in `generate_jobs.py` (SLURM; add `--submit`). For laptop exploration, the
  `relax_uc` LP relaxation used above is within ~0.8 % of the exact cost on this
  case (measured — `tools/uc_relaxation_gap.jl`).
- **The GIS siting pipeline** needs external raster/vector layers (set
  `GARUDA_GIS_DIR`); the per-village CSVs it produces are already in the repo, so
  the model runs above need none of it.
