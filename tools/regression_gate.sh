#!/usr/bin/env bash
# Frozen-baseline regression gate.
#
# Solves a small fixed set of fast cases and records their headline numbers, so
# that when you change shared model or reporting code you can tell a *reporting*
# fix from a *physics* change. Without it, "the number moved" is ambiguous and
# every enabler looks equally risky.
#
#   tools/regression_gate.sh capture        # record the current numbers
#   tools/regression_gate.sh check          # re-solve and diff against the record
#   tools/regression_gate.sh check --tol 0  # exact match required
#
# The baseline lives in tests/regression_baseline.csv (tracked, small). Update it
# deliberately — with the reason in the commit body — never to make a red gate green.
#
# Cases are chosen to cover the surfaces most easily broken:
#   maluku      grid-only, NON-UNIFORM Sub_Weights -> catches annualisation errors
#               that uniform-weight datasets hide. Also the CI case.
#   timor_demo  a village layer with Commit=1 village diesel -> catches village
#               generation / CO2 / RE-share regressions a grid-only case cannot see.
#   timor_belu  (--full, ~4 min) the real NTT structure: Commit=0 village diesel and
#               a zero-demand grid zone. timor_demo cannot see bugs in either, which
#               is precisely how the village-CO2 and NaN-RE-share defects survived.
#
# `check` re-solves exactly the cases recorded in the baseline, so a baseline
# captured with --full is always checked with --full.
#
# Runs on Julia + HiGHS (no licence) and Python + pandas. Minutes, not hours.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE="${REPO}/tests/regression_baseline.csv"
PYTHON="${GARUDA_PYTHON:-python3}"
TOL="1e-9"
FULL=0

ALL_CASES=(
  "maluku_dispatch|maluku|2030|base|reference|dispatch"
  "timor_demo_gridvillage_dispatch|timor_demo|2030|gridvillage|reference|dispatch"
  "timor_belu_gridvillage_dispatch|timor_belu|2030|gridvillage|reference|dispatch"
)
FAST_CASES=("${ALL_CASES[0]}" "${ALL_CASES[1]}")

usage() { sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2; }

mode="${1:-}"
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tol) TOL="$2"; shift 2 ;;
    --full) FULL=1; shift ;;
    *) echo "unknown option: $1" >&2; usage ;;
  esac
done
[[ "$mode" == "capture" || "$mode" == "check" ]] || usage

if [[ "${mode}" == "capture" ]]; then
  if [[ "${FULL}" == "1" ]]; then CASES=("${ALL_CASES[@]}"); else CASES=("${FAST_CASES[@]}"); fi
