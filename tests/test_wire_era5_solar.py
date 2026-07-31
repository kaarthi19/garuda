"""Wiring hourly solar CF into site variability: right weeks, right columns, right rows.

The three failure modes this guards, all silent:

- **Wrong weeks.** The representative weeks belong to the dataset
  (`demand.csv::corresponding_week`), not to the tool. Slicing another dataset's
  weeks still yields 8 x 168 rows, so a row-count check cannot catch it.
- **Wrong column.** Variability columns map to generators by *position* (`R_ID`),
  and the village a solar unit belongs to comes from an explicit join on
  `village_generators.csv`. Pairing the Nth solar column with the Nth village
  breaks as soon as one village has two solar units — so the fixture here gives
  one village two, and shuffles the generator row order.
- **Flattening a genset.** Diesel and battery availability must stay 1.0.

Solver-free; runs in CI.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.ntt import wire_era5_solar as W

H = W.HOURS_PER_WEEK
WEEKS = [2, 9]
VILLAGES = [1, 2, 3, 4]

VIL_GEN_COLS = ["R_ID", "Zone", "Village", "Resource", "technology", "owner",
                "Existing_Cap_MW", "Existing_Cap_MWh", "New_Build", "Max_Cap_MW",
                "Inv_Cost_per_MWyr", "Inv_Cost_per_MWhyr", "Fixed_OM_Cost_per_MWyr",
                "Fixed_OM_Cost_per_MWhyr", "Var_OM_Cost_per_MWh", "Min_Power_MW",
                "Ramp_Up_Percentage", "Ramp_Dn_Percentage", "Commit",
                "Start_Cost_per_MW", "Start_Fuel_MMBTU_per_MW",
                "Heat_Rate_MMBTU_per_MWh", "Fuel", "Up_Time", "Down_Time",
                "Eff_Up", "Eff_Down", "STOR", "VRE", "RE", "THERM"]


def _gen_row(r_id, village, resource, tech):
    row = {c: 0 for c in VIL_GEN_COLS}
    row.update(R_ID=r_id, Zone=1, Village=village, Resource=resource,
               technology=tech, owner="village_coop", Fuel="None",
               Ramp_Up_Percentage=1.0, Ramp_Dn_Percentage=1.0,
               Eff_Up=1, Eff_Down=1)
    if tech == "solar":
        row.update(New_Build=1, VRE=1, RE=1)
    elif tech == "battery":
        row.update(New_Build=1, STOR=1, Eff_Up=0.92, Eff_Down=0.92)
    else:
        row.update(Existing_Cap_MW=0.5, THERM=1, Heat_Rate_MMBTU_per_MWh=10.5,
                   Fuel="diesel")
    return row


@pytest.fixture
def dataset(tmp_path):
    """A 4-village dataset over 2 representative weeks.

    Village 3 deliberately has TWO solar units, so the solar units are not the
    every-third row and a positional plts<->village pairing would mis-wire.
    """
    d = tmp_path / "2030" / "tiny"
    d.mkdir(parents=True)

    rows, r_id = [], 1
    layout = []   # (village, resource, tech) in R_ID order
    for v in VILLAGES:
        layout.append((v, f"pltd_{v}", "diesel"))
        layout.append((v, f"plts_{v}", "solar"))
        layout.append((v, f"batt_{v}", "battery"))
        if v == 3:
            layout.append((v, "plts_3b", "solar"))
    for village, resource, tech in layout:
        rows.append(_gen_row(r_id, village, resource, tech))
        r_id += 1
    gens = pd.DataFrame(rows, columns=VIL_GEN_COLS)
    # shuffle the row order, then restore consecutive R_IDs: the join must survive
    # a file that is not grouped village-by-village
    gens = gens.sample(frac=1.0, random_state=3).reset_index(drop=True)
    gens["R_ID"] = range(1, len(gens) + 1)
    gens.to_csv(d / "village_generators.csv", index=False)

    T = len(WEEKS) * H
    demand = pd.DataFrame({
        "Voll": [2000] + [""] * (T - 1),
        "Demand_Segment": list(range(1, 5)) + [""] * (T - 4),
        "Cost_of_Demand_Curtailment_per_MW": [1.0, 0.9, 0.55, 0.2] + [""] * (T - 4),
        "Max_Demand_Curtailment": [1.0, 0.04, 0.024, 0.003] + [""] * (T - 4),
        "Rep_Periods": [len(WEEKS)] + [""] * (T - 1),
        "Timesteps_per_Rep_Period": [H] + [""] * (T - 1),
        "Sub_Weights": [4380, 4380] + [""] * (T - 2),
        "corresponding_week": WEEKS + [""] * (T - 2),
        "r_id": range(1, T + 1),
        "hour": range(T),
        "demand_z1": [1.0] * T,
    })
    demand.to_csv(d / "demand.csv", index=False)

    var = {"r_id": list(range(1, T + 1))}
    for _v, resource, _t in [(g["Village"], g["Resource"], g["technology"])
                             for _, g in gens.iterrows()]:
        var[resource] = [1.0] * T
    pd.DataFrame(var).to_csv(d / "village_generators_variability.csv", index=False)

    # full-year CF: village v has the constant value v/100, so a mis-wire is obvious
    cf = {"time": pd.date_range("2023-01-01", periods=8760, freq="h")}
    for v in VILLAGES:
        cf[f"village_{v}"] = [v / 100.0] * 8760
    cf_path = tmp_path / "cf.csv"
    pd.DataFrame(cf).to_csv(cf_path, index=False)

    return str(d), str(cf_path), gens


def quiet(*_a, **_k):
    pass


def test_weeks_come_from_the_dataset(dataset):
    d, _cf, _g = dataset
    weeks, P, hours = W.dataset_weeks(d)
    assert weeks == WEEKS
    assert (P, hours) == (len(WEEKS), H)


def test_wires_each_solar_unit_to_its_own_village(dataset):
    d, cf, gens = dataset
    patched, stats = W.wire(d, cf, report=quiet)

    solar = gens[gens["technology"] == "solar"]
    assert len(solar) == 5, "4 villages + a second unit on village 3"
    assert stats["wired"] == 5

    for _, row in solar.iterrows():
        col = patched.iloc[:, int(row["R_ID"])]
        expected = int(row["Village"]) / 100.0
        assert np.allclose(pd.to_numeric(col), expected), (
            f"{row['Resource']} (village {row['Village']}) got {col.iloc[0]} "
            f"instead of {expected} — columns are wired by position, so a shifted "
            f"join mis-wires every later unit"
        )


def test_non_solar_units_stay_flat(dataset):
    d, cf, gens = dataset
    patched, _s = W.wire(d, cf, report=quiet)
    for _, row in gens[gens["technology"] != "solar"].iterrows():
        col = pd.to_numeric(patched.iloc[:, int(row["R_ID"])])
        assert (col == W.FLAT_CF).all(), f"{row['Resource']} is no longer flat"


def test_row_count_and_slice_length(dataset):
    d, cf, _g = dataset
    patched, _s = W.wire(d, cf, report=quiet)
    assert len(patched) == len(WEEKS) * H


def test_slicing_picks_the_right_hours(dataset):
    """A CF frame numbered by hour proves which hours were taken."""
    _d, _cf, _g = dataset
    cf = pd.DataFrame({"village_1": np.arange(8760, dtype=float)})
    out = W.slice_weeks(cf, [2, 9], H)
    assert list(out["village_1"][:3]) == [168.0, 169.0, 170.0]        # week 2 starts at 168
    assert list(out["village_1"][H:H + 3]) == [1344.0, 1345.0, 1346.0]  # week 9 at 8*168
    assert len(out) == 2 * H


def test_overriding_weeks_warns_but_works(dataset):
    d, cf, _g = dataset
    msgs = []
    W.wire(d, cf, weeks=[1, 2], report=msgs.append)
    assert any("WARNING" in m and "demand.csv uses" in m for m in msgs)


def test_week_beyond_the_cf_file_is_an_error(dataset):
    _d, _cf, _g = dataset
    cf = pd.DataFrame({"village_1": [0.1] * 500})
    with pytest.raises(SystemExit):
        W.slice_weeks(cf, [52], H)


def test_missing_cf_column_is_an_error(dataset):
    d, _cf, _g = dataset
    bad = os.path.join(os.path.dirname(d), "bad_cf.csv")
    pd.DataFrame({"village_1": [0.1] * 8760}).to_csv(bad, index=False)
    with pytest.raises(SystemExit) as ex:
        W.wire(d, bad, report=quiet)
    assert "no matching CF column" in str(ex.value)


def test_out_of_range_cf_is_rejected(dataset):
    d, _cf, _g = dataset
    bad = os.path.join(os.path.dirname(d), "hot_cf.csv")
    pd.DataFrame({f"village_{v}": [1.4] * 8760 for v in VILLAGES}).to_csv(bad, index=False)
    with pytest.raises(SystemExit) as ex:
        W.wire(d, bad, report=quiet)
    assert "[0, 1]" in str(ex.value)


def test_hours_per_period_must_be_a_week(dataset):
    cf = pd.DataFrame({"village_1": [0.1] * 8760})
    with pytest.raises(SystemExit):
        W.slice_weeks(cf, [2], 24)


def test_real_timor_weeks_are_what_the_docs_claim():
    """Anchors the default against the shipped dataset rather than a constant."""
    weeks, P, hours = W.dataset_weeks(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data_indonesia", "2030", "timor"))
    assert weeks == [2, 9, 16, 24, 32, 40, 46, 52]
    assert (P, hours) == (8, 168)


def test_nusa_tenggara_uses_different_weeks():
    """The reason the weeks must not be a module constant."""
    weeks, _P, _H = W.dataset_weeks(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data_indonesia", "2030", "nusa_tenggara"))
    assert weeks == [24, 3, 4, 45, 8, 46, 39, 5]
    assert weeks != [2, 9, 16, 24, 32, 40, 46, 52]
