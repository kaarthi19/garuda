# tests/verify_data_core.jl
#
# Layer A regression. Confirms the data-core refactor — the ZonalSystem wrapper,
# the site vocabulary aliases (site_/village_/ip_), and zones.csv -> zone_names —
# is behaviour-preserving, and that the engine-agnostic data loads identically
# across spellings. No solver required.
#
#   Run:  julia --project=. tests/verify_data_core.jl
using Pkg
const GARUDA = normpath(joinpath(@__DIR__, ".."))
Pkg.activate(GARUDA)
using CSV, DataFrames
include(joinpath(GARUDA, "functions", "input_data.jl"))   # self-includes site_aliases.jl + zones.jl
include(joinpath(GARUDA, "functions", "zonal_system.jl"))

data(args...) = joinpath(GARUDA, "data_indonesia", args...)
fails = 0
function check(cond, msg)
    if cond
        println("  ok   ", msg)
    else
        global fails += 1
        println("  FAIL ", msg)
    end
end

println("[A] ZonalSystem forwarding (timor_demo)")
let path = data("2030", "timor_demo")
    nt  = input_data(path)
    sys = ZonalSystem(nt)
    check(all(getproperty(sys, k) === getproperty(nt, k) for k in propertynames(nt)),
          "all $(length(propertynames(nt))) fields forward by identity")
    check(sys.data === nt, "sys.data === wrapped NamedTuple")
    check(build_system(path) isa ZonalSystem, "build_system returns ZonalSystem")
end

println("[B] site vocabulary aliases (village_* vs synthesised site_*)")
let src = data("2030", "timor_demo"), dst = mktempdir()
    for f in ("generators.csv","demand.csv","generators_variability.csv","fuels_data.csv","network.csv")
        isfile(joinpath(src, f)) && cp(joinpath(src, f), joinpath(dst, f))
    end
    g = DataFrame(CSV.File(joinpath(src, "village_generators.csv"))); rename!(g, :Village => :Site)
    CSV.write(joinpath(dst, "site_generators.csv"), g)
    for (s, d) in (("village_demand.csv","site_demand.csv"), ("village_demandheat.csv","site_demandheat.csv"))
        df = DataFrame(CSV.File(joinpath(src, s)))
        rn = Dict(Symbol(c) => Symbol(replace(c, "demand_village" => "demand_site"))
                  for c in names(df) if startswith(c, "demand_village"))
        rename!(df, rn); CSV.write(joinpath(dst, d), df)
    end
    cp(joinpath(src, "village_generators_variability.csv"), joinpath(dst, "site_generators_variability.csv"))
    v = build_system(src); s = build_system(dst)
    check(v.VIL == s.VIL && v.VIL_G == s.VIL_G, "site & village VIL/VIL_G sets match")
    check(Matrix(v.village_demand) == Matrix(s.village_demand), "site & village demand values match")
    check(isequal(v.village_generators.Var_Cost, s.village_generators.Var_Cost), "derived Var_Cost matches")
    check(resolve_site_csv(dst, "generators") == joinpath(dst, "site_generators.csv"), "resolve_site_csv finds site_")
    check(site_id_col(DataFrame(Industrial_Park = [1])) == :Industrial_Park, "site_id_col handles ip/Industrial_Park")
end

println("[C] zones.csv -> zone_names")
let sys = build_system(data("2030", "sulawesi"))
    check(sys.zone_names[1] == "north_sulawesi" && sys.zone_names[2] == "gorontalo", "sulawesi zone names parsed")
    check(isempty(setdiff(sys.Z, collect(keys(sys.zone_names)))), "every modelled sulawesi zone has a name")
    check(isempty(build_system(data("2030", "timor_demo")).zone_names), "timor_demo has empty zone_names")
end

println(fails == 0 ? "\nDATA_CORE_OK: all checks passed" : "\nDATA_CORE_FAIL: $fails check(s) failed")
exit(fails == 0 ? 0 : 1)
