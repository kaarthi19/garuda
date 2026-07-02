#!/usr/bin/env python3
"""Hero figure: Garuda's multi-scale resolution, nation -> island -> zone -> village.

Four linked panels that progressively zoom in, with connector lines showing where
each panel drills into the previous one. The differentiator no national model can
draw: from the 100 GW program down to one village's 5 km solar catchment.

  python tools/plot_zoom_pyramid.py --desa BINAUS
"""
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import geopandas as gpd
from matplotlib.patches import Rectangle, Circle
from matplotlib.patches import ConnectionPatch
from shapely.geometry import Point

import figlib as F

HL = "#d64500"          # highlight / zoom colour


def _rect(ax, xlim, ylim, **kw):
    ax.add_patch(Rectangle((xlim[0], ylim[0]), xlim[1]-xlim[0], ylim[1]-ylim[0], **kw))


def _connect(fig, axA, axB, xlimA, ylimA):
    """Draw connector lines from rect corners in axA to the left edge of axB."""
    # right edge of the highlight rect in A -> left corners of B's data box
    xr = xlimA[1]
    for yA, cornerB in ((ylimA[1], 1.0), (ylimA[0], 0.0)):
        con = ConnectionPatch(
            xyA=(xr, yA), coordsA=axA.transData,
            xyB=(0.0, cornerB), coordsB=axB.transAxes,
            color=HL, lw=1.2, ls=(0, (4, 3)), zorder=20, alpha=0.8)
        fig.add_artist(con)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desa", default="BINAUS")
    ap.add_argument("--zone-km", type=float, default=42.0)
    ap.add_argument("--village-km", type=float, default=12.0)
    ap.add_argument("--scratch", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", default=os.path.join(F.REPO, "docs", "img", "zoom_pyramid_timor.png"))
    args = ap.parse_args()

    vg = F.load_villages()
    row = vg[(vg["desa"].str.upper() == args.desa.upper()) & vg["lat"].notna()].iloc[0]
    lat, lon, name = float(row["lat"]), float(row["lon"]), str(row["desa"]).title()
    hub, hubkm = str(row["hub_name"]), float(row["hubdist_km"])
    solar_mw, ghi = float(row["solar_MW"]), float(row["ghi"])

    pt = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(F.METRIC).iloc[0]
    zh = args.zone_km*1000/2
    zone_x, zone_y = (pt.x-zh, pt.x+zh), (pt.y-zh, pt.y+zh)
    vh = args.village_km*1000/2
    vil_x, vil_y = (pt.x-vh, pt.x+vh), (pt.y-vh, pt.y+vh)
    ring = pt.buffer(F.RADIUS_KM*1000)

    gv = F.village_gdf(vg)
    subs = gpd.read_file(F.SUBS).to_crs(F.METRIC)

    fig = plt.figure(figsize=(20, 6.4))
    gs = fig.add_gridspec(1, 4, wspace=0.06, left=0.01, right=0.99, top=0.86, bottom=0.04)
    axN, axI, axZ, axV = [fig.add_subplot(gs[0, i]) for i in range(4)]

    # ---- (1) Nation ----
    prov = F.provinces(args.scratch)
    ntt = prov["Propinsi"].str.contains("NUSA TENGGARA TIMUR", case=False, na=False)
    axN.set_facecolor(F.SEA)
    prov.plot(ax=axN, facecolor="#e7e2d5", edgecolor="white", linewidth=0.3)
    prov[ntt].plot(ax=axN, facecolor=HL, edgecolor="white", linewidth=0.4)
    tb = F.TIMOR_BBOX
    _rect(axN, (tb[0], tb[2]), (tb[1], tb[3]), fill=False, ec=HL, lw=1.6, zorder=10)
    axN.set_xlim(94, 142); axN.set_ylim(-11.5, 7.5)
    axN.set_xticks([]); axN.set_yticks([])
    axN.set_title("Indonesia — 100 GW program", fontsize=13, fontweight="bold")
    axN.text(0.5, -0.03, "33 grid zones · 8 island systems", transform=axN.transAxes,
             ha="center", va="top", fontsize=9.5, color="#555")

    # ---- (2) Timor island ----
    xlimI, ylimI = F.bbox_metric(*F.TIMOR_BBOX)
    F.draw_base(axI, xlimI, ylimI, res_m=260, shade_ghi=False)
    axI.scatter(gv.geometry.x, gv.geometry.y, s=5, c="#c0562a", alpha=0.7, zorder=3, lw=0)
    subI = subs.cx[xlimI[0]:xlimI[1], ylimI[0]:ylimI[1]]
    axI.scatter(subI.geometry.x, subI.geometry.y, s=45, marker="s", facecolor=F.BLUE,
                edgecolor="white", linewidth=0.8, zorder=5)
    _rect(axI, zone_x, zone_y, fill=False, ec=HL, lw=1.8, zorder=10)
    axI.set_title("Timor island — 780 villages", fontsize=13, fontweight="bold")
    axI.text(0.5, -0.03, "grid zone · substations · village demand", transform=axI.transAxes,
             ha="center", va="top", fontsize=9.5, color="#555")

    # ---- (3) Zone / district ----
    F.draw_base(axZ, zone_x, zone_y, res_m=90, shade_ghi=True)
    from shapely.geometry import box as _box
    cand = gpd.read_file(F.CAND).to_crs(F.METRIC)
    cand = cand[cand.geom_type.isin(["Polygon", "MultiPolygon"])]
    candZ = gpd.clip(cand, _box(zone_x[0], zone_y[0], zone_x[1], zone_y[1]))
    if len(candZ):
        candZ.plot(ax=axZ, facecolor=F.SOLAR, edgecolor="none", alpha=0.6, zorder=2)
    gvZ = gv.cx[zone_x[0]:zone_x[1], zone_y[0]:zone_y[1]]
    axZ.scatter(gvZ.geometry.x, gvZ.geometry.y, s=16, facecolor="white",
                edgecolor="#333", linewidth=0.5, zorder=4)
    subZ = subs.cx[zone_x[0]:zone_x[1], zone_y[0]:zone_y[1]]
    axZ.scatter(subZ.geometry.x, subZ.geometry.y, s=90, marker="s", facecolor=F.BLUE,
                edgecolor="white", linewidth=1.1, zorder=6)
    axZ.add_patch(Circle((pt.x, pt.y), F.RADIUS_KM*1000, fill=False, ls=(0, (5, 3)),
                         lw=1.4, ec="#b5530b", zorder=7))
    _rect(axZ, vil_x, vil_y, fill=False, ec=HL, lw=1.8, zorder=10)
    axZ.set_title(f"Local grid & resource", fontsize=13, fontweight="bold")
    axZ.text(0.5, -0.03, "developable land · siting to substations", transform=axZ.transAxes,
             ha="center", va="top", fontsize=9.5, color="#555")

    # ---- (4) Village catchment ----
    F.draw_base(axV, vil_x, vil_y, res_m=45, shade_ghi=True)
    candV = gpd.clip(cand, _box(vil_x[0], vil_y[0], vil_x[1], vil_y[1]))
    inside = gpd.clip(candV, ring)
    if len(candV):
        candV.plot(ax=axV, facecolor=F.SOLAR2, edgecolor="none", alpha=0.7, zorder=1)
    if len(inside):
        inside.plot(ax=axV, facecolor=F.SOLAR, edgecolor="#7a2800", linewidth=0.1, zorder=2)
    axV.add_patch(Circle((pt.x, pt.y), F.RADIUS_KM*1000, fill=False, ls=(0, (6, 4)),
                         lw=1.8, ec="#b5530b", zorder=4))
    subV = subs.cx[vil_x[0]:vil_x[1], vil_y[0]:vil_y[1]]
    axV.scatter(subV.geometry.x, subV.geometry.y, s=120, marker="s", facecolor=F.BLUE,
                edgecolor="white", linewidth=1.1, zorder=5)
    axV.scatter([pt.x], [pt.y], s=280, marker="*", facecolor=F.RED, edgecolor="white",
                linewidth=1.2, zorder=7)
    axV.annotate(name, (pt.x, pt.y), xytext=(8, 8), textcoords="offset points",
                 fontsize=12, fontweight="bold", color=F.INK, zorder=8)
    axV.set_title(f"{name} — 5 km solar catchment", fontsize=13, fontweight="bold")
    axV.text(0.5, -0.03,
             f"{solar_mw:,.0f} MW developable · GHI {ghi:.2f} · grid {hubkm:.1f} km",
             transform=axV.transAxes, ha="center", va="top", fontsize=9.5, color="#555")

    # ---- connectors ----
    _connect(fig, axN, axI, (tb[0], tb[2]), (tb[1], tb[3]))
    _connect(fig, axI, axZ, zone_x, zone_y)
    _connect(fig, axZ, axV, vil_x, vil_y)

    fig.suptitle("Garuda resolves the 100 GW program from nation to village",
                 fontsize=18, fontweight="bold", x=0.01, ha="left", y=0.975)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=170, bbox_inches="tight", facecolor="white")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
