"""Derive a Timor grid-zone demand series from the NTT zone-2 load, net of village load.

The shipped `timor` dataset has `demand_z1 = 0` for all 1344 hours: the grid bus
carries one PLN diesel and no load. That is fine for the coordination question
(does interconnecting villages beat islanding them?) but it makes every *export*
question unanswerable — with no grid load, the zonal balance forces
`Σ village export ≤ Σ village import` in every hour, so an export study on plain
`timor` measures a data artifact, not economics. This tool gives the grid bus a
real load so an exported village MWh can actually displace grid generation.

    # inspect the derivation without writing anything
    python -m tools.ntt.build_grid_demand --share 0.42

    # build the market dataset
    python -m tools.ntt.build_grid_demand --share 0.42 --out-dataset timor__market

**Where the load comes from.** `data_indonesia/2030/nusa_tenggara` is the only
committed dataset covering NTT, and its zone 2 is East Nusa Tenggara — the
province Timor sits in. Note the donor ships **no `zones.csv`**, so the zone
identity is not declared in a zone table; it is read from `generators.csv`'s
`Province` column (`east_nusa_tenggara` -> zone 2), falling back to
`--donor-zone` if that column is ever dropped. Earlier notes described the
identity as coming from resource naming; the `Province` column is the firmer
basis and is what this tool uses.

**Annualisation uses the donor's own `Sub_Weights`.** The donor's eight
representative weeks carry *non-uniform* weights (2022, 505, 168, 2527, 1516,
842, 337, 843 hours) while the target's are uniform (1095 each). Weighting
correctly gives **2,919 GWh/yr** for donor zone 2; treating the rep periods as
equally likely (x 8760/1344) gives **3,003 GWh/yr** — a 2.9 % overstatement that
would propagate into every downstream export number. Both are reported.

**The share is an assumption in front of the headline.** `--share` is Timor's
fraction of the East Nusa Tenggara total. 0.42 is the working central value
(PLN's Sistem Timor peak 131 MW / NTT 296.6 MW), bracketed by 0.33 (population
share) and 0.47. At 0.42 the gross Timor system is 1,226 GWh/yr and its peak is
0.42 x the donor's 419 MW = 176 MW, implying +6.1 %/yr from Timor's actual
131 MW in 2025 — consistent with Flores at 8.26 %/yr.

**Village load is netted out hour by hour.** The 780 villages (544 GWh/yr) are
already modelled as their own nodes with their own demand, and they sit *inside*
the NTT provincial total. Writing the gross Timor series into `demand_z1` would
double-count them. So `demand_z1[t] = share x donor_z2[t] - Σ village demand[t]`,
i.e. the load on the grid that the village nodes are *not* already carrying. At
0.42 that is 1,226 - 544 = **682 GWh/yr**, peaking at ~124 MW. A handful of hours
can go slightly negative (village load is a bigger share of the total at night);
those are clipped to 0 and both the count and the energy added are reported.

**A grid load alone is not enough — see `--fleet`.** `timor/generators.csv` is a
single non-expandable 122 MW diesel. Write ~180 MW of `demand_z1` against it and
the balance closes on non-served energy at `Voll x Max_Demand_Curtailment` =
$2,000/MWh, which values every exported village MWh at ~$2,000/MWh: garbage that
reads as a spectacular business case. So writing a dataset requires an explicit
`--fleet` choice, and `--fleet none` warns.

Never rewrites the base dataset: `--out-dataset` copies the base folder, patches
the copy, and runs the schema validator on it.

Runs on Python + pandas; no solver.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from tools.validate_schema import validate_dataset
except ImportError:  # pragma: no cover - direct-script invocation
    sys.path.insert(0, REPO)
    from tools.validate_schema import validate_dataset

NA = dict(encoding="utf-8-sig", keep_default_na=False, na_values=[""])

DONOR_PROVINCE = "east_nusa_tenggara"

# Existing donor zone-2 units that physically sit on Timor. The rest of the
# existing zone-2 fleet (pltu_ende_ftp1 on Flores, pltu_alor, pltu_rote_ndao) is
# on other islands in the same province and cannot serve the Timor grid, so
# `--existing named` carries these at 100 % and drops the others rather than
# giving Timor a fraction of every plant in the province.
TIMOR_EXISTING = ("pltu_kupang_ftp1", "pltu_timor_1", "pltu_atambua")

# Value used for a transplanted unit's availability when the donor ships no
# variability column for it (all the donor's thermal candidates). The loader
# pads missing trailing columns with 1.0 itself, but it maps columns to
# generators POSITIONALLY, so every unit needs its column in R_ID order.
FLAT_CF = 1.0


def variability_column(var, gen_row_index):
    """The availability column for the generator at `gen_row_index` (0-based).

    `input_data.jl` drops the first column of generators_variability.csv and then
    indexes the rest **positionally** by R_ID, padding missing trailing columns
    with 1.0. Column *names* are decorative. Looking a profile up by resource name
    would be wrong here: the donor repeats 26 resource names (`plts_sumba` nine
    times), so its CSV has duplicate headers that pandas renames `foo.1`, `foo.2`
    — from position 9 onward the donor's column names no longer line up with its
    own generator order. Returns None when the CSV is shorter than the fleet.
    """
    col = gen_row_index + 1          # +1 for the leading hour-index column
    if col >= len(var.columns):
        return None
    return var.iloc[:, col]


def unique_names(names):
    """Column labels for the variability header: readable, and never duplicated."""
    seen, out = {}, []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name}__{seen[name]}")
    return out


def _read(path):
    return pd.read_csv(path, **NA)


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def dataset_path(year, island):
    return os.path.join(REPO, "data_indonesia", str(year), island)


# ------------------------------------------------------------------ annualising

def period_shape(demand):
    """(rep_periods, hours_per_period, weights) from a demand.csv."""
    P = int(_num(demand["Rep_Periods"]).dropna().iloc[0])
    H = int(_num(demand["Timesteps_per_Rep_Period"]).dropna().iloc[0])
    w = _num(demand["Sub_Weights"]).dropna().to_numpy()[:P]
    if len(w) != P:
        raise SystemExit(f"demand.csv declares {P} representative periods but "
                         f"carries {len(w)} Sub_Weights")
    return P, H, w


def annual_gwh(series, P, H, weights):
    """Weighted annual energy (GWh) from a rep-period hourly MW series.

    Sub_Weights are the *hours of the year* each representative period stands
    for (they sum to 8760), so the period's mean power is what gets weighted.
    """
    blocks = series[:P * H].reshape(P, H)
    return float((blocks.sum(axis=1) / H * weights).sum()) / 1000.0


def naive_annual_gwh(series, P, H):
    """Annual energy if every rep hour were equally likely — the wrong answer,
    reported so the difference from the weighted figure is visible."""
    return float(series[:P * H].sum()) * 8760.0 / (P * H) / 1000.0


# --------------------------------------------------------------------- the donor

def resolve_donor_zone(gens, explicit, province):
    if explicit is not None:
        return int(explicit)
    if "Province" not in gens.columns:
        raise SystemExit(
            "donor generators.csv has no Province column; pass --donor-zone "
            "explicitly (the donor ships no zones.csv, so there is no other "
            "declared zone identity)")
    match = gens[gens["Province"].astype(str).str.strip() == province]
    zones = sorted(set(int(z) for z in _num(match["Zone"]).dropna()))
    if len(zones) != 1:
        raise SystemExit(f"expected exactly one donor zone for province "
                         f"{province!r}, found {zones}")
    return zones[0]


def donor_profile(donor_dir, zone, province):
    """(zone, hourly MW series, rep_periods, hours_per_period, weights) for the donor."""
    gens = _read(os.path.join(donor_dir, "generators.csv"))
    z = resolve_donor_zone(gens, zone, province)
    demand = _read(os.path.join(donor_dir, "demand.csv"))
    col = f"demand_z{z}"
    if col not in demand.columns:
        raise SystemExit(f"donor demand.csv has no column {col!r}")
    P, H, w = period_shape(demand)
    series = _num(demand[col]).to_numpy()[:P * H]
    if pd.isna(series).any():
        raise SystemExit(f"donor {col} has blank hours")
    return z, series, P, H, w


# ------------------------------------------------------------------ the demand

def build_demand(base_dir, donor_dir, share, donor_zone, province, report=print):
    """Return (net_series, stats) — the demand_z1 MW series for the base dataset."""
    z, donor_series, dP, dH, dW = donor_profile(donor_dir, donor_zone, province)
    donor_annual = annual_gwh(donor_series, dP, dH, dW)
    donor_naive = naive_annual_gwh(donor_series, dP, dH)

    base_demand = _read(os.path.join(base_dir, "demand.csv"))
    P, H, w = period_shape(base_demand)
    if (P, H) != (dP, dH):
        raise SystemExit(f"donor rep-period shape {dP}x{dH} does not match the base "
                         f"dataset's {P}x{H}; the hour-for-hour transplant needs the same shape")

    village = _read(os.path.join(base_dir, "village_demand.csv"))
    vcols = [c for c in village.columns if c.startswith("demand_")]
    village_total = village[vcols].apply(_num).to_numpy()[:P * H].sum(axis=1)
    village_annual = annual_gwh(village_total, P, H, w)

    # Gross Timor system: `share` of the donor's *weighted* annual energy. The
    # donor's hourly shape is carried across position-for-position and rescaled
    # so the gross annual comes out exact under the BASE dataset's weights. The
    # two datasets pick different calendar weeks (donor 24,3,4,45,8,46,39,5 vs
    # base 2,9,16,24,32,40,46,52), so this transplants the load *shape*, not the
    # season — defensible for NTT, whose load has weak seasonality, but it is an
    # assumption worth stating.
    gross_target = share * donor_annual
    gross_under_base_weights = annual_gwh(donor_series, P, H, w)
    k = gross_target / gross_under_base_weights
    gross = donor_series * k

    net = gross - village_total
    negative_hours = int((net < 0).sum())
    clipped = net.clip(min=0.0)
    clip_gwh = annual_gwh(clipped, P, H, w) - annual_gwh(net, P, H, w)

    stats = dict(
        donor_zone=z, donor_annual_gwh=donor_annual, donor_naive_gwh=donor_naive,
        donor_peak_mw=float(donor_series.max()), donor_lf=float(donor_series.mean() / donor_series.max()),
        share=share, gross_annual_gwh=gross_target, gross_peak_mw=float(gross.max()),
        village_annual_gwh=village_annual,
        net_annual_gwh=annual_gwh(clipped, P, H, w), net_peak_mw=float(clipped.max()),
        net_lf=float(clipped.mean() / clipped.max()) if clipped.max() > 0 else 0.0,
        negative_hours=negative_hours, clip_gwh=clip_gwh, scale=k, P=P, H=H,
    )

    origin = f"{province}" if donor_zone is None else "explicit --donor-zone"
    report(f"  donor zone {z} ({origin}): {donor_annual:,.1f} GWh/yr weighted, "
           f"peak {stats['donor_peak_mw']:,.0f} MW, LF {stats['donor_lf']:.2f}")
    report(f"    (naive equal-weight annualisation would say {donor_naive:,.1f} GWh/yr — "
           f"{100 * (donor_naive / donor_annual - 1):+.1f} %; the weighted figure is the right one)")
    report(f"  share {share:.2%} -> gross Timor {gross_target:,.1f} GWh/yr, "
           f"peak {stats['gross_peak_mw']:,.0f} MW (hourly shape rescaled x {k:.4f})")
    report(f"  less village load already modelled as its own nodes: "
           f"{village_annual:,.1f} GWh/yr")
    report(f"  = grid demand_z1 {stats['net_annual_gwh']:,.1f} GWh/yr, "
           f"peak {stats['net_peak_mw']:,.1f} MW, LF {stats['net_lf']:.2f}")
    if negative_hours:
        report(f"  NOTE {negative_hours} of {P * H} hours netted below zero "
               f"(village load exceeds the Timor share in those hours); clipped to 0, "
               f"adding {clip_gwh:,.2f} GWh/yr")
    return clipped, stats


# ------------------------------------------------------------------- the fleet

def transplant_fleet(base_dir, out_dir, donor_dir, share, donor_zone,
                     existing_mode, drop_techs, fuel_source, report=print):
    """Write out_dir's generators / variability / fuels with a donor-derived fleet."""
    base_gens = _read(os.path.join(base_dir, "generators.csv"))
    base_var = _read(os.path.join(base_dir, "generators_variability.csv"))
    base_fuels = _read(os.path.join(base_dir, "fuels_data.csv"))
    d_gens = _read(os.path.join(donor_dir, "generators.csv"))
    d_var = _read(os.path.join(donor_dir, "generators_variability.csv"))
    d_fuels = _read(os.path.join(donor_dir, "fuels_data.csv"))

    zone = int(_num(base_gens["Zone"]).iloc[0])
    d_zone = d_gens[_num(d_gens["Zone"]) == donor_zone].copy()
    d_zone["_is_new"] = _num(d_zone["New_Build"]) == 1

    dropped_tech = d_zone[d_zone["technology"].astype(str).isin(drop_techs)]
    d_zone = d_zone[~d_zone["technology"].astype(str).isin(drop_techs)]

    # `keep` carries each donor row's ORIGINAL row position (row.name, since
    # d_gens was read with a fresh RangeIndex) because the variability lookup is
    # positional, not by name — see variability_column().
    keep, scales = [], []
    for _, row in d_zone.iterrows():
        if row["_is_new"]:
            keep.append(row)
            scales.append(share)
        elif existing_mode == "named":
            if str(row["Resource"]) in TIMOR_EXISTING:
                keep.append(row)
                scales.append(1.0)
        else:  # rescale
            keep.append(row)
            scales.append(share)

    # ---- generators.csv, mapped onto the base dataset's column schema -------
    CAP_COLS = ("Existing_Cap_MW", "Existing_Cap_MWh", "Max_Cap_MW")
    DEFAULTS = {"owner": "pln"}
    rows = base_gens.to_dict("records")
    for row, scale in zip(keep, scales):
        out = {}
        for c in base_gens.columns:
            if c in row.index:
                out[c] = row[c]
            elif c in DEFAULTS:
                out[c] = DEFAULTS[c]
            else:
                raise SystemExit(f"donor row has no value for base column {c!r} "
                                 "and no documented default")
        out["Zone"] = zone
        for c in CAP_COLS:
            if c in out:
                v = pd.to_numeric(out[c], errors="coerce")
                out[c] = round(float(v) * scale, 4) if pd.notna(v) else out[c]
        # Commit=1 rows must keep Existing_Cap_MW>0 (the model divides by it);
        # a scaled-to-zero committed unit would fail schema validation.
        if pd.to_numeric(out.get("Commit"), errors="coerce") == 1 and \
                not pd.to_numeric(out.get("Existing_Cap_MW"), errors="coerce") > 0:
            out["Commit"] = 0
        rows.append(out)

    gens = pd.DataFrame(rows, columns=list(base_gens.columns))
    gens["R_ID"] = range(1, len(gens) + 1)   # validator: consecutive 1..N in row order

    # ---- generators_variability.csv, one column per generator IN R_ID ORDER --
    # Sources are indexed positionally against their own generators.csv: base
    # generator j -> base_var column j+1, donor generator at original position p
    # -> d_var column p+1.
    hours = len(base_var)
    cols = [base_var.iloc[:, 0]]
    labels = [str(base_var.columns[0])]
    n_flat = 0
    sources = ([(base_var, j) for j in range(len(base_gens))]
               + [(d_var, int(row.name)) for row in keep])
    for (src, pos), res in zip(sources, gens["Resource"].astype(str)):
        series = variability_column(src, pos)
        if series is None:
            series = pd.Series([FLAT_CF] * hours)
            n_flat += 1
        cols.append(pd.Series(series.to_numpy()[:hours]).reset_index(drop=True))
        labels.append(res)
    variability = pd.concat(cols, axis=1)
    variability.columns = [labels[0]] + unique_names(labels[1:])

    # ---- fuels_data.csv -----------------------------------------------------
    if fuel_source == "donor":
        fuels = d_fuels.copy()
    else:
        # Keep the base dataset's own prices (its diesel is the validated NTT
        # field number, $18/MMBtu) and add only the fuels it does not have.
        have = set(base_fuels["Fuel"].astype(str))
        add = d_fuels[~d_fuels["Fuel"].astype(str).isin(have)]
        fuels = pd.concat([base_fuels, add], ignore_index=True)
    fuels["fuel_indices"] = range(1, len(fuels) + 1)
    missing_fuels = sorted(set(gens["Fuel"].astype(str)) - set(fuels["Fuel"].astype(str)))
    if missing_fuels:
        raise SystemExit(f"transplanted units reference fuels absent from the merged "
                         f"fuels_data.csv: {missing_fuels}")

    gens.to_csv(os.path.join(out_dir, "generators.csv"), index=False)
    variability.to_csv(os.path.join(out_dir, "generators_variability.csv"), index=False)
    fuels.to_csv(os.path.join(out_dir, "fuels_data.csv"), index=False)

    n_base = len(base_gens)
    ex = gens.iloc[n_base:][_num(gens.iloc[n_base:]["New_Build"]) != 1]
    cand = gens.iloc[n_base:][_num(gens.iloc[n_base:]["New_Build"]) == 1]
    report(f"  fleet: {n_base} base unit(s) kept + {len(gens) - n_base} donor unit(s) "
           f"({len(ex)} existing, {len(cand)} candidate)")
    report(f"    existing capacity {_num(gens['Existing_Cap_MW'])[_num(gens['New_Build']) != 1].sum():,.1f} MW"
           f"  ({existing_mode} allocation)")
    report(f"    candidate Max_Cap_MW {_num(cand['Max_Cap_MW']).sum():,.0f} MW "
           f"(donor potential x {share:.2%})")
    by_tech = _num(cand["Max_Cap_MW"]).groupby(cand["technology"].astype(str)).sum()
    report("    candidates by technology (MW): "
           + ", ".join(f"{t} {v:,.0f}" for t, v in by_tech.sort_values(ascending=False).items()))
    if dropped_tech is not None and len(dropped_tech):
        report(f"    dropped {len(dropped_tech)} unit(s) by --drop-tech "
               f"({', '.join(sorted(set(dropped_tech['technology'].astype(str))))}): "
               f"{_num(dropped_tech['Max_Cap_MW']).sum():,.0f} MW of donor potential")
    if n_flat:
        report(f"    {n_flat} transplanted unit(s) had no donor variability column "
               f"-> flat availability {FLAT_CF}")
    diesel = fuels[fuels["Fuel"].astype(str) == "diesel"]
    if len(diesel):
        report(f"    fuels: --fuel-source {fuel_source}; diesel "
               f"${float(_num(diesel['Cost_per_MMBtu']).iloc[0]):.4f}/MMBtu")
    return gens, fuels


