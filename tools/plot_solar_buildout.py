#!/usr/bin/env python3
"""Solar buildout by planning regime — the 100 GW-programme exhibit.

One question, partner-first: how much solar does least-cost planning actually
deploy on Timor, and what does the answer depend on? Three regimes:

  islanded        every village a solar+storage+diesel microgrid (exact LP)
  coordinated     least-cost with the grid, no carbon constraint (incumbent)
  carbon-neutral  least-cost with the grid, CO2 capped at the islanded level
                  and RE share floored at the islanded share (incumbent; 2-week
                  model until fix-and-verify)

Each bar splits village solar vs grid (utility) solar. The middle bar is the
warning the study exists to deliver: with DMO coal available and no carbon
constraint, cost-optimal coordination DISMANTLES ~90% of the village solar the
islanded programme would build — cheap existing coal outcompetes distributed
solar. The third bar shows what survives when coordination may not out-emit
islanding.

Context annotations: MW as a share of the 100 GW national ambition (pure
arithmetic), and kW per household (436,995 households). Incumbent-based values
carry their achieved solver gap per the study's one-number convention.

Reads landed results; the carbon-neutral bar renders as "solving" until
results/gridvillage_timor__marketfix2w_2030_clean/ exists, then upgrades on
re-run. Requires matplotlib; solver-free.
"""
import argparse
import datetime as _dt
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BLUE, BLUE_LIGHT = "#2a78d6", "#86b6ef"   # village solar / grid solar (one ramp)
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID_LN, BASE, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
HOUSEHOLDS = 436_995


def _read(p):
    return pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def solar_mw(run_dir):
    """(village_solar_MW, grid_solar_MW) from a landed run, or None."""
    sg = os.path.join(run_dir, "site_generator_results.csv")
    if not os.path.exists(sg):
        return None
    s = _read(sg)
    village = float(s.loc[s.technology == "solar", "Total_MW"].sum())
    grid = 0.0
    gg = os.path.join(run_dir, "generator_results.csv")
    if os.path.exists(gg):
        g = _read(gg)
        grid = float(g.loc[g.technology == "solar", "Total_MW"].sum())
    return village, grid


def achieved_gap(log_path):
    gap = None
    if os.path.exists(log_path):
        for line in open(log_path, errors="ignore"):
            m = re.search(r"gap (\d+\.?\d*)%", line)
            if m:
                gap = float(m.group(1))
    return gap


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures",
                                                  "solar_buildout.png"))
    args = ap.parse_args(argv)

    R = os.path.join(REPO, "results")
    rows = [
        dict(label="islanded\n(one microgrid per village)",
             run=os.path.join(R, "village_timor_2030_reference"),
             note="exact LP — no solver gap", gap=None),
        dict(label="coordinated, unconstrained\n(DMO coal available)",
             run=os.path.join(R, "gridvillage_timor__marketfix_2030_reference__ucrelax"),
             note=None, gap=achieved_gap(os.path.join(REPO, "jobs", "ucr_marketfix_gridvillage", "solve.log"))),
        dict(label="coordinated, carbon-neutral\n(CO2 capped at islanded level)",
             run=os.path.join(R, "gridvillage_timor__marketfix2w_2030_clean"),
             note="2-week model; fix-and-verify pending",
             gap=achieved_gap(os.path.join(REPO, "jobs", "w2c_gridvillage", "solve.log"))),
    ]
    for r in rows:
        r["mw"] = solar_mw(r["run"])

    fig, ax = plt.subplots(figsize=(9.6, 5.4), dpi=200)
    fig.subplots_adjust(left=0.08, right=0.96, top=0.86, bottom=0.26)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    xs = range(len(rows))
    for i, r in enumerate(rows):
        if r["mw"] is None:
            ax.bar(i, 5, color=SURFACE, edgecolor=MUTED, ls="--", lw=1.2, width=0.55)
            ax.text(i, 12, "solving —\nlands shortly", ha="center", fontsize=9,
                    color=MUTED, style="italic")
            continue
        v, g = r["mw"]
        ax.bar(i, v, width=0.55, color=BLUE, zorder=3, label="village solar" if i == 0 else None)
        ax.bar(i, g, bottom=v, width=0.55, color=BLUE_LIGHT, zorder=3,
               label="grid (utility) solar" if i == 0 else None)
        total = v + g
        pct100 = total / 100_000 * 100
        kwhh = total * 1000 / HOUSEHOLDS
        sub = f"{pct100:.2f}% of 100 GW · {kwhh:.2f} kW/household"
        ax.text(i, total + 34, f"{total:,.0f} MW", ha="center", va="bottom",
                fontsize=13, color=INK, fontweight="bold")
        ax.text(i, total + 28, sub, ha="center", va="top", fontsize=8, color=INK2)
        # split labels only when both components are visible
        if v > 1 and g > 1:
            ax.text(i + 0.31, v / 2, f"village {v:,.0f}", ha="left", fontsize=8.5, color=INK2)
            ax.text(i + 0.31, v + g / 2, f"grid {g:,.0f}", ha="left", fontsize=8.5, color=INK2)

    ax.set_xticks(list(xs))
    ax.set_xticklabels([r["label"] for r in rows], fontsize=9.5, color=INK)
    ax.set_ylabel("solar capacity (MW)", fontsize=10, color=INK2)
    ax.set_ylim(0, 430)
    ax.yaxis.grid(True, color=GRID_LN, lw=0.8, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(BASE)
    ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=9)

    ax.set_title("Solar buildout on Timor under three planning regimes",
                 fontsize=13, color=INK, loc="left", pad=12)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}")
    for r in rows:
        mw = r["mw"]
        print(f"  {r['label'].splitlines()[0]:36s} " +
              (f"village {mw[0]:8.2f} + grid {mw[1]:8.2f} MW" if mw else "pending"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
