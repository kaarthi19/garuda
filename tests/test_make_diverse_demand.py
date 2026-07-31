"""Load-shape diversity: move the peak, never the energy.

The experiment this dataset supports compares a homogeneous village fleet against
a heterogeneous one. That comparison is only clean if the reshaping changes *when*
load falls and nothing else — so the central test is that per-period energy is
preserved exactly, which keeps weighted annual energy exact for any `Sub_Weights`,
uniform or not.

Solver-free; runs in CI.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.ntt import make_diverse_demand as M

NA = dict(encoding="utf-8-sig", keep_default_na=False, na_values=[""])
P, H = 2, 24          # two short representative "days" keep the fixture readable
VILLAGES = 4


def quiet(*_a, **_k):
    pass


def evening_peaked(n_hours):
    """An evening-peaking profile like the archetype curves."""
    return [0.2 + 0.8 * (1.0 if (t % 24) == 18 else 0.3 if 17 <= (t % 24) <= 20 else 0.0)
            for t in range(n_hours)]


@pytest.fixture
def demand():
    T = P * H
    base = evening_peaked(T)
    cols = {"Voll": [2000] + [""] * (T - 1),
            "Demand_Segment": [1, 2, 3, 4] + [""] * (T - 4),
            "Cost_of_Demand_Curtailment_per_MW": [1.0, 0.9, 0.55, 0.2] + [""] * (T - 4),
            "Max_Demand_Curtailment": [1.0, 0.04, 0.024, 0.003] + [""] * (T - 4),
            "r_id": list(range(1, T + 1)),
            "hour": list(range(T))}
    for v in range(1, VILLAGES + 1):
        cols[f"demand_village{v}"] = [x * v for x in base]
    return pd.DataFrame(cols)


# ------------------------------------------------------------------- the shape

def test_midday_shape_peaks_at_noon():
    shape = M.midday_shape(24)
    assert shape.index(max(shape)) == int(M.PEAK_HOUR)
    assert min(shape) == pytest.approx(M.BASELOAD, abs=0.02), "must keep a night baseload"
    assert all(0 < s <= 1 for s in shape)


def test_midday_shape_wraps_around_midnight():
    """Hour 23 must be treated as 1 h from hour 0, not 23 h."""
    shape = M.midday_shape(24)
    assert shape[23] == pytest.approx(shape[1], rel=1e-9)


def test_midday_shape_repeats_daily_over_a_longer_period():
    shape = M.midday_shape(48)
    assert shape[:24] == pytest.approx(shape[24:])


# --------------------------------------------------------------- the selection

def test_selection_is_a_fraction_evenly_spread():
    cols = [f"demand_village{v}" for v in range(1, 11)]
    half = M.select_villages(cols, 0.5)
    assert len(half) == 5
    # evenly spread, not the first five
    assert half != cols[:5]
    assert M.select_villages(cols, 1.0) == cols
    assert M.select_villages(cols, 0.0) == []


def test_selection_is_deterministic():
    cols = [f"demand_village{v}" for v in range(1, 101)]
    assert M.select_villages(cols, 0.5) == M.select_villages(cols, 0.5)


# ------------------------------------------------------------------ the energy

def test_per_period_energy_is_preserved(demand):
    # Values are written at 6 decimals, matching the demand CSVs the generator
    # produces, so the guarantee is "exact to write precision" — the same 1e-6
    # relative bound the tool itself refuses to exceed.
    out, stats = M.reshape(demand, 0.5, (P, H), report=quiet)
    cols = [c for c in demand.columns if c.startswith("demand_")]
    for p in range(P):
        lo, hi = p * H, (p + 1) * H
        before = demand[cols].apply(pd.to_numeric).to_numpy()[lo:hi].sum()
        after = out[cols].apply(pd.to_numeric).to_numpy()[lo:hi].sum()
        assert after == pytest.approx(before, rel=1e-6)
    assert stats["energy_error_rel"] < 1e-6


def test_energy_preserved_per_village_not_just_in_total(demand):
    out, _s = M.reshape(demand, 0.5, (P, H), report=quiet)
    for c in [c for c in demand.columns if c.startswith("demand_")]:
        assert pd.to_numeric(out[c]).sum() == pytest.approx(
            pd.to_numeric(demand[c]).sum(), rel=1e-6), f"{c} changed total energy"


def test_the_peak_actually_moves(demand):
    out, stats = M.reshape(demand, 1.0, (P, H), report=quiet)
    assert stats["peak_hour_before"] == 18
    assert stats["peak_hour_after"] == int(M.PEAK_HOUR)
    # reshaping every village onto one shape lowers nothing in total but does move it
    cols = [c for c in demand.columns if c.startswith("demand_")]
    tot = out[cols].apply(pd.to_numeric).to_numpy().sum(axis=1)
    assert tot.argmax() % 24 == int(M.PEAK_HOUR)


def test_unselected_villages_are_untouched(demand):
    out, stats = M.reshape(demand, 0.5, (P, H), report=quiet)
    cols = [c for c in demand.columns if c.startswith("demand_")]
    chosen = set(M.select_villages(cols, 0.5))
    assert stats["reshaped"] == len(chosen)
    untouched = [c for c in cols if c not in chosen]
    assert untouched, "the fixture must leave some villages alone"
    for c in untouched:
        assert list(pd.to_numeric(out[c])) == pytest.approx(list(pd.to_numeric(demand[c])))


def test_diversity_lowers_the_coincident_peak(demand):
    """Half midday + half evening must be flatter than all-evening."""
    out, stats = M.reshape(demand, 0.5, (P, H), report=quiet)
    assert stats["coincident_peak_after"] < stats["coincident_peak_before"]
    assert len(out) == len(demand)


# ------------------------------------------------------------------ the guards

def test_row_count_mismatch_is_an_error(demand):
    with pytest.raises(SystemExit):
        M.reshape(demand, 0.5, (P, H + 1), report=quiet)


def test_no_demand_columns_is_an_error():
    with pytest.raises(SystemExit):
        M.reshape(pd.DataFrame({"r_id": list(range(P * H))}), 0.5, (P, H), report=quiet)


def test_fraction_must_be_a_fraction():
    for bad in ("0", "-0.5", "1.2"):
        with pytest.raises(SystemExit):
            M.main(["--dataset", "data_indonesia/2030/timor", "--fraction", bad,
                    "--dry-run"])


def test_period_shape_reads_the_zonal_demand_file():
    """The rep-period structure lives in demand.csv, not village_demand.csv."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert M.period_shape(os.path.join(root, "data_indonesia", "2030", "timor")) == (8, 168)
    vd = pd.read_csv(os.path.join(root, "data_indonesia", "2030", "timor",
                                  "village_demand.csv"), nrows=1, **NA)
    assert "Rep_Periods" not in vd.columns
