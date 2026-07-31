"""Reshape a fraction of a dataset's villages onto a midday load peak.

The Timor village demand profiles all come from a small set of archetype
hour-of-day curves, so the villages are close to load-shape *clones*. That matters
for the coordination question: if every village peaks at the same hour and has the
same solar, there is nothing to trade, and a measured coordination value of ~0
could be an artifact of homogeneous inputs rather than a result. This tool builds
the counterfactual — half the villages moved onto a **midday** peak, coincident
with solar — so the experiment can be run and the explanation separated.

    python -m tools.ntt.make_diverse_demand --dataset data_indonesia/2030/timor
    # -> data_indonesia/2030/timor__diverse

**Energy-preserving by construction.** The reshaping happens *within each
representative period*: a selected village's hours in a period are re-weighted
onto the midday shape and rescaled so that period's total is exactly what it was.
Preserving per-period totals (rather than the horizon total) keeps weighted annual
energy exact for **any** `Sub_Weights`, uniform or not. So the only thing that
changes is *when* the load falls — never how much of it there is. That is what
makes the comparison against the base dataset clean.

Copies the dataset and patches the copy; never rewrites `--dataset` in place. An
in-place rewrite is how a stale, silently-diverged `timor_diverse` folder came to
exist once already.

Runs on Python + pandas; no solver.
"""
from __future__ import annotations

import argparse
import math
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

# Midday shape: a Gaussian centred on local noon over a flat baseload, so a
# reshaped village still draws overnight (a village with literally zero night
# load would make its diesel and battery behave unlike any real system).
PEAK_HOUR = 12.0
WIDTH_H = 3.0        # Gaussian sigma, hours
BASELOAD = 0.2       # fraction of the peak that persists overnight


def midday_shape(hours_per_period, peak_hour=PEAK_HOUR, width_h=WIDTH_H,
                 baseload=BASELOAD):
    """Relative load weight per hour of a representative period (length = H)."""
    out = []
    for t in range(hours_per_period):
        hod = t % 24
        # wrap the distance so 23:00 is 1 h from 00:00, not 23
        d = min(abs(hod - peak_hour), 24 - abs(hod - peak_hour))
        out.append(baseload + (1.0 - baseload) * math.exp(-(d ** 2) / (2 * width_h ** 2)))
    return out


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def select_villages(columns, fraction):
    """Evenly spread deterministic selection of `fraction` of the demand columns.

    Spread rather than "the first half" so the reshaped set is not concentrated in
    one kabupaten (the columns are ordered by village id, which is ordered by
    kabupaten), and deterministic so the dataset is reproducible.
    """
    n = len(columns)
    k = int(round(n * fraction))
    if k <= 0:
        return []
    if k >= n:
        return list(columns)
    step = n / k
    idx = sorted({min(n - 1, int(i * step)) for i in range(k)})
    return [columns[i] for i in idx]


def period_shape(dataset_dir):
    """(rep_periods, hours_per_period) — declared in demand.csv, not village_demand.csv."""
    zonal = pd.read_csv(os.path.join(dataset_dir, "demand.csv"), **NA)
    for col in ("Rep_Periods", "Timesteps_per_Rep_Period"):
        if col not in zonal.columns:
            raise SystemExit(f"demand.csv has no {col!r} column")
    return (int(_num(zonal["Rep_Periods"]).dropna().iloc[0]),
            int(_num(zonal["Timesteps_per_Rep_Period"]).dropna().iloc[0]))


