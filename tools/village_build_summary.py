#!/usr/bin/env python3
"""Per-village build and trade summary for a solved site-layer run.

Joins the site result CSVs into one row per village: solar MW built, battery
power MW and energy MWh built, whether it connected, and its annual import and
export in MWh. Writes `village_build_summary.csv` into the results folder and
prints headline totals plus the distribution.

    python3 tools/village_build_summary.py results/gridvillage_timor_2030_reference
    python3 tools/village_build_summary.py <dir_A> --compare <dir_B>

TWO THINGS THIS TOOL WILL TELL YOU ABOUT, BECAUSE THEY INVALIDATE NAIVE READINGS:

1. **Trade allocation is not unique at import_price = export_price = 0.** With
   both prices zero the import/export variables carry no objective coefficient,
   so the optimum is a face rather than a point: total system cost is pinned but
   the per-village split of who imports and who exports is arbitrary among many
   equally optimal allocations. Measured on timor_demo, Gurobi and HiGHS agreed
   on Total_Costs to 11 s.f. while differing 47% on one village's imports and
   reporting 308.7 vs 0.0 MWh of export for the same village. BUILD columns
   (solar, battery) are well determined; TRADE columns are not. The tool prints a
   warning whenever it detects that regime from the run's config sidecar.

2. **`Connected` is `round(Int, ...)` of a possibly-fractional binary**
   (result_extraction_function.jl:140). On a `relax_uc: true` run a village that
   actually traded can report `Connected = 0`. The tool cross-checks `Connected`
   against non-zero import/export and reports any disagreement.

Energy columns in the result CSVs are already annual — the extractor applies the
representative-period sample weights. Do not rescale by 8760/1344.

Solver-free; reads result CSVs only.
"""
import argparse
import json
import os
import sys

import pandas as pd


def _read(path):
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def _cfg_for(run_dir):
    """Find the run's config, wherever the launcher happened to put it.

    sensitivity.py writes `<results_root>/<name>.config.json` beside the folder;
    generate_jobs*.py write `jobs/<name>/config.json` in a sibling tree. Check
    both, or the trade-degeneracy warning silently never fires.
    """
    run_dir = run_dir.rstrip("/")
    name = os.path.basename(run_dir)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(run_dir)))
    for cand in (run_dir + ".config.json",
                 os.path.join(run_dir, "config.json"),
                 os.path.join(repo, "jobs", name, "config.json")):
        if os.path.exists(cand):
            try:
                return json.load(open(cand))
            except (ValueError, OSError):
                return None
    return None


def summarise(run_dir):
    gen = _read(os.path.join(run_dir, "site_generator_results.csv"))
    key = "Village" if "Village" in gen.columns else "ID"

    solar = (gen[gen.technology == "solar"].groupby(key)
             .agg(solar_MW=("Total_MW", "sum"),
                  solar_built_MW=("Change_in_MW", "sum"),
                  solar_GWh=("Electricity_GWh", "sum")))
    batt_p = (gen[gen.technology == "battery"].groupby(key)
              .agg(battery_MW=("Total_MW", "sum"),
                   battery_built_MW=("Change_in_MW", "sum")))
    out = solar.join(batt_p, how="outer")

    stor_path = os.path.join(run_dir, "site_storage_results.csv")
    if os.path.exists(stor_path):
        st = _read(stor_path)
        skey = key if key in st.columns else "ID"
        out = out.join(st.groupby(skey).agg(battery_MWh=("Total_Storage_MWh", "sum"),
                                            battery_built_MWh=("Change_in_Storage_MWh", "sum")),
                       how="outer")

    conn_path = os.path.join(run_dir, "site_connection_results.csv")
    if os.path.exists(conn_path):
        cn = _read(conn_path)
        ckey = key if key in cn.columns else "ID"
        keep = [c for c in ("Connected", "Total_Import_MWh", "Total_Export_MWh")
                if c in cn.columns]
        out = out.join(cn.groupby(ckey)[keep].sum(), how="outer")

    return out.fillna(0.0).sort_index()


