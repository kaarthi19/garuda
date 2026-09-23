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
# Fixed-duration site storage: energy (MWh) = battery_duration_h x power (MW).
# 0 (default) leaves power and energy co-optimised independently — a strict no-op.
battery_duration_h = Float64(get(cfg, "battery_duration_h", 0.0))
battery_duration_h >= 0 ||
    error("config key battery_duration_h must be >= 0 hours (0 = off), got $(battery_duration_h)")
engine   = lowercase(get(cfg, "engine", "expansion"))        # "expansion" | "dispatch"
# LP-relax the unit-commitment binaries. Default ON for dispatch (fast operational
# LP) and OFF for expansion (exact MILP — the decision-grade default); set
# "relax_uc" in the config to override either, e.g. fast license-free expansion.
relax_uc = Bool(get(cfg, "relax_uc", engine == "dispatch"))

# Keep the village grid-connection decision binary even when relax_uc LP-relaxes
# the unit-commitment binaries. UC_BINARIES includes vVIL_CONNECT, so plain
# relax_uc also relaxes the wire decision: a fractional connect pays a fraction
# of the connection cost for full trade benefit, and `Connected` becomes a
# rounded artifact. exact_connect leaves the 780 wire binaries exact while the
# ~121k UC binaries relax — the tractability sweet spot for coordination runs.
# Default false = existing behaviour, a strict no-op.
exact_connect = Bool(get(cfg, "exact_connect", false))
# Fix-and-verify: path to a CSV with ID and Connected columns — a landed run's
# site_connection_results.csv works verbatim — whose 0/1 pattern is fixed onto
# vVIL_CONNECT before the solve. Use it to price a connection plan found on a
# reduced-time-resolution dataset (tools/make_reduced_weeks.py) at full
# resolution: with relax_uc the remaining problem is an LP and one solve gives
# the exact full-resolution cost of that concrete plan, with no aggregation
# caveat. Default "" = off, a strict no-op.
connect_pattern = String(get(cfg, "connect_pattern", ""))
isempty(connect_pattern) || isfile(connect_pattern) ||
    error("config key connect_pattern points to a missing file: $(connect_pattern)")
# Seeded warm start: same file format as connect_pattern, but the 0/1 values
# are MIP start values on vVIL_CONNECT rather than fixes — the search may move
# off them. Use it to seed a pattern search from a known-good plan so the
# reported incumbent can never be worse than that plan. Ignored when
# connect_pattern is also given (nothing is free to start). Default "" = the
# all-islanded start, a strict no-op.
start_pattern = String(get(cfg, "start_pattern", ""))
isempty(start_pattern) || isfile(start_pattern) ||
    error("config key start_pattern points to a missing file: $(start_pattern)")
# Gurobi LP algorithm (its "Method" attribute) for the root relaxation and node
# LPs: -1 automatic (the default — a strict no-op), 0 primal simplex, 1 dual
# simplex, 2 barrier, 3 concurrent, 4/5 deterministic concurrent. On the
# 780-village Timor MILP, Gurobi's automatic choice spends its whole root solve
# in concurrent mode (~535 s of "concurrent spin time" it reports as avoidable);
# Method=2 removes that. No HiGHS equivalent — ignored there.
lp_method = Int(get(cfg, "lp_method", -1))
-1 <= lp_method <= 5 ||
    error("config key lp_method must be in -1..5 (Gurobi Method), got $(lp_method)")
# Solver wall-clock limit in seconds. Default 3 days = the make_solver default, so
# omitting this key is a strict no-op. Set it when a MILP may not close its gap:
# on TIME_LIMIT the engines print "reached the time limit" and then extract
# results from the incumbent as normal (optimizer.jl:921, dispatch_engine.jl), so
# a bounded run yields a usable feasible plan plus a reported gap. Killing the
# process from outside instead (`timeout`) destroys the result CSVs entirely.
time_limit = Float64(get(cfg, "time_limit", 3 * 24 * 60 * 60))
time_limit > 0 ||
    error("config key time_limit must be > 0 seconds, got $(time_limit)")
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
# Require every exported MWh to come out of that site's own renewable generation
# in the same hour — the rule a real feed-in contract imposes. Off by default (a
# strict no-op); it adds one constraint row per (hour, site), ~1.05 M on Timor.
# Its purpose is to make a wash trade structurally impossible: without it, on a
# dataset with no grid demand, two villages can trade at a profit while
# generating nothing. build_model! refuses that configuration outright.
export_backed_by_generation = Bool(get(cfg, "export_backed_by_generation", false))
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
    exact_connect = exact_connect,
    connect_pattern = connect_pattern,
    start_pattern = start_pattern,
    export_price = export_price,
    policy_scope = policy_scope,
    lp_method = lp_method,
    time_limit = time_limit,
    battery_duration_h = battery_duration_h,
    export_backed_by_generation = export_backed_by_generation
)
