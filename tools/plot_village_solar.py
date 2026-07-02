#!/usr/bin/env python3
"""Figure: one village and the solar-suitable land available around it.

Grounds the story on a real Timor (NTT) village. Shows the modelled 5 km solar
catchment, the QGIS suitable-land polygons that make up its developable-PV
ceiling, the nearest grid substation, and an island-locator inset.

Data
----
  data_indonesia/2030/timor/village_solar_potential.csv   village pts + solar_MW + hub
  data_indonesia/2030/timor/timor_villages_manifest.csv    ghi, households
  ~/Desktop/QGIS_NEW/candidate_solar_timor.gpkg            suitable-land polygons (EPSG:32751)
  ~/Desktop/QGIS_NEW/substations_projected.shp             substation points
  province GeoJSON (fetched)                                island outline for the inset

Usage
-----
  python tools/plot_village_solar.py                       # default village (MANUSAK)
  python tools/plot_village_solar.py --village 232
  python tools/plot_village_solar.py --desa NAIBONAT --out docs/img/foo.png
"""
import argparse
import os
import urllib.request

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Circle
from matplotlib.lines import Line2D
from shapely.geometry import Point

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMOR = os.path.join(REPO, "data_indonesia", "2030", "timor")
GIS = os.path.expanduser("~/Desktop/QGIS_NEW")
GEOJSON_URL = ("https://raw.githubusercontent.com/superpikar/indonesia-geojson/"
               "master/indonesia-province-simple.json")
METRIC = 32751          # UTM 51S, matches the candidate layer
RADIUS_KM = 5.0         # modelled per-village solar catchment
DENSITY = 62.0          # MW per km2 of suitable land (QGIS PV density)

SOLAR = "#D64500"       # suitable land inside the catchment (pops over GHI ramp)
SOLAR_OUT = "#E8842E"   # suitable land outside the catchment
SEA = "#cfe6f2"
LAND = "#f3efe3"
INK = "#2a2a2a"


def _load_villages():
    sp = pd.read_csv(os.path.join(TIMOR, "village_solar_potential.csv"))
    man = pd.read_csv(os.path.join(TIMOR, "timor_villages_manifest.csv"))
    return sp.merge(man[["Village", "ghi"]], on="Village", how="left")


def _ntt(scratch):
    src = os.path.join(scratch, "idn_prov.json")
    if not os.path.exists(src):
        urllib.request.urlretrieve(GEOJSON_URL, src)
    g = gpd.read_file(src)
    return g[g["Propinsi"].str.contains("NUSA TENGGARA TIMUR", case=False, na=False)]


def _island_outline(scratch):
    ntt = _ntt(scratch)
    # clip to (West) Timor to isolate the island for the locator inset
    timor_bbox = gpd.GeoDataFrame(
        geometry=[gpd.GeoSeries.from_wkt(
            ["POLYGON((123.4 -10.6,125.3 -10.6,125.3 -9.0,123.4 -9.0,123.4 -10.6))"])[0]],
        crs=4326)
    return gpd.clip(ntt.to_crs(4326), timor_bbox)


GHI_LO, GHI_HI = 5.0, 6.0           # kWh/m2/day colour range on Timor
GHI_CMAP = None                     # built lazily


def _ghi_cmap():
    global GHI_CMAP
    if GHI_CMAP is None:
        from matplotlib.colors import LinearSegmentedColormap
        GHI_CMAP = LinearSegmentedColormap.from_list(
            "ghi", ["#f3efe3", "#f6e6bf", "#f4d38a", "#efb55b"])
    return GHI_CMAP


def _reproj(path, xlim, ylim, res_m):
    """Read `path` over the metric view bbox and reproject to a metric grid."""
    import rasterio
    from rasterio.warp import reproject, Resampling, transform_bounds
    from rasterio.windows import from_bounds
    from affine import Affine
    with rasterio.open(path) as ds:
        w, s, e, n = transform_bounds(METRIC, ds.crs, xlim[0], ylim[0], xlim[1], ylim[1])
        pad = 0.03
        win = from_bounds(w - pad, s - pad, e + pad, n + pad, ds.transform)
        src = ds.read(1, window=win, boundless=True,
                      fill_value=(ds.nodata if ds.nodata is not None else 0)).astype("float32")
        if ds.nodata is not None:
            src[src == ds.nodata] = np.nan
        src_t, src_crs = ds.window_transform(win), ds.crs
    nx = max(1, int((xlim[1] - xlim[0]) / res_m))
    ny = max(1, int((ylim[1] - ylim[0]) / res_m))
    dst = np.full((ny, nx), np.nan, dtype="float32")
    reproject(src, dst, src_transform=src_t, src_crs=src_crs,
              dst_transform=Affine(res_m, 0, xlim[0], 0, -res_m, ylim[1]),
              dst_crs=METRIC, resampling=Resampling.bilinear)
    return dst


