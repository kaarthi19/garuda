#!/usr/bin/env bash
# Battery-duration and weather sensitivities on the islanded kit, plus the two
# fix-and-verify legs re-priced at a 4 h battery and with a trade tie-breaker.
# All seven solves are LPs
# (village legs have no binaries; the gridvillage legs have every wire decision
# fixed by connect_pattern), so each is ~15-30 min of barrier at 52-58 GB.
#
#   jobs/bd_village_4h            islanded, battery fixed at 4 h   -> village_timor__marketfix_2030_reference__bd4h
#   jobs/bd_village_2h            islanded, battery fixed at 2 h   -> village_timor__marketfix_2030_reference__bd2h
#   jobs/bd4h_fv_marketfix_gridvillage   733-village pattern, 4 h  -> gridvillage_timor__marketfix_2030_reference__fixverify_bd4h
#   jobs/bd4h_fv_clean_gridvillage       450-village pattern, 4 h  -> gridvillage_timor__marketfix_2030_clean__fixverify_bd4h
#   jobs/era5_village             islanded, ERA5 weather, free duration -> village_timor__marketfix_era5_2030_reference__era5
#   jobs/tb_fv_marketfix_gridvillage     733-village pattern, import_price 0.01 $/MWh tie-breaker
#                                        -> gridvillage_timor__marketfix_2030_reference__fixverify_tb
#   jobs/tb_fv_clean_gridvillage         450-village pattern, same tie-breaker
#                                        -> gridvillage_timor__marketfix_2030_clean__fixverify_tb
#
# The tie-breaker legs address the trade-allocation degeneracy at 0/0 prices:
# a $0.01/MWh import charge (about $6k on a ~$100 M objective) makes the
# per-village import/export split unique without changing the plan. The summary
# nets the charge back out (Total_Import_MWh x 0.01) before comparing to the
# anchors; the connection pattern, builds and net flows should be unchanged.
#
# Anchors to compare against (RUN_LOG 2026-09-14): islanded 101.717594,
# fix-and-verify reference 77.758726, fix-and-verify clean 98.872226 $M/yr.
# The 4 h islanded penalty is bounded above at $1.81 M/yr (same 825 MWh, more MW).
#
# Run from the repo root on the server:
#   nohup bash jobs/sched_bd4h.sh > jobs/sched_bd4h.log 2>&1 &
set -u
cd /home/pwrlabadmin/garuda/.claude/worktrees/repo-orientation-sync-bd6b46
export GRB_LICENSE_FILE=/home/pwrlabadmin/gurobi.lic
ERA5_CF=/home/pwrlabadmin/village-indonesia-100gw/solar_era5/village_solar_cf_hourly.csv
log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*"; }
free_gb() { free -g | awk 'NR==2{print $7}'; }

# 0. Derived dataset for the ERA5 leg (seconds; gitignored via *__*). Slices the
#    ERA5 hourly CFs to timor__marketfix's own representative weeks and writes
#    them at each solar unit's R_ID position. Never modifies the source.
if [ ! -d data_indonesia/2030/timor__marketfix_era5 ]; then
  if [ -f "$ERA5_CF" ]; then
    log "BUILD timor__marketfix_era5"
    python3 -m tools.ntt.wire_era5_solar --cf "$ERA5_CF" \
      --dataset data_indonesia/2030/timor__marketfix \
      --out-dataset timor__marketfix_era5 || log "ERA5 build FAILED — era5_village will be skipped"
  else
    log "ERA5 CF file not found at $ERA5_CF — era5_village will be skipped"
  fi
fi

# 1. Solves, at most two concurrent (memory-gated at 75 GB free, per the
#    measured 52-58 GB peaks). Order: the cheap kit sensitivities first.
JOBS="bd_village_4h bd_village_2h bd4h_fv_marketfix_gridvillage bd4h_fv_clean_gridvillage tb_fv_marketfix_gridvillage tb_fv_clean_gridvillage"
[ -d data_indonesia/2030/timor__marketfix_era5 ] && JOBS="$JOBS era5_village"
for job in $JOBS; do
  while [ "$(free_gb)" -lt 75 ]; do sleep 60; done
  log "LAUNCH $job ($(free_gb)GB free)"
  ( timeout 5h julia --project=. run_model.jl \
      --config "jobs/$job/config.json" > "jobs/$job/solve.log" 2>&1
    log "END $job rc=$?" ) &
  sleep 180
done
wait
log "all solves complete"

# 2. Summary: cost against the anchors, and the kit per MW of village peak.
python3 - <<'PYEOF'
import os
import numpy as np
import pandas as pd

