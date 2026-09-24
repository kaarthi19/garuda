#!/usr/bin/env python3
"""The technical-brief figure suite, on the ERA5 results, in one clean style.

Every figure here is drawn without a title, subtitle or explanatory annotation:
the prose lives in the brief's captions and text, the figure carries only the
data, axis labels, value labels and a legend where one is needed. One palette,
one font size ladder, white background, 200 dpi.

    python tools/plot_brief_figures.py                # all figures -> results/figures/brief/
    python tools/plot_brief_figures.py --only kit cost_stack

Result folders (ERA5 weather, full 8-week model; see RUN_LOG 2026-09-20):
  islanded          results/village_timor__marketfix_era5_2030_reference__bd4h
  unconstrained     results/gridvillage_timor__marketfix_era5_2030_reference__fixverify_bd4h
  carbon-neutral    results/gridvillage_timor__marketfix_era5_2030_clean__fixverify_p450_bd4h
The carbon-neutral ceiling is parsed from jobs/e5_w2c_gridvillage/solve.log
(the 2-week clean root bound) against the 2-week islanded LP. Override any
folder with --root / the RUNS table below when the seeded search lands.

Figures:
  village_map        Fig 1  where the villages are, by kabupaten, on the basemap
  kit                Fig 2  solar and battery per household; diesel before/after
  cost_stack         Fig 3  islanded annual cost by component
  three_regimes      Fig 4  cost, CO2, village solar, villages connected
  village_supply     Fig 5  energy serving village load, by source, per regime
  cost_vs_co2        Fig 6  the three plans on a cost / CO2 plane
  connection_basemap Fig 7  who connects, both regimes, on the basemap
  kit_split          Fig 8  sizing by connection status, carbon-neutral plan
  coordination       Fig 9  coordination value per pairing (floor + ceiling)
"""
import argparse
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figlib as F  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(REPO, "results")
DATA = os.path.join(REPO, "data_indonesia", "2030", "timor")
OUT = os.path.join(RESULTS, "figures", "brief")

DS = "timor__marketfix_era5"
# Numbers of record (decision 2026-09-24): the 4 h-battery legs of every regime.
RUNS = {
    "islanded":      f"village_{DS}_2030_reference__bd4h",
    "unconstrained": f"gridvillage_{DS}_2030_reference__fixverify_bd4h",
    "carbon_neutral": f"gridvillage_{DS}_2030_clean__fixverify_p450_bd4h",
    "islanded_2w":   f"village_{DS}_2w_2030_reference",
}
SHOW_CEILING = False   # the 2-week search bound was measured without the duration constraint
CLEAN_SEARCH_LOG = os.path.join(REPO, "jobs", "e5_w2c_gridvillage", "solve.log")
DIESEL_FUEL = 18.0     # $/MMBtu, fuels_data.csv
VILLAGE_DEMAND_GWH = 544.075

# ---- style -------------------------------------------------------------------
BLUE, ORANGE, GREY, GREEN = "#2a78d6", "#eb6834", "#8a8984", "#3a9d6b"
LIGHTBLUE = "#9cc3ee"
INK, INK2, MUTED, GRIDLN = "#1a1a1a", "#4a4a48", "#8a8984", "#e4e3dd"
KAB = {"BELU": "#4c8fdc", "KUPANG": "#eb6834", "TIMOR TENGAH SELATAN": "#3aa878", "TIMOR TENGAH UTARA": "#e0a520"}
REGIME_LABELS = ["Islanded", "Coordinated,\nno carbon rule", "Coordinated,\ncarbon-neutral"]
REGIME_COLOURS = [BLUE, ORANGE, GREEN]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": "#c9c8c1",
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "white",
    "axes.facecolor": "white", "savefig.facecolor": "white", "legend.frameon": False,
})


def style(ax, ygrid=True):
    ax.grid(axis="y" if ygrid else "x", color=GRIDLN, lw=0.7, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"{name}.png")
    fig.savefig(p, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", p)


# ---- data ----------------------------------------------------------------------
def _read(p):
    return pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False, na_values=[""])


