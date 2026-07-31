"""Village battery power capex is priced, and priced consistently with the calculator.

Battery capex has a power component (Rp/kW — inverter/PCS) and an energy
component (Rp/kWh — cells). The power component used to be 0, so the optimiser
could buy unlimited charge/discharge MW against a priced MWh build and the
resulting storage duration floated instead of being an economic choice. These
tests pin the fix in both places it lives: the calculator that generates the
number, and the committed CSVs that carry it.

Also guards the `battery_fom_per_mwyr` benchmark, which used to ride on an
`or 1_000_000` fallback that only fired while the power capex was 0 — pricing the
power block would otherwise have moved fixed O&M 1250 -> 4088 $/MW-yr silently.

Solver-free; runs in CI.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.ntt import costs as C
from tools.ntt.calculators.base import Calculator

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NA = dict(encoding="utf-8-sig", keep_default_na=False, na_values=[""])

# The fishing calculator (a validated translation of the KDKMP workbook) prices
# its own battery; those rows legitimately differ from the default recipe.
FISHING_INV_PER_MWYR = 9173
FISHING_FOM_PER_MWYR = 5625

DEFAULT_FOM_PER_MWYR = 1250      # benchmarked to a 1 MRp/kW power block
DEFAULT_INV_PER_MWHYR = 41277    # energy component, unchanged by this work

DATASETS = ("timor", "timor_belu")


def village_storage_rows(island):
    path = os.path.join(REPO_ROOT, "data_indonesia", "2030", island,
                        "village_generators.csv")
    g = pd.read_csv(path, **NA)
    return g[pd.to_numeric(g["STOR"], errors="coerce") == 1]


def test_calculator_prices_battery_power():
    assert Calculator.battery_idr_per_kw > 0, "battery power capex must not be free"
    assert C.annualise_idr_per_kw(Calculator.battery_idr_per_kw, "battery") == 30001


def test_battery_fom_benchmark_is_pinned_not_derived():
    """FOM must not move when the power capex changes."""
    src = open(os.path.join(REPO_ROOT, "tools", "ntt", "calculators", "base.py"),
               encoding="utf-8").read()
    assert 'battery_fom_per_mwyr=C.fixed_om_per_mwyr(1_000_000, "battery")' in src, (
        "the battery FOM benchmark must be the explicit 1 MRp/kW literal; deriving it "
        "from battery_idr_per_kw silently changes fixed O&M whenever capex changes"
    )
    assert C.fixed_om_per_mwyr(1_000_000, "battery") == DEFAULT_FOM_PER_MWYR


def test_calculator_costs_are_self_consistent():
    from tools.ntt.calculators.base import SizingResult

    cost = Calculator().costs(SizingResult(solar_kwp=100.0, battery_kwh=200.0,
                                           diesel_mw=0.1))
    assert cost.battery_inv_per_mwyr == 30001
    assert cost.battery_fom_per_mwyr == DEFAULT_FOM_PER_MWYR
    assert cost.battery_inv_per_mwhyr == DEFAULT_INV_PER_MWHYR


@pytest.mark.parametrize("island", DATASETS)
def test_no_committed_storage_row_has_free_power(island):
    s = village_storage_rows(island)
    inv = pd.to_numeric(s["Inv_Cost_per_MWyr"], errors="coerce")
    assert len(s) > 0
    assert (inv > 0).all(), (
        f"{island}: {int((inv <= 0).sum())} storage row(s) still price battery power at 0"
    )


@pytest.mark.parametrize("island", DATASETS)
def test_committed_battery_costs_match_the_calculator(island):
    s = village_storage_rows(island)
    inv = pd.to_numeric(s["Inv_Cost_per_MWyr"], errors="coerce")
    fom = pd.to_numeric(s["Fixed_OM_Cost_per_MWyr"], errors="coerce")
    mwh = pd.to_numeric(s["Inv_Cost_per_MWhyr"], errors="coerce")

    default = inv != FISHING_INV_PER_MWYR
    fishing = ~default

    assert (inv[default] == 30001).all(), "default-recipe rows must carry the calculator value"
    assert (fom[default] == DEFAULT_FOM_PER_MWYR).all(), "fixed O&M must not have moved"
    assert (mwh[default] == DEFAULT_INV_PER_MWHYR).all(), "energy capex must not have moved"

    # the fishing rows are a different recipe and must survive untouched
    assert fishing.sum() > 0, f"{island} should still have fishing-archetype battery rows"
    assert (fom[fishing] == FISHING_FOM_PER_MWYR).all()


def test_fishing_row_counts_are_unchanged():
    """A blanket column overwrite would have flattened these; keep the count pinned."""
    assert (pd.to_numeric(village_storage_rows("timor")["Inv_Cost_per_MWyr"],
                          errors="coerce") == FISHING_INV_PER_MWYR).sum() == 7
    assert (pd.to_numeric(village_storage_rows("timor_belu")["Inv_Cost_per_MWyr"],
                          errors="coerce") == FISHING_INV_PER_MWYR).sum() == 3
