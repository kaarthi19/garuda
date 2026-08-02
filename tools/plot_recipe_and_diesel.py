#!/usr/bin/env python3
"""F2 + F3 — one kit fits 780 villages, and diesel shrinks to a 3% backstop.

Implements figures F2 and F3 of docs/figure_plan_timor.md as one two-row
figure from the islanded exact-LP baseline (A1a OFF — a pure LP, so there is
no MIP gap and no incumbent caveat on this leg):

    python3 tools/plot_recipe_and_diesel.py            # -> results/figures/
    python3 tools/plot_recipe_and_diesel.py --out fig.png

Top row (F2): two narrow histograms of the per-village design — solar MW per
MW of village peak (median 2.957, IQR 2.895-2.993) and storage duration
(mean 5.5579 h, s.d. 0.036) — plus the "standard kit" card with the medians
and the island totals (360.7 MW solar, 148.5 MW / 825.1 MWh battery).

Bottom row (F3): diesel capacity before/after (134.35 MW -> 6.66 MW, -95.0%)
and a 100%-stacked generation bar (diesel 2.82% of solar+diesel generation;
battery discharge, 276.3 GWh, is deliberately excluded from the denominator
because it is recycled solar, not primary supply — stated on the figure).

Sources (everything is recomputed from disk, then checked against the
verified figures above; a drifted result folder fails loudly):
  results/village_timor_2030_reference/site_generator_results.csv
  results/village_timor_2030_reference/site_storage_results.csv
  data_indonesia/2030/timor/timor_villages_manifest.csv::peak_mw
    -- NOT village_solar_potential.csv::peak_mw; the two columns differ
       (mean 0.1566 vs 0.1644) and the manifest is the demand-side truth.

Must-carry caveats (printed on the figure; do not strip them for a deck):
- The tightness is substantially manufactured by input homogeneity: one
  solar-profile family, GHI spanning only 4.91-5.95 kWh/m2/day, 621 of 780
  villages on a single demand archetype. The honest claim is "given these
  archetypes and this resource data, one design is optimal everywhere".
- 5.56 h is a continuous optimum, not a product: commercial BESS ship in
  2 h and 4 h blocks.
- The 6.66 MW diesel residual is a continuous variable spread across 780
  sites (median ~6 kW per village), not a procurable genset size.

Chart conventions follow the dataviz method: one axis per panel, thin marks,
single-hue blue for single-series panels, orange as the second categorical
slot only where diesel and solar share a panel, text in ink tokens.

Requires matplotlib + pandas (not part of the core pip set). Solver-free.
"""
import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(REPO, "results", "village_timor_2030_reference")
DATASET = os.path.join(REPO, "data_indonesia", "2030", "timor")

# ---- palette (reference dataviz palette, light mode) ----
BLUE = "#2a78d6"       # series slot 1
BLUE_LIGHT = "#86b6ef" # ramp step: secondary/unresolved
ORANGE = "#eb6834"     # series slot 2 — diesel, only where two hues coexist
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"


def _read(path):
    """Dataset CSV read: BOM-safe, literal fuel name "None" preserved."""
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False,
                       na_values=[""])