_MAN = None
def manifest():
    global _MAN
    if _MAN is None:
        _MAN = _read(os.path.join(DATA, "timor_villages_manifest.csv")).set_index("Village")
    return _MAN


def load(key, tiebreak=0.0):
    """Per-village builds, totals, energy and cost for one result folder."""
    d = os.path.join(RESULTS, RUNS[key])
    if not os.path.exists(os.path.join(d, "cost_results.csv")):
        raise FileNotFoundError(d)
    vg = _read(os.path.join(DATA, "village_generators.csv"))
    g = _read(os.path.join(d, "site_generator_results.csv"))
    s = _read(os.path.join(d, "site_storage_results.csv"))
    n = _read(os.path.join(d, "site_connection_results.csv")).set_index("ID")
    c = _read(os.path.join(d, "cost_results.csv")).iloc[0]
    e = _read(os.path.join(d, "clean_energy_results.csv")).iloc[0]
    gg = _read(os.path.join(d, "generator_results.csv"))
    t = g.technology.str.lower()
    sol = g[t.str.contains("solar")].groupby("Village").Total_MW.sum()
    bp = g[t.str.contains("batt")].groupby("Village").Total_MW.sum().reindex(sol.index).fillna(0)
    be = s.groupby("Village").Total_Storage_MWh.sum().reindex(sol.index).fillna(0)
    dmw = g[t.str.contains("diesel")].groupby("Village").Total_MW.sum().reindex(sol.index).fillna(0)
    pk = manifest().peak_mw.reindex(sol.index)
    conn = (n.Connected.reindex(sol.index).fillna(0) >= 0.5)
    # cost attribution (figure_plan §0 formula; reconciles to Total_Costs village terms to 6 d.p.)
    gm = g.merge(vg[["R_ID", "Inv_Cost_per_MWyr", "Fixed_OM_Cost_per_MWyr", "Var_OM_Cost_per_MWh",
                     "Heat_Rate_MMBTU_per_MWh"]], left_on="ID", right_on="R_ID")
    gm["inv"] = gm.Change_in_MW.clip(lower=0) * gm.Inv_Cost_per_MWyr
    gm["fom"] = gm.Total_MW * gm.Fixed_OM_Cost_per_MWyr
    gm["var"] = gm.Electricity_GWh * 1e3 * (gm.Var_OM_Cost_per_MWh + gm.Heat_Rate_MMBTU_per_MWh * DIESEL_FUEL)
    sm = s.merge(vg[["R_ID", "Inv_Cost_per_MWhyr", "Fixed_OM_Cost_per_MWhyr"]], left_on="ID", right_on="R_ID")
    sm["e_inv"] = sm.Change_in_Storage_MWh.clip(lower=0) * sm.Inv_Cost_per_MWhyr
    sm["e_fom"] = sm.Total_Storage_MWh * sm.Fixed_OM_Cost_per_MWhyr
    tm = gm.technology.str.lower()
    comp = {
        "Battery energy": sm.e_inv.sum() + sm.e_fom.sum(),
        "Battery power": gm.loc[tm.str.contains("batt"), ["inv", "fom"]].sum().sum(),
        "Battery operation": gm.loc[tm.str.contains("batt"), "var"].sum(),
        "Solar": gm.loc[tm.str.contains("solar"), ["inv", "fom"]].sum().sum(),
        "Diesel fuel": gm.loc[tm.str.contains("diesel"), "var"].sum(),
        "Diesel fixed O&M": gm.loc[tm.str.contains("diesel"), "fom"].sum(),
    }
    per_village = (gm.groupby("Village")[["inv", "fom", "var"]].sum().sum(axis=1)
                   + sm.groupby("Village")[["e_inv", "e_fom"]].sum().sum(axis=1).reindex(sol.index).fillna(0))
    imp, exp = n.Total_Import_MWh.sum(), n.Total_Export_MWh.sum()
    tg = gg.technology.str.lower()
    return dict(
        sol=sol, bp=bp, be=be, dmw=dmw, pk=pk, conn=conn, per_village=per_village, comp=comp,
        cost=float(c.Total_Costs) - imp * tiebreak / 1e6,
        village_cost=sum(comp.values()) / 1e6,
        co2=float(e.CO2_Emissions) / 1e3, re=float(e.System_REShare),
        solar_gwh=g[t.str.contains("solar")].Electricity_GWh.sum(),
        diesel_gwh=g[t.str.contains("diesel")].Electricity_GWh.sum(),
        batt_gwh=g[t.str.contains("batt")].Electricity_GWh.sum(),
        net_grid_gwh=(imp - exp) / 1e3, gross_import_gwh=imp / 1e3,
        n_conn=int(conn.sum()),
        coal_gwh=gg.loc[tg.str.contains("coal"), "GWh"].sum(),
        diesel_today=manifest().diesel_mw.sum(),
    )


