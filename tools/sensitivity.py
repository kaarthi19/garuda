#!/usr/bin/env python3
"""Sensitivity sweeps — how robust is a plan to the uncertain inputs?

Perturbs a scenario's uncertain parameters around the base case, solves each
variant, and reports how the headline numbers (cost, CO₂, RE shares, unserved
energy, connections) move. One-at-a-time by default; full grid opt-in.

    # fuel price ±20%, demand ±10%, solar CF −10%, one-at-a-time (base + 5 runs):
    python tools/sensitivity.py run --island timor_demo --year 2030 --scenario gridvillage \
        --param fuel=0.8,1.2 --param demand=0.9,1.1 --param solar_cf=0.9

    # every combination instead (2x2x2 = 8 runs + base):
    ... --param fuel=0.8,1.2 --param demand=0.9,1.1 --param solar_cf=0.9,1.1 --full-grid

Two kinds of axis, both expressed as multipliers on the base:

- **Dataset axes** (`fuel`, `demand`, `solar_cf`, `connection_cost`,
  `connect_cap`) copy the input folder to an auditable sibling variant — e.g.
  `data_indonesia/2030/timor_demo__fuel1.2/` — and scale the relevant CSV columns
  there (fuel: `fuels_data.csv::Cost_per_MMBtu`; demand: every `demand_z*` and
  site demand column; solar_cf: every solar resource's availability column,
  clipped to [0,1]; connection_cost: `*_connection.csv::Cost_per_yr`;
  connect_cap: `*_connection.csv::Max_Connect_MW`). Variants are plain datasets:
  they pass `validate_schema.py` and any tool can inspect them. They are derived
  artifacts, gitignored (`data_indonesia/*/*__*/`).
- **Config axes** (`import_price`, `export_price`) need no dataset copy — the
  multiplier applies to the base value in the run's `config.json`. Note the
  multiplier is applied to the *base* value, so an axis whose base is `0`
  (`export_price` by default) stays 0 at every point and the sweep reads as
  perfectly flat — pass a non-zero `--export-price` to sweep it.

Each run solves through the normal pipeline (`run_model.jl`; LP-relaxed
expansion on HiGHS by default, same as the demo walkthrough) into the standard
results folders, so every variant result is a first-class run — reportable with
`tools/report.py`, comparable with `tools/coordination_value.py`. A dataset-axis
run is named after its variant dataset
(`results/<scenario>_<island>__<tag>_<year>_<clean>/`); a config-axis run reuses
the base dataset and is separated by a `run_tag` suffix instead
(`results/<scenario>_<island>_<year>_<clean>__<tag>/`).

Outputs: `results/sensitivity_<scenario>_<island>_<year>_<clean>/`
`sensitivity_results.csv` (one row per run × headline metrics) and
`sensitivity_results.md` (the base row, per-axis ranges, and which axis moves
each metric most). Runs on Python + pandas; solving needs Julia + HiGHS.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import shutil
import subprocess
import sys

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    print("sensitivity requires pandas", file=sys.stderr)
    sys.exit(3)

try:
    from tools.coordination_value import load_metrics
    from tools.validate_schema import validate_dataset
except ImportError:  # pragma: no cover
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from coordination_value import load_metrics
    from validate_schema import validate_dataset

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATASET_AXES = ("fuel", "demand", "solar_cf", "connection_cost", "connect_cap")
CONFIG_AXES = ("import_price", "export_price", "battery_duration_h")
AXES = DATASET_AXES + CONFIG_AXES

# headline metrics carried into the summary (key in load_metrics -> label, unit)
METRICS = [
    ("cost.Total_Costs",       "Total_Costs",        "M$/yr"),
    ("CO2_Emissions",          "CO2_Emissions",      "tCO2/yr"),
    ("Grid_REShare",           "Grid_REShare",       "share"),
    ("System_REShare",         "System_REShare",     "share"),
    ("grid_nse_mwh",           "Grid_NSE",           "MWh/yr"),
    ("site_nse_mwh",           "Village_NSE",        "MWh/yr"),
    ("villages_connected",     "Villages_connected", "count"),
    ("site_solar_built_mw",    "Village_solar_built","MW"),
]


def _read(path):
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def _write(df, path):
    df.to_csv(path, index=False)


# ------------------------------------------------------------- perturbations

def perturb_fuel(folder, mult):
    """Scale every fuel's Cost_per_MMBtu (the literal 'None' fuel stays 0)."""
    p = os.path.join(folder, "fuels_data.csv")
    f = _read(p)
    mask = f["Fuel"].astype(str) != "None"
    f.loc[mask, "Cost_per_MMBtu"] = pd.to_numeric(f.loc[mask, "Cost_per_MMBtu"],
                                                  errors="coerce") * mult
    _write(f, p)