def _landsea_base(xlim, ylim, res_m=120):
    """RGBA raster for the view: sea from the DEM land mask, land shaded by GHI.
    Returns (rgba, extent) or (None, None)."""
    from matplotlib.colors import to_rgb, Normalize
    dem = os.path.join(GIS, "clipped_elevation.tif")
    ghi = os.path.join(GIS, "GHI.tif")
    if not os.path.exists(dem):
        return None, None
    elev = _reproj(dem, xlim, ylim, res_m)              # NaN over sea
    land = np.isfinite(elev)
    ny, nx = elev.shape
    rgba = np.zeros((ny, nx, 4), dtype="float32")
    rgba[..., :3] = to_rgb(SEA)
    rgba[..., 3] = 1.0
    if os.path.exists(ghi):
        g = _reproj(ghi, xlim, ylim, res_m)
        norm = Normalize(GHI_LO, GHI_HI)
        shade = _ghi_cmap()(norm(np.clip(g, GHI_LO, GHI_HI)))[..., :3]
        fill = np.repeat(np.array(to_rgb(LAND))[None, None, :], ny, 0).repeat(nx, 1)
        shade = np.where(np.isfinite(g)[..., None], shade, fill)
    else:
        shade = np.repeat(np.array(to_rgb(LAND))[None, None, :], ny, 0).repeat(nx, 1)
    rgba[..., :3] = np.where(land[..., None], shade, rgba[..., :3])
    return rgba, [xlim[0], xlim[1], ylim[0], ylim[1]]


def _scalebar(ax, x0, y0, length_m, label):
    ax.plot([x0, x0 + length_m], [y0, y0], color=INK, lw=2.5, solid_capstyle="butt")
    ax.text(x0 + length_m / 2, y0 + length_m * 0.10, label, ha="center", va="bottom",
            fontsize=8, color=INK)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--village", type=int, help="Village id")
    ap.add_argument("--desa", help="Village (desa) name, case-insensitive")
    ap.add_argument("--window-km", type=float, default=11.0)
    ap.add_argument("--out", default=os.path.join(REPO, "docs", "img", "village_solar.png"))
    ap.add_argument("--scratch", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()

    vg = _load_villages()
    vg = vg[vg["sited"] == True].copy()
    if args.desa:
        row = vg[vg["desa"].str.upper() == args.desa.upper()].iloc[0]
    elif args.village:
        row = vg[vg["Village"] == args.village].iloc[0]
    else:
        row = vg[vg["desa"] == "MANUSAK"].iloc[0]

    lat, lon = float(row["lat"]), float(row["lon"])
    solar_mw = float(row["solar_MW"])
    hubkm = float(row["hubdist_km"])
    hubname = str(row["hub_name"])
    ghi = float(row["ghi"])
    hh = int(row["households"])
    name = str(row["desa"]).title()
    kab = str(row["kabupaten"]).title()
    kec = str(row["kecamatan"]).title()

    # focus point + view window in the metric CRS
    pt = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(METRIC).iloc[0]
    half = args.window_km * 1000 / 2
    xlim = (pt.x - half, pt.x + half)
    ylim = (pt.y - half, pt.y + half)
    ring = pt.buffer(RADIUS_KM * 1000)

    # suitable-land polygons in view
    cand = gpd.read_file(os.path.join(GIS, "candidate_solar_timor.gpkg"))
    from shapely.geometry import box
    bbox = box(xlim[0], ylim[0], xlim[1], ylim[1])
    cand_v = gpd.clip(cand, bbox)
    cand_v = cand_v[cand_v.geom_type.isin(["Polygon", "MultiPolygon"])]
    inside = gpd.clip(cand_v, ring)
    suit_km2 = inside.area.sum() / 1e6

    # substations + nearby villages
    subs = gpd.read_file(os.path.join(GIS, "substations_projected.shp")).to_crs(METRIC)
    subs_v = subs[subs.intersects(bbox)]
    vg_m = gpd.GeoDataFrame(vg, geometry=gpd.points_from_xy(vg["lon"], vg["lat"]), crs=4326).to_crs(METRIC)
    near = vg_m[vg_m.geometry.within(bbox) & (vg_m["Village"] != row["Village"])]

    # ---- figure ----
    fig, ax = plt.subplots(figsize=(9.2, 9.2))
    ax.set_facecolor(SEA)
    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])

    # land/sea base from the GHI land mask (accurate coastline at ~275 m)
    rgba, extent = _landsea_base(xlim, ylim)
    if rgba is not None:
        ax.imshow(rgba, extent=extent, origin="upper", interpolation="nearest",
                  zorder=0, aspect="equal")
    else:  # fallback: whole frame is land
        ax.add_patch(plt.Rectangle((xlim[0], ylim[0]), xlim[1]-xlim[0], ylim[1]-ylim[0],
                                   facecolor=LAND, edgecolor="none", zorder=0))

    if len(cand_v):
        cand_v.plot(ax=ax, facecolor=SOLAR_OUT, edgecolor="none", alpha=0.72, zorder=1)
    if len(inside):
        inside.plot(ax=ax, facecolor=SOLAR, edgecolor="#7a2800", linewidth=0.12, zorder=2)

    # catchment ring
    ax.add_patch(Circle((pt.x, pt.y), RADIUS_KM*1000, fill=False, ls=(0, (6, 4)),
                        lw=2.0, ec="#b5530b", zorder=4))

    # nearby villages
    if len(near):
        ax.scatter(near.geometry.x, near.geometry.y, s=14, marker="o",
                   facecolor="white", edgecolor=INK, linewidth=0.6, zorder=5)

    # substations
    for _, s in subs_v.iterrows():
        ax.scatter([s.geometry.x], [s.geometry.y], s=130, marker="s",
                   facecolor="#2b6cb0", edgecolor="white", linewidth=1.2, zorder=6)

    # focus village
    ax.scatter([pt.x], [pt.y], s=340, marker="*", facecolor="#d62728",
               edgecolor="white", linewidth=1.4, zorder=7)
    ax.annotate(name, (pt.x, pt.y), xytext=(10, 10), textcoords="offset points",
                fontsize=13, fontweight="bold", color=INK, zorder=8,
                path_effects=[])

    # scale bar + north arrow
    _scalebar(ax, xlim[0] + half*0.10, ylim[0] + half*0.12, 2000, "2 km")
    ax.annotate("N", xy=(xlim[1]-half*0.10, ylim[1]-half*0.10),
                xytext=(xlim[1]-half*0.10, ylim[1]-half*0.28),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=2),
                ha="center", fontsize=12, fontweight="bold", color=INK)

    ax.set_title(f"Solar-suitable land around {name}",
                 fontsize=16, fontweight="bold", loc="left", pad=26)
    ax.text(0, 1.012, f"{kec}, {kab} — Timor, Nusa Tenggara Timur",
            transform=ax.transAxes, fontsize=10.5, color="#555", va="bottom")

    # stats box
    txt = (f"Households: {hh:,}\n"
           f"Solar resource (GHI): {ghi:.2f} kWh/m$^2$/day\n"
           f"Developable solar within {RADIUS_KM:.0f} km: {solar_mw:,.0f} MW\n"
           f"Suitable land in catchment: {suit_km2:,.0f} km$^2$\n"
           f"Nearest grid: {hubname} ({hubkm:.1f} km)")
    ax.text(0.015, 0.015, txt, transform=ax.transAxes, fontsize=9.6, va="bottom",
            ha="left", color=INK,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="#ccc", alpha=0.92), zorder=9)

    # legend
    handles = [
        Line2D([], [], marker="*", ls="", mfc="#d62728", mec="white", ms=15, label=f"{name} village"),
        Line2D([], [], marker="s", ls="", mfc="#2b6cb0", mec="white", ms=10, label="Grid substation"),
        Line2D([], [], marker="o", ls="", mfc="white", mec=INK, ms=7, label="Other villages"),
        plt.Rectangle((0,0),1,1, fc=SOLAR, ec="#7a2800", label="Suitable solar land (in catchment)"),
        plt.Rectangle((0,0),1,1, fc=SOLAR_OUT, ec="none", label="Suitable solar land (nearby)"),
        Line2D([], [], color="#b5530b", ls=(0,(6,4)), lw=2, label=f"{RADIUS_KM:.0f} km solar catchment"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=8.6, framealpha=0.92,
              borderpad=0.7, handletextpad=0.6)

    # GHI colourbar (land shading)
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    sm = ScalarMappable(norm=Normalize(GHI_LO, GHI_HI), cmap=_ghi_cmap())
    cax = ax.inset_axes([0.985, 0.02, 0.02, 0.26])
    cb = fig.colorbar(sm, cax=cax)
    cb.set_label("GHI  (kWh/m$^2$/day)", fontsize=8.5)
    cb.ax.tick_params(labelsize=7.5)

    # ---- island locator inset ----
    isl = _island_outline(args.scratch).to_crs(METRIC)
    axi = fig.add_axes([0.66, 0.66, 0.30, 0.24])
    axi.set_facecolor(SEA)
    if len(isl):
        isl.plot(ax=axi, facecolor=LAND, edgecolor="#999", linewidth=0.5)
    axi.scatter([pt.x], [pt.y], s=90, marker="*", facecolor="#d62728",
                edgecolor="white", linewidth=1.0, zorder=5)
    axi.set_xticks([]); axi.set_yticks([])
    axi.set_title("Timor (West) — NTT", fontsize=8.5, color="#555")
    for sp_ in axi.spines.values():
        sp_.set_edgecolor("#bbb")

    fig.tight_layout()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=190, bbox_inches="tight", facecolor="white")
    print("wrote", args.out)
    print(f"{name}: solar_MW={solar_mw:.0f}  suitable_km2={suit_km2:.1f}  hub={hubname} {hubkm:.1f}km")


if __name__ == "__main__":
    main()