def clean_ceiling():
    """Upper bound on the carbon-neutral coordination value from the 2-week search:
    2-week islanded LP cost minus the clean MILP's best bound. None if unavailable."""
    p = os.path.join(RESULTS, RUNS["islanded_2w"], "cost_results.csv")
    if not (os.path.exists(p) and os.path.exists(CLEAN_SEARCH_LOG)):
        return None
    w2 = float(_read(p).Total_Costs.iloc[0])
    bounds = [re.search(r"best bound ([0-9.e+]+)", l) for l in open(CLEAN_SEARCH_LOG) if "best bound" in l]
    bounds = [float(m.group(1)) / 1e6 for m in bounds if m]
    return (w2 - bounds[-1]) if bounds else None


def label_bars(ax, bars, fmt, dy=0.01, fontsize=10, color=INK):
    ymax = ax.get_ylim()[1]
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + ymax * dy, fmt(b.get_height()),
                ha="center", va="bottom", fontsize=fontsize, color=color)


# ---- Fig 1: village map --------------------------------------------------------
def fig_village_map():
    import geopandas as gpd
    xlim, ylim = F.bbox_metric(*F.TIMOR_BBOX)
    vg = F.load_villages()
    g = F.village_gdf(vg)
    subs = gpd.read_file(F.SUBS).to_crs(F.METRIC).cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
    fig, ax = plt.subplots(figsize=(11, 8.2))
    F.draw_base(ax, xlim, ylim, res_m=200, shade_ghi=False)
    for kab, col in KAB.items():
        sel = g[g.kabupaten.str.upper() == kab]
        ax.scatter(sel.geometry.x, sel.geometry.y, s=np.sqrt(sel.households.astype(float)) * 1.1,
                   facecolor=col, edgecolor="#333", linewidth=0.35, alpha=0.9, zorder=4)
    ax.scatter(subs.geometry.x, subs.geometry.y, s=170, marker="s", facecolor="#1f4e8c",
               edgecolor="white", linewidth=1.3, zorder=6)
    h = [Line2D([], [], marker="o", ls="", mfc=c, mec="#333", ms=8, label=k.title().replace("Tengah", "Tengah"))
         for k, c in KAB.items()]
    h.append(Line2D([], [], marker="s", ls="", mfc="#1f4e8c", mec="white", ms=10, label="Grid substation"))
    leg1 = ax.legend(handles=h, loc="upper left", fontsize=9.5, framealpha=0.92, frameon=True)
    ax.add_artist(leg1)
    hh = [Line2D([], [], marker="o", ls="", mfc="#ddd", mec="#333", ms=np.sqrt(np.sqrt(x) * 1.1), label=f"{x:,} households")
          for x in (500, 2000, 8000)]
    ax.legend(handles=hh, loc="lower right", fontsize=9, frameon=True, framealpha=0.92,
              labelspacing=1.3, borderpad=0.9, handletextpad=1.2)
    F.scalebar(ax, xlim, ylim, 20000, "20 km", frac=(0.30, 0.045))
    F.north_arrow(ax, xlim, ylim, frac=(0.94, 0.80))
    fig.tight_layout()
    save(fig, "fig1_village_map")


