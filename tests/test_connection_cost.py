"""Unit tests for the distance-based connection-cost derivation.

Covers the cost math in tools/ntt/costs.py (CRF, distance monotonicity, the
shipped-data cross-check) and the tools/connection_cost.py CLI (hubdist read,
fallback distance, written file shape). Solver-free; runs in CI.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.ntt import costs as C
from tools import connection_cost as cc


def test_crf_value():
    # CRF(10%, 30y) = 0.10608 (standard annuity factor)
    assert abs(C.crf(0.10, 30) - 0.106079) < 1e-5


def test_cost_matches_shipped_default_km_row():
    """The 10 km fallback must reproduce the shipped timor value (27,514 $/yr).

    Village 1 (ATAMBUA) has no coordinates, so build_timor priced it at
    CONNECT_DEFAULT_KM — the regression anchor for the formula.
    """
    assert C.connection_cost_per_yr(C.CONNECT_DEFAULT_KM) == 27514


def test_cost_monotonic_in_distance():
    costs = [C.connection_cost_per_yr(km) for km in (0.5, 5, 20, 60, 120)]
    assert costs == sorted(costs)
    assert costs[0] > 0  # fixed tap cost keeps even adjacent villages non-free


def test_connect_max_floor():
    assert C.connect_max_mw(1.0) == 1.5
    assert C.connect_max_mw(0.001) == C.CONNECT_MAX_FLOOR_MW


def _solar_potential(folder, rows):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "village_solar_potential.csv"), "w") as fh:
        fh.write("Village,desa,hubdist_km,peak_mw\n")
        for r in rows:
            fh.write(",".join("" if x is None else str(x) for x in r) + "\n")


def test_cli_derives_and_falls_back(tmp_path):
    folder = str(tmp_path / "ds")
    _solar_potential(folder, [
        (1, "NEAR", 2.0, 0.5),       # 2 km from the grid
        (2, "FAR", 50.0, 0.1),       # 50 km
        (3, "UNSITED", None, 0.2),   # no hubdist -> default-km fallback
    ])
    rc = cc.main(["connection_cost", folder])
    assert rc == 0

    import pandas as pd
    out = pd.read_csv(os.path.join(folder, "village_connection.csv")).set_index("Village")
    assert list(out.index) == [1, 2, 3]
    # near strictly cheaper than far; fallback equals the 10 km anchor value
    assert out.loc[1, "Cost_per_yr"] < out.loc[2, "Cost_per_yr"]
    assert out.loc[3, "Cost_per_yr"] == 27514
    assert out.loc[1, "Max_Connect_MW"] == 0.75
    # exact values from the documented formula
    assert out.loc[1, "Cost_per_yr"] == C.connection_cost_per_yr(2.0)
    assert out.loc[2, "Cost_per_yr"] == C.connection_cost_per_yr(50.0)


def test_cli_dry_run_writes_nothing(tmp_path):
    folder = str(tmp_path / "ds")
    _solar_potential(folder, [(1, "X", 5.0, 0.3)])
    rc = cc.main(["connection_cost", folder, "--dry-run"])
    assert rc == 0
    assert not os.path.exists(os.path.join(folder, "village_connection.csv"))
