#!/usr/bin/env python3
"""Per-village annualised cost attribution for a solved site-layer run.

No result CSV carries per-village cost: `cost_results.csv` is system-wide, and the
`site_*` files carry capacity and energy but no money. This reconstructs cost from
the solved quantities and the input cost columns, one row per village, and checks
the reconstruction closes against the reported system total.

    python3 tools/village_cost_attribution.py results/village_timor_2030_reference
    python3 tools/village_cost_attribution.py <run_dir> --compare <run_dir_B>

Writes `village_cost_attribution.csv` into the run folder and prints the component
split plus the closure residual.

THE COST FORMULA (annualised $/yr, matching the objective in functions/optimizer.jl):

    generation = max(Change_in_MW, 0) * Inv_Cost_per_MWyr          # new build only
               + Total_MW            * Fixed_OM_Cost_per_MWyr      # on the whole fleet
               + Electricity_GWh*1e3 * (Var_OM_Cost_per_MWh
                                        + Heat_Rate_MMBTU_per_MWh * fuel_$/MMBtu)
    storage    = max(Change_in_Storage_MWh, 0) * Inv_Cost_per_MWhyr
               + Total_Storage_MWh              * Fixed_OM_Cost_per_MWhyr

`Change_in_*` is clipped at zero because a retirement is not a negative investment:
the objective charges investment only on new capacity. Energy columns in the result
CSVs are already annual (the extractor applies the representative-period sample
weights), so nothing is rescaled by 8760/1344.

WHY THIS TOOL EXISTS — the reallocation it exposes:

`cost_results.csv` books battery **power** capex inside `Fixed_Costs_Village`,
alongside solar, while only battery **energy** lands in
`Fixed_Costs_Village_Storage`. Read naively that file says "solar $29.96 M,
storage $35.60 M". Attributed by component the split is solar $25.24 M and storage
$40.20 M — 58.2 % of system cost. The programme is a storage procurement with solar
attached, and no system-level CSV says so.

TWO TRAPS THIS TOOL HANDLES:

1. `site_storage_results.csv` and `village_generators.csv` BOTH carry a `Village`
   column. Merging without suffixes silently drops the groupby key. Merge on
   ID/R_ID and suffix.
2. `fuels_data.csv` contains a fuel literally named "None". Reading it with pandas
   defaults turns that string into NaN and the fuel-price join fails open at zero
   cost. All reads here use keep_default_na=False (the repo convention).

Solver-free; reads result CSVs and dataset inputs only.
"""
import argparse
import json
import os
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def _resolve_dataset(run_dir, data_root, island=None, year=None):
    """Find the input folder for a run, from its config sidecar or its folder name."""
    run_dir = run_dir.rstrip("/")
    name = os.path.basename(run_dir)
    if island is None or year is None:
        cfg = None
        for cand in (run_dir + ".config.json",
                     os.path.join(run_dir, "config.json"),
                     os.path.join(REPO_ROOT, "jobs", name, "config.json")):
            if os.path.exists(cand):
                try:
                    cfg = json.load(open(cand))
                except (ValueError, OSError):
                    cfg = None
                break
        if cfg:
            island, year = island or cfg.get("island"), year or str(cfg.get("year"))
        else:
            # results/<scenario>_<island>_<year>_<clean>[__tag] — year is the 4-digit part
            parts = name.split("_")
            digits = [i for i, p in enumerate(parts) if p.isdigit() and len(p) == 4]
            if not digits:
                raise SystemExit(f"cannot infer island/year from {name!r}; pass --island/--year")
            y = digits[-1]
            year = year or parts[y]
            island = island or "_".join(parts[1:y])
    path = os.path.join(data_root, str(year), island)
    if not os.path.isdir(path):
        raise SystemExit(f"dataset not found: {path} (pass --island/--year to override)")
    return path, island, year


