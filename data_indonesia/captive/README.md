# Captive-power (industrial-park) datasets

Captive / industrial-park (IP) energy-system datasets for Indonesia, organised
`<year>/<island>/`. These are the **captive** counterpart to the village datasets
in `../<year>/<island>/`: same interconnected grid, a different decentralised
**site** layer (industrial parks instead of village microgrids).

## Provenance

Vendored from **[Power-Lab/data-indonesia-2025](https://github.com/Power-Lab/data-indonesia-2025)**
(MIT, see `LICENSE`), the data release for the **captive-indonesia-2025** study:

- Model code: <https://github.com/Power-Lab/captive-indonesia-2025>
- Report: <https://zenodo.org/records/17345968>

## Relationship to the village datasets

The **grid files are byte-identical** to the village islands one level up — for
sumatera and jawa_bali (2030 and 2035), `generators.csv`, `demand.csv`,
`network.csv`, `fuels_data.csv`, `generators_variability.csv` and `zones.csv` all
match exactly. Both descend from the same Power-Lab grid model. The only
difference is the site layer:

| | `../<year>/<island>/` (village) | `captive/<year>/<island>/` (this folder) |
|---|---|---|
| site layer | `village_*` (village microgrids) | `ip_*` (industrial parks) |

## Why a separate folder

`functions/site_aliases.jl` resolves a site table as `site_ → village_ → ip_`
(**first match wins**). If `ip_*` files sat next to the existing `village_*`
files in `../<year>/<island>/`, the loader would silently load the village layer
and ignore the captive one. Keeping the captive datasets here — each island
folder carrying its grid files **and** its `ip_*` layer (and no `village_*`) —
makes the `ip_` layer the one that loads.

## Running a captive scenario

Each island folder is self-contained (grid + `ip_*`).

- **Launcher** (validate / preview / scaffold), point `--data-root` here:
  ```bash
  python tools/launcher.py --data-root data_indonesia/captive \
      --island sumatera --year 2030 --scenario gridcaptive --clean reference --engine dispatch
  ```
- **Direct `run_model.jl`** resolves `data_indonesia/<year>/<island>`, so copy or
  symlink an island into that path first, e.g.
  `data_indonesia/2030/sumatera_captive`, then run with `island=sumatera_captive`.

Use the `captive` (islanded) or `gridcaptive` (grid-connected) scenario. The
IP-laden LP is heavy for HiGHS — prefer Gurobi, or run the LP-relaxed dispatch
engine as a long job. Outputs use the canonical `site_*` result names.

## Islands

`jawa_bali`, `kalimantan`, `north_maluku`, `nusa_tenggara`, `papua`, `sulawesi`,
`sumatera` — both 2030 and 2035. (`maluku` has no captive layer upstream and is
omitted.)
