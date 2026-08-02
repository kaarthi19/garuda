#!/usr/bin/env python3
"""Derive a reduced-representative-weeks variant of a dataset (default: 2 of 8).

Purpose: the 780-site coordination MILP has hour-long node LPs at 1,344 hours,
so branch-and-bound explores ~1 node/hour and never closes. A 336-hour variant
makes node LPs ~4x smaller (super-linearly cheaper), letting the tree actually
explore. The intended workflow is **fix-and-verify**: solve the reduced model to
a small gap, then fix its 780 vVIL_CONNECT values on the FULL dataset and solve
the resulting LP once — the final number is the exact full-resolution cost of a
concrete plan and carries no aggregation caveat.

    python3 tools/make_reduced_weeks.py data_indonesia/2030/timor__marketfix
    # -> data_indonesia/2030/timor__marketfix2w

Week selection (documented, deterministic):
- STRESS week: the lowest mean village-solar CF week — the week that sizes
  storage and backup. Dropping it would make the reduced model systematically
  optimistic about islanding.
- REPRESENTATIVE week: among the rest, the week whose (mean system power, mean
  solar CF) pair is closest (z-scored) to the all-weeks mean.

Weights: solve w_rep + w_str = 8760 and w_rep*P_rep + w_str*P_str = E_annual
(total grid + village electric energy), so total hours AND total system energy
are preserved exactly (to integer rounding of the loader's Int cast of
Sub_Weights). Heat energy is not separately matched; its residual is printed.
If the 2x2 solve goes negative the tool falls back to 4380/4380 and says so.

What is rewritten: the five 1,344-row time-series files (demand,
generators_variability, village_demand, village_demandheat,
village_generators_variability) sliced to the two weeks in chronological order,
r_id renumbered 1..336, demand.csv's hour column recomputed 0..167 per period,
Rep_Periods -> 2, Sub_Weights -> the two weights. `corresponding_week` keeps the
ORIGINAL week numbers as an audit trail. Everything else copies verbatim.

The reduced variant is for FINDING a connection pattern, not for quoting costs:
storage sizing on 2 weeks is not the 8-week sizing. Quote only fix-and-verify
numbers. Solver-free; requires pandas.
"""
import argparse
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOURS = 168
TS_FILES = ("demand.csv", "generators_variability.csv", "village_demand.csv",
            "village_demandheat.csv", "village_generators_variability.csv")


def _read(path):
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def pick_weeks(src):
    d = _read(os.path.join(src, "demand.csv"))
    vd = _read(os.path.join(src, "village_demand.csv"))
    vg = _read(os.path.join(src, "village_generators.csv"))
    vv = _read(os.path.join(src, "village_generators_variability.csv"))

    n_weeks = len(d) // HOURS
    zcols = [c for c in d.columns if c.startswith("demand_z")]
    vcols = [c for c in vd.columns if c.startswith("demand_")]
    solar_pos = vg.index[vg.technology == "solar"].to_numpy()  # 0-based == R_ID-1
    solar = vv.iloc[:, 1:].to_numpy()[:, solar_pos]            # col 1 dropped by loader

    grid = d[zcols].sum(axis=1).to_numpy()
    vill = vd[vcols].sum(axis=1).to_numpy()
    stats = []
    for w in range(n_weeks):
        s = slice(w * HOURS, (w + 1) * HOURS)
        stats.append(dict(week=w,
                          mean_power=float(grid[s].mean() + vill[s].mean()),
                          solar_cf=float(solar[s].mean())))
    st = pd.DataFrame(stats)

    # stress week: lowest solar CF — unless the profile repeats weekly (the
    # synthetic timor solar does: all weeks share one mean CF), in which case
    # the stressor is the peak-demand week instead.
    cf_varies = st.solar_cf.std() > 1e-9
    stress = int(st.solar_cf.idxmin()) if cf_varies else int(st.mean_power.idxmax())
    rest = st[st.week != stress]
    # the pair must BRACKET the all-weeks mean power, or no convex weighting can
    # reproduce annual energy (both weeks above the mean forces a +2%+ residual).
    # Prefer opposite-side candidates; fall back to all if none exist.
    mean_p = st.mean_power.mean()
    # STRICTLY opposite: a week sitting exactly on the mean would satisfy a
    # sign-inequality test but forces zero weight onto the stress week.
    opposite = rest[(rest.mean_power - mean_p)
                    * (st.mean_power[stress] - mean_p) < 0]
    pool = opposite if len(opposite) else rest
    std = st[["mean_power", "solar_cf"]].std().replace(0.0, 1.0)
    z = (pool[["mean_power", "solar_cf"]] - st[["mean_power", "solar_cf"]].mean()) / std
    rep = int(pool.week.iloc[int(np.argmin(np.hypot(z.mean_power, z.solar_cf).to_numpy()))])
    print(f"stress criterion: {'min weekly solar CF' if cf_varies else 'peak-demand week (solar CF identical across weeks)'}")

    # energy-preserving weights (2x2): hours and total electric energy both match
    P_rep, P_str = st.mean_power[rep], st.mean_power[stress]
    E_annual = 1095.0 * st.mean_power.sum()          # source annualisation
    if abs(P_rep - P_str) < 1e-9:
        w_rep = 4380
    else:
        w_rep = (E_annual - 8760.0 * P_str) / (P_rep - P_str)
    w_rep = int(round(w_rep))
    w_str = 8760 - w_rep
    fallback = not (0 < w_rep < 8760)
    if fallback:
        w_rep = w_str = 4380
    return sorted([(rep, w_rep), (stress, w_str)]), st, fallback, E_annual


