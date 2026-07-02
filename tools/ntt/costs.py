"""IDR -> annualised USD cost conversion.

The source calculators (and the KDKMP workbook) quote equipment costs as
*overnight* capital in Indonesian Rupiah (Rp), per kWp for PV, per kWh for
batteries, etc. The capacity-expansion model expects **annualised investment
cost in USD per MW-year** (and per MWh-year for storage energy). This module is
the single place that conversion happens, so every calculator and the partner
documentation can point at one set of assumptions.

Conversion, per component:

    usd_per_kw   = idr_per_kw / FX_RATE          # Rp -> USD
    usd_per_mw   = usd_per_kw * 1000             # per-kW -> per-MW
    crf          = r (1+r)^n / ((1+r)^n - 1)     # capital recovery factor
    inv_per_mwyr = usd_per_mw * crf              # overnight -> annualised

All defaults are documented and overridable so a partner can re-run with their
own exchange rate / discount rate / asset lives.
"""

from __future__ import annotations

# ---- Default assumptions (override via CLI / function args) -----------------
FX_RATE = 16_000.0          # Rp per USD (mid-2024..2026 working assumption)
DISCOUNT_RATE = 0.10        # real discount rate for annualisation
LIFETIME_YEARS = {          # economic life per technology (years)
    "solar": 25,
    "battery": 12,
    "diesel": 15,
    "grid": 30,             # distribution / interconnection assets
}
FIXED_OM_FRACTION = {       # annual fixed O&M as a fraction of overnight capex
    "solar": 0.02,
    "battery": 0.02,
    "diesel": 0.03,
    "grid": 0.01,
}

# Grid-interconnection (MV feeder) cost assumptions. NTT working numbers —
# replace with PLN unit costs when available. Used by build_timor.py (provisional,
# centroid-distance), tools/connection_cost.py (hubdist_km-based refinement) and
# tools/make_timor_demo.py (stylised demo distances).
CONNECT_FIXED_IDR = 150_000_000      # Rp: fixed cost to tap the MV grid per village
CONNECT_IDR_PER_KM = 400_000_000     # Rp/km: MV feeder to the grid backbone
CONNECT_DEFAULT_KM = 10.0            # fallback when a village has no distance data
CONNECT_MAX_FACTOR = 1.5             # interconnection sized to peak demand x this
CONNECT_MAX_FLOOR_MW = 0.02          # ...but never below this


def crf(rate: float, years: int) -> float:
    """Capital recovery factor: fraction of overnight capex paid per year."""
    if rate == 0:
        return 1.0 / years
    f = (1.0 + rate) ** years
    return rate * f / (f - 1.0)


def annualise_idr_per_kw(idr_per_kw: float, tech: str,
                         fx: float = FX_RATE, rate: float = DISCOUNT_RATE) -> float:
    """Rp/kWp (or Rp/kW) overnight capital -> USD/MW-yr annualised investment."""
    usd_per_mw = (idr_per_kw / fx) * 1000.0
    return round(usd_per_mw * crf(rate, LIFETIME_YEARS[tech]))


def annualise_idr_per_kwh(idr_per_kwh: float, tech: str = "battery",
                          fx: float = FX_RATE, rate: float = DISCOUNT_RATE) -> float:
    """Rp/kWh overnight capital -> USD/MWh-yr annualised investment (storage energy)."""
    usd_per_mwh = (idr_per_kwh / fx) * 1000.0
    return round(usd_per_mwh * crf(rate, LIFETIME_YEARS[tech]))


def fixed_om_per_mwyr(idr_per_kw: float, tech: str, fx: float = FX_RATE) -> float:
    """Annual fixed O&M (USD/MW-yr) as a fraction of overnight capex."""
    usd_per_mw = (idr_per_kw / fx) * 1000.0
    return round(usd_per_mw * FIXED_OM_FRACTION[tech])


def idr_to_usd(idr: float, fx: float = FX_RATE) -> float:
    """Plain currency conversion (for reporting absolute capex in USD)."""
    return idr / fx


def connection_cost_per_yr(dist_km: float,
                           fixed_idr: float = CONNECT_FIXED_IDR,
                           idr_per_km: float = CONNECT_IDR_PER_KM,
                           fx: float = FX_RATE,
                           rate: float = DISCOUNT_RATE) -> int:
    """Annualised village grid-interconnection cost (USD/yr) from distance.

    Overnight capex = fixed tap cost + MV feeder length x cost/km, annualised
    with the grid-asset CRF. `dist_km` should be the distance to the nearest
    grid substation (`hubdist_km` from the siting pipeline) where known.
    Feeds `village_connection.csv::Cost_per_yr`, which gates the co-optimised
    connect-vs-island decision (`vVIL_CONNECT` in the objective).
    """
    capex_idr = fixed_idr + max(0.0, dist_km) * idr_per_km
    return round(idr_to_usd(capex_idr, fx) * crf(rate, LIFETIME_YEARS["grid"]))


def connect_max_mw(peak_mw: float,
                   factor: float = CONNECT_MAX_FACTOR,
                   floor_mw: float = CONNECT_MAX_FLOOR_MW) -> float:
    """Interconnection capacity cap (MW): peak demand x margin, floored."""
    return round(max(peak_mw * factor, floor_mw), 4)
