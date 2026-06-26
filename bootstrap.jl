#!/usr/bin/env julia
using Pkg

const REPO_ROOT = @__DIR__

println("Activating Julia environment at $(REPO_ROOT)")
Pkg.activate(REPO_ROOT)
Pkg.resolve()
Pkg.instantiate()

using JuMP
using HiGHS

include(joinpath(REPO_ROOT, "functions", "preflight.jl"))

println("Checking the default open-source solver (HiGHS)")
validate_solver("highs")

println("Julia environment is ready. (Gurobi is optional — set \"solver\": \"gurobi\" in a config to use it.)")