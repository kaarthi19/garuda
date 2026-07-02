"""Shared helpers for Garuda Timor/NTT presentation figures.

These figures are *presentation artifacts*, not part of the model run. They
depend on external GIS layers (DEM, GHI raster, candidate-land polygons,
substations, land cover) that are **not shipped in the repo** — they are large
and licensed separately. Point the scripts at your local copy with the
``GARUDA_GIS_DIR`` environment variable (default: ``~/Desktop/QGIS_NEW``); the
committed PNGs under ``docs/img/`` were rendered from such a copy. The village
CSVs the figures overlay *are* in the repo (``data_indonesia/2030/timor/``).

Expected files under ``$GARUDA_GIS_DIR`` (all EPSG:4326 unless noted):
  clipped_elevation.tif        DEM ~90 m, nodata over sea -> coastline
  GHI.tif                      GHI ~275 m (fills near-shore sea)
  candidate_solar_timor.gpkg   suitable-land polygons (EPSG:32751)
  substations_projected.shp    substation points
  idn_land_cover.shp           land cover w/ `suitable` 0/2/3
"""
import os
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMOR = os.path.join(REPO, "data_indonesia", "2030", "timor")
GIS = os.path.expanduser(os.environ.get("GARUDA_GIS_DIR", "~/Desktop/QGIS_NEW"))
DEM = os.path.join(GIS, "clipped_elevation.tif")
GHI = os.path.join(GIS, "GHI.tif")
CAND = os.path.join(GIS, "candidate_solar_timor.gpkg")
SUBS = os.path.join(GIS, "substations_projected.shp")
LANDCOVER = os.path.join(GIS, "idn_land_cover.shp")
GEOJSON_URL = ("https://raw.githubusercontent.com/superpikar/indonesia-geojson/"
               "master/indonesia-province-simple.json")

METRIC = 32751          # UTM 51S
RADIUS_KM = 5.0
PV_DENSITY = 62.0       # MW / km2 suitable land
MAX_SLOPE = 15.0
MIN_SUITABLE = 2

# palette
SOLAR = "#D64500"       # developable land (emphasis)
SOLAR2 = "#E8842E"      # developable land (context)
SEA = "#cfe6f2"
LAND = "#f3efe3"
INK = "#2a2a2a"
RED = "#d62728"
BLUE = "#2b6cb0"
GHI_LO, GHI_HI = 5.0, 6.0

# West-Timor bounding box (lon/lat) used to isolate the island
TIMOR_BBOX = (123.35, -10.65, 125.25, -8.85)

_GHI_CMAP = None


def ghi_cmap():
    global _GHI_CMAP
    if _GHI_CMAP is None:
        from matplotlib.colors import LinearSegmentedColormap
        _GHI_CMAP = LinearSegmentedColormap.from_list(
            "ghi", ["#f3efe3", "#f6e6bf", "#f4d38a", "#efb55b"])
    return _GHI_CMAP


def provinces(scratch):
    """Indonesia province polygons (EPSG:4326), fetched/cached to `scratch`."""
    import geopandas as gpd
    import urllib.request
    src = os.path.join(scratch, "idn_prov.json")
    if not os.path.exists(src):
        urllib.request.urlretrieve(GEOJSON_URL, src)
    return gpd.read_file(src)


def timor_land(scratch):
    """(West) Timor land polygon clipped from the NTT province geometry."""
    import geopandas as gpd
    from shapely.geometry import box
    g = provinces(scratch)
    ntt = g[g["Propinsi"].str.contains("NUSA TENGGARA TIMUR", case=False, na=False)]
    return gpd.clip(ntt.to_crs(4326), box(*TIMOR_BBOX))


def load_villages():
    import pandas as pd
    sp = pd.read_csv(os.path.join(TIMOR, "village_solar_potential.csv"))
    man = pd.read_csv(os.path.join(TIMOR, "timor_villages_manifest.csv"))
    keep = [c for c in ("Village", "ghi", "ghi_matched", "diesel_mw", "annual_kwh")
            if c in man.columns]
    return sp.merge(man[keep], on="Village", how="left")


def village_gdf(df):
    import geopandas as gpd
    d = df.dropna(subset=["lat", "lon"]).copy()
    return gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d["lon"], d["lat"]),
                            crs=4326).to_crs(METRIC)


