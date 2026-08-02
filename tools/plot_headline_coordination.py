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
     OFF exact LP 101.71759 minus ON incumbent 84.15450 = $17.56 M/yr at an
     achieved gap of 28.8144% (jobs/ucr_marketfix_gridvillage/solve.log).
     Mechanism warning carried on the figure: the cost-optimal plan connects
     746/780 villages to EXISTING coal headroom and dismantles ~90% of the
     village solar build — system CO2 rises ~46%.

  3. village <-> grid, carbon-neutral (`timor__marketfix2w`, `clean`,
     CO2_limit 656,500 t, RE_limit 0.48). Reads
     results/gridvillage_timor__marketfix2w_2030_clean/cost_results.csv when
     the run has landed (value = 101.72300 - Total_Costs, gap from the final
     `Best objective` line of jobs/w2c_gridvillage/solve.log). While the run
     is still solving the row renders muted as "solving — floor $X.X M/yr so
     far", the floor taken from the latest incumbent in the same log. Either
     way the row carries the aggregation caveat: 2-week reduced model
     (OFF 2w LP = 101.72300 vs 101.71759 full, 0.005%); fix-and-verify on
     the full 8-week dataset pending.

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
import re
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
OFF_REF = 101.717594   # marketfix `village` ucrelax, `Optimal objective` (exact LP)
ON_REF_INC = 84.154499  # marketfix gridvillage ucrelax incumbent at the 8 h cap
REF_GAP_PCT = 28.8144  # achieved, from the final Best objective line
OFF_CLEAN_2W = 101.72300  # marketfix2w `village` clean, exact LP

RESULTS = os.path.join(REPO, "results")
REF_OFF_CSV = os.path.join(
    RESULTS, "village_timor__marketfix_2030_reference__ucrelax", "cost_results.csv")
REF_ON_CSV = os.path.join(
    RESULTS, "gridvillage_timor__marketfix_2030_reference__ucrelax", "cost_results.csv")
REF_LOG = os.path.join(REPO, "jobs", "ucr_marketfix_gridvillage", "solve.log")
CLEAN_OFF_CSV = os.path.join(
    RESULTS, "village_timor__marketfix2w_2030_clean", "cost_results.csv")
CLEAN_ON_CSV = os.path.join(
    RESULTS, "gridvillage_timor__marketfix2w_2030_clean", "cost_results.csv")
CLEAN_LOG = os.path.join(REPO, "jobs", "w2c_gridvillage", "solve.log")

_SCI = re.compile(r"\d\.\d+e\+\d+")


def _total_costs(path, fallback):
    """cost_results.csv::Total_Costs ($M/yr), or the documented anchor."""
    if os.path.exists(path):
        return float(pd.read_csv(path).Total_Costs[0])
    return fallback


def _final_gap_pct(log_path, fallback=None):
    """Achieved gap from the last `Best objective ..., gap X%` line, if any."""
    gap = fallback
    if os.path.exists(log_path):
        for line in open(log_path, errors="ignore"):
            if line.startswith("Best objective") and "gap" in line:
                gap = float(line.split("gap")[1].strip().rstrip("%\n"))
    return gap


