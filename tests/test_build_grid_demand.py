"""The Timor grid-demand derivation: weighted annualisation and the netting identity.

Two things here are load-bearing and easy to get silently wrong.

**Weighted vs naive annualisation.** The donor's eight representative weeks carry
non-uniform `Sub_Weights`, so summing rep hours and scaling by 8760/1344 gives
3,003 GWh/yr where the correct weighted figure is 2,919 — a 2.9 % overstatement
that would ride into every export number downstream.

**Positional variability lookup.** `input_data.jl` maps
`generators_variability.csv` columns to generators by position, and the donor
repeats 26 resource names (`plts_sumba` nine times), so its CSV has duplicate
headers and its column names stop matching its own generator order at position 9.
A by-name lookup silently wires the wrong solar profile onto a unit.

Solver-free; runs in CI.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.ntt import build_grid_demand as B

NA = dict(encoding="utf-8-sig", keep_default_na=False, na_values=[""])

TIMOR = B.dataset_path("2030", "timor")
DONOR = B.dataset_path("2030", "nusa_tenggara")

# Documented reference figures (data_indonesia/DATA_PROVENANCE.md, docs/ntt_data_integration.md)
DONOR_WEIGHTED_GWH = 2918.9
DONOR_NAIVE_GWH = 3003.0
VILLAGE_GWH = 544.1


def quiet(*_a, **_k):
    pass


# ------------------------------------------------------- annualisation arithmetic

def test_donor_weighted_and_naive_annualisation_differ_as_documented():
    _z, series, P, H, w = B.donor_profile(DONOR, None, B.DONOR_PROVINCE)
    weighted = B.annual_gwh(series, P, H, w)
    naive = B.naive_annual_gwh(series, P, H)
    assert weighted == pytest.approx(DONOR_WEIGHTED_GWH, abs=1.0)
    assert naive == pytest.approx(DONOR_NAIVE_GWH, abs=1.0)
    assert naive > weighted, "the naive figure must be the larger, wrong one"
    assert naive / weighted == pytest.approx(1.029, abs=0.002)


def test_donor_zone_resolves_from_the_province_column():
    """The donor ships no zones.csv; the identity comes from Province."""
    gens = pd.read_csv(os.path.join(DONOR, "generators.csv"), **NA)
    assert "zones.csv" not in os.listdir(DONOR)
    assert B.resolve_donor_zone(gens, None, B.DONOR_PROVINCE) == 2
    assert B.resolve_donor_zone(gens, None, "west_nusa_tenggara") == 1
    assert B.resolve_donor_zone(gens, 7, B.DONOR_PROVINCE) == 7, "explicit zone wins"


def test_unknown_province_is_an_error():
    gens = pd.read_csv(os.path.join(DONOR, "generators.csv"), **NA)
    with pytest.raises(SystemExit):
        B.resolve_donor_zone(gens, None, "atlantis")


def test_sub_weights_sum_to_a_year_in_both_datasets():
    for folder in (TIMOR, DONOR):
        d = pd.read_csv(os.path.join(folder, "demand.csv"), **NA)
        P, H, w = B.period_shape(d)
        assert (P, H) == (8, 168)
        assert w.sum() == pytest.approx(8760.0)


# --------------------------------------------------------------- netting identity

def test_netting_identity_and_nonnegativity():
    net, stats = B.build_demand(TIMOR, DONOR, 0.42, None, B.DONOR_PROVINCE, report=quiet)

    assert stats["village_annual_gwh"] == pytest.approx(VILLAGE_GWH, abs=0.5)
    assert stats["gross_annual_gwh"] == pytest.approx(0.42 * DONOR_WEIGHTED_GWH, abs=1.0)
    # the whole point: grid demand is the provincial share NET of village load,
    # which is already modelled as its own nodes
    assert stats["net_annual_gwh"] == pytest.approx(
        stats["gross_annual_gwh"] - stats["village_annual_gwh"], abs=0.5)
    assert stats["net_annual_gwh"] == pytest.approx(682.0, abs=1.0)

    # gross peak is share x the donor's own peak
    assert stats["gross_peak_mw"] == pytest.approx(0.42 * stats["donor_peak_mw"], rel=0.03)

    assert len(net) == 8 * 168
    assert (net >= 0).all(), "demand_z1 must never be negative"
    assert net.sum() > 0
    assert (net > 0).mean() > 0.99, "all but a handful of hours must carry real load"


def test_higher_share_removes_the_clipped_hours():
    """The zero hours are a share artifact, not a bug — they vanish as share rises."""
    _n_low, low = B.build_demand(TIMOR, DONOR, 0.33, None, B.DONOR_PROVINCE, report=quiet)
    _n_high, high = B.build_demand(TIMOR, DONOR, 0.47, None, B.DONOR_PROVINCE, report=quiet)
    assert low["negative_hours"] > high["negative_hours"]
    assert high["negative_hours"] == 0
    assert high["net_annual_gwh"] > low["net_annual_gwh"]


def test_grid_demand_is_not_zero_unlike_the_base_dataset():
    base = pd.read_csv(os.path.join(TIMOR, "demand.csv"), **NA)
    assert pd.to_numeric(base["demand_z1"], errors="coerce").sum() == 0, (
        "the base timor dataset is expected to have a zero grid load — that is the "
        "condition this tool exists to fix")
    net, _s = B.build_demand(TIMOR, DONOR, 0.42, None, B.DONOR_PROVINCE, report=quiet)
    assert net.sum() > 0


# ------------------------------------------------- positional variability lookup

def test_variability_column_is_positional_not_by_name():
    var = pd.DataFrame({"r_id": [1, 2], "a": [0.1, 0.1], "b": [0.2, 0.2], "c": [0.3, 0.3]})
    assert list(B.variability_column(var, 0)) == [0.1, 0.1]   # generator 1 -> column 1
    assert list(B.variability_column(var, 2)) == [0.3, 0.3]   # generator 3 -> column 3
    assert B.variability_column(var, 3) is None               # past the end -> pad flat


def test_donor_variability_names_do_not_match_its_generator_order():
    """Guards the reason the lookup must be positional."""
    gens = pd.read_csv(os.path.join(DONOR, "generators.csv"), **NA)
    var = pd.read_csv(os.path.join(DONOR, "generators_variability.csv"), **NA)
    names = list(var.columns[1:])
    resources = list(gens["Resource"].astype(str))
    assert names != resources[:len(names)], (
        "if the donor's variability headers ever line up with its generator order, "
        "revisit this test — but do NOT switch the tool to a by-name lookup")
    dups = gens["Resource"].astype(str).value_counts()
    assert (dups > 1).any(), "duplicate resource names are why by-name lookup breaks"


def test_unique_names_deduplicates_without_losing_columns():
    assert B.unique_names(["a", "b", "a", "a", "c"]) == ["a", "b", "a__2", "a__3", "c"]
    assert len(B.unique_names(["x"] * 9)) == 9
    assert len(set(B.unique_names(["x"] * 9))) == 9


# ------------------------------------------------------------------ cli contracts

def test_out_dataset_requires_an_explicit_fleet_choice():
    with pytest.raises(SystemExit) as ex:
        B.main(["--out-dataset", "timor__whatever"])
    assert "--fleet" in str(ex.value)


def test_share_must_be_a_fraction():
    for bad in ("0", "-0.1", "1.5"):
        with pytest.raises(SystemExit):
            B.main(["--share", bad])


def test_refuses_to_overwrite_the_base_dataset():
    net, _s = B.build_demand(TIMOR, DONOR, 0.42, None, B.DONOR_PROVINCE, report=quiet)
    with pytest.raises(SystemExit) as ex:
        B.write_dataset("timor", "timor", "2030", net, DONOR, 0.42, 2, "none",
                        "named", (), "target", report=quiet)
    assert "never" in str(ex.value).lower() or "differ" in str(ex.value).lower()
