#!/usr/bin/env python3
"""Who powers the villages — the honest import/export figure.

Per-village trade volumes are NOT publishable from these runs: at
import_price = export_price = 0 the trade variables carry no objective
coefficient, so the optimum is a face and the per-village (and gross) split is
one arbitrary allocation among many — Gurobi and HiGHS agreed on total cost to
11 s.f. while differing 47% on one village's imports. What IS pinned by costed
dispatch: village generation by technology, and the NET grid->village flow.
This figure shows exactly that and nothing more, and says so on its face.

Stacked bars of energy serving the 544 GWh/yr village load, by regime:
village solar / village diesel / net grid supply (coal-dominated in the
unconstrained plan). Battery is excluded from the stack (it shifts energy, it
does not source it); losses explain the small overhang vs demand. The
carbon-neutral bar fills in when its run lands. Requires matplotlib.
"""
import argparse, datetime as _dt, os, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#898781"
INK, INK2, MUTED, GRID_LN, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

def _read(p): return pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False, na_values=[""])

def supply(run):
    sg = os.path.join(run, "site_generator_results.csv")
    if not os.path.exists(sg): return None
    g = _read(sg).groupby("technology").Electricity_GWh.sum()
    solar, diesel = float(g.get("solar", 0)), float(g.get("diesel", 0))
    cn = os.path.join(run, "site_connection_results.csv")
    net = 0.0
    if os.path.exists(cn):
        c = _read(cn)
        net = float(c.Total_Import_MWh.sum() - c.Total_Export_MWh.sum()) / 1e3
    return solar, diesel, max(net, 0.0)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures", "village_supply.png"))
    args = ap.parse_args(argv)
    R = os.path.join(REPO, "results")
    rows = [("islanded", os.path.join(R, "village_timor_2030_reference")),
            ("coordinated,\nunconstrained", os.path.join(R, "gridvillage_timor__marketfix_2030_reference__fixverify")),
            ("coordinated,\ncarbon-neutral", os.path.join(R, "gridvillage_timor__marketfix_2030_clean__fixverify"))]

    fig, ax = plt.subplots(figsize=(9.2, 5.4), dpi=200)
    fig.subplots_adjust(left=0.09, right=0.86, top=0.80, bottom=0.24)
    fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)
    first = True
    for i, (lab, run) in enumerate(rows):
        s = supply(run)
        if s is None:
            ax.bar(i, 20, color=SURFACE, edgecolor=MUTED, ls="--", lw=1.2, width=0.55)
            ax.text(i, 40, "solving", ha="center", fontsize=9, color=MUTED, style="italic")
            continue
        solar, diesel, net = s
        ax.bar(i, solar, width=0.55, color=BLUE, zorder=3, label="village solar" if first else None)
        ax.bar(i, diesel, bottom=solar, width=0.55, color=ORANGE, zorder=3, label="village diesel" if first else None)
        ax.bar(i, net, bottom=solar + diesel, width=0.55, color=GREY, zorder=3,
               label="net grid supply" if first else None)
        first = False
        tot = solar + diesel + net
        ax.text(i, tot + 18, f"{tot:,.0f} GWh/yr", ha="center", fontsize=11, color=INK, fontweight="bold")
        for val, base_, name in ((solar, 0, "solar"), (diesel, solar, "diesel"), (net, solar + diesel, "grid")):
            if val > 35:
                ax.text(i, base_ + val / 2, f"{name} {val:,.0f}", ha="center", fontsize=8.5,
                        color="#ffffff" if val > 60 else INK)
    ax.axhline(544.1, color=BASE, lw=1, ls=":")
    ax.text(2.52, 544, "village demand\n544 GWh/yr", fontsize=8, color=INK2,
            ha="left", va="center", clip_on=False)
    ax.set_xticks(range(len(rows))); ax.set_xticklabels([r[0] for r in rows], fontsize=9.5, color=INK)
    ax.set_ylabel("energy serving village load (GWh/yr)", fontsize=10, color=INK2)
    ax.set_ylim(0, 700)
    ax.yaxis.grid(True, color=GRID_LN, lw=0.8, zorder=0)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.spines["left"].set_color(BASE); ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.005), ncol=3,
              frameon=False, fontsize=9)
    ax.set_title("Who powers the villages", fontsize=13, color=INK, loc="left", pad=30)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