def bbox_metric(lon0, lat0, lon1, lat1):
    """lon/lat bbox -> (xlim, ylim) in METRIC."""
    import geopandas as gpd
    from shapely.geometry import Point
    pts = gpd.GeoSeries([Point(lon0, lat0), Point(lon1, lat1)], crs=4326).to_crs(METRIC)
    xs = [p.x for p in pts]; ys = [p.y for p in pts]
    return (min(xs), max(xs)), (min(ys), max(ys))


def reproj(path, xlim, ylim, res_m):
    """Read `path` over metric bbox, reproject to a metric grid, NaN at nodata."""
    import rasterio
    from rasterio.warp import reproject as _rp, Resampling, transform_bounds
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
    _rp(src, dst, src_transform=src_t, src_crs=src_crs,
        dst_transform=Affine(res_m, 0, xlim[0], 0, -res_m, ylim[1]),
        dst_crs=METRIC, resampling=Resampling.bilinear)
    return dst


def land_mask(xlim, ylim, res_m):
    """Boolean land mask (True over land) from the DEM."""
    return np.isfinite(reproj(DEM, xlim, ylim, res_m))


def landsea_rgba(xlim, ylim, res_m=120, shade_ghi=True):
    """RGBA base image: sea from DEM, land flat or GHI-shaded. Returns (rgba, extent)."""
    from matplotlib.colors import to_rgb, Normalize
    if not os.path.exists(DEM):
        return None, None
    land = np.isfinite(reproj(DEM, xlim, ylim, res_m))
    ny, nx = land.shape
    rgba = np.zeros((ny, nx, 4), dtype="float32")
    rgba[..., :3] = to_rgb(SEA)
    rgba[..., 3] = 1.0
    if shade_ghi and os.path.exists(GHI):
        g = reproj(GHI, xlim, ylim, res_m)
        shade = ghi_cmap()(Normalize(GHI_LO, GHI_HI)(np.clip(g, GHI_LO, GHI_HI)))[..., :3]
        fill = np.tile(np.array(to_rgb(LAND)), (ny, nx, 1))
        shade = np.where(np.isfinite(g)[..., None], shade, fill)
    else:
        shade = np.tile(np.array(to_rgb(LAND)), (ny, nx, 1))
    rgba[..., :3] = np.where(land[..., None], shade, rgba[..., :3])
    return rgba, [xlim[0], xlim[1], ylim[0], ylim[1]]


def draw_base(ax, xlim, ylim, res_m=120, shade_ghi=True):
    import matplotlib.pyplot as plt
    ax.set_facecolor(SEA)
    rgba, extent = landsea_rgba(xlim, ylim, res_m, shade_ghi)
    if rgba is not None:
        ax.imshow(rgba, extent=extent, origin="upper", interpolation="nearest",
                  zorder=0, aspect="equal")
    else:
        ax.add_patch(plt.Rectangle((xlim[0], ylim[0]), xlim[1]-xlim[0], ylim[1]-ylim[0],
                                   facecolor=LAND, zorder=0))
    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])


def scalebar(ax, xlim, ylim, length_m, label, frac=(0.06, 0.06)):
    x0 = xlim[0] + (xlim[1]-xlim[0]) * frac[0]
    y0 = ylim[0] + (ylim[1]-ylim[0]) * frac[1]
    ax.plot([x0, x0 + length_m], [y0, y0], color=INK, lw=2.6, solid_capstyle="butt", zorder=9)
    ax.text(x0 + length_m/2, y0 + (ylim[1]-ylim[0])*0.012, label, ha="center",
            va="bottom", fontsize=8.5, color=INK, zorder=9)


def north_arrow(ax, xlim, ylim, frac=(0.94, 0.90)):
    x = xlim[0] + (xlim[1]-xlim[0]) * frac[0]
    y = ylim[0] + (ylim[1]-ylim[0]) * frac[1]
    dy = (ylim[1]-ylim[0]) * 0.06
    ax.annotate("N", xy=(x, y), xytext=(x, y - dy),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=2),
                ha="center", fontsize=12, fontweight="bold", color=INK, zorder=9)