# ---- Fig 2: the kit ------------------------------------------------------------
def fig_kit():
    o = load("islanded")
    hh = manifest().households.reindex(o["sol"].index).astype(float)
    kwp = (1e3 * o["sol"] / hh).dropna()
    kwh = (1e3 * o["be"] / hh).dropna()
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), gridspec_kw=dict(width_ratios=[1.2, 1.2, 0.8]))
    ax = axes[0]
    ax.hist(kwp, bins=np.arange(0.5, 1.11, 0.02), color=BLUE, edgecolor="white", lw=0.4, zorder=3)
    ax.axvline(kwp.median(), color=INK, lw=1, ls="--", zorder=4)
    ax.text(kwp.median() + 0.02, ax.get_ylim()[1] * 0.93, f"median {kwp.median():.2f}", fontsize=9.5, color=INK)
    ax.set_xlabel("Solar kWp per household"); ax.set_ylabel("Villages"); style(ax)
    ax = axes[1]
    ax.hist(kwh, bins=np.arange(0.8, 2.21, 0.04), color=BLUE, edgecolor="white", lw=0.4, zorder=3)
    ax.axvline(kwh.median(), color=INK, lw=1, ls="--", zorder=4)
    ax.text(kwh.median() + 0.05, ax.get_ylim()[1] * 0.93, f"median {kwh.median():.2f}", fontsize=9.5, color=INK)
    ax.set_xlabel("Battery kWh per household"); style(ax)
    ax = axes[2]
    today, plan = o["diesel_today"], o["dmw"].sum()
    bars = ax.bar(["Existing\ngensets", "Retained\nin plan"], [today, plan], color=[GREY, ORANGE], width=0.6, zorder=3)
    label_bars(ax, bars, lambda v: f"{v:.0f} MW")
    ax.set_ylabel("Diesel capacity, MW"); ax.set_ylim(0, today * 1.15); style(ax)
    fig.tight_layout(w_pad=2.5)
    save(fig, "fig2_kit")


# ---- Fig 2b: duration sensitivity ---------------------------------------------
def fig_duration():
    rows = []
    for key, lab in (("islanded", "5.9 h\n(optimum)"), ("islanded_4h", "4 h"), ("islanded_2h", "2 h")):
        o = load(key)
        gen = o["solar_gwh"] + o["diesel_gwh"]
        rows.append((lab, (o["sol"] / o["pk"]).median(), (o["be"] / o["pk"]).median(),
                     100 * o["diesel_gwh"] / gen, o["village_cost"]))
    labs = [r[0] for r in rows]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.6))
    specs = [("Solar MW per MW peak", 1, "{:.2f}", BLUE), ("Battery MWh per MW peak", 2, "{:.2f}", BLUE),
             ("Diesel share of village energy, %", 3, "{:.0f}%", ORANGE), ("Village programme cost, \\$M/yr", 4, "{:.1f}", GREY)]
    for ax, (ylabel, i, fmt, col) in zip(axes, specs):
        vals = [r[i] for r in rows]
        bars = ax.bar(labs, vals, color=col, width=0.6, zorder=3)
        ax.set_ylim(0, max(vals) * 1.18)
        label_bars(ax, bars, lambda v, f=fmt: f.format(v), fontsize=9.5)
        ax.set_ylabel(ylabel, fontsize=9.5); style(ax)
    fig.tight_layout(w_pad=2.0)
    save(fig, "fig2b_duration")