def perturb_demand(folder, mult):
    """Scale zonal and site electricity demand columns (heat untouched)."""
    for name in ("demand.csv", "site_demand.csv", "village_demand.csv", "ip_demand.csv"):
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            continue
        d = _read(p)
        cols = [c for c in d.columns if c.startswith("demand_")]
        for c in cols:
            d[c] = pd.to_numeric(d[c], errors="coerce") * mult
        _write(d, p)


def perturb_solar_cf(folder, mult):
    """Scale solar availability columns (clipped to [0,1]) in both layers."""
    pairs = [("generators.csv", "generators_variability.csv"),
             ("site_generators.csv", "site_generators_variability.csv"),
             ("village_generators.csv", "village_generators_variability.csv"),
             ("ip_generators.csv", "ip_generators_variability.csv")]
    for gen_name, var_name in pairs:
        gp, vp = os.path.join(folder, gen_name), os.path.join(folder, var_name)
        if not (os.path.isfile(gp) and os.path.isfile(vp)):
            continue
        g = _read(gp)
        if "technology" not in g.columns or "Resource" not in g.columns:
            continue
        solar = set(g.loc[g["technology"].astype(str).str.lower() == "solar", "Resource"].astype(str))
        if not solar:
            continue
        v = _read(vp)
        for c in v.columns:
            if c in solar:
                v[c] = (pd.to_numeric(v[c], errors="coerce") * mult).clip(0.0, 1.0)
        _write(v, vp)


CONNECTION_FILES = ("site_connection.csv", "village_connection.csv", "ip_connection.csv")


def _perturb_connection(folder, mult, column):
    """Scale one column of whichever connection file the dataset uses."""
    for name in CONNECTION_FILES:
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            continue
        c = _read(p)
        if column not in c.columns:
            continue
        c[column] = pd.to_numeric(c[column], errors="coerce") * mult
        _write(c, p)


def perturb_connection_cost(folder, mult):
    """Scale every site's grid-interconnection Cost_per_yr (Max_Connect_MW untouched).

    This is the connect-vs-island price. `connection_cost=0` makes interconnection
    free, which is the upper bound on coordination value: whatever the coordinated
    plan saves when the connection itself costs nothing, it can never save more.
    """
    _perturb_connection(folder, mult, "Cost_per_yr")


def perturb_connect_cap(folder, mult):
    """Scale every site's Max_Connect_MW (Cost_per_yr untouched).

    Interconnection is sized at `CONNECT_MAX_FACTOR` (1.5) x the site's *own* peak
    demand (tools/ntt/costs.py), which on timor leaves a mean of only ~0.07 MW of
    headroom above peak — so a village cannot export much however much solar it
    builds, and an export study run at the shipped cap measures a sizing assumption
    rather than economics. Sweeping this axis is how you separate the two.

    Note the shipped `Cost_per_yr` depends only on distance, not on MW, so scaling
    the cap alone buys extra export capacity for free. Pair it with
    `connection_cost` (or add an MW term to the cost) before reading the result as
    a business case.
    """
    _perturb_connection(folder, mult, "Max_Connect_MW")


PERTURB = {"fuel": perturb_fuel, "demand": perturb_demand, "solar_cf": perturb_solar_cf,
           "connection_cost": perturb_connection_cost, "connect_cap": perturb_connect_cap}


def make_variant(data_root, year, island, changes):
    """Copy the base dataset and apply dataset-axis multipliers; return island name."""
    tag = "_".join(f"{k}{v:g}" for k, v in changes)
    variant = f"{island}__{tag}"
    src = os.path.join(data_root, str(year), island)
    dst = os.path.join(data_root, str(year), variant)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for axis, mult in changes:
        PERTURB[axis](dst, mult)
    return variant


# -------------------------------------------------------------------- plans

def build_plan(params, full_grid):
    """[(run_tag, {axis: mult})] — base first; OAT or full cartesian.

    In full-grid mode each axis implicitly includes the base multiplier 1.0,
    so partial combinations (e.g. fuel perturbed, demand at base) are covered.
    """
    plan = [("base", {})]
    if full_grid:
        axes = sorted(params)
        levels = [sorted(set(params[a]) | {1.0}) for a in axes]
        for combo in itertools.product(*levels):
            changes = {a: m for a, m in zip(axes, combo) if m != 1.0}
            if not changes:
                continue
            tag = "_".join(f"{a}{m:g}" for a, m in sorted(changes.items()))
            plan.append((tag, changes))
    else:
        for axis in sorted(params):
            for mult in params[axis]:
                if mult == 1.0:
                    continue
                plan.append((f"{axis}{mult:g}", {axis: mult}))
    return plan


# --------------------------------------------------------------------- runs

