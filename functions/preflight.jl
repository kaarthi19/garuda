function parse_cli_args(args::Vector{String})
    config_path = "config.json"
    preflight_only = false
    index = 1

    while index <= length(args)
        arg = args[index]

        if arg == "--preflight-only"
            preflight_only = true
        elseif arg == "--config"
            index += 1
            index <= length(args) || error("Missing value after --config")
            config_path = args[index]
        elseif startswith(arg, "--")
            error("Unknown argument: $(arg)")
        else
            config_path = arg
        end

        index += 1
    end

    return (abspath(config_path), preflight_only)
end

function load_config(config_path::AbstractString)
    isfile(config_path) || error("Config file not found: $(config_path)")
    cfg = JSON.parsefile(config_path)

    required_keys = [
        "island",
        "year",
        "scenario",
        "clean",
        "CO235reduction",
        "BAUCO2emissions",
        "CO2_limit",
    ]

    missing_keys = [key for key in required_keys if !haskey(cfg, key)]
    isempty(missing_keys) || error("Config file is missing required keys: $(join(missing_keys, ", "))")

    return cfg
end

function scenario_settings(scenario::AbstractString)
    # "captive" and "gridcaptive" are legacy aliases from the industrial-park
    # studies; they map to the same settings as "village" and "gridvillage".
    if scenario == "base"
        return (Grid = false, VillageBuild = false, ImportPrice = 59.0, NoCoal = false)
    elseif scenario == "gridvillage" || scenario == "gridcaptive"
        return (Grid = true, VillageBuild = true, ImportPrice = 59.0, NoCoal = false)
    elseif scenario == "grid"
        return (Grid = true, VillageBuild = false, ImportPrice = 59.0, NoCoal = false)
    elseif scenario == "village" || scenario == "captive"
        return (Grid = false, VillageBuild = true, ImportPrice = 59.0, NoCoal = false)
    elseif scenario == "highimportprice"
        return (Grid = true, VillageBuild = true, ImportPrice = 59.0 * 1.21, NoCoal = false)
    elseif scenario == "nocoal"
        return (Grid = true, VillageBuild = false, ImportPrice = 59.0, NoCoal = true)
    end

    error("Unknown scenario: $(scenario). Valid values: base, grid, village, gridvillage, highimportprice, nocoal")
end

function clean_settings(clean::AbstractString)
    if clean == "reference"
        return (CO2_constraint = false, RE_constraint = false)
    elseif clean == "clean"
        return (CO2_constraint = true, RE_constraint = true)
    end

    error("Unknown clean flag: $(clean)")
end

function expected_input_files(flags)
    required = [
        "generators.csv",
        "demand.csv",
        "generators_variability.csv",
        "fuels_data.csv",
    ]

    if flags.Grid
        push!(required, "network.csv")
    end

    if flags.VillageBuild
        # canonical `site_` names; any of the site_/village_/ip_ spellings satisfies
        # the requirement (resolved in validate_input_files), so captive (ip_) and
        # village (village_) datasets both pass.
        append!(required, [
            "site_generators.csv",
            "site_demand.csv",
            "site_demandheat.csv",
            "site_generators_variability.csv",
        ])
    end

    return required
end

# accepted site-table spellings, canonical first (mirrors functions/site_aliases.jl)
const _SITE_PREFIXES = ("site_", "village_", "ip_")

# A required input is present if the file exists, or — for a site table (a
# `site_*` name) — if any of the site_/village_/ip_ spellings of it exists.
function _input_present(inputs_path::AbstractString, filename::AbstractString)
    isfile(joinpath(inputs_path, filename)) && return true
    for p in _SITE_PREFIXES
        if startswith(filename, p)
            base = filename[length(p)+1:end]
            for q in _SITE_PREFIXES
                isfile(joinpath(inputs_path, q * base)) && return true
            end
        end
    end
    return false
end

function validate_input_files(inputs_path::AbstractString, flags)
    isdir(inputs_path) || error("Input data directory not found: $(inputs_path)")

    missing_files = [f for f in expected_input_files(flags) if !_input_present(inputs_path, f)]

    isempty(missing_files) || error(
        "Missing required input files in $(inputs_path): $(join(missing_files, ", "))"
    )
end

function validate_solver(solver::AbstractString)
    s = lowercase(strip(solver))
    try
        model = s == "gurobi" ? Model(Gurobi.Optimizer) : Model(HiGHS.Optimizer)
        set_silent(model)
        @variable(model, 0 <= x <= 1)
        @objective(model, Max, x)
        optimize!(model)
    catch err
        error(
            "Solver \"$(solver)\" could not start a working optimizer session: " *
            sprint(showerror, err)
        )
    end

    return nothing
end

function validate_schema(inputs_path::AbstractString, repo_root::AbstractString)
    # Best-effort: shell out to the Python schema validator (tools/validate_schema.py).
    # Block only on confirmed data errors (exit 1); skip with a warning if the
    # validator cannot run (no python/pandas) so a pure-Julia setup is never blocked.
    script = joinpath(repo_root, "tools", "validate_schema.py")
    isfile(script) || return nothing
    get(ENV, "GARUDA_SKIP_VALIDATION", "") == "1" && return nothing
    python = get(ENV, "GARUDA_PYTHON", "python3")
    buf = IOBuffer()
    code = try
        run(pipeline(ignorestatus(`$(python) $(script) $(inputs_path)`); stdout = buf, stderr = buf)).exitcode
    catch err
        @warn "schema validation skipped: $(sprint(showerror, err))"
        return nothing
    end
    out = String(take!(buf))
    if code == 0
        return nothing
    elseif code == 1
        error("Input schema validation failed:\n" * out *
              "\nFix the inputs above, or set GARUDA_SKIP_VALIDATION=1 to bypass.")
    else
        @warn "schema validation skipped (validator exit $(code)):\n$(out)"
        return nothing
    end
end

function run_preflight(config_path::AbstractString, repo_root::AbstractString)
    cfg = load_config(config_path)
    flags = scenario_settings(cfg["scenario"])
    clean_flags = clean_settings(cfg["clean"])
    solver = lowercase(get(cfg, "solver", "highs"))
    inputs_path = joinpath(repo_root, "data_indonesia", cfg["year"], cfg["island"])
    results_dir = joinpath(repo_root, "results", "$(cfg["scenario"])_$(cfg["island"])_$(cfg["year"])_$(cfg["clean"])")

    validate_solver(solver)
    validate_input_files(inputs_path, flags)
    validate_schema(inputs_path, repo_root)

    return (
        cfg = cfg,
        flags = flags,
        clean_flags = clean_flags,
        inputs_path = inputs_path,
        results_dir = results_dir,
        solver = solver,
    )
end