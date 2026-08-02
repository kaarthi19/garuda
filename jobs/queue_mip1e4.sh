#!/usr/bin/env bash
# Queued re-runs at mipgap 1e-4.
#
# WHY. At mipgap 0.01 the A1a `gridvillage` run returned $69.545469 M against a
# `village` optimum of $69.134350 M -- an apparent coordination value of
# -$411,118/yr. That is impossible: all-connections-off is feasible for the ON
# problem, so its optimum is <= the OFF cost. Gurobi explored ONE node, hit
# gap 0.8311% < 1%, and stopped on a provably suboptimal incumbent while printing
# "Optimal solution found". Every downstream run that differences against these
# numbers (A3, A5, B1) inherits the defect.
#
# LEGS:
#   1. timor gridvillage        780 binaries (connection only). The invalid run.
#   2. timor__market village     UC binaries. Was 0.1682% gap, not exact.
#
# DROPPED: timor__market gridvillage at 1e-4. Its 0.01 run was killed at 2h32m
# still at the ROOT node -- root relaxation alone took 4193 s and returned a very
# weak bound ($43.13 M), leaving gap 36.2% with 121,767 binaries. If 1% is many
# hours away, 1e-4 is unreachable, so the run would only burn the timeout. A1b's
# coordination value is instead reported as an interval: its killed log gives a
# feasible incumbent of $67.57456 M against a `village` optimum in
# [86.26695, 86.41227], hence coordination value >= $18.69 M/yr -- a rigorous
# lower bound that no further compute can invalidate.
#
# NOT re-run: timor `village`. Plain timor is Commit=0 throughout and the OFF
# scenario has no connection binaries, so it is a pure LP already solved exactly
# by barrier. mipgap is meaningless for it.
#
# TIMEOUT GUARD. `time_limit` has no config key -- it is a make_solver kwarg
# defaulting to 3 days (functions/solver.jl:26) and a timed-out run still exits 0
# and writes normal CSVs. `timeout` converts that into an honest failure. A killed
# leg loses its result CSVs but its log still carries the last
# Best objective / Best bound / gap, which is the number the decision turns on.
set -u
cd /home/pwrlabadmin/garuda/.claude/worktrees/repo-orientation-sync-bd6b46
export GRB_LICENSE_FILE=/home/pwrlabadmin/gurobi.lic

TIMEOUT=${TIMEOUT:-8h}
log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*"; }

# Match the julia binary, not the string "run_model.jl --config" -- a monitoring
# command containing that literal would otherwise look like a running solve.
solves_running() { pgrep -f "bin/julia.*run_model" >/dev/null 2>&1; }

log "queue start; waiting for in-flight solves"
while solves_running; do sleep 60; done
log "in-flight solves clear"

for job in mip1e4_timor mip1e4_market_village; do
  avail=$(free -g | awk 'NR==2{print $7}')
  if [ "$avail" -lt 70 ]; then
    log "SKIP $job: only ${avail}GB available, need ~70GB headroom"
    continue
  fi
  log "START $job (mipgap 1e-4, timeout ${TIMEOUT}, ${avail}GB free)"
  start=$SECONDS
  timeout "$TIMEOUT" julia --project=. run_model.jl \
      --config "jobs/$job/config.json" > "jobs/$job/solve.log" 2>&1
  rc=$?
  dur=$(( SECONDS - start ))
  if [ $rc -eq 124 ]; then
    log "END $job TIMED OUT after $((dur/60))m -- no result CSVs; bound is in jobs/$job/solve.log"
  else
    log "END $job rc=$rc after $((dur/60))m"
  fi
  grep -iE "Explored|Best objective|Optimal objective|reached the time limit" \
      "jobs/$job/solve.log" 2>/dev/null | tail -3 | sed 's/^/    /'
done

log "queue complete"
