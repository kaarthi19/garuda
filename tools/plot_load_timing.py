#!/usr/bin/env python3
"""When villages and the grid need power — and what the netting construction does.

Mean hour-of-day load profiles for the village aggregate and for the grid zone
under the TWO defensible constructions of the derived grid series:

- **hourly-netted** (what `build_grid_demand` builds and every market run uses):
  `demand_z1[t] = share x provincial[t] - village[t]`, clipped at 0. Because the
  village series is subtracted hour by hour, the residual dips exactly when the
  villages peak — the apparent anti-correlation (r = -0.81) and the midnight
  grid peak are properties of this subtraction, not of any measured system.
- **shape-preserved**: the provincial shape scaled to the same net energy.
  Under it the grid is +0.32 correlated with the villages (both evening-peaking).

The truth is unknowable from this data — the provincial series does not say
which hours the (largely unelectrified) villages occupy inside it — so the two
constructions bracket it, and the figure's job is to keep that bracket visible.
The coordination headline survives either one: under both, combined load never
exceeds the firm existing fleet in any of the 1,344 hours, so the value is
carried by cheap coal energy, not by hourly complementarity.

Inputs: `data_indonesia/2030/timor/village_demand.csv`, the donor
`nusa_tenggara/demand.csv`, and `timor__market/demand.csv` (rebuild in seconds
with `python -m tools.ntt.build_grid_demand --share 0.42 --out-dataset
timor__market --fleet rescale` if absent; `timor__marketfix` is used when
present — its demand series is identical).

    python3 tools/plot_load_timing.py              # -> results/figures/

Requires matplotlib + pandas + numpy. Solver-free.
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

BLUE = "#2a78d6"       # villages
ORANGE = "#eb6834"     # grid zone (one entity, two constructions -> two styles)
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID_LN = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"

NA = dict(encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def _read(path):
    return pd.read_csv(path, **NA)


def load_series():
    vd = _read(os.path.join(REPO, "data_indonesia/2030/timor/village_demand.csv"))
    cols = [c for c in vd.columns if c.startswith("demand_village")]
    village = vd[cols].apply(pd.to_numeric, errors="coerce").to_numpy().sum(axis=1)

    grid_csv = os.path.join(REPO, "data_indonesia/2030/timor__marketfix/demand.csv")
    if not os.path.exists(grid_csv):
        grid_csv = os.path.join(REPO, "data_indonesia/2030/timor__market/demand.csv")
    if not os.path.exists(grid_csv):
        raise SystemExit(
            "no market dataset found — build one first:\n"
            "  python -m tools.ntt.build_grid_demand --share 0.42 "
            "--out-dataset timor__market --fleet rescale")
    netted = pd.to_numeric(_read(grid_csv)["demand_z1"], errors="coerce").to_numpy()

    donor = pd.to_numeric(
        _read(os.path.join(REPO, "data_indonesia/2030/nusa_tenggara/demand.csv"))
        ["demand_z2"], errors="coerce").to_numpy()[:len(village)]
    preserved = donor * (netted.sum() / donor.sum())
    return village, netted, preserved


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(REPO, "results", "figures",
                                                  "load_timing.png"))
    args = ap.parse_args(argv)

    village, netted, preserved = load_series()
    hod = np.arange(len(village)) % 24
    prof = lambda s: pd.Series(s).groupby(hod).mean().to_numpy()
    pv, pn, pp = prof(village), prof(netted), prof(preserved)
    r = lambda a, b: float(np.corrcoef(a, b)[0, 1])
    r_net, r_pres = r(village, netted), r(village, preserved)

    fig, ax = plt.subplots(figsize=(10.6, 5.6), dpi=200)
    fig.subplots_adjust(left=0.08, right=0.90, top=0.82, bottom=0.16)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    x = np.arange(24)
    ax.plot(x, pv, color=BLUE, lw=2.4, zorder=4, label="villages (780 sites)")
    ax.plot(x, pn, color=ORANGE, lw=2.2, zorder=3,
            label=f"grid — hourly-netted, as modelled (r = {r_net:+.2f})")
    ax.plot(x, pp, color=ORANGE, lw=1.8, ls=(0, (5, 3)), zorder=3,
            label=f"grid — shape-preserved alternative (r = {r_pres:+.2f})")

    ax.set_ylim(15, 135)

    # direct labels just past the right edge, staggered
    ax.text(23.7, pv[-1], "villages", fontsize=9.5, color=INK, va="center",
            clip_on=False)
    ax.text(23.7, pn[-1] + 3, "netted", fontsize=9, color=INK2, va="center",
            clip_on=False)
    ax.text(23.7, pp[-1] - 4, "preserved", fontsize=9, color=INK2, va="center",
            clip_on=False)

    # the two tell-tale features of the netted series
    ax.annotate("the netted series peaks at midnight —\n"
                "no real system does; this is the village\n"
                "evening peak subtracted, not Kupang",
                xy=(0.6, pn[0] - 3), xytext=(3.0, 88),
                fontsize=8.5, color=INK2, va="top",
                arrowprops=dict(arrowstyle="-", lw=0.8, color=MUTED,
                                shrinkA=2, shrinkB=3))
    pk = int(np.argmax(pv))
    ax.annotate("village evening peak",
                xy=(pk, pv[pk]), xytext=(pk - 7.5, pv[pk] + 2),
                fontsize=8.5, color=INK2,
                arrowprops=dict(arrowstyle="-", lw=0.8, color=MUTED,
                                shrinkA=2, shrinkB=3))

    ax.set_xlim(0, 23.6)
    ax.set_xticks(range(0, 24, 3))
    ax.set_xlabel("hour of day (mean across the 8 representative weeks)",
                  fontsize=10, color=INK2)
    ax.set_ylabel("MW", fontsize=10, color=INK2)
    ax.yaxis.grid(True, color=GRID_LN, lw=0.8, zorder=0)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.spines["left"].set_color(BASE)
    ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.005), ncol=3,
              frameon=False, fontsize=8.5, handlelength=2.2)

    ax.set_title("When villages and the grid need power — two constructions "
                 "of the same grid series",
                 fontsize=13, color=INK, loc="left", pad=34)
    fig.text(0.08, 0.025,
             "the two constructions bracket the truth · the coordination headline "
             "survives both: combined load never exceeds the firm fleet",
             fontsize=7.5, color=MUTED, va="bottom")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, facecolor=SURFACE)
    print(f"written: {args.out}")
    print(f"  r(village, netted)    = {r_net:+.3f}   (as modelled)")
    print(f"  r(village, preserved) = {r_pres:+.3f}   (alternative)")
    print(f"  village peak h{int(np.argmax(pv))}, netted peak h{int(np.argmax(pn))}, "
          f"preserved peak h{int(np.argmax(pp))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
