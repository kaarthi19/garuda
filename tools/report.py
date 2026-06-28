#!/usr/bin/env python3
"""Auto-report generator for garuda result folders (Phase 5).

Turns a scenario's result CSVs (written by functions/result_extraction_function.jl
and, for dispatch runs, dispatch_engine.jl) into a single shareable report —
headline metrics, a generation/capacity mix, a cost breakdown, and per-zone
reliability — as a self-contained HTML file and a PDF.

    python tools/report.py results/base_maluku_2030_reference
    python tools/report.py results/gridvillage_timor_demo_2030_reference --open

Outputs report.html and report.pdf inside the results folder (override with
--html/--pdf). HTML embeds its charts (base64 PNG) so it travels as one file. The
PDF uses weasyprint if installed (HTML-fidelity) and otherwise matplotlib's
PdfPages, so a PDF is always produced with no extra system dependencies.

Runs on Python + pandas + matplotlib (jinja2 for HTML). All optional pieces
degrade gracefully if a CSV is absent.
"""
from __future__ import annotations

import argparse
import base64
import io
import os
import sys

try:
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
except ImportError:  # pragma: no cover
    print("report requires pandas + numpy + matplotlib", file=sys.stderr)
    sys.exit(3)

NA = dict(keep_default_na=False, na_values=[""])
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# a stable, color-blind-friendly-ish palette per technology
TECH_COLORS = {
    "solar": "#f4b400", "wind": "#4dd0e1", "hydro": "#1565c0", "geothermal": "#8d6e63",
    "coal": "#37474f", "gas": "#ef6c00", "diesel": "#6d4c41", "battery": "#7e57c2",
    "thermal": "#90a4ae", "biomass": "#2e7d32", "nuclear": "#c2185b", "other": "#bdbdbd",
}


def _read(path):
    return pd.read_csv(path, encoding="utf-8-sig", **NA)


def _color(tech):
    t = str(tech).lower()
    for k, v in TECH_COLORS.items():
        if k in t:
            return v
    return TECH_COLORS["other"]


def load_results(d):
    """Load whichever result CSVs are present into a name->DataFrame dict."""
    R = {}
    for f in os.listdir(d):
        if f.endswith(".csv"):
            try:
                R[f[:-4]] = _read(os.path.join(d, f))
            except Exception:
                pass
    return R


def parse_scenario(d):
    base = os.path.basename(os.path.normpath(d))
    parts = base.split("_")
    # <scenario>_<island...>_<year>_<clean> — year is the 4-digit token
    yi = next((i for i, p in enumerate(parts) if p.isdigit() and len(p) == 4), None)
    if yi is not None and yi >= 1 and yi + 1 < len(parts):
        return dict(scenario=parts[0], island="_".join(parts[1:yi]),
                    year=parts[yi], clean=parts[yi + 1], name=base)
    return dict(scenario="", island="", year="", clean="", name=base)


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def annual_demand_gwh(meta, input_folder=None):
    """Exact annual grid demand (GWh) from the matching input demand.csv.

    The result CSVs are a mix of annualised (cost, CO₂, reliability) and
    representative-period-sum (generator GWh, nse_results) quantities; with
    non-uniform Sub_Weights the latter cannot be annualised after the fact. So
    energy-share headlines are anchored on the *input* demand, which carries the
    weights. Returns None if the input folder can't be located.
    """
    folder = input_folder
    if folder is None and meta.get("year") and meta.get("island"):
        cand = os.path.join(REPO_ROOT, "data_indonesia", meta["year"], meta["island"])
        folder = cand if os.path.isdir(cand) else None
    if not folder or not os.path.isfile(os.path.join(folder, "demand.csv")):
        return None
    d = _read(os.path.join(folder, "demand.csv"))
    P = int(_num(d["Rep_Periods"]).dropna().iloc[0])
    H = int(_num(d["Timesteps_per_Rep_Period"]).dropna().iloc[0])
    W = _num(d["Sub_Weights"]).dropna().to_numpy()[:P]
    T = P * H
    # Bail to None (→ the annual cards are simply omitted) on any malformed input
    # rather than crashing the report: too few Sub_Weights or too few demand rows
    # would otherwise broadcast-mismatch, and an all-missing demand column would
    # propagate NaN into the headline. validate_schema gates a real run on these,
    # but the report can be pointed at any folder.
    if len(W) != P or len(d) < T:
        return None
    sw = np.repeat(W / H, H)[:T]
    zcols = [c for c in d.columns if c.startswith("demand_z")]
    total = sum(float((sw * _num(d[c]).to_numpy()[:T]).sum()) for c in zcols)
    return None if not np.isfinite(total) else total / 1e3  # GWh/yr