else
  # re-solve exactly what the baseline covers, so coverage cannot silently shrink
  [[ -f "${BASELINE}" ]] || { echo "no baseline at ${BASELINE} — run 'capture' first" >&2; exit 1; }
  CASES=()
  while IFS= read -r want; do
    for spec in "${ALL_CASES[@]}"; do
      [[ "${spec%%|*}" == "${want}" ]] && CASES+=("${spec}")
    done
  done < <(tail -n +2 "${BASELINE}" | cut -d, -f1 | awk '!seen[$0]++')
  [[ ${#CASES[@]} -gt 0 ]] || { echo "baseline names no known case" >&2; exit 1; }
fi

scratch="$(mktemp -d)"
trap 'rm -rf "${scratch}"' EXIT
out="${scratch}/metrics.csv"
echo "case,metric,value" > "${out}"

for spec in "${CASES[@]}"; do
  IFS='|' read -r name island year scenario clean engine <<< "${spec}"
  cfg="${scratch}/${name}.json"
  cat > "${cfg}" <<JSON
{
  "island": "${island}", "year": "${year}", "scenario": "${scenario}",
  "clean": "${clean}", "CO235reduction": false, "BAUCO2emissions": 0.0,
  "CO2_limit": 1000000000000.0, "engine": "${engine}", "relax_uc": true,
  "solver": "highs", "mipgap": 0.01, "run_tag": "reggate"
}
JSON
  echo "== solving ${name} (${scenario} ${island} ${year} ${clean}, ${engine}) =="
  if ! julia --project="${REPO}" "${REPO}/run_model.jl" --config "${cfg}" > "${scratch}/${name}.log" 2>&1; then
    echo "  SOLVE FAILED — see ${scratch}/${name}.log" >&2
    tail -20 "${scratch}/${name}.log" >&2
    exit 1
  fi
  dir="${REPO}/results/${scenario}_${island}_${year}_${clean}__reggate"
  "${PYTHON}" - "${name}" "${dir}" "${out}" <<'PY'
import os, sys
import pandas as pd

name, run_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
NA = dict(encoding="utf-8-sig", keep_default_na=False, na_values=[""])
num = lambda s: pd.to_numeric(s, errors="coerce")


def read(f):
    p = os.path.join(run_dir, f)
    return pd.read_csv(p, **NA) if os.path.isfile(p) else None


rows = []
cost = read("cost_results.csv")
if cost is not None:
    for c in cost.columns:
        rows.append((f"cost.{c}", float(num(pd.Series([cost.iloc[0][c]])).iloc[0])))

clean = read("clean_energy_results.csv")
if clean is not None:
    for c in clean.columns:
        rows.append((c, float(num(pd.Series([clean.iloc[0][c]])).iloc[0])))

for f, col, label in (("generator_results.csv", "GWh", "grid_generation_gwh"),
                      ("site_generator_results.csv", "Electricity_GWh", "site_generation_gwh")):
    d = read(f)
    if d is not None and col in d.columns:
        rows.append((label, float(num(d[col]).sum())))

for f, label in (("reliability_results.csv", "grid_nse_mwh"),
                 ("site_reliability_results.csv", "site_nse_mwh")):
    d = read(f)
    if d is not None and "Total_NSE_MWh" in d.columns:
        rows.append((label, float(num(d["Total_NSE_MWh"]).sum())))

with open(out_path, "a") as fh:
    for metric, value in rows:
        fh.write(f"{name},{metric},{value!r}\n")
print(f"  captured {len(rows)} metric(s)")
PY
done

if [[ "${mode}" == "capture" ]]; then
  mkdir -p "$(dirname "${BASELINE}")"
  cp "${out}" "${BASELINE}"
  echo
  echo "wrote $(( $(wc -l < "${BASELINE}") - 1 )) metric(s) to ${BASELINE#"${REPO}/"}"
  exit 0
fi

if [[ ! -f "${BASELINE}" ]]; then
  echo "no baseline at ${BASELINE} — run 'tools/regression_gate.sh capture' first" >&2
  exit 1
fi

"${PYTHON}" - "${BASELINE}" "${out}" "${TOL}" <<'PY'
import sys
import pandas as pd

base = pd.read_csv(sys.argv[1]).set_index(["case", "metric"])["value"]
now = pd.read_csv(sys.argv[2]).set_index(["case", "metric"])["value"]
tol = float(sys.argv[3])

def isnan(x):
    return x != x


moved, missing, added = [], [], []
for key, want in base.items():
    if key not in now.index:
        missing.append(key)
        continue
    got, want = float(now[key]), float(want)
    # NaN needs explicit handling: `abs(nan - nan) > tol` is False, so a metric
    # going NaN -> a real number (exactly what fixing a 0/0 share does) would
    # otherwise slip through as "unchanged".
    if isnan(want) or isnan(got):
        if isnan(want) != isnan(got):
            moved.append((key, want, got, float("nan")))
        continue
    denom = abs(want) if abs(want) > 0 else 1.0
    rel = abs(got - want) / denom
    if rel > tol:
        moved.append((key, want, got, rel))
for key in now.index:
    if key not in base.index:
        added.append(key)

for case, metric in missing:
    print(f"  MISSING  {case}  {metric}")
for case, metric in added:
    print(f"  NEW      {case}  {metric}")
for (case, metric), want, got, rel in moved:
    delta = "NaN boundary" if rel != rel else f"{rel:.3%}"
    print(f"  MOVED    {case}  {metric}\n"
          f"           baseline {want!r}\n"
          f"           now      {got!r}   ({delta})")

print()
if moved or missing:
    print(f"REGRESSION_GATE_FAIL: {len(moved)} moved, {len(missing)} missing, "
          f"{len(added)} new (tolerance {tol:g})")
    print("If the move is intended, re-capture the baseline and say why in the commit body.")
    sys.exit(1)
print(f"REGRESSION_GATE_OK: {len(base)} metric(s) unchanged"
      + (f", {len(added)} new" if added else "") + f" (tolerance {tol:g})")
PY
