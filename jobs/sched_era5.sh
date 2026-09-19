#!/usr/bin/env bash
# The ERA5 study: the full Timor regime chain re-run on real (ERA5 reanalysis)
# solar weather instead of the synthetic clear-sky profile. These runs are the
# numbers of record for the IESR technical brief.
#
# Why a chain and not a batch. Every regime number depends on the one before it:
# the carbon-neutral cap is measured on the islanded run; the connection
# patterns are found on a 2-week reduced model; the patterns are then priced
# exactly on the full 8-week model (fix-and-verify). With real weather the
# islanded plan burns more diesel, so the cap moves, the patterns may move, and
# the whole chain has to be redone. Five stages, 12 solves, 2 dataset builds:
#
#   stage 0  build data_indonesia/2030/timor__marketfix_era5     (tools.ntt.wire_era5_solar)
#            build data_indonesia/2030/timor__marketfix_era5_2w  (tools/make_reduced_weeks.py)
#   stage 1  e5_village          islanded, full model, free duration     -> village_timor__marketfix_era5_2030_reference
#            e5_village_4h       islanded, battery fixed 4 h             -> ..._reference__bd4h
#            e5_village_2h       islanded, battery fixed 2 h             -> ..._reference__bd2h
#            => carbon-neutral caps for stage 3/4 measured here (CO2 x1.005, RE share -0.005)
#   stage 2  e5_w2_village       islanded on the 2-week model            -> village_timor__marketfix_era5_2w_2030_reference
#            => caps for the 2-week clean search measured here
#            e5_w2_gridvillage   2-week MILP, unconstrained, mipgap 1e-3, 4 h cap  -> gridvillage_..._2w_2030_reference
#            e5_w2c_gridvillage  2-week MILP, carbon-neutral                       -> gridvillage_..._2w_2030_clean
#   stage 3  e5_fv_gridvillage         unconstrained pattern priced on the full model  -> gridvillage_..._2030_reference__fixverify
#            e5_fv_clean_gridvillage   carbon-neutral pattern priced on the full model -> gridvillage_..._2030_clean__fixverify
#   stage 4  e5_fv_*_4h          both patterns at a 4 h battery              -> ...__fixverify_bd4h
#            e5_fv_*_tb          both patterns with a $0.01/MWh import       -> ...__fixverify_tb
#                                tie-breaker (makes the per-village trade split unique;
#                                the summary nets the ~$6k charge back out)
#
# Everything except the two 2-week MILPs is an LP (village legs have no
# binaries; fix-and-verify legs have every wire decision fixed). Full-model LPs
# run 20-30 min at 52-58 GB; the 2-week MILPs run to their 4 h caps at ~15 GB.
# Two solves at a time. Expect ~9-10 h end to end.
#
# The clean configs are committed with the synthetic-era placeholders
# (656,500 t / 0.48); this script overwrites them with the ERA5-measured values
# before they launch and logs both.
#
# Run from the worktree root on the server:
#   nohup bash jobs/sched_era5.sh > jobs/sched_era5.log 2>&1 &
set -u
cd /home/pwrlabadmin/garuda/.claude/worktrees/repo-orientation-sync-bd6b46
export GRB_LICENSE_FILE=/home/pwrlabadmin/gurobi.lic
ERA5_CF=/home/pwrlabadmin/village-indonesia-100gw/solar_era5/village_solar_cf_hourly.csv
FULL=timor__marketfix_era5
W2=timor__marketfix_era5_2w
MAXPAR=2

log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*"; }
free_gb() { free -g | awk 'NR==2{print $7}'; }
die() { log "ABORT: $*"; exit 1; }

# run_stage <min_free_gb> <job> [job ...]  — launch up to MAXPAR at once, then wait
run_stage() {
  local gate=$1; shift
  for job in "$@"; do
    [ -f "jobs/$job/config.json" ] || die "missing jobs/$job/config.json"
    while [ "$(jobs -rp | wc -l)" -ge "$MAXPAR" ] || [ "$(free_gb)" -lt "$gate" ]; do sleep 60; done
    log "LAUNCH $job ($(free_gb)GB free)"
    ( timeout 5h julia --project=. run_model.jl \
        --config "jobs/$job/config.json" > "jobs/$job/solve.log" 2>&1
      log "END $job rc=$?" ) &
    sleep 180
  done
  wait
}

# set_caps <islanded_results_dir> <config> [config ...] — CO2 cap = measured x1.005,
# RE floor = measured share - 0.005 (floored to 3 d.p.), written into each config
set_caps() {
  local src=$1; shift
  [ -f "$src/clean_energy_results.csv" ] || die "no clean_energy_results.csv in $src"
  python3 - "$src" "$@" <<'PYEOF'
import json, math, sys
import pandas as pd
src, cfgs = sys.argv[1], sys.argv[2:]
e = pd.read_csv(f"{src}/clean_energy_results.csv").iloc[0]
co2 = round(float(e.CO2_Emissions) * 1.005, 1)
re = math.floor((float(e.System_REShare) - 0.005) * 1000) / 1000
print(f"  measured on {src}: CO2 {float(e.CO2_Emissions):,.1f} t, RE share {float(e.System_REShare):.4f}"
      f"  ->  CO2_limit {co2:,.1f}, RE_limit {re:.3f}")
for p in cfgs:
    c = json.load(open(p)); c["CO2_limit"] = co2; c["RE_limit"] = re
    json.dump(c, open(p, "w"), indent=2); open(p, "a").write("\n")
    print(f"  wrote {p}")
PYEOF
}

