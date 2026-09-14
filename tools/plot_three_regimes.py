#!/usr/bin/env python3
"""Three regimes on one page — the partner summary figure.

Four small-multiple panels (system cost, system CO2, village solar, villages
connected), each with the same three bars: islanded, coordinated with no carbon
constraint, coordinated under a carbon cap + RE floor. Every number is read from
the committed result CSVs of the CONSISTENT full-8-week trio (same model, same
dataset, all three legs exact LPs — the coordinated legs are the 2026-09-14
fix-and-verify runs), so the panels are comparable within and across.

The story the four panels tell together: the wires alone save $24.0 M/yr by
substituting existing coal for village solar (+455 kt CO2, solar 361 -> 21 MW);
the same wires under a carbon cap keep the solar programme intact and still
save $2.8 M/yr. The constraint, not the technology, decides the buildout.

    python3 tools/plot_three_regimes.py            # -> results/figures/

Small multiples per the dataviz method: four measures of different units never
share an axis. One hue (the same three plans in every panel); direct labels;
no legend needed (x tick labels carry identity).

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
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID_LN = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"

RESULTS = os.path.join(REPO, "results")
LEGS = [  # (results dir, x label)
    ("village_timor__marketfix_2030_reference__ucrelax", "islanded"),
    ("gridvillage_timor__marketfix_2030_reference__fixverify", "wires,\nno carbon cap"),
    ("gridvillage_timor__marketfix_2030_clean__fixverify", "wires +\ncarbon cap"),
]
NA = dict(encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def leg_metrics(run_dir):
    d = os.path.join(RESULTS, run_dir)
    cost = float(_num(pd.read_csv(os.path.join(d, "cost_results.csv"), **NA)
                      .iloc[0:1].Total_Costs).iloc[0])
    co2 = float(_num(pd.read_csv(os.path.join(d, "clean_energy_results.csv"), **NA)
                     .iloc[0:1].CO2_Emissions).iloc[0]) / 1000.0  # kt
    conn = pd.read_csv(os.path.join(d, "site_connection_results.csv"), **NA)
    n_conn = int((_num(conn.Connected) > 0.5).sum())
    gen = pd.read_csv(os.path.join(d, "site_generator_results.csv"), **NA)
    solar = float(_num(gen[gen.technology.astype(str) == "solar"].Total_MW).sum())
    return cost, co2, solar, n_conn


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(RESULTS, "figures",
                                                  "three_regimes.png"))
    args = ap.parse_args(argv)

    rows = [leg_metrics(d) for d, _ in LEGS]
    labels = [l for _, l in LEGS]
    panels = [
        ("system cost", "$M/yr", [r[0] for r in rows], "{:,.1f}"),
        ("system CO₂", "kt/yr", [r[1] for r in rows], "{:,.0f}"),
        ("village solar", "MW", [r[2] for r in rows], "{:,.0f}"),
        ("villages connected", "of 780", [r[3] for r in rows], "{:,.0f}"),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(12.8, 4.4), dpi=200)
    fig.subplots_adjust(left=0.05, right=0.985, top=0.80, bottom=0.20,
                        wspace=0.42)
    fig.patch.set_facecolor(SURFACE)

    for ax, (title, unit, vals, fmt) in zip(axes, panels):
        ax.set_facecolor(SURFACE)
        ax.bar(range(3), vals, width=0.58, color=BLUE, zorder=3)
        top = max(vals)
        ax.set_ylim(0, top * 1.30)
        # islanded level as the reference line the other bars are read against
        ax.axhline(vals[0], color=BASE, lw=1.0, ls=(0, (4, 3)), zorder=2)
        for i, v in enumerate(vals):
            ax.text(i, v + top * 0.045, fmt.format(v), ha="center", va="bottom",
                    fontsize=10.5, fontweight="bold", color=INK)
        ax.set_title(f"{title}  ({unit})", fontsize=10.5, color=INK, pad=8)
        ax.set_xticks(range(3))
        ax.set_xticklabels(labels, fontsize=8, color=INK2)
        ax.set_yticks([])
        for s_ in ("top", "right", "left"):
            ax.spines[s_].set_visible(False)
        ax.spines["bottom"].set_color(BASE)
        ax.tick_params(colors=MUTED, length=0)

    cost, co2 = [r[0] for r in rows], [r[1] for r in rows]
    fig.suptitle("Wires without a carbon cap dismantle the solar programme; "
                 "wires with one complete it",
                 fontsize=13.5, color=INK, x=0.05, y=0.965, ha="left")
    fig.text(0.05, 0.885,
             f"coordination saves \\${cost[0]-cost[1]:.1f} M/yr unconstrained — by burning "
             f"{co2[1]-co2[0]:,.0f} kt/yr more coal · under a carbon cap it saves "
             f"\\${cost[0]-cost[2]:.1f} M/yr with the solar fleet intact",
             fontsize=10, color=INK2)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}")
    for (d, lab), r in zip(LEGS, rows):
        print(f"  {lab.replace(chr(10), ' '):28s} cost {r[0]:9.5f}  CO2 {r[1]:7.1f} kt  "
              f"solar {r[2]:7.2f} MW  connected {r[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
