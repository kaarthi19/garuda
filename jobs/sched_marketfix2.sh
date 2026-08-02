#!/usr/bin/env bash
# Memory-aware parallel scheduler for the 4 cost-corrected A1b solves.
#
# Launches as many concurrently as RAM allows instead of running them serially.
# Measured peaks: 780-village timor solve 51.9 GB; timor__market solve 58.3 GB
# AT THE ROOT NODE, before branch-and-bound grows the tree. On 187 GB total that
# caps real concurrency at 2 market solves (116 GB, 71 GB headroom). Four at once
# would need 232 GB and be OOM-killed, which surfaces only as `exit code -9`
# after hours of work -- hence the gate rather than a fixed -j 4.
#
# The gate: never launch unless MIN_FREE GB is available, then wait RAMP seconds
# so the new job's JuMP build (~10 min to peak) is reflected before the next check.
set -u
cd /home/pwrlabadmin/garuda/.claude/worktrees/repo-orientation-sync-bd6b46
export GRB_LICENSE_FILE=/home/pwrlabadmin/gurobi.lic

MIN_FREE=${MIN_FREE:-75}      # GB required before launching another solve
RAMP=${RAMP:-600}             # s to let a new job reach peak RSS before re-checking
TIMEOUT=${TIMEOUT:-16h}
JOBS=(mf_marketfix_gridvillage mf_marketfixnf_gridvillage
      mf_marketfixnf_village)

log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*"; }
avail() { free -g | awk 'NR==2{print $7}'; }

log "scheduler start: ${#JOBS[@]} jobs, MIN_FREE=${MIN_FREE}GB, ramp=${RAMP}s, timeout=${TIMEOUT}"

for job in "${JOBS[@]}"; do
  while [ "$(avail)" -lt "$MIN_FREE" ]; do
    log "  waiting: $(avail)GB free, need ${MIN_FREE}GB"
    sleep 60
  done
  log "LAUNCH $job ($(avail)GB free)"
  ( start=$SECONDS
    timeout "$TIMEOUT" julia --project=. run_model.jl \
        --config "jobs/$job/config.json" > "jobs/$job/solve.log" 2>&1
    rc=$?; dur=$(( SECONDS - start ))
    if [ $rc -eq 124 ]; then
      log "END $job TIMED OUT after $((dur/60))m"
    elif [ $rc -ne 0 ]; then
      log "END $job FAILED rc=$rc after $((dur/60))m (rc=-9/137 => OOM-killed)"
    else
      log "END $job ok after $((dur/60))m"
    fi
  ) &
  sleep "$RAMP"
done

log "all launched; waiting for completion"
wait
log "all solves finished"

# ---- validity gate + per-village summaries -------------------------------
for ds in marketfix marketfixnf; do
  python3 - "$ds" <<'PY'
import sys, os, pandas as pd
ds=sys.argv[1]; isl=f"timor__{ds}"
def cost(sc):
    p=f"results/{sc}_{isl}_2030_reference/cost_results.csv"
    return pd.read_csv(p).Total_Costs[0] if os.path.exists(p) else None
off,on = cost("village"), cost("gridvillage")
print(f"\n=== {isl} ===")
if off is None or on is None:
    print(f"  incomplete: village={off} gridvillage={on}")
else:
    bad = on > off + 1e-9
    print(f"  village(OFF)     {off:.6f} $M/yr")
    print(f"  gridvillage(ON)  {on:.6f} $M/yr")
    print(f"  coordination     {(off-on)*1e6:,.0f} $/yr" +
          ("   *** INVALID: ON > OFF => suboptimal incumbent ***" if bad else ""))
PY
  for sc in village gridvillage; do
    d="results/${sc}_timor__${ds}_2030_reference"
    [ -d "$d" ] && [ -n "$(ls -A "$d" 2>/dev/null)" ] && \
      python3 tools/village_build_summary.py "$d" --top 0 2>/dev/null | sed 's/^/  /'
  done
done

log "scheduler complete"
