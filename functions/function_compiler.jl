# function_compiler.jl
include("input_data.jl")
include("zonal_system.jl")   # Layer A data-core wrapper (ZonalSystem, build_system)
include("solver.jl")         # pluggable optimizer (HiGHS default, Gurobi optional)
include("optimizer.jl")
include("dispatch_engine.jl")   # dispatch/reliability engine (reuses build_model!)
include("result_extraction_function.jl")
# benders_decomposition.jl provides an optional capacity_expansion_benders
# solver for very large problems; include it and swap the call below to use it

function function_compiler(
        filepath::AbstractString,
        results_dir::AbstractString,
        mipgap::Float64,
        CO2_constraint::Bool,
        CO2_limit,
        RE_constraint::Bool,
        RE_limit,
        Grid::Bool,
        VillageBuild::Bool,
        ImportPrice,
        NoCoal::Bool,
        CO235reduction::Bool,
        BAUCO2emissions;
        village_storage_max_mwh::Float64 = 208.0,
        solver::AbstractString = "highs",
        engine::AbstractString = "expansion",
        relax_uc::Bool = true,
        export_price::Float64 = 0.0,
        policy_scope::AbstractString = "grid",
        lp_method::Int = -1,
        time_limit::Float64 = 3 * 24 * 60 * 60.0,
        battery_duration_h::Float64 = 0.0,
        export_backed_by_generation::Bool = false
    )
    # 1) Load inputs into the Layer A data core (engine-agnostic ZonalSystem)
    inputs = build_system(filepath)

    # 2) Run the chosen engine on the shared model definition (build_model!)
    if engine == "dispatch"
        solution = dispatch_only(
            inputs, mipgap, CO2_constraint, CO2_limit, RE_constraint, RE_limit,
            Grid, VillageBuild, ImportPrice, NoCoal, CO235reduction, BAUCO2emissions;
            village_storage_max_mwh = village_storage_max_mwh, solver = solver, relax_uc = relax_uc,
            export_price = export_price, policy_scope = policy_scope, lp_method = lp_method,
            time_limit = time_limit,
            battery_duration_h = battery_duration_h,
            export_backed_by_generation = export_backed_by_generation
        )
    else
        solution = capacity_expansion(
            inputs, mipgap, CO2_constraint, CO2_limit, RE_constraint, RE_limit,
            Grid, VillageBuild, ImportPrice, NoCoal, CO235reduction, BAUCO2emissions;
            village_storage_max_mwh = village_storage_max_mwh, solver = solver, relax_uc = relax_uc,
            export_price = export_price, policy_scope = policy_scope, lp_method = lp_method,
            time_limit = time_limit,
            battery_duration_h = battery_duration_h,
            export_backed_by_generation = export_backed_by_generation
        )
    end

    # 3) Extract & write results into the folder
    result_extraction(
        solution,
        inputs.demand,
        inputs,
        filepath,
        results_dir
    )
    if engine == "dispatch"
        reliability_results(solution, inputs, results_dir)
    end

    return solution
end