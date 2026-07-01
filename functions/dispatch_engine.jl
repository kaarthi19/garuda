# dispatch_engine.jl
#
# Dispatch / reliability engine. Reuses the SAME model definition as the
# capacity-expansion engine (`build_model!` in optimizer.jl) but FIXES capacity
# to the existing fleet, so it solves only the operational problem: how a given
# fleet runs hour-by-hour and where it falls short. Non-served energy is the
# slack in the balance, so the problem is always feasible — an undersized fleet
# reports a shortage rather than going infeasible.
#
# `relax_uc = true` (default) relaxes the unit-commitment binaries to [0,1],
# turning the dispatch into an LP that the open-source HiGHS solver handles
# quickly; `relax_uc = false` keeps an exact unit-commitment (MILP) dispatch.

using CSV, DataFrames
import Base.Filesystem: mkpath

# Existing-fleet capacity: the real Existing_Cap_* for OLD units, but 0 for
# New_Build==1 candidates (which carry a "potential" Existing_Cap_* in some
# datasets but are not built). Mirrors the loader's NEW = New_Build.==1.
_existing_cap(df, col, g) = df.New_Build[g] == 1 ? 0.0 : Float64(df[g, col])

# _relax_binaries! and UC_BINARIES are defined in solver.jl (shared by both engines).

function dispatch_only(inputs, mipgap, CO2_constraint, CO2_limit, RE_constraint, RE_limit, Grid, VillageBuild, ImportPrice, NoCoal, CO235reduction, BAUCO2emissions; village_storage_max_mwh = 208.0, solver = "highs", relax_uc = true)
    CE = make_solver(solver; mipgap = mipgap)
    refs = build_model!(CE, inputs, CO2_constraint, CO2_limit, RE_constraint, RE_limit,
                        Grid, VillageBuild, ImportPrice, NoCoal, CO235reduction, BAUCO2emissions;
                        village_storage_max_mwh = village_storage_max_mwh)

    # --- fix capacity to the existing fleet (no investment / retirement) ---
    for g in inputs.G
        JuMP.fix(refs.CAP[g], _existing_cap(inputs.generators, :Existing_Cap_MW, g); force = true)
    end
    for g in inputs.STOR
        JuMP.fix(refs.E_CAP[g], _existing_cap(inputs.generators, :Existing_Cap_MWh, g); force = true)
    end
    for l in inputs.L
        JuMP.fix(refs.T_CAP[l], Float64(inputs.lines.Line_Max_Flow_MW[l]); force = true)
    end
    for g in inputs.VIL_G
        JuMP.fix(refs.VIL_CAP[g], _existing_cap(inputs.village_generators, :Existing_Cap_MW, g); force = true)
    end
    for g in inputs.VIL_STOR
        JuMP.fix(refs.VIL_E_CAP[g], _existing_cap(inputs.village_generators, :Existing_Cap_MWh, g); force = true)
    end

    # LP-relaxed dispatch (fast on HiGHS) unless an exact UC dispatch is requested
    relax_uc && _relax_binaries!(CE, UC_BINARIES)

    optimize!(CE)
    if termination_status(CE) == MOI.OPTIMAL
        println("Dispatch solved successfully$(relax_uc ? " (LP, UC relaxed)" : " (MILP, exact UC)").")
    elseif termination_status(CE) == MOI.TIME_LIMIT
        println("Dispatch reached the time limit.")
    elseif termination_status(CE) == MOI.INFEASIBLE
        println("Dispatch is infeasible (fleet cannot meet demand even with full non-served energy).")
    else
        println("Dispatch did not solve. Termination status: ", termination_status(CE))
    end

    return merge(refs, (cost = objective_value(CE),))
end

# Reliability metrics from the non-served-energy slack: per-zone shortage energy,
# loss-of-load expectation (sample-weighted shortage hours per year), peak.
function reliability_results(solution, inputs, results_dir)
    mkpath(results_dir)
    sw = inputs.sample_weight
    eps = 1e-6
    znames = inputs.zone_names

    NSEv = value.(solution.NSE)
    zrows = DataFrame(Zone = Int[], Zone_Name = String[], Total_NSE_MWh = Float64[],
                      NSE_Percent_of_Demand = Float64[], LOLE_hours = Float64[], Peak_Shortage_MW = Float64[])
    for z in inputs.Z
        nse_t = [sum(NSEv[t, s, z] for s in inputs.S) for t in inputs.T]
        total = sum(sw[t] * nse_t[t] for t in inputs.T; init = 0.0)
        lole = sum(sw[t] for t in inputs.T if nse_t[t] > eps; init = 0.0)
        peak = isempty(nse_t) ? 0.0 : maximum(nse_t)
        dem = sum(sw[t] * inputs.demand[t, Symbol("demand_z$z")] for t in inputs.T; init = 0.0)
        push!(zrows, (z, get(znames, z, ""), total, dem > 0 ? 100 * total / dem : 0.0, lole, peak))
    end
    CSV.write(joinpath(results_dir, "reliability_results.csv"), zrows)

    if !isempty(inputs.VIL)
        VNSEv = value.(solution.VIL_NSE)
        vrows = DataFrame(Village = Int[], Total_NSE_MWh = Float64[], NSE_Percent_of_Demand = Float64[],
                          LOLE_hours = Float64[], Peak_Shortage_MW = Float64[])
        for vil in inputs.VIL
            nse_t = [sum(VNSEv[t, s, vil] for s in inputs.S) for t in inputs.T]
            total = sum(sw[t] * nse_t[t] for t in inputs.T; init = 0.0)
            lole = sum(sw[t] for t in inputs.T if nse_t[t] > eps; init = 0.0)
            peak = isempty(nse_t) ? 0.0 : maximum(nse_t)
            dem = sum(sw[t] * inputs.village_demand[t, vil] for t in inputs.T; init = 0.0)
            push!(vrows, (vil, total, dem > 0 ? 100 * total / dem : 0.0, lole, peak))
        end
        CSV.write(joinpath(results_dir, "site_reliability_results.csv"), vrows)
    end
    return nothing
end
