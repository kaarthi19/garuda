#!/usr/bin/env python3
"""Validate PyPSA-export dispatch parity against the garuda dispatch engine (Phase 4).

Builds the PyPSA network from an input folder (mode="dispatch": existing fleet
fixed, the LP-relaxed operational problem), solves it on HiGHS, and compares the
per-zone reliability outcome — unserved energy (MWh) and unserved share (% of
demand) — against the reference written by functions/dispatch_engine.jl
(reliability_results.csv).

    # 1) produce the garuda reference (Julia):
    julia --project=. run_model.jl --config maluku_dispatch.json   # engine=dispatch
    # 2) check the PyPSA export reproduces it:
    python tools/validate_pypsa_parity.py data_indonesia/2030/maluku \
        --reference results/base_maluku_2030_reference

The pass/fail metric is the SYSTEM-TOTAL unserved energy. Per-zone unserved is
degenerate (a uniform NSE price + a connected lossless network make the optimizer
indifferent to which connected zone sheds), so it is reported but not asserted.

The garuda grid-zone dispatch is decoupled from the village layer whenever the
scenario is grid-off (base/village), so a `base` reference is the clean
comparison for this grid-only export. Use `base` references only.

Exit code 0 if the system total is within tolerance, 1 otherwise — so it can gate CI.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

try:
    import numpy as np
    import pandas as pd
except ImportError:  # pragma: no cover
    print("validate_pypsa_parity requires pandas + numpy", file=sys.stderr)
    sys.exit(3)

try:  # importable as a package, or runnable as a bare script from anywhere
    from tools.export_pypsa import build_network, _read, _num
except ImportError:  # pragma: no cover
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from export_pypsa import build_network, _read, _num  # noqa: E402


def pypsa_zone_reliability(n):
    """Per-zone unserved energy (MWh/yr) and % of demand from a solved network."""
    sw = n.snapshot_weightings.objective.to_numpy()
    rows = []
    ls = n.generators[n.generators.carrier == "load_shedding"]
    for bus in n.buses.index:
        # zone integer from the load name (load_z{z}) on this bus
        loads = n.loads[n.loads.bus == bus]
        if loads.empty:
            continue
        zone = int(loads.index[0].replace("load_z", ""))
        dem = float((sw * n.loads_t.p_set[loads.index].sum(axis=1).to_numpy()).sum())
        bus_ls = ls[ls.bus == bus].index
        nse = float((sw * n.generators_t.p[bus_ls].sum(axis=1).to_numpy()).sum()) if len(bus_ls) else 0.0
        rows.append(dict(Zone=zone, Total_NSE_MWh=nse,
                         NSE_Percent_of_Demand=100 * nse / dem if dem else 0.0,
                         Demand_MWh=dem))
    return pd.DataFrame(rows).sort_values("Zone").reset_index(drop=True)


def solve_pypsa(folder, quiet=True):
    if quiet:
        logging.disable(logging.WARNING)
    n = build_network(folder, mode="dispatch")
    n.optimize(solver_name="highs",
               solver_options={"output_flag": False} if quiet else {})
    return n


def compare(folder, reference_dir, rel_tol=0.01):
    """Compare PyPSA dispatch to the garuda dispatch reference.

    The pass/fail metric is the **system-total** unserved energy. That is the
    well-defined quantity: with a uniform non-served-energy price and a connected,
    lossless transport network, the LP is degenerate in *which* connected zone
    bears a given shortfall (generation can be reshuffled over the zero-cost
    links), so the per-zone split is not unique and is reported for information
    only — not used to pass or fail.

    Returns (per_zone_table, totals_dict, ok).
    """
    ref_path = os.path.join(reference_dir, "reliability_results.csv")
    if not os.path.isfile(ref_path):
        raise FileNotFoundError(
            f"no reliability_results.csv in {reference_dir} — run the garuda dispatch "
            f"engine first (engine=dispatch in the run config).")
    ref = _read(ref_path)

    n = solve_pypsa(folder)
    pp = pypsa_zone_reliability(n)

    m = ref.merge(pp, on="Zone", suffixes=("_garuda", "_pypsa"))
    # the inner merge must keep every zone — a mismatch means the export and the
    # reference disagree on the zone set, which would silently bias the totals.
    if len(m) != len(ref) or len(m) != len(pp):
        raise ValueError(
            f"zone-set mismatch: reference zones {sorted(ref['Zone'])} vs PyPSA zones "
            f"{sorted(pp['Zone'])} — the export and the reference describe different zones.")
    m["dNSE_pct_points"] = m["NSE_Percent_of_Demand_pypsa"] - m["NSE_Percent_of_Demand_garuda"]

    g_tot = float(_num(m["Total_NSE_MWh_garuda"]).sum())
    p_tot = float(_num(m["Total_NSE_MWh_pypsa"]).sum())
    dem = float(pp["Demand_MWh"].sum())
    # relative difference, guarding a ~0 garuda total (max(.,1 MWh) keeps it stable)
    rel = abs(p_tot - g_tot) / max(g_tot, 1.0)
    totals = dict(garuda_total_nse=g_tot, pypsa_total_nse=p_tot, rel_diff=rel,
                  garuda_pct=100 * g_tot / dem if dem else 0.0,
                  pypsa_pct=100 * p_tot / dem if dem else 0.0,
                  rel_tol=rel_tol)
    return m, totals, rel <= rel_tol


def main(argv):
    ap = argparse.ArgumentParser(description="PyPSA-export dispatch-parity check vs garuda.")
    ap.add_argument("folder", help="garuda input folder, e.g. data_indonesia/2030/maluku")
    ap.add_argument("--reference", required=True,
                    help="garuda results dir containing reliability_results.csv (a base-scenario dispatch run)")
    ap.add_argument("--rel-tol", type=float, default=0.01,
                    help="relative tolerance on system-total unserved energy (default 0.01 = 1%%)")
    ap.add_argument("--csv", help="write the per-zone comparison table to this CSV")
    args = ap.parse_args(argv[1:])

    table, totals, ok = compare(args.folder, args.reference, rel_tol=args.rel_tol)
    pd.set_option("display.width", 200, "display.max_columns", 30)
    cols = ["Zone", "Total_NSE_MWh_garuda", "Total_NSE_MWh_pypsa",
            "NSE_Percent_of_Demand_garuda", "NSE_Percent_of_Demand_pypsa", "dNSE_pct_points"]
    print(f"PyPSA dispatch parity — {args.folder}  vs  {args.reference}")
    print("\nper-zone (informational — distribution is degenerate under uniform NSE price):")
    print(table[cols].round(3).to_string(index=False))
    print(f"\nsystem total unserved energy   garuda {totals['garuda_total_nse']:>16,.1f} MWh "
          f"({totals['garuda_pct']:.3f}%)")
    print(f"                               pypsa  {totals['pypsa_total_nse']:>16,.1f} MWh "
          f"({totals['pypsa_pct']:.3f}%)")
    print(f"                               rel. difference {100*totals['rel_diff']:.4f}%  "
          f"(tolerance {100*totals['rel_tol']:.2f}%)")
    if args.csv:
        table.to_csv(args.csv, index=False)
        print(f"\nwrote {args.csv}")
    print("\nPARITY OK — system-total unserved within tolerance" if ok else
          "\nPARITY FAIL — system-total unserved outside tolerance")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