def attribute(run_dir, dataset_dir):
    gen = _read(os.path.join(run_dir, "site_generator_results.csv"))
    vg = _read(os.path.join(dataset_dir, "village_generators.csv"))
    fuels = _read(os.path.join(dataset_dir, "fuels_data.csv"))
    price = dict(zip(fuels.Fuel.astype(str), fuels.Cost_per_MMBtu.astype(float)))

    cost_cols = ["R_ID", "Inv_Cost_per_MWyr", "Fixed_OM_Cost_per_MWyr",
                 "Var_OM_Cost_per_MWh", "Heat_Rate_MMBTU_per_MWh", "Fuel"]
    # suffix everything from the input frame: village_generators also has `Village`
    g = gen.merge(vg[cost_cols], left_on="ID", right_on="R_ID",
                  how="left", suffixes=("", "_in"))
    if g.R_ID.isna().any():
        raise SystemExit(f"{int(g.R_ID.isna().sum())} result rows did not join to village_generators")

    g["fuel_price"] = g.Fuel.astype(str).map(price)
    if g.fuel_price.isna().any():
        bad = sorted(set(g.Fuel[g.fuel_price.isna()].astype(str)))
        raise SystemExit(f"fuel(s) missing from fuels_data.csv: {bad}")

    mwh = g.Electricity_GWh.astype(float) * 1e3
    g["c_inv"] = g.Change_in_MW.clip(lower=0) * g.Inv_Cost_per_MWyr
    g["c_fom"] = g.Total_MW * g.Fixed_OM_Cost_per_MWyr
    g["c_vom"] = mwh * g.Var_OM_Cost_per_MWh
    g["c_fuel"] = mwh * g.Heat_Rate_MMBTU_per_MWh * g.fuel_price
    g["cost"] = g.c_inv + g.c_fom + g.c_vom + g.c_fuel

    stor_path = os.path.join(run_dir, "site_storage_results.csv")
    st = None
    if os.path.exists(stor_path):
        sr = _read(stor_path)
        scols = ["R_ID", "Inv_Cost_per_MWhyr", "Fixed_OM_Cost_per_MWhyr"]
        st = sr.merge(vg[scols], left_on="ID", right_on="R_ID",
                      how="left", suffixes=("", "_in"))
        st["c_inv_e"] = st.Change_in_Storage_MWh.clip(lower=0) * st.Inv_Cost_per_MWhyr
        st["c_fom_e"] = st.Total_Storage_MWh * st.Fixed_OM_Cost_per_MWhyr
        st["cost"] = st.c_inv_e + st.c_fom_e

    # ---- components, in the order they matter ----
    def gsum(mask, col="cost"):
        return float(g.loc[mask, col].sum())

    solar, batt, diesel = g.technology == "solar", g.technology == "battery", g.technology == "diesel"
    comp = {
        "battery_energy": float(st.cost.sum()) if st is not None else 0.0,
        "solar": gsum(solar),
        "battery_power": gsum(batt, "c_inv") + gsum(batt, "c_fom"),
        "diesel_fuel_vom": gsum(diesel, "c_fuel") + gsum(diesel, "c_vom"),
        "battery_vom": gsum(batt, "c_vom"),
        "diesel_fixed": gsum(diesel, "c_inv") + gsum(diesel, "c_fom"),
    }
    other = gsum(~(solar | batt | diesel))
    if abs(other) > 1e-6:
        comp["other_tech"] = other

    # ---- per village ----
    per = g.groupby("Village").agg(
        gen_cost=("cost", "sum"),
        solar_cost=("cost", lambda s: float(s[g.loc[s.index, "technology"] == "solar"].sum())),
        diesel_cost=("cost", lambda s: float(s[g.loc[s.index, "technology"] == "diesel"].sum())),
        battery_power_cost=("cost", lambda s: float(s[g.loc[s.index, "technology"] == "battery"].sum())),
    )
    if st is not None and "Village" in st.columns:
        per = per.join(st.groupby("Village").cost.sum().rename("battery_energy_cost"), how="outer")
    per = per.fillna(0.0)
    per["total_cost"] = per.gen_cost + per.get("battery_energy_cost", 0.0)
    return per.sort_index(), comp


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--compare", help="second run dir to diff totals against")
    ap.add_argument("--data-root", default=os.path.join(REPO_ROOT, "data_indonesia"))
    ap.add_argument("--island")
    ap.add_argument("--year")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args(argv)

    def run(rd):
        ds, isl, yr = _resolve_dataset(rd, args.data_root, args.island, args.year)
        per, comp = attribute(rd, ds)
        total = sum(comp.values())

        print(f"\n=== {os.path.basename(rd.rstrip('/'))}  (inputs: {isl}/{yr}, {len(per)} villages) ===")
        print(f"  {'component':<22}{'$M/yr':>10}{'share':>9}")
        for k, v in sorted(comp.items(), key=lambda kv: -kv[1]):
            print(f"  {k:<22}{v/1e6:>10.4f}{v/total*100:>8.1f}%")
        print(f"  {'TOTAL (reconstructed)':<22}{total/1e6:>10.4f}")

        cp = os.path.join(rd, "cost_results.csv")
        if os.path.exists(cp):
            rep = float(_read(cp).Total_Costs[0]) * 1e6
            res = total - rep
            sf = "n/a" if rep == 0 else f"{abs(res/rep):.2e}"
            print(f"  {'reported Total_Costs':<22}{rep/1e6:>10.4f}")
            print(f"  {'residual':<22}{res:>10.2e}  (relative {sf})")
            if rep and abs(res / rep) > 1e-6:
                print("  ** RECONSTRUCTION DOES NOT CLOSE — do not use these numbers **")

        storage = comp.get("battery_energy", 0) + comp.get("battery_power", 0) + comp.get("battery_vom", 0)
        print(f"\n  storage all-in: ${storage/1e6:.4f} M/yr = {storage/total*100:.1f}% of system cost")
        print(f"  solar all-in  : ${comp.get('solar',0)/1e6:.4f} M/yr = {comp.get('solar',0)/total*100:.1f}%")
        print("  (cost_results.csv books battery POWER inside Fixed_Costs_Village, so that")
        print("   file understates storage and overstates solar — see the module docstring)")

        out = os.path.join(rd, "village_cost_attribution.csv")
        per.to_csv(out)
        print(f"\n  written: {out}")
        if args.top:
            print(f"\n  top {args.top} villages by total cost:")
            print(per.nlargest(args.top, "total_cost").round(0).to_string())
        return per, comp, total

    per_a, _, tot_a = run(args.run_dir)
    if args.compare:
        per_b, _, tot_b = run(args.compare)
        print(f"\n=== delta: {os.path.basename(args.compare.rstrip('/'))} "
              f"minus {os.path.basename(args.run_dir.rstrip('/'))} ===")
        print(f"  system total: {(tot_b-tot_a)/1e6:+.4f} $M/yr")
        j = per_a[["total_cost"]].join(per_b[["total_cost"]], lsuffix="_a", rsuffix="_b", how="outer").fillna(0)
        d = (j.total_cost_b - j.total_cost_a)
        moved = d[d.abs() > 1e-6]
        print(f"  villages whose cost moved by >$1e-6: {len(moved)} of {len(j)}")
        if len(moved):
            print(f"  largest movers:\n{moved.reindex(moved.abs().sort_values(ascending=False).index).head(8).round(2).to_string()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
