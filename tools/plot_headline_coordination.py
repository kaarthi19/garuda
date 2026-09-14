#!/usr/bin/env python3
"""Headline coordination values — the lead figure, one number per pairing.

Replaces the bounds chart (tools/plot_coordination_bounds.py) as the lead
figure under the reporting convention recorded in RUN_LOG.md (2026-08-02):
headline coordination values are a SINGLE number computed from the best
feasible plan (OFF islanded cost minus ON incumbent), annotated with the
ACHIEVED solver gap — never the permitted `mipgap`. Because the ON incumbent
only ever improves, each number is conservative by construction: it can only
understate the true value. Interval presentation moves to the appendix.

    python3 tools/plot_headline_coordination.py          # -> results/figures/
    python3 tools/plot_headline_coordination.py --out fig.png

Three rows, all $M/yr (provenance in RUN_LOG.md):

  1. village <-> village, `timor` (zero-load grid) — FINAL
     $0/yr. Fixing all 780 `vVIL_CONNECT` to 0 reproduces the islanded exact
     LP and is feasible for the ON problem (dominance), and the ON root LP
     bound closes the bracket to [0, 0.167]. Structural: diversity factor
     1.000 — every village peaks in the same hours, nothing to trade.

  2. village <-> grid, reference (`timor__marketfix`, full 8-week model)
     OFF exact LP 101.71759 minus ON fix-and-verify exact LP 77.75873
     (results/gridvillage_timor__marketfix_2030_reference__fixverify: the
     2-week winner's 733-village pattern priced at full resolution) =
     $23.96 M/yr. Both sides are pure LPs solved to optimality — no solver
     gap; the number is exact for this concrete plan and a FLOOR on the true
     value (a better pattern could only raise it). Mechanism warning carried
     on the figure: the plan runs on existing coal headroom, village solar
     collapses to 21 MW, system CO2 rises ~68%.

  3. village <-> grid, carbon-neutral (same dataset, `clean`, CO2_limit
     656,500 t, RE_limit 0.48, policy_scope system). Same construction:
     OFF 101.71759 (the islanded plan meets the cap by construction) minus
     ON fix-and-verify exact LP 98.87223
     (results/gridvillage_timor__marketfix_2030_clean__fixverify: the
     450-village pattern; CO2 = 656,500.000 t and RE share = 0.480000 bind
     exactly at full resolution) = $2.85 M/yr, exact for this plan. The
     former 2-week aggregation caveat is retired — both headline rows are
     now full-8-week numbers.

Chart conventions follow the dataviz method: horizontal lollipop per row
(this is a set of headline numbers, not intervals — no bars), one axis, big
values as direct labels in ink tokens (text never wears series colour), the
pending row in muted ink, caveats in the caption block. Single series hue,
so no legend.

Requires matplotlib + pandas (not part of the core pip set). Solver-free.
"""
import argparse
import datetime as _dt
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- palette (reference dataviz palette, light mode) ----
BLUE = "#2a78d6"       # series slot 1: measured headline values
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"

# ---- anchors ($M/yr) — provenance in the module docstring / RUN_LOG.md ----
OFF_REF = 101.717594    # marketfix `village` ucrelax, `Optimal objective` (exact LP)
ON_REF_FV = 77.758726   # fix-and-verify exact LP, 733-village pattern (2026-09-14)
ON_CLEAN_FV = 98.872226  # fix-and-verify exact LP, 450-village pattern (2026-09-14)

RESULTS = os.path.join(REPO, "results")
REF_OFF_CSV = os.path.join(
    RESULTS, "village_timor__marketfix_2030_reference__ucrelax", "cost_results.csv")
REF_ON_CSV = os.path.join(
    RESULTS, "gridvillage_timor__marketfix_2030_reference__fixverify", "cost_results.csv")
CLEAN_ON_CSV = os.path.join(
    RESULTS, "gridvillage_timor__marketfix_2030_clean__fixverify", "cost_results.csv")