# ------------------------------------------------------------------------ write

def write_dataset(base, out, year, net, donor_dir, share, donor_zone, fleet,
                  existing_mode, drop_techs, fuel_source, report=print):
    base_dir, out_dir = dataset_path(year, base), dataset_path(year, out)
    if os.path.normpath(base_dir) == os.path.normpath(out_dir):
        raise SystemExit("--out-dataset must differ from --base; this tool never "
                         "rewrites the base dataset in place")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(base_dir, out_dir)

    demand = _read(os.path.join(out_dir, "demand.csv"))
    if len(net) != len(demand):
        raise SystemExit(f"derived {len(net)} hours but demand.csv has {len(demand)} rows")
    demand["demand_z1"] = [round(float(v), 4) for v in net]
    demand.to_csv(os.path.join(out_dir, "demand.csv"), index=False)
    report(f"  wrote {os.path.relpath(os.path.join(out_dir, 'demand.csv'), REPO)}")

    if fleet == "rescale":
        transplant_fleet(base_dir, out_dir, donor_dir, share, donor_zone,
                         existing_mode, drop_techs, fuel_source, report=report)
    else:
        report("  WARNING --fleet none: the grid bus keeps the base dataset's fleet. "
               "If that fleet cannot meet the demand just written, the balance closes "
               "on non-served energy priced at Voll (~$2,000/MWh) and every exported "
               "village MWh is valued at scarcity, not at generation cost.")

    errors, warnings = validate_dataset(out_dir)
    for w in warnings:
        report(f"  warning: {w}")
    if errors:
        for e in errors[:5]:
            report(f"  ERROR: {e}")
        raise SystemExit(f"{out} failed schema validation ({len(errors)} error(s))")
    report(f"  schema OK ({len(warnings)} warning(s)) — {out}")
    return out_dir