def load():
    gen = pd.read_csv(os.path.join(RESULTS, "site_generator_results.csv"))
    sto = pd.read_csv(os.path.join(RESULTS, "site_storage_results.csv"))
    man = _read(os.path.join(DATASET, "timor_villages_manifest.csv"))
    peak = man.set_index("Village")["peak_mw"]

    solar = gen[gen.technology == "solar"].groupby("Village").Total_MW.sum()
    batt_mw = gen[gen.technology == "battery"].groupby("Village").Total_MW.sum()
    batt_mwh = sto.groupby("Village").Total_Storage_MWh.sum()
    diesel = gen[gen.technology == "diesel"]

    d = dict(
        ratio=(solar / peak).dropna(),                 # solar MW per MW peak
        dur=(batt_mwh / batt_mw).dropna(),             # storage duration, h
        batt_mw_pk=(batt_mw / peak).median(),
        batt_mwh_pk=(batt_mwh / peak).median(),
        keep_frac=(diesel.groupby("Village").Total_MW.sum()
                   / diesel.groupby("Village").Start_MW.sum()).median(),
        solar_tot=solar.sum(), batt_mw_tot=batt_mw.sum(),
        batt_mwh_tot=batt_mwh.sum(),
        die_start=diesel.Start_MW.sum(), die_tot=diesel.Total_MW.sum(),
        die_gwh=diesel.Electricity_GWh.sum(),
        sol_gwh=gen[gen.technology == "solar"].Electricity_GWh.sum(),
        bat_gwh=gen[gen.technology == "battery"].Electricity_GWh.sum(),
        die_kw_med=1000 * diesel.groupby("Village").Total_MW.sum().median(),
        n_arch=int((man.archetype == man.archetype.mode()[0]).sum()),
        n=len(peak),
    )
    # guard against a drifted result folder (verified numbers, figure plan §F2/F3)
    assert abs(d["ratio"].median() - 2.957) < 5e-3, d["ratio"].median()
    assert abs(d["dur"].mean() - 5.5579) < 5e-3, d["dur"].mean()
    assert abs(d["die_start"] - 134.3455) < 1e-3 and abs(d["die_tot"] - 6.6558) < 1e-3
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures",
                                                  "recipe_and_diesel.png"))
    args = ap.parse_args(argv)
    d = load()

    fig = plt.figure(figsize=(12.6, 8.2), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    gs = fig.add_gridspec(2, 6, left=0.06, right=0.965, top=0.855, bottom=0.205,
                          hspace=0.52, wspace=0.85,
                          height_ratios=[1.0, 0.9])
    ax_h1 = fig.add_subplot(gs[0, 0:2])
    ax_h2 = fig.add_subplot(gs[0, 2:4])
    ax_kit = fig.add_subplot(gs[0, 4:6])
    ax_cap = fig.add_subplot(gs[1, 0:2])
    ax_en = fig.add_subplot(gs[1, 2:6])
    for ax in (ax_h1, ax_h2, ax_kit, ax_cap, ax_en):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(BASE)
        ax.tick_params(colors=MUTED, labelsize=8.5)

    # ---------------- F2: two narrow histograms ----------------
    med = d["ratio"].median()
    ax_h1.hist(d["ratio"], bins=np.arange(2.70, 4.55, 0.05), color=BLUE,
               edgecolor=SURFACE, linewidth=0.6, zorder=3)
    ax_h1.axvline(med, color=INK_2, lw=0.9, ls=(0, (2, 2)), zorder=4)
    ax_h1.text(med + 0.07, ax_h1.get_ylim()[1] * 0.97,
               f"median {med:.2f}\nIQR {d['ratio'].quantile(.25):.2f}"
               f"–{d['ratio'].quantile(.75):.2f}",
               fontsize=8.5, color=INK, va="top")
    ax_h1.text(d["ratio"].max(), 30, f"max {d['ratio'].max():.2f}  ",
               fontsize=7.5, color=MUTED, ha="right", va="bottom")
    ax_h1.set_xlabel("solar MW per MW of village peak", fontsize=9, color=INK_2)
    ax_h1.set_ylabel("villages", fontsize=9, color=INK_2)
    ax_h1.set_title("Solar sizing: one number", fontsize=10.5, color=INK,
                    loc="left", pad=8)

    mean = d["dur"].mean()
    ax_h2.hist(d["dur"], bins=np.arange(5.15, 5.625, 0.0125), color=BLUE,
               edgecolor=SURFACE, linewidth=0.6, zorder=3)
    ax_h2.text(mean - 0.02, ax_h2.get_ylim()[1] * 0.97,
               f"mean {mean:.2f} h\ns.d. {d['dur'].std():.3f} h",
               fontsize=8.5, color=INK, va="top", ha="right")
    ax_h2.text(d["dur"].min(), 30, f"  min {d['dur'].min():.2f}",
               fontsize=7.5, color=MUTED, ha="left", va="bottom")
    ax_h2.set_xlabel("storage duration (h = MWh / MW)", fontsize=9, color=INK_2)
    ax_h2.set_ylabel("villages", fontsize=9, color=INK_2)
    ax_h2.set_xticks([5.2, 5.3, 5.4, 5.5, 5.6])
    ax_h2.set_title("Storage sizing: one number", fontsize=10.5, color=INK,
                    loc="left", pad=8)
    for ax in (ax_h1, ax_h2):
        ax.yaxis.grid(True, color=GRID, lw=0.8, zorder=0)

    # ---------------- F2: the kit card ----------------
    ax_kit.set_xticks([]), ax_kit.set_yticks([])
    ax_kit.spines["bottom"].set_visible(False)
    ax_kit.add_patch(plt.Rectangle((0.0, 0.0), 1.0, 1.0, transform=ax_kit.transAxes,
                                   facecolor="#f4f3ef", edgecolor=BASE, lw=0.8))
    ax_kit.set_title("The standard kit", fontsize=10.5, color=INK,
                     loc="left", pad=8)
    kit = (
        "per MW of village peak (medians):\n"
        f"  solar     {med:.2f} MW\n"
        f"  battery   {d['batt_mw_pk']:.2f} MW / {d['batt_mwh_pk']:.2f} MWh\n"
        f"            = {mean:.2f} h duration\n"
        f"  diesel    keep ~{100 * d['keep_frac']:.0f}% of nameplate\n"
    )
    tot = (
        f"× {d['n']} villages =\n"
        f"  {d['solar_tot']:.1f} MW solar\n"
        f"  {d['batt_mw_tot']:.1f} MW / {d['batt_mwh_tot']:.1f} MWh battery\n"
        f"  {d['die_tot']:.1f} MW diesel retained"
    )
    ax_kit.text(0.07, 0.94, kit, transform=ax_kit.transAxes, fontsize=8.8,
                color=INK, va="top", family="monospace", linespacing=1.6)
    ax_kit.text(0.07, 0.42, tot, transform=ax_kit.transAxes, fontsize=8.8,
                color=INK_2, va="top", family="monospace", linespacing=1.6)

    # ---------------- F3: diesel capacity before/after ----------------
    ax_cap.bar([0, 1], [d["die_start"], d["die_tot"]], width=0.16,
               color=ORANGE, zorder=3)
    ax_cap.set_xlim(-0.55, 1.55)
    ax_cap.set_xticks([0, 1])
    ax_cap.set_xticklabels(["today\n(existing gensets)", "optimised plan"],
                           fontsize=8.5, color=INK)
    ax_cap.set_ylabel("diesel capacity, MW", fontsize=9, color=INK_2)
    ax_cap.yaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax_cap.text(0, d["die_start"] + 3, f"{d['die_start']:.1f}", fontsize=9,
                color=INK, ha="center", va="bottom")
    ax_cap.text(1, d["die_tot"] + 3, f"{d['die_tot']:.1f}", fontsize=9,
                color=INK, ha="center", va="bottom")
    ax_cap.annotate("−95.0%", xy=(0.5, 62), fontsize=11, color=INK,
                    ha="center",
                    xytext=(0.5, 62))
    ax_cap.set_title("Capacity: −95% — but not to zero",
                     fontsize=10.5, color=INK, loc="left", pad=8)

    # ---------------- F3: share of generation ----------------
    share = 100 * d["die_gwh"] / (d["die_gwh"] + d["sol_gwh"])
    ax_en.barh(0, 100 - share, left=0, height=0.34, color=BLUE, zorder=3)
    ax_en.barh(0, share, left=100 - share, height=0.34, color=ORANGE, zorder=3)
    ax_en.set_xlim(0, 100)
    ax_en.set_ylim(-0.75, 0.9)
    ax_en.set_yticks([])
    ax_en.set_xticks([0, 25, 50, 75, 100])
    ax_en.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax_en.xaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax_en.text(1.5, 0, f"solar  {d['sol_gwh']:.1f} GWh — {100 - share:.1f}%",
               fontsize=9.5, color="white", va="center", zorder=4)
    ax_en.annotate(f"diesel  {d['die_gwh']:.1f} GWh — {share:.2f}%",
                   xy=(100 - share / 2, 0.17), xytext=(97, 0.62),
                   fontsize=9.5, color=INK, ha="right",
                   arrowprops=dict(arrowstyle="-", lw=0.8, color=MUTED,
                                   shrinkA=2, shrinkB=1))
    ax_en.text(0, -0.62,
               "denominator = solar + diesel generation only; battery discharge "
               f"({d['bat_gwh']:.1f} GWh) is excluded — it is recycled "
               "solar, not primary supply",
               fontsize=8, color=INK_2, va="top")
    ax_en.set_title("Share of generation: a "
                    f"{share:.1f}% insurance policy", fontsize=10.5,
                    color=INK, loc="left", pad=8)

    # ---------------- section headers + caveats ----------------
    fig.text(0.06, 0.965, "One kit fits 780 villages",
             fontsize=14, color=INK, va="top", fontweight="bold")
    fig.text(0.06, 0.922, "and diesel does not disappear — it shrinks to a "
             "3% insurance policy   ·   islanded exact-LP plan, no MIP gap "
             "on this leg", fontsize=9.5, color=INK_2, va="top")
    fig.text(0.06, 0.145,
             "Tightness is partly manufactured by input homogeneity: one solar-profile family, GHI spanning only "
             f"4.91–5.95 kWh/m²/day, and {d['n_arch']} of {d['n']} villages on a single demand archetype — "
             "the honest claim is\n“given these archetypes and this resource data, one design is optimal "
             f"everywhere”. {mean:.2f} h is a continuous optimum, not a product: commercial BESS ship in 2 h and "
             "4 h blocks.\n"
             f"The {d['die_tot']:.2f} MW diesel residual is a continuous variable spread across {d['n']} sites "
             f"(median ≈ {d['die_kw_med']:.0f} kW per village), not a procurable genset size — fuel spend "
             "shrinks ~95%, the maintenance\nfootprint does not. Source: results/village_timor_2030_reference · "
             "peak from timor_villages_manifest.csv (not village_solar_potential.csv — the columns differ).",
             fontsize=7.5, color=MUTED, va="top", linespacing=1.6)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}")
    print(f"  solar/peak   : median {med:.4f}  IQR {d['ratio'].quantile(.25):.4f}-"
          f"{d['ratio'].quantile(.75):.4f}  min {d['ratio'].min():.4f}  "
          f"max {d['ratio'].max():.4f}")
    print(f"  duration     : mean {mean:.4f} h  s.d. {d['dur'].std():.4f}")
    print(f"  diesel MW    : {d['die_start']:.4f} -> {d['die_tot']:.4f} "
          f"({100 * (d['die_tot'] / d['die_start'] - 1):.1f}%)")
    print(f"  diesel share : {share:.4f}% of solar+diesel generation "
          f"(battery discharge {d['bat_gwh']:.1f} GWh excluded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
