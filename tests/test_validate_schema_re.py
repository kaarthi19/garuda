"""Tests for validate_schema's RE-flag consistency warnings.

Builds a minimal valid dataset in tmp_path and checks the two warning
directions: a fossil-fuelled unit flagged RE=1 (inflates the RE share — the
maluku a0cf7d5 class) and a renewable technology left at RE=0 (deflates it).
Solver-free; runs in CI.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.validate_schema import validate_dataset

T = 4  # 1 rep period x 4 hours


def _write(path, header, *rows):
    with open(path, "w") as fh:
        fh.write(header + "\n")
        for r in rows:
            fh.write(",".join(str(x) for x in r) + "\n")


def _dataset(folder, gens):
    """Minimal schema-valid dataset with the given generator rows."""
    os.makedirs(folder, exist_ok=True)
    _write(os.path.join(folder, "fuels_data.csv"),
           "Fuel,Cost_per_MMBtu,CO2_content_tons_per_MMBtu",
           ("None", 0, 0), ("diesel", 18, 0.0732))
    _write(os.path.join(folder, "generators.csv"),
           "R_ID,Zone,Resource,technology,Fuel,Commit,New_Build,Existing_Cap_MW,"
           "Max_Cap_MW,Heat_Rate_MMBTU_per_MWh,RE,VRE",
           *gens)
    _write(os.path.join(folder, "demand.csv"),
           "Voll,r_id,Rep_Periods,Timesteps_per_Rep_Period,Sub_Weights,demand_z1",
           (2000, 1, 1, T, 8760, 10), ("", 2, "", "", "", 10),
           ("", 3, "", "", "", 10), ("", 4, "", "", "", 10))
    _write(os.path.join(folder, "generators_variability.csv"),
           "r_id," + ",".join(g[2] for g in gens),
           *[[t] + [1.0] * len(gens) for t in range(1, T + 1)])


def test_fossil_flagged_re_warns(tmp_path):
    folder = str(tmp_path / "ds")
    _dataset(folder, [
        (1, 1, "pltd_x", "diesel", "diesel", 0, 0, 5.0, 5.0, 10.5, 1, 0),  # RE=1 fossil!
        (2, 1, "plts_x", "solar", "None", 0, 1, 0.0, 10.0, 0, 1, 1),
    ])
    errors, warnings = validate_dataset(folder)
    assert errors == []
    assert any("RE=1 on fossil-fuelled" in w and "pltd_x" in w for w in warnings)


def test_unflagged_renewable_warns(tmp_path):
    folder = str(tmp_path / "ds")
    _dataset(folder, [
        (1, 1, "pltp_x", "geothermal", "None", 0, 1, 20.0, 20.0, 0, 0, 0),  # RE=0!
        (2, 1, "plts_x", "solar", "None", 0, 1, 0.0, 10.0, 0, 1, 1),
    ])
    errors, warnings = validate_dataset(folder)
    assert errors == []
    assert any("renewable technology with RE=0" in w and "pltp_x" in w for w in warnings)


def test_consistent_flags_no_re_warnings(tmp_path):
    folder = str(tmp_path / "ds")
    _dataset(folder, [
        (1, 1, "pltd_x", "diesel", "diesel", 0, 0, 5.0, 5.0, 10.5, 0, 0),
        (2, 1, "pltp_x", "geothermal", "None", 0, 1, 20.0, 20.0, 0, 1, 0),
        (3, 1, "plts_x", "solar", "None", 0, 1, 0.0, 10.0, 0, 1, 1),
    ])
    errors, warnings = validate_dataset(folder)
    assert errors == []
    assert not any("RE" in w for w in warnings)
