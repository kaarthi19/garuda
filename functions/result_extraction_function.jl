# result_extraction_function.jl

using CSV
using DataFrames
import Base.Filesystem: mkpath

function result_extraction(
        solution,
        demand::DataFrame,
        inputs,
        input_path::AbstractString,
        results_dir::AbstractString
    )
    # 0) ensure output folder exists
    mkpath(results_dir)

    # 1) Compute generation totals.
    #
    # Materialise each JuMP value container ONCE — indexing value.(...) inside a
    # loop re-evaluates the whole container every iteration (pathological at
    # hundreds of villages).
    #
    # ENERGY QUANTITIES ARE ANNUALISED WITH sample_weight.
    #
    # The model solves representative periods, not a full year: each modelled hour
    # stands for `sample_weight[t]` hours of the year (Sub_Weights[p] divided by
    # Timesteps_per_Rep_Period). A bare sum over the 1344 modelled hours therefore
    # reports only the sample, not the year — 6.518x low on Timor (uniform weights
    # of 1095/168), and wrong per-period on datasets whose weights are NOT uniform
    # (maluku's sample_weight ranges 1.0 to 15.04, so no single factor exists and
    # even the generation *mix* is distorted). The objective already weights its
    # cost terms this way; only the reported energy did not.
    #
    # Weight energy (MWh / MWh-summed-over-time); do NOT weight power (MW), which
    # is instantaneous — peaks and capacities stay as solved.
    w = inputs.sample_weight
    annualise(series) = sum(w[t] * series[t] for t in eachindex(series))

    GENv = value.(solution.GEN)
    NG = size(inputs.G, 1)
    generation = zeros(NG)
    for i in 1:NG
        generation[i] = annualise(GENv[:, inputs.G[i]].data)
    end

    VILGENv = value.(solution.VIL_GEN)
    NVILG = size(inputs.VIL_G, 1)
    village_generation = zeros(NVILG)
    for i in 1:NVILG
        village_generation[i] = annualise(VILGENv[:, inputs.VIL_G[i]].data)
    end

    VILGENHEATv = value.(solution.VIL_GEN_HEAT)
    NVILUC = size(inputs.VIL_UC, 1)
    village_heat_generation = zeros(NVILUC)
    for i in 1:NVILUC
        village_heat_generation[i] = annualise(VILGENHEATv[:, inputs.VIL_UC[i]].data)
    end

    total_demand = sum(w[t] * sum(demand[t, :]) for t in eachindex(w))
    peak_demand  = maximum(sum(eachcol(demand)))
    MWh_share    = generation ./ total_demand .* 100
    cap_share    = value.(solution.CAP).data ./ peak_demand .* 100

    # 2) Build DataFrames…
    generator = DataFrame(
        ID             = inputs.G,
        Resource       = inputs.generators.Resource[inputs.G],
        Zone           = inputs.generators.Zone[inputs.G],
        technology     = inputs.generators.technology[inputs.G],
        owner          = inputs.generators.owner[inputs.G],
        Total_MW       = value.(solution.CAP).data,
        Start_MW       = inputs.generators.Existing_Cap_MW[inputs.G],
        Change_in_MW   = value.(solution.CAP).data .- inputs.generators.Existing_Cap_MW[inputs.G],
        Percent_MW     = cap_share,
        GWh            = generation ./ 1000,
        Percent_GWh    = MWh_share,
        STOR           = inputs.generators.STOR[inputs.G],
        VRE            = inputs.generators.VRE[inputs.G],
        THERM          = inputs.generators.THERM[inputs.G],
        New_Build      = inputs.generators.New_Build[inputs.G],
    )

    village_generators = DataFrame(
        ID                   = inputs.VIL_G,
        Resource             = inputs.village_generators.Resource[inputs.VIL_G],
        Zone                 = inputs.village_generators.Zone[inputs.VIL_G],
        Village              = inputs.village_generators.Village[inputs.VIL_G],
        technology           = inputs.village_generators.technology[inputs.VIL_G],
        Total_MW             = value.(solution.VIL_CAP).data,
        Start_MW             = inputs.village_generators.Existing_Cap_MW[inputs.VIL_G],
        Change_in_MW         = value.(solution.VIL_CAP).data .- inputs.village_generators.Existing_Cap_MW[inputs.VIL_G],
        Electricity_GWh      = village_generation ./ 1000,
    )

    village_heat_generators = DataFrame(
        ID                  = inputs.VIL_UC,
        Resource            = inputs.village_generators.Resource[inputs.VIL_UC],
        Zone                = inputs.village_generators.Zone[inputs.VIL_UC],
        Village             = inputs.village_generators.Village[inputs.VIL_UC],
        technology          = inputs.village_generators.technology[inputs.VIL_UC],
        GWh                 = village_heat_generation ./ 1000
    )

    # Materialise village import/export value containers once (0 sentinel when
    # not a Grid scenario).
    VILIMPORTv = solution.VIL_IMPORT == 0 ? 0 : value.(solution.VIL_IMPORT)
    VILEXPORTv = solution.VIL_EXPORT == 0 ? 0 : value.(solution.VIL_EXPORT)

    if VILIMPORTv == 0 || all(VILIMPORTv .== 0)
        village_import = DataFrame(
            ID               = inputs.VIL,
            Zone             = [inputs.village_zone[v] for v in inputs.VIL],
            Total_Import_MWh = zeros(length(inputs.VIL)),
            Peak_Import_MW   = zeros(length(inputs.VIL)),
        )
    else
        village_import = DataFrame(
            ID               = inputs.VIL,
            Zone             = [inputs.village_zone[v] for v in inputs.VIL],
            Total_Import_MWh = [annualise(VILIMPORTv[:, v].data) for v in inputs.VIL],
            Peak_Import_MW   = vec(maximum(VILIMPORTv[:, inputs.VIL].data, dims=1)),
        )
    end

    # village grid-connection decision + import/export energy (Grid scenarios only)
    if solution.VIL_CONNECT == 0
        village_connection = DataFrame(
            ID               = inputs.VIL,
            Zone             = [inputs.village_zone[v] for v in inputs.VIL],
            Connected        = zeros(Int, length(inputs.VIL)),
            Total_Import_MWh = zeros(length(inputs.VIL)),
            Total_Export_MWh = zeros(length(inputs.VIL)),
        )
    else
        CONNECTv = value.(solution.VIL_CONNECT)
        village_connection = DataFrame(
            ID               = inputs.VIL,
            Zone             = [inputs.village_zone[v] for v in inputs.VIL],
            Connected        = [round(Int, CONNECTv[v]) for v in inputs.VIL],
            Total_Import_MWh = [annualise(VILIMPORTv[:, v].data) for v in inputs.VIL],
            Total_Export_MWh = [annualise(VILEXPORTv[:, v].data) for v in inputs.VIL],
        )
    end

    storage = DataFrame(
        ID                    = inputs.STOR,
        Zone                  = inputs.generators.Zone[inputs.STOR],
        Resource              = inputs.generators.Resource[inputs.STOR],
        Total_Storage_MWh     = value.(solution.E_CAP).data,
        Start_Storage_MWh     = inputs.generators.Existing_Cap_MW[inputs.STOR],
        Change_in_Storage_MWh = value.(solution.E_CAP).data .- inputs.generators.Existing_Cap_MW[inputs.STOR],
    )

    village_storage = DataFrame()
    if !isempty(inputs.VIL_STOR)
        try
            if solution.VIL_E_CAP isa AbstractArray
                total_storage = value.(solution.VIL_E_CAP).data
                start_storage = inputs.village_generators.Existing_Cap_MW[inputs.VIL_STOR]
                change_storage = total_storage .- start_storage

                village_storage = DataFrame(
                    ID                    = inputs.VIL_STOR,
                    Zone                  = inputs.village_generators.Zone[inputs.VIL_STOR],
                    Village       = inputs.village_generators.Village[inputs.VIL_STOR],
                    Resource              = inputs.village_generators.Resource[inputs.VIL_STOR],
                    Total_Storage_MWh     = total_storage,
                    Start_Storage_MWh     = start_storage,
                    Change_in_Storage_MWh = change_storage,
                )
            else
                @warn "solution.VIL_E_CAP is not a JuMP container. Using zero-filled values."
                N = length(inputs.VIL_STOR)
                village_storage = DataFrame(
                    ID                    = inputs.VIL_STOR,
                    Zone                  = inputs.village_generators.Zone[inputs.VIL_STOR],
                    Resource              = inputs.village_generators.Resource[inputs.VIL_STOR],
                    Total_Storage_MWh     = zeros(N),
                    Start_Storage_MWh     = inputs.village_generators.Existing_Cap_MW[inputs.VIL_STOR],
                    Change_in_Storage_MWh = -inputs.village_generators.Existing_Cap_MW[inputs.VIL_STOR],
                )
            end
        catch e
            @error "Error generating village_storage DataFrame: $e"
            village_storage = DataFrame()
        end
    end


    transmission = DataFrame(
        ID                       = inputs.L,
        Path                     = inputs.lines.path_name[inputs.L],
        Substation_Path          = inputs.lines.substation_path[inputs.L],
        Total_Transfer_Capacity  = value.(solution.T_CAP).data,
        Start_Transfer_Capacity  = inputs.lines.Line_Max_Flow_MW,
        Change_in_Transfer_Capacity = value.(solution.T_CAP).data .- inputs.lines.Line_Max_Flow_MW,
    )

    FLOWv = value.(solution.FLOW)
    transmission_flow = DataFrame(
        ID           = inputs.L,
        Path         = inputs.lines.path_name[inputs.L],
        Net_Flow_MWh = [annualise(FLOWv[:, l].data) for l in inputs.L],
        Peak_Flow_MW = [maximum(FLOWv[:, l].data) for l in inputs.L],
    )

    num_s = maximum(inputs.S)
    num_z = maximum(inputs.Z)
    nse_r = DataFrame(
        Segment               = Int[],
        Zone                  = Int[],
        NSE_Price             = Float64[],
        Max_NSE_MW            = Float64[],
        Total_NSE_MWh         = Float64[],
        NSE_Percent_of_Demand = Float64[]
    )
    NSEv = value.(solution.NSE)
    for s in inputs.S, z in inputs.Z
        push!(nse_r, (
            s,
            z,
            inputs.nse.NSE_Cost[s],
            maximum(NSEv[:, s, z].data),
            annualise(NSEv[:, s, z].data),
            annualise(NSEv[:, s, z].data) / total_demand * 100
        ))
    end

    nse_r_village = DataFrame(
        Segment               = Int[],
        Zone                  = Int[],
        NSE_Price             = Float64[],
        Max_NSE_MW            = Float64[],
        Total_NSE_MWh         = Float64[],
        NSE_Percent_of_Demand = Float64[]
    )
    VILNSEv = value.(solution.VIL_NSE)
    for s in inputs.S, vil in inputs.VIL
        push!(nse_r_village, (
            s,
            vil,
            inputs.nse.NSE_Cost[s],
            maximum(VILNSEv[:, s, vil].data),
            annualise(VILNSEv[:, s, vil].data),
            annualise(VILNSEv[:, s, vil].data) / total_demand * 100
        ))
    end

    nse_heat_village = DataFrame(
        Segment               = Int[],
        Zone                  = Int[],
        NSE_Price             = Float64[],
        Max_NSE_MW            = Float64[],
        Total_NSE_MWh         = Float64[],
        NSE_Percent_of_Demand = Float64[]
    )
    VILNSEHEATv = value.(solution.VIL_NSE_HEAT)
    for s in inputs.S, vil in inputs.VIL
        push!(nse_heat_village, (
            s,
            vil,
            inputs.nse.NSE_Cost[s],
            maximum(VILNSEHEATv[:, s, vil].data),
            annualise(VILNSEHEATv[:, s, vil].data),
            annualise(VILNSEHEATv[:, s, vil].data) / total_demand * 100
        ))
    end

    cost = DataFrame(
        Total_Costs              = solution.cost / 1e6,
        Fixed_Costs_Generation   = value.(solution.FixedCostsGeneration) / 1e6,
        Fixed_Costs_Transmission = value.(solution.FixedCostsTransmission) / 1e6,
        Fixed_Costs_Storage      = value.(solution.FixedCostsStorage) / 1e6,
        Fixed_Costs_Village           = value.(solution.FixedCostsVILGeneration) / 1e6,
        Fixed_Costs_Village_Storage   = value.(solution.FixedCostsVILStorage) / 1e6,
        Variable_Costs_Grid      = value.(solution.VariableCostsGrid) / 1e6,
        Variable_Costs_Village        = value.(solution.VariableCostsVIL) / 1e6,
        NSE_Costs                = value.(solution.NSECosts) / 1e6,
        VILNSECosts               = value.(solution.VILNSECosts) / 1e6,
        VILNSEHeatCosts           = value.(solution.VILNSEHeatCosts) / 1e6,
        Grid_Import_Costs        = value.(solution.GridImportCosts) / 1e6,
        Village_Export_Revenue   = value.(solution.VILExportRevenue) / 1e6,
        StartCostsGrid           = value.(solution.StartCostsGrid) / 1e6,
        StartCostsVIL             = value.(solution.StartCostsVIL) / 1e6

    )

    # Grid_REShare is renewable grid generation over grid demand. With no grid
    # demand (a site-only dataset such as timor) that ratio is undefined, not 0 —
    # reporting 0 % would read as "the grid runs on fossil", which is not a fact
    # about anything. NaN says "not applicable here"; System_REShare, whose
    # denominator includes site demand, is the meaningful figure on those runs.
    grid_re_share = get(solution, :GridDemandPositive, true) ?
        value.(solution.REShare) : NaN

    clean_energy = DataFrame(
        CO2_Emissions      = value.(solution.CO2Emissions),
        CO2_Emissions_Grid = value.(solution.CO2EmissionsGrid),
        CO2_Emissions_Village   = value.(solution.CO2EmissionsVIL),
        Grid_REShare       = grid_re_share,
        System_REShare     = value.(solution.REShareSystem)
    )

    # 11) Write CSVs into the scenario folder
    # Canonical `site_` naming for the decentralised-node result tables (the data
    # core's site vocabulary — village_/ip_ are input aliases; outputs are site_).
    CSV.write(joinpath(results_dir, "generator_results.csv"),      generator)
    CSV.write(joinpath(results_dir, "site_generator_results.csv"),      village_generators)
    CSV.write(joinpath(results_dir, "site_heat_generator_results.csv"), village_heat_generators)
    CSV.write(joinpath(results_dir, "site_import_results.csv"),         village_import)
    CSV.write(joinpath(results_dir, "site_connection_results.csv"),     village_connection)
    CSV.write(joinpath(results_dir, "transmission_flow_results.csv"),   transmission_flow)
    CSV.write(joinpath(results_dir, "storage_results.csv"),        storage)
    CSV.write(joinpath(results_dir, "site_storage_results.csv"),        village_storage)
    CSV.write(joinpath(results_dir, "transmission_results.csv"),   transmission)
    CSV.write(joinpath(results_dir, "nse_results.csv"),            nse_r)
    CSV.write(joinpath(results_dir, "site_nse_results.csv"),            nse_r_village)
    CSV.write(joinpath(results_dir, "site_nse_heat_results.csv"),       nse_heat_village)
    CSV.write(joinpath(results_dir, "cost_results.csv"),           cost)
    CSV.write(joinpath(results_dir, "clean_energy_results.csv"),   clean_energy)

    return (
        generator_results        = generator,
        site_generator_results        = village_generators,
        site_heat_generator_results   = village_heat_generators,
        site_import_results           = village_import,
        site_connection_results       = village_connection,
        transmission_flow_results     = transmission_flow,
        storage_results          = storage,
        site_storage_results          = village_storage,
        transmission_results     = transmission,
        nse_results              = nse_r,
        site_nse_results              = nse_r_village,
        site_nse_heat_results         = nse_heat_village,
        cost_results             = cost,
        clean_energy             = clean_energy
    )
end