def reshape(demand, fraction, period, report=print):
    """Return (patched demand frame, stats). Per-period energy is preserved exactly."""
    P, H = period
    if len(demand) != P * H:
        raise SystemExit(f"village_demand.csv has {len(demand)} rows; expected {P * H}")

    cols = [c for c in demand.columns if c.startswith("demand_")]
    if not cols:
        raise SystemExit("village_demand.csv has no demand_* columns")
    chosen = select_villages(cols, fraction)
    shape = midday_shape(H)
    shape_sum = sum(shape)

    out = demand.copy()
    moved = 0
    for col in chosen:
        series = _num(out[col]).to_numpy(dtype=float)
        new = series.copy()
        for p in range(P):
            lo, hi = p * H, (p + 1) * H
            block_total = float(series[lo:hi].sum())
            if block_total <= 0:
                continue
            scale = block_total / shape_sum
            new[lo:hi] = [w * scale for w in shape]
        out[col] = [round(v, 6) for v in new]
        moved += 1

    before = demand[cols].apply(_num).to_numpy()
    after = out[cols].apply(_num).to_numpy()
    # Relative, not absolute: the only residual is the 6-decimal rounding of the
    # written values, which grows with villages x hours, so an absolute MWh
    # threshold would false-trip on a bigger dataset.
    per_period_err, per_period_rel = 0.0, 0.0
    for p in range(P):
        lo, hi = p * H, (p + 1) * H
        b, a = before[lo:hi].sum(), after[lo:hi].sum()
        per_period_err = max(per_period_err, abs(b - a))
        if b > 0:
            per_period_rel = max(per_period_rel, abs(b - a) / b)

    peak_hours = {}
    for label, arr in (("base", before), ("diverse", after)):
        tot = arr.sum(axis=1)
        by_hod = {}
        for t, v in enumerate(tot):
            by_hod[t % 24] = by_hod.get(t % 24, 0.0) + v
        peak_hours[label] = max(by_hod, key=by_hod.get)

    stats = dict(villages=len(cols), reshaped=moved, P=P, H=H,
                 energy_error_mwh=per_period_err, energy_error_rel=per_period_rel,
                 coincident_peak_before=float(before.sum(axis=1).max()),
                 coincident_peak_after=float(after.sum(axis=1).max()),
                 peak_hour_before=peak_hours["base"],
                 peak_hour_after=peak_hours["diverse"])

    report(f"  reshaped {moved} of {len(cols)} village(s) onto a midday peak "
           f"(hour {PEAK_HOUR:.0f}, sigma {WIDTH_H:.0f} h, baseload {BASELOAD:.0%})")
    report(f"  per-period energy preserved to {per_period_err:.3g} MWh "
           f"({per_period_rel:.2g} relative — write rounding only)")
    report(f"  system coincident peak {stats['coincident_peak_before']:.1f} -> "
           f"{stats['coincident_peak_after']:.1f} MW; busiest hour-of-day "
           f"{stats['peak_hour_before']} -> {stats['peak_hour_after']}")
    if per_period_rel > 1e-6:
        raise SystemExit(f"energy not preserved (max per-period relative error "
                         f"{per_period_rel:.3g}) — refusing to write")
    return out, stats


def write_dataset(dataset_dir, out_name, patched, report=print):
    year = os.path.basename(os.path.dirname(os.path.normpath(dataset_dir)))
    out_dir = os.path.join(REPO, "data_indonesia", year, out_name)
    if os.path.normpath(out_dir) == os.path.normpath(dataset_dir):
        raise SystemExit("--out-dataset must differ from --dataset; this tool never "
                         "rewrites the source dataset in place")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(dataset_dir, out_dir)
    patched.to_csv(os.path.join(out_dir, "village_demand.csv"), index=False)
    report(f"  wrote {os.path.relpath(out_dir, REPO)}/village_demand.csv")

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
    ap.add_argument("--dataset", required=True,
                    help="dataset folder to read (e.g. data_indonesia/2030/timor)")
    ap.add_argument("--out-dataset", default=None,
                    help="name of the patched copy under data_indonesia/<year>/ "
                         "(default <dataset>__diverse, which is gitignored as a "
                         "derived variant)")
    ap.add_argument("--fraction", type=float, default=0.5,
                    help="fraction of villages to move onto a midday peak (default 0.5)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the reshaping without writing a dataset")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.dataset):
        raise SystemExit(f"dataset not found: {args.dataset}")
    if not 0 < args.fraction <= 1:
        raise SystemExit(f"--fraction must be in (0, 1], got {args.fraction}")

    path = os.path.join(args.dataset, "village_demand.csv")
    if not os.path.isfile(path):
        raise SystemExit(f"no village_demand.csv in {args.dataset}")

    base = os.path.basename(os.path.normpath(args.dataset))
    out_name = args.out_dataset or f"{base}__diverse"

    print(f"== load-shape diversity from {args.dataset} ==")
    patched, _stats = reshape(pd.read_csv(path, **NA), args.fraction,
                              period_shape(args.dataset))
    if args.dry_run:
        print("\n  dry run — omit --dry-run to write the dataset")
        return 0
    print(f"\n== writing {out_name} ==")
    write_dataset(args.dataset, out_name, patched)
    print(f"\nDone. Run with island '{out_name}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