def report(run_dir, df):
    cfg = _cfg_for(run_dir)
    print(f"\n=== {os.path.basename(run_dir.rstrip('/'))} — {len(df)} villages ===")

    tot = {
        "solar built (MW)": df.get("solar_built_MW", pd.Series(dtype=float)).sum(),
        "solar total (MW)": df.get("solar_MW", pd.Series(dtype=float)).sum(),
        "battery power built (MW)": df.get("battery_built_MW", pd.Series(dtype=float)).sum(),
        "battery energy built (MWh)": df.get("battery_built_MWh", pd.Series(dtype=float)).sum(),
        "import (MWh/yr)": df.get("Total_Import_MWh", pd.Series(dtype=float)).sum(),
        "export (MWh/yr)": df.get("Total_Export_MWh", pd.Series(dtype=float)).sum(),
    }
    for k, v in tot.items():
        print(f"  {k:<28} {v:>14,.2f}")

    if "Connected" in df.columns:
        n = int(round(df.Connected.sum()))
        print(f"  {'connected':<28} {n:>14,} of {len(df)}")
        traded = df[(df.get("Total_Import_MWh", 0) > 1e-9) |
                    (df.get("Total_Export_MWh", 0) > 1e-9)]
        mismatch = traded[traded.Connected < 0.5]
        if len(mismatch):
            print(f"  !! {len(mismatch)} village(s) trade but report Connected=0 "
                  f"— fractional-binary rounding; see module docstring")

    if "solar_built_MW" in df.columns:
        s = df.solar_built_MW
        print(f"\n  solar built per village (MW): min {s.min():.4f} "
              f"median {s.median():.4f} mean {s.mean():.4f} max {s.max():.4f}; "
              f"{int((s > 1e-9).sum())} of {len(df)} built any")

    if cfg is not None:
        ip, ep = float(cfg.get("import_price", 0) or 0), float(cfg.get("export_price", 0) or 0)
        if ip == 0 and ep == 0 and (
                df.get("Total_Import_MWh", pd.Series([0])).sum() > 1e-9 or
                df.get("Total_Export_MWh", pd.Series([0])).sum() > 1e-9):
            print("\n  *** import_price = export_price = 0: trade variables carry no")
            print("      objective coefficient, so the optimum is a FACE. The per-village")
            print("      import/export split above is ONE valid allocation among many and")
            print("      must not be reported as the model's answer. Build columns are fine.")
    else:
        print("\n  (no config sidecar found — could not check the trade-degeneracy regime)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--compare", help="second results dir to diff against")
    ap.add_argument("--top", type=int, default=10, help="show N largest builders")
    args = ap.parse_args(argv)

    df = summarise(args.run_dir)
    out = os.path.join(args.run_dir, "village_build_summary.csv")
    df.to_csv(out)
    report(args.run_dir, df)
    print(f"\n  written: {out}")

    if args.top and "solar_built_MW" in df.columns:
        cols = [c for c in ("solar_built_MW", "battery_built_MW", "battery_built_MWh",
                            "Connected", "Total_Import_MWh", "Total_Export_MWh")
                if c in df.columns]
        print(f"\n  top {args.top} by solar built:")
        print(df.nlargest(args.top, "solar_built_MW")[cols].to_string())

    if args.compare:
        d2 = summarise(args.compare)
        d2.to_csv(os.path.join(args.compare, "village_build_summary.csv"))
        report(args.compare, d2)
        common = [c for c in df.columns if c in d2.columns]
        delta = (d2[common].sum() - df[common].sum())
        print(f"\n=== totals delta: {os.path.basename(args.compare.rstrip('/'))} "
              f"minus {os.path.basename(args.run_dir.rstrip('/'))} ===")
        print(delta.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
