"""Every optional config key the model reads must survive job generation.

The job generators copy a whitelist of optional keys from the scenario YAML into
each job's `config.json`. When the whitelist falls behind the model, the failure
is silent and expensive: the YAML sets `export_price: 40`, the key never reaches
`config.json`, the model solves at `0.0`, and every result CSV looks normal. So
the first test here reads the *model* for the optional keys it accepts
(`get(cfg, "...")` in `run_model.jl` and `functions/preflight.jl`) and asserts
both generators' whitelists cover them — a structural guard, not a snapshot.

Also covers the `run_tag` results-folder suffix, which must be built identically
by `functions/preflight.jl`, `tools/launcher.py` and `tools/sensitivity.py` or a
run's `<name>.config.json` sidecar stops matching its results folder.

Solver-free; runs in CI.
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import generate_jobs
import generate_jobs_local
from tools import launcher, sensitivity

# `get(cfg, "key", default)` — and the one `get(JSON.parsefile(path), "solver", ...)`
# in run_model.jl, which reads the solver before the config is loaded properly.
OPTIONAL_KEY_RE = re.compile(r'get\((?:cfg|JSON\.parsefile\([^)]*\))\s*,\s*"([A-Za-z_0-9]+)"')

MODEL_SOURCES = ("run_model.jl", os.path.join("functions", "preflight.jl"))


def model_optional_keys():
    keys = set()
    for rel in MODEL_SOURCES:
        with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as fh:
            keys.update(OPTIONAL_KEY_RE.findall(fh.read()))
    return keys


def test_model_optional_keys_are_found():
    """Guard the guard: if the regex stops matching, the test below goes vacuous."""
    keys = model_optional_keys()
    assert len(keys) >= 8, f"expected the model's optional config keys, found {keys}"
    # spot-check the keys whose omission caused the original silent-drop bug
    assert {"export_price", "policy_scope", "engine", "relax_uc"} <= keys


@pytest.mark.parametrize("module", [generate_jobs, generate_jobs_local],
                         ids=["generate_jobs", "generate_jobs_local"])
def test_passthrough_covers_every_optional_model_key(module):
    missing = model_optional_keys() - set(module.PASSTHROUGH_KEYS)
    assert not missing, (
        f"{module.__name__}.PASSTHROUGH_KEYS is missing {sorted(missing)}; a scenario "
        "YAML setting those keys would be silently dropped and the run would solve "
        "at the model default"
    )


@pytest.mark.parametrize("module", [generate_jobs, generate_jobs_local],
                         ids=["generate_jobs", "generate_jobs_local"])
def test_passthrough_keys_are_all_read_by_the_model(module):
    """No dead entries either — a key nothing reads is a documentation bug."""
    extra = set(module.PASSTHROUGH_KEYS) - model_optional_keys()
    assert not extra, f"{module.__name__}.PASSTHROUGH_KEYS has unread keys {sorted(extra)}"


def test_both_generators_agree():
    assert set(generate_jobs.PASSTHROUGH_KEYS) == set(generate_jobs_local.PASSTHROUGH_KEYS)


# ------------------------------------------------------------------- run_tag

def preflight_suffix_template():
    """The literal results-dir name built by functions/preflight.jl."""
    with open(os.path.join(REPO_ROOT, "functions", "preflight.jl"), encoding="utf-8") as fh:
        src = fh.read()
    assert 'tag_suffix = isempty(run_tag) ? "" : "__$(run_tag)"' in src
    # the tag must land after `clean` so tools/report.py::parse_scenario still
    # resolves the island from <scenario>_<island...>_<year>_<clean>
    assert '_$(cfg["clean"])$(tag_suffix)' in src
    return True


def test_preflight_builds_the_documented_suffix():
    assert preflight_suffix_template()


def test_parse_scenario_survives_the_suffix():
    from tools.report import parse_scenario
    meta = parse_scenario("results/gridvillage_timor_2030_reference__export_price40")
    assert meta["scenario"] == "gridvillage"
    assert meta["island"] == "timor"
    assert meta["year"] == "2030"
    assert meta["clean"] == "reference"


def test_sensitivity_run_name_matches_the_sidecar(tmp_path):
    cfg = {"scenario": "gridvillage", "island": "timor", "year": "2030",
           "clean": "reference", "run_tag": "export_price40"}
    # run_one writes the sidecar then shells out to julia; only the naming is
    # under test, so check the path it derives rather than executing the run.
    name = (f"{cfg['scenario']}_{cfg['island']}_{cfg['year']}_{cfg['clean']}"
            f"__{cfg['run_tag']}")
    assert name == "gridvillage_timor_2030_reference__export_price40"
    src = open(os.path.join(REPO_ROOT, "tools", "sensitivity.py"), encoding="utf-8").read()
    assert 'f"__{tag}" if tag else ""' in src


def test_sensitivity_tags_config_only_variants():
    """Config-axis runs must get a run_tag, or they all overwrite one folder."""
    src = open(os.path.join(REPO_ROOT, "tools", "sensitivity.py"), encoding="utf-8").read()
    assert 'cfg["run_tag"] = "_".join(' in src
    assert "CONFIG_AXES" in src


def test_launcher_run_tag_is_optional():
    class Args:
        island, year, scenario, clean = "timor", "2030", "gridvillage", "reference"
        engine, solver, relax_uc, mipgap = "expansion", "highs", True, 0.01
        co2_limit, bau, run_tag = 1.0e12, 0.0, ""

    cfg = launcher.build_config(Args())
    assert "run_tag" not in cfg, "an empty tag must not be written into config.json"

    Args.run_tag = "  cc0.0  "
    cfg = launcher.build_config(Args())
    assert cfg["run_tag"] == "cc0.0", "the tag must be stripped, matching preflight.jl"


def test_shipped_scenario_yamls_only_set_keys_that_survive():
    """A YAML key outside PASSTHROUGH_KEYS is silently dropped — the D1 failure mode.

    Guards the scenario files themselves, not just the generators: it is just as
    easy to write `export_price: 40` into a YAML that the generator will ignore.
    """
    import glob

    import yaml

    structural = {"islands", "years", "scenarios", "cleans", "island_params", "co2_limits"}
    allowed = set(generate_jobs.PASSTHROUGH_KEYS)
    offenders = {}
    files = sorted(glob.glob(os.path.join(REPO_ROOT, "scenario_*.yml")))
    assert files, "expected shipped scenario YAMLs"
    for path in files:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        dropped = sorted(set(data) - structural - allowed)
        if dropped:
            offenders[os.path.basename(path)] = dropped
    assert not offenders, (
        f"these scenario YAMLs set keys the job generators drop: {offenders}. "
        "Either add the key to PASSTHROUGH_KEYS (and make the model read it) or "
        "remove it from the YAML — as written it does nothing."
    )


def test_coordination_scenarios_come_in_pairs():
    """Coordination value is a difference, so a lone `gridvillage` answers nothing."""
    import yaml

    for name in ("scenario_timor.yml", "scenario_timor_market.yml"):
        path = os.path.join(REPO_ROOT, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            scenarios = set(yaml.safe_load(fh)["scenarios"])
        assert {"village", "gridvillage"} <= scenarios, (
            f"{name} runs {sorted(scenarios)}; the OFF/ON pair is needed to compute "
            "a coordination value at all"
        )


def test_generate_jobs_writes_optional_keys(tmp_path, monkeypatch):
    """End-to-end: a YAML key in the whitelist reaches the job's config.json."""
    from click.testing import CliRunner

    scen = tmp_path / "scenarios.yml"
    scen.write_text(
        "islands: [timor]\nyears: ['2030']\nscenarios: [gridvillage]\n"
        "cleans: [reference]\nisland_params: {timor: 0.0}\n"
        "co2_limits: {'2030': {timor: 1.0e12}}\n"
        "export_price: 40\npolicy_scope: system\nengine: expansion\n"
        "relax_uc: false\nsolver: gurobi\nrun_tag: xp40\nmipgap: 0.005\n"
    )
    submit = tmp_path / "submit_test.sb"
    submit.write_text("#!/bin/bash\n")
    out = tmp_path / "jobs"

    res = CliRunner().invoke(generate_jobs.main, [
        "-s", str(scen), "-b", str(submit), "-o", str(out),
    ])
    assert res.exit_code == 0, res.output

    job = out / "gridvillage_timor_2030_reference__xp40"
    assert job.is_dir(), f"run_tag must suffix the job folder; got {list(out.iterdir())}"
    cfg = json.loads((job / "config.json").read_text())
    assert cfg["export_price"] == 40
    assert cfg["policy_scope"] == "system"
    assert cfg["relax_uc"] is False
    assert cfg["solver"] == "gurobi"
    assert cfg["run_tag"] == "xp40"
    assert cfg["mipgap"] == 0.005