# ---- stage 0: datasets ------------------------------------------------------
[ -f "$ERA5_CF" ] || die "ERA5 CF file not found at $ERA5_CF"
if [ ! -d "data_indonesia/2030/$FULL" ]; then
  log "BUILD $FULL"
  python3 -m tools.ntt.wire_era5_solar --cf "$ERA5_CF" \
    --dataset data_indonesia/2030/timor__marketfix --out-dataset "$FULL" || die "ERA5 dataset build failed"
fi
if [ ! -d "data_indonesia/2030/$W2" ]; then
  log "BUILD $W2"
  python3 tools/make_reduced_weeks.py "data_indonesia/2030/$FULL" --suffix _2w || die "2-week dataset build failed"
fi

# ---- stage 1: islanded, full model -----------------------------------------
log "STAGE 1 — islanded full-model LPs"
run_stage 75 e5_village e5_village_4h e5_village_2h
log "caps for the full-model clean legs:"
set_caps "results/village_${FULL}_2030_reference" \
  jobs/e5_fv_clean_gridvillage/config.json \
  jobs/e5_fv_clean_gridvillage_4h/config.json \
  jobs/e5_fv_clean_gridvillage_tb/config.json

# ---- stage 2: 2-week search --------------------------------------------------
log "STAGE 2 — 2-week islanded LP, then the two pattern-search MILPs"
run_stage 40 e5_w2_village
log "caps for the 2-week clean search:"
set_caps "results/village_${W2}_2030_reference" jobs/e5_w2c_gridvillage/config.json
run_stage 40 e5_w2_gridvillage e5_w2c_gridvillage
for j in e5_w2_gridvillage e5_w2c_gridvillage; do
  grep -E "Best objective|Optimal solution|reached the time" "jobs/$j/solve.log" | tail -1 | sed "s/^/  $j: /"
done

# ---- stage 3: fix-and-verify -------------------------------------------------
log "STAGE 3 — fix-and-verify on the full model"
for pair in "gridvillage_${W2}_2030_reference:e5_fv_gridvillage" "gridvillage_${W2}_2030_clean:e5_fv_clean_gridvillage"; do
  src="results/${pair%%:*}/site_connection_results.csv"; dst="jobs/${pair##*:}/connect_pattern.csv"
  [ -f "$src" ] || die "no connection pattern at $src (did the 2-week MILP write results?)"
  cp "$src" "$dst"
  log "pattern ${pair##*:}: $(python3 -c "import pandas as pd; print(int(pd.read_csv('$dst').Connected.sum()))")/780 connected"
done
run_stage 75 e5_fv_gridvillage e5_fv_clean_gridvillage

# ---- stage 4: variants on the fixed patterns ---------------------------------
log "STAGE 4 — 4 h battery and trade tie-breaker on the fixed patterns"
run_stage 75 e5_fv_gridvillage_4h e5_fv_clean_gridvillage_4h e5_fv_gridvillage_tb e5_fv_clean_gridvillage_tb
log "all solves complete"

# ---- summary -----------------------------------------------------------------
python3 - "$FULL" "$W2" <<'PYEOF'
import os, sys
import numpy as np
import pandas as pd
FULL, W2 = sys.argv[1], sys.argv[2]
R = "results"
TIEBREAK = 0.01
man = pd.read_csv("data_indonesia/2030/timor/timor_villages_manifest.csv").set_index("Village")

def load(d):
    if not os.path.exists(f"{d}/cost_results.csv"):
        return None
    o = {}
    o["cost"] = float(pd.read_csv(f"{d}/cost_results.csv").Total_Costs.iloc[0])
    e = pd.read_csv(f"{d}/clean_energy_results.csv").iloc[0]
    o["co2"] = float(e.CO2_Emissions); o["re"] = float(e.System_REShare)
    g = pd.read_csv(f"{d}/site_generator_results.csv"); s = pd.read_csv(f"{d}/site_storage_results.csv")
    n = pd.read_csv(f"{d}/site_connection_results.csv")
    sol = g[g.technology.str.contains("solar", case=False)].groupby("Village").Total_MW.sum()
    bp = g[g.technology.str.contains("batt", case=False)].groupby("Village").Total_MW.sum()
    be = s.groupby("Village").Total_Storage_MWh.sum().reindex(sol.index).fillna(0)
    pk = man.peak_mw.reindex(sol.index)
    o["solar_mw"] = sol.sum(); o["batt_mwh"] = be.sum(); o["batt_mw"] = bp.sum()
    o["solar_pk"] = (sol / pk).median(); o["mwh_pk"] = (be / pk).median()
    o["dur"] = (be / bp.reindex(be.index).replace(0, np.nan)).median()
    o["n_solar"] = int((sol > 1e-3).sum())
    dsl = g[g.technology.str.contains("diesel", case=False)].Electricity_GWh.sum()
    gen = g[~g.technology.str.contains("batt", case=False)].Electricity_GWh.sum()
    o["diesel_pct"] = 100 * dsl / gen if gen else float("nan")
    o["diesel_mw"] = g[g.technology.str.contains("diesel", case=False)].Total_MW.sum()
    o["connected"] = int(n.Connected.sum())
    o["imp"] = n.Total_Import_MWh.sum(); o["exp"] = n.Total_Export_MWh.sum()
    o["net_grid_gwh"] = (o["imp"] - o["exp"]) / 1e3
    if d.endswith("__fixverify_tb"):
        o["cost"] -= o["imp"] * TIEBREAK / 1e6
    return o

