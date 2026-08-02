#!/usr/bin/env bash
# Carbon-neutral coordination pair (2w, clean, policy_scope=system).
# Cap 656,500 t = measured islanded emissions +0.5%; RE floor 0.48 = measured
# islanded share (0.4872) minus margin. The question: what is coordination worth
# when it may neither out-emit nor be less renewable than islanding?
set -u
cd /home/pwrlabadmin/garuda/.claude/worktrees/repo-orientation-sync-bd6b46
export GRB_LICENSE_FILE=/home/pwrlabadmin/gurobi.lic
log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*"; }
for job in w2c_village w2c_gridvillage; do
  while [ "$(free -g | awk 'NR==2{print $7}')" -lt 35 ]; do sleep 60; done
  log "LAUNCH $job ($(free -g | awk 'NR==2{print $7}')GB free)"
  ( timeout 5h julia --project=. run_model.jl \
      --config "jobs/$job/config.json" > "jobs/$job/solve.log" 2>&1
    log "END $job rc=$?" ) &
  sleep 120
done
wait
log "clean pair complete"
python3 - <<'PYEOF'
import pandas as pd, os
rows=[]
for sc in ("village","gridvillage"):
    d=f"results/{sc}_timor__marketfix2w_2030_clean"
    if os.path.exists(f"{d}/cost_results.csv"):
        c=pd.read_csv(f"{d}/cost_results.csv").iloc[0]
        e=pd.read_csv(f"{d}/clean_energy_results.csv").iloc[0]
        rows.append((sc, c.Total_Costs, e.CO2_Emissions, e.System_REShare))
        print(f"  {sc:12s} cost={c.Total_Costs:.5f}  CO2={e.CO2_Emissions:,.0f}  RE={e.System_REShare:.4f}")
if len(rows)==2:
    print(f"  carbon-neutral coordination value: {(rows[0][1]-rows[1][1])*1e6:,.0f} $/yr")
PYEOF
