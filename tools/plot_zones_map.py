#!/usr/bin/env python3
"""Render the map of Garuda's sub-national zonal division of Indonesia.

Produces `docs/img/zones_map.png` — a choropleth of Indonesia coloured by the
model's eight island systems, with the per-system grid-zone count. In the four
multi-zone systems (Sumatera, Jawa–Bali, Kalimantan, Sulawesi) the zones are
provinces; the rest are single/coarse island zones. Zone counts are read from the
data (`generators.csv` `Zone` column), so the figure stays in sync with the model.

    python tools/plot_zones_map.py            # fetches boundaries, writes the PNG
    python tools/plot_zones_map.py --geojson local.json --out docs/img/zones_map.png

Requires geopandas + matplotlib (`pip install geopandas matplotlib`). Province
boundaries come from public Indonesian administrative data
(github.com/superpikar/indonesia-geojson); only the rendered image is committed.
This is a documentation utility, not part of the modelling pipeline.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request

GEOJSON_URL = ("https://raw.githubusercontent.com/superpikar/indonesia-geojson/"
               "master/indonesia-province.json")

# province (as named in the GeoJSON) -> Garuda island system
PROVINCE_TO_ISLAND = {
    "DI. ACEH": "sumatera", "SUMATERA UTARA": "sumatera", "RIAU": "sumatera",
    "SUMATERA BARAT": "sumatera", "JAMBI": "sumatera", "SUMATERA SELATAN": "sumatera",
    "BENGKULU": "sumatera", "LAMPUNG": "sumatera", "BANGKA BELITUNG": "sumatera",
    "DKI JAKARTA": "jawa_bali", "PROBANTEN": "jawa_bali", "JAWA BARAT": "jawa_bali",
    "JAWA TENGAH": "jawa_bali", "DAERAH ISTIMEWA YOGYAKARTA": "jawa_bali",
    "JAWA TIMUR": "jawa_bali", "BALI": "jawa_bali",
    "KALIMANTAN BARAT": "kalimantan", "KALIMANTAN TENGAH": "kalimantan",
    "KALIMANTAN SELATAN": "kalimantan", "KALIMANTAN TIMUR": "kalimantan",
    "SULAWESI UTARA": "sulawesi", "GORONTALO": "sulawesi", "SULAWESI TENGAH": "sulawesi",
    "SULAWESI SELATAN": "sulawesi", "SULAWESI TENGGARA": "sulawesi",
    "MALUKU": "maluku", "MALUKU UTARA": "north_maluku",
    "NUSATENGGARA BARAT": "nusa_tenggara", "NUSA TENGGARA TIMUR": "nusa_tenggara",
    "IRIAN JAYA BARAT": "papua", "IRIAN JAYA TENGAH": "papua", "IRIAN JAYA TIMUR": "papua",
}
ISLANDS = ["sumatera", "jawa_bali", "kalimantan", "sulawesi", "papua",
           "nusa_tenggara", "maluku", "north_maluku"]
LABEL = {"sumatera": "Sumatera", "jawa_bali": "Jawa–Bali", "kalimantan": "Kalimantan",
         "sulawesi": "Sulawesi", "papua": "Papua", "nusa_tenggara": "Nusa Tenggara",
         "maluku": "Maluku", "north_maluku": "N. Maluku"}
COLOR = {"sumatera": "#4e79a7", "jawa_bali": "#f28e2b", "kalimantan": "#59a14f",
         "sulawesi": "#e15759", "papua": "#b07aa1", "nusa_tenggara": "#edc948",
         "maluku": "#76b7b2", "north_maluku": "#9c755f"}
# small nudges (lon, lat) so labels sit on land for cramped island groups
NUDGE = {"jawa_bali": (0, -1.4), "nusa_tenggara": (0, -1.2),
         "maluku": (0.4, 0.6), "north_maluku": (-0.3, 0.7), "papua": (0.5, 0)}


def zone_counts(data_root="data_indonesia", year="2030"):
    import pandas as pd
    out = {}
    for isl in ISLANDS:
        f = os.path.join(data_root, year, isl, "generators.csv")
        g = pd.read_csv(f, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
        out[isl] = int(pd.to_numeric(g["Zone"], errors="coerce").dropna().nunique())
    return out


def main(argv):
    ap = argparse.ArgumentParser(description="Render the Indonesia zonal-division map.")
    ap.add_argument("--geojson", help="local province GeoJSON (default: fetch from source)")
    ap.add_argument("--out", default="docs/img/zones_map.png")
    ap.add_argument("--data-root", default="data_indonesia")
    args = ap.parse_args(argv[1:])

    try:
        import geopandas as gpd
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patheffects as pe
    except ImportError:
        print("needs geopandas + matplotlib: pip install geopandas matplotlib", file=sys.stderr)
        return 3

    src = args.geojson
    if not src:
        src = "/tmp/idn_province.json"
        urllib.request.urlretrieve(GEOJSON_URL, src)

    zc = zone_counts(args.data_root)
    g = gpd.read_file(src)
    g["island"] = g["Propinsi"].map(PROVINCE_TO_ISLAND)
    unmapped = sorted(set(g.loc[g["island"].isna(), "Propinsi"]))
    if unmapped:
        print(f"warning: unmapped provinces: {unmapped}", file=sys.stderr)
    g = g.dropna(subset=["island"]).copy()

    fig, ax = plt.subplots(figsize=(13, 6.0))
    g.plot(ax=ax, color=g["island"].map(COLOR), edgecolor="white", linewidth=0.7)
    for isl, sub in g.groupby("island"):
        p = sub.geometry.unary_union.representative_point()
        dx, dy = NUDGE.get(isl, (0, 0))
        ax.annotate(f"{LABEL[isl]}\n{zc[isl]} zone{'s' if zc[isl] != 1 else ''}",
                    (p.x + dx, p.y + dy), ha="center", va="center", fontsize=8.5,
                    fontweight="bold", color="#15202b",
                    path_effects=[pe.withStroke(linewidth=2.4, foreground="white")])
    ax.set_xlim(94, 142)
    ax.set_ylim(-11.5, 8.0)
    ax.set_aspect(1.0)
    ax.set_axis_off()
    ax.set_title("Garuda — sub-national zonal division of Indonesia",
                 fontsize=15.5, fontweight="bold", loc="left", color="#15202b")
    ax.annotate(f"{len(ISLANDS)} island systems · {sum(zc.values())} grid zones — in the four "
                "multi-zone systems (Sumatera, Jawa–Bali, Kalimantan, Sulawesi) the zones are provinces",
                (0.0, -0.025), xycoords="axes fraction", fontsize=9, color="#5a6675")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=160, bbox_inches="tight", facecolor="white")
    print(f"wrote {args.out}  ({sum(zc.values())} zones across {len(ISLANDS)} island systems)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
