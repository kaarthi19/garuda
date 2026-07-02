# tests/check_dispatch_headlines.jl
#
# CI guard: confirm a fresh maluku 2030 base dispatch (HiGHS, relax_uc) still
# reproduces the known headline numbers, so a model change cannot silently move
# results. Tolerance-based (±1 %) so it is robust to solver/platform noise; no
# reference CSVs are committed (results/ is gitignored).
#
#   Run:  julia --project=. tests/check_dispatch_headlines.jl <results_dir>
#
# Reference numbers: maluku 2030 base dispatch, HiGHS, relax_uc=true, mipgap=0.01
# (see .github/ci/maluku_dispatch.config.json). Regenerate them locally with
# `julia --project=. run_model.jl --config .github/ci/maluku_dispatch.config.json`
# if the model or dataset legitimately changes, then update the expected values.
using CSV, DataFrames

const TOL = 0.01   # ±1 %
const EXPECTED = (
    Total_Costs   = 418.75012738446367,   # cost_results.csv, $M/yr
    CO2_Emissions = 889909.6973480765,    # clean_energy_results.csv, tCO2/yr
    Total_NSE_MWh = 205997.29702380873,   # Σ reliability_results.csv
)

dir = length(ARGS) >= 1 ? ARGS[1] : joinpath(@__DIR__, "..", "results", "base_maluku_2030_reference")
fails = 0

function within(name, got, want)
    rel = abs(got - want) / abs(want)
    if rel <= TOL
        println("  ok   $name = $got  (Δ $(round(100rel, digits=3)) % of $want)")
    else
        global fails += 1
        println("  FAIL $name = $got  (Δ $(round(100rel, digits=3)) % > $(100TOL) % of $want)")
    end
end

need(f) = (p = joinpath(dir, f); isfile(p) || (global fails += 1; println("  FAIL missing $f"); return nothing); p)

println("Checking dispatch headline numbers in $dir")

let p = need("cost_results.csv")
    p !== nothing && within("Total_Costs", CSV.read(p, DataFrame).Total_Costs[1], EXPECTED.Total_Costs)
end
let p = need("clean_energy_results.csv")
    p !== nothing && within("CO2_Emissions", CSV.read(p, DataFrame).CO2_Emissions[1], EXPECTED.CO2_Emissions)
end
let p = need("reliability_results.csv")
    p !== nothing && within("Total_NSE_MWh (sum)", sum(CSV.read(p, DataFrame).Total_NSE_MWh), EXPECTED.Total_NSE_MWh)
end
# outputs a dispatch run must produce
for f in ("generator_results.csv", "nse_results.csv", "reliability_results.csv")
    isfile(joinpath(dir, f)) || (global fails += 1; println("  FAIL missing expected output $f"))
end

if fails == 0
    println("DISPATCH_HEADLINES_OK: all checks passed")
    exit(0)
else
    println("DISPATCH_HEADLINES_FAIL: $fails check(s) failed")
    exit(1)
end
