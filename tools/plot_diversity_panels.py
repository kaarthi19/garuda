#!/usr/bin/env python3
"""Two diversity factors — villages cannot trade with each other, but can with the grid (F11).

Panel (a) — the within-village null. Histogram of all C(780,2) = 303,810
pairwise Pearson correlations between peak-normalised village load shapes
(`data_indonesia/2030/timor/village_demand.csv`), drawn on the full [-1, +1]
axis so the spike at +1 is the message: 98.2% of pairs correlate >= 0.999, the
sum of the 780 individual peaks equals the coincident system peak (128.24 MW),
and the diversity factor is 1.0000000 — only 2 distinct peak hours exist across
780 villages. Solar CF is even more degenerate: every pairwise correlation is
1.000000 (the 516 "distinct" profiles differ in amplitude only), so it is
stated as an annotation, not drawn as a histogram.

Panel (b) — the village-grid contrast. Village aggregate load overlaid on the
grid series `demand_z1` (`data_indonesia/2030/timor__marketfix/demand.csv`) for
one representative week. Correlation over all 1,344 hours is -0.8081, the
global peaks fall 283 hours apart (village hour 690, grid hour 407), and
combining the two systems cuts the coincident peak from 252.34 to 171.05 MW —
an 81.29 MW saving, diversity factor 1.475.

Together the panels convert the coordination null into a structural statement:
village-to-village coordination could not have paid on this data (arithmetic,
not economics). The village-grid anti-correlation, by contrast, is INHERITED
from the netting construction (the grid series is provincial load minus village
load; the two are +0.32 correlated before the subtraction), so panel (b) shows a
modelling construction, not measured complementarity — see plot_load_timing.py
for the two-construction bracket.

    python3 tools/plot_diversity_panels.py            # -> results/figures/
    python3 tools/plot_diversity_panels.py --out fig.png

Caveats printed on the figure (do not strip them for a deck):
- Panel (a) is a property of how the archetype profiles were synthesised, not
  an empirical finding about Timorese villages: 621 of 780 sit on a single
  demand archetype and GHI spans only 4.908-5.952 kWh/m2/day.
- 1,344 hours from 8 representative weeks cannot express weather-driven
  decorrelation even in principle; real spatial decorrelation needs ERA5.
- Panel (b)'s grid series is derived, not measured (build_grid_demand
  --share 0.42, NTT zone-2 net of village load) — the anti-correlation is
  inherited from that construction.
- Peak-normalisation is stated on panel (a)'s axis.

All numbers are recomputed from the input CSVs at run time; nothing is read
from results/, so the figure needs no solve. Requires matplotlib + numpy +
pandas (not part of the core pip set). Solver-free.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- palette (reference dataviz palette, light mode) ----
BLUE = "#2a78d6"       # series slot 1: village side
ORANGE = "#eb6834"     # series slot 2: grid side (two series need distinct hues)
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"

WEEK = 4  # 0-based representative week for panel (b): contains the village annual peak


def _read(path):
    """Dataset CSV read — NA config preserves the literal fuel name 'None'."""
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False,
                       na_values=[""])


def _load(repo):
    vd = _read(os.path.join(repo, "data_indonesia/2030/timor/village_demand.csv"))
    cols = [c for c in vd.columns if c.startswith("demand_village")]
    load = vd[cols].to_numpy(float)                      # 1344 h x 780 villages
    grid_csv = os.path.join(repo, "data_indonesia/2030/timor__marketfix/demand.csv")
    if not os.path.exists(grid_csv):
        # marketfix only re-costs generators; its demand series is identical to
        # timor__market, which rebuilds locally in seconds (build_grid_demand)
        grid_csv = os.path.join(repo, "data_indonesia/2030/timor__market/demand.csv")
    grid = _read(grid_csv)["demand_z1"].to_numpy(float)  # 1344 h, derived series

    # Solar CF profiles: variability columns are POSITIONAL — column 1 dropped
    # unconditionally, profile column g belongs to R_ID g (input_data.jl:72).
    vg = _read(os.path.join(repo, "data_indonesia/2030/timor/village_generators.csv"))
    vv = _read(os.path.join(
        repo, "data_indonesia/2030/timor/village_generators_variability.csv"))
    prof = vv.iloc[:, 1:].to_numpy(float)
    rid = vg["R_ID"].to_numpy(int)
    is_solar = vg["technology"].str.contains("solar", case=False).to_numpy()
    solar = prof[:, rid[is_solar] - 1]
    return load, grid, solar


def _pairwise_upper(mat):
    """Upper-triangle pairwise correlations between the COLUMNS of mat."""
    c = np.corrcoef(mat.T)
    return c[np.triu_indices(mat.shape[1], k=1)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures",
                                                  "diversity_panels.png"))
    args = ap.parse_args(argv)

    load, grid, solar = _load(REPO)
    nv = load.shape[1]

    # ---- panel (a) arithmetic ----
    peaks = load.max(axis=0)
    agg = load.sum(axis=1)
    coincident = agg.max()
    df_within = peaks.sum() / coincident                 # 1.0000000
    peak_hours = np.unique(load.argmax(axis=0))          # 2 distinct hours
    pc = _pairwise_upper(load / peaks)                   # peak-normalised shapes
    share_999 = (pc >= 0.999).mean()
    tail = pc[pc < 0.999]                                # 5,411 fishing-vs-rest pairs
    sc = _pairwise_upper(solar)
    solar_degenerate = sc.min() > 0.999999               # one shape, 6+ d.p.

    # ---- panel (b) arithmetic ----
    r = np.corrcoef(agg, grid)[0, 1]                     # -0.8081
    v_pk_h, g_pk_h = int(agg.argmax()), int(grid.argmax())
    sum_pk = coincident + grid.max()                     # 252.34
    comb_pk = (agg + grid).max()                         # 171.05
    saving = sum_pk - comb_pk                            # 81.29
    df_grid = sum_pk / comb_pk                           # 1.475
    s = slice(WEEK * 168, (WEEK + 1) * 168)

    fig, (axa, axb) = plt.subplots(1, 2, figsize=(12.8, 5.8), dpi=200)
    fig.subplots_adjust(left=0.065, right=0.975, top=0.825, bottom=0.265,
                        wspace=0.24)
    fig.patch.set_facecolor(SURFACE)

    # ---------------- panel (a): within villages ----------------
    axa.set_facecolor(SURFACE)
    axa.hist(pc, bins=np.arange(-1.0, 1.021, 0.02), color=BLUE, zorder=3)
    axa.set_xlim(-1.05, 1.05)
    axa.set_xticks([-1, -0.5, 0, 0.5, 1])
    axa.set_xlabel("pairwise correlation of peak-normalised load shapes\n"
                   f"(all C(780,2) = {pc.size:,} village pairs)",
                   fontsize=9.5, color=INK_2)
    axa.set_ylabel("village pairs", fontsize=9.5, color=INK_2)
    axa.yaxis.set_major_formatter(FuncFormatter(
        lambda v, _: f"{v/1000:.0f}k" if v else "0"))
    axa.annotate(f"{share_999:.1%} of pairs ≥ 0.999; mean {pc.mean():.4f}\n"
                 "(every non-fishing pair ≥ 0.9999999)",
                 xy=(0.985, pc.size * 0.70), xytext=(0.60, pc.size * 0.74),
                 ha="right", va="center", fontsize=9, color=INK,
                 arrowprops=dict(arrowstyle="-", lw=0.8, color=MUTED,
                                 shrinkA=4, shrinkB=2))
    axa.annotate(f"the other {1 - share_999:.1%}: {tail.size:,} pairs vs the "
                 f"7 fishing-archetype villages, r = {tail.mean():.3f}",
                 xy=(0.815, pc.size * 0.028), xytext=(0.70, pc.size * 0.075),
                 ha="right", va="bottom", fontsize=8.5, color=INK_2,
                 arrowprops=dict(arrowstyle="-", lw=0.8, color=MUTED,
                                 shrinkA=2, shrinkB=2))
    axa.text(-0.96, pc.size * 0.545,
             f"diversity factor  {df_within:.7f}\n"
             f"Σ of {nv} village peaks = coincident peak\n"
             f"= {coincident:.2f} MW — only {peak_hours.size} distinct "
             "peak hours\nacross 780 villages: nothing to trade",
             fontsize=9, color=INK, va="top", linespacing=1.55)
    axa.text(-0.96, pc.size * 0.30,
             "solar CF is stated, not drawn — degenerate:\n"
             f"every pairwise correlation = {sc.min():.6f}\n"
             "(the 516 “distinct” profiles differ in\namplitude only; "
             "one shape)" if solar_degenerate else
             f"solar CF: min pairwise correlation {sc.min():.6f}",
             fontsize=8.5, color=INK_2, va="top", linespacing=1.5)
    axa.set_title("(a)  Within villages — no diversity",
                  fontsize=11.5, color=INK, loc="left", pad=10)

    # ---------------- panel (b): villages vs grid ----------------
    axb.set_facecolor(SURFACE)
    x = np.arange(168)
    axb.plot(x, agg[s], color=BLUE, lw=2, zorder=4,
             label="village aggregate (780 sites)")
    axb.plot(x, grid[s], color=ORANGE, lw=2, zorder=3,
             label="grid demand_z1 (derived, not measured)")
    wk_pk_h = int(agg[s].argmax())
    axb.annotate(f"village annual peak {coincident:.2f} MW (h {v_pk_h})",
                 xy=(wk_pk_h, agg[s].max()), xytext=(3, 140),
                 ha="left", va="center", fontsize=8.5, color=INK,
                 arrowprops=dict(arrowstyle="-", lw=0.8, color=MUTED,
                                 shrinkA=2, shrinkB=3))
    axb.text(2, 197,
             f"r = −{abs(r):.2f} as constructed — but +0.32 before the netting\n"
             f"coincident peak {sum_pk:.2f} → {comb_pk:.2f} MW "
             f"({saving:.2f} MW saved) under this construction",
             fontsize=9, color=INK, va="top", linespacing=1.6)
    axb.set_xlim(0, 167)
    axb.set_ylim(0, 200)
    axb.set_xticks(np.arange(0, 169, 24))
    axb.set_yticks([0, 50, 100, 150])
    axb.set_xlabel(f"hour of representative week {WEEK + 1} of 8 "
                   "(contains the village annual peak)",
                   fontsize=9.5, color=INK_2)
    axb.set_ylabel("MW", fontsize=9.5, color=INK_2)
    axb.legend(loc="upper right", bbox_to_anchor=(1.0, 0.845), frameon=False,
               fontsize=8.5, handlelength=1.6)
    axb.set_title("(b)  Villages vs grid — a constructed complementarity",
                  fontsize=11.5, color=INK, loc="left", pad=10)

    for ax in (axa, axb):
        ax.yaxis.grid(True, color=GRID, lw=0.8, zorder=0)
        ax.tick_params(colors=MUTED, labelsize=8.5)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(BASE)

    fig.suptitle("Two diversity factors: none among the villages; the "
                 "village\u2194grid one is a modelling construction",
                 fontsize=13.5, color=INK, x=0.065, y=0.965, ha="left")

    fig.text(0.065, 0.155,
             "panel (a) reflects archetype synthesis (621 of 780 villages share one demand "
             "archetype), not measured behaviour\n"
             "panel (b): the grid series is provincial load MINUS village load, so its "
             "anti-correlation is inherited from that subtraction — the two are +0.32 "
             "correlated before it",
             fontsize=7.5, color=MUTED, va="top", linespacing=1.6)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}")
    print(f"  (a) diversity factor {df_within:.7f}; {pc.size:,} pairs, "
          f"mean corr {pc.mean():.4f}, {share_999:.1%} >= 0.999; "
          f"{peak_hours.size} distinct peak hours; solar min corr {sc.min():.6f}")
    print(f"  (b) r = {r:.4f}; peaks {abs(v_pk_h - g_pk_h)} h apart "
          f"(village h{v_pk_h}, grid h{g_pk_h}); "
          f"{sum_pk:.2f} -> {comb_pk:.2f} MW ({saving:.2f} MW saved), "
          f"diversity factor {df_grid:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