# ---- Fig 3: cost stack ---------------------------------------------------------
def fig_cost_stack():
    o = load("islanded")
    comp = o["comp"]; tot = sum(comp.values())
    order = ["Battery energy", "Battery power", "Battery operation", "Solar", "Diesel fuel", "Diesel fixed O&M"]
    cols = [BLUE, LIGHTBLUE, "#c9ddf4", ORANGE, GREY, "#bdbcb7"]
    fig, ax = plt.subplots(figsize=(11, 2.9))
    left = 0
    for name, col in zip(order, cols):
        v = comp[name] / 1e6
        ax.barh([0], [v], left=left, color=col, edgecolor="white", lw=0.8, height=0.55, zorder=3)
        share = comp[name] / tot
        if share > 0.12:
            ax.text(left + v / 2, 0, f"{name}\n\\${v:.1f}M · {share:.0%}", ha="center", va="center",
                    fontsize=9.5, color="white" if col in (BLUE, ORANGE, GREY) else INK)
        elif share > 0.045:
            ax.plot([left + v / 2] * 2, [0.28, 0.4], color=INK2, lw=0.8, zorder=4)
            ax.text(left + v / 2, 0.43, f"{name}  \\${v:.1f}M · {share:.0%}", ha="center", va="bottom", fontsize=9, color=INK)
        left += v
    small = [(n, comp[n] / 1e6, comp[n] / tot) for n in order if comp[n] / tot <= 0.045]
    ax.text(0, -0.5, "   ".join(f"{n}: \\${v:.1f}M ({s:.1%})" for n, v, s in small), fontsize=8.5, color=MUTED, va="top")
    ax.set_xlim(0, tot / 1e6 * 1.005); ax.set_ylim(-0.9, 0.75); ax.set_yticks([])
    ax.set_xlabel("Annualised cost of the islanded programme, \\$M per year"); ax.spines["left"].set_visible(False)
    style(ax, ygrid=False)
    fig.tight_layout()
    save(fig, "fig3_cost_stack")


# ---- Fig 4: three regimes ------------------------------------------------------
def fig_three_regimes():
    os_ = [load("islanded"), load("unconstrained"), load("carbon_neutral")]
    panels = [("System cost, \\$M/yr", [o["cost"] for o in os_], "{:.1f}"),
              ("System CO₂, kt/yr", [o["co2"] for o in os_], "{:,.0f}"),
              ("Village solar built, MW", [o["sol"].sum() for o in os_], "{:.0f}"),
              ("Villages connected, of 780", [o["n_conn"] for o in os_], "{:.0f}")]
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.8))
    for ax, (ylabel, vals, fmt) in zip(axes, panels):
        bars = ax.bar(REGIME_LABELS, vals, color=REGIME_COLOURS, width=0.62, zorder=3)
        ax.set_ylim(0, max(vals) * 1.18)
        label_bars(ax, bars, lambda v, f=fmt: f.format(v), fontsize=9.5)
        ax.set_ylabel(ylabel, fontsize=9.5); ax.tick_params(axis="x", labelsize=8.2); style(ax)
    fig.tight_layout(w_pad=2.4)
    save(fig, "fig4_three_regimes")


# ---- Fig 5: who powers the villages ------------------------------------------
def fig_village_supply():
    os_ = [load("islanded"), load("unconstrained"), load("carbon_neutral")]
    sol = [o["solar_gwh"] for o in os_]; dsl = [o["diesel_gwh"] for o in os_]; grid = [max(o["net_grid_gwh"], 0) for o in os_]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    x = np.arange(3)
    b1 = ax.bar(x, sol, color=BLUE, width=0.6, zorder=3, label="Village solar")
    b2 = ax.bar(x, dsl, bottom=sol, color=ORANGE, width=0.6, zorder=3, label="Village diesel")
    b3 = ax.bar(x, grid, bottom=np.add(sol, dsl), color=GREY, width=0.6, zorder=3, label="Net supply from the grid")
    for i in range(3):
        tot = sol[i] + dsl[i] + grid[i]
        ax.text(i, tot + 12, f"{tot:.0f}", ha="center", fontsize=10, color=INK)
        for val, bottom in ((sol[i], 0), (grid[i], sol[i] + dsl[i])):
            if val > 60:
                ax.text(i, bottom + val / 2, f"{val:.0f}", ha="center", va="center", fontsize=9.5, color="white")
    ax.axhline(VILLAGE_DEMAND_GWH, color=INK, lw=1, ls=":", zorder=4)
    ax.text(2.42, VILLAGE_DEMAND_GWH, f"village demand\n{VILLAGE_DEMAND_GWH:.0f} GWh/yr", fontsize=8.5, va="center", color=INK2)
    ax.set_xticks(x); ax.set_xticklabels(REGIME_LABELS, fontsize=9.5)
    ax.set_ylabel("Energy serving village load, GWh/yr"); ax.set_ylim(0, 700); ax.set_xlim(-0.5, 2.9)
    ax.legend(loc="upper center", ncol=3, fontsize=9, bbox_to_anchor=(0.5, 1.08)); style(ax)
    fig.tight_layout()
    save(fig, "fig5_village_supply")