# -------------------------------------------------------------------------- cli

def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="timor", help="dataset to derive from (default timor)")
    ap.add_argument("--year", default="2030")
    ap.add_argument("--donor", default="nusa_tenggara",
                    help="dataset supplying the provincial load shape (default nusa_tenggara)")
    ap.add_argument("--donor-zone", type=int, default=None,
                    help="donor zone number; default resolves it from the Province column")
    ap.add_argument("--donor-province", default=DONOR_PROVINCE)
    ap.add_argument("--share", type=float, default=0.42,
                    help="Timor's share of the donor province (default 0.42; "
                         "0.33 population, 0.47 high)")
    ap.add_argument("--out-dataset", default=None,
                    help="write a patched copy of --base under this name "
                         "(never modifies --base). Omit for a dry run.")
    ap.add_argument("--fleet", choices=("rescale", "none"), default=None,
                    help="required with --out-dataset. 'rescale' transplants the donor "
                         "zone's fleet; 'none' keeps the base fleet (warned — see the "
                         "module docstring)")
    ap.add_argument("--existing", choices=("named", "rescale"), default="named",
                    help="how to allocate the donor zone's EXISTING units: 'named' keeps "
                         "the Timor-sited plants at 100 %% and drops the other islands' "
                         "(default); 'rescale' gives Timor --share of every plant")
    ap.add_argument("--drop-tech", default="",
                    help="comma-separated technologies to exclude from the transplanted "
                         "candidate set, e.g. 'wind' (the donor carries NTT-wide "
                         "potential that is not Timor-sited)")
    ap.add_argument("--fuel-source", choices=("target", "donor"), default="target",
                    help="'target' keeps the base dataset's fuel prices and adds only "
                         "the fuels it lacks (default); 'donor' takes the donor table "
                         "wholesale, which replaces the base diesel price")
    args = ap.parse_args(argv)

    if args.out_dataset and args.fleet is None:
        raise SystemExit(
            "--out-dataset requires an explicit --fleet choice.\n"
            "  --fleet rescale  transplant the donor zone's fleet, scaled to --share\n"
            "  --fleet none     keep the base fleet (a single 122 MW diesel on timor), "
            "which will close the balance on non-served energy at ~$2,000/MWh")
    if not 0 < args.share <= 1:
        raise SystemExit(f"--share must be in (0, 1], got {args.share}")

    base_dir, donor_dir = dataset_path(args.year, args.base), dataset_path(args.year, args.donor)
    for d in (base_dir, donor_dir):
        if not os.path.isdir(d):
            raise SystemExit(f"dataset not found: {d}")

    print(f"== grid demand for {args.base} ({args.year}) from {args.donor} ==")
    net, stats = build_demand(base_dir, donor_dir, args.share, args.donor_zone,
                              args.donor_province)
    zone = stats["donor_zone"]

    if not args.out_dataset:
        print("\n  dry run — pass --out-dataset <name> --fleet <choice> to write a dataset")
        return 0

    drop = tuple(t.strip() for t in args.drop_tech.split(",") if t.strip())
    print(f"\n== writing {args.out_dataset} ==")
    write_dataset(args.base, args.out_dataset, args.year, net, donor_dir, args.share,
                  zone, args.fleet, args.existing, drop, args.fuel_source)
    print(f"\nDone. Run with island '{args.out_dataset}', year {args.year}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
