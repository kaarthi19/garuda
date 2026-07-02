"""Unit tests for the sensitivity harness — perturbations, plans, summary.

Solver-free: builds a tiny dataset in tmp_path, applies the perturbation
functions, and checks the sweep plan and summary logic. The end-to-end solve
path is validated manually on timor_demo (see docs/sensitivity.md).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import sensitivity as sx


def _dataset(folder):
    os.makedirs(folder, exist_ok=True)
    pd.DataFrame({"Fuel": ["None", "diesel"], "Cost_per_MMBtu": [0.0, 18.0],
                  "CO2_content_tons_per_MMBtu": [0.0, 0.0732]}) \
      .to_csv(os.path.join(folder, "fuels_data.csv"), index=False)
    pd.DataFrame({"r_id": [1, 2], "demand_z1": [10.0, 20.0], "demand_z2": [5.0, 5.0]}) \
      .to_csv(os.path.join(folder, "demand.csv"), index=False)
    pd.DataFrame({"r_id": [1, 2], "demand_village1": [1.0, 2.0]}) \
      .to_csv(os.path.join(folder, "village_demand.csv"), index=False)
    pd.DataFrame({"R_ID": [1, 2], "Resource": ["pltd_x", "plts_x"],
                  "technology": ["diesel", "solar"]}) \
      .to_csv(os.path.join(folder, "generators.csv"), index=False)
    pd.DataFrame({"r_id": [1, 2], "pltd_x": [1.0, 1.0], "plts_x": [0.6, 0.9]}) \
      .to_csv(os.path.join(folder, "generators_variability.csv"), index=False)


def test_perturb_fuel_skips_none(tmp_path):
    f = str(tmp_path / "ds"); _dataset(f)
    sx.perturb_fuel(f, 1.5)
    out = pd.read_csv(os.path.join(f, "fuels_data.csv"), keep_default_na=False)
    assert float(out.loc[out.Fuel == "diesel", "Cost_per_MMBtu"].iloc[0]) == 27.0
    assert float(out.loc[out.Fuel == "None", "Cost_per_MMBtu"].iloc[0]) == 0.0


def test_perturb_demand_scales_all_layers(tmp_path):
    f = str(tmp_path / "ds"); _dataset(f)
    sx.perturb_demand(f, 1.1)
    d = pd.read_csv(os.path.join(f, "demand.csv"))
    v = pd.read_csv(os.path.join(f, "village_demand.csv"))
    assert float(d.demand_z1.iloc[0]) == 11.0 and float(d.demand_z2.iloc[1]) == 5.5
    assert float(v.demand_village1.iloc[1]) == 2.2
    assert list(d.r_id) == [1, 2]  # index column untouched


def test_perturb_solar_cf_clips_and_targets_solar_only(tmp_path):
    f = str(tmp_path / "ds"); _dataset(f)
    sx.perturb_solar_cf(f, 1.5)
    v = pd.read_csv(os.path.join(f, "generators_variability.csv"))
    assert abs(float(v.plts_x.iloc[0]) - 0.9) < 1e-12   # 0.6*1.5
    assert float(v.plts_x.iloc[1]) == 1.0               # 0.9*1.5 clipped
    assert list(v.pltd_x) == [1.0, 1.0]                 # non-solar untouched


def test_make_variant_copies_and_tags(tmp_path):
    root = str(tmp_path / "data"); base = os.path.join(root, "2030", "demo")
    _dataset(base)
    variant = sx.make_variant(root, "2030", "demo", [("fuel", 1.2)])
    assert variant == "demo__fuel1.2"
    vf = pd.read_csv(os.path.join(root, "2030", variant, "fuels_data.csv"))
    bf = pd.read_csv(os.path.join(base, "fuels_data.csv"))
    assert float(vf.loc[1, "Cost_per_MMBtu"]) == 21.6
    assert float(bf.loc[1, "Cost_per_MMBtu"]) == 18.0   # base untouched


def test_build_plan_oat_and_grid():
    params = {"fuel": [0.8, 1.2], "demand": [1.1]}
    oat = sx.build_plan(params, full_grid=False)
    assert [t for t, _ in oat] == ["base", "demand1.1", "fuel0.8", "fuel1.2"]
    grid = sx.build_plan(params, full_grid=True)
    tags = [t for t, _ in grid]
    # axes implicitly include 1.0: {0.8,1.0,1.2} x {1.0,1.1} = 6 combos = base + 5
    assert "base" in tags and "demand1.1_fuel0.8" in tags and "fuel0.8" in tags
    assert len(grid) == 6
    # a 1.0 multiplier is the base case, not a separate run
    assert sx.build_plan({"fuel": [1.0]}, False) == [("base", {})]


def test_parse_params_validates_axis():
    assert sx.parse_params(["fuel=0.8,1.2"]) == {"fuel": [0.8, 1.2]}
    try:
        sx.parse_params(["nonsense=2"])
        assert False, "should reject unknown axis"
    except SystemExit:
        pass


def test_summarise_ranges(tmp_path):
    df = pd.DataFrame([
        {"run": "base", "Total_Costs": 100.0, "CO2_Emissions": 1000.0},
        {"run": "fuel1.2", "Total_Costs": 110.0, "CO2_Emissions": 980.0},
        {"run": "demand0.9", "Total_Costs": 95.0, "CO2_Emissions": 900.0},
    ])
    csv_path, md_path = sx.summarise(df, str(tmp_path))
    assert os.path.isfile(csv_path)
    md = open(md_path).read()
    assert "range 95.000 – 110.000" in md
    assert "largest move: `demand0.9`" in md or "largest move: `fuel1.2`" in md