# ---- Fig 6: cost vs CO2 --------------------------------------------------------
def fig_cost_vs_co2():
    os_ = [load("islanded"), load("unconstrained"), load("carbon_neutral")]
    fig, ax = plt.subplots(figsize=(8, 5))
    for o, col, lab, dx, dy in zip(os_, REGIME_COLOURS, [l.replace("\n", " ") for l in REGIME_LABELS],
                                   (0.6, 0.6, -0.6), (-18, 18, -18)):
        ax.scatter(o["cost"], o["co2"], s=220, color=col, edgecolor="white", lw=1.5, zorder=4)
        ax.annotate(lab, (o["cost"], o["co2"]), xytext=(dx * 8, dy), textcoords="offset points",
                    fontsize=9.5, color=INK, ha="left" if dx > 0 else "right", va="center")
    ax.set_xlabel("System cost, \\$M per year"); ax.set_ylabel("System CO₂, kt per year")
    ax.set_xlim(70, 112); ax.set_ylim(600, 1200); style(ax)
    fig.tight_layout()
    save(fig, "fig6_cost_vs_co2")


# ---- Fig 7: connection basemap ------------------------------------------------
def fig_connection_basemap():
    import geopandas as gpd
    import plot_connection_basemap as pcb
    xlim, ylim = F.bbox_metric(*F.TIMOR_BBOX)
    subs = gpd.read_file(F.SUBS).to_crs(F.METRIC).cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
    fig, axes = plt.subplots(1, 2, figsize=(21, 9))
    for ax, key, title in zip(axes, ("unconstrained", "carbon_neutral"), ("Coordinated, unconstrained", "Coordinated, carbon-neutral")):
        m = pcb.load_run(os.path.join(RESULTS, RUNS[key]))
        pcb.draw_panel(ax, m, xlim, ylim, subs, title, 200)
    sym = [Line2D([], [], marker="o", ls="", mfc=pcb.CONNECTED, mec="#333", ms=8, label="Village — connects to grid"),
           Line2D([], [], marker="o", ls="", mfc=pcb.ISLANDED, mec="#333", ms=8, label="Village — stays islanded"),
           Line2D([], [], marker="s", ls="", mfc=F.BLUE, mec="white", ms=11, label="Grid substation")]
    leg = axes[1].legend(handles=sym, loc="lower left", fontsize=9.5, frameon=True, framealpha=0.92)
    axes[1].add_artist(leg)
    size_h = [Line2D([], [], marker="o", ls="", mfc="#ddd", mec="#333", ms=np.sqrt(12 + (p / 1.0) * 240), label=f"{p:.1f} MW peak")
              for p in (0.1, 0.5, 1.0)]
    axes[0].legend(handles=size_h, loc="lower right", fontsize=9, frameon=True, framealpha=0.92,
                   title="Village peak demand", title_fontsize=9, labelspacing=1.4, borderpad=1.0, handletextpad=1.4)
    fig.tight_layout()
    save(fig, "fig7_connection_basemap")


