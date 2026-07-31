#!/usr/bin/env python3
"""Coordination value — the site-vs-coordinated delta as one command.

Garuda's headline claim is that co-optimising village solar+storage+diesel *with*
the zonal grid's expansion and dispatch reveals a **coordination value**: the
system cost, diesel, emissions and unserved energy avoided when the two are
planned together instead of separately. Until now that meant running two
scenarios and diffing the result CSVs by hand. This tool does it in one step.

    # compare two runs you already have:
    python tools/coordination_value.py compare \
        results/village_timor_demo_2030_reference \
        results/gridvillage_timor_demo_2030_reference

    # or scaffold + solve both scenarios (HiGHS, licence-free) then compare:
    python tools/coordination_value.py run --island timor_demo --year 2030

**Coordination value** = ``Total_Costs(reference plan) − Total_Costs(coordinated
gridvillage plan)`` in M$/yr, for the same island, year, clean case, engine and
solver settings. Because the coordinated model's feasible set contains the
standalone one (a village can always decline to connect at zero extra cost), the
value is non-negative for optimal same-engine pairs, up to the solver gap.

It is NOT a welfare or benefit–cost measure (no tariffs, no distributional
effects), not carbon-priced (reference runs carry no CO₂ price), and it excludes
distribution-network detail below the modelled village interconnection. Under
``relax_uc`` both plans are LP lower bounds (measured UC gap ≈0.8 %), so a value
smaller than ~1 % of total cost is indistinguishable from zero. A dispatch-engine
pair measures operations-only value (no new build).

Runs on Python + pandas. The ``run`` subcommand additionally needs Julia + the
project (it reuses tools/launcher.py, which shells out to run_model.jl).

Note for tools/report.py: this writes ``coordination_value.csv`` into the
coordinated run's directory, where report.py's load_results() already picks up
every ``*.csv`` — a future report can surface it without extra plumbing.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

try:
    import pandas as pd
    import numpy as np
except ImportError:  # pragma: no cover
    print("coordination_value requires pandas + numpy", file=sys.stderr)
    sys.exit(3)

try:
    from tools.export_pypsa import time_structure, _read
    from tools.report import parse_scenario
    from tools.launcher import main as launcher_main
except ImportError:  # pragma: no cover
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from export_pypsa import time_structure, _read
    from report import parse_scenario
    from launcher import main as launcher_main

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# scenarios that legitimately sit on each side of a coordination comparison
REF_SCENARIOS = {"base", "grid", "village", "captive"}
COORD_SCENARIOS = {"gridvillage", "gridcaptive"}

# canonical site-table prefixes, canonical first (mirrors functions/site_aliases.jl)
SITE_PREFIXES = ("site", "village", "ip")


# --------------------------------------------------------------------------- IO

def _read_csv(path):
    """Read a result CSV, or return None if absent/empty (header-only counts)."""
    if not os.path.isfile(path):
        return None
    try:
        df = _read(path)
    except Exception:
        return None
    return df if len(df) else None


def _site_csv(run_dir, base):
    """Resolve <prefix>_<base>.csv in run_dir by site-alias precedence."""
    for pfx in SITE_PREFIXES:
        p = os.path.join(run_dir, f"{pfx}_{base}.csv")
        if os.path.isfile(p):
            return p
    return None


def _num(s):
    return pd.to_numeric(s, errors="coerce")


# ----------------------------------------------------------------- annualisation

def annualisation(meta, data_root, quiet=False):
    """Return (factor, note): a rep-period-sum → annual multiplier 8760/T.

    Exact when Sub_Weights are uniform (e.g. timor_demo); approximate otherwise
    (e.g. maluku). Falls back to 8760/1344 with a louder note if demand.csv can't
    be read.
    """
    folder = os.path.join(data_root, meta.get("year", ""), meta.get("island", ""))
    demand_path = os.path.join(folder, "demand.csv")
    try:
        demand = _read(demand_path)
        P, H, T, sw = time_structure(demand)
        factor = 8760.0 / T
        weights = _num(demand["Sub_Weights"]).dropna().to_numpy()[:P]
        uniform = np.allclose(weights, weights[0]) if len(weights) else True
        if uniform:
            note = f"annualised ×{factor:.4f} (=8760/{T}; uniform Sub_Weights — exact)"
        else:
            note = (f"annualised ×{factor:.4f} (=8760/{T}; Sub_Weights are NON-uniform "
                    f"— APPROXIMATE for rep-period sums)")
        return factor, note
    except Exception as exc:
        factor = 8760.0 / 1344.0
        note = (f"annualised ×{factor:.4f} (fallback 8760/1344 — could not read "
                f"{demand_path}: {exc})")
        if not quiet:
            print(f"  warning: {note}", file=sys.stderr)
        return factor, note


# ------------------------------------------------------------------- run metrics

def _sidecar_cfg(run_dir, meta):
    sidecar = os.path.join(os.path.dirname(os.path.normpath(run_dir)),
                           meta["name"] + ".config.json")
    if os.path.isfile(sidecar):
        try:
            with open(sidecar) as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


def infer_engine(run_dir, meta):
    """dispatch | expansion | unknown. Config sidecar wins; else infer."""
    eng = _sidecar_cfg(run_dir, meta).get("engine")
    if eng in ("dispatch", "expansion"):
        return eng
    # infer: a *fresh* reliability_results.csv is the dispatch-only signature
    rel = os.path.join(run_dir, "reliability_results.csv")
    cost = os.path.join(run_dir, "cost_results.csv")
    if os.path.isfile(rel) and os.path.isfile(cost):
        if abs(os.path.getmtime(rel) - os.path.getmtime(cost)) <= 3600:
            return "dispatch"
    return "expansion"


def _diesel_gwh(gen_df, gwh_col):
    """Sum the generation column over diesel rows (technology, else pltd_ prefix)."""
    if gen_df is None or gwh_col not in gen_df.columns:
        return 0.0
    tech = gen_df.get("technology")
    if tech is not None:
        mask = tech.astype(str).str.lower().str.contains("diesel", na=False)
    else:
        mask = gen_df.get("Resource", pd.Series("", index=gen_df.index)) \
                     .astype(str).str.lower().str.startswith("pltd")
    return float(_num(gen_df.loc[mask, gwh_col]).sum())


def load_metrics(run_dir, data_root, no_annualise=False):
    """Return (meta, metrics dict, notes list) for one results dir."""
    meta = parse_scenario(run_dir)
    meta["engine"] = infer_engine(run_dir, meta)
    sidecar = _sidecar_cfg(run_dir, meta)
    meta["export_price"] = sidecar.get("export_price", 0.0)
    meta["policy_scope"] = sidecar.get("policy_scope", "grid")
    notes = []
    # Energy columns in the result CSVs are ALREADY annual: since the
    # sample-weight fix, result_extraction_function.jl weights every rep-period
    # energy sum by sample_weight. Applying an 8760/T factor here would
    # double-count it (6.518x on Timor). Kept as an explicit 1.0 so the reason is
    # visible rather than implied by absence.
    factor = 1.0
    anote = ("energy columns read as annual (result extraction applies "
             "sample_weight; no post-hoc 8760/T factor)")
    if no_annualise:
        anote += " — --no-annualise no longer has an effect and is deprecated"
    notes.append(anote)
    m = {}

    cost = _read_csv(os.path.join(run_dir, "cost_results.csv"))
    if cost is not None:
        row = cost.iloc[0]
        for c in cost.columns:
            m[f"cost.{c}"] = float(_num(pd.Series([row[c]])).iloc[0])

    clean = _read_csv(os.path.join(run_dir, "clean_energy_results.csv"))
    if clean is not None:
        row = clean.iloc[0]
        for c in ("CO2_Emissions", "CO2_Emissions_Grid", "CO2_Emissions_Village",
                  "Grid_REShare"):
            if c in clean.columns:
                m[c] = float(_num(pd.Series([row[c]])).iloc[0])

    # generation (rep-period sums -> annualise)
    gen = _read_csv(os.path.join(run_dir, "generator_results.csv"))
    m["grid_diesel_gwh"] = _diesel_gwh(gen, "GWh") * factor
    if gen is not None and "THERM" in gen.columns and "GWh" in gen.columns:
        m["grid_fossil_gwh"] = float(_num(gen.loc[_num(gen["THERM"]) == 1, "GWh"]).sum()) * factor

    sgen_path = _site_csv(run_dir, "generator_results")
    sgen = _read_csv(sgen_path) if sgen_path else None
    if sgen is None:
        notes.append("no village/site layer in this run (site tables absent or header-only)")
    else:
        col = "Electricity_GWh" if "Electricity_GWh" in sgen.columns else "GWh"
        m["site_diesel_gwh"] = _diesel_gwh(sgen, col) * factor
        if "Change_in_MW" in sgen.columns:
            tech = sgen.get("technology", pd.Series("", index=sgen.index)).astype(str).str.lower()
            chg = _num(sgen["Change_in_MW"])
            m["site_solar_built_mw"] = float(chg[(chg > 0) & tech.str.contains("solar", na=False)].sum())

    sstor_path = _site_csv(run_dir, "storage_results")
    sstor = _read_csv(sstor_path) if sstor_path else None
    if sstor is not None and "Change_in_Storage_MWh" in sstor.columns:
        chg = _num(sstor["Change_in_Storage_MWh"])
        m["site_battery_built_mwh"] = float(chg[chg > 0].sum())

    trans = _read_csv(os.path.join(run_dir, "transmission_results.csv"))
    if trans is not None and "Change_in_Transfer_Capacity" in trans.columns:
        chg = _num(trans["Change_in_Transfer_Capacity"])
        m["transmission_reinforcement_mw"] = float(chg[chg > 0].sum())

    # unserved energy: prefer the annual reliability tables (dispatch); else nse (rep-period)
    rel = _read_csv(os.path.join(run_dir, "reliability_results.csv"))
    if rel is not None and "Total_NSE_MWh" in rel.columns:
        m["grid_nse_mwh"] = float(_num(rel["Total_NSE_MWh"]).sum())
        if "LOLE_hours" in rel.columns:
            m["grid_lole_hours"] = float(_num(rel["LOLE_hours"]).max())
    else:
        nse = _read_csv(os.path.join(run_dir, "nse_results.csv"))
        if nse is not None and "Total_NSE_MWh" in nse.columns:
            m["grid_nse_mwh"] = float(_num(nse["Total_NSE_MWh"]).sum()) * factor

    srel_path = _site_csv(run_dir, "reliability_results")
    srel = _read_csv(srel_path) if srel_path else None
    if srel is not None and "Total_NSE_MWh" in srel.columns:
        m["site_nse_mwh"] = float(_num(srel["Total_NSE_MWh"]).sum())
    else:
        snse_path = _site_csv(run_dir, "nse_results")
        snse = _read_csv(snse_path) if snse_path else None
        if snse is not None and "Total_NSE_MWh" in snse.columns:
            m["site_nse_mwh"] = float(_num(snse["Total_NSE_MWh"]).sum()) * factor

    conn_path = _site_csv(run_dir, "connection_results")
    conn = _read_csv(conn_path) if conn_path else None
    if conn is not None and "Connected" in conn.columns:
        m["villages_connected"] = int((_num(conn["Connected"]) > 0.5).sum())

    return meta, m, notes


# ----------------------------------------------------------------------- compare

# (metric key, label, unit, "avoided" sign) — avoided=True means positive delta
# (ref−coord) is a saving/reduction from coordination.
ROWS = [
    ("cost.Total_Costs",             "Total system cost",        "M$/yr", True),
    ("cost.Variable_Costs_Grid",     "  grid variable cost",     "M$/yr", True),
    ("cost.Fixed_Costs_Transmission","  transmission fixed cost","M$/yr", True),
    ("cost.Fixed_Costs_Village",     "  village generation capex","M$/yr", True),
    ("cost.Fixed_Costs_Village_Storage", "  village storage capex","M$/yr", True),
    ("cost.Village_Export_Revenue",  "  village export revenue", "M$/yr", False),
    ("cost.NSE_Costs",               "  grid unserved-energy cost","M$/yr", True),
    ("CO2_Emissions",                "CO₂ emissions",            "tCO₂/yr", True),
    ("grid_diesel_gwh",              "grid diesel generation",   "GWh/yr", True),
    ("site_diesel_gwh",              "village diesel generation","GWh/yr", True),
    ("grid_nse_mwh",                 "grid unserved energy",     "MWh/yr", True),
    ("site_nse_mwh",                 "village unserved energy",  "MWh/yr", True),
    ("grid_lole_hours",              "grid loss-of-load",        "h/yr",  True),
    # structural "where the money moved" rows (delta shown, not framed as saving)
    ("transmission_reinforcement_mw","transmission reinforcement","MW",  False),
    ("site_solar_built_mw",          "village solar built",      "MW",    False),
    ("site_battery_built_mwh",       "village battery built",    "MWh",   False),
    ("villages_connected",           "villages grid-connected",  "count", False),
]


def guard(ref_meta, coord_meta, allow_mismatch):
    problems = []
    for k in ("island", "year", "clean"):
        if ref_meta.get(k) != coord_meta.get(k):
            problems.append(f"{k}: {ref_meta.get(k)!r} vs {coord_meta.get(k)!r}")
    if ref_meta.get("engine") != coord_meta.get("engine"):
        problems.append(f"engine: {ref_meta.get('engine')!r} vs {coord_meta.get('engine')!r}")
    warns = []
    if ref_meta.get("scenario") not in REF_SCENARIOS:
        warns.append(f"reference scenario {ref_meta.get('scenario')!r} is not one of {sorted(REF_SCENARIOS)}")
    if coord_meta.get("scenario") not in COORD_SCENARIOS:
        warns.append(f"coordinated scenario {coord_meta.get('scenario')!r} is not one of {sorted(COORD_SCENARIOS)}")
    if ref_meta.get("export_price", 0.0) != coord_meta.get("export_price", 0.0):
        warns.append(f"export_price differs between the runs "
                     f"({ref_meta.get('export_price')} vs {coord_meta.get('export_price')}) — "
                     "the delta mixes a feed-in change into the coordination value")
    if ref_meta.get("policy_scope", "grid") != coord_meta.get("policy_scope", "grid"):
        warns.append(f"policy_scope differs between the runs "
                     f"({ref_meta.get('policy_scope')} vs {coord_meta.get('policy_scope')}) — "
                     "the delta mixes a policy-scope change into the coordination value")
    return problems, warns


def build_table(ref_m, coord_m):
    table = []
    for key, label, unit, avoided in ROWS:
        if key not in ref_m and key not in coord_m:
            continue
        r = ref_m.get(key, 0.0)
        c = coord_m.get(key, 0.0)
        table.append(dict(metric=label, unit=unit, reference=r, coordinated=c,
                          delta=r - c, avoided=avoided))
    return table


def _fmt(x):
    if isinstance(x, float):
        if abs(x) >= 1000:
            return f"{x:,.0f}"
        if abs(x) >= 1:
            return f"{x:,.2f}"
        return f"{x:.4f}"
    return str(x)


def emit_console(ref_meta, coord_meta, table, cv, notes):
    print(f"\n== coordination value — {coord_meta['island']} {coord_meta['year']} "
          f"({coord_meta['clean']}, {coord_meta['engine']}) ==")
    print(f"reference plan : {ref_meta['name']}")
    print(f"coordinated    : {coord_meta['name']}\n")
    w = max(len(r["metric"]) for r in table)
    print(f"  {'metric'.ljust(w)}  {'reference':>14}  {'coordinated':>14}  {'Δ (ref−coord)':>16}  unit")
    for r in table:
        print(f"  {r['metric'].ljust(w)}  {_fmt(r['reference']):>14}  "
              f"{_fmt(r['coordinated']):>14}  {_fmt(r['delta']):>16}  {r['unit']}")
    print(f"\n  COORDINATION VALUE = {cv:,.3f} M$/yr "
          f"({100*cv/ref_meta.get('_total', cv) if ref_meta.get('_total') else 0:.2f}% of reference cost)")
    for n in notes:
        print(f"  note: {n}")


def write_outputs(out_dir, ref_meta, coord_meta, table, cv, notes):
    os.makedirs(out_dir, exist_ok=True)
    df = pd.DataFrame([dict(Metric=r["metric"].strip(), Unit=r["unit"],
                            Reference=r["reference"], Coordinated=r["coordinated"],
                            Delta_Ref_minus_Coord=r["delta"]) for r in table])
    csv_path = os.path.join(out_dir, "coordination_value.csv")
    df.to_csv(csv_path, index=False)

    md_path = os.path.join(out_dir, "coordination_value.md")
    with open(md_path, "w") as fh:
        fh.write(f"# Coordination value — {coord_meta['island']} {coord_meta['year']}\n\n")
        fh.write(f"**{cv:,.3f} M$/yr** — the annual system-cost saving from planning "
                 f"village DRE and the zonal grid together (`{coord_meta['name']}`) "
                 f"instead of separately (`{ref_meta['name']}`), same data and solver "
                 f"settings.\n\n")
        fh.write("| Metric | Reference | Coordinated | Δ (ref−coord) | Unit |\n")
        fh.write("|---|--:|--:|--:|---|\n")
        for r in table:
            fh.write(f"| {r['metric'].strip()} | {_fmt(r['reference'])} | "
                     f"{_fmt(r['coordinated'])} | {_fmt(r['delta'])} | {r['unit']} |\n")
        fh.write("\n**Caveats.** Coordination value is a system-cost difference, not a "
                 "welfare/benefit–cost measure (no tariffs or distributional effects) and "
                 "not carbon-priced. Under `relax_uc` both plans are LP lower bounds "
                 "(UC gap ≈0.8%), so a value below ~1% of total cost is indistinguishable "
                 "from zero.\n")
        for n in notes:
            fh.write(f"\n- _{n}_")
        fh.write("\n")
    return csv_path, md_path


def compare(ref_dir, coord_dir, data_root, out_dir=None, allow_mismatch=False,
            no_annualise=False):
    ref_meta, ref_m, ref_notes = load_metrics(ref_dir, data_root, no_annualise)
    coord_meta, coord_m, coord_notes = load_metrics(coord_dir, data_root, no_annualise)

    problems, warns = guard(ref_meta, coord_meta, allow_mismatch)
    for w in warns:
        print(f"  warning: {w}", file=sys.stderr)
    if problems:
        msg = "runs are not a valid comparison pair:\n    " + "\n    ".join(problems)
        if allow_mismatch:
            print(f"  warning: {msg}", file=sys.stderr)
        else:
            print(f"  ERROR: {msg}\n  (pass --allow-mismatch to override)", file=sys.stderr)
            return 2

    if "cost.Total_Costs" not in ref_m or "cost.Total_Costs" not in coord_m:
        print("  ERROR: cost_results.csv missing Total_Costs in one or both runs",
              file=sys.stderr)
        return 2
    cv = ref_m["cost.Total_Costs"] - coord_m["cost.Total_Costs"]
    ref_meta["_total"] = ref_m["cost.Total_Costs"]

    notes = list(dict.fromkeys(ref_notes + coord_notes))
    tol = 1e-6 * abs(ref_m["cost.Total_Costs"])
    if cv < -tol:
        notes.append("coordinated plan costs MORE than the reference — check that the "
                     "two runs share engine/solver/relax_uc settings and both solved to "
                     "optimality.")

    table = build_table(ref_m, coord_m)
    emit_console(ref_meta, coord_meta, table, cv, notes)
    out = out_dir or coord_dir
    csv_path, md_path = write_outputs(out, ref_meta, coord_meta, table, cv, notes)
    print(f"\n  wrote {csv_path}\n  wrote {md_path}")
    return 0


# --------------------------------------------------------------------------- run

def _rename_aside(run_dir):
    if os.path.isdir(run_dir):
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        aside = f"{run_dir}.pre-{stamp}"
        os.rename(run_dir, aside)
        print(f"  moved existing {run_dir} -> {aside}")


def run(args):
    pair = args.pair
    coord = "gridcaptive" if pair == "captive" else "gridvillage"
    results = os.path.join(REPO_ROOT, "results")
    ref_name = f"{pair}_{args.island}_{args.year}_{args.clean}"
    coord_name = f"{coord}_{args.island}_{args.year}_{args.clean}"

    for scen, name in ((pair, ref_name), (coord, coord_name)):
        run_dir = os.path.join(results, name)
        if not args.keep_existing:
            _rename_aside(run_dir)
        argv = ["launcher", "--island", args.island, "--year", str(args.year),
                "--scenario", scen, "--clean", args.clean,
                "--engine", "expansion", "--solver", args.solver, "--run"]
        argv += ["--exact-uc"] if args.exact_uc else ["--relax-uc"]
        print(f"\n=== solving {name} ===")
        rc = launcher_main(argv)
        if rc != 0:
            print(f"  ERROR: solve for {name} exited {rc}", file=sys.stderr)
            return rc

    return compare(os.path.join(results, ref_name), os.path.join(results, coord_name),
                   args.data_root, out_dir=args.out, no_annualise=args.no_annualise)


# --------------------------------------------------------------------------- cli

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compare", help="compare two existing results directories")
    c.add_argument("ref_dir", help="the reference (standalone/grid-only) run")
    c.add_argument("coord_dir", help="the coordinated (gridvillage) run")
    c.add_argument("--data-root", default=os.path.join(REPO_ROOT, "data_indonesia"))
    c.add_argument("--out", help="artifact directory (default: coord_dir)")
    c.add_argument("--allow-mismatch", action="store_true",
                   help="downgrade island/year/engine guard failures to warnings")
    c.add_argument("--no-annualise", action="store_true",
                   help="DEPRECATED and ignored — result energy columns are annual "
                        "at source now that result extraction applies sample_weight")

    r = sub.add_parser("run", help="scaffold + solve both scenarios, then compare")
    r.add_argument("--island", required=True)
    r.add_argument("--year", default="2030")
    r.add_argument("--clean", default="reference", choices=("reference", "clean"))
    r.add_argument("--pair", default="village", choices=("village", "grid", "base", "captive"),
                   help="the reference scenario to compare against gridvillage")
    r.add_argument("--solver", default="highs", choices=("highs", "gurobi"))
    r.add_argument("--exact-uc", action="store_true",
                   help="exact UC MILP (default: relax_uc LP, fast + licence-free)")
    r.add_argument("--keep-existing", action="store_true",
                   help="do not move an existing results dir aside before solving")
    r.add_argument("--data-root", default=os.path.join(REPO_ROOT, "data_indonesia"))
    r.add_argument("--out", help="artifact directory (default: the coordinated run dir)")
    r.add_argument("--no-annualise", action="store_true")

    args = ap.parse_args(argv[1:])
    if args.cmd == "compare":
        return compare(args.ref_dir, args.coord_dir, args.data_root, args.out,
                       args.allow_mismatch, args.no_annualise)
    return run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