def base_config(args):
    return {
        "island": args.island, "year": str(args.year), "scenario": args.scenario,
        "clean": args.clean, "CO235reduction": False, "BAUCO2emissions": 0.0,
        "CO2_limit": float(args.co2_limit), "RE_limit": float(args.re_limit),
        "engine": args.engine, "relax_uc": not args.exact_uc, "solver": args.solver,
        "mipgap": 0.01, "import_price": float(args.import_price),
        "export_price": float(args.export_price), "policy_scope": args.policy_scope,
        "battery_duration_h": float(args.battery_duration_h),
    }


def run_one(cfg, results_root):
    # Mirrors the results-folder name built in functions/preflight.jl (including
    # the optional run_tag suffix) so the `<name>.config.json` sidecar stays
    # paired with its run — coordination_value.load_metrics finds the sidecar by
    # the run folder's basename.
    tag = str(cfg.get("run_tag", "")).strip()
    name = (f"{cfg['scenario']}_{cfg['island']}_{cfg['year']}_{cfg['clean']}"
            + (f"__{tag}" if tag else ""))
    cfg_path = os.path.join(results_root, name + ".config.json")
    os.makedirs(results_root, exist_ok=True)
    with open(cfg_path, "w") as fh:
        json.dump(cfg, fh, indent=2)
    cmd = ["julia", "--project=.", "run_model.jl", "--config", cfg_path]
    rc = subprocess.run(cmd, cwd=REPO_ROOT).returncode
    return rc, os.path.join(results_root, name)


def collect(run_dir, data_root):
    meta, m, _notes = load_metrics(run_dir, data_root)
    row = {}
    for key, label, _unit in METRICS:
        if key in m:
            row[label] = m[key]
    return row


# ------------------------------------------------------------------ summary

def summarise(df, out_dir):
    csv_path = os.path.join(out_dir, "sensitivity_results.csv")
    df.to_csv(csv_path, index=False)

    base = df[df.run == "base"].iloc[0]
    lines = ["# Sensitivity sweep", "",
             f"{len(df)} runs (base + {len(df) - 1} perturbations). "
             "Multipliers apply to the base value of each axis.", "",
             "| run | " + " | ".join(l for _, l, _ in METRICS if l in df.columns) + " |",
             "|---|" + "---|" * sum(1 for _, l, _ in METRICS if l in df.columns)]
    for _, r in df.iterrows():
        cells = [f"{r[l]:,.3f}" if isinstance(r.get(l), float) else str(r.get(l, ""))
                 for _, l, _ in METRICS if l in df.columns]
        lines.append(f"| {r.run} | " + " | ".join(cells) + " |")

    lines += ["", "## Ranges and the most influential axis", ""]
    pert = df[df.run != "base"]
    for _key, label, unit in METRICS:
        if label not in df.columns or not len(pert):
            continue
        vals = pd.to_numeric(pert[label], errors="coerce")
        if vals.isna().all():
            continue
        lo, hi = float(vals.min()), float(vals.max())
        # run that moves this metric furthest from base (if anything moved)
        dev = (vals - float(base[label])).abs()
        if not dev.notna().any() or float(dev.max()) == 0.0:
            lines.append(f"- **{label}** ({unit}): base {base[label]:,.3f} — "
                         "unchanged across the sweep")
            continue
        top = pert.loc[dev.idxmax(), "run"]
        lines.append(f"- **{label}** ({unit}): base {base[label]:,.3f}, "
                     f"range {lo:,.3f} – {hi:,.3f}; largest move: `{top}`")

    lines += ["", "_Every variant is a full run under "
              "`results/<scenario>_<island>__<tag>_<year>_<clean>/`; dataset "
              "variants live beside the base under `data_indonesia/<year>/` "
              "and pass the schema validator._", ""]
    md_path = os.path.join(out_dir, "sensitivity_results.md")
    with open(md_path, "w") as fh:
        fh.write("\n".join(lines))
    return csv_path, md_path


# ---------------------------------------------------------------------- cli

