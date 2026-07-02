"""Tests for the report's language support (--lang en/id).

Checks the string tables stay in lockstep and that metrics() labels follow the
selected language. Deliberately avoids matplotlib/jinja2 (CI installs neither);
the full render path is exercised manually / in the demo walkthrough.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.report import STRINGS, metrics


def test_string_tables_have_identical_keys():
    assert set(STRINGS) == {"en", "id"}
    assert STRINGS["en"].keys() == STRINGS["id"].keys()
    # no empty translations
    for lang, table in STRINGS.items():
        for k, v in table.items():
            assert isinstance(v, str) and v.strip(), f"{lang}:{k} is empty"


def _results():
    return {
        "cost_results": pd.DataFrame({"Total_Costs": [418.75]}),
        "clean_energy_results": pd.DataFrame(
            {"CO2_Emissions": [889909.7], "Grid_REShare": [0.25]}),
        "reliability_results": pd.DataFrame({"Total_NSE_MWh": [1000.0, 2000.0]}),
    }


def test_metrics_labels_follow_language():
    m_en = metrics(_results(), ad_gwh=100.0, lang="en")
    m_id = metrics(_results(), ad_gwh=100.0, lang="id")
    assert m_en["cost"][2] == "Total system cost"
    assert m_id["cost"][2] == "Total biaya sistem"
    assert m_id["unserved"][2] == "Energi tak terlayani"
    # same metrics, same values — only labels differ
    assert m_en.keys() == m_id.keys()
    for k in m_en:
        assert m_en[k][0] == m_id[k][0]
        assert m_en[k][1] == m_id[k][1]


def test_default_language_is_english():
    m = metrics(_results())
    assert m["cost"][2] == "Total system cost"
