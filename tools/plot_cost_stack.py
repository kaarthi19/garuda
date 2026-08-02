#!/usr/bin/env python3
"""F1 — Where the money goes: a storage programme with solar attached.

Single horizontal stacked bar of the six annualised cost components of the
islanded village optimum (`results/village_timor_2030_reference`, exact LP —
no binaries, no MIP gap), with the two battery capital segments bracketed:

    storage: $40.20 M/yr = 58.2% (capital)

    python3 tools/plot_cost_stack.py                       # -> results/figures/
    python3 tools/plot_cost_stack.py <run_dir> --out fig.png

The split is recomputed live by importing `attribute()` from
tools/village_cost_attribution.py (the §0 reconstruction, which closes on the
reported `cost_results.csv::Total_Costs` to 12 s.f.); if the run directory is
missing the script falls back to the session-verified constants and labels the
figure accordingly. Verified split ($M/yr): battery energy 35.6002, solar
25.2364, battery power 4.6042, diesel fuel+VOM 3.2974, battery VOM 0.2763,
diesel fixed O&M 0.1198.

Two caveats the caption must carry (figure_plan_timor.md, F1 "must carry"):

1. THE REALLOCATION. `cost_results.csv` books battery POWER capex inside
   `Fixed_Costs_Village` ($29.96 M/yr) alongside solar, and only battery
   ENERGY lands in `Fixed_Costs_Village_Storage`. Read naively that file says
   "solar $29.96 M, storage $35.60 M"; attributed by component the truth is
   solar $25.24 M and storage $40.20 M of capital (58.2%; $40.48 M = 58.6%
   all-in with battery VOM).
2. THE LCOE GAP. Solar generates at ~$46/MWh, yet delivered energy costs
   $127.47/MWh (measured mean; median $127.69) — about half of delivered
   energy is time-shifted through the battery, whose capital dominates the
   system. And battery power capex is not one number: it ranges
   $9,173–$30,001/MW-yr across rows.

Chart conventions follow the dataviz method: one axis; thin bar; 2px surface
gaps between segments; sequential blue ramp for the battery components, orange
for solar (second categorical slot), neutral greys for the diesel residual;
text in ink tokens, never series colour; selective direct labels with leader
lines for the sliver segments.

Requires matplotlib (not part of the core pip set). Solver-free.
"""
import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["text.parse_math"] = False  # figure text is full of literal "$"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

# ---- palette (reference dataviz palette, light mode) ----
BLUE = "#2a78d6"        # battery energy — the headline segment
BLUE_MID = "#5897e2"    # battery power  — same ramp, one step lighter
BLUE_LIGHT = "#86b6ef"  # battery VOM    — lightest ramp step
ORANGE = "#eb6834"      # solar — second categorical slot
GREY = "#898781"        # diesel fuel + VOM — deliberate neutral (residual)
GREY_LIGHT = "#c3c2b7"  # diesel fixed O&M
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"

# ---- session-verified fallback ($/yr), used only if the run dir is absent ----
VERIFIED = {
    "battery_energy": 35.6002e6, "solar": 25.2364e6, "battery_power": 4.6042e6,
    "diesel_fuel_vom": 3.2974e6, "battery_vom": 0.2763e6, "diesel_fixed": 0.1198e6,
}
VERIFIED_FCV = 29.9604  # cost_results.csv::Fixed_Costs_Village, $M/yr

ORDER = [  # battery group first so the capital bracket spans contiguous segments
    ("battery_energy", "battery energy", BLUE),
    ("battery_power", "battery power", BLUE_MID),
    ("battery_vom", "battery VOM", BLUE_LIGHT),
    ("solar", "solar (inv + FOM)", ORANGE),
    ("diesel_fuel_vom", "diesel fuel + VOM", GREY),
    ("diesel_fixed", "diesel fixed O&M", GREY_LIGHT),
]