print("\n== Regime trio, full 8-week model, ERA5 weather ==")
trio = [("islanded", f"{R}/village_{FULL}_2030_reference"),
        ("coordinated, unconstrained", f"{R}/gridvillage_{FULL}_2030_reference__fixverify"),
        ("coordinated, carbon-neutral", f"{R}/gridvillage_{FULL}_2030_clean__fixverify")]
base = load(trio[0][1])
print(f"{'regime':30s} {'cost $M':>9s} {'coord $M':>9s} {'CO2 kt':>8s} {'RE':>6s} {'solar MW':>9s} {'batt MWh':>9s} {'conn':>5s} {'net grid GWh':>13s} {'diesel %':>9s}")
for label, d in trio:
    o = load(d)
    if o is None: print(f"{label:30s} (missing)"); continue
    cv = base["cost"] - o["cost"] if base and label != "islanded" else float("nan")
    print(f"{label:30s} {o['cost']:9.3f} {cv:9.3f} {o['co2']/1e3:8.1f} {o['re']:6.3f} {o['solar_mw']:9.1f} {o['batt_mwh']:9.0f} {o['connected']:5d} {o['net_grid_gwh']:13.1f} {o['diesel_pct']:9.1f}")

print("\n== The kit (islanded, per MW of village peak) and its duration sensitivity ==")
print(f"{'run':30s} {'cost $M':>9s} {'d cost':>8s} {'solar/pk':>9s} {'MWh/pk':>7s} {'dur h':>6s} {'solar MW':>9s} {'batt MW':>8s} {'batt MWh':>9s} {'diesel MW':>10s} {'diesel %':>9s}")
for label, d in [("islanded, free duration", f"{R}/village_{FULL}_2030_reference"),
                 ("islanded, 4 h", f"{R}/village_{FULL}_2030_reference__bd4h"),
                 ("islanded, 2 h", f"{R}/village_{FULL}_2030_reference__bd2h")]:
    o = load(d)
    if o is None or base is None: print(f"{label:30s} (missing)"); continue
    print(f"{label:30s} {o['cost']:9.3f} {o['cost']-base['cost']:+8.3f} {o['solar_pk']:9.2f} {o['mwh_pk']:7.2f} {o['dur']:6.2f} "
          f"{o['solar_mw']:9.1f} {o['batt_mw']:8.1f} {o['batt_mwh']:9.0f} {o['diesel_mw']:10.1f} {o['diesel_pct']:9.1f}")

print("\n== Fix-and-verify variants (delta against the free-duration, untied leg of the same regime) ==")
for leg, key in (("reference", "unconstrained"), ("clean", "carbon-neutral")):
    a = load(f"{R}/gridvillage_{FULL}_2030_{leg}__fixverify")
    for tag, label in (("bd4h", "4 h battery"), ("tb", "tie-breaker (charge netted out)")):
        o = load(f"{R}/gridvillage_{FULL}_2030_{leg}__fixverify_{tag}")
        if a is None or o is None: print(f"  {key}, {label}: (missing)"); continue
        print(f"  {key:15s} {label:32s} cost {o['cost']:9.3f} ({o['cost']-a['cost']:+.3f}); "
              f"connected {o['connected']} vs {a['connected']}; solar {o['solar_mw']:.1f} vs {a['solar_mw']:.1f} MW; "
              f"batt {o['batt_mwh']:.0f} vs {a['batt_mwh']:.0f} MWh; net grid {o['net_grid_gwh']:.1f} vs {a['net_grid_gwh']:.1f} GWh; "
              f"gross import {o['imp']/1e3:.1f} vs {a['imp']/1e3:.1f} GWh")

print("\n== 2-week search: achieved gaps (quote these, never the permitted mipgap) ==")
for j in ("e5_w2_gridvillage", "e5_w2c_gridvillage"):
    p = f"jobs/{j}/solve.log"
    if os.path.exists(p):
        lines = [l.strip() for l in open(p) if "Best objective" in l or "Optimal solution" in l or "reached the time" in l]
        print(f"  {j}: {lines[-1] if lines else '(no solver status line)'}")
print("\nCoordination values are OFF minus ON on the same dataset and duration; the fix-and-verify legs are exact LPs "
      "for their pattern, so each value is a floor on the true coordination value.")
PYEOF
