# Garuda — Development Log

**Garuda** is an open-source, stakeholder-facing **zonal energy-transition
platform for Indonesia**. It is being built on the zonal power-system model
inherited from `village-indonesia-100gw`, evolving that research model into a
layered platform:

- **Layer A — Data Core:** the zonal model itself (zones, transmission,
  generators, demand, RE resource, sites, fuels, costs) as a standalone,
  validated, documented asset — engine-agnostic.
- **Layer B — Engines:** capacity expansion (inherited), dispatch/reliability,
  no-solve accounting, RE resource & siting, and open-format (PyPSA) export.
- **Layer C — Experience:** a thin guided on-ramp (validation + auto-reports).

Design rules: engines never own the data; the experience layer never wires
straight to the optimizer. Open-source-first (HiGHS default; Gurobi optional).

**This file is the authoritative, chronological record** of every change made
while building the platform. Each entry says *what*, *why*, and *how to verify*.

---

## Phase 0 — Stand up the platform repo + name the data core

### 0.1 Snapshot-fork from `village-indonesia-100gw` — 2026-06-26

Created `garuda` as a **clean snapshot-fork** (no upstream git history) of
`village-indonesia-100gw` at commit
`1096aa48ff5829e7679a1252b2b84a2b79d07750` (`1096aa4`, *"Add GIS solar-land
resource assessment; wire per-village solar caps"*).

**Why a fork rather than changes in place or a branch.** The source repo is an
active research project; the platform must develop in complete separation and
will diverge architecturally (de-monolithing the optimizer, multiple engines).
`village-indonesia-100gw` is left **untouched**; future data/model fixes there
flow into garuda only by deliberate cherry-pick. Once the data core stabilises,
the shared model may be factored into a Julia package both repos can use
(deferred decision).

**Copied in:** `functions/`, `tools/`, `data_indonesia/`, `docs/`, `templates/`,
`tests/`, `scenario_*.yml`, `generate_jobs*.py`, `run_model.jl`, `bootstrap.jl`,
`Project.toml`, `Manifest.toml`, `README.md`, `MODEL.md`, `LICENSE`.

**Excluded:** `.git` (garuda has its own), `jobs/` and `results/` (run artifacts
— now gitignored), `.claude` and `.DS_Store` (local cruft), `__pycache__/`,
`*.pyc`, `*.log`.

**Command:**
```bash
rsync -a --exclude='.git' --exclude='jobs' --exclude='results' \
  --exclude='.claude' --exclude='.DS_Store' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='*.log' \
  .../village-indonesia-100gw/ .../garuda/
```

**Also:** added `jobs/` and `results/` to `.gitignore`; added a
provenance/status banner to `README.md` pointing here.

**Verify:** the next step reproduces a known result from the source repo
*before* any code change, proving the fork behaves identically (Phase 0.5).

### 0.2 `ZonalSystem` data-core type + `build_system()` — 2026-06-26

Introduced the **Layer A data-core type** so every engine dispatches on one
named, documented contract instead of an anonymous NamedTuple.

**New file `functions/zonal_system.jl`:**
- `struct ZonalSystem` wraps the loader's data; `Base.getproperty` forwards field
  access to the wrapped NamedTuple, so existing engine code (`inputs.G`,
  `inputs.demand`, …) is unchanged. The raw NamedTuple stays available as
  `sys.data`.
- `build_system(filepath)::ZonalSystem` — a drop-in for `input_data` on the solve
  path.

**`functions/function_compiler.jl`:** includes `zonal_system.jl` and loads via
`build_system(filepath)` instead of `input_data(filepath)` (the variable is still
`inputs`, so `optimizer.jl` / `result_extraction_function.jl` are untouched).

**Why a forwarding wrapper, not a flat 48-field struct:** zero risk of field
drift, nothing to keep in sync, identical property access guaranteed. Verified
safe first: a grep showed no NamedTuple-specific use of `inputs` in `functions/`,
and `input_data` / `capacity_expansion` each have exactly one caller
(`function_compiler.jl`).

**Verified (no solver needed):** `julia --project=. /tmp/verify_zonal.jl` →
*"ZonalSystem forwards all 48 fields by identity; build_system matches
input_data"* on the `timor_demo` dataset. End-to-end solve reproduction is done
in Phase 0.5.

`input_data` itself is left intact (the Layer A loader); `ZonalSystem` is purely
additive.

<!-- Append new Phase 0 entries below (0.3 site aliases, 0.4 zones.csv,
     0.5 verification). -->