def metrics(R, ad_gwh=None):
    """Headline metrics dict (value, unit, label) — missing pieces omitted.

    All energy figures are annual: cost/CO₂/RE come straight from the annualised
    result CSVs; demand/served/unserved are anchored on the input annual demand
    (ad_gwh) so the unserved share is a true fraction of yearly demand, not of the
    representative-period generation sum.
    """
    m = {}
    if "cost_results" in R and "Total_Costs" in R["cost_results"]:
        m["cost"] = (float(R["cost_results"]["Total_Costs"].iloc[0]), "M$", "Total system cost")
    if "clean_energy_results" in R:
        ce = R["clean_energy_results"]
        if "CO2_Emissions" in ce:
            m["co2"] = (float(ce["CO2_Emissions"].iloc[0]) / 1e3, "ktCO₂", "CO₂ emissions")
        if "Grid_REShare" in ce:
            m["re"] = (100 * float(ce["Grid_REShare"].iloc[0]), "%", "Grid RE share")

    # annual unserved energy (reliability_results is sample-weighted/annual)
    unserved_gwh = None
    if "reliability_results" in R and "Total_NSE_MWh" in R["reliability_results"]:
        unserved_gwh = float(_num(R["reliability_results"]["Total_NSE_MWh"]).sum()) / 1e3

    if ad_gwh is not None:
        m["demand"] = (ad_gwh, "GWh", "Annual demand")
        if unserved_gwh is not None:
            served = max(ad_gwh - unserved_gwh, 0.0)
            m["served"] = (served, "GWh", "Energy served")
            m["unserved"] = (unserved_gwh, "GWh", "Unserved energy")
            m["unserved_pct"] = (100 * unserved_gwh / ad_gwh if ad_gwh else 0.0, "%", "Unserved share")
    elif unserved_gwh is not None:
        m["unserved"] = (unserved_gwh, "GWh", "Unserved energy (annual)")
    return m


def _fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _by_tech(df, value_col):
    if df is None or value_col not in df.columns or "technology" not in df.columns:
        return None
    s = df.assign(_v=_num(df[value_col])).groupby("technology")["_v"].sum()
    s = s[s.abs() > 1e-9].sort_values(ascending=False)
    return s if len(s) else None


def figures(R, meta):
    """Return a list of (caption, matplotlib Figure)."""
    figs = []
    gen = R.get("generator_results")

    mix = _by_tech(gen, "GWh")
    if mix is not None:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(mix.index, mix.values, color=[_color(t) for t in mix.index])
        ax.set_ylabel("Generation (GWh, representative periods)")
        ax.set_title("Generation mix by technology")
        ax.tick_params(axis="x", rotation=35)
        for lbl in ax.get_xticklabels():
            lbl.set_ha("right")
        figs.append(("Generation by technology over the representative periods "
                     "(not annualised — Sub_Weights vary by period).", fig))

    cap = _by_tech(gen, "Total_MW")
    if cap is not None:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(cap.index, cap.values, color=[_color(t) for t in cap.index])
        ax.set_ylabel("Capacity (MW)")
        ax.set_title("Installed capacity by technology")
        ax.tick_params(axis="x", rotation=35)
        for lbl in ax.get_xticklabels():
            lbl.set_ha("right")
        figs.append(("Installed capacity by technology (post-solve).", fig))

    cost = R.get("cost_results")
    if cost is not None and len(cost):
        row = cost.iloc[0]
        items = [(c.replace("_", " "), float(_num(pd.Series([row[c]])).fillna(0).iloc[0]))
                 for c in cost.columns if c != "Total_Costs"]
        items = [(k, v) for k, v in items if abs(v) > 1e-9]
        if items:
            fig, ax = plt.subplots(figsize=(7, 4))
            ks, vs = zip(*sorted(items, key=lambda kv: kv[1], reverse=True))
            ax.barh(list(ks)[::-1], list(vs)[::-1], color="#5b8def")
            ax.set_xlabel("Cost (M$)")
            ax.set_title("Cost breakdown")
            figs.append(("System cost decomposition (M$/yr).", fig))

    rel = R.get("reliability_results")
    if rel is not None and len(rel) > 1 and "NSE_Percent_of_Demand" in rel:
        fig, ax = plt.subplots(figsize=(7, 4))
        labels = [str(z) if not str(n).strip() else f"{z}:{n}"
                  for z, n in zip(rel["Zone"], rel.get("Zone_Name", rel["Zone"]))]
        ax.bar(labels, _num(rel["NSE_Percent_of_Demand"]), color="#e15759")
        ax.set_ylabel("Unserved (% of zone demand)")
        ax.set_title("Per-zone reliability shortfall")
        ax.tick_params(axis="x", rotation=35)
        for lbl in ax.get_xticklabels():
            lbl.set_ha("right")
        figs.append(("Unserved energy share by zone (dispatch / reliability run).", fig))
    return figs