# ---- Fig 8: kit split by connection status -----------------------------------
def fig_kit_split():
    ref = load("islanded"); cn = load("carbon_neutral")
    groups = [("Islanded plan, all 780", ref["sol"] / ref["pk"], ref["be"] / ref["pk"], BLUE),
              ("Carbon-neutral plan, stays islanded", (cn["sol"] / cn["pk"])[~cn["conn"]], (cn["be"] / cn["pk"])[~cn["conn"]], GREEN),
              ("Carbon-neutral plan, connected", (cn["sol"] / cn["pk"])[cn["conn"]], (cn["be"] / cn["pk"])[cn["conn"]], ORANGE)]
    SOL_MAX = float(np.ceil(max(g[1].max() for g in groups)))
    BAT_MAX = float(np.ceil(max(g[2].max() for g in groups)))
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.2), sharex="row")
    for j, (lab, sr, br, col) in enumerate(groups):
        for i, (r, xl, bins) in enumerate(((sr, "Solar MW per MW of village peak", np.arange(0, SOL_MAX + 0.25, 0.25)),
                                            (br, "Battery MWh per MW of village peak", np.arange(0, BAT_MAX + 0.5, 0.5)))):
            ax = axes[i, j]
            ax.hist(r.dropna(), bins=bins, color=col, edgecolor="white", lw=0.4, zorder=3)
            med = r.median()
            ax.axvline(med, color=INK, lw=1, ls="--", zorder=4)
            ax.text(0.98, 0.9, f"n = {len(r)}\nmedian {med:.2f}", transform=ax.transAxes, ha="right", va="top", fontsize=9, color=INK)
            if i == 0: ax.set_title(lab, fontsize=10.5, color=INK, loc="left")
            ax.set_xlabel(xl, fontsize=9.5)
            if j == 0: ax.set_ylabel("Villages")
            style(ax)
    fig.tight_layout(h_pad=1.5, w_pad=2.0)
    save(fig, "fig8_kit_split")


# ---- Fig 9: coordination value ------------------------------------------------
def fig_coordination():
    isl, unc, cn = load("islanded"), load("unconstrained"), load("carbon_neutral")
    v_unc, v_cn = isl["cost"] - unc["cost"], isl["cost"] - cn["cost"]
    ceil = clean_ceiling() if SHOW_CEILING else None
    rows = [("Village to village", 0.0, None), ("Village to grid,\nunconstrained", v_unc, None),
            ("Village to grid,\ncarbon-neutral", v_cn, ceil)]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    for i, (lab, v, c) in enumerate(reversed(rows)):
        y = i
        if c:
            ax.plot([v, c], [y, y], color=LIGHTBLUE, lw=7, solid_capstyle="butt", zorder=2)
            ax.text(c + 0.3, y, f"≤ {c:.1f}", va="center", fontsize=9.5, color=INK2)
        ax.plot([0, v], [y, y], color=BLUE, lw=3, zorder=3)
        ax.scatter([v], [y], s=140, color=BLUE, zorder=4)
        ax.text(v + 0.35 if not c else v - 0.35, y + (0.28 if c else 0), f"{v:.1f}" if v else "0",
                va="center", ha="left" if not c else "right", fontsize=11, color=INK, fontweight="bold")
    ax.set_yticks(range(3)); ax.set_yticklabels([r[0] for r in reversed(rows)], fontsize=10)
    ax.set_xlabel("Coordination value: islanded cost minus coordinated cost, \\$M per year")
    ax.set_xlim(-0.5, max(v_unc, ceil or 0) * 1.15); ax.set_ylim(-0.6, 2.6)
    if ceil:
        ax.legend(handles=[Line2D([], [], color=BLUE, lw=3, marker="o", ms=9, label="Best plan found (exact)"),
                           Patch(color=LIGHTBLUE, label="Range to the search bound")],
                  loc="lower right", fontsize=9)
    style(ax, ygrid=False)
    fig.tight_layout()
    save(fig, "fig9_coordination")


FIGS = {"village_map": fig_village_map, "kit": fig_kit, "cost_stack": fig_cost_stack,
        "three_regimes": fig_three_regimes, "village_supply": fig_village_supply, "cost_vs_co2": fig_cost_vs_co2,
        "connection_basemap": fig_connection_basemap, "kit_split": fig_kit_split, "coordination": fig_coordination}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="*", choices=sorted(FIGS), help="subset of figures")
    args = ap.parse_args(argv)
    for name in (args.only or FIGS):
        FIGS[name]()


if __name__ == "__main__":
    main()
