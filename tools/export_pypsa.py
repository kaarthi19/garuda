#!/usr/bin/env python3
"""Export a garuda zonal-model input folder to a PyPSA network (Phase 4).

Feeds the zonal data core into the established open-source power-system framework
[PyPSA](https://pypsa.org) instead of competing with it: zones -> buses, the
transmission network -> links, generators/VRE -> generators, storage -> storage
units, demand -> loads, non-served-energy segments -> load-shedding generators,
and the representative periods -> snapshots with annualising weightings.

    python tools/export_pypsa.py data_indonesia/2030/maluku --netcdf maluku.nc
    # importable:
    from tools.export_pypsa import build_network
    n = build_network("data_indonesia/2030/sulawesi", mode="dispatch")

Two modes:
  * mode="dispatch" (default) — capacity fixed to the EXISTING fleet (New_Build==1
    candidates -> 0), matching functions/dispatch_engine.jl. This is the path the
    parity check validates (tools/validate_pypsa_parity.py).
  * mode="expansion" — new-build units are extendable up to Max_Cap_MW with their
    investment cost, for users who want to run a PyPSA capacity expansion. This is
    a faithful-as-possible translation, NOT bit-parity with garuda's UC-MILP.

SCOPE (v1, mirrors the roadmap): the zonal GRID layer only — buses, lines,
generators, loads, storage, snapshots. The decentralised village/site layer
(village_*/ip_* files) is intentionally out of scope here; it is a separate
sub-problem in the source model and is documented as a boundary in
docs/pypsa_export.md.

KNOWN FIDELITY GAPS (see docs/pypsa_export.md for the full list):
  * Transport vs KVL — garuda's network is a transport model (the DC-power-flow /
    susceptance block is commented out in optimizer.jl), so lines map to
    bidirectional, lossless PyPSA *links* bounded by Line_Max_Flow_MW, NOT
    angle-constrained Lines. Line_Loss_Percentage is not in garuda's balance.
  * Unit commitment — exported generators are continuous (no binary commitment,
    min-up/down or start costs). This matches garuda's default LP-relaxed dispatch
    (relax_uc=true), where min-power is non-binding; it does not capture an exact
    UC (MILP) dispatch or its start costs.
  * Storage discharge — garuda caps storage CHARGE at the power rating but not
    discharge (only by available energy); PyPSA caps both at p_nom. Immaterial for
    the parity datasets, where every battery is a New_Build candidate (-> 0 MW in
    dispatch).
  * Representative-period storage — garuda makes each storage SOC cyclic *within*
    each representative period (cSOCWrap). The export concatenates the periods and
    makes SOC cyclic over the whole horizon (PyPSA's cyclic_state_of_charge); this
    is the standard representative-period simplification and only affects the
    expansion mode (storage is 0 MW in the validated dispatch mode).

Runs on Python + pandas/numpy + pypsa. pypsa is imported lazily, so the pure-data
helpers here are importable without it.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

try:
    import numpy as np
    import pandas as pd
except ImportError:  # pragma: no cover
    print("export_pypsa requires pandas + numpy", file=sys.stderr)
    sys.exit(3)

# utf-8-sig strips the BOM some inputs carry; keep_default_na=False preserves the
# literal fuel "None" (pandas would read it as NaN) — mirrors the other tools.
NA = dict(keep_default_na=False, na_values=[""])
ANNUAL_HOURS = 8760.0


def _read(path):
    return pd.read_csv(path, encoding="utf-8-sig", **NA)


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _carrier(resource, vre, stor):
    """A coarse PyPSA carrier label from the resource name / flags."""
    if stor:
        return "battery"
    r = str(resource).lower()
    if vre:
        if any(k in r for k in ("solar", "plts", "surya", "pv")):
            return "solar"
        if any(k in r for k in ("wind", "angin", "bayu", "pltb")):
            return "wind"
        return "vre"
    if any(k in r for k in ("hydro", "plta", "air")):
        return "hydro"
    if any(k in r for k in ("geo", "pltp", "panas")):
        return "geothermal"
    if "coal" in r or "batubara" in r or "pltu" in r:
        return "coal"
    if "gas" in r or "pltg" in r or "pltgu" in r or "lng" in r:
        return "gas"
    if "diesel" in r or "pltd" in r or "hsd" in r or "mfo" in r:
        return "diesel"
    return "thermal"


def zone_names(folder):
    """zone integer -> human-readable name from the optional zones.csv."""
    p = os.path.join(folder, "zones.csv")
    names = {}
    if os.path.isfile(p):
        z = _read(p)
        cols = {c.lower().lstrip("﻿").strip(): c for c in z.columns}
        zc = cols.get("zone")
        nc = cols.get("province") or cols.get("zone_name") or cols.get("name") or cols.get("system")
        if zc and nc:
            for _, r in z.iterrows():
                m = re.search(r"\d+", str(r[zc]))
                if m:
                    names[int(m.group())] = str(r[nc])
    return names


def time_structure(demand):
    """(P, H, T, sample_weight[T]) from demand.csv — mirrors input_data.jl.

    sample_weight[t] = W[p]/H so it sums to ΣW = 8760 and annualises the
    representative periods. This is PyPSA's snapshot objective weighting.
    """
    P = int(_num(demand["Rep_Periods"]).dropna().iloc[0])
    H = int(_num(demand["Timesteps_per_Rep_Period"]).dropna().iloc[0])
    W = _num(demand["Sub_Weights"]).dropna().to_numpy()[:P]
    T = P * H
    sample_weight = np.repeat(W / H, H)[:T]
    return P, H, T, sample_weight


def _fuel_maps(fuels):
    cost = dict(zip(fuels["Fuel"].astype(str), _num(fuels["Cost_per_MMBtu"]).fillna(0.0)))
    co2 = dict(zip(fuels["Fuel"].astype(str), _num(fuels["CO2_content_tons_per_MMBtu"]).fillna(0.0)))
    return cost, co2


def _var_cost(row, fuel_cost):
    # $/MWh = Var_OM + fuel $/MMBtu * heat rate MMBtu/MWh  (input_data.jl)
    return float(_num(pd.Series([row.get("Var_OM_Cost_per_MWh", 0)])).fillna(0.0).iloc[0]) + \
        fuel_cost.get(str(row.get("Fuel")), 0.0) * float(_num(pd.Series([row.get("Heat_Rate_MMBTU_per_MWh", 0)])).fillna(0.0).iloc[0])


def _co2_rate(row, fuel_co2):
    return fuel_co2.get(str(row.get("Fuel")), 0.0) * float(_num(pd.Series([row.get("Heat_Rate_MMBTU_per_MWh", 0)])).fillna(0.0).iloc[0])


def build_network(folder, mode="dispatch"):
    """Build and return a pypsa.Network from a garuda input folder.

    mode: "dispatch" (existing fleet fixed) or "expansion" (new-build extendable).

    Snapshots are a flat hourly index over the concatenated representative periods;
    storage is made cyclic over the whole horizon (see the module docstring on the
    representative-period simplification).
    """
    import pypsa  # lazy: keeps the data helpers importable without pypsa

    if mode not in ("dispatch", "expansion"):
        raise ValueError(f"mode must be 'dispatch' or 'expansion', got {mode!r}")

    gens = _read(os.path.join(folder, "generators.csv"))
    demand = _read(os.path.join(folder, "demand.csv"))
    var = _read(os.path.join(folder, "generators_variability.csv")).iloc[:, 1:]  # drop hour index
    fuels = _read(os.path.join(folder, "fuels_data.csv"))
    fuel_cost, fuel_co2 = _fuel_maps(fuels)
    znames = zone_names(folder)

    P, H, T, sample_weight = time_structure(demand)

    n = pypsa.Network()
    n.name = f"garuda:{os.path.basename(os.path.normpath(folder))}:{mode}"

    # --- snapshots + annualising weightings ---------------------------------
    n.set_snapshots(pd.RangeIndex(1, T + 1, name="snapshot"))

    # objective: weight variable/NSE costs by the hours each period represents.
    # stores: each timestep is 1 real hour for the SOC dynamics (NOT sample_weight)
    # so the hourly SOC recursion matches garuda's cSOC. generators: weight energy
    # accounting the same as the objective.
    n.snapshot_weightings.loc[:, "objective"] = sample_weight
    n.snapshot_weightings.loc[:, "generators"] = sample_weight
    n.snapshot_weightings.loc[:, "stores"] = 1.0

    Z = sorted(int(z) for z in _num(gens["Zone"]).dropna().unique())

    # --- carriers (so PyPSA consistency checks are quiet & for grouping) -----
    n.add("Carrier", "AC")
    for c in ("solar", "wind", "vre", "hydro", "geothermal", "coal", "gas",
              "diesel", "thermal", "battery", "load_shedding"):
        n.add("Carrier", c)

    # --- buses (one per zone) -----------------------------------------------
    bus = {z: f"zone_{z}" + (f"_{znames[z]}" if z in znames else "") for z in Z}
    for z in Z:
        n.add("Bus", bus[z], carrier="AC", v_nom=1.0)

    # --- loads (zonal demand) -----------------------------------------------
    for z in Z:
        col = f"demand_z{z}"
        p_set = _num(demand[col]).to_numpy()[:T]
        n.add("Load", f"load_z{z}", bus=bus[z], p_set=pd.Series(p_set, index=n.snapshots))

    # --- transmission network -> bidirectional, lossless links --------------
    npath = os.path.join(folder, "network.csv")
    if os.path.isfile(npath):
        net = _read(npath)
        for _, ln in net.iterrows():
            inc = {z: _num(pd.Series([ln.get(f"z{z}", 0)])).fillna(0.0).iloc[0] for z in Z}
            src = [z for z in Z if inc[z] == 1]    # power leaves the +1 zone...
            dst = [z for z in Z if inc[z] == -1]   # ...and enters the -1 zone
            if len(src) != 1 or len(dst) != 1:
                # skip malformed incidence rows (validate_schema flags these)
                continue
            cap = float(_num(pd.Series([ln.get("Line_Max_Flow_MW", 0)])).fillna(0.0).iloc[0])
            name = str(ln.get("path_name") or f"line_{ln.get('r_id')}")
            kw = dict(bus0=bus[src[0]], bus1=bus[dst[0]], carrier="AC",
                      p_min_pu=-1.0, p_max_pu=1.0, efficiency=1.0)
            if mode == "expansion":
                reinf = float(_num(pd.Series([ln.get("Line_Max_Reinforcement_MW", 0)])).fillna(0.0).iloc[0])
                cc = float(_num(pd.Series([ln.get("Line_Reinforcement_Cost_per_MWyr", 0)])).fillna(0.0).iloc[0])
                n.add("Link", name, p_nom=cap, p_nom_extendable=True,
                      p_nom_min=cap, p_nom_max=cap + reinf, capital_cost=cc, **kw)
            else:
                n.add("Link", name, p_nom=cap, p_nom_extendable=False, **kw)

    # --- generators & storage ------------------------------------------------
    nser = var.shape[1]
    for _, row in gens.iterrows():
        rid = int(row["R_ID"])
        z = int(_num(pd.Series([row["Zone"]])).iloc[0])
        is_stor = _num(pd.Series([row.get("STOR", 0)])).fillna(0).astype(int).iloc[0] >= 1
        is_vre = _num(pd.Series([row.get("VRE", 0)])).fillna(0).astype(int).iloc[0] == 1
        is_new = _num(pd.Series([row.get("New_Build", 0)])).fillna(0).astype(int).iloc[0] == 1
        commit = _num(pd.Series([row.get("Commit", 0)])).fillna(0).astype(int).iloc[0]
        exist_mw = float(_num(pd.Series([row.get("Existing_Cap_MW", 0)])).fillna(0.0).iloc[0])
        carrier = _carrier(row.get("Resource"), is_vre, is_stor)
        mc = _var_cost(row, fuel_cost)
        name = f"{carrier}_{rid}_{re.sub(r'[^A-Za-z0-9]+', '_', str(row.get('Resource', '')))[:24]}"

        if is_stor:
            eff_up = float(_num(pd.Series([row.get("Eff_Up", 1)])).fillna(1.0).iloc[0])
            eff_dn = float(_num(pd.Series([row.get("Eff_Down", 1)])).fillna(1.0).iloc[0])
            exist_mwh = float(_num(pd.Series([row.get("Existing_Cap_MWh", 0)])).fillna(0.0).iloc[0])
            if mode == "dispatch":
                p_nom = 0.0 if is_new else exist_mw            # New_Build candidate -> 0
                mh = (exist_mwh / exist_mw) if (not is_new and exist_mw > 0) else 1.0
                n.add("StorageUnit", name, bus=bus[z], carrier="battery",
                      p_nom=p_nom, p_nom_extendable=False, max_hours=mh,
                      efficiency_store=eff_up, efficiency_dispatch=eff_dn,
                      marginal_cost=mc, cyclic_state_of_charge=True)
            else:
                # extendable new-build battery (MW); energy tied via max_hours.
                cc = float(_num(pd.Series([row.get("Inv_Cost_per_MWyr", 0)])).fillna(0.0).iloc[0]) + \
                    float(_num(pd.Series([row.get("Fixed_OM_Cost_per_MWyr", 0)])).fillna(0.0).iloc[0])
                maxmw = float(_num(pd.Series([row.get("Max_Cap_MW", 0)])).fillna(0.0).iloc[0])
                mh = (exist_mwh / exist_mw) if exist_mw > 0 else 4.0
                kw = dict(p_nom_extendable=is_new, capital_cost=cc)
                if is_new and maxmw > 0:
                    kw["p_nom_max"] = maxmw
                n.add("StorageUnit", name, bus=bus[z], carrier="battery",
                      p_nom=0.0 if is_new else exist_mw, max_hours=mh,
                      efficiency_store=eff_up, efficiency_dispatch=eff_dn,
                      marginal_cost=mc, cyclic_state_of_charge=True, **kw)
            continue

        # --- conventional / VRE generator ---
        # garuda applies the per-hour variability profile (cMaxPowerED) to every
        # economic-dispatch unit (Commit==0) — VRE *and* derated thermal — while
        # unit-commitment units (Commit==1) are capped by Existing_Cap·COMMIT, with
        # no variability term. Key the availability on Commit, not the VRE flag, so
        # a thermal ED unit with a <1.0 availability column is not over-stated.
        if commit == 0:
            col = rid - 1
            prof = var.iloc[:T, col].to_numpy() if 0 <= col < nser else np.ones(T)
            p_max_pu = pd.Series(np.clip(prof.astype(float), 0.0, 1.0), index=n.snapshots)
        else:
            p_max_pu = 1.0  # UC unit: capped by Existing_Cap·COMMIT (LP-relaxed -> [0, p_nom])

        co2 = _co2_rate(row, fuel_co2)
        if mode == "dispatch":
            p_nom = 0.0 if is_new else exist_mw
            n.add("Generator", name, bus=bus[z], carrier=carrier, p_nom=p_nom,
                  p_nom_extendable=False, marginal_cost=mc, p_max_pu=p_max_pu,
                  efficiency=1.0)
        else:
            cc = float(_num(pd.Series([row.get("Inv_Cost_per_MWyr", 0)])).fillna(0.0).iloc[0]) + \
                float(_num(pd.Series([row.get("Fixed_OM_Cost_per_MWyr", 0)])).fillna(0.0).iloc[0])
            maxmw = float(_num(pd.Series([row.get("Max_Cap_MW", 0)])).fillna(0.0).iloc[0])
            kw = dict(p_nom_extendable=is_new, capital_cost=cc)
            if is_new and maxmw > 0:
                kw["p_nom_max"] = maxmw
            n.add("Generator", name, bus=bus[z], carrier=carrier,
                  p_nom=0.0 if is_new else exist_mw, marginal_cost=mc,
                  p_max_pu=p_max_pu, efficiency=1.0, **kw)

    # --- non-served energy as per-segment load-shedding generators ----------
    voll = float(_num(pd.Series([demand["Voll"].iloc[0]])).fillna(0.0).iloc[0])
    seg = _num(demand["Demand_Segment"]).dropna().astype(int).tolist()
    seg_cost = _num(demand["Cost_of_Demand_Curtailment_per_MW"]).dropna().to_numpy()
    seg_max = _num(demand["Max_Demand_Curtailment"]).dropna().to_numpy()
    for i, s in enumerate(seg):
        nse_cost = voll * float(seg_cost[i])
        frac = float(seg_max[i])  # fraction of demand curtailable in this segment
        for z in Z:
            dz = _num(demand[f"demand_z{z}"]).to_numpy()[:T]
            pnom = float(np.max(dz)) if len(dz) else 0.0
            if pnom <= 0:
                continue
            pmax = pd.Series(np.clip(frac * dz / pnom, 0.0, 1.0), index=n.snapshots)
            n.add("Generator", f"nse_z{z}_s{s}", bus=bus[z], carrier="load_shedding",
                  p_nom=pnom, p_nom_extendable=False, marginal_cost=nse_cost,
                  p_max_pu=pmax, efficiency=1.0)

    return n


def main(argv):
    ap = argparse.ArgumentParser(description="Export a garuda input folder to a PyPSA network.")
    ap.add_argument("folder")
    ap.add_argument("--mode", choices=("dispatch", "expansion"), default="dispatch",
                    help="dispatch = existing fleet fixed (default); expansion = new-build extendable")
    ap.add_argument("--netcdf", help="write the network to this .nc file")
    args = ap.parse_args(argv[1:])

    n = build_network(args.folder, mode=args.mode)
    print(f"PyPSA network — {n.name}")
    print(f"  buses        {len(n.buses)}")
    print(f"  links        {len(n.links)}")
    print(f"  generators   {len(n.generators)} "
          f"({int((n.generators.carrier == 'load_shedding').sum())} load-shedding)")
    print(f"  storage      {len(n.storage_units)}")
    print(f"  loads        {len(n.loads)}")
    print(f"  snapshots    {len(n.snapshots)}  (Σweight = {n.snapshot_weightings.objective.sum():.1f} h)")
    if args.netcdf:
        n.export_to_netcdf(args.netcdf)
        print(f"\nwrote {args.netcdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
