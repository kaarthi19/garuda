#!/usr/bin/env python3
"""Figure: developable solar potential across Timor (opportunity map).

Rasterises the QGIS suitable-land polygons and aggregates to a grid of
developable MW per cell -> a quantitative "where is the solar" choropleth.
Headline compares total developable GW to Timor's village peak demand:
resource is not the constraint.

  python tools/plot_developable_solar.py
"""
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import geopandas as gpd
from affine import Affine
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from rasterio.features import rasterize

import figlib as F


def block_sum(a, k):
    ny, nx = a.shape
    ny2, nx2 = ny // k, nx // k
    return a[:ny2*k, :nx2*k].reshape(ny2, k, nx2, k).sum(axis=(1, 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell-km", type=float, default=5.0)
    ap.add_argument("--base-m", type=float, default=100.0)
    ap.add_argument("--scratch", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", default=os.path.join(F.REPO, "docs", "img", "developable_solar_timor.png"))
    args = ap.parse_args()

    xlim, ylim = F.bbox_metric(*F.TIMOR_BBOX)
    res = args.base_m
    nx = int((xlim[1]-xlim[0]) / res); ny = int((ylim[1]-ylim[0]) / res)
    transform = Affine(res, 0, xlim[0], 0, -res, ylim[1])

    print("rasterising suitable-land polygons ...")
    cand = gpd.read_file(F.CAND).to_crs(F.METRIC)
    cand = cand[cand.geom_type.isin(["Polygon", "MultiPolygon"])]
    suit = rasterize(((g, 1) for g in cand.geometry), out_shape=(ny, nx),
                     transform=transform, fill=0, dtype="uint8")

    k = int(round(args.cell_km * 1000 / res))
    px_km2 = (res * res) / 1e6
    mw_cell = block_sum(suit.astype("float32"), k) * px_km2 * F.PV_DENSITY   # MW per cell
    # land fraction per cell to drop sea cells
    landpx = np.isfinite(F.reproj(F.DEM, xlim, ylim, res)).astype("float32")
    landfrac = block_sum(landpx, k) / (k * k)
    gw_cell = mw_cell / 1000.0
    gw_cell[(landfrac < 0.04)] = np.nan
    gw_cell[gw_cell <= 0] = np.nan

    total_km2 = suit.sum() * px_km2
    total_gw = total_km2 * F.PV_DENSITY / 1000.0

    vg = F.load_villages()
    peak_mw = vg["peak_mw"].sum()
    diesel_mw = vg["diesel_mw"].sum() if "diesel_mw" in vg else float("nan")

    # ---- figure ----
    fig, ax = plt.subplots(figsize=(12, 9))
    F.draw_base(ax, xlim, ylim, res_m=200, shade_ghi=False)

    cmap = LinearSegmentedColormap.from_list(
        "dev", ["#fde9c8", "#fbbf5a", "#f18f22", "#d64500", "#8c2400"])
    vmax = float(np.nanpercentile(gw_cell, 98))
    extent = [xlim[0], xlim[1], ylim[0], ylim[1]]
    im = ax.imshow(np.ma.masked_invalid(gw_cell), extent=extent, origin="upper",
                   cmap=cmap, vmin=0, vmax=vmax, interpolation="nearest", zorder=2)

    # substations for grid context
    subs = gpd.read_file(F.SUBS).to_crs(F.METRIC)
    subs = subs.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
    ax.scatter(subs.geometry.x, subs.geometry.y, s=90, marker="s",
               facecolor=F.BLUE, edgecolor="white", linewidth=1.1, zorder=5,
               label="Grid substation")

    cb = fig.colorbar(im, ax=ax, fraction=0.032, pad=0.01)
    cb.set_label(f"Developable solar  (GW per {args.cell_km:.0f}×{args.cell_km:.0f} km cell)",
                 fontsize=10)

    ax.set_title("Developable solar potential — Timor", fontsize=17,
                 fontweight="bold", loc="left", pad=24)
    ax.text(0, 1.008, "Technical potential on suitable land only (slope ≤ 15°, screened land cover) × 62 MW/km²",
            transform=ax.transAxes, fontsize=10.5, color="#555", va="bottom")

    txt = (f"Technical potential:  ~{total_gw:,.0f} GW solar\n"
           f"Suitable land:  {total_km2:,.0f} km$^2$\n"
           f"— about {total_gw/100.0:,.0f}× Indonesia's national\n"
           f"   100 GW program, on one island")
    ax.text(0.015, 0.97, txt, transform=ax.transAxes, fontsize=11.5, va="top",
            ha="left", color=F.INK, zorder=9,
            bbox=dict(boxstyle="round,pad=0.6", fc="white", ec="#ccc", alpha=0.94))

    ax.legend(loc="upper right", fontsize=9.5, framealpha=0.92)
    F.scalebar(ax, xlim, ylim, 20000, "20 km", frac=(0.30, 0.045))
    F.north_arrow(ax, xlim, ylim)

    fig.tight_layout()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=180, bbox_inches="tight", facecolor="white")
    print("wrote", args.out)
    print(f"total developable {total_gw:,.0f} GW on {total_km2:,.0f} km2; peak {peak_mw/1000:.2f} GW")


if __name__ == "__main__":
    main()