ANCHOR = {"village": 101.717594, "gridvillage_reference": 77.758726, "gridvillage_clean": 98.872226}
RUNS = [
    ("islanded, free duration (anchor)", "results/village_timor__marketfix_2030_reference__ucrelax", "village"),
    ("islanded, 4 h",                    "results/village_timor__marketfix_2030_reference__bd4h",    "village"),
    ("islanded, 2 h",                    "results/village_timor__marketfix_2030_reference__bd2h",    "village"),
    ("islanded, ERA5 weather",           "results/village_timor__marketfix_era5_2030_reference__era5", "village"),
    ("coordinated unconstrained, 4 h",   "results/gridvillage_timor__marketfix_2030_reference__fixverify_bd4h", "gridvillage_reference"),
    ("coordinated carbon-neutral, 4 h",  "results/gridvillage_timor__marketfix_2030_clean__fixverify_bd4h",    "gridvillage_clean"),
    ("coordinated unconstrained, tie-br", "results/gridvillage_timor__marketfix_2030_reference__fixverify_tb", "gridvillage_reference"),
    ("coordinated carbon-neutral, tie-br","results/gridvillage_timor__marketfix_2030_clean__fixverify_tb",    "gridvillage_clean"),
]
TIEBREAK = 0.01  # $/MWh import charge on the tie-breaker legs, netted out below
man = pd.read_csv("data_indonesia/2030/timor/timor_villages_manifest.csv").set_index("Village")
print(f"\n{'run':36s} {'cost $M':>10s} {'vs anchor':>10s} {'solar/pk':>9s} {'MWh/pk':>7s} {'dur h':>6s} {'solar MW':>9s} {'batt MWh':>9s} {'diesel %':>9s}")
for label, d, key in RUNS:
    if not os.path.exists(f"{d}/cost_results.csv"):
        print(f"{label:36s} {'(missing)':>10s}"); continue
    cost = float(pd.read_csv(f"{d}/cost_results.csv").Total_Costs.iloc[0])
    if d.endswith("__fixverify_tb"):
        imp = pd.read_csv(f"{d}/site_connection_results.csv").Total_Import_MWh.sum()
        cost -= imp * TIEBREAK / 1e6   # remove the tie-breaker charge; compare like with like
    g = pd.read_csv(f"{d}/site_generator_results.csv"); s = pd.read_csv(f"{d}/site_storage_results.csv")
    sol = g[g.technology.str.contains("solar", case=False)].groupby("Village").Total_MW.sum()
    bp = g[g.technology.str.contains("batt", case=False)].groupby("Village").Total_MW.sum()
    be = s.groupby("Village").Total_Storage_MWh.sum()
    dsl = g[g.technology.str.contains("diesel", case=False)].Electricity_GWh.sum()
    gen = g[~g.technology.str.contains("batt", case=False)].Electricity_GWh.sum()
    pk = man.peak_mw.reindex(sol.index)
    dur = (be / bp.replace(0, np.nan)).median()
    print(f"{label:36s} {cost:10.4f} {cost-ANCHOR[key]:+10.4f} {(sol/pk).median():9.2f} "
          f"{(be.reindex(pk.index)/pk).median():7.2f} {dur:6.2f} {sol.sum():9.1f} {be.sum():9.0f} {100*dsl/gen:9.1f}")
print("\n'vs anchor' is the cost delta against the free-duration run of the same regime; "
      "coordination values are OFF minus ON within the same duration. Tie-breaker rows have the "
      "$0.01/MWh import charge netted out and should sit within ~$0.01 M of their anchor.")

# Tie-breaker check: same pattern, same builds, now-determinate trade split.
for leg, anchor in (("reference", "results/gridvillage_timor__marketfix_2030_reference__fixverify"),
                    ("clean", "results/gridvillage_timor__marketfix_2030_clean__fixverify")):
    tb = f"results/gridvillage_timor__marketfix_2030_{leg}__fixverify_tb"
    if not (os.path.exists(f"{tb}/site_connection_results.csv") and os.path.exists(f"{anchor}/site_connection_results.csv")):
        continue
    a = pd.read_csv(f"{anchor}/site_connection_results.csv").set_index("ID")
    b = pd.read_csv(f"{tb}/site_connection_results.csv").set_index("ID")
    ga = pd.read_csv(f"{anchor}/site_generator_results.csv").groupby("Village").Total_MW.sum()
    gb = pd.read_csv(f"{tb}/site_generator_results.csv").groupby("Village").Total_MW.sum()
    print(f"\ntie-breaker vs anchor ({leg}): connected {int(b.Connected.sum())} vs {int(a.Connected.sum())}; "
          f"max |dCapacity| per village {float((gb - ga).abs().max()):.4f} MW; "
          f"gross import {b.Total_Import_MWh.sum()/1e3:.1f} vs {a.Total_Import_MWh.sum()/1e3:.1f} GWh; "
          f"net grid supply {(b.Total_Import_MWh.sum()-b.Total_Export_MWh.sum())/1e3:.1f} vs "
          f"{(a.Total_Import_MWh.sum()-a.Total_Export_MWh.sum())/1e3:.1f} GWh")
PYEOF