def build(src, out, weeks):
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(src, out)
    rows = np.concatenate([np.arange(w * HOURS, (w + 1) * HOURS) for w, _ in weeks])

    for f in TS_FILES:
        df = _read(os.path.join(src, f))
        body = df.iloc[rows].reset_index(drop=True)
        if "r_id" in body.columns:
            body["r_id"] = np.arange(1, len(body) + 1)
        if "hour" in body.columns:
            body["hour"] = np.tile(np.arange(HOURS), len(weeks))
        # segment/period reference columns live in the first rows only: carry the
        # originals (they are shorter than the sliced body, so re-stamp them)
        for col, vals in (("Rep_Periods", [float(len(weeks))]),
                          ("Timesteps_per_Rep_Period", [float(HOURS)]),
                          ("Sub_Weights", [float(w) for _, w in weeks])):
            if col in body.columns:
                body[col] = np.nan
                body.loc[: len(vals) - 1, col] = vals
        for col in ("Voll", "Demand_Segment", "Cost_of_Demand_Curtailment_per_MW",
                    "Max_Demand_Curtailment"):
            if col in body.columns:
                ref = df[col].iloc[: (df[col].astype(str) != "").sum()]
                ref = df[col].dropna()
                body[col] = np.nan
                body.loc[: len(ref) - 1, col] = ref.to_numpy()
        body.to_csv(os.path.join(out, f), index=False)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="source dataset folder (e.g. data_indonesia/2030/timor__marketfix)")
    ap.add_argument("--suffix", default="2w")
    args = ap.parse_args(argv)

    src = args.src.rstrip("/")
    out = src + args.suffix
    weeks, st, fallback, E_annual = pick_weeks(src)

    print(f"source weeks:\n{st.round(4).to_string(index=False)}")
    print(f"selected: {[(w, int(wt)) for w, wt in weeks]}  (week, Sub_Weight)"
          + ("  [FALLBACK uniform weights]" if fallback else ""))
    build(src, out, weeks)

    # verification: annualised electric energy must match the source
    d, vd = _read(os.path.join(out, "demand.csv")), _read(os.path.join(out, "village_demand.csv"))
    zc = [c for c in d.columns if c.startswith("demand_z")]
    vc = [c for c in vd.columns if c.startswith("demand_")]
    sw = np.repeat([w for _, w in weeks], HOURS) / HOURS
    E_out = float((d[zc].sum(axis=1).to_numpy() * sw).sum()
                  + (vd[vc].sum(axis=1).to_numpy() * sw).sum())
    print(f"annual electric energy: source {E_annual/1e3:,.2f} GWh -> reduced {E_out/1e3:,.2f} GWh"
          f"  (residual {(E_out-E_annual)/E_annual*100:+.4f}%)")

    r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "validate_schema.py"), out],
                       capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[-200:])
    return 1 if r.returncode not in (0,) else 0


if __name__ == "__main__":
    sys.exit(main())
