#!/usr/bin/env python3
"""Derive distance-based village grid-connection costs (village_connection.csv).

Rewrites a dataset's ``village_connection.csv`` from the siting pipeline's
per-village **distance to the nearest grid substation** (``hubdist_km`` in
``village_solar_potential.csv``), so that a remote village pays more to connect
than one next to the grid. This is the cost the optimiser trades against
islanded solar+storage via the connection binary (``vVIL_CONNECT``) — before
this step, ``build_timor.py`` writes provisional costs from a village-centroid
proxy, and datasets with no connection file at all default to *free* connection.

    python tools/connection_cost.py data_indonesia/2030/timor
    python tools/connection_cost.py data_indonesia/2030/timor --dry-run
    python tools/connection_cost.py <folder> --idr-per-km 3e8 --fx 15500

Cost model (constants + formula in ``tools/ntt/costs.py``, one place):

    capex_IDR   = CONNECT_FIXED_IDR + hubdist_km x CONNECT_IDR_PER_KM
    Cost_per_yr = capex_IDR / FX_RATE x CRF(DISCOUNT_RATE, grid lifetime)
    Max_Connect_MW = max(peak_mw x 1.5, 0.02)

Defaults are NTT working assumptions (Rp 150 M fixed + Rp 400 M/km MV feeder,
Rp 16,000/USD, 10 % over 30 y) — replace with PLN unit costs via the flags when
official figures are available. Villages without ``hubdist_km`` (not sited) fall
back to ``--default-km`` (10 km).

Runs on Python + pandas.
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    print("connection_cost requires pandas", file=sys.stderr)
    sys.exit(3)

try:
    from tools.ntt import costs as C
except ImportError:  # pragma: no cover
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ntt import costs as C


def derive(folder, *, fixed_idr, idr_per_km, fx, rate, default_km):
    """Return (df with Village/Cost_per_yr/Max_Connect_MW, stats dict)."""
    sp_path = os.path.join(folder, "village_solar_potential.csv")
    if not os.path.isfile(sp_path):
        raise FileNotFoundError(
            f"{sp_path} not found — run the siting pipeline first "
            "(tools/resource_siting.py), or use build_timor.py's provisional costs.")
    sp = pd.read_csv(sp_path, encoding="utf-8-sig")
    for col in ("Village", "peak_mw"):
        if col not in sp.columns:
            raise ValueError(f"{sp_path} is missing required column {col!r}")

    hub = pd.to_numeric(sp.get("hubdist_km"), errors="coerce")
    peaks = pd.to_numeric(sp["peak_mw"], errors="coerce").fillna(0.0)
    dist = hub.fillna(default_km)

    out = pd.DataFrame({
        "Village": sp["Village"].astype(int),
        "Cost_per_yr": [C.connection_cost_per_yr(d, fixed_idr=fixed_idr,
                                                 idr_per_km=idr_per_km,
                                                 fx=fx, rate=rate)
                        for d in dist],
        "Max_Connect_MW": [C.connect_max_mw(p) for p in peaks],
    })
    stats = dict(n=len(out),
                 n_hubdist=int(hub.notna().sum()),
                 n_fallback=int(hub.isna().sum()),
                 km_min=float(dist.min()), km_med=float(dist.median()),
                 km_max=float(dist.max()),
                 usd_min=int(out.Cost_per_yr.min()),
                 usd_med=int(out.Cost_per_yr.median()),
                 usd_max=int(out.Cost_per_yr.max()))
    return out, stats


def main(argv):
    ap = argparse.ArgumentParser(
        description="Rewrite village_connection.csv from hubdist_km (distance-based costs).")
    ap.add_argument("folder", help="dataset folder, e.g. data_indonesia/2030/timor")
    ap.add_argument("--fixed-idr", type=float, default=C.CONNECT_FIXED_IDR,
                    help="fixed grid-tap cost per village, Rp (default %(default)s)")
    ap.add_argument("--idr-per-km", type=float, default=C.CONNECT_IDR_PER_KM,
                    help="MV feeder cost per km, Rp (default %(default)s)")
    ap.add_argument("--fx", type=float, default=C.FX_RATE,
                    help="Rp per USD (default %(default)s)")
    ap.add_argument("--rate", type=float, default=C.DISCOUNT_RATE,
                    help="real discount rate for annualisation (default %(default)s)")
    ap.add_argument("--default-km", type=float, default=C.CONNECT_DEFAULT_KM,
                    help="distance for villages without hubdist_km (default %(default)s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the summary without writing the file")
    args = ap.parse_args(argv[1:])

    out, s = derive(args.folder, fixed_idr=args.fixed_idr, idr_per_km=args.idr_per_km,
                    fx=args.fx, rate=args.rate, default_km=args.default_km)

    print(f"== connection_cost — {args.folder} ==")
    print(f"  villages        {s['n']}  ({s['n_hubdist']} with hubdist_km, "
          f"{s['n_fallback']} fallback @ {args.default_km} km)")
    print(f"  distance km     min {s['km_min']:.2f} · median {s['km_med']:.2f} · max {s['km_max']:.2f}")
    print(f"  Cost_per_yr $   min {s['usd_min']:,} · median {s['usd_med']:,} · max {s['usd_max']:,}")
    print(f"  model           (Rp {args.fixed_idr:,.0f} + km x Rp {args.idr_per_km:,.0f}) "
          f"/ {args.fx:,.0f} x CRF({args.rate}, {C.LIFETIME_YEARS['grid']}y)")

    dst = os.path.join(args.folder, "village_connection.csv")
    if args.dry_run:
        print(f"  dry-run: NOT writing {dst}")
        return 0
    out.to_csv(dst, index=False)
    print(f"  wrote {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
