#!/usr/bin/env python3
"""Cost against carbon — the three Timor plans as one trade-off picture.

One scatter: annual system cost (x) against annual system CO2 (y), one point
per plan, with arrows from the islanded plan to the two coordinated ones. The
figure exists to make a single sentence unmissable: the big saving is bought
with coal, and the carbon-neutral saving is real but small.

All numbers read from the committed CSVs of the consistent full-8-week
trio (coordinated legs: the 2026-09-14 fix-and-verify exact LPs).

    python3 tools/plot_cost_vs_co2.py              # -> results/figures/

Form per the dataviz method: two measures -> a connected scatter, NOT a
dual-axis chart. One categorical hue for the plans; the coal-heavy point
carries the suite's fossil accent. Direct labels, no legend (three labelled
points need none).

Requires matplotlib + pandas. Solver-free.
"""
import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BLUE = "#2a78d6"
ORANGE = "#eb6834"     # the suite's fossil accent: the coal-substitution plan
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID_LN = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"

RESULTS = os.path.join(REPO, "results")
NA = dict(encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def _leg(run_dir):
    d = os.path.join(RESULTS, run_dir)
    num = lambda s: pd.to_numeric(s, errors="coerce")
    cost = float(num(pd.read_csv(os.path.join(d, "cost_results.csv"), **NA)
                     .iloc[0:1].Total_Costs).iloc[0])
    co2 = float(num(pd.read_csv(os.path.join(d, "clean_energy_results.csv"), **NA)
                    .iloc[0:1].CO2_Emissions).iloc[0]) / 1000.0
    return cost, co2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(RESULTS, "figures",
                                                  "cost_vs_co2.png"))
    args = ap.parse_args(argv)

    isl = _leg("village_timor__marketfix_2030_reference__ucrelax")
    unc = _leg("gridvillage_timor__marketfix_2030_reference__fixverify")
    cln = _leg("gridvillage_timor__marketfix_2030_clean__fixverify")

    fig, ax = plt.subplots(figsize=(9.8, 6.2), dpi=200)
    fig.subplots_adjust(left=0.10, right=0.965, top=0.84, bottom=0.13)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # arrows islanded -> each coordinated plan
    for tgt in (unc, cln):
        ax.annotate("", xy=tgt, xytext=isl,
                    arrowprops=dict(arrowstyle="->", lw=1.3, color=BASE,
                                    shrinkA=12, shrinkB=12))

    pts = [(isl, BLUE, "islanded\n780 microgrids", (14, 10), "left"),
           (unc, ORANGE, "coordinated, unconstrained\nruns on existing coal",
            (16, 10), "left"),
           (cln, BLUE, "coordinated, carbon-neutral\nsolar fleet intact,\n"
            f"save \\${isl[0]-cln[0]:.1f} M/yr at lower CO₂", (-16, 26), "right")]
    for (x, y), c, lab, (dx, dy), ha in pts:
        ax.plot([x], [y], "o", ms=12, color=c, zorder=4)
        ax.annotate(lab, xy=(x, y), xytext=(dx, dy),
                    textcoords="offset points", ha=ha,
                    va="bottom" if dy > 0 else "top",
                    fontsize=10, color=INK, fontweight="bold", linespacing=1.3)

    # the big delta, written on the long arrow
    ax.annotate(f"save \\${isl[0]-unc[0]:.1f} M/yr\n"
                f"+{unc[1]-isl[1]:,.0f} kt CO₂ (+{100*(unc[1]/isl[1]-1):.0f}%)",
                xy=((isl[0]+unc[0])/2, (isl[1]+unc[1])/2), xytext=(0, 12),
                textcoords="offset points", ha="center", fontsize=9, color=INK2)

    ax.set_xlabel("system cost  ($M/yr)", fontsize=10.5, color=INK2)
    ax.set_ylabel("system CO₂  (kt/yr)", fontsize=10.5, color=INK2)
    ax.set_xlim(74, 108)
    ax.set_ylim(560, 1200)
    ax.grid(True, color=GRID_LN, lw=0.8, zorder=0)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.spines["left"].set_color(BASE)
    ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=9)

    ax.set_title("What the wires buy — and what they cost in carbon",
                 fontsize=13.5, color=INK, loc="left", pad=26)
    ax.text(0.0, 1.045, "three plans for the same 780 villages; "
            "down-left is better", transform=ax.transAxes,
            fontsize=10, color=INK2)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}")
    print(f"  islanded       {isl[0]:9.5f} $M  {isl[1]:7.1f} kt")
    print(f"  unconstrained  {unc[0]:9.5f} $M  {unc[1]:7.1f} kt")
    print(f"  carbon-neutral {cln[0]:9.5f} $M  {cln[1]:7.1f} kt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