def _tables(R):
    """Key tables as (title, DataFrame) for the report body."""
    out = []
    rel = R.get("reliability_results")
    if rel is not None and len(rel):
        cols = [c for c in ["Zone", "Zone_Name", "Total_NSE_MWh", "NSE_Percent_of_Demand",
                            "LOLE_hours", "Peak_Shortage_MW"] if c in rel.columns]
        out.append(("Per-zone reliability", rel[cols].round(2)))
    gen = R.get("generator_results")
    if gen is not None and "GWh" in gen.columns and "technology" in gen.columns:
        t = gen.assign(GWh=_num(gen["GWh"]), MW=_num(gen.get("Total_MW", 0))) \
               .groupby("technology").agg(Capacity_MW=("MW", "sum"), Generation_GWh=("GWh", "sum"))
        t = t[(t.abs() > 1e-6).any(axis=1)].sort_values("Generation_GWh", ascending=False)
        out.append(("Capacity & generation by technology", t.round(1).reset_index()))
    return out


HTML_TMPL = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Garuda report — {{ name }}</title>
<style>
 :root{ --ink:#1a2233; --muted:#62708a; --line:#e3e8f0; --accent:#2f6df6; --bg:#fff; }
 *{box-sizing:border-box} body{font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
   color:var(--ink);max-width:980px;margin:0 auto;padding:32px 24px;background:var(--bg)}
 h1{font-size:26px;margin:0 0 2px} h2{font-size:18px;margin:34px 0 12px;border-bottom:1px solid var(--line);padding-bottom:6px}
 .sub{color:var(--muted);margin:0 0 18px}
 .cards{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}
 .card{flex:1 1 150px;border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:#fafbfe}
 .card .v{font-size:22px;font-weight:650} .card .u{color:var(--muted);font-size:13px} .card .l{color:var(--muted);font-size:12px;margin-top:4px}
 figure{margin:18px 0} figure img{max-width:100%;border:1px solid var(--line);border-radius:8px}
 figcaption{color:var(--muted);font-size:13px;margin-top:6px}
 table{border-collapse:collapse;width:100%;font-size:13.5px;margin:8px 0}
 th,td{border:1px solid var(--line);padding:6px 9px;text-align:right} th{background:#f3f6fc;text-align:right}
 td:first-child,th:first-child{text-align:left}
 footer{color:var(--muted);font-size:12px;margin-top:40px;border-top:1px solid var(--line);padding-top:12px}
</style></head><body>
<h1>{{ title }}</h1>
<p class="sub">{{ subtitle }}</p>
<div class="cards">
{% for c in cards %}<div class="card"><div class="v">{{ c.value }} <span class="u">{{ c.unit }}</span></div><div class="l">{{ c.label }}</div></div>{% endfor %}
</div>
{% for cap, img in figures %}<figure><img src="data:image/png;base64,{{ img }}"><figcaption>{{ cap }}</figcaption></figure>{% endfor %}
{% for title, html in tables %}<h2>{{ title }}</h2>{{ html|safe }}{% endfor %}
<footer>Generated by Garuda <code>tools/report.py</code> from {{ name }}. Cost (M$/yr), CO₂, RE share, demand and unserved energy are annualised over the representative periods; the generation-mix chart shows the representative-period sum (Sub_Weights vary, so it is not annualised).</footer>
</body></html>"""


CARD_ORDER = ["cost", "co2", "re", "demand", "served", "unserved", "unserved_pct"]


def render_html(R, meta, out_path, ad_gwh=None):
    from jinja2 import Template
    m = metrics(R, ad_gwh)
    figs = [(cap, _fig_to_b64(fig)) for cap, fig in figures(R, meta)]
    cards = []
    for k in CARD_ORDER:
        if k in m:
            v, u, lbl = m[k]
            cards.append(dict(value=f"{v:,.1f}", unit=u, label=lbl))
    tables = [(t, df.to_html(index=False, border=0)) for t, df in _tables(R)]
    eng = "dispatch / reliability" if "reliability_results" in R else "capacity expansion"
    title = f"{meta['scenario'] or 'scenario'} · {meta['island'] or meta['name']} · {meta['year']}".strip(" ·")
    subtitle = f"{meta['clean']} case · {eng} run · folder {meta['name']}"
    html = Template(HTML_TMPL).render(title=title, subtitle=subtitle, name=meta["name"],
                                      cards=cards, figures=figs, tables=tables)
    with open(out_path, "w") as fh:
        fh.write(html)
    return out_path


def render_pdf(R, meta, out_path, html_path=None, ad_gwh=None):
    # Prefer weasyprint (renders the HTML we already built) for visual fidelity;
    # fall back to a self-contained matplotlib PdfPages so a PDF always exists.
    if html_path and os.path.isfile(html_path):
        try:
            from weasyprint import HTML  # type: ignore
            HTML(html_path).write_pdf(out_path)
            return out_path, "weasyprint"
        except Exception:
            pass

    m = metrics(R, ad_gwh)
    figs = figures(R, meta)
    with PdfPages(out_path) as pdf:
        # cover page: title + metric grid
        fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
        fig.text(0.07, 0.93, f"Garuda — {meta['scenario']} {meta['island']} {meta['year']}".strip(),
                 fontsize=20, fontweight="bold")
        fig.text(0.07, 0.905, f"{meta['clean']} case · folder {meta['name']}", fontsize=11, color="#555")
        y = 0.84
        for k in CARD_ORDER:
            if k in m:
                v, u, lbl = m[k]
                fig.text(0.09, y, f"{lbl}", fontsize=12, color="#555")
                fig.text(0.62, y, f"{v:,.1f} {u}", fontsize=13, fontweight="bold")
                y -= 0.045
        pdf.savefig(fig)
        plt.close(fig)
        # one chart per page
        for cap, f in figs:
            f.set_size_inches(8.27, 5.5)
            f.text(0.5, 0.01, cap, ha="center", fontsize=9, color="#666")
            pdf.savefig(f)
            plt.close(f)
        # key tables
        for title, df in _tables(R):
            fig, ax = plt.subplots(figsize=(8.27, min(11, 1 + 0.3 * len(df))))
            ax.axis("off")
            ax.set_title(title, loc="left", fontsize=13, fontweight="bold")
            tbl = ax.table(cellText=df.values, colLabels=df.columns, loc="upper center", cellLoc="center")
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(8)
            tbl.scale(1, 1.3)
            pdf.savefig(fig)
            plt.close(fig)
    return out_path, "matplotlib"


def main(argv):
    ap = argparse.ArgumentParser(description="Generate an HTML+PDF report from a garuda results folder.")
    ap.add_argument("results_dir")
    ap.add_argument("--html", help="HTML output path (default: <results_dir>/report.html)")
    ap.add_argument("--pdf", help="PDF output path (default: <results_dir>/report.pdf)")
    ap.add_argument("--no-pdf", action="store_true", help="skip the PDF")
    ap.add_argument("--input-folder", help="input data folder for exact annual demand "
                    "(default: auto-locate data_indonesia/<year>/<island>)")
    ap.add_argument("--open", action="store_true", help="open the HTML when done")
    args = ap.parse_args(argv[1:])

    if not os.path.isdir(args.results_dir):
        print(f"results folder not found: {args.results_dir}", file=sys.stderr)
        return 2
    R = load_results(args.results_dir)
    if not R:
        print(f"no result CSVs in {args.results_dir}", file=sys.stderr)
        return 1
    meta = parse_scenario(args.results_dir)
    ad = annual_demand_gwh(meta, args.input_folder)
    if ad is None:
        print("  note: input demand.csv not found — annual demand/served/share omitted "
              "(pass --input-folder to enable)", file=sys.stderr)

    html_path = args.html or os.path.join(args.results_dir, "report.html")
    render_html(R, meta, html_path, ad_gwh=ad)
    print(f"wrote {html_path}")

    if not args.no_pdf:
        pdf_path = args.pdf or os.path.join(args.results_dir, "report.pdf")
        path, engine = render_pdf(R, meta, pdf_path, html_path=html_path, ad_gwh=ad)
        print(f"wrote {path}  (via {engine})")

    if args.open:
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(html_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
