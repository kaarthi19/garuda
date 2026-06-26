# zones.jl
#
# Read optional human-readable zone names from zones.csv. Zones are integers
# internally (derived from generators.Zone); zones.csv (columns like `province`
# + `zone`, where `zone` is a label such as "z1") was previously never read.
# This maps zone integer -> name for readable reports and named buses on
# open-format (PyPSA) export. Returns an empty Dict when the file is absent.

const _BOM = Char(0xFEFF)  # byte-order mark some CSV headers carry on the first column

"""
    read_zone_names(path) -> Dict{Int,String}

Parse `zones.csv` at `path` into a `zone integer => name` map. Tolerant of a
leading BOM, column order, a `z`-prefixed zone label (`z1` -> `1`), and the
`province` / `zone_name` / `name` / `system` spellings of the name column.
Returns an empty `Dict` if the file is missing or its columns are unrecognised.
"""
function read_zone_names(path)
    names_map = Dict{Int,String}()
    isfile(path) || return names_map
    df = DataFrame(CSV.File(path))
    norm(s) = lowercase(strip(replace(string(s), _BOM => "")))
    cols = names(df)
    zonecol = findfirst(c -> norm(c) == "zone", cols)
    namecol = findfirst(c -> norm(c) in ("province", "zone_name", "name", "system"), cols)
    (zonecol === nothing || namecol === nothing) && return names_map
    for r in eachrow(df)
        m = match(r"\d+", string(r[cols[zonecol]]))
        m === nothing && continue
        names_map[parse(Int, m.match)] = string(r[cols[namecol]])
    end
    return names_map
end
