# tests/verify_capacity_accounting.jl
#
# Every generator must be capacity-accounted. Guards the defect where a shipped
# `Commit` sentinel dropped a row out of BOTH the UC and ED subsets, leaving its
# `vCAP` with no capacity constraint at all: `Max_Cap_MW` unapplied,
# `Inv_Cost_per_MWyr` uncharged, and `vGEN` uncapped by capacity. On
# `timor__marketfix` that reported a 517 MW battery against a 42 MW bound for $0.
#
# The regression gate cannot see this: its cases are dispatch-only, and
# dispatch_only() pins `CAP` for every g in G (dispatch_engine.jl:34-36), which
# masks a missing capacity constraint entirely. Hence a dedicated check.
#
# Builds the JuMP model but never solves it — no solver required.
#
#   Run:  julia --project=. tests/verify_capacity_accounting.jl
using Pkg
const GARUDA = normpath(joinpath(@__DIR__, ".."))
Pkg.activate(GARUDA)
using CSV, DataFrames, JuMP
include(joinpath(GARUDA, "functions", "input_data.jl"))
include(joinpath(GARUDA, "functions", "solver.jl"))
include(joinpath(GARUDA, "functions", "optimizer.jl"))

fails = 0
function check(cond, msg)
    if cond
        println("  ok   ", msg)
    else
        global fails += 1
        println("  FAIL ", msg)
    end
end

# --- [A] UC and ED partition G, on every shipped dataset -------------------
#
# Set-level and cheap, so it runs across the whole data tree. `Commit` carries
# sentinels beyond {0,1} (battery candidates are all Commit=2), so testing
# `Commit .== 0` for ED is what opened the hole; ED is now the complement of UC.
println("[A] UC/ED partition G on every shipped dataset")
datasets = String[]
for (root, _, files) in walkdir(joinpath(GARUDA, "data_indonesia"))
    "generators.csv" in files && push!(datasets, root)
end
sort!(datasets)
check(!isempty(datasets), "found $(length(datasets)) dataset(s) to check")
for path in datasets
    local inp
    try
        inp = input_data(path)
    catch e
        # a folder that cannot load is a different, already-documented defect
        println("  skip ", relpath(path, GARUDA), " (does not load: ", sprint(showerror, e)[1:min(60, end)], ")")
        continue
    end
    rel = relpath(path, GARUDA)
    orphans = setdiff(inp.G, union(inp.UC, inp.ED))
    both    = intersect(inp.UC, inp.ED)
    check(isempty(orphans), "$rel: every generator is UC or ED (orphans: $orphans)")
    check(isempty(both),    "$rel: UC and ED are disjoint (both: $both)")
    if !isempty(inp.VIL_G)
        vorph = setdiff(inp.VIL_G, union(inp.VIL_UC, inp.VIL_ED))
        vboth = intersect(inp.VIL_UC, inp.VIL_ED)
        check(isempty(vorph), "$rel: every site generator is VIL_UC or VIL_ED (orphans: $vorph)")
        check(isempty(vboth), "$rel: VIL_UC and VIL_ED are disjoint (both: $vboth)")
    end
end

# --- [B] the model actually constrains a Commit=2 storage row --------------
#
# maluku is the smallest grid-only dataset carrying the sentinel (R_ID 61,
# battery_candidate, Commit=2, STOR=1, New_Build=1, Max_Cap_MW=100).
println("[B] model-level capacity accounting (maluku, Commit=2 battery)")
let path = joinpath(GARUDA, "data_indonesia", "2030", "maluku")
    inp = input_data(path)
    g   = only(intersect(inp.STOR, inp.NEW))
    check(inp.generators.Commit[g] == 2, "R_ID $g is the Commit=2 battery candidate")

    CE = Model()   # no optimizer attached: build only, never solved
    build_model!(CE, inp, false, 0.0, false, 0.0, false, false, 0.0, false, false, 0.0)

    # Max_Cap_MW binds the new-build variable, and cCapNew ties vCAP to it.
    nc = CE[:vNEW_CAP_ED][g]
    check(has_upper_bound(nc) && upper_bound(nc) == inp.generators.Max_Cap_MW[g],
          "vNEW_CAP_ED[$g] upper bound == Max_Cap_MW ($(inp.generators.Max_Cap_MW[g]) MW)")

    # Which constraints mention vCAP[g]? Storage power must be bounded in BOTH
    # directions: cMaxPowerED caps discharge, cMaxCharge caps charge. Before the
    # fix vCAP[g] appeared in cMaxCharge alone, so discharge was unlimited.
    vcap = CE[:vCAP][g]
    seen = Set{String}()
    for (F, S) in list_of_constraint_types(CE), c in all_constraints(CE, F, S)
        f = constraint_object(c).func
        f isa AffExpr && haskey(f.terms, vcap) || continue
        n = name(c)
        isempty(n) || push!(seen, first(split(n, '[')))
    end
    check("cCapNew"     in seen, "vCAP[$g] is tied to new build by cCapNew")
    check("cMaxPowerED" in seen, "vCAP[$g] caps discharge via cMaxPowerED")
    check("cMaxCharge"  in seen, "vCAP[$g] caps charge via cMaxCharge")

    # Storage is exempt from the thermal ramp constraints: they bound vGEN only
    # and ignore vCHARGE, and every grid battery row ships
    # Ramp_Up_Percentage=0 / Ramp_Dn_Percentage=1 — a one-way ratchet that would
    # pin discharge to a constant across each representative period.
    check(!(g in inp.ED_RAMP), "R_ID $g is exempt from the thermal ramp set ED_RAMP")
    check(!("cRampUp" in seen) && !("cRampDown" in seen),
          "no thermal ramp constraint is imposed on storage R_ID $g")
    check(inp.ED_RAMP == setdiff(inp.ED, inp.STOR), "ED_RAMP == ED minus STOR")
end

println()
if fails == 0
    println("capacity accounting: all checks passed")
else
    println("capacity accounting: $fails FAILED")
    exit(1)
end
