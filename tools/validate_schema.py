#!/usr/bin/env python3
"""Schema validator for garuda zonal-model input folders.

Catches the structural errors that otherwise surface as cryptic Julia
BoundsError / KeyError *during* an expensive solve — R_ID gaps, wrong row
counts, misaligned zones, a Sub_Weights sum that does not annualise, missing
fuels, bad network incidence — and reports them up front.

Standalone:
    python tools/validate_schema.py data_indonesia/2030/timor_demo
Importable:
    from tools.validate_schema import validate_dataset
    errors, warnings = validate_dataset(folder)

Exit code is 0 when there are no errors (warnings are allowed), 1 otherwise, so
preflight.jl can shell out to it and gate a run.
"""
from __future__ import annotations

import os
import sys

try:
    import pandas as pd
except ImportError:  # exit 3 (not 1) so callers can tell "can't run" from "found errors"
    print("schema validation unavailable: pandas not installed", file=sys.stderr)
    sys.exit(3)

# Canonical platform term is `site`; village_* / ip_* are accepted aliases
# (mirrors functions/site_aliases.jl).
SITE_PREFIXES = ("site", "village", "ip")
SITE_ID_COLS = ("Site", "Village", "Industrial_Park")
ANNUAL_HOURS = 8760
TOL = 1e-6


def _read(path: str) -> pd.DataFrame:
    # utf-8-sig strips a leading BOM some files carry on the first column name.
    # keep_default_na=False preserves the literal fuel "None" as a string (pandas
    # would otherwise read it as NaN); only genuinely empty cells become NaN.
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def _first_scalar(df: pd.DataFrame, col: str):
    s = df[col].dropna()
    return s.iloc[0] if len(s) else None


def _resolve_site_csv(folder: str, base: str):
    for p in SITE_PREFIXES:
        f = os.path.join(folder, f"{p}_{base}.csv")
        if os.path.isfile(f):
            return f, p
    return None, None


def _site_id_col(df: pd.DataFrame):
    for c in SITE_ID_COLS:
        if c in df.columns:
            return c
    return None


def validate_dataset(folder: str):
    """Return (errors, warnings) for the input folder. Empty errors == valid."""
    errors: list[str] = []
    warnings: list[str] = []

    def err(msg):
        errors.append(msg)

    def warn(msg):
        warnings.append(msg)

    if not os.path.isdir(folder):
        return [f"input folder not found: {folder}"], warnings

    core = ["generators.csv", "demand.csv", "generators_variability.csv", "fuels_data.csv"]
    for f in core:
        if not os.path.isfile(os.path.join(folder, f)):
            err(f"missing required file: {f}")
    if errors:  # cannot proceed without the core files
        return errors, warnings

    gens = _read(os.path.join(folder, "generators.csv"))
    demand = _read(os.path.join(folder, "demand.csv"))
    var = _read(os.path.join(folder, "generators_variability.csv"))
    fuels = _read(os.path.join(folder, "fuels_data.csv"))

    # ---- fuels_data.csv -------------------------------------------------
    for c in ("Fuel", "Cost_per_MMBtu", "CO2_content_tons_per_MMBtu"):
        if c not in fuels.columns:
            err(f"fuels_data.csv: missing column '{c}'")
    fuel_names = set()
    if "Fuel" in fuels.columns:
        fuel_names = set(fuels["Fuel"].astype(str))
        if "None" not in fuel_names:
            err("fuels_data.csv: must include a 'None' fuel row (fuel-free units reference it)")
        dups = fuels["Fuel"][fuels["Fuel"].duplicated()].tolist()
        if dups:
            err(f"fuels_data.csv: duplicate Fuel rows: {sorted(set(dups))}")

    # ---- generators.csv -------------------------------------------------
    for c in ("R_ID", "Zone", "Fuel", "Commit", "New_Build", "Existing_Cap_MW"):
        if c not in gens.columns:
            err(f"generators.csv: missing column '{c}'")
    zones = []
    if "R_ID" in gens.columns:
        rid = list(gens["R_ID"])
        expected = list(range(1, len(rid) + 1))
        if rid != expected:
            err("generators.csv: R_ID must be the consecutive integers 1..N in row "
                f"order (it is used directly as an array index). Got {rid[:8]}{'...' if len(rid) > 8 else ''}")
    if "Zone" in gens.columns:
        z = pd.to_numeric(gens["Zone"], errors="coerce")
        if z.isna().any():
            err("generators.csv: Zone must be integers")
        else:
            zones = sorted(set(int(v) for v in z))
    if "Fuel" in gens.columns and fuel_names:
        unknown = sorted(set(gens["Fuel"].astype(str)) - fuel_names)
        if unknown:
            err(f"generators.csv: Fuel value(s) not in fuels_data.csv: {unknown}")
    # NB: Commit / New_Build carry sentinel values beyond {0,1} in real data
    # (e.g. Commit=2, New_Build=-1), interpreted by the loader's ==1 / !=1 tests,
    # so they are intentionally NOT constrained to 0/1 here.
    if {"Commit", "Existing_Cap_MW"} <= set(gens.columns):
        commit = pd.to_numeric(gens["Commit"], errors="coerce")
        cap = pd.to_numeric(gens["Existing_Cap_MW"], errors="coerce")
        offenders = gens["R_ID"][(commit == 1) & (~(cap > 0))].tolist()
        if offenders:
            err("generators.csv: unit-commitment rows (Commit=1) must have Existing_Cap_MW>0 "
                f"(the model divides by it). Offending R_ID: {offenders}")
    if "Max_Cap_MW" not in gens.columns:
        warn("generators.csv: no Max_Cap_MW column (new-build capacity will be unbounded)")

    # ---- demand.csv: time structure ------------------------------------
    P = H = T = None
    for c in ("Rep_Periods", "Timesteps_per_Rep_Period", "Sub_Weights", "r_id"):
        if c not in demand.columns:
            err(f"demand.csv: missing column '{c}'")
    if {"Rep_Periods", "Timesteps_per_Rep_Period"} <= set(demand.columns):
        P = _first_scalar(demand, "Rep_Periods")
        H = _first_scalar(demand, "Timesteps_per_Rep_Period")
        if P is not None and H is not None:
            P, H = int(P), int(H)
            T = P * H
            if len(demand) != T:
                err(f"demand.csv: has {len(demand)} rows but Rep_Periods×Timesteps "
                    f"= {P}×{H} = {T}; every hourly file must have exactly {T} rows")
    if "Sub_Weights" in demand.columns and P is not None:
        w = pd.to_numeric(demand["Sub_Weights"], errors="coerce").dropna()
        if len(w) != P:
            err(f"demand.csv: Sub_Weights has {len(w)} values but Rep_Periods={P}")
        if abs(w.sum() - ANNUAL_HOURS) > 0.5:
            err(f"demand.csv: Sub_Weights sum to {w.sum():.3f}, must sum to {ANNUAL_HOURS} "
                "(they annualise the representative periods)")
    for z in zones:
        if f"demand_z{z}" not in demand.columns:
            err(f"demand.csv: missing demand column 'demand_z{z}' for zone {z} (zones come from generators.Zone)")
    if "Voll" in demand.columns:
        voll = _first_scalar(demand, "Voll")
        if voll is None or float(voll) <= 0:
            warn("demand.csv: Voll (value of lost load) is missing or non-positive")

    # ---- generators_variability.csv ------------------------------------
    if T is not None and len(var) != T:
        err(f"generators_variability.csv: has {len(var)} rows; must equal the {T} time steps in demand.csv")
    data_cols = var.columns[1:]  # first column is the hour index
    vnum = var[data_cols].apply(pd.to_numeric, errors="coerce")
    if ((vnum < -TOL) | (vnum > 1 + 1e-4)).any().any():
        err("generators_variability.csv: capacity factors must lie in [0, 1]")

    # ---- network.csv (optional; required for grid scenarios) -----------
    npath = os.path.join(folder, "network.csv")
    if os.path.isfile(npath):
        net = _read(npath)
        for z in zones:
            zc = f"z{z}"
            if zc not in net.columns:
                err(f"network.csv: missing incidence column '{zc}' for zone {z}")
            else:
                bad = set(pd.to_numeric(net[zc], errors="coerce").dropna().unique()) - {-1, 0, 1}
                if bad:
                    err(f"network.csv: incidence column '{zc}' must be -1/0/1; found {sorted(bad)}")
        if "Line_Max_Flow_MW" not in net.columns:
            err("network.csv: missing column 'Line_Max_Flow_MW'")

    # ---- site files (site_/village_/ip_), optional ---------------------
    sgen_path, prefix = _resolve_site_csv(folder, "generators")
    if sgen_path is not None:
        sgen = _read(sgen_path)
        base = os.path.basename(sgen_path)
        idcol = _site_id_col(sgen)
        if idcol is None:
            err(f"{base}: needs a site-identifier column (one of {SITE_ID_COLS})")
        site_ids = []
        if idcol is not None:
            site_ids = sorted(set(int(v) for v in pd.to_numeric(sgen[idcol], errors="coerce").dropna()))
        if "R_ID" in sgen.columns:
            rid = list(sgen["R_ID"])
            if rid != list(range(1, len(rid) + 1)):
                err(f"{base}: R_ID must be the consecutive integers 1..N in row order")
        if "Max_Cap_MW" not in sgen.columns:
            warn(f"{base}: no Max_Cap_MW column (site new-build capacity will be unbounded)")
        # site demand columns
        sdem_path, dpref = _resolve_site_csv(folder, "demand")
        if sdem_path is None:
            err(f"{base} present but no site demand file (expected {prefix}_demand.csv)")
        else:
            sdem = _read(sdem_path)
            for i in site_ids:
                if not any(f"demand_{p}{i}" in sdem.columns for p in SITE_PREFIXES):
                    err(f"{os.path.basename(sdem_path)}: missing demand column for site {i} "
                        f"(expected demand_{prefix}{i})")
        svar_path, _ = _resolve_site_csv(folder, "generators_variability")
        if svar_path is not None and T is not None:
            svar = _read(svar_path)
            if len(svar) != T:
                err(f"{os.path.basename(svar_path)}: has {len(svar)} rows; must equal {T} time steps")

    return errors, warnings


def main(argv):
    if len(argv) != 2:
        print("usage: python tools/validate_schema.py <input_folder>", file=sys.stderr)
        return 2
    folder = argv[1]
    errors, warnings = validate_dataset(folder)
    for w in warnings:
        print(f"  warning: {w}")
    for e in errors:
        print(f"  ERROR:   {e}")
    if errors:
        print(f"\nFAIL: {len(errors)} error(s), {len(warnings)} warning(s) in {folder}")
        return 1
    print(f"OK: schema valid ({len(warnings)} warning(s)) — {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
