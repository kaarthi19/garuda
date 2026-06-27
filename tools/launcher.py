#!/usr/bin/env python3
"""Guided validation + run launcher for the garuda zonal model (Phase 5).

A non-expert on-ramp for a single run: it (1) validates the input schema, (2)
previews the scenario size — zones, generators, representative hours, the implied
problem dimensions — and a rough ETA, (3) scaffolds the run's config.json, and
(4) optionally invokes the Julia solver. It is the thin launcher the roadmap's
experience layer calls for; it wires nothing straight to the optimizer — it shells
out to run_model.jl exactly as a human would.

    # preview + validate only (no run):
    python tools/launcher.py --island maluku --year 2030 --scenario base --clean reference
    # write a config and launch the fast LP dispatch engine on HiGHS:
    python tools/launcher.py --island maluku --year 2030 --scenario base \
        --clean reference --engine dispatch --run

Runs on Python + pandas. The --run step needs Julia + the project (see
docs/environment_setup.md).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    print("launcher requires pandas", file=sys.stderr)
    sys.exit(3)

try:
    from tools.validate_schema import validate_dataset
    from tools.export_pypsa import time_structure, _read
except ImportError:  # pragma: no cover
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from validate_schema import validate_dataset
    from export_pypsa import time_structure, _read

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# scenario -> grid/village flags (mirrors functions/preflight.jl::scenario_settings)
SCENARIOS = {"base", "grid", "village", "gridvillage", "highimportprice", "nocoal",
             "captive", "gridcaptive"}
CLEANS = {"reference", "clean"}


def preview(folder, engine, solver):
    """Print a scenario-size preview and a qualitative ETA; return a dims dict."""
    gens = _read(os.path.join(folder, "generators.csv"))
    demand = _read(os.path.join(folder, "demand.csv"))
    P, H, T, _ = time_structure(demand)

    nz = int(pd.to_numeric(gens["Zone"], errors="coerce").nunique())
    ng = len(gens)
    n_uc = int((pd.to_numeric(gens.get("Commit", 0), errors="coerce") == 1).sum())
    n_vre = int((pd.to_numeric(gens.get("VRE", 0), errors="coerce") == 1).sum())
    n_stor = int((pd.to_numeric(gens.get("STOR", 0), errors="coerce") >= 1).sum())
    nlines = 0
    npath = os.path.join(folder, "network.csv")
    if os.path.isfile(npath):
        nlines = len(_read(npath))

    # decentralised site layer (site_/village_/ip_ generators), if present
    n_sites = n_site_gens = 0
    for pfx in ("site", "village", "ip"):
        sg = os.path.join(folder, f"{pfx}_generators.csv")
        if os.path.isfile(sg):
            sgens = _read(sg)
            n_site_gens = len(sgens)
            idc = next((c for c in ("Site", "Village", "Industrial_Park") if c in sgens.columns), None)
            n_sites = int(pd.to_numeric(sgens[idc], errors="coerce").nunique()) if idc else 0
            break

    # a coarse variable-count proxy: T hourly steps x (generation + commitment)
    approx_vars = T * (ng + n_site_gens + n_stor * 2 + nlines) + (T * n_uc * 3 if engine != "dispatch" else 0)

    print(f"  zones           {nz}")
    print(f"  generators      {ng}  (UC {n_uc} · VRE {n_vre} · storage {n_stor})")
    if n_site_gens:
        print(f"  sites           {n_sites} site(s) · {n_site_gens} site generator(s)")
    print(f"  transmission    {nlines} line(s)")
    print(f"  representative  {P} period(s) x {H} h = {T} hourly steps")
    print(f"  engine          {engine}   solver {solver}")
    print(f"  ~problem size   {approx_vars:,} primal variables (order-of-magnitude)")

    # ETA from measured anchors: dispatch LP on HiGHS is seconds–minutes; the UC-MILP
    # capacity expansion is fast on Gurobi but hard for HiGHS (timor_demo ~27 min).
    if engine == "dispatch":
        eta = "seconds to a few minutes (LP-relaxed dispatch is fast on HiGHS)"
    elif solver == "gurobi":
        eta = "seconds to minutes (UC-MILP; Gurobi is the fast path)"
    else:
        eta = ("minutes to tens of minutes — the UC-MILP is hard for HiGHS at this "
               "scale; consider engine=dispatch or solver=gurobi for production")
    print(f"  est. runtime    {eta}")
    return dict(zones=nz, generators=ng, uc=n_uc, vre=n_vre, storage=n_stor,
                lines=nlines, periods=P, hours_per_period=H, timesteps=T)


def build_config(args):
    # BAUCO2emissions only feeds the 2035-clean reduction constraint; mirror
    # generate_jobs.py and zero it otherwise so configs match across the two paths.
    reduction = bool(args.year == "2035" and args.clean == "clean")
    cfg = {
        "island": args.island,
        "year": str(args.year),
        "scenario": args.scenario,
        "clean": args.clean,
        "CO235reduction": reduction,
        "BAUCO2emissions": float(args.bau) if reduction else 0.0,
        "CO2_limit": float(args.co2_limit),
        "engine": args.engine,
        "relax_uc": bool(args.relax_uc),
        "solver": args.solver,
        "mipgap": float(args.mipgap),
    }
    return cfg


def main(argv):
    ap = argparse.ArgumentParser(description="Guided validate + preview + launch a garuda run.")
    ap.add_argument("--island", required=True)
    ap.add_argument("--year", default="2030")
    ap.add_argument("--scenario", default="base", choices=sorted(SCENARIOS))
    ap.add_argument("--clean", default="reference", choices=sorted(CLEANS))
    ap.add_argument("--engine", default="expansion", choices=("expansion", "dispatch"))
    ap.add_argument("--solver", default="highs", choices=("highs", "gurobi"))
    ap.add_argument("--relax-uc", dest="relax_uc", action="store_true", default=True,
                    help="LP-relax UC in the dispatch engine (default on; fast on HiGHS)")
    ap.add_argument("--exact-uc", dest="relax_uc", action="store_false",
                    help="keep an exact UC (MILP) dispatch instead of the LP relaxation")
    ap.add_argument("--mipgap", type=float, default=0.01)
    ap.add_argument("--co2-limit", dest="co2_limit", default=1.0e12,
                    help="CO2 cap (tCO2) for clean runs; default effectively unconstrained")
    ap.add_argument("--bau", default=0.0, help="BAU CO2 emissions (tCO2) for 2035 clean runs")
    ap.add_argument("--config", help="path to write config.json (default: scratch next to results)")
    ap.add_argument("--data-root", default=os.path.join(REPO_ROOT, "data_indonesia"))
    ap.add_argument("--force", action="store_true", help="proceed even if schema validation finds errors")
    ap.add_argument("--run", action="store_true", help="invoke run_model.jl after scaffolding")
    args = ap.parse_args(argv[1:])

    folder = os.path.join(args.data_root, str(args.year), args.island)
    name = f"{args.scenario}_{args.island}_{args.year}_{args.clean}"
    print(f"== garuda launcher — {name} ==")
    print(f"input folder: {folder}")
    if not os.path.isdir(folder):
        print(f"  ERROR: input folder not found", file=sys.stderr)
        return 2

    print("\n[1/3] schema validation")
    errors, warnings = validate_dataset(folder)
    for w in warnings:
        print(f"  warning: {w}")
    for e in errors:
        print(f"  ERROR:   {e}")
    if errors and not args.force:
        print(f"\n  {len(errors)} error(s) — fix the inputs or pass --force. Aborting.")
        return 1
    if not errors:
        print(f"  OK ({len(warnings)} warning(s))")

    print("\n[2/3] scenario preview")
    preview(folder, args.engine, args.solver)

    print("\n[3/3] config")
    cfg = build_config(args)
    config_path = args.config or os.path.join(REPO_ROOT, "results", name + ".config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as fh:
        json.dump(cfg, fh, indent=2)
    print(f"  wrote {config_path}")
    print(f"  results will land in results/{name}/")

    run_cmd = ["julia", "--project=.", "run_model.jl", "--config", config_path]
    if not args.run:
        print("\nNext: run it with")
        print("  " + " ".join(run_cmd))
        return 0

    print("\nlaunching:", " ".join(run_cmd))
    try:
        return subprocess.run(run_cmd, cwd=REPO_ROOT).returncode
    except FileNotFoundError:
        print("  ERROR: 'julia' not found on PATH — see docs/environment_setup.md", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main(sys.argv))
