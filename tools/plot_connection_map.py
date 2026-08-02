#!/usr/bin/env python3
"""Map: who connects and who stays islanded — the distance-decay exhibit.

Scatter of villages on lat/lon from the coordinated (ON) plan's exact
connection binaries: connected in blue, islanded in orange, dot area by
households. The spatial story is distance decay: islanded villages sit twice
as far from a substation (median 37.3 km) as connected ones (19.6 km).

Sources: results/gridvillage_timor__marketfix_2030_reference__ucrelax/
site_connection_results.csv (Connected is exact — the wire binaries were not
relaxed) joined to data_indonesia/2030/timor/village_solar_potential.csv on
Village. 153 of 780 villages lack coordinates and are counted in the caption,
not drawn. The pattern comes from a feasible incumbent at achieved gap 28.8%;
the exact membership of the connected set may shift in a tighter solve, the
distance gradient is robust. Requires matplotlib; solver-free.
"""
import argparse, datetime as _dt, os, sys
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, MUTED, GRID_LN, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

def _read(p): return pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False, na_values=[""])

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", default=os.path.join(REPO, "results",
                    "gridvillage_timor__marketfix_2030_reference__ucrelax"))
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures", "connection_map.png"))
    args = ap.parse_args(argv)

    cn = _read(os.path.join(args.run, "site_connection_results.csv"))
    sp = _read(os.path.join(REPO, "data_indonesia/2030/timor/village_solar_potential.csv"))
    m = cn.merge(sp[["Village", "lat", "lon", "hubdist_km", "households"]],
                 left_on="ID", right_on="Village", how="left")
    m["lat"] = pd.to_numeric(m.lat, errors="coerce"); m["lon"] = pd.to_numeric(m.lon, errors="coerce")
    have = m[m.lat.notna() & m.lon.notna()]
    miss = len(m) - len(have)
    conn, isl = have[have.Connected >= 0.5], have[have.Connected < 0.5]
    med_c = m[m.Connected >= 0.5].hubdist_km.median()
    med_i = m[m.Connected < 0.5].hubdist_km.median()

    fig, ax = plt.subplots(figsize=(9.6, 6.4), dpi=200)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.88, bottom=0.20)
    fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)
    for df, c, lab in ((conn, BLUE, None), (isl, ORANGE, None)):
        ax.scatter(df.lon, df.lat, s=np.sqrt(df.households.astype(float)) * 1.6,
                   c=c, alpha=0.75, lw=0.6, edgecolors=SURFACE, zorder=3)
    ax.scatter([], [], c=BLUE, s=40, label=f"connected  ({int(m.Connected.sum())} of 780)")
    ax.scatter([], [], c=ORANGE, s=40, label=f"stays islanded  ({int((m.Connected<0.5).sum())} of 780)")
    ax.set_aspect(1 / np.cos(np.deg2rad(9.5)))
    ax.grid(True, color=GRID_LN, lw=0.6, zorder=0)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.spines["left"].set_color(BASE); ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.set_xlabel("longitude", fontsize=9, color=INK2); ax.set_ylabel("latitude", fontsize=9, color=INK2)
    ax.legend(loc="upper left", frameon=False, fontsize=9.5)
    ax.set_title("Who connects: distance decides", fontsize=13, color=INK, loc="left", pad=12)
    ax.text(0.98, 0.98, f"median substation distance\nconnected {med_c:.1f} km  ·  "
            f"islanded {med_i:.1f} km", transform=ax.transAxes, fontsize=9.5,
            color=INK, ha="right", va="top")
    fig.text(0.07, 0.02,
             f"dot area = households · {miss} of 780 villages lack coordinates and are "
             "not drawn · pattern from the best plan (gap 28.8%); the distance gradient is robust",
             fontsize=7.5, color=MUTED, va="bottom")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}  (drawn {len(have)}, missing {miss}; medians {med_c:.1f}/{med_i:.1f} km)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
