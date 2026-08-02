#!/usr/bin/env bash
# A1b re-run on the cost-corrected market datasets (docs/findings_grid_cost_units.md).
#
# 4 solves: village + gridvillage on each of timor__marketfix (costs annualised,
# battery power priced) and timor__marketfixnf (same, plus 24 candidate fossil
# rows zeroed). Each generate_jobs_local.py invocation runs its two legs serially.
#
# Waits for leg 1 (mip1e4_timor, A1a gridvillage at 1e-4) to clear first — it is
# orphaned but still running, and two 780-village solves plus a market solve will
# not fit in 187 GB.
#
# DROPPED from the previous queue: mip1e4_market_village. It targeted the
# UNCORRECTED timor__market, which we now know charges renewables ~9x their annual
# cost. Tightening the gap on a broken dataset buys nothing.
#
# mipgap stays at 0.01 per the brief ("don't mind the gap, want credible results")
# -- but gap is not purely precision here: at 0.01 the A1a gridvillage run returned
# an incumbent WORSE than the known-feasible all-islanded solution, i.e. a negative
# coordination value. So validity is checked by dominance after each pair, not by
# trusting the "Optimal solution found" banner.
set -u
cd /home/pwrlabadmin/garuda/.claude/worktrees/repo-orientation-sync-bd6b46
export GRB_LICENSE_FILE=/home/pwrlabadmin/gurobi.lic

TIMEOUT=${TIMEOUT:-16h}
log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*"; }
solves_running() { pgrep -f "bin/julia.*run_model" >/dev/null 2>&1; }

log "queue start; waiting for leg 1 (mip1e4_timor) to clear"
while solves_running; do sleep 60; done
log "clear"

for v in marketfix marketfixnf; do
  avail=$(free -g | awk 'NR==2{print $7}')
  if [ "$avail" -lt 70 ]; then log "SKIP $v: only ${avail}GB free"; continue; fi
  log "START $v (2 solves, timeout ${TIMEOUT}, ${avail}GB free)"
  start=$SECONDS
  timeout "$TIMEOUT" python3 generate_jobs_local.py \
      -s "scenario_timor_${v}.yml" -r run_model.jl -o jobs --no-bootstrap \
      > "jobs/stage_${v}.log" 2>&1
  rc=$?; dur=$(( SECONDS - start ))
  log "END $v rc=$rc after $((dur/60))m"

  # validity gate: gridvillage strictly dominates village (all connections off is
  # feasible), so ON must be <= OFF. A violation means the MILP stopped on a
  # suboptimal incumbent and the coordination value is not usable.
  python3 - "$v" <<'PY'
import sys, os, pandas as pd
v=sys.argv[1]; isl=f"timor__{v}"
def cost(sc):
    p=f"results/{sc}_{isl}_2030_reference/cost_results.csv"
    return pd.read_csv(p).Total_Costs[0] if os.path.exists(p) else None
off, on = cost("village"), cost("gridvillage")
if off is None or on is None:
    print(f"    [{isl}] incomplete: village={off} gridvillage={on}")
else:
    cv=(off-on)*1e6
    flag = "  *** INVALID: ON > OFF, suboptimal incumbent ***" if on > off + 1e-9 else ""
    print(f"    [{isl}] village={off:.6f}  gridvillage={on:.6f}  coordination={cv:,.0f} $/yr{flag}")
PY
  for sc in village gridvillage; do
    d="results/${sc}_timor__${v}_2030_reference"
    [ -d "$d" ] && python3 tools/village_build_summary.py "$d" --top 0 2>/dev/null \
        | grep -E "villages|solar built|battery|import|export|connected" | sed 's/^/    /'
  done
  grep -iE "Explored|Best objective|reached the time limit" "jobs/stage_${v}.log" \
      2>/dev/null | tail -4 | sed 's/^/    /'
done

log "queue complete"
