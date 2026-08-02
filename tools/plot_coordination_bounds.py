#!/usr/bin/env python3
"""Coordination value as proven intervals — the preliminary-results figure.

Draws the coordination value (islanded cost minus coordinated cost) for each
case as the interval the solves have PROVEN, not as a point estimate. Bounds
only ever tighten, so the figure is safe to show before the runs finish and is
regenerated, not redrawn, when they land:

    python3 tools/plot_coordination_bounds.py            # -> results/figures/
    python3 tools/plot_coordination_bounds.py --out fig.png

Anchor provenance (all $M/yr; RUN_LOG.md carries the full derivations):

  timor (village <-> village, zero-load grid) — FINAL, no further compute needed
    OFF  = 69.134350   exact: pure LP (no Commit=1 units, no binaries in `village`)
    ON  >= 68.967491   root LP bound (Gurobi log, A1a gridvillage)
    ON  <= 69.134350   dominance: all-connections-off is feasible for ON
    => coordination in [0, 0.166859]

  timor__marketfix (village <-> grid, DMO coal, corrected RE costs) — PRELIMINARY
    OFF <= 96.886109   marketfixnf `village` incumbent; valid for marketfix because
                       nf is a strict restriction (only fossil-candidate headroom
                       differs, so every nf-feasible point is fix-feasible)
    OFF >= 96.812863   marketfix `village` solver bound
    ON  >= 59.274058   barrier DUAL at rel gap 1e-05 (jobs/mf_marketfix_gridvillage)
                       — a dual value is a valid lower bound on the LP relaxation,
                       which lower-bounds the MILP
    ON  <= OFF upper   dominance
    => coordination in [0, 96.886109 - 59.274058] = [0, 37.612]

When `results/gridvillage_timor__marketfix_2030_reference/cost_results.csv`
exists (the run has landed), its incumbent tightens the LOWER bound to
OFF_lower - incumbent, and the solver log's final `Best bound` replaces the
barrier dual in the upper bound. This script reads the results dir when present
and falls back to the anchors above otherwise — so re-running it after the
solves IS the verification step.

Caveats printed on the figure (do not strip them for a deck):
- `timor__marketfix` is a sensitivity dataset, not a corrected one (its own
  scenario file's wording); the grid demand series is derived, not measured.
- The ON lower bound is an LP relaxation; the integrality gap on this
  formulation has measured ~55% elsewhere, so the true upper bound on the
  coordination value is likely far below the relaxation-based one shown.
- Per-village trade allocation is degenerate at import = export = 0; interval
  totals are unaffected.

Chart conventions follow the dataviz method: one axis, intervals as thin bars
from a zero baseline, certainty as two steps of a single blue ramp (solid =
proven, light = unresolved), text in ink tokens rather than series colour.

Requires matplotlib (not part of the core pip set). Solver-free.
"""
import argparse
import datetime as _dt
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- palette (reference dataviz palette, light mode) ----
BLUE = "#2a78d6"       # series slot 1: the proven/final interval
BLUE_LIGHT = "#86b6ef" # ramp step 250: the unresolved breadth
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"

# ---- anchors ($M/yr) — provenance in the module docstring / RUN_LOG.md ----
TIMOR = dict(off=69.134350, on_lb=68.967491)  # final (exact LP + dominance)
# Market case, ucrelax treatment (relax_uc + exact_connect, DMO coal, capacity-
# accounting fix in): OFF is an exact LP; ON bracketed by its root relaxation and
# the improving incumbent from the B&B log (H-line at 4234 s, both variants found
# the identical plan). Superseded anchors from the free-battery era removed.
MKT = dict(off_ub=101.717594, off_lb=101.717594, on_lb=59.905910)
MKT_ON_INC = 84.154500  # log incumbent; auto-replaced once cost_results.csv lands