def _total_costs(path, fallback):
    """cost_results.csv::Total_Costs ($M/yr), or the documented anchor."""
    if os.path.exists(path):
        return float(pd.read_csv(path).Total_Costs[0])
    return fallback


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures",
                                                  "headline_coordination.png"))
    args = ap.parse_args(argv)

    # rows 2 and 3 — the same OFF (the islanded plan meets the carbon cap by
    # construction) minus each fix-and-verify exact LP. No solver gap anywhere.
    off = _total_costs(REF_OFF_CSV, OFF_REF)
    ref_val = off - _total_costs(REF_ON_CSV, ON_REF_FV)
    clean_val = off - _total_costs(CLEAN_ON_CSV, ON_CLEAN_FV)

    fig, ax = plt.subplots(figsize=(10.4, 5.2), dpi=200)
    fig.subplots_adjust(left=0.215, right=0.975, top=0.87, bottom=0.14)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    Y1, Y2, Y3 = 2.0, 1.0, 0.0  # village<->village, reference, carbon-neutral

    # -- row 1: village <-> village — a zero, final --
    ax.plot([0], [Y1], "o", ms=10, color=BLUE, zorder=4)
    ax.text(0.45, Y1 + 0.02, "$0/yr", fontsize=15, fontweight="bold",
            color=INK, va="center")
    ax.text(0.0, Y1 - 0.32, "every village peaks in the same hours — nothing to trade",
            fontsize=9, color=INK_2, va="top")

    # -- row 2: village <-> grid, reference --
    ax.hlines(Y2, 0, ref_val, color=BLUE, lw=2, zorder=3)
    ax.plot([ref_val], [Y2], "o", ms=10, color=BLUE, zorder=4)
    ax.text(ref_val + 0.45, Y2 + 0.02, f"${ref_val:.2f} M/yr",
            fontsize=15, fontweight="bold", color=INK, va="center")
    ax.text(0.0, Y2 - 0.32,
            "the cost-optimal plan runs on existing coal — system CO₂ rises",
            fontsize=9, color=INK_2, va="top")

    # -- row 3: village <-> grid, carbon-neutral --
    ax.hlines(Y3, 0, clean_val, color=BLUE, lw=2, zorder=3)
    ax.plot([clean_val], [Y3], "o", ms=10, color=BLUE, zorder=4)
    ax.text(clean_val + 0.45, Y3 + 0.02, f"${clean_val:.2f} M/yr",
            fontsize=15, fontweight="bold", color=INK, va="center")
    ax.text(0.0, Y3 - 0.32,
            "the solar programme stays intact — CO₂ held at the islanded level",
            fontsize=9, color=INK_2, va="top")

    # axes / chrome
    ax.set_yticks([Y3, Y2, Y1])
    ax.set_yticklabels(["village ↔ grid\ncarbon-neutral",
                        "village ↔ grid\nunconstrained",
                        "village ↔ village"],
                       fontsize=10, color=INK)
    ax.set_xlim(-0.5, 32.0)
    ax.set_ylim(-0.55, 2.50)
    ax.set_xticks([0, 5, 10, 15, 20, 25])
    ax.set_xlabel("coordination value  (islanded − best coordinated plan found,  $M/yr)",
                  fontsize=10, color=INK_2)
    ax.xaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.tick_params(colors=MUTED, labelsize=9)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.axvline(0, color=BASE, lw=1, zorder=2)

    ax.set_title("What coordination is worth on Timor — one number per pairing",
                 fontsize=13, color=INK, loc="left", pad=14)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}")
    print(f"  village<->village : $0/yr (final)")
    print(f"  reference         : ${ref_val:.5f} M/yr (fix-and-verify exact LP — no solver gap)")
    print(f"  carbon-neutral    : ${clean_val:.5f} M/yr (fix-and-verify exact LP — no solver gap)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
