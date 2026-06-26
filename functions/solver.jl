# solver.jl
#
# Pluggable optimizer for the platform. Open-source **HiGHS** is the default so
# the model runs with no commercial licence; **Gurobi** is an optional fast path
# for large instances. The chosen solver's package must already be imported by
# the entry point (run_model.jl / bootstrap.jl import HiGHS always, and Gurobi
# only when a run requests it), so a pure open-source setup never needs Gurobi.

"""
    make_solver(solver="highs"; mipgap=0.01, time_limit=3*24*60*60, silent=false)

Build and return a configured, empty `JuMP.Model` for `solver` ∈ {`"highs"`,
`"gurobi"`}, mapping the relative MIP gap and time limit to each solver's own
attribute names (`mip_rel_gap`/`time_limit` for HiGHS, `MIPGap`/`TimeLimit` for
Gurobi). Errors on an unknown solver.
"""
function make_solver(solver::AbstractString = "highs"; mipgap::Real = 0.01,
                     time_limit::Real = 3 * 24 * 60 * 60, silent::Bool = false)
    s = lowercase(strip(solver))
    if s == "highs"
        model = Model(HiGHS.Optimizer)
        set_attribute(model, "mip_rel_gap", float(mipgap))
        set_attribute(model, "time_limit", float(time_limit))
    elseif s == "gurobi"
        model = Model(Gurobi.Optimizer)
        set_attribute(model, "MIPGap", mipgap)
        set_attribute(model, "TimeLimit", time_limit)
        set_attribute(model, "Crossover", 0)
    else
        error("Unknown solver \"$(solver)\"; expected \"highs\" or \"gurobi\".")
    end
    silent && set_silent(model)
    return model
end
