#!/usr/bin/env python3
"""RE-resource & siting summary for the garuda zonal model.

Surfaces the developable renewable potential per **zone** (and per **site** for
village datasets) as a consumable product: developable **solar / wind capacity
(MW)**, **mean capacity factor**, and the implied **annual energy potential
(GWh)**. The developable-MW ceilings are produced upstream by the GIS siting
pipeline (`tools/dem_slope.py` -> `candidate_land.py` -> `resource_siting.py` ->
`ntt/solar_potential.py`, which write the ceiling into the generator tables);
this tool reads those caps from the model inputs and reports them. See
`docs/re_resource.md`.

    python tools/re_resource.py data_indonesia/2030/maluku
    python tools/re_resource.py <folder> --csv re_resource_maluku.csv

Runs on Python + pandas/numpy alone — no Julia, no solver, no GIS stack.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("re_resource requires pandas + numpy", file=sys.stderr)
    sys.exit(3)

NA = dict(keep_default_na=False, na_values=[""])
SITE_PREFIXES = ("site", "village", "ip")
SITE_ID_COLS = ("Site", "Village", "Industrial_Park")
HOURS = 8760


def _read(p):
    return pd.read_csv(p, encoding="utf-8-sig", **NA)


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _kind(resource):
    r = str(resource).lower()
    if "solar" in r or "plts" in r or "surya" in r:
        return "solar"
    if "wind" in r or "angin" in r or "bayu" in r:
        return "wind"
    return "other"


def _zone_names(folder):
    p = os.path.join(folder, "zones.csv")
    names = {}
    if os.path.isfile(p):
        z = _read(p)
        cols = {c.lower().strip(): c for c in z.columns}
        zc = cols.get("zone")
        nc = cols.get("province") or cols.get("zone_name") or cols.get("name") or cols.get("system")
        if zc and nc:
            for _, r in z.iterrows():
                m = re.search(r"\d+", str(r[zc]))
                if m:
                    names[int(m.group())] = str(r[nc])
    return names


def _resolve(folder, base):
    for p in SITE_PREFIXES:
        f = os.path.join(folder, f"{p}_{base}.csv")
        if os.path.isfile(f):
            return f
    return None


def _summarise(gens, var, group_col, group_label, znames=None):
    """Per-group developable solar/wind MW, capacity-weighted mean CF, GWh potential."""
    g = gens.copy()
    g["dev"] = np.maximum(_num(g["Existing_Cap_MW"]).fillna(0.0),
                          _num(g.get("Max_Cap_MW", 0)).fillna(0.0))
    g["vre"] = _num(g.get("VRE", 0)).fillna(0).astype(int) == 1
    g["grp"] = _num(g[group_col]).astype("Int64")

    acc = {}
    for _, u in g[g["vre"]].iterrows():
        col = int(u["R_ID"]) - 1
        cf = float(var.iloc[:, col].mean()) if 0 <= col < var.shape[1] else 1.0
        k = _kind(u["Resource"])
        if k == "other":
            continue
        d = acc.setdefault(int(u["grp"]), {})
        d[f"{k}_mw"] = d.get(f"{k}_mw", 0.0) + u["dev"]
        d[f"{k}_mwcf"] = d.get(f"{k}_mwcf", 0.0) + u["dev"] * cf  # cap-weighted CF numerator

    rows = []
    for grp in sorted(acc):
        d = acc[grp]
        row = {group_label: grp}
        if znames is not None:
            row["Zone_Name"] = znames.get(grp, "")
        for k in ("solar", "wind"):
            mw = d.get(f"{k}_mw", 0.0)
            cf = d.get(f"{k}_mwcf", 0.0) / mw if mw else 0.0
            row[f"{k.title()}_Developable_MW"] = mw
            row[f"{k.title()}_Mean_CF"] = cf
            row[f"{k.title()}_Potential_GWh"] = mw * cf * HOURS / 1e3
        rows.append(row)
    return pd.DataFrame(rows)


def re_resource(folder):
    gens = _read(os.path.join(folder, "generators.csv"))
    var = _read(os.path.join(folder, "generators_variability.csv")).iloc[:, 1:]
    zones = _summarise(gens, var, "Zone", "Zone", _zone_names(folder))

    sites = None
    sgen_path = _resolve(folder, "generators")
    svar_path = _resolve(folder, "generators_variability")
    if sgen_path and svar_path:
        sgen = _read(sgen_path)
        idcol = next((c for c in SITE_ID_COLS if c in sgen.columns), None)
        if idcol:
            svar = _read(svar_path).iloc[:, 1:]
            sites = _summarise(sgen, svar, idcol, "Site")
    return zones, sites


def main(argv):
    ap = argparse.ArgumentParser(description="Per-zone / per-site RE developable potential.")
    ap.add_argument("folder")
    ap.add_argument("--csv", help="write the per-zone table to this CSV")
    args = ap.parse_args(argv[1:])
    zones, sites = re_resource(args.folder)
    pd.set_option("display.width", 200, "display.max_columns", 30)
    print("RE-resource summary —", args.folder)
    print("(developable MW = GIS land-based ceiling: what's physically sitable on "
          "suitable land, often large & non-binding — not what's economic to build)")
    print("\n[zones]")
    print(zones.round(2).to_string(index=False) if len(zones) else "  (no VRE units)")
    if sites is not None and len(sites):
        print("\n[sites]")
        print(sites.round(2).to_string(index=False))
    if args.csv:
        zones.to_csv(args.csv, index=False)
        print(f"\nwrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
