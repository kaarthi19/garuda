"""Developable-land allocation: conserve the total, starve nobody, cap nothing wrongly.

The failure modes this guards are all quantitative rather than crashes:

- a **buffer** counts the same hectare for every village in range. The caps it
  produced summed to 2,472 GW against an island total of 197 GW — 13x the land
  that exists.
- **nearest-village** assignment conserves the total but starves any village that
  is never the closest: 178 of 627 located villages got nothing while a neighbour
  a few hundred metres away got hundreds of MW.
- a village left at **0** is read by the model as *unbounded* (`optimizer.jl`:
  `Max_Cap_MW == 0` means no land data), so a "no land" village silently becomes
  the least constrained one.

Solver-free; runs in CI. The 368 MB source layer is NOT required — the geometry
here is synthetic.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.ntt import usable_land as UL


def poly(xs, ys, areas):
    return dict(x=list(xs), y=list(ys), area=list(areas),
                cover=["Savannah"] * len(xs), kab=["Belu"] * len(xs))


def quiet(*_a, **_k):
    pass


# ------------------------------------------------------------------ allocation

def test_shared_allocation_conserves_total():
    """The sum over villages must equal the land, not a multiple of it."""
    p = poly([0, 1000, 2000], [0, 0, 0], [100.0, 200.0, 300.0])
    # three villages, all within radius of everything
    alloc, unalloc, allocated = UL.allocate(p, [0, 1000, 2000], [0, 0, 0], [1, 2, 3],
                                            max_radius_km=50, mode="shared", report=quiet)
    assert sum(alloc.values()) == pytest.approx(600.0)
    assert allocated == pytest.approx(600.0)
    assert unalloc == pytest.approx(0.0)


def test_shared_allocation_starves_nobody():
    """Every village within reach of land gets some — the nearest-mode failure."""
    # two villages 200 m apart; all the land sits beside village 1
    p = poly([0, 10, 20], [0, 0, 0], [90.0, 90.0, 90.0])
    shared, _u, _a = UL.allocate(p, [0, 200], [0, 0], [1, 2],
                                 max_radius_km=50, mode="shared", report=quiet)
    nearest, _u2, _a2 = UL.allocate(p, [0, 200], [0, 0], [1, 2],
                                    max_radius_km=50, mode="nearest", report=quiet)
    assert set(shared) == {1, 2}, "shared must reach both villages"
    assert shared[1] == pytest.approx(shared[2]), "equal split within the radius"
    assert set(nearest) == {1}, "nearest mode is expected to starve village 2"
    # both conserve the total
    assert sum(shared.values()) == pytest.approx(sum(nearest.values()))


def test_nearest_mode_conserves_total_too():
    p = poly([0, 5000], [0, 0], [10.0, 20.0])
    alloc, unalloc, _a = UL.allocate(p, [0, 5000], [0, 0], [1, 2],
                                     max_radius_km=50, mode="nearest", report=quiet)
    assert sum(alloc.values()) + unalloc == pytest.approx(30.0)


def test_land_beyond_the_radius_is_reported_not_dropped_silently():
    p = poly([0, 500_000], [0, 0], [10.0, 40.0])
    alloc, unalloc, allocated = UL.allocate(p, [0], [0], [1],
                                            max_radius_km=10, mode="shared", report=quiet)
    assert alloc[1] == pytest.approx(10.0)
    assert unalloc == pytest.approx(40.0), "distant land must surface as unallocated"
    assert allocated + unalloc == pytest.approx(50.0)


def test_no_villages_leaves_everything_unallocated():
    p = poly([0], [0], [7.0])
    alloc, unalloc, allocated = UL.allocate(p, [], [], [], max_radius_km=10, report=quiet)
    assert alloc == {} and unalloc == pytest.approx(7.0) and allocated == 0.0


def test_empty_layer_is_not_an_error():
    alloc, unalloc, allocated = UL.allocate(poly([], [], []), [0], [0], [1],
                                            max_radius_km=10, report=quiet)
    assert alloc == {} and allocated == 0.0


# -------------------------------------------------------------- shipped output

LAND_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data_indonesia", "2030", "timor", "village_solar_land.csv")


@pytest.mark.skipif(not os.path.isfile(LAND_CSV), reason="land CSV not generated")
def test_shipped_land_table_is_sane():
    import pandas as pd

    df = pd.read_csv(LAND_CSV, comment="#")
    assert len(df) == 780, "one row per village, including the un-located ones"
    assert set(df.columns) >= {"Village", "developable_km2", "developable_MW", "source"}
    assert (df["developable_MW"] > 0).all(), (
        "a village at 0 is read by the model as UNBOUNDED, which is the opposite "
        "of a land cap — un-located villages must take the median fallback")
    assert df["Village"].is_unique


@pytest.mark.skipif(not os.path.isfile(LAND_CSV), reason="land CSV not generated")
def test_caps_are_far_above_village_peak_but_below_the_old_overcount():
    """The caps should still not bind, but should no longer exceed the island."""
    import pandas as pd

    df = pd.read_csv(LAND_CSV, comment="#")
    # village coincident peak is ~128 MW across 780 villages; per village ~0.16 MW
    assert df["developable_MW"].median() > 1.0, "still comfortably non-binding"
    # the previous per-village caps summed to ~2,472 GW against ~197 GW of land
    assert df["developable_MW"].sum() / 1000 < 400, (
        "total developable MW must stay the same order as the island's usable land; "
        "a buffer-style over-count shows up here")


@pytest.mark.skipif(not os.path.isfile(LAND_CSV), reason="land CSV not generated")
def test_provenance_header_records_the_land_assumption():
    """The land filter decides the headline, so it must travel with the numbers."""
    head = "".join(open(LAND_CSV).readlines()[:3])
    assert head.startswith("#")
    for key in ("region=", "excluded_classes=", "mwp_per_km2=", "max_radius_km="):
        assert key in head, f"missing {key} in the provenance header"