def parse_params(pairs):
    params = {}
    for p in pairs:
        if "=" not in p:
            raise SystemExit(f"--param must look like axis=0.8,1.2 (got {p!r})")
        axis, vals = p.split("=", 1)
        axis = axis.strip()
        if axis not in AXES:
            raise SystemExit(f"unknown axis {axis!r}; choose from {AXES}")
        params[axis] = [float(v) for v in vals.split(",") if v.strip()]
    return params


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="build variants, solve them, summarise")
    r.add_argument("--island", required=True)
    r.add_argument("--year", default="2030")
    r.add_argument("--scenario", default="gridvillage")
    r.add_argument("--clean", default="reference", choices=("reference", "clean"))
    r.add_argument("--engine", default="expansion", choices=("expansion", "dispatch"))
    r.add_argument("--solver", default="highs", choices=("highs", "gurobi"))
    r.add_argument("--exact-uc", action="store_true",
                   help="exact UC MILP per run (default: relax_uc LP, licence-free)")
    r.add_argument("--param", action="append", default=[],
                   help=f"axis=multipliers, e.g. fuel=0.8,1.2 (axes: {', '.join(AXES)})")
    r.add_argument("--full-grid", action="store_true",
                   help="every combination of the multipliers (default: one-at-a-time)")
    r.add_argument("--import-price", type=float, default=59.0)
    r.add_argument("--export-price", type=float, default=0.0)
    r.add_argument("--battery-duration-h", type=float, default=0.0,
                   help="base fixed site-storage duration in hours (0 = power/energy "
                        "co-optimised); pass a non-zero base to sweep it")
    r.add_argument("--policy-scope", default="grid", choices=("grid", "system"))
    r.add_argument("--co2-limit", type=float, default=1.0e12)
    r.add_argument("--re-limit", type=float, default=0.34)
    r.add_argument("--data-root", default=os.path.join(REPO_ROOT, "data_indonesia"))
    r.add_argument("--keep-going", action="store_true",
                   help="continue the sweep if one run fails (it is dropped from the summary)")
    args = ap.parse_args(argv[1:])

    params = parse_params(args.param)
    if not params:
        raise SystemExit("give at least one --param axis=multipliers")
    # A config axis is a multiplier on the base config value, so sweeping one
    # whose base is 0 gives 0 at every point: the sweep runs, costs hours, and
    # reads as perfectly flat. Refuse it rather than report a fake null.
    zero_base = sorted(a for a in params
                       if a in CONFIG_AXES and float(base_config(args).get(a, 0.0)) == 0.0)
    if zero_base:
        flags = ", ".join("--" + a.replace("_", "-") for a in zero_base)
        raise SystemExit(
            f"axis {zero_base} has a base value of 0, and the multipliers apply to the "
            f"base — every point would be 0 and the sweep would look flat. Pass a "
            f"non-zero base ({flags}) or drop the axis.")
    plan = build_plan(params, args.full_grid)
    n_dataset_variants = sum(1 for _t, ch in plan if any(a in DATASET_AXES for a in ch))
    print(f"== sensitivity sweep — {args.scenario} {args.island} {args.year} ({args.clean}) ==")
    print(f"  {len(plan)} runs (base + {len(plan) - 1}); "
          f"{n_dataset_variants} dataset variant(s); engine {args.engine} "
          f"({'exact UC' if args.exact_uc else 'relax_uc LP'}) on {args.solver}")

    results_root = os.path.join(REPO_ROOT, "results")
    rows = []
    for tag, changes in plan:
        cfg = base_config(args)
        ds_changes = [(a, m) for a, m in sorted(changes.items()) if a in DATASET_AXES]
        cfg_changes = {a: m for a, m in changes.items() if a in CONFIG_AXES}
        for axis, mult in cfg_changes.items():
            cfg[axis] = round(cfg[axis] * mult, 6)
        # A config-axis variant reuses the base dataset, so its results folder
        # would collide with the base run's (and with every other config-axis
        # point) — each run would overwrite the last and the summary would report
        # one run eight times. run_tag suffixes the folder to keep them distinct.
        if cfg_changes:
            cfg["run_tag"] = "_".join(f"{a}{m:g}" for a, m in sorted(cfg_changes.items()))
        if ds_changes:
            variant = make_variant(args.data_root, args.year, args.island, ds_changes)
            errors, _w = validate_dataset(os.path.join(args.data_root, str(args.year), variant))
            if errors:
                raise SystemExit(f"variant {variant} failed schema validation: {errors[:3]}")
            cfg["island"] = variant
        print(f"\n=== [{tag}] solving {cfg['scenario']}_{cfg['island']}_{cfg['year']}_{cfg['clean']} ===")
        rc, run_dir = run_one(cfg, results_root)
        if rc != 0:
            msg = f"run {tag!r} exited {rc}"
            if args.keep_going:
                print(f"  WARNING: {msg} — dropped from the summary", file=sys.stderr)
                continue
            raise SystemExit(msg)
        row = {"run": tag}
        row.update({a: m for a, m in changes.items()})
        row.update(collect(run_dir, args.data_root))
        rows.append(row)

    df = pd.DataFrame(rows)
    out_dir = os.path.join(results_root,
                           f"sensitivity_{args.scenario}_{args.island}_{args.year}_{args.clean}")
    os.makedirs(out_dir, exist_ok=True)
    csv_path, md_path = summarise(df, out_dir)
    print(f"\n  wrote {csv_path}\n  wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
