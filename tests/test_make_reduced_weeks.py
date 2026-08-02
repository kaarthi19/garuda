"""Unit tests for the reduced-representative-weeks builder.

Guards the two defects found (and fixed) during its first real use:

1. **Non-bracketing week pairs.** The first build selected two above-mean-power
   weeks; no convex weighting of such a pair can reproduce annual energy, and
   the tool silently fell back to uniform weights with a +2.29 % energy error.
   The selection must prefer a representative week on the OPPOSITE side of the
   all-weeks mean from the stress week, making the 2x2 hours+energy solve land
   inside (0, 8760).
2. **Degenerate solar statistics.** The synthetic timor solar repeats weekly —
   every week has the identical mean CF — so "worst solar week" is undefined
   and a z-score against a zero std produced all-NaN. The stress criterion must
   fall back to the peak-demand week and the z-score must not divide by zero.

Solver-free; runs in CI.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import make_reduced_weeks as mrw

HOURS = mrw.HOURS


def _dataset(folder, week_scale):
    """8 synthetic weeks; per-week mean power controlled by week_scale."""
    os.makedirs(folder, exist_ok=True)
    n = len(week_scale) * HOURS
    hours = np.tile(np.arange(HOURS), len(week_scale))
    scale = np.repeat(week_scale, HOURS)
    demand = 100.0 * scale * (1 + 0.2 * np.sin(hours / 24 * 2 * np.pi))
    ref = {"Voll": [2000.0] + [np.nan] * (n - 1),
           "Demand_Segment": [1.0, 2.0] + [np.nan] * (n - 2),
           "Cost_of_Demand_Curtailment_per_MW": [1.0, 0.9] + [np.nan] * (n - 2),
           "Max_Demand_Curtailment": [1.0, 0.04] + [np.nan] * (n - 2),
           "Rep_Periods": [float(len(week_scale))] + [np.nan] * (n - 1),
           "Timesteps_per_Rep_Period": [float(HOURS)] + [np.nan] * (n - 1),
           "Sub_Weights": [1095.0] * len(week_scale) + [np.nan] * (n - len(week_scale))}
    pd.DataFrame({**ref, "corresponding_week": np.repeat(range(len(week_scale)), HOURS),
                  "r_id": np.arange(1, n + 1), "hour": hours,
                  "demand_z1": demand}).to_csv(os.path.join(folder, "demand.csv"), index=False)
    pd.DataFrame({"r_id": np.arange(1, n + 1),
                  "demand_village1": demand * 0.1}).to_csv(
        os.path.join(folder, "village_demand.csv"), index=False)
    pd.DataFrame({"r_id": np.arange(1, n + 1),
                  "demand_village1": demand * 0.01}).to_csv(
        os.path.join(folder, "village_demandheat.csv"), index=False)
    pd.DataFrame({"R_ID": [1, 2], "Village": [1, 1],
                  "technology": ["diesel", "solar"]}).to_csv(
        os.path.join(folder, "village_generators.csv"), index=False)
    # solar CF repeats identically every week -> degenerate weekly stats (trap 2)
    cf = 0.5 * np.clip(np.sin((hours - 6) / 12 * np.pi), 0, None)
    pd.DataFrame({"r_id": np.arange(1, n + 1), "pltd_1": 1.0, "plts_1": cf}).to_csv(
        os.path.join(folder, "village_generators_variability.csv"), index=False)
    pd.DataFrame({"r_id": np.arange(1, n + 1), "gen_1": 1.0}).to_csv(
        os.path.join(folder, "generators_variability.csv"), index=False)


def test_pair_brackets_the_mean_and_energy_is_preserved(tmp_path):
    # week 7 is the clear peak (stress); weeks below the mean exist to bracket it
    scale = np.array([0.90, 0.95, 1.00, 1.02, 1.04, 1.05, 1.06, 1.30])
    src = str(tmp_path / "ds")
    _dataset(src, scale)
    weeks, st, fallback, E_annual = mrw.pick_weeks(src)

    assert not fallback, "bracketing selection must make the 2x2 solve feasible"
    (w_a, wt_a), (w_b, wt_b) = weeks
    assert wt_a + wt_b == 8760
    assert {w_a, w_b} & {7}, "the peak-demand stress week must be kept"
    mean_p = st.mean_power.mean()
    sides = {np.sign(st.mean_power[w] - mean_p) for w, _ in weeks}
    assert len(sides) == 2, "selected weeks must straddle the all-weeks mean"
    # energy preserved to integer-weight rounding
    E_sel = sum(wt * st.mean_power[w] for w, wt in weeks)
    assert abs(E_sel - E_annual) / E_annual < 1e-3


def test_degenerate_solar_falls_back_to_peak_demand_week(tmp_path):
    scale = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.5])
    src = str(tmp_path / "ds")
    _dataset(src, scale)
    weeks, st, fallback, _ = mrw.pick_weeks(src)
    assert st.solar_cf.std() < 1e-9, "fixture must reproduce the degenerate-CF case"
    assert any(w == 7 for w, _ in weeks), "stress must fall back to the peak-demand week"


def test_build_slices_renumbers_and_stamps_metadata(tmp_path):
    scale = np.array([0.9, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.3])
    src, out = str(tmp_path / "ds"), str(tmp_path / "ds2w")
    _dataset(src, scale)
    weeks, *_ = mrw.pick_weeks(src)
    mrw.build(src, out, weeks)

    d = pd.read_csv(os.path.join(out, "demand.csv"))
    assert len(d) == 2 * HOURS
    assert list(d.r_id) == list(range(1, 2 * HOURS + 1))
    assert list(d.hour[:HOURS]) == list(range(HOURS))
    assert float(d.Rep_Periods.dropna().iloc[0]) == 2.0
    sw = d.Sub_Weights.dropna().tolist()
    assert len(sw) == 2 and sum(sw) == 8760
    # audit trail: original week ids survive
    assert set(d.corresponding_week.unique()) == {w for w, _ in weeks}
    # every time-series file sliced consistently
    for f in mrw.TS_FILES:
        assert len(pd.read_csv(os.path.join(out, f))) == 2 * HOURS
