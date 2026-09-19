#!/usr/bin/env python3
"""Map: who connects and who stays islanded, on the Timor basemap.

Same drawing conventions as docs/img/electrification_baseline_timor.png
(figlib basemap: DEM coastline, substation squares, dot size = village peak
demand, scale bar, north arrow), coloured by the coordinated plan's fixed
connection decision: connected in blue, islanded in orange.

One panel per --run. Two runs side by side give the unconstrained and the
carbon-neutral pattern in one figure.

  python tools/plot_connection_basemap.py                       # both fix-and-verify runs
  python tools/plot_connection_basemap.py --run results/<one>   # single panel

Sources: <run>/site_connection_results.csv (Connected, exact — the wire
decisions were fixed to the 2-week winner and priced on the full 8-week model,
RUN_LOG 2026-09-14) joined to data_indonesia/2030/timor/village_solar_potential.csv
on Village. Villages without coordinates (153 of 780) are counted in the stats
box, not drawn. Needs the GIS layers under $GARUDA_GIS_DIR (see figlib.py).
"""
import argparse
import os

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

import figlib as F

CONNECTED = "#2a78d6"
ISLANDED = "#eb6834"
FIXVERIFY = {
    "unconstrained plan": "gridvillage_timor__marketfix_2030_reference__fixverify",
    "carbon-neutral plan": "gridvillage_timor__marketfix_2030_clean__fixverify",
}


def _read(p):
    return pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def load_run(run):
    cn = _read(os.path.join(run, "site_connection_results.csv"))
    vg = F.load_villages()
    m = vg.merge(cn[["ID", "Connected"]], left_on="Village", right_on="ID", how="left")
    m["Connected"] = (pd.to_numeric(m.Connected, errors="coerce").fillna(0) >= 0.5)
    return m


def regime_label(run):
    base = os.path.basename(run.rstrip("/"))
    return "carbon-neutral plan" if "_clean" in base else "unconstrained plan"


def draw_panel(ax, m, xlim, ylim, subs, title, res_m):
    F.draw_base(ax, xlim, ylim, res_m=res_m, shade_ghi=False)
    g = F.village_gdf(m)
    sizes = 12 + (g["peak_mw"].clip(0, 1.0) / 1.0) * 240
    for flag, colour, z in ((False, ISLANDED, 4), (True, CONNECTED, 5)):
        sel = g[g.Connected == flag]
        ax.scatter(sel.geometry.x, sel.geometry.y, s=sizes[sel.index],
                   facecolor=colour, edgecolor="#333", linewidth=0.4,
                   alpha=0.9, zorder=z)
    ax.scatter(subs.geometry.x, subs.geometry.y, s=200, marker="s",
               facecolor=F.BLUE, edgecolor="white", linewidth=1.4, zorder=6)

    n_c = int(m.Connected.sum()); n_i = int((~m.Connected).sum())
    hh = m["households"].astype(float)
    hh_c = hh[m.Connected].sum() / hh.sum()
    med_c = m.loc[m.Connected, "hubdist_km"].median()
    med_i = m.loc[~m.Connected, "hubdist_km"].median()
    txt = (f"Connected:  {n_c} of {len(m)} villages  ({hh_c:.0%} of households)\n"
           f"Stays islanded:  {n_i}\n"
           f"Median distance to substation\n"
           f"   connected {med_c:.1f} km  ·  islanded {med_i:.1f} km")
    ax.text(0.015, 0.97, txt, transform=ax.transAxes, fontsize=10.5, va="top",
            ha="left", color=F.INK, zorder=9,
            bbox=dict(boxstyle="round,pad=0.6", fc="white", ec="#ccc", alpha=0.94))
    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", loc="left", pad=8)
    F.scalebar(ax, xlim, ylim, 20000, "20 km", frac=(0.30, 0.045))
    F.north_arrow(ax, xlim, ylim, frac=(0.94, 0.72))
    return n_c, med_c, med_i


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", default=None,
                    help="results folder; repeat for side-by-side panels "
                         "(default: both fix-and-verify runs)")
    ap.add_argument("--out", default=os.path.join(F.REPO, "results", "figures",
                                                  "connection_basemap.png"))
    ap.add_argument("--res", type=int, default=200, help="basemap grid, metres")
    args = ap.parse_args()
    runs = args.run or [os.path.join(F.REPO, "results", d) for d in FIXVERIFY.values()]

    xlim, ylim = F.bbox_metric(*F.TIMOR_BBOX)
    subs = gpd.read_file(F.SUBS).to_crs(F.METRIC).cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]

    n = len(runs)
    fig, axes = plt.subplots(1, n, figsize=(12 * n if n == 1 else 10.5 * n, 9),
                             squeeze=False)
    subtitle = ("Coordinated plans on the full 8-week model; dot size = village peak demand; "
                "153 villages without coordinates are counted, not drawn")
    for ax, run in zip(axes[0], runs):
        m = load_run(run)
        panel_title = regime_label(run).capitalize() if n > 1 else None
        n_c, med_c, med_i = draw_panel(ax, m, xlim, ylim, subs, panel_title, args.res)
        print(f"{os.path.basename(run.rstrip('/'))}: connected {n_c}, medians {med_c:.1f}/{med_i:.1f} km")

    sym = [Line2D([], [], marker="o", ls="", mfc=CONNECTED, mec="#333", ms=8, label="Village — connects to grid"),
           Line2D([], [], marker="o", ls="", mfc=ISLANDED, mec="#333", ms=8, label="Village — stays islanded"),
           Line2D([], [], marker="s", ls="", mfc=F.BLUE, mec="white", ms=11, label="Grid substation")]
    leg1 = axes[0][-1].legend(handles=sym, loc="lower left", fontsize=9.5, framealpha=0.92)
    axes[0][-1].add_artist(leg1)
    size_h = [Line2D([], [], marker="o", ls="", mfc="#ddd", mec="#333",
                     ms=np.sqrt(12 + (p / 1.0) * 240), label=f"{p:.1f} MW peak")
              for p in (0.1, 0.5, 1.0)]
    axes[0][0].legend(handles=size_h, loc="lower right", fontsize=9, framealpha=0.92,
                      title="Village peak demand", title_fontsize=9, labelspacing=1.4,
                      borderpad=1.0, handletextpad=1.4)

    if n == 1:
        ax = axes[0][0]
        ax.set_title(f"Who connects: distance decides — {regime_label(runs[0])}", fontsize=17,
                     fontweight="bold", loc="left", pad=24)
        ax.text(0, 1.008, subtitle, transform=ax.transAxes, fontsize=10.5, color="#555", va="bottom")
        fig.tight_layout()
    else:
        fig.suptitle("Who connects: distance decides — Timor villages", fontsize=17,
                     fontweight="bold", x=0.01, ha="left", y=0.99)
        fig.text(0.01, 0.945, subtitle, fontsize=10.5, color="#555", ha="left", va="bottom")
        fig.tight_layout(rect=(0, 0, 1, 0.93))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=180, bbox_inches="tight", facecolor="white")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