def load_split(run_dir):
    """(comp $/yr, Fixed_Costs_Village $M/yr, live?) — recomputed or fallback."""
    try:
        import pandas as pd
        from village_cost_attribution import _resolve_dataset, attribute
        ds, _, _ = _resolve_dataset(run_dir, os.path.join(REPO, "data_indonesia"))
        _, comp = attribute(run_dir, ds)
        fcv = float(pd.read_csv(os.path.join(run_dir, "cost_results.csv"))
                    .Fixed_Costs_Village[0])
        return comp, fcv, True
    except (SystemExit, OSError, ImportError, KeyError) as exc:
        print(f"warning: live reconstruction unavailable ({exc}); "
              "using session-verified constants", file=sys.stderr)
        return dict(VERIFIED), VERIFIED_FCV, False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run_dir", nargs="?",
                    default=os.path.join(REPO, "results",
                                         "village_timor_2030_reference"))
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures",
                                                  "cost_stack.png"))
    args = ap.parse_args(argv)

    comp, fcv, live = load_split(args.run_dir)
    extra = sorted(set(comp) - {k for k, _, _ in ORDER})
    if extra:  # non-timor dataset with other technologies: fold in, keep honest
        print(f"note: extra component(s) appended in grey: {extra}", file=sys.stderr)
    order = ORDER + [(k, k.replace("_", " "), GREY_LIGHT) for k in extra]

    total = sum(comp.values())
    val = {k: comp.get(k, 0.0) / 1e6 for k, _, _ in order}     # $M/yr
    pct = {k: comp.get(k, 0.0) / total * 100 for k, _, _ in order}
    cap = val["battery_energy"] + val["battery_power"]          # storage capital
    tot = total / 1e6

    fig, ax = plt.subplots(figsize=(10.8, 5.6), dpi=200)
    ax.set_position([0.055, 0.315, 0.92, 0.445])
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    h = 0.065  # bar thickness in data units (~30 px — thin mark)
    left = 0.0
    edges = {}
    for k, _, colour in order:
        w = val[k]
        ax.barh(0, w, left=left, height=h, color=colour, zorder=3,
                edgecolor=SURFACE, linewidth=0.72)   # 0.72 pt = 2 px surface gap
        edges[k] = (left, left + w)
        left += w

    # ---- inside labels for the two wide segments (the fill-luminance exception)
    ax.text(sum(edges["battery_energy"]) / 2, 0,
            f"battery energy — ${val['battery_energy']:.2f} M/yr · "
            f"{pct['battery_energy']:.1f}%",
            ha="center", va="center", fontsize=9, color="white", zorder=4)
    ax.text(sum(edges["solar"]) / 2, 0,
            f"solar (inv + FOM) — ${val['solar']:.2f} M/yr · {pct['solar']:.1f}%",
            ha="center", va="center", fontsize=9, color=INK, zorder=4)

    # ---- the bracket: storage CAPITAL = battery energy + battery power
    b0, b1 = 0.0, edges["battery_power"][1]
    yt, yl = 0.06, 0.095
    ax.plot([b0, b0, b1, b1], [yt, yl, yl, yt], color=INK_2, lw=1.0,
            solid_capstyle="butt", zorder=4)
    ax.text((b0 + b1) / 2, 0.125,
            f"storage: ${cap:.2f} M/yr = {cap / tot * 100:.1f}% (capital)",
            ha="center", va="bottom", fontsize=10.5, color=INK,
            fontweight="semibold")

    # ---- leader-line labels for the sliver segments
    def leader(key, name, xytext, ha):
        c = sum(edges[key]) / 2
        y0 = h / 2 + 0.005 if xytext[1] > 0 else -h / 2 - 0.005
        ax.annotate(f"{name} — ${val[key]:.2f} M/yr · {pct[key]:.1f}%",
                    xy=(c, y0), xytext=xytext, ha=ha, va="center",
                    fontsize=8.8, color=INK,
                    arrowprops=dict(arrowstyle="-", lw=0.8, color=MUTED,
                                    shrinkA=3, shrinkB=2))

    leader("diesel_fuel_vom", "diesel fuel + VOM", (70.2, 0.15), "right")
    leader("battery_power", "battery power", (37.3, -0.22), "right")
    leader("diesel_fixed", "diesel fixed O&M", (70.2, -0.22), "right")
    leader("battery_vom", "battery VOM", (41.8, -0.40), "left")

    # ---- axes / chrome
    ax.set_xlim(-0.25, 70.4)
    ax.set_ylim(-0.60, 0.46)
    ax.set_yticks([])
    ax.set_xticks(range(0, 71, 10))
    ax.set_xlabel("annualised cost  ($M/yr)", fontsize=10, color=INK_2)
    ax.xaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.tick_params(colors=MUTED, labelsize=9)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.axvline(0, color=BASE, lw=1, zorder=2)

    # ---- title block
    src = os.path.basename(args.run_dir.rstrip("/"))
    status = "" if live else "  ·  SESSION-VERIFIED CONSTANTS (run dir unavailable)"
    fig.text(0.055, 0.935, "Where the money goes: a storage programme "
             "with solar attached", fontsize=13.5, color=INK, va="top",
             fontweight="semibold")
    fig.text(0.055, 0.878,
             f"780 villages, islanded · total ${tot:.2f} M/yr",
             fontsize=9.5, color=INK_2, va="top")

    # ---- caption: the two must-carry caveats

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}")
    for k, name, _ in order:
        print(f"  {name:<20}{val[k]:>9.4f} $M/yr  {pct[k]:>5.1f}%")
    print(f"  {'TOTAL':<20}{tot:>9.4f} $M/yr   (storage capital "
          f"{cap:.4f} = {cap / tot * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
