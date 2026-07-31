"""Wire hourly ERA5 solar capacity factors into a dataset's site variability.

`tools/solar_resource_era5.py` produces a full-year (8760 h) capacity factor per
village. The model runs on representative periods (8 weeks x 168 h = 1344 h), so
those hours have to be sliced to the *same* weeks the demand files use and written
as the solar columns of `village_generators_variability.csv`. This tool does that
in one step, non-destructively.

    python -m tools.ntt.wire_era5_solar \
        --cf solar_era5/village_solar_cf_hourly.csv \
        --dataset data_indonesia/2030/timor \
        --out-dataset timor_era5

Why it is worth a tool rather than three manual steps — three ways to get this
wrong silently:

1. **The representative weeks are a property of the dataset, not a constant.**
   They are read from the target's own `demand.csv::corresponding_week`
   (`timor` uses 2, 9, 16, 24, 32, 40, 46, 52; `nusa_tenggara` uses
   24, 3, 4, 45, 8, 46, 39, 5). Hard-coding one set and pointing the tool at
   another dataset slices the wrong weeks — and the row-count check still passes,
   because it is still 8 x 168 rows. `--weeks` overrides deliberately.
2. **Columns map to generators by POSITION.** `input_data.jl` drops the first
   column of the variability CSV and indexes the rest by `R_ID`. So a profile is
   written at the solar unit's `R_ID` position, and the village it belongs to comes
   from an explicit join on `village_generators.csv` (`technology == 'solar'` ->
   `Resource`, `Village`) — not from pairing the Nth `plts_*` column with the Nth
   village. Those agree on `timor` today, but any village with two solar units
   would shift every later column by one and mis-wire the whole file.
3. **Non-solar rows must stay flat.** Diesel and battery availability is 1.0; an
   accidental overwrite would cap a genset at the solar capacity factor.

Writes nothing unless `--out-dataset` is given, and never modifies `--dataset`.

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

HOURS_PER_WEEK = 168      # a representative "week" is 168 hours by definition
FLAT_CF = 1.0             # non-solar site units (diesel, battery)


def _read(path):
    return pd.read_csv(path, **NA)


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def dataset_weeks(dataset_dir):
    """(weeks, rep_periods, hours_per_period) from the dataset's own demand.csv."""
    demand = _read(os.path.join(dataset_dir, "demand.csv"))
    P = int(_num(demand["Rep_Periods"]).dropna().iloc[0])
    H = int(_num(demand["Timesteps_per_Rep_Period"]).dropna().iloc[0])
    weeks = [int(w) for w in _num(demand["corresponding_week"]).dropna().to_numpy()[:P]]
    if len(weeks) != P:
        raise SystemExit(f"demand.csv declares {P} representative periods but carries "
                         f"{len(weeks)} corresponding_week values")
    return weeks, P, H


def slice_weeks(cf, weeks, hours_per_period):
    """Concatenate the given 1-based calendar weeks out of a full-year CF frame."""
    if hours_per_period != HOURS_PER_WEEK:
        raise SystemExit(f"this tool slices whole weeks ({HOURS_PER_WEEK} h); the dataset "
                         f"declares {hours_per_period} timesteps per representative period")
    parts = []
    for w in weeks:
        lo, hi = (w - 1) * HOURS_PER_WEEK, w * HOURS_PER_WEEK
        if hi > len(cf):
            raise SystemExit(f"week {w} needs hours {lo}..{hi} but the CF file has "
                             f"only {len(cf)} rows")
        parts.append(cf.iloc[lo:hi])
    out = pd.concat(parts, ignore_index=True)
    assert len(out) == len(weeks) * HOURS_PER_WEEK, "week slicing lost rows"
    return out


def solar_units(dataset_dir):
    """[(r_id, resource, village)] for every site solar unit, in R_ID order."""
    gens = _read(os.path.join(dataset_dir, "village_generators.csv"))
    for col in ("R_ID", "Resource", "technology", "Village"):
        if col not in gens.columns:
            raise SystemExit(f"village_generators.csv has no {col!r} column")
    solar = gens[gens["technology"].astype(str).str.lower() == "solar"]
    units = [(int(r["R_ID"]), str(r["Resource"]), str(r["Village"]).strip())
             for _, r in solar.iterrows()]
    return sorted(units), len(gens)


