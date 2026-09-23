# solver.jl
#
# Pluggable optimizer for the platform. Open-source **HiGHS** is the default so
# the model runs with no commercial licence; **Gurobi** is an optional fast path
# for large instances. The chosen solver's package must already be imported by
# the entry point (run_model.jl / bootstrap.jl import HiGHS always, and Gurobi
# only when a run requests it), so a pure open-source setup never needs Gurobi.

"""
    make_solver(solver="highs"; mipgap=0.01, time_limit=3*24*60*60, silent=false,
                lp_method=-1)

Build and return a configured, empty `JuMP.Model` for `solver` ∈ {`"highs"`,
`"gurobi"`}, mapping the relative MIP gap and time limit to each solver's own
attribute names (`mip_rel_gap`/`time_limit` for HiGHS, `MIPGap`/`TimeLimit` for
Gurobi). Errors on an unknown solver.

`lp_method` selects Gurobi's LP algorithm for the root relaxation and the
node LPs (Gurobi's `Method` attribute: 0 primal simplex, 1 dual simplex,
2 barrier, 3 concurrent, 4 deterministic concurrent, 5 deterministic
concurrent simplex). The default `-1` leaves Gurobi on automatic, so this is a
strict no-op unless a run asks for a method — no shipped result moves. It is a
Gurobi attribute with no HiGHS equivalent and is ignored under HiGHS.
"""
function make_solver(solver::AbstractString = "highs"; mipgap::Real = 0.01,
                     time_limit::Real = 3 * 24 * 60 * 60, silent::Bool = false,
                     lp_method::Integer = -1)
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
        lp_method >= 0 && set_attribute(model, "Method", lp_method)
    else
        error("Unknown solver \"$(solver)\"; expected \"highs\" or \"gurobi\".")
    end
    silent && set_silent(model)
    return model
end

"""
    _relax_binaries!(CE, names)

LP-relax the named binary variable containers on model `CE`: each binary variable
is freed to the continuous range `[0, 1]`. Used to turn the unit-commitment MILP
into an LP (a fast, license-free relaxation) in both the dispatch and the
capacity-expansion engines. Names absent from the model (e.g. the village
grid-connection binary in a grid-off scenario) are skipped.
"""
function _relax_binaries!(CE, names)
    od = object_dictionary(CE)
    for nm in names
        haskey(od, nm) || continue
        for v in CE[nm]
            if is_binary(v)
                unset_binary(v)
                set_lower_bound(v, 0.0)
                set_upper_bound(v, 1.0)
            end
        end
    end
    return nothing
end

# the unit-commitment binaries shared by both engines (grid + village commitment,
# plus the village grid-connection decision); fed to _relax_binaries!.
const UC_BINARIES = (:vCOMMIT, :vSTART, :vSHUT, :vVIL_COMMIT, :vVIL_START, :vVIL_SHUT, :vVIL_CONNECT)

"""
    _fix_connect_pattern!(CE, path) -> Int

Fix every `vVIL_CONNECT` variable to the 0/1 values in `path` — a CSV with `ID`
and `Connected` columns, so a landed run's `site_connection_results.csv` works
verbatim. This is the fix-and-verify step for reduced-time-resolution runs:
solve the reduced model for a connection pattern, fix that pattern on the full
dataset, and the remaining solve (an LP under `relax_uc`) prices the concrete
plan at full resolution with no aggregation caveat. `force = true` overrides
both bound states a connect variable can be in (binary under `exact_connect`,
`[0, 1]`-bounded after `_relax_binaries!`). Returns the connected-village
count. Errors on a model without `vVIL_CONNECT` (non-Grid scenarios), a row
count that mismatches the village set, or a non-0/1 value — a silently ignored
pattern would report a base-case answer as a verified one.
"""
function _fix_connect_pattern!(CE, path::AbstractString)
    pat, vcon = _read_connect_pattern(CE, path, "connect_pattern")
    for r in eachrow(pat)
        JuMP.fix(vcon[r.ID], Float64(r.Connected); force = true)
    end
    return count(==(1), pat.Connected)
end

"""
    _start_connect_pattern!(CE, path) -> Int

Warm-start (MIP start) every `vVIL_CONNECT` variable at the 0/1 values in
`path` — same file format and validation as `_fix_connect_pattern!`, but the
values are `set_start_value`s, not fixes: the solver is free to move off them.
Use it to seed a connection-pattern search from a plan that is already known
to be good (e.g. a fix-and-verify winner from another dataset) instead of the
default all-islanded start, so the reported incumbent can never be worse than
that plan. A start only helps or is discarded; it never binds. Returns the
connected-village count in the start.
"""
function _start_connect_pattern!(CE, path::AbstractString)
    pat, vcon = _read_connect_pattern(CE, path, "start_pattern")
    for r in eachrow(pat)
        set_start_value(vcon[r.ID], Float64(r.Connected))
    end
    return count(==(1), pat.Connected)
end

# Shared validation for connect_pattern / start_pattern: a CSV with ID and
# Connected columns, one row per village, 0/1 values, on a model that has the
# wire variables at all. Errors rather than ignoring, because a silently
# skipped pattern would report a base-case answer as a verified (or seeded) one.
function _read_connect_pattern(CE, path::AbstractString, key::AbstractString)
    pat = CSV.read(path, DataFrame)
    ("ID" in names(pat) && "Connected" in names(pat)) ||
        error("$(key) file $(path) needs ID and Connected columns, has $(names(pat))")
    od = object_dictionary(CE)
    haskey(od, :vVIL_CONNECT) ||
        error("$(key) given but the model has no vVIL_CONNECT — Grid + VillageBuild scenarios only")
    vcon = CE[:vVIL_CONNECT]
    length(vcon) == nrow(pat) ||
        error("$(key) has $(nrow(pat)) rows for $(length(vcon)) villages")
    for r in eachrow(pat)
        r.Connected in (0, 1) ||
            error("$(key) Connected must be 0/1, got $(r.Connected) at ID $(r.ID)")
    end
    return pat, vcon
end
