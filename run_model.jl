#!/usr/bin/env julia
using Pkg

const REPO_ROOT = @__DIR__
Pkg.activate(REPO_ROOT)

using JSON
using JuMP
using DataFrames, CSV
using HiGHS
using Base.Filesystem: mkpath

include(joinpath(REPO_ROOT, "functions", "preflight.jl"))

# 1) Load your core modeling code
include(joinpath(REPO_ROOT, "functions/function_compiler.jl"))

# 2) Read config.json
config_path, preflight_only = parse_cli_args(ARGS)

# Select the solver from config (open-source HiGHS by default) and load its
# package. HiGHS is always available; Gurobi is imported only when requested.
solver = lowercase(get(JSON.parsefile(config_path), "solver", "highs"))
solver == "gurobi" && @eval using Gurobi

preflight = run_preflight(config_path, REPO_ROOT)
cfg = preflight.cfg
island           = cfg["island"]
year             = cfg["year"]
scenario         = cfg["scenario"]
clean            = cfg["clean"]
CO235reduction   = cfg["CO235reduction"]
BAUCO2emissions  = cfg["BAUCO2emissions"]
CO2_limit        = cfg["CO2_limit"]

# 3) Baseline model settings — overridable per job via optional config.json keys
mipgap         = Float64(get(cfg, "mipgap", 0.01))            # relative MIP gap
CO2_constraint = preflight.clean_flags.CO2_constraint
RE_constraint  = preflight.clean_flags.RE_constraint
RE_limit       = Float64(get(cfg, "RE_limit", 0.34))          # min RE share (clean runs)
village_storage_max_mwh = Float64(get(cfg, "village_storage_max_mwh", 208.0)) # per-unit cap on new village storage
engine   = lowercase(get(cfg, "engine", "expansion"))        # "expansion" | "dispatch"
# LP-relax the unit-commitment binaries. Default ON for dispatch (fast operational
# LP) and OFF for expansion (exact MILP — the decision-grade default); set
# "relax_uc" in the config to override either, e.g. fast license-free expansion.
relax_uc = Bool(get(cfg, "relax_uc", engine == "dispatch"))
# Gurobi LP algorithm (its "Method" attribute) for the root relaxation and node
# LPs: -1 automatic (the default — a strict no-op), 0 primal simplex, 1 dual
# simplex, 2 barrier, 3 concurrent, 4/5 deterministic concurrent. On the
# 780-village Timor MILP, Gurobi's automatic choice spends its whole root solve
# in concurrent mode (~535 s of "concurrent spin time" it reports as avoidable);
# Method=2 removes that. No HiGHS equivalent — ignored there.
lp_method = Int(get(cfg, "lp_method", -1))
-1 <= lp_method <= 5 ||
    error("config key lp_method must be in -1..5 (Gurobi Method), got $(lp_method)")
if lp_method >= 0 && solver != "gurobi"
    println("WARNING: lp_method=$(lp_method) is a Gurobi attribute and is ignored by solver \"$(solver)\".")
end

# 4) Scenario toggles
Grid = preflight.flags.Grid
VillageBuild = preflight.flags.VillageBuild
ImportPrice = Float64(get(cfg, "import_price", preflight.flags.ImportPrice)) # $/MWh village grid imports
# Feed-in price ($/MWh) paid for village exports to the grid. Default 0 keeps
# exports an unremunerated spill path (the shipped-reference behaviour).
export_price = Float64(get(cfg, "export_price", 0.0))
# Scope of the clean-run policy constraints (CO2 cap + RE floor): "grid" (the
# default — village generation sits outside both) or "system" (cap covers
# grid + village emissions; the RE floor counts village RE generation over
# grid + village electricity demand).
policy_scope = lowercase(String(get(cfg, "policy_scope", "grid")))
policy_scope in ("grid", "system") ||
    error("config key policy_scope must be \"grid\" or \"system\", got \"$(policy_scope)\"")
if export_price > ImportPrice
    println("WARNING: export_price ($(export_price)) > import_price ($(ImportPrice)) — " *
            "a connected village profits from importing and re-exporting; results " *
            "will be distorted by that arbitrage (bounded only by the interconnection cap).")
end
NoCoal = preflight.flags.NoCoal

if preflight_only
    println("Preflight checks passed for $(scenario)_$(island)_$(year)_$(clean)")
    exit()
end

# 6) Build input path
inputs_path = preflight.inputs_path

# 7) Create a scenario‑specific results folder
results_dir = preflight.results_dir
mkpath(results_dir)

# 8) Invoke the compiler, passing that folder
function_compiler(
    inputs_path,
    results_dir,
    mipgap,
    CO2_constraint,
    CO2_limit,
    RE_constraint,
    RE_limit,
    Grid,
    VillageBuild,
    ImportPrice,
    NoCoal,
    CO235reduction,
    BAUCO2emissions;
    village_storage_max_mwh = village_storage_max_mwh,
    solver = solver,
    engine = engine,
    relax_uc = relax_uc,
    export_price = export_price,
    policy_scope = policy_scope,
    lp_method = lp_method
)
