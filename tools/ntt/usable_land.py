"""Developable solar land for the NTT / Timor case, from the usable-land polygon layer.

Turns a large GIS suitability layer into two small, auditable artifacts: a
per-village developable-MW table, and an island-level screening figure. The source
layer stays outside the repo (it is hundreds of MB and gitignored); only the
derived CSV is committed, so results stay reproducible without vendoring the GIS.

    # summarise; writes nothing
    python -m tools.ntt.usable_land --shapefile ../usable_land_ntt/usable_land_ntt.shp

    # write the per-village table
    python -m tools.ntt.usable_land --shapefile <path> \
        --out data_indonesia/2030/timor/village_solar_land.csv

    # ...and push it into a dataset's village solar Max_Cap_MW
    python -m tools.ntt.usable_land --shapefile <path> \
        --out data_indonesia/2030/timor/village_solar_land.csv \
        --patch-dataset data_indonesia/2030/timor

**What the layer does and does not carry.** Measured on the NTT layer (145,190
polygons, EPSG:32751, `Area` verified as m² against true UTM geometry):

- land-cover class (`desc_en`) and kabupaten (`WADMKK`) are fully populated;
- `WADMKC` (kecamatan) and `WADMKD` (desa) are **100 % empty**, so land cannot be
  joined to a village by name — allocation here is spatial (see `allocate`);
- every PV capacity column shipped with the layer (`PVcap_MWp`, `Gen_GWh_y`,
  `Capacity`, `MWh_year`, `area_ha`, `Slope10`) is **identically zero** — they are
  placeholders from an unfinished workflow. Capacity is computed here instead,
  from area × an explicit `--mwp-per-km2`, so the assumption is visible.

**Settlement Area is excluded by default.** The layer's own definition of "usable"
includes 384 km² of settlement across the Timor footprint. `--include-classes` /
`--exclude-classes` override; whatever you choose is written into the output
header so a result can be traced to its land assumption.

**Villages with no coordinates fall back to the sited median**, matching the
policy `tools/ntt/build_timor.py` already documents. On the shipped Timor manifest
that is 153 of 780 villages, and the count is always reported. `--fallback zero`
instead leaves them at 0 — which `optimizer.jl` reads as *unbounded*, not as no
land, so it is rarely what you want.

Runs on Python + pandas + fiona/shapely/pyproj; no solver.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NA = dict(encoding="utf-8-sig", keep_default_na=False, na_values=[""])

# Utility-scale fixed-tilt PV in the tropics, ~2 ha per MWp.
DEFAULT_MWP_PER_KM2 = 50.0
# Land further than this from a village is counted in the island total but not
# allocated to any village — a village cannot plausibly develop it.
DEFAULT_MAX_RADIUS_KM = 10.0
# The layer's own "usable" set includes settlement; solar on rooftops is a
# different technology with different costs, so it is out by default.
DEFAULT_EXCLUDE = ("Settlement Area",)
# The four kabupaten (plus the city) that make up the 780-village Timor footprint.
# Malaka is in NTT and on Timor island but outside the modelled village set.
TIMOR_KABUPATEN = ("Kupang", "Kota Kupang", "Timor Tengah Selatan",
                   "Timor Tengah Utara", "Belu")


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def read_polygons(shapefile, kabupaten, exclude_classes, include_classes, report=print):
    """Stream the layer; return (records, stats). Geometry is reduced to a centroid."""
    try:
        import fiona
        from shapely.geometry import shape
    except ImportError:  # pragma: no cover
        raise SystemExit("this tool needs fiona + shapely (pip install fiona shapely pyproj)")

    kabset = {k.lower() for k in kabupaten} if kabupaten else None
    excl = {c.lower() for c in exclude_classes}
    incl = {c.lower() for c in include_classes} if include_classes else None

    xs, ys, areas, covers, kabs = [], [], [], [], []
    seen_cover, seen_kab = defaultdict(float), defaultdict(float)
    n_total = n_kept = 0
    dropped_class = defaultdict(float)

    with fiona.open(shapefile) as src:
        crs = src.crs
        for feat in src:
            n_total += 1
            p = feat["properties"]
            kab = str(p.get("WADMKK") or "")
            if kabset is not None and kab.lower() not in kabset:
                continue
            cover = str(p.get("desc_en") or "")
            area = float(p.get("Area") or 0.0)
            seen_cover[cover] += area
            seen_kab[kab] += area
            if incl is not None and cover.lower() not in incl:
                dropped_class[cover] += area
                continue
            if cover.lower() in excl:
                dropped_class[cover] += area
                continue
            if area <= 0:
                continue
            c = shape(feat["geometry"]).centroid
            xs.append(c.x); ys.append(c.y)
            areas.append(area); covers.append(cover); kabs.append(kab)
            n_kept += 1

    stats = dict(crs=crs, n_total=n_total, n_in_region=int(sum(1 for _ in ())) or None,
                 n_kept=n_kept, by_cover=dict(seen_cover), by_kab=dict(seen_kab),
                 dropped_class=dict(dropped_class))
    report(f"  layer: {n_total:,} polygons; {n_kept:,} kept after region + class filter")
    return dict(x=xs, y=ys, area=areas, cover=covers, kab=kabs), stats


def village_points(dataset_dir, crs_to):
    """(ids, x, y, n_missing) for villages with coordinates, projected into the layer CRS."""
    from pyproj import Transformer

    man = None
    for name in ("timor_villages_manifest.csv", "village_solar_potential.csv"):
        p = os.path.join(dataset_dir, name)
        if os.path.isfile(p):
            man = pd.read_csv(p, **NA)
            break
    if man is None:
        raise SystemExit(f"no village manifest in {dataset_dir} "
                         "(expected timor_villages_manifest.csv or village_solar_potential.csv)")
    idcol = "Village" if "Village" in man.columns else man.columns[0]
    lat, lon = _num(man.get("lat")), _num(man.get("lon"))
    ok = lat.notna() & lon.notna()
    tf = Transformer.from_crs("EPSG:4326", crs_to, always_xy=True)
    x, y = tf.transform(lon[ok].to_numpy(), lat[ok].to_numpy())
    return (man.loc[ok, idcol].astype(int).to_numpy(), x, y,
            list(man[idcol].astype(int)), int((~ok).sum()))


def allocate(poly, vx, vy, vids, max_radius_km, mode="shared", report=print):
    """Attribute polygon area to villages. Returns (m² per village, unallocated, allocated).

    Neither obvious approach is right on its own:

    - a plain **buffer** (all land within R km) counts the same hectare once for
      every village in range, so the per-village figures sum to several times the
      land that exists;
    - pure **nearest-village** assignment uses each hectare once but starves any
      village that is never the closest — measured here, 178 of 627 villages with
      coordinates got nothing while a neighbour a few hundred metres away got
      hundreds of MW.

    `shared` (the default) splits each polygon equally among the villages within
    the radius. The total is preserved exactly, no hectare is double counted, and
    no village with land nearby is left at zero. `nearest` is kept for comparison.
    """
    import numpy as np

    px = np.asarray(poly["x"], dtype=float); py = np.asarray(poly["y"], dtype=float)
    pa = np.asarray(poly["area"], dtype=float)
    vxa = np.asarray(vx, dtype=float); vya = np.asarray(vy, dtype=float)
    if len(px) == 0 or len(vxa) == 0:
        return {}, float(pa.sum()), 0.0

    r2 = (max_radius_km * 1000.0) ** 2
    totals = np.zeros(len(vxa))
    unallocated = 0.0
    # Chunked over polygons: the full distance matrix would be
    # len(polygons) x len(villages), which is ~14 M entries on the real layer.
    # numpy only — scipy is not among the project's CI dependencies.
    CHUNK = 2048
    for lo in range(0, len(px), CHUNK):
        hi = min(lo + CHUNK, len(px))
        d2 = ((px[lo:hi, None] - vxa[None, :]) ** 2
              + (py[lo:hi, None] - vya[None, :]) ** 2)
        area = pa[lo:hi]
        if mode == "nearest":
            idx = d2.argmin(axis=1)
            within = d2[np.arange(hi - lo), idx] <= r2
            np.add.at(totals, idx[within], area[within])
            unallocated += float(area[~within].sum())
        else:
            near = d2 <= r2
            counts = near.sum(axis=1)
            has = counts > 0
            unallocated += float(area[~has].sum())
            if has.any():
                share = np.where(has, area / np.maximum(counts, 1), 0.0)
                totals += (near * share[:, None]).sum(axis=0)

    out = {int(vids[i]): float(t) for i, t in enumerate(totals) if t > 0}
    allocated = float(pa.sum()) - unallocated
    report(f"  {mode} allocation: {allocated/1e6:,.1f} km² across {len(out):,} village(s) "
           f"within {max_radius_km:g} km; {unallocated/1e6:,.1f} km² beyond any village")
    return dict(out), unallocated, allocated


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shapefile", required=True, help="path to usable_land_ntt.shp")
    ap.add_argument("--dataset", default=os.path.join(REPO, "data_indonesia", "2030", "timor"),
                    help="dataset supplying the village coordinates")
    ap.add_argument("--kabupaten", default=",".join(TIMOR_KABUPATEN),
                    help="comma-separated WADMKK filter; empty = the whole layer")
    ap.add_argument("--exclude-classes", default=",".join(DEFAULT_EXCLUDE),
                    help="comma-separated desc_en classes to drop (default: Settlement Area)")
    ap.add_argument("--include-classes", default="",
                    help="if given, keep ONLY these desc_en classes")
    ap.add_argument("--mwp-per-km2", type=float, default=DEFAULT_MWP_PER_KM2,
                    help="land-use factor (default 50 MWp/km², ~2 ha/MWp)")
    ap.add_argument("--max-radius-km", type=float, default=DEFAULT_MAX_RADIUS_KM,
                    help="attribute land to villages within this distance (default 10 km)")
    ap.add_argument("--mode", choices=("shared", "nearest"), default="shared",
                    help="'shared' splits each polygon among the villages in range "
                         "(total preserved, nobody starved); 'nearest' assigns it to "
                         "the closest one only")
    ap.add_argument("--fallback", choices=("median", "zero"), default="median",
                    help="cap for villages with no coordinates. 'median' matches "
                         "tools/ntt/build_timor.py's documented policy; 'zero' is read "
                         "by the model as UNBOUNDED, which is rarely what you want")
    ap.add_argument("--out", default=None, help="write the per-village CSV here")
    ap.add_argument("--patch-dataset", default=None,
                    help="also write the MW into this dataset's village solar Max_Cap_MW")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.shapefile):
        raise SystemExit(f"shapefile not found: {args.shapefile}")
    kab = tuple(k.strip() for k in args.kabupaten.split(",") if k.strip())
    excl = tuple(c.strip() for c in args.exclude_classes.split(",") if c.strip())
    incl = tuple(c.strip() for c in args.include_classes.split(",") if c.strip())

    print(f"== developable solar land from {os.path.basename(args.shapefile)} ==")
    poly, stats = read_polygons(args.shapefile, kab, excl, incl)
    kept_km2 = sum(poly["area"]) / 1e6
    print(f"  region: {', '.join(kab) if kab else 'entire layer'}")
    print(f"  classes excluded: {', '.join(excl) if excl else '(none)'}")
    if stats["dropped_class"]:
        for c, a in sorted(stats["dropped_class"].items(), key=lambda x: -x[1]):
            print(f"     dropped {c:32s} {a/1e6:>8,.1f} km²")
    print(f"\n  developable land : {kept_km2:,.1f} km²")
    print(f"  at {args.mwp_per_km2:g} MWp/km²  : {kept_km2 * args.mwp_per_km2 / 1000:,.1f} GWp")

    print("\n  by kabupaten (developable km² | GWp):")
    by_kab = defaultdict(float)
    for k, a in zip(poly["kab"], poly["area"]):
        by_kab[k] += a
    for k, a in sorted(by_kab.items(), key=lambda x: -x[1]):
        print(f"     {k:26s} {a/1e6:>8,.1f} | {a/1e6*args.mwp_per_km2/1000:>7,.1f}")

    vids_ok, vx, vy, all_ids, n_missing = village_points(args.dataset, stats["crs"])
    print(f"\n  villages: {len(all_ids):,} total, {len(vids_ok):,} with coordinates, "
          f"{n_missing:,} without")
    alloc, unalloc, allocated = allocate(poly, vx, vy, vids_ok, args.max_radius_km,
                                        mode=args.mode)

    # villages that were located and DID get land, used for the fallback median
    located = {int(v) for v in vids_ok}
    sited_mw = sorted(alloc[v] / 1e6 * args.mwp_per_km2 for v in alloc if alloc[v] > 0)
    fallback_mw = (round(sited_mw[len(sited_mw) // 2], 2)
                   if (sited_mw and args.fallback == "median") else 0.0)

    rows, n_fallback = [], 0
    for vid in all_ids:
        vid = int(vid)
        m2 = alloc.get(vid, 0.0)
        mw = round(m2 / 1e6 * args.mwp_per_km2, 2)
        source = "sited"
        if mw <= 0:
            mw, source = fallback_mw, ("fallback" if fallback_mw > 0 else "unbounded")
            n_fallback += 1
        rows.append({"Village": vid,
                     "developable_km2": round(m2 / 1e6, 4),
                     "developable_MW": mw,
                     "source": source})
    df = pd.DataFrame(rows)
    print(f"  {n_fallback:,} village(s) had no land attributed "
          f"(no coordinates, or none within {args.max_radius_km:g} km)")
    if fallback_mw > 0:
        print(f"     -> given the sited median, {fallback_mw:,.1f} MW "
              f"(matching build_timor.py's policy)")
    else:
        print("     -> left at 0, which the model reads as UNBOUNDED, not as no land")
    print(f"  per-village MW: median {df['developable_MW'].median():,.1f}, "
          f"max {df['developable_MW'].max():,.1f}")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as fh:
            fh.write(f"# developable solar land per village, derived from "
                     f"{os.path.basename(args.shapefile)}\n")
            fh.write(f"# region={'|'.join(kab)} excluded_classes={'|'.join(excl) or 'none'} "
                     f"mwp_per_km2={args.mwp_per_km2:g} max_radius_km={args.max_radius_km:g}\n")
            fh.write(f"# nearest-village allocation; land beyond the radius "
                     f"({unalloc/1e6:,.1f} km²) is not attributed to any village\n")
            df.to_csv(fh, index=False)
        print(f"\n  wrote {os.path.relpath(args.out, REPO)}")

    if args.patch_dataset:
        patch_dataset(args.patch_dataset, df)
    return 0


def patch_dataset(dataset_dir, df):
    """Write developable_MW into the dataset's village solar Max_Cap_MW."""
    p = os.path.join(dataset_dir, "village_generators.csv")
    if not os.path.isfile(p):
        raise SystemExit(f"no village_generators.csv in {dataset_dir}")
    g = pd.read_csv(p, **NA)
    solar = g["technology"].astype(str).str.lower() == "solar"
    caps = dict(zip(df["Village"].astype(int), df["developable_MW"].astype(float)))
    before = _num(g.loc[solar, "Max_Cap_MW"]).copy()
    g.loc[solar, "Max_Cap_MW"] = [caps.get(int(v), 0.0) for v in g.loc[solar, "Village"]]
    g.to_csv(p, index=False)
    after = _num(g.loc[solar, "Max_Cap_MW"])
    print(f"  patched {int(solar.sum()):,} solar row(s) in "
          f"{os.path.relpath(p, REPO)}")
    print(f"    Max_Cap_MW median {before.median():,.1f} -> {after.median():,.1f}; "
          f"total {before.sum()/1000:,.1f} -> {after.sum()/1000:,.1f} GW")


if __name__ == "__main__":
    sys.exit(main())