def wire(dataset_dir, cf_path, weeks=None, report=print):
    """Return the patched village_generators_variability frame and a stats dict."""
    ds_weeks, P, H = dataset_weeks(dataset_dir)
    weeks = weeks or ds_weeks
    if weeks != ds_weeks:
        report(f"  WARNING slicing weeks {weeks} but the dataset's demand.csv uses "
               f"{ds_weeks}; the solar profile will not line up with the demand hours")

    cf = _read(cf_path)
    cf = cf.drop(columns=[c for c in ("time", "date", "datetime") if c in cf.columns])
    sliced = slice_weeks(cf, weeks, H)

    var_path = os.path.join(dataset_dir, "village_generators_variability.csv")
    var = _read(var_path)
    if len(var) != P * H:
        raise SystemExit(f"{var_path} has {len(var)} rows; expected {P * H}")

    units, n_gens = solar_units(dataset_dir)
    if len(var.columns) - 1 != n_gens:
        report(f"  NOTE variability has {len(var.columns) - 1} unit columns for {n_gens} "
               f"site generators (the loader pads the tail with {FLAT_CF})")

    out = var.copy()
    missing, wired = [], 0
    for r_id, resource, village in units:
        col_key = f"village_{village}"
        if col_key not in sliced.columns:
            missing.append((resource, col_key))
            continue
        pos = r_id  # +0 for the leading hour-index column, so R_ID n -> column n
        if pos >= len(out.columns):
            raise SystemExit(f"solar unit R_ID {r_id} ({resource}) has no column in "
                             f"{var_path} ({len(out.columns) - 1} unit columns)")
        if str(out.columns[pos]) != resource:
            report(f"  WARNING column {pos} is named {out.columns[pos]!r} but R_ID {r_id} "
                   f"is {resource!r}; writing by position (the loader's contract)")
        out.iloc[:, pos] = sliced[col_key].to_numpy()
        wired += 1

    if missing:
        raise SystemExit(
            f"{len(missing)} solar unit(s) have no matching CF column, e.g. "
            f"{missing[:3]}. The CF file must carry one 'village_<Village>' column per "
            f"site solar unit (see tools/solar_resource_era5.py).")

    values = out.iloc[:, 1:].apply(_num)
    if not bool(((values >= 0) & (values <= 1)).all().all()):
        raise SystemExit("patched availability values fall outside [0, 1]")

    # every non-solar unit must still be flat
    solar_positions = {r_id for r_id, _r, _v in units}
    non_solar = [i for i in range(1, len(out.columns)) if i not in solar_positions]
    flat_ok = all(bool((values.iloc[:, i - 1] == FLAT_CF).all()) for i in non_solar)
    if not flat_ok:
        raise SystemExit("a non-solar site unit no longer has flat availability")

    mean_cf = float(values.iloc[:, [r - 1 for r, _r, _v in units]].to_numpy().mean())
    stats = dict(weeks=weeks, wired=wired, mean_cf=mean_cf,
                 distinct_profiles=int(sliced[[f"village_{v}" for _r, _n, v in units]]
                                       .T.drop_duplicates().shape[0]))
    report(f"  weeks {weeks} -> {len(sliced)} hours")
    report(f"  wired {wired} solar unit(s); mean sliced CF {mean_cf:.4f} "
           f"({mean_cf * 8760:,.0f} full-load hours if the weeks are representative)")
    report(f"  {stats['distinct_profiles']} distinct profile(s) across {wired} units")
    report(f"  {len(non_solar)} non-solar unit column(s) verified flat at {FLAT_CF}")
    return out, stats


def write_dataset(dataset_dir, out_name, patched, report=print):
    year = os.path.basename(os.path.dirname(os.path.normpath(dataset_dir)))
    out_dir = os.path.join(REPO, "data_indonesia", year, out_name)
    if os.path.normpath(out_dir) == os.path.normpath(dataset_dir):
        raise SystemExit("--out-dataset must differ from --dataset; this tool never "
                         "rewrites the source dataset in place")
    if "__" in out_name:
        report(f"  NOTE '{out_name}' contains a double underscore, which .gitignore "
               f"treats as a derived sweep variant (data_indonesia/*/*__*/). Use a "
               f"single underscore if you mean to commit it.")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(dataset_dir, out_dir)
    patched.to_csv(os.path.join(out_dir, "village_generators_variability.csv"), index=False)
    report(f"  wrote {os.path.relpath(out_dir, REPO)}/village_generators_variability.csv")

    errors, warnings = validate_dataset(out_dir)
    for w in warnings:
        report(f"  warning: {w}")
    if errors:
        for e in errors[:5]:
            report(f"  ERROR: {e}")
        raise SystemExit(f"{out_name} failed schema validation ({len(errors)} error(s))")
    report(f"  schema OK ({len(warnings)} warning(s)) — {out_name}")
    return out_dir


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cf", required=True,
                    help="hourly CF CSV from tools/solar_resource_era5.py "
                         "(village_solar_cf_hourly.csv)")
    ap.add_argument("--dataset", required=True,
                    help="dataset folder to read (e.g. data_indonesia/2030/timor)")
    ap.add_argument("--out-dataset", default=None,
                    help="name of the patched copy under data_indonesia/<year>/ "
                         "(omit for a dry run). Keep a SINGLE underscore, e.g. "
                         "timor_era5 — a double underscore is gitignored.")
    ap.add_argument("--weeks", default=None,
                    help="comma-separated 1-based calendar weeks to slice; default "
                         "reads them from the dataset's demand.csv")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.dataset):
        raise SystemExit(f"dataset not found: {args.dataset}")
    if not os.path.isfile(args.cf):
        raise SystemExit(f"CF file not found: {args.cf}\n"
                         "Generate it with tools/solar_resource_era5.py "
                         "(see docs/solar_resource_era5.md).")
    weeks = ([int(w) for w in args.weeks.split(",") if w.strip()]
             if args.weeks else None)

    print(f"== wiring ERA5 solar into {args.dataset} ==")
    patched, _stats = wire(args.dataset, args.cf, weeks)
    if not args.out_dataset:
        print("\n  dry run — pass --out-dataset <name> to write a dataset")
        return 0
    print(f"\n== writing {args.out_dataset} ==")
    write_dataset(args.dataset, args.out_dataset, patched)
    print(f"\nDone. Run with island '{args.out_dataset}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
