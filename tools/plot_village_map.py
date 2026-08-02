#!/usr/bin/env python3
"""F14 orientation map: where the 780 Timor villages are, and the third that isn't.

Plain-matplotlib scatter of every village in
`data_indonesia/2030/timor/village_solar_potential.csv` that carries
coordinates: dot area proportional to households, colour = kabupaten (four
fixed categorical hues in kabupaten-name sort order), one axis pair in
degrees with a 1/cos(lat) x-correction standing in for a projection.
No basemap and no admin polygons are drawn — none ship with the repo and
geopandas is not assumed.

The figure's one obligation beyond orientation is the caption: the villages
WITHOUT coordinates are counted from the same file at run time and reported
as a share of villages and of households ("the third that is not on the
map"). They are modelled and fully costed in every run; they are only
unlocatable. Do not strip that block for a deck.

Usage:
    python3 tools/plot_village_map.py                 # -> results/figures/village_map.png
    python3 tools/plot_village_map.py --out fig.png

Requires matplotlib and pandas (matplotlib is not part of the core pip
set). Solver-free; reads inputs only, no results directory needed.
"""
import argparse
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(REPO, "data_indonesia", "2030", "timor", "village_solar_potential.csv")

# ---- palette (reference dataviz palette, light mode) ----
# Categorical hues in FIXED order, assigned to kabupaten sorted by name.
KAB_HUES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # blue, orange, aqua, yellow
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"

REF_LAT = -9.5          # Timor mid-latitude for the aspect correction
HH_TO_PT2 = 0.04        # dot area (pt^2) per household — area-proportional


def _read(path):
    """Dataset CSV read convention (preserves the literal fuel name 'None')."""
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False,
                       na_values=[""])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures",
                                                  "village_map.png"),
                    help="output PNG path (default: results/figures/village_map.png)")
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    df = _read(CSV)
    kabs = sorted(df["kabupaten"].unique())
    hues = dict(zip(kabs, KAB_HUES))

    missing = df["lat"].isna() | df["lon"].isna()
    shown, hidden = df[~missing], df[missing]
    n, n_hidden = len(df), len(hidden)
    hh_total = df["households"].sum()
    hh_hidden = hidden["households"].sum()

    fig, ax = plt.subplots(figsize=(10.0, 8.2))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # Dots, largest first so small villages stay visible on top.
    for kab in kabs:
        sub = shown[shown["kabupaten"] == kab].sort_values("households",
                                                           ascending=False)
        ax.scatter(sub["lon"], sub["lat"], s=sub["households"] * HH_TO_PT2,
                   color=hues[kab], alpha=0.8, edgecolors=SURFACE,
                   linewidths=0.4, zorder=3)

    # Equal-ish ground distances: 1 deg lon shrinks by cos(lat) at this latitude.
    ax.set_aspect(1.0 / math.cos(math.radians(abs(REF_LAT))))

    # Recessive frame: hairline grid, muted ticks, no spines.
    ax.grid(True, color=GRID, linewidth=0.6, zorder=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=MUTED, labelcolor=INK_2, length=0, labelsize=9)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(
        lambda v, _: f"{v:.1f}\N{DEGREE SIGN}E"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(
        lambda v, _: f"{abs(v):.1f}\N{DEGREE SIGN}S"))

    # Kabupaten legend (identity), counts of what is actually drawn.
    kab_handles = [
        ax.scatter([], [], s=60, color=hues[k], alpha=0.8,
                   edgecolors=SURFACE, linewidths=0.4,
                   label=f"{k.title()} \N{EN DASH} "
                         f"{(shown['kabupaten'] == k).sum()} of "
                         f"{(df['kabupaten'] == k).sum()}")
        for k in kabs]
    leg1 = ax.legend(handles=kab_handles, loc="upper left", frameon=False,
                     fontsize=9.5, labelcolor=INK_2,
                     title="Kabupaten (villages drawn)",
                     borderaxespad=0.2, handletextpad=0.4)
    leg1.get_title().set_color(INK)
    leg1.get_title().set_fontsize(10)
    ax.add_artist(leg1)

    # Size key (magnitude): grey, so it reads as scale, not as a fifth series.
    size_handles = [
        ax.scatter([], [], s=v * HH_TO_PT2, facecolors=BASE,
                   edgecolors=MUTED, linewidths=0.5, label=f"{v:,}")
        for v in (500, 2000, 8000)]
    leg2 = ax.legend(handles=size_handles, loc="lower right", frameon=False,
                     fontsize=9, labelcolor=INK_2, title="Households",
                     labelspacing=1.1, borderaxespad=0.2, handletextpad=0.6)
    leg2.get_title().set_color(INK)
    leg2.get_title().set_fontsize(10)

    ax.set_title("Where the villages are", color=INK, fontsize=15,
                 loc="left", pad=24)
    ax.text(0, 1.015, f"{n} modelled villages of West Timor "
                      f"\N{EN DASH} dot area \N{PROPORTIONAL TO} households",
            transform=ax.transAxes, color=INK_2, fontsize=10.5)


    fig.subplots_adjust(left=0.075, right=0.97, top=0.90, bottom=0.16)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=args.dpi, facecolor=SURFACE)
    print(f"wrote {args.out}  ({len(shown)} villages drawn, "
          f"{n_hidden} without coordinates)")


if __name__ == "__main__":
    main()
