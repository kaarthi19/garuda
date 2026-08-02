#!/usr/bin/env bash
# NodeMethod experiment: rerun both ucrelax gridvillage legs with barrier node
# LPs (NodeMethod 2) and bound-focused search (MIPFocus 3), warm-started.
#
# WHY. The ucrelax legs use ~2 of their 32 permitted threads: node LPs default
# to dual simplex, which is serial. Barrier (the ~9-core phase) at the nodes may
# raise node throughput substantially. Cheap experiment; tonight's results stay
# intact under the ucrelax tag, these write to ucrelax2.
#
# gurobi.env applies to ANY Gurobi run started from the repo root while present;
# it is created just before the first leg and removed on exit (trap). Do not
# launch unrelated solves while this queue is active. Timing comparisons against
# earlier runs are confounded by these params — this queue is for bound
# tightening, not benchmarks.
set -u
cd /home/pwrlabadmin/garuda/.claude/worktrees/repo-orientation-sync-bd6b46
export GRB_LICENSE_FILE=/home/pwrlabadmin/gurobi.lic
log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*"; }
solves_running() { pgrep -f "bin/julia.*run_model" >/dev/null 2>&1; }

log "armed; waiting for the ucrelax legs to finish (caps ~03:17/03:24)"
while solves_running; do sleep 120; done
log "clear; letting the old scheduler finish its post-processing"
sleep 180

printf 'NodeMethod 2\nMIPFocus 3\n' > gurobi.env
trap 'rm -f gurobi.env' EXIT
log "gurobi.env written (NodeMethod 2, MIPFocus 3)"

for job in ucr2_marketfix_gridvillage ucr2_marketfixnf_gridvillage; do
  while [ "$(free -g | awk 'NR==2{print $7}')" -lt 75 ]; do sleep 60; done
  log "LAUNCH $job ($(free -g | awk 'NR==2{print $7}')GB free)"
  ( timeout 9h julia --project=. run_model.jl \
      --config "jobs/$job/config.json" > "jobs/$job/solve.log" 2>&1
    log "END $job rc=$?" ) &
  sleep 600
done
wait
rm -f gurobi.env
log "queue complete; gurobi.env removed"
for j in ucr2_marketfix_gridvillage ucr2_marketfixnf_gridvillage; do
  grep -E "Best objective|reached the time" "jobs/$j/solve.log" 2>/dev/null | tail -1 | sed "s/^/  $j: /"
done