def _latest_incumbent(log_path):
    """Best incumbent ($M) so far from a running Gurobi B&B log, or None."""
    inc = None
    if os.path.exists(log_path):
        for line in open(log_path, errors="ignore"):
            if line.startswith(("H", "*")):
                m = _SCI.search(line)
                if m:
                    inc = float(m.group()) / 1e6
    return inc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures",
                                                  "headline_coordination.png"))
    args = ap.parse_args(argv)

    # row 2 — reference pair
    ref_val = _total_costs(REF_OFF_CSV, OFF_REF) - _total_costs(REF_ON_CSV, ON_REF_INC)
    ref_gap = _final_gap_pct(REF_LOG, REF_GAP_PCT)

    # row 3 — carbon-neutral pair (may still be solving)
    off_clean = _total_costs(CLEAN_OFF_CSV, OFF_CLEAN_2W)
    clean_landed = os.path.exists(CLEAN_ON_CSV)
    if clean_landed:
        clean_val = off_clean - _total_costs(CLEAN_ON_CSV, None)
        clean_gap = _final_gap_pct(CLEAN_LOG)
    else:
        inc = _latest_incumbent(CLEAN_LOG)
        clean_val = (off_clean - inc) if inc is not None else 0.0
        clean_gap = None

    fig, ax = plt.subplots(figsize=(10.4, 5.2), dpi=200)
    fig.subplots_adjust(left=0.215, right=0.975, top=0.87, bottom=0.14)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    Y1, Y2, Y3 = 2.0, 1.0, 0.0  # village<->village, reference, carbon-neutral

    # -- row 1: village <-> village — a zero, final --
    ax.plot([0], [Y1], "o", ms=10, color=BLUE, zorder=4)
    ax.text(0.45, Y1 + 0.02, "$0/yr", fontsize=15, fontweight="bold",
            color=INK, va="center")
    ax.text(0.0, Y1 - 0.30, "final (exact LP + dominance)",
            fontsize=8.5, color=INK_2, va="top")
    ax.text(0.0, Y1 - 0.47, "structural — diversity factor 1.000, nothing to trade",
            fontsize=8.5, color=INK_2, va="top")

    # -- row 2: village <-> grid, reference --
    ax.hlines(Y2, 0, ref_val, color=BLUE, lw=2, zorder=3)
    ax.plot([ref_val], [Y2], "o", ms=10, color=BLUE, zorder=4)
    ax.text(ref_val + 0.45, Y2 + 0.02, f"${ref_val:.2f} M/yr",
            fontsize=15, fontweight="bold", color=INK, va="center")
    ax.text(0.0, Y2 - 0.30,
            f"from the best plan found; achieved solver gap {ref_gap:.2f}% — "
            "conservative, can only understate",
            fontsize=8.5, color=INK_2, va="top")
    ax.text(0.0, Y2 - 0.47,
            "cost-optimal plan substitutes existing coal for village solar: "
            "system CO₂ +46%",
            fontsize=8.5, color=INK_2, va="top")

    # -- row 3: village <-> grid, carbon-neutral --
    if clean_landed:
        ax.hlines(Y3, 0, clean_val, color=BLUE, lw=2, zorder=3)
        ax.plot([clean_val], [Y3], "o", ms=10, color=BLUE, zorder=4)
        ax.text(clean_val + 0.45, Y3 + 0.02, f"${clean_val:.2f} M/yr",
                fontsize=15, fontweight="bold", color=INK, va="center")
        gap_txt = (f"achieved solver gap {clean_gap:.2f}% — conservative, "
                   "can only understate" if clean_gap is not None
                   else "gap unavailable — solver log missing a final Best objective line")
        ax.text(0.0, Y3 - 0.30, f"from the best plan found; {gap_txt}",
                fontsize=8.5, color=INK_2, va="top")
    else:
        ax.hlines(Y3, 0, clean_val, color=MUTED, lw=1.4,
                  linestyle=(0, (4, 3)), zorder=3)
        ax.plot([clean_val], [Y3], "o", ms=10, mfc=SURFACE, mec=MUTED,
                mew=1.6, zorder=4)
        ax.text(clean_val + 0.45, Y3 + 0.02,
                f"solving — floor ${clean_val:.1f} M/yr so far",
                fontsize=12, color=MUTED, va="center")
        ax.text(0.0, Y3 - 0.30,
                "incumbent still improving; the floor can only rise",
                fontsize=8.5, color=MUTED, va="top")
    ax.text(0.0, Y3 - 0.47,
            "2-week reduced model (OFF leg 0.005% off the 8-week anchor); "
            "fix-and-verify on the full dataset pending",
            fontsize=8.5, color=MUTED if not clean_landed else INK_2, va="top")

    # axes / chrome
    ax.set_yticks([Y3, Y2, Y1])
    ax.set_yticklabels(["village ↔ grid\ncarbon-neutral (2-week)",
                        "village ↔ grid\nreference (full model)",
                        "village ↔ village\ntimor (zero-load grid)"],
                       fontsize=10, color=INK)
    ax.set_xlim(-0.4, 22.5)
    ax.set_ylim(-0.75, 2.55)
    ax.set_xticks([0, 5, 10, 15, 20])
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
    print(f"  reference         : ${ref_val:.5f} M/yr at achieved gap {ref_gap:.4f}%")
    if clean_landed:
        gtxt = f"{clean_gap:.4f}%" if clean_gap is not None else "n/a"
        print(f"  carbon-neutral    : ${clean_val:.5f} M/yr at achieved gap {gtxt} (landed)")
    else:
        print(f"  carbon-neutral    : solving — floor ${clean_val:.5f} M/yr so far")
    return 0


if __name__ == "__main__":
    sys.exit(main())
