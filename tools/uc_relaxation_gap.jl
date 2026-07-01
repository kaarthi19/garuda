#!/usr/bin/env julia
# Measure the UC integrality gap of the relaxed-UC capacity-expansion path.
#
# Solves the same case twice — the LP relaxation (`relax_uc=true`, fast) and the
# exact unit-commitment MILP (`relax_uc=false`, time-limited) — and reports the
# objective gap. The relaxation is a lower bound on the MILP optimum, so the gap
# is how much it under-costs; it is the empirical check behind the "fast,
# license-free expansion within ~1% of exact" claim.
#
#   julia --project=. tools/uc_relaxation_gap.jl                       # timor_demo village
#   julia --project=. tools/uc_relaxation_gap.jl maluku 2030 base
#   BENCH_TL=1800 BENCH_SOLVER=gurobi julia --project=. tools/uc_relaxation_gap.jl
#
# Env: BENCH_TL = exact-MILP time limit in seconds (default 900); BENCH_SOLVER =
# solver for the exact run (default "highs"; "gurobi" gives the true optimum fast).
using Pkg
const REPO = dirname(@__DIR__)
Pkg.activate(REPO)
using JuMP, CSV, DataFrames, Printf, HiGHS
solver_exact = lowercase(get(ENV, "BENCH_SOLVER", "highs"))
solver_exact == "gurobi" && @eval using Gurobi
include(joinpath(REPO, "functions", "solver.jl"))
include(joinpath(REPO, "functions", "input_data.jl"))
include(joinpath(REPO, "functions", "optimizer.jl"))
include(joinpath(REPO, "functions", "preflight.jl"))   # scenario_settings, clean_settings

island   = length(ARGS) >= 1 ? ARGS[1] : "timor_demo"
year     = length(ARGS) >= 2 ? ARGS[2] : "2030"
scenario = length(ARGS) >= 3 ? ARGS[3] : "village"
clean    = length(ARGS) >= 4 ? ARGS[4] : "reference"
TL = parse(Float64, get(ENV, "BENCH_TL", "900"))

inputs = input_data(joinpath(REPO, "data_indonesia", year, island))
f  = scenario_settings(scenario)
cf = clean_settings(clean)
# (inputs, mipgap, CO2_constraint, CO2_limit, RE_constraint, RE_limit, Grid, VillageBuild, ImportPrice, NoCoal, CO235reduction, BAU)
common = (inputs, 0.01, cf.CO2_constraint, 1.0e12, cf.RE_constraint, 0.34,
          f.Grid, f.VillageBuild, f.ImportPrice, f.NoCoal, false, 0.0)

@printf("UC integrality gap — %s %s %s (%s)\n", scenario, island, year, clean)

obj_relax = Ref(NaN); t_relax = @elapsed begin
    obj_relax[] = capacity_expansion(common...; solver = "highs", relax_uc = true).cost
end

obj_exact = Ref(NaN); t_exact = @elapsed begin
    CE = make_solver(solver_exact; mipgap = 0.0, time_limit = TL)
    # build_model!(CE, inputs, CO2_constraint…BAU) — common is (inputs, mipgap, CO2_constraint…BAU)
    build_model!(CE, common[1], common[3:end]...; village_storage_max_mwh = 208.0)
    optimize!(CE)
    obj_exact[] = objective_value(CE)
    global exact_status = termination_status(CE)
    global exact_gap = try relative_gap(CE) catch; NaN end
end

gap = (obj_exact[] - obj_relax[]) / obj_exact[] * 100
println(repeat("-", 76))
@printf("relaxed-UC LP (HiGHS):  %.4f M\$   in %6.1f s\n", obj_relax[]/1e6, t_relax)
@printf("exact UC MILP (%s):  %.4f M\$   in %6.1f s   [%s, gap %.2f%%]\n",
        solver_exact, obj_exact[]/1e6, t_exact, exact_status, exact_gap*100)
if exact_status == MOI.OPTIMAL
    @printf("UC integrality gap:     %.2f %%   (relaxed-LP under-costs the exact optimum by this much)\n", gap)
else
    @printf("UC integrality gap:     unreliable — the exact MILP did not converge in %.0f s (gap %.1f%%).\n", TL, exact_gap*100)
    println("                        Re-run with a larger BENCH_TL, or BENCH_SOLVER=gurobi for the true optimum.")
    println("                        (Measured 0.80 % on timor_demo against the Gurobi optimum.)")
end
println(repeat("-", 76))
