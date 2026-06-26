#!/usr/bin/env python3
"""No-solve screening engine for the garuda zonal model.

A solver-free, instant per-zone screen of an input folder: a merit-order dispatch
of the EXISTING fleet against the representative-hour demand (VRE must-take at its
availability, thermal stacked cheapest-first; storage and transmission are
ignored). Reports annual demand, renewable share, emissions, operating cost and
unserved energy per zone — an order-of-magnitude sanity check / rapid what-if,
NOT an optimised result.

    python tools/screening.py data_indonesia/2030/sulawesi
    python tools/screening.py <folder> --csv screening_sulawesi.csv

Runs on a laptop with only Python + pandas/numpy — no Julia, no solver, no licence.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

SITE_NA = dict(keep_default_na=False, na_values=[""])  # preserve the literal fuel "None"


def _read(path):
    return pd.read_csv(path, encoding="utf-8-sig", **SITE_NA)


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _zone_names(folder):
    zpath = os.path.join(folder, "zones.csv")
    names = {}
    if os.path.isfile(zpath):
        z = _read(zpath)
        cols = {c.lower().lstrip("﻿").strip(): c for c in z.columns}
        zc = cols.get("zone")
        nc = cols.get("province") or cols.get("zone_name") or cols.get("name") or cols.get("system")
        if zc and nc:
            for _, r in z.iterrows():
                import re
                m = re.search(r"\d+", str(r[zc]))
                if m:
                    names[int(m.group())] = str(r[nc])
    return names


def screen(folder):
    gens = _read(os.path.join(folder, "generators.csv"))
    fuels = _read(os.path.join(folder, "fuels_data.csv"))
    demand = _read(os.path.join(folder, "demand.csv"))
    var = _read(os.path.join(folder, "generators_variability.csv")).iloc[:, 1:]  # drop hour index
    znames = _zone_names(folder)

    # --- time structure: sample_weight[t] = (hours that period represents)/H ---
    P = int(_num(demand["Rep_Periods"]).dropna().iloc[0])
    H = int(_num(demand["Timesteps_per_Rep_Period"]).dropna().iloc[0])
    W = _num(demand["Sub_Weights"]).dropna().to_numpy()[:P]
    T = P * H
    sample_weight = np.repeat(W / H, H)[:T]

    # --- per-generator economics ---
    fuel_cost = dict(zip(fuels["Fuel"].astype(str), _num(fuels["Cost_per_MMBtu"])))
    fuel_co2 = dict(zip(fuels["Fuel"].astype(str), _num(fuels["CO2_content_tons_per_MMBtu"])))
    g = gens.copy()
    # Existing-fleet screen: dispatch only units that exist today. New-build
    # candidates (New_Build==1) carry a "potential" Existing_Cap_MW in some
    # datasets but are not built, so they contribute zero capacity here — matching
    # the loader's OLD = !(New_Build==1).
    existing = _num(g.get("New_Build", 0)).fillna(0).astype(int) != 1
    g["cap"] = _num(g["Existing_Cap_MW"]).fillna(0.0).where(existing, 0.0)
    g["hr"] = _num(g.get("Heat_Rate_MMBTU_per_MWh", 0)).fillna(0.0)
    g["fc"] = g["Fuel"].astype(str).map(fuel_cost).fillna(0.0)
    g["co2"] = g["Fuel"].astype(str).map(fuel_co2).fillna(0.0)
    g["var_cost"] = _num(g.get("Var_OM_Cost_per_MWh", 0)).fillna(0.0) + g["fc"] * g["hr"]
    g["co2_rate"] = g["co2"] * g["hr"]                       # tCO2/MWh
    g["fom"] = _num(g.get("Fixed_OM_Cost_per_MWyr", 0)).fillna(0.0) * g["cap"]
    g["vre"] = _num(g.get("VRE", 0)).fillna(0).astype(int) == 1
    g["re"] = _num(g.get("RE", 0)).fillna(0).astype(int) == 1
    g["stor"] = _num(g.get("STOR", 0)).fillna(0).astype(int) >= 1
    g["zone"] = _num(g["Zone"]).astype(int)

    zones = sorted(g["zone"].unique())
    rows = []
    for z in zones:
        dz = _num(demand[f"demand_z{z}"]).to_numpy()[:T]
        gz = g[g["zone"] == z]

        # VRE must-take at availability (column index = R_ID-1 in the dropped frame)
        vre_avail = np.zeros(T)
        for _, u in gz[gz["vre"]].iterrows():
            col = int(u["R_ID"]) - 1
            av = var.iloc[:T, col].to_numpy() if col < var.shape[1] else np.ones(T)
            vre_avail += u["cap"] * np.asarray(av, dtype=float)
        vre_used = np.minimum(vre_avail, dz)
        residual = np.maximum(dz - vre_used, 0.0)

        # thermal/dispatchable merit order (skip storage)
        disp = gz[(~gz["vre"]) & (~gz["stor"]) & (gz["cap"] > 0)].sort_values("var_cost")
        emissions = 0.0
        var_cost_tot = 0.0
        re_thermal = 0.0
        cum = 0.0
        for _, u in disp.iterrows():
            gen = np.clip(residual - cum, 0.0, u["cap"])          # MW per hour
            cum += u["cap"]
            ann = float(np.sum(sample_weight * gen))             # MWh/yr
            emissions += ann * u["co2_rate"]
            var_cost_tot += ann * u["var_cost"]
            if u["re"]:
                re_thermal += ann
        unserved = float(np.sum(sample_weight * np.maximum(residual - cum, 0.0)))

        ann_demand = float(np.sum(sample_weight * dz))
        re_gen = float(np.sum(sample_weight * vre_used)) + re_thermal
        rows.append(dict(
            Zone=z, Zone_Name=znames.get(z, ""),
            Annual_Demand_GWh=ann_demand / 1e3,
            RE_Share_pct=100 * re_gen / ann_demand if ann_demand else 0.0,
            Emissions_ktCO2=emissions / 1e3,
            Variable_Cost_MUSD=var_cost_tot / 1e6,
            Fixed_OM_Cost_MUSD=float(gz["fom"].sum()) / 1e6,
            Unserved_GWh=unserved / 1e3,
            Unserved_pct=100 * unserved / ann_demand if ann_demand else 0.0,
        ))

    out = pd.DataFrame(rows)
    total = dict(Zone="TOTAL", Zone_Name="",
                 Annual_Demand_GWh=out["Annual_Demand_GWh"].sum(),
                 RE_Share_pct=(out["RE_Share_pct"] * out["Annual_Demand_GWh"]).sum()
                              / out["Annual_Demand_GWh"].sum() if out["Annual_Demand_GWh"].sum() else 0.0,
                 Emissions_ktCO2=out["Emissions_ktCO2"].sum(),
                 Variable_Cost_MUSD=out["Variable_Cost_MUSD"].sum(),
                 Fixed_OM_Cost_MUSD=out["Fixed_OM_Cost_MUSD"].sum(),
                 Unserved_GWh=out["Unserved_GWh"].sum(),
                 Unserved_pct=100 * out["Unserved_GWh"].sum() / out["Annual_Demand_GWh"].sum()
                              if out["Annual_Demand_GWh"].sum() else 0.0)
    out = pd.concat([out, pd.DataFrame([total])], ignore_index=True)
    return out


def main(argv):
    ap = argparse.ArgumentParser(description="No-solve per-zone screening (existing fleet).")
    ap.add_argument("folder")
    ap.add_argument("--csv", help="write the per-zone table to this CSV")
    args = ap.parse_args(argv[1:])
    out = screen(args.folder)
    pd.set_option("display.width", 160, "display.max_columns", 20)
    print("Screening estimate (no solver; storage & transmission ignored) —", args.folder)
    print(out.round(2).to_string(index=False))
    if args.csv:
        out.to_csv(args.csv, index=False)
        print(f"\nwrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
