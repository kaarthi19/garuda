#!/usr/bin/env bash
# ERA5 follow-up: close the two gaps the first chain (jobs/sched_era5.sh) left
# on the carbon-neutral leg.
#
# 1. The 2-week clean MILP never left its all-islanded seed (1 node in 4 h, no
#    heuristic incumbent), so the carbon-neutral 4 h and tie-breaker variants
#    priced an EMPTY pattern. Re-run both on the real floor plan, the 450-village
#    pattern (jobs/e5_fv_clean_gridvillage_p450, $97.418 M/yr, exact LP).
# 2. Re-run the 2-week clean search seeded from that same pattern with the new
#    `start_pattern` key (a MIP start, not a fix), at an 8 h cap. Whatever it
#    finds is priced on the full model by fix-and-verify; if it beats p450 the
#    floor rises, and the run's bound tightens the ceiling either way.
#
#   stage A  e5_fv_clean_gridvillage_p450_4h   p450 pattern, 4 h battery       -> gridvillage_timor__marketfix_era5_2030_clean__fixverify_p450_bd4h
#            e5_fv_clean_gridvillage_p450_tb   p450 pattern, $0.01/MWh import  -> ..._clean__fixverify_p450_tb
#   stage B  e5_w2c_gridvillage_seeded         2-week clean MILP, start_pattern = p450, mipgap 1e-3, 8 h cap
#                                              -> gridvillage_timor__marketfix_era5_2w_2030_clean__seeded
#   stage C  e5_fv_clean_gridvillage_seeded    the seeded winner priced on the full model (skipped if the
#                                              winner IS the p450 seed — its price is already known)
#                                              -> ..._clean__fixverify_seeded
#
# Stage A is two ~30 min LPs (52-58 GB each, run together); stage B is one
# MILP to its 8 h cap (~15 GB); stage C one ~30 min LP. Expect ~9.5 h.
#
# Anchors: islanded ERA5 104.575 $M/yr; p450 floor 97.418 (coordination $7.157 M);
# the failed 2-week clean search's root bound 88.102 (2-week islanded 108.674).
#
# Run from the worktree root on the server:
#   nohup bash jobs/sched_era5b.sh > jobs/sched_era5b.log 2>&1 &
set -u
cd /home/pwrlabadmin/garuda/.claude/worktrees/repo-orientation-sync-bd6b46
export GRB_LICENSE_FILE=/home/pwrlabadmin/gurobi.lic
FULL=timor__marketfix_era5
W2=timor__marketfix_era5_2w
MAXPAR=2
P450=jobs/e5_fv_clean_gridvillage_p450/connect_pattern.csv

log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*"; }
free_gb() { free -g | awk 'NR==2{print $7}'; }
die() { log "ABORT: $*"; exit 1; }

run_stage() {
  local gate=$1; shift
  for job in "$@"; do
    [ -f "jobs/$job/config.json" ] || die "missing jobs/$job/config.json"
    while [ "$(jobs -rp | wc -l)" -ge "$MAXPAR" ] || [ "$(free_gb)" -lt "$gate" ]; do sleep 60; done
    log "LAUNCH $job ($(free_gb)GB free)"
    ( timeout 9h julia --project=. run_model.jl \
        --config "jobs/$job/config.json" > "jobs/$job/solve.log" 2>&1
      log "END $job rc=$?" ) &
    sleep 180
  done
  wait
}

[ -f "$P450" ] || die "p450 pattern not found at $P450"
[ -d "data_indonesia/2030/$FULL" ] && [ -d "data_indonesia/2030/$W2" ] || die "ERA5 datasets missing — run jobs/sched_era5.sh first"
# the seeded MILP must see the caps the first chain measured on the 2-week islanded run
python3 - <<'PYEOF'
import json
a = json.load(open("jobs/e5_w2c_gridvillage/config.json")); b = json.load(open("jobs/e5_w2c_gridvillage_seeded/config.json"))
assert a["CO2_limit"] == b["CO2_limit"] and a["RE_limit"] == b["RE_limit"], "seeded config caps differ from the measured 2-week caps"
print(f"  seeded search caps: CO2 {b['CO2_limit']:,.1f} t, RE {b['RE_limit']}; start_pattern {b['start_pattern']}")
PYEOF

# ---- stage A: the p450 variants ----------------------------------------------
log "STAGE A — carbon-neutral 4 h and tie-breaker legs on the p450 pattern"
run_stage 75 e5_fv_clean_gridvillage_p450_4h e5_fv_clean_gridvillage_p450_tb

# ---- stage B: seeded 2-week clean search -------------------------------------
log "STAGE B — 2-week clean MILP seeded from p450 (8 h cap)"
run_stage 40 e5_w2c_gridvillage_seeded
grep -E "Best objective|Optimal solution|reached the time|warm-started|User MIP start" jobs/e5_w2c_gridvillage_seeded/solve.log | sed 's/^/  seeded: /'

