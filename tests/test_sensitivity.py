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
    pd.DataFrame({"Village": [1, 2], "Cost_per_yr": [10000, 50000],
                  "Max_Connect_MW": [0.1, 0.25]}) \
      .to_csv(os.path.join(folder, "village_connection.csv"), index=False)


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


def test_perturb_connection_cost_scales_cost_only(tmp_path):
    """The connect-vs-island price moves; the interconnection capacity does not."""
    f = str(tmp_path / "ds"); _dataset(f)
    sx.perturb_connection_cost(f, 0.0)
    c = pd.read_csv(os.path.join(f, "village_connection.csv"))
    assert list(c.Cost_per_yr) == [0.0, 0.0], "connection made free"
    assert list(c.Max_Connect_MW) == [0.1, 0.25], "capacity must be untouched"
    assert list(c.Village) == [1, 2]


def test_perturb_connect_cap_scales_cap_only(tmp_path):
    """Export headroom moves; the price of connecting does not."""
    f = str(tmp_path / "ds"); _dataset(f)
    sx.perturb_connect_cap(f, 20.0)
    c = pd.read_csv(os.path.join(f, "village_connection.csv"))
    assert list(c.Max_Connect_MW) == [2.0, 5.0]
    assert list(c.Cost_per_yr) == [10000, 50000], "cost must be untouched"


def test_connection_axes_are_independent(tmp_path):
    """Both applied together must not interfere — they are separate columns."""
    f = str(tmp_path / "ds"); _dataset(f)
    sx.perturb_connection_cost(f, 0.5)
    sx.perturb_connect_cap(f, 4.0)
    c = pd.read_csv(os.path.join(f, "village_connection.csv"))
    assert list(c.Cost_per_yr) == [5000.0, 25000.0]
    assert list(c.Max_Connect_MW) == [0.4, 1.0]


def test_connection_perturbations_are_noops_without_the_file(tmp_path):
    f = str(tmp_path / "ds"); _dataset(f)
    os.remove(os.path.join(f, "village_connection.csv"))
    sx.perturb_connection_cost(f, 0.0)     # must not raise
    sx.perturb_connect_cap(f, 5.0)
    assert not os.path.isfile(os.path.join(f, "village_connection.csv"))


def test_new_axes_are_registered():
    for axis in ("connection_cost", "connect_cap"):
        assert axis in sx.DATASET_AXES
        assert axis in sx.AXES
        assert axis in sx.PERTURB
    assert "battery_duration_h" in sx.CONFIG_AXES
    # every dataset axis must have a perturbation, or make_variant KeyErrors mid-sweep
    assert set(sx.DATASET_AXES) == set(sx.PERTURB)


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


def test_base_config_carries_lp_method():
    """Guards the sweep-vs-reference solver mismatch.

    base_config() previously omitted lp_method entirely, so every sweep ran at
    Gurobi Method=-1 (automatic) even when the reference run it is differenced
    against used Method=2 (barrier). On a model whose optimum is degenerate --
    e.g. the Timor scenarios at import_price=export_price=0, where the trade
    variables carry no objective coefficient -- two algorithms can return
    different vertices of the same optimal face, so the delta is not
    like-for-like. The default stays -1, preserving prior behaviour.
    """
    p = sx.build_parser()

    default = sx.base_config(p.parse_args(["run", "--island", "timor"]))
    assert default["lp_method"] == -1, "default must not change existing behaviour"

    barrier = sx.base_config(
        p.parse_args(["run", "--island", "timor", "--lp-method", "2"]))
    assert barrier["lp_method"] == 2

    # lp_method must survive the job generators too, or it is silently dropped.
    import re
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "generate_jobs_local.py")).read()
    keys = re.search(r"PASSTHROUGH_KEYS\s*=\s*\((.*?)\)", src, re.S).group(1)
    assert "'lp_method'" in keys or '"lp_method"' in keys


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