def _live_market_bounds():
    """Tighten the market-case interval from landed results, if any."""
    import pandas as pd
    d = os.path.join(REPO, "results", "gridvillage_timor__marketfix_2030_reference")
    cost = os.path.join(d, "cost_results.csv")
    inc = None
    if os.path.exists(cost):
        inc = float(pd.read_csv(cost).Total_Costs[0])
    log = os.path.join(REPO, "jobs", "mf_marketfix_gridvillage", "solve.log")
    bound = None
    if os.path.exists(log):
        for line in open(log, errors="ignore"):
            if line.startswith("Best objective") and "best bound" in line:
                bound = float(line.split("best bound")[1].split(",")[0].strip()) / 1e6
    return inc, bound


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures",
                                                  "coordination_bounds.png"))
    args = ap.parse_args(argv)

    # timor: final interval
    t_hi = TIMOR["off"] - TIMOR["on_lb"]                     # 0.166859
    # market: preliminary interval, tightened by landed results when available
    inc, bound = _live_market_bounds()
    landed = inc is not None
    if inc is None:
        inc = MKT_ON_INC
    m_lo = max(0.0, MKT["off_lb"] - inc)
    on_lb = bound if bound is not None else MKT["on_lb"]
    m_hi = MKT["off_ub"] - on_lb
    status = "landed" if landed else "B&B in progress — tightening"

    fig, ax = plt.subplots(figsize=(9.6, 4.6), dpi=200)
    fig.subplots_adjust(left=0.20, right=0.97, top=0.86, bottom=0.30)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    bar_h = 0.26
    # -- village <-> grid (top row, y=1) --
    ax.barh(1, m_hi - m_lo, left=m_lo, height=bar_h, color=BLUE_LIGHT, zorder=3)
    ax.plot([m_hi], [1], marker="|", ms=22, mew=2.4, color=BLUE, zorder=4)
    if m_lo > 0:
        ax.plot([m_lo], [1], marker="|", ms=22, mew=2.4, color=BLUE, zorder=4)
    # -- village <-> village (bottom row, y=0) --
    ax.barh(0, t_hi, left=0, height=bar_h, color=BLUE, zorder=3)

    # direct labels (ink tokens, never series colour)
    ax.annotate(f"≤ ${m_hi:.1f} M/yr — upper bound (root LP; {status})",
                xy=(m_hi, 1 + bar_h / 2), xytext=(m_hi - 0.8, 1 + 0.42),
                ha="right", va="bottom", fontsize=9.5, color=INK,
                arrowprops=dict(arrowstyle="-", lw=0.8, color=MUTED,
                                shrinkA=2, shrinkB=2))
    if m_lo > 0:
        ax.annotate(f"≥ ${m_lo:.1f} M/yr proven",
                    xy=(m_lo, 1), xytext=(m_lo + 0.4, 1 - 0.36),
                    ha="left", va="top", fontsize=9.5, color=INK)
    ax.annotate(f"≤ ${t_hi:.2f} M/yr — final\n"
                "(exact LP + dominance; no further compute needed)",
                xy=(t_hi, 0), xytext=(3.2, 0.02),
                ha="left", va="center", fontsize=9.5, color=INK,
                arrowprops=dict(arrowstyle="-", lw=0.8, color=MUTED,
                                shrinkA=2, shrinkB=1))

    # mechanism notes (secondary ink)
    ax.text(0.0, 1 - 0.52, "village and grid load anti-correlated (r = −0.81): "
            "a genuine counterparty", fontsize=8.5, color=INK_2, va="top")
    ax.text(0.0, 0 - 0.52, "village peaks are simultaneous (diversity factor 1.000): "
            "nothing to trade with each other", fontsize=8.5, color=INK_2, va="top")

    # axes / chrome
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["village ↔ village\ntimor (zero-load grid)",
                        "village ↔ grid\ntimor__marketfix (DMO coal)"],
                       fontsize=10, color=INK)
    ax.set_xlim(-0.4, 46)
    ax.set_ylim(-0.85, 1.85)
    ax.set_xticks([0, 10, 20, 30, 40])
    ax.set_xlabel("coordination value  (islanded − coordinated,  $M/yr)",
                  fontsize=10, color=INK_2)
    ax.xaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.tick_params(colors=MUTED, labelsize=9)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.axvline(0, color=BASE, lw=1, zorder=2)

    ax.legend(handles=[Patch(color=BLUE, label="proven interval (final)"),
                       Patch(color=BLUE_LIGHT, label="unresolved breadth (preliminary)")],
              loc="lower right", frameon=False, fontsize=8.5)

    ax.set_title("Coordination value: what is proven so far",
                 fontsize=13, color=INK, loc="left", pad=14)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    fig.text(0.20, 0.115,
             f"as of {stamp} · ucrelax: UC relaxed in BOTH legs (~0.8% ops optimism, cancels in the delta); wire decisions exact\n"
             "sensitivity dataset (derived grid demand, corrected RE costs, DMO coal) · upper bound is the LP relaxation —\n"
             "true value likely well below it · per-village trade allocation degenerate at 0/0 prices (totals unaffected)",
             fontsize=7, color=MUTED, va="top", linespacing=1.5)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}")
    print(f"  timor        : coordination in [0, {t_hi:.6f}] $M/yr (final)")
    print(f"  marketfix    : coordination in [{m_lo:.3f}, {m_hi:.3f}] $M/yr ({status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
