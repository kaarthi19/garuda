#!/usr/bin/env python3
"""Figure: electrification / diesel-dependence baseline across Timor.

The starting point the 100 GW program must reach: every village sized by its
peak demand and coloured by distance to the nearest grid substation, over the
existing substation network. Headline totals: villages, diesel capacity,
households, and how many sit far from the grid.

  python tools/plot_electrification_baseline.py
"""
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import geopandas as gpd
from matplotlib.lines import Line2D
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

import figlib as F

FAR_KM = 10.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", default=os.path.join(F.REPO, "docs", "img", "electrification_baseline_timor.png"))
    args = ap.parse_args()

    xlim, ylim = F.bbox_metric(*F.TIMOR_BBOX)
    vg = F.load_villages()
    n_total = len(vg)
    diesel_mw = vg["diesel_mw"].sum() if "diesel_mw" in vg else float("nan")
    hh = vg["households"].sum() if "households" in vg else float("nan")
    g = F.village_gdf(vg)                       # only villages with coords
    far = (g["hubdist_km"] >= FAR_KM).sum()

    fig, ax = plt.subplots(figsize=(12, 9))
    F.draw_base(ax, xlim, ylim, res_m=200, shade_ghi=False)

    # substation network
    subs = gpd.read_file(F.SUBS).to_crs(F.METRIC).cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]

    # villages: size ~ peak demand, colour ~ distance to grid
    norm = Normalize(0, 25)
    cmap = plt.get_cmap("RdYlGn_r")
    sizes = 12 + (g["peak_mw"].clip(0, 1.0) / 1.0) * 240
    sc = ax.scatter(g.geometry.x, g.geometry.y, s=sizes,
                    c=g["hubdist_km"].clip(0, 25), cmap=cmap, norm=norm,
                    edgecolor="#333", linewidth=0.4, alpha=0.9, zorder=4)

    ax.scatter(subs.geometry.x, subs.geometry.y, s=200, marker="s",
               facecolor=F.BLUE, edgecolor="white", linewidth=1.4, zorder=6)

    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax,
                      fraction=0.032, pad=0.01, extend="max")
    cb.set_label("Distance to nearest grid substation (km)", fontsize=10)

    ax.set_title("Electrification baseline — Timor villages", fontsize=17,
                 fontweight="bold", loc="left", pad=24)
    ax.text(0, 1.008, "What the 100 GW program must reach: demand, diesel reliance and grid distance today",
            transform=ax.transAxes, fontsize=10.5, color="#555", va="bottom")

    txt = (f"Villages:  {n_total:,}\n"
           f"Households:  {hh:,.0f}\n"
           f"Diesel capacity in place:  {diesel_mw:,.0f} MW\n"
           f"Villages ≥ {FAR_KM:.0f} km from grid:  {far:,} of {len(g):,}")
    ax.text(0.015, 0.97, txt, transform=ax.transAxes, fontsize=11.5, va="top",
            ha="left", color=F.INK, zorder=9,
            bbox=dict(boxstyle="round,pad=0.6", fc="white", ec="#ccc", alpha=0.94))

    # legends: symbols + size
    sym = [Line2D([], [], marker="s", ls="", mfc=F.BLUE, mec="white", ms=11, label="Grid substation"),
           Line2D([], [], marker="o", ls="", mfc="#bbb", mec="#333", ms=6, label="Village")]
    leg1 = ax.legend(handles=sym, loc="upper right", fontsize=9.5, framealpha=0.92)
    ax.add_artist(leg1)
    size_h = [Line2D([], [], marker="o", ls="", mfc="#ddd", mec="#333",
                     ms=np.sqrt(12 + (p/1.0)*240), label=f"{p:.1f} MW peak")
              for p in (0.1, 0.5, 1.0)]
    ax.legend(handles=size_h, loc="lower right", fontsize=9, framealpha=0.92,
              title="Village peak demand", title_fontsize=9, labelspacing=1.4,
              borderpad=1.0, handletextpad=1.4)

    F.scalebar(ax, xlim, ylim, 20000, "20 km", frac=(0.30, 0.045))
    F.north_arrow(ax, xlim, ylim)

    fig.tight_layout()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=180, bbox_inches="tight", facecolor="white")
    print("wrote", args.out)
    print(f"{n_total} villages, {diesel_mw:.0f} MW diesel, {hh:.0f} hh, {far} far from grid")


if __name__ == "__main__":
    main()
