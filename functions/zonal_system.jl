# zonal_system.jl
#
# Layer A — Data Core type for the Garuda platform.
#
# `ZonalSystem` is a thin, documented wrapper around the engine-agnostic data
# object produced by `input_data` (see input_data.jl). It exists so every
# analysis engine — capacity expansion, dispatch/reliability, no-solve
# screening, open-format export — dispatches on a single named, contracted type
# instead of an anonymous NamedTuple, while the data it carries (DataFrames,
# index sets, time structure, derived economics, site tables) stays exactly as
# the loader produced it. It contains NO JuMP/solver objects.

"""
    ZonalSystem

Engine-agnostic, in-memory representation of a zonal power system: the platform's
**Layer A data core**. Carries grid tables (`generators`, `demand`,
`variability`, `lines`, `nse`), site/village tables (`village_*`), index
sets/subsets (`G`, `Z`, `L`, `UC`, `ED`, `STOR`, `VRE`, `VIL`, …), the
representative-period time structure (`T`, `P`, `W`, `sample_weight`,
`hours_per_period`), and derived economics (`Var_Cost`, `CO2_Rate`, … columns on
the generator frames). It holds no solver state.

Build one with [`build_system`](@ref). Property access forwards to the underlying
loaded data, so `sys.generators`, `sys.G`, `sys.sample_weight`, `sys.VIL`, … work
exactly as the loader's NamedTuple. The raw NamedTuple is available as `sys.data`.
"""
struct ZonalSystem
    data::NamedTuple
end

# Forward field access to the wrapped data so existing engine code (`inputs.G`,
# `inputs.demand`, …) is unchanged; `sys.data` returns the raw NamedTuple.
function Base.getproperty(sys::ZonalSystem, name::Symbol)
    name === :data && return getfield(sys, :data)
    return getproperty(getfield(sys, :data), name)
end

Base.propertynames(sys::ZonalSystem) = (:data, propertynames(getfield(sys, :data))...)

"""
    build_system(filepath) -> ZonalSystem

Load a model input folder (the same folder layout `input_data` reads) and wrap it
as a [`ZonalSystem`](@ref). Behaviourally identical to calling `input_data`
directly — just typed and documented — so it is a drop-in for the loader on the
existing solve path.
"""
build_system(filepath::AbstractString) = ZonalSystem(input_data(filepath))
