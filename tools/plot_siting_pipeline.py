#!/usr/bin/env python3
"""Figure: how Garuda derives developable-solar land (siting-pipeline explainer).

Four linked panels over one rugged window:
  1. Elevation (Copernicus GLO-30 DEM)
  2. Slope screen  (keep slope ≤ 15°)
  3. Land-cover screen  (keep suitable classes: savannah/shrub/farm/bare)
  4. Candidate solar = slope AND land-cover suitable  → × 62 MW/km²

  python tools/plot_siting_pipeline.py --desa BINAUS
"""
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import geopandas as gpd
from affine import Affine
from matplotlib.colors import to_rgb, ListedColormap, Normalize
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from rasterio.features import rasterize
from shapely.geometry import Point, box as _box

import figlib as F


def _sea_rgba(shape, land):
    rgba = np.zeros((*shape, 4), dtype="float32")
    rgba[..., :3] = to_rgb(F.SEA); rgba[..., 3] = 1.0
    return rgba


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desa", default="BINAUS")
    ap.add_argument("--window-km", type=float, default=20.0)
    ap.add_argument("--res-m", type=float, default=60.0)
    ap.add_argument("--scratch", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", default=os.path.join(F.REPO, "docs", "img", "siting_pipeline_timor.png"))
    args = ap.parse_args()

    vg = F.load_villages()
    row = vg[(vg["desa"].str.upper() == args.desa.upper()) & vg["lat"].notna()].iloc[0]
    lat, lon, name = float(row["lat"]), float(row["lon"]), str(row["desa"]).title()
    pt = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(F.METRIC).iloc[0]
    h = args.window_km*1000/2
    xlim, ylim = (pt.x-h, pt.x+h), (pt.y-h, pt.y+h)
    res = args.res_m
    nx = int((xlim[1]-xlim[0])/res); ny = int((ylim[1]-ylim[0])/res)
    transform = Affine(res, 0, xlim[0], 0, -res, ylim[1])
    extent = [xlim[0], xlim[1], ylim[0], ylim[1]]

    # elevation + slope
    elev = F.reproj(F.DEM, xlim, ylim, res)
    land = np.isfinite(elev)
    gy, gx = np.gradient(np.nan_to_num(elev, nan=0.0), res, res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    slope[~land] = np.nan
    slope_ok = (slope <= F.MAX_SLOPE) & land

    # land cover -> suitable score grid
    corners = gpd.GeoSeries([Point(xlim[0], ylim[0]), Point(xlim[1], ylim[1])],
                            crs=F.METRIC).to_crs(4326)
    lon0, lat0 = corners.iloc[0].x, corners.iloc[0].y
    lon1, lat1 = corners.iloc[1].x, corners.iloc[1].y
    pad = 0.03
    lc = gpd.read_file(F.LANDCOVER, bbox=(min(lon0, lon1)-pad, min(lat0, lat1)-pad,
                                          max(lon0, lon1)+pad, max(lat0, lat1)+pad))
    lc = lc.to_crs(F.METRIC)
    suit_grid = rasterize(((g, int(s)) for g, s in zip(lc.geometry, lc["suitable"])),
                          out_shape=(ny, nx), transform=transform, fill=0, dtype="uint8")
    lc_ok = (suit_grid >= F.MIN_SUITABLE) & land

    # final candidate polygons (real output layer)
    cand = gpd.read_file(F.CAND).to_crs(F.METRIC)
    cand = cand[cand.geom_type.isin(["Polygon", "MultiPolygon"])]
    candW = gpd.clip(cand, _box(xlim[0], ylim[0], xlim[1], ylim[1]))
    dev_km2 = (slope_ok & lc_ok).sum() * (res*res)/1e6

    fig = plt.figure(figsize=(20, 5.8))
    gs = fig.add_gridspec(1, 4, wspace=0.05, left=0.01, right=0.99, top=0.82, bottom=0.10)
    ax = [fig.add_subplot(gs[0, i]) for i in range(4)]
    for a in ax:
        a.set_xlim(*xlim); a.set_ylim(*ylim); a.set_aspect("equal")
        a.set_xticks([]); a.set_yticks([]); a.set_facecolor(F.SEA)

    def sea_under(a):
        a.imshow(_sea_rgba((ny, nx), land), extent=extent, origin="upper", zorder=0)

    # 1) elevation
    sea_under(ax[0])
    terr = ListedColormap(plt.get_cmap("terrain")(np.linspace(0.28, 1.0, 256)))
    em = np.ma.masked_where(~land, elev)
    ax[0].imshow(em, extent=extent, origin="upper", cmap=terr, vmin=0,
                 vmax=float(np.nanpercentile(elev, 99)), zorder=1)
    ax[0].set_title("1.  Elevation", fontsize=13, fontweight="bold")
    ax[0].text(0.5, -0.04, "Copernicus GLO-30 DEM (30 m)", transform=ax[0].transAxes,
               ha="center", va="top", fontsize=9.5, color="#555")

    # 2) slope screen
    sea_under(ax[1])
    sm = np.ma.masked_where(~land, slope)
    ax[1].imshow(sm, extent=extent, origin="upper", cmap="Greys", vmin=0, vmax=30, zorder=1)
    steep = np.zeros((ny, nx, 4), dtype="float32")
    steep[..., :3] = to_rgb("#d62728")
    steep[..., 3] = np.where((slope > F.MAX_SLOPE) & land, 0.75, 0.0)
    ax[1].imshow(steep, extent=extent, origin="upper", zorder=2)
    ax[1].set_title("2.  Slope screen", fontsize=13, fontweight="bold")
    ax[1].text(0.5, -0.04, f"exclude slope > {F.MAX_SLOPE:.0f}° (shaded)", transform=ax[1].transAxes,
               ha="center", va="top", fontsize=9.5, color="#555")
    ax[1].legend(handles=[Patch(fc="#7a2020", alpha=0.55, label=f"slope > {F.MAX_SLOPE:.0f}° (excluded)")],
                 loc="lower left", fontsize=8.2, framealpha=0.9)

    # 3) land-cover screen
    sea_under(ax[2])
    lcrgba = np.zeros((ny, nx, 4), dtype="float32")
    lcrgba[..., :3] = to_rgb("#d9d9d9")           # not suitable
    lcrgba[(suit_grid == 2)] = (*to_rgb("#bfe3a0"), 1.0)
    lcrgba[(suit_grid == 3)] = (*to_rgb("#5aa02c"), 1.0)
    lcrgba[..., 3] = np.where(land, 1.0, 0.0)
    ax[2].imshow(lcrgba, extent=extent, origin="upper", zorder=1)
    ax[2].set_title("3.  Land-cover screen", fontsize=13, fontweight="bold")
    ax[2].text(0.5, -0.04, "keep savannah/shrub/farm/bare", transform=ax[2].transAxes,
               ha="center", va="top", fontsize=9.5, color="#555")
    ax[2].legend(handles=[
        Patch(fc="#5aa02c", label="suitable (score 3)"),
        Patch(fc="#bfe3a0", label="suitable (score 2)"),
        Patch(fc="#d9d9d9", label="not suitable")],
        loc="lower left", fontsize=8.2, framealpha=0.9)

    # 4) candidate solar
    F.draw_base(ax[3], xlim, ylim, res_m=res, shade_ghi=True)
    if len(candW):
        candW.plot(ax=ax[3], facecolor=F.SOLAR, edgecolor="#7a2800", linewidth=0.1, zorder=2)
    ax[3].set_title("4.  Candidate solar", fontsize=13, fontweight="bold")
    ax[3].text(0.5, -0.04, f"suitable land = {dev_km2:,.0f} km² × 62 MW/km²",
               transform=ax[3].transAxes, ha="center", va="top", fontsize=9.5, color="#555")
    ax[3].legend(handles=[Patch(fc=F.SOLAR, ec="#7a2800", label="developable solar land")],
                 loc="lower left", fontsize=8.2, framealpha=0.9)

    # flow arrows between panels
    for xf in (0.253, 0.503, 0.753):
        fig.text(xf, 0.46, "➜", ha="center", va="center", fontsize=22, color=F.SOLAR)

    fig.suptitle(f"How Garuda finds developable solar land — worked example near {name}, Timor",
                 fontsize=17, fontweight="bold", x=0.01, ha="left", y=0.96)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=170, bbox_inches="tight", facecolor="white")
    print("wrote", args.out, "| developable", round(dev_km2), "km2")


if __name__ == "__main__":
    main()