# ---- stage C: price the seeded winner on the full model ----------------------
SRC="results/gridvillage_${W2}_2030_clean__seeded/site_connection_results.csv"
[ -f "$SRC" ] || die "seeded search wrote no results at $SRC"
if python3 - "$SRC" "$P450" <<'PYEOF'
import sys, pandas as pd
a = pd.read_csv(sys.argv[1]).set_index("ID").Connected.round().astype(int)
b = pd.read_csv(sys.argv[2]).set_index("ID").Connected.round().astype(int)
diff = int((a != b.reindex(a.index)).sum())
print(f"  seeded winner: {int(a.sum())}/780 connected; differs from p450 in {diff} villages")
sys.exit(0 if diff > 0 else 1)
PYEOF
then
  cp "$SRC" jobs/e5_fv_clean_gridvillage_seeded/connect_pattern.csv
  log "STAGE C — fix-and-verify of the seeded winner"
  run_stage 75 e5_fv_clean_gridvillage_seeded
else
  log "STAGE C skipped — the seeded search returned its own seed; the full-model price is p450's"
fi
log "all solves complete"

# ---- summary -----------------------------------------------------------------
python3 - "$FULL" "$W2" <<'PYEOF'
import os, re, sys
import pandas as pd
FULL, W2 = sys.argv[1], sys.argv[2]
R = "results"; TIEBREAK = 0.01
def load(d, tb=False):
    if not os.path.exists(f"{d}/cost_results.csv"): return None
    c = float(pd.read_csv(f"{d}/cost_results.csv").Total_Costs.iloc[0])
    e = pd.read_csv(f"{d}/clean_energy_results.csv").iloc[0]
    g = pd.read_csv(f"{d}/site_generator_results.csv"); s = pd.read_csv(f"{d}/site_storage_results.csv")
    n = pd.read_csv(f"{d}/site_connection_results.csv")
    sol = g[g.technology.str.contains("solar", case=False)].Total_MW.sum()
    dsl = g[g.technology.str.contains("diesel", case=False)]
    gen = g[~g.technology.str.contains("batt", case=False)].Electricity_GWh.sum()
    imp = n.Total_Import_MWh.sum()
    if tb: c -= imp * TIEBREAK / 1e6
    return dict(cost=c, co2=float(e.CO2_Emissions)/1e3, re=float(e.System_REShare), solar=sol, mwh=s.Total_Storage_MWh.sum(),
                dmw=dsl.Total_MW.sum(), dpct=100*dsl.Electricity_GWh.sum()/gen if gen else float("nan"),
                conn=int(n.Connected.sum()), imp=imp/1e3, net=(imp-n.Total_Export_MWh.sum())/1e3)
isl = load(f"{R}/village_{FULL}_2030_reference")
rows = [("islanded (anchor)",              f"{R}/village_{FULL}_2030_reference", False),
        ("carbon-neutral, p450",           f"{R}/gridvillage_{FULL}_2030_clean__fixverify_p450", False),
        ("carbon-neutral, p450, 4 h",      f"{R}/gridvillage_{FULL}_2030_clean__fixverify_p450_bd4h", False),
        ("carbon-neutral, p450, tie-br",   f"{R}/gridvillage_{FULL}_2030_clean__fixverify_p450_tb", True),
        ("carbon-neutral, seeded winner",  f"{R}/gridvillage_{FULL}_2030_clean__fixverify_seeded", False)]
print(f"\n{'run':32s} {'cost $M':>8s} {'coord':>7s} {'CO2 kt':>7s} {'RE':>6s} {'solar MW':>9s} {'batt MWh':>9s} {'diesel MW':>10s} {'diesel %':>9s} {'conn':>5s} {'gross imp':>10s} {'net GWh':>8s}")
best = None
for label, d, tb in rows:
    o = load(d, tb)
    if o is None: print(f"{label:32s} (missing)"); continue
    cv = isl["cost"] - o["cost"] if isl and "islanded" not in label else float("nan")
    print(f"{label:32s} {o['cost']:8.3f} {cv:7.3f} {o['co2']:7.1f} {o['re']:6.3f} {o['solar']:9.1f} {o['mwh']:9.0f} {o['dmw']:10.1f} {o['dpct']:9.1f} {o['conn']:5d} {o['imp']:10.1f} {o['net']:8.1f}")
    if label in ("carbon-neutral, p450", "carbon-neutral, seeded winner") and (best is None or o["cost"] < best[1]): best = (label, o["cost"])
p = "jobs/e5_w2c_gridvillage_seeded/solve.log"
bound = None
if os.path.exists(p):
    m = [re.search(r"best bound ([0-9.e+]+)", l) for l in open(p) if "best bound" in l]
    m = [x for x in m if x]
    if m: bound = float(m[-1].group(1)) / 1e6
w2_isl = f"{R}/village_{W2}_2030_reference/cost_results.csv"
w2c = float(pd.read_csv(w2_isl).Total_Costs.iloc[0]) if os.path.exists(w2_isl) else None
if best and isl:
    print(f"\nCarbon-neutral coordination value on ERA5: floor ${isl['cost']-best[1]:.3f} M/yr from '{best[0]}' (exact LP)", end="")
    if bound and w2c: print(f"; ceiling ~${w2c-bound:.1f} M/yr from the seeded 2-week root bound ({w2c:.3f} - {bound:.3f})")
    else: print()
print("The tie-breaker row has the $0.01/MWh import charge netted out; its cost, net flow and builds should match p450 and only gross import should fall.")
PYEOF
