"""Tests for validate_schema's Commit-sentinel and ramp-ratchet guards.

Both exist because of the storage capacity-accounting defect: the loader used to
partition generators with `Commit==1` (UC) and `Commit==0` (ED), which orphaned
every `Commit=2` battery row out of both sets and left its `vCAP` with no
capacity constraint at all. `ED` is now the complement of `UC`, so an
unrecognised sentinel is dispatched rather than orphaned — safe, but silent,
hence the warning. The ramp check guards the data defect that the same rows
carried: `Ramp_Up_Percentage=0` with `Ramp_Dn_Percentage=1`, a unit that can
fall but never rise.

Solver-free; runs in CI. See tests/verify_capacity_accounting.jl for the
model-level property.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.validate_schema import validate_dataset

T = 4  # 1 rep period x 4 hours

HEADER = ("R_ID,Zone,Resource,technology,Fuel,Commit,New_Build,Existing_Cap_MW,"
          "Max_Cap_MW,Heat_Rate_MMBTU_per_MWh,RE,VRE,STOR,"
          "Ramp_Up_Percentage,Ramp_Dn_Percentage")

# (R_ID, Zone, Resource, technology, Fuel, Commit, New_Build, Existing_Cap_MW,
#  Max_Cap_MW, Heat_Rate, RE, VRE, STOR, Ramp_Up, Ramp_Dn)
SOLAR = (1, 1, "plts_x", "solar", "None", 0, 1, 0.0, 10.0, 0, 1, 1, 0, 1, 1)
BATTERY = (2, 1, "battery_candidate", "battery", "None", 2, 1, 0.0, 5.0, 0, 0, 0, 1, 1, 1)


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
    _write(os.path.join(folder, "generators.csv"), HEADER, *gens)
    _write(os.path.join(folder, "demand.csv"),
           "Voll,r_id,Rep_Periods,Timesteps_per_Rep_Period,Sub_Weights,demand_z1",
           (2000, 1, 1, T, 8760, 10), ("", 2, "", "", "", 10),
           ("", 3, "", "", "", 10), ("", 4, "", "", "", 10))
    _write(os.path.join(folder, "generators_variability.csv"),
           "r_id," + ",".join(g[2] for g in gens),
           *[[t] + [1.0] * len(gens) for t in range(1, T + 1)])


def _replace(row, **kw):
    fields = dict(zip(HEADER.split(","), row))
    fields.update(kw)
    return tuple(fields[c] for c in HEADER.split(","))


def test_commit_2_battery_is_accepted_silently(tmp_path):
    """Commit=2 on a STOR row is the shipped battery-candidate sentinel."""
    folder = str(tmp_path / "ds")
    _dataset(folder, [SOLAR, BATTERY])
    errors, warnings = validate_dataset(folder)
    assert errors == []
    assert not any("Commit" in w for w in warnings)


def test_unrecognised_commit_sentinel_warns(tmp_path):
    folder = str(tmp_path / "ds")
    _dataset(folder, [SOLAR, _replace(BATTERY, Commit=7)])
    errors, warnings = validate_dataset(folder)
    assert errors == []
    assert any("unrecognised Commit value(s) [7]" in w for w in warnings)


def test_commit_2_on_non_storage_warns(tmp_path):
    """The sentinel means 'battery candidate'; on a non-STOR row it is a mistake."""
    folder = str(tmp_path / "ds")
    _dataset(folder, [SOLAR, _replace(BATTERY, STOR=0)])
    errors, warnings = validate_dataset(folder)
    assert errors == []
    assert any("Commit=2 is the battery-candidate sentinel" in w for w in warnings)


def test_one_way_ramp_ratchet_is_an_error(tmp_path):
    """Ramp_Up=0 with Ramp_Dn>0 pins output to a constant — not a physical unit."""
    folder = str(tmp_path / "ds")
    _dataset(folder, [_replace(SOLAR, Ramp_Up_Percentage=0, Ramp_Dn_Percentage=1)])
    errors, _ = validate_dataset(folder)
    assert any("one-way ratchet" in e and "[1]" in e for e in errors)


def test_symmetric_zero_ramp_is_allowed(tmp_path):
    """Ramp_Up == Ramp_Dn == 0 is a legitimate must-run baseload (geothermal)."""
    folder = str(tmp_path / "ds")
    _dataset(folder, [_replace(SOLAR, technology="geothermal",
                               Ramp_Up_Percentage=0, Ramp_Dn_Percentage=0)])
    errors, _ = validate_dataset(folder)
    assert not any("one-way ratchet" in e for e in errors)


def test_storage_ramp_columns_are_not_checked(tmp_path):
    """Storage is exempt from the ramp constraints, so its ramp columns are unused.

    Every shipped grid battery row carries exactly this ratchet; flagging it
    would fail 30 datasets over a field the model no longer reads.
    """
    folder = str(tmp_path / "ds")
    _dataset(folder, [SOLAR, _replace(BATTERY, Ramp_Up_Percentage=0,
                                      Ramp_Dn_Percentage=1)])
    errors, _ = validate_dataset(folder)
    assert not any("one-way ratchet" in e for e in errors)
