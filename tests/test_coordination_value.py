"""Unit tests for tools/coordination_value.py — no solver, synthetic result dirs.

Exercises the metric deltas, the site/village prefix fallback, the engine guard
(the check that would have caught a stale expansion-vs-dispatch pair), and the
annualisation factor. Solver-free, so it runs in CI.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import coordination_value as cv


def _write(path, header, *rows):
    with open(path, "w") as fh:
        fh.write(header + "\n")
        for r in rows:
            fh.write(",".join(str(x) for x in r) + "\n")


def _make_run(root, name, engine, *, total_cost, co2, site_gen_prefix="site",
              connected=0, diesel_gwh=0.0, config=True):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    _write(os.path.join(d, "cost_results.csv"),
           "Total_Costs,Fixed_Costs_Transmission,Fixed_Costs_Village,"
           "Fixed_Costs_Village_Storage,Variable_Costs_Grid,NSE_Costs",
           (total_cost, 0.0, 1.0, 0.5, total_cost - 1.5, 0.0))
    _write(os.path.join(d, "clean_energy_results.csv"),
           "CO2_Emissions,CO2_Emissions_Grid,CO2_Emissions_Village,Grid_REShare",
           (co2, co2, 0.0, 0.3))
    _write(os.path.join(d, "generator_results.csv"),
           "ID,Resource,Zone,technology,Total_MW,Start_MW,Change_in_MW,GWh,THERM",
           (1, "pltd_x", 1, "diesel", 1.0, 1.0, 0.0, diesel_gwh, 1),
           (2, "plts_x", 1, "solar", 2.0, 0.0, 2.0, 5.0, 0))
    # site layer under the requested prefix
    _write(os.path.join(d, f"{site_gen_prefix}_generator_results.csv"),
           "ID,Resource,Zone,Village,technology,Total_MW,Start_MW,Change_in_MW,Electricity_GWh",
           (1, "plts_v", 1, 1, "solar", 0.5, 0.0, 0.5, 1.2))
    _write(os.path.join(d, f"{site_gen_prefix}_connection_results.csv"),
           "ID,Zone,Connected,Total_Import_MWh,Total_Export_MWh",
           (1, 1, connected, 3.0 if connected else 0.0, 0.0))
    if engine == "dispatch":
        _write(os.path.join(d, "reliability_results.csv"),
               "Zone,Zone_Name,Total_NSE_MWh,NSE_Percent_of_Demand,LOLE_hours,Peak_Shortage_MW",
               (1, "z", 10.0, 1.0, 4.0, 2.0))
    if config:
        import json
        with open(os.path.join(root, name + ".config.json"), "w") as fh:
            json.dump({"engine": engine, "solver": "highs", "relax_uc": True}, fh)
    return d


def _demand(root, year, island):
    folder = os.path.join(root, year, island)
    os.makedirs(folder, exist_ok=True)
    # 2 rep periods x 4 h, uniform weights -> factor 8760/8 = 1095
    _write(os.path.join(folder, "demand.csv"),
           "Rep_Periods,Timesteps_per_Rep_Period,Sub_Weights,demand_z1",
           (2, 4, 4380, 100), ("", "", 4380, 100))


def test_coordination_value_positive(tmp_path):
    root = str(tmp_path / "results")
    data = str(tmp_path / "data")
    _demand(data, "2030", "demo")
    ref = _make_run(root, "village_demo_2030_reference", "expansion",
                    total_cost=100.0, co2=1000.0, connected=0)
    coord = _make_run(root, "gridvillage_demo_2030_reference", "expansion",
                      total_cost=90.0, co2=800.0, connected=1)
    rc = cv.compare(ref, coord, data)
    assert rc == 0
    out = os.path.join(coord, "coordination_value.csv")
    assert os.path.isfile(out)
    import pandas as pd
    df = pd.read_csv(out).set_index("Metric")
    # CV = 100 - 90 = 10 M$/yr on the Total system cost row
    assert abs(df.loc["Total system cost", "Delta_Ref_minus_Coord"] - 10.0) < 1e-9
    assert abs(df.loc["CO₂ emissions", "Delta_Ref_minus_Coord"] - 200.0) < 1e-9


def test_engine_mismatch_guard(tmp_path):
    """A stale expansion-vs-dispatch pair must be refused (exit 2)."""
    root = str(tmp_path / "results")
    data = str(tmp_path / "data")
    _demand(data, "2030", "demo")
    ref = _make_run(root, "village_demo_2030_reference", "expansion",
                    total_cost=100.0, co2=1000.0)
    coord = _make_run(root, "gridvillage_demo_2030_reference", "dispatch",
                      total_cost=90.0, co2=800.0)
    assert cv.compare(ref, coord, data) == 2
    # ...unless explicitly overridden
    assert cv.compare(ref, coord, data, allow_mismatch=True) == 0


def test_island_mismatch_guard(tmp_path):
    root = str(tmp_path / "results")
    data = str(tmp_path / "data")
    _demand(data, "2030", "demo")
    ref = _make_run(root, "village_demo_2030_reference", "expansion",
                    total_cost=100.0, co2=1000.0)
    coord = _make_run(root, "gridvillage_other_2030_reference", "expansion",
                      total_cost=90.0, co2=800.0)
    assert cv.compare(ref, coord, data) == 2


def test_site_prefix_fallback(tmp_path):
    """A run whose site tables use the village_ prefix still loads."""
    root = str(tmp_path / "results")
    data = str(tmp_path / "data")
    _demand(data, "2030", "demo")
    ref = _make_run(root, "village_demo_2030_reference", "expansion",
                    total_cost=100.0, co2=1000.0, site_gen_prefix="village")
    coord = _make_run(root, "gridvillage_demo_2030_reference", "expansion",
                      total_cost=90.0, co2=800.0, site_gen_prefix="village",
                      connected=1)
    assert cv.compare(ref, coord, data) == 0
    import pandas as pd
    df = pd.read_csv(os.path.join(coord, "coordination_value.csv")).set_index("Metric")
    assert df.loc["villages grid-connected", "Coordinated"] == 1


def test_annualisation_factor(tmp_path):
    """The 8760/T helper still reports the rep-period structure correctly."""
    data = str(tmp_path / "data")
    _demand(data, "2030", "demo")
    factor, note = cv.annualisation({"year": "2030", "island": "demo"}, data, quiet=True)
    assert abs(factor - 1095.0) < 1e-9   # 8760 / (2*4)
    assert "uniform" in note


def test_energy_metrics_are_not_annualised_twice(tmp_path):
    """Result CSVs are annual at source, so load_metrics must NOT re-scale them.

    result_extraction_function.jl weights every rep-period energy sum by
    sample_weight. Multiplying by 8760/T here as well would inflate every energy
    metric by that factor again — 6.518x on Timor — and it would look plausible.
    """
    root = str(tmp_path / "results")
    data = str(tmp_path / "data")
    _demand(data, "2030", "demo")
    # 8760/T for this fixture is 1095, so a double-count would be unmistakable
    run = _make_run(root, "gridvillage_demo_2030_reference", "dispatch",
                    total_cost=90.0, co2=800.0, site_gen_prefix="village",
                    connected=1, diesel_gwh=7.0)
    _meta, m, notes = cv.load_metrics(run, data)

    assert abs(m["grid_diesel_gwh"] - 7.0) < 1e-9, (
        f"grid diesel GWh is {m['grid_diesel_gwh']}, not the 7.0 written to the CSV — "
        "a post-hoc 8760/T factor would double-count the sample weighting that "
        "result extraction already applies")
    assert abs(m["grid_nse_mwh"] - 10.0) < 1e-9
    assert any("annual" in n for n in notes)
