#!/usr/bin/env bash
# The 2-week batch: nf village (completes the OFF pair), then both gridvillage
# legs at mipgap 0.001 — the tolerance the small model can actually afford.
# Models are ~1/4 the full size (~12-15 GB each), so they run alongside the
# finishing ucrelax legs without pressure. Warm-started via the vVIL_CONNECT=0
# MIP start already in capacity_expansion.
set -u
cd /home/pwrlabadmin/garuda/.claude/worktrees/repo-orientation-sync-bd6b46
export GRB_LICENSE_FILE=/home/pwrlabadmin/gurobi.lic
log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*"; }
for job in w2_fix_gridvillage w2_nf_gridvillage; do
  while [ "$(free -g | awk 'NR==2{print $7}')" -lt 40 ]; do sleep 60; done
  log "LAUNCH $job ($(free -g | awk 'NR==2{print $7}')GB free)"
  ( timeout 5h julia --project=. run_model.jl \
      --config "jobs/$job/config.json" > "jobs/$job/solve.log" 2>&1
    log "END $job rc=$?" ) &
  sleep 120
done
wait
log "w2 batch complete"
for j in w2_fix_gridvillage w2_nf_gridvillage; do
  grep -E "Best objective|Optimal solution|reached the time" "jobs/$j/solve.log" 2>/dev/null | tail -1 | sed "s/^/  $j: /"
done
