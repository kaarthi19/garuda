# site_aliases.jl
#
# The Garuda platform's canonical term for a decentralised demand+generation
# node within a zone is a **site**. Two inherited dataset families spell it
# differently:
#   - `village_*` / `Village`         — the 100 GW village-solar study
#   - `ip_*`      / `Industrial_Park` — the captive-industrial study
# New datasets should use the canonical `site_*` / `Site` spelling. These helpers
# resolve any of the three spellings at the I/O boundary so all of them load,
# while the loader keeps its internal `Village` / `village_*` names unchanged
# (so the engines and result writers need no changes).

# Filename and demand-column prefixes, canonical first.
const SITE_PREFIXES = ("site", "village", "ip")

# Accepted site-identifier column names, canonical first.
const SITE_ID_COLUMNS = (:Site, :Village, :Industrial_Park)

"""
    resolve_site_csv(dir, base) -> String | Nothing

Return the path to the site table `<prefix>_<base>.csv` for the first prefix in
`SITE_PREFIXES` that exists in `dir` (e.g. base `"generators"` →
`site_generators.csv`, else `village_generators.csv`, else `ip_generators.csv`),
or `nothing` if none exists. (Grid tables like `generators.csv` carry no prefix,
so they are never matched here.)
"""
function resolve_site_csv(dir, base)
    for p in SITE_PREFIXES
        f = joinpath(dir, string(p, "_", base, ".csv"))
        isfile(f) && return f
    end
    return nothing
end

"""
    site_id_col(df) -> Symbol

The site-identifier column present in `df` — the first of `SITE_ID_COLUMNS`
(`:Site`, `:Village`, `:Industrial_Park`). Errors if none is present.
"""
function site_id_col(df)
    for c in SITE_ID_COLUMNS
        hasproperty(df, c) && return c
    end
    error("no site-identifier column found; expected one of $(SITE_ID_COLUMNS)")
end

"""
    site_demand_col(df, i) -> Symbol

The demand column for site `i` in `df` — the first present of `demand_site\$i`,
`demand_village\$i`, `demand_ip\$i`. Errors if none is present.
"""
function site_demand_col(df, i)
    for p in SITE_PREFIXES
        c = Symbol(string("demand_", p, i))
        hasproperty(df, c) && return c
    end
    error("no demand column for site $i; expected demand_{site|village|ip}$i")
end
