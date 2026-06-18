"""
Island + rules attribution for synthetic building trip emissions.

Rules:
  - Off-island / off-island: exclude
  - Off-island -> on-island: destination (exclude return-home purpose 11)
  - On-island -> off-island: origin
  - On-island / on-island: home-orig -> dest; home-dest -> orig; else -> dest

HOME from person_buildings. Requires trip lat/lon on the trips table.
"""

from __future__ import annotations

import re

SCHEMA = "popgen"

CAR_MODE_FILTER = (
    "trim(COALESCE(e.mode_group, t.mode_group)::text) IN ('1','1.0','10','11','10.0','11.0')"
)
CAR_MODE_FILTER_ROUTES = (
    "trim(COALESCE(r.mode_group::text, t.mode_group::text)) IN ('1','1.0','10','11','10.0','11.0')"
)
EMISSIONS_G_EXPR = "COALESCE(e.emissions_g_pair, e.emissions_g)::double precision"
ROUTE_EMISSIONS_G_EXPR = "r.route_emissions_g::double precision"
CAR_MODE_LIST = "'1','1.0','10','11','10.0','11.0'"


def _pg_ident(name: str) -> str:
    s = str(name).strip().lower()
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", s):
        raise ValueError(f"Invalid PostgreSQL identifier: {name!r}")
    return s


def home_flags_lateral_sql(*, pb_alias: str = "pb", t_alias: str = "t") -> str:
    pb, t = pb_alias, t_alias
    return f"""
        CROSS JOIN LATERAL (
            SELECT
                (
                    ({pb}.home_building_id IS NOT NULL
                      AND {t}.orig_building_id::text = {pb}.home_building_id::text)
                    OR ({pb}.home_geo_id IS NOT NULL
                      AND {t}.orig_geo_id::text = {pb}.home_geo_id::text)
                ) AS is_home_orig,
                (
                    ({pb}.home_building_id IS NOT NULL
                      AND {t}.dest_building_id::text = {pb}.home_building_id::text)
                    OR ({pb}.home_geo_id IS NOT NULL
                      AND {t}.dest_geo_id::text = {pb}.home_geo_id::text)
                ) AS is_home_dest
        ) flags
    """


def home_flags_geo_lateral_sql(*, pb_alias: str = "pb", r_alias: str = "r") -> str:
    """HOME at orig/dest using zone geo_id only (route rows have no building_id)."""
    pb, r = pb_alias, r_alias
    return f"""
        CROSS JOIN LATERAL (
            SELECT
                ({pb}.home_geo_id IS NOT NULL
                  AND {r}.orig_geo_id::text = {pb}.home_geo_id::text) AS is_home_orig,
                ({pb}.home_geo_id IS NOT NULL
                  AND {r}.dest_geo_id::text = {pb}.home_geo_id::text) AS is_home_dest
        ) flags
    """


def is_return_home_sql(*, leg_alias: str = "t") -> str:
    L = leg_alias
    return (
        f"regexp_replace(trim(COALESCE({L}.purpose::text, '')), '\\\\.0$', '') = '11'"
    )


def motif_travel_reason_sql(*, purpose_expr: str) -> str:
    p = f"regexp_replace(trim(COALESCE({purpose_expr}::text, '')), '\\\\.0$', '')"
    return f"""
        CASE {p}
            WHEN '1' THEN 'work'
            WHEN '2' THEN 'work'
            WHEN '3' THEN 'education'
            WHEN '4' THEN 'education'
            WHEN '5' THEN 'shopping'
            WHEN '6' THEN 'personal_business'
            WHEN '7' THEN 'leisure'
            WHEN '8' THEN 'visit_social'
            WHEN '9' THEN 'health'
            WHEN '10' THEN 'pickup_dropoff'
            WHEN '11' THEN 'return_home'
            ELSE 'other'
        END
    """


def mapped_geo_id_sql(*, leg_alias: str = "leg") -> str:
    L = leg_alias
    return f"""
        CASE
            WHEN NOT {L}.orig_on_island AND NOT {L}.dest_on_island THEN NULL::text
            WHEN NOT {L}.orig_on_island AND {L}.dest_on_island AND {L}.is_return_home THEN NULL::text
            WHEN NOT {L}.orig_on_island AND {L}.dest_on_island THEN {L}.dest_geo_id::text
            WHEN {L}.orig_on_island AND NOT {L}.dest_on_island THEN {L}.orig_geo_id::text
            WHEN {L}.orig_on_island AND {L}.dest_on_island AND {L}.is_home_orig THEN {L}.dest_geo_id::text
            WHEN {L}.orig_on_island AND {L}.dest_on_island AND {L}.is_home_dest THEN {L}.orig_geo_id::text
            WHEN {L}.orig_on_island AND {L}.dest_on_island THEN {L}.dest_geo_id::text
            ELSE NULL::text
        END
    """


def mapped_building_id_sql(*, leg_alias: str = "leg") -> str:
    """
    Same island + meeting rules as mapped_geo_id_sql, but attributed building id.

    Building choice is travel-reason aware when person_buildings provides it:
      - work/work-related -> pb.work_building_id (fallback dest_building_id)
      - education/school  -> pb.education_building_id (fallback dest_building_id)
      - other reasons     -> dest_building_id (or orig_building_id where rules say origin)
    """
    L = leg_alias
    reason = motif_travel_reason_sql(purpose_expr=f"{L}.purpose")
    dest_activity_building = f"""
        CASE ({reason})
            WHEN 'work' THEN COALESCE(NULLIF(btrim({L}.work_building_id::text), ''), NULLIF(btrim({L}.dest_building_id::text), ''))
            WHEN 'education' THEN COALESCE(NULLIF(btrim({L}.education_building_id::text), ''), NULLIF(btrim({L}.dest_building_id::text), ''))
            ELSE NULLIF(btrim({L}.dest_building_id::text), '')
        END
    """
    return f"""
        CASE
            WHEN NOT {L}.orig_on_island AND NOT {L}.dest_on_island THEN NULL::text
            WHEN NOT {L}.orig_on_island AND {L}.dest_on_island AND {L}.is_return_home THEN NULL::text
            WHEN NOT {L}.orig_on_island AND {L}.dest_on_island THEN ({dest_activity_building})
            WHEN {L}.orig_on_island AND NOT {L}.dest_on_island THEN NULLIF(btrim({L}.orig_building_id::text), '')
            WHEN {L}.orig_on_island AND {L}.dest_on_island AND {L}.is_home_orig THEN ({dest_activity_building})
            WHEN {L}.orig_on_island AND {L}.dest_on_island AND {L}.is_home_dest THEN NULLIF(btrim({L}.orig_building_id::text), '')
            WHEN {L}.orig_on_island AND {L}.dest_on_island THEN ({dest_activity_building})
            ELSE NULL::text
        END
    """


def route_assignment_label_sql(*, leg_alias: str = "leg", target: str = "zone") -> str:
    L = leg_alias
    mapped = mapped_building_id_sql(leg_alias=L) if str(target).strip().lower() == "building" else mapped_geo_id_sql(leg_alias=L)
    return f"({motif_travel_reason_sql(purpose_expr=f'{L}.purpose')}) || ':' || ({mapped})"


def home_flags_buildings_lateral_sql(*, pb_alias: str = "pb", r_alias: str = "r") -> str:
    """HOME at orig/dest using building id when present, else home zone geo."""
    pb, r = pb_alias, r_alias
    return f"""
        CROSS JOIN LATERAL (
            SELECT
                (
                    ({pb}.home_building_id IS NOT NULL
                      AND NULLIF(btrim({r}.orig_building_id::text), '') IS NOT NULL
                      AND {r}.orig_building_id::text = {pb}.home_building_id::text)
                    OR ({pb}.home_geo_id IS NOT NULL
                      AND {r}.orig_geo_id::text = {pb}.home_geo_id::text)
                ) AS is_home_orig,
                (
                    ({pb}.home_building_id IS NOT NULL
                      AND NULLIF(btrim({r}.dest_building_id::text), '') IS NOT NULL
                      AND {r}.dest_building_id::text = {pb}.home_building_id::text)
                    OR ({pb}.home_geo_id IS NOT NULL
                      AND {r}.dest_geo_id::text = {pb}.home_geo_id::text)
                ) AS is_home_dest
        ) flags
    """


def building_meeting_aggregate_sql(
    emissions_table: str,
    trips_table: str,
    person_buildings_table: str,
    trip_emissions_key_join: str,
    *,
    min_emissions_g: float = 0.0,
    boundary_placeholder: str = ":boundary_wkt",
) -> str:
    bph = boundary_placeholder
    em = _pg_ident(emissions_table)
    trips = _pg_ident(trips_table)
    pb = _pg_ident(person_buildings_table)
    having = f"HAVING SUM(emissions_g) >= {float(min_emissions_g)}" if min_emissions_g > 0 else ""

    return f"""
    WITH island AS (
        SELECT ST_SetSRID(ST_GeomFromText({bph}, 4326), 4326) AS geom
    ),
    zone_agg AS (
        SELECT mapped_geo_id::text AS geo_id, COUNT(*)::bigint AS trips,
               SUM(emissions_g)::double precision AS emissions_g
        FROM (
            SELECT {mapped_geo_id_sql()} AS mapped_geo_id, leg.emissions_g
            FROM (
                SELECT t.orig_geo_id, t.dest_geo_id, flags.is_home_orig, flags.is_home_dest,
                       {EMISSIONS_G_EXPR} AS emissions_g,
                       ST_Contains(i.geom, ST_SetSRID(ST_Point(t.orig_lon::double precision, t.orig_lat::double precision), 4326)) AS orig_on_island,
                       ST_Contains(i.geom, ST_SetSRID(ST_Point(t.dest_lon::double precision, t.dest_lat::double precision), 4326)) AS dest_on_island,
                       ({is_return_home_sql()}) AS is_return_home
                FROM {SCHEMA}.{em} AS e
                JOIN {SCHEMA}.{trips} AS t
                  ON t.synthetic_person_id::text = e.synthetic_person_id::text
                 AND t.orig_geo_id::int = e.orig_geo_id::int
                 AND t.dest_geo_id::int = e.dest_geo_id::int
                 {trip_emissions_key_join}
                 AND (e.hh_id IS NULL OR t.hh_id::text IS NOT DISTINCT FROM e.hh_id::text)
                LEFT JOIN {SCHEMA}.{pb} AS pb
                  ON pb.synthetic_person_id::text = e.synthetic_person_id::text
                 AND pb.hh_id::text IS NOT DISTINCT FROM COALESCE(e.hh_id, t.hh_id)::text
                {home_flags_lateral_sql()}
                CROSS JOIN island AS i
                WHERE {EMISSIONS_G_EXPR} > 0 AND {CAR_MODE_FILTER}
                  AND t.orig_lat IS NOT NULL AND t.orig_lon IS NOT NULL
                  AND t.dest_lat IS NOT NULL AND t.dest_lon IS NOT NULL
            ) AS leg
        ) x
        WHERE mapped_geo_id IS NOT NULL AND btrim(mapped_geo_id) <> ''
        GROUP BY mapped_geo_id
        {having}
    )
    SELECT geo_id, trips, emissions_g FROM zone_agg
    """


def trip_routes_key_join_sql(*, t_alias: str = "t", r_alias: str = "r") -> str:
    t, r = t_alias, r_alias
    return f"""
         AND regexp_replace(trim(COALESCE({t}.purpose::text, '')), '\\\\.0$', '') =
             regexp_replace(trim(COALESCE({r}.purpose::text, '')), '\\\\.0$', '')
         AND (
             CASE WHEN trim(COALESCE({t}.dep_time_bin::text, '')) = '' THEN NULL::numeric
                  ELSE trim({t}.dep_time_bin::text)::numeric
             END
         ) IS NOT DISTINCT FROM (
             CASE WHEN trim(COALESCE({r}.dep_time_bin::text, '')) = '' THEN NULL::numeric
                  ELSE trim({r}.dep_time_bin::text)::numeric
             END
         )
    """


def routes_meeting_aggregate_sql(
    routes_table: str,
    trips_table: str,
    person_buildings_table: str,
    *,
    min_emissions_g: float = 0.0,
    boundary_placeholder: str = "%(boundary_wkt)s",
) -> str:
    """
    Island + meeting aggregation from trip_routes_* (route_emissions_g) joined to popgen_trip_building_*.
  Bind ``%(boundary_wkt)s``. Trips table must have orig/dest lat/lon and building ids.
    """
    bph = boundary_placeholder
    routes = _pg_ident(routes_table)
    trips = _pg_ident(trips_table)
    pb = _pg_ident(person_buildings_table)
    having = f"HAVING SUM(emissions_g) >= {float(min_emissions_g)}" if min_emissions_g > 0 else ""
    tr_join = trip_routes_key_join_sql()

    return f"""
    WITH island AS (
        SELECT ST_SetSRID(ST_GeomFromText({bph}, 4326), 4326) AS geom
    ),
    zone_agg AS (
        SELECT mapped_geo_id::text AS geo_id, COUNT(*)::bigint AS trips,
               SUM(emissions_g)::double precision AS emissions_g
        FROM (
            SELECT {mapped_geo_id_sql()} AS mapped_geo_id, leg.emissions_g
            FROM (
                SELECT t.orig_geo_id, t.dest_geo_id, flags.is_home_orig, flags.is_home_dest,
                       {ROUTE_EMISSIONS_G_EXPR} AS emissions_g,
                       ST_Contains(i.geom, ST_SetSRID(ST_Point(t.orig_lon::double precision, t.orig_lat::double precision), 4326)) AS orig_on_island,
                       ST_Contains(i.geom, ST_SetSRID(ST_Point(t.dest_lon::double precision, t.dest_lat::double precision), 4326)) AS dest_on_island,
                       ({is_return_home_sql(leg_alias="t")}) AS is_return_home
                FROM {SCHEMA}.{routes} AS r
                JOIN {SCHEMA}.{trips} AS t
                  ON t.synthetic_person_id::text = r.synthetic_person_id::text
                 AND t.orig_geo_id::int = r.orig_geo_id::int
                 AND t.dest_geo_id::int = r.dest_geo_id::int
                 {tr_join}
                 AND (r.hh_id IS NULL OR t.hh_id::text IS NOT DISTINCT FROM r.hh_id::text)
                LEFT JOIN {SCHEMA}.{pb} AS pb
                  ON pb.synthetic_person_id::text = r.synthetic_person_id::text
                 AND pb.hh_id::text IS NOT DISTINCT FROM COALESCE(r.hh_id::text, t.hh_id::text)
                {home_flags_lateral_sql(pb_alias="pb", t_alias="t")}
                CROSS JOIN island AS i
                WHERE r.route_emissions_g IS NOT NULL AND r.route_emissions_g > 0
                  AND r.distance_m > 0 AND {CAR_MODE_FILTER_ROUTES}
                  AND t.orig_lat IS NOT NULL AND t.orig_lon IS NOT NULL
                  AND t.dest_lat IS NOT NULL AND t.dest_lon IS NOT NULL
            ) AS leg
        ) x
        WHERE mapped_geo_id IS NOT NULL AND btrim(mapped_geo_id) <> ''
        GROUP BY mapped_geo_id
        {having}
    )
    SELECT geo_id, trips, emissions_g FROM zone_agg
    """


def routes_meeting_assignment_aggregate_sql(
    routes_table: str,
    *,
    min_emissions_g: float = 0.0,
) -> str:
    """Fast zone totals from meeting ``route_emission_assignment`` labels (motif:geo_id)."""
    routes = _pg_ident(routes_table)
    having = f"HAVING SUM(emissions_g) >= {float(min_emissions_g)}" if min_emissions_g > 0 else ""
    return f"""
    WITH per_route AS (
        SELECT
            r.route_emissions_g::double precision AS emissions_g,
            NULLIF(
                trim(
                    CASE
                        WHEN position(':' IN r.route_emission_assignment::text) > 0 THEN
                            split_part(r.route_emission_assignment::text, ':', 2)
                        ELSE regexp_replace(
                            r.route_emission_assignment::text, '^[^:]*:', ''
                        )
                    END
                ),
                ''
            ) AS geo_raw
        FROM {SCHEMA}.{routes} AS r
        WHERE r.route_emissions_g IS NOT NULL AND r.route_emissions_g > 0
          AND r.route_emission_assignment IS NOT NULL
          AND btrim(r.route_emission_assignment::text) <> ''
    ),
    keyed AS (
        SELECT
            emissions_g,
            CASE
                WHEN geo_raw ~ '^[0-9]+(\\.[0-9]+)?$' THEN (geo_raw::numeric)::bigint::text
                ELSE geo_raw
            END AS geo_id
        FROM per_route
        WHERE geo_raw IS NOT NULL
    ),
    zone_agg AS (
        SELECT geo_id, COUNT(*)::bigint AS trips,
               SUM(emissions_g)::double precision AS emissions_g
        FROM keyed
        WHERE geo_id IS NOT NULL AND btrim(geo_id) <> ''
        GROUP BY geo_id
        {having}
    )
    SELECT geo_id, trips, emissions_g FROM zone_agg
    """


def routes_meeting_attributed_geo_aggregate_sql(
    routes_table: str,
    *,
    min_emissions_g: float = 0.0,
) -> str:
    """Zone totals from rules ``route_attributed_geo_id`` (works with building attribution)."""
    routes = _pg_ident(routes_table)
    having = f"HAVING SUM(emissions_g) >= {float(min_emissions_g)}" if min_emissions_g > 0 else ""
    return f"""
    WITH keyed AS (
        SELECT
            r.route_emissions_g::double precision AS emissions_g,
            COALESCE(r.distance_m, 0)::double precision AS distance_m,
            split_part(trim(r.route_attributed_geo_id::text), '.', 1) AS geo_id
        FROM {SCHEMA}.{routes} AS r
        WHERE r.route_emissions_g IS NOT NULL AND r.route_emissions_g > 0
          AND r.route_attributed_geo_id IS NOT NULL
          AND btrim(r.route_attributed_geo_id::text) <> ''
    ),
    zone_agg AS (
        SELECT geo_id, COUNT(*)::bigint AS trips,
               SUM(emissions_g)::double precision AS emissions_g,
               SUM(distance_m)::double precision / 1000.0 AS distance_km
        FROM keyed
        WHERE geo_id IS NOT NULL AND btrim(geo_id) <> ''
        GROUP BY geo_id
        {having}
    )
    SELECT geo_id, trips, emissions_g, distance_km FROM zone_agg
    """


def routes_dest_geo_aggregate_sql(
    routes_table: str,
    *,
    min_emissions_g: float = 0.0,
) -> str:
    """Zone totals from destination CT only (``route_dest_geo_id`` or ``dest_geo_id``)."""
    routes = _pg_ident(routes_table)
    having = f"HAVING SUM(emissions_g) >= {float(min_emissions_g)}" if min_emissions_g > 0 else ""
    return f"""
    WITH keyed AS (
        SELECT
            r.route_emissions_g::double precision AS emissions_g,
            COALESCE(r.distance_m, 0)::double precision AS distance_m,
            split_part(
                trim(
                    COALESCE(
                        NULLIF(btrim(r.route_dest_geo_id::text), ''),
                        r.dest_geo_id::text
                    )
                ),
                '.',
                1
            ) AS geo_id
        FROM {SCHEMA}.{routes} AS r
        WHERE r.route_emissions_g IS NOT NULL AND r.route_emissions_g > 0
          AND COALESCE(
                NULLIF(btrim(r.route_dest_geo_id::text), ''),
                NULLIF(btrim(r.dest_geo_id::text), '')
              ) IS NOT NULL
    ),
    zone_agg AS (
        SELECT geo_id, COUNT(*)::bigint AS trips,
               SUM(emissions_g)::double precision AS emissions_g,
               SUM(distance_m)::double precision / 1000.0 AS distance_km
        FROM keyed
        WHERE geo_id IS NOT NULL AND btrim(geo_id) <> ''
        GROUP BY geo_id
        {having}
    )
    SELECT geo_id, trips, emissions_g, distance_km FROM zone_agg
    """


def routes_building_rules_aggregate_sql(
    routes_table: str,
    *,
    min_emissions_g: float = 0.0,
) -> str:
    """Building totals: sum route emissions by ``route_attributed_building_id`` (island/rules)."""
    routes = _pg_ident(routes_table)
    having = f"HAVING SUM(emissions_g) >= {float(min_emissions_g)}" if min_emissions_g > 0 else ""
    return f"""
    WITH keyed AS (
        SELECT
            r.route_attributed_building_id::text AS building_id,
            r.route_emissions_g::double precision AS emissions_g,
            COALESCE(r.distance_m, 0)::double precision AS distance_m
        FROM {SCHEMA}.{routes} AS r
        WHERE r.route_emissions_g IS NOT NULL AND r.route_emissions_g > 0
          AND r.route_attributed_building_id IS NOT NULL
          AND btrim(r.route_attributed_building_id::text) <> ''
    ),
    building_agg AS (
        SELECT building_id, COUNT(*)::bigint AS trips,
               SUM(emissions_g)::double precision AS emissions_g,
               SUM(distance_m)::double precision / 1000.0 AS distance_km
        FROM keyed
        WHERE building_id IS NOT NULL AND btrim(building_id) <> ''
        GROUP BY building_id
        {having}
    )
    SELECT building_id, trips, emissions_g, distance_km FROM building_agg
    """


def routes_building_dest_aggregate_sql(
    routes_table: str,
    *,
    min_emissions_g: float = 0.0,
) -> str:
    """Building totals: sum route emissions by ``dest_building_id`` (destination end)."""
    routes = _pg_ident(routes_table)
    having = f"HAVING SUM(emissions_g) >= {float(min_emissions_g)}" if min_emissions_g > 0 else ""
    return f"""
    WITH keyed AS (
        SELECT
            r.dest_building_id::text AS building_id,
            r.route_emissions_g::double precision AS emissions_g,
            COALESCE(r.distance_m, 0)::double precision AS distance_m
        FROM {SCHEMA}.{routes} AS r
        WHERE r.route_emissions_g IS NOT NULL AND r.route_emissions_g > 0
          AND r.dest_building_id IS NOT NULL
          AND btrim(r.dest_building_id::text) <> ''
    ),
    building_agg AS (
        SELECT building_id, COUNT(*)::bigint AS trips,
               SUM(emissions_g)::double precision AS emissions_g,
               SUM(distance_m)::double precision / 1000.0 AS distance_km
        FROM keyed
        WHERE building_id IS NOT NULL AND btrim(building_id) <> ''
        GROUP BY building_id
        {having}
    )
    SELECT building_id, trips, emissions_g, distance_km FROM building_agg
    """


def routes_meeting_zone_from_buildings_aggregate_sql(
    routes_table: str,
    buildings_table: str = "buildings_footprint",
    *,
    min_emissions_g: float = 0.0,
) -> str:
    """Zone totals: sum route emissions by CT zone of the attributed building."""
    routes = _pg_ident(routes_table)
    bldg = _pg_ident(buildings_table)
    having = f"HAVING SUM(emissions_g) >= {float(min_emissions_g)}" if min_emissions_g > 0 else ""
    return f"""
    WITH keyed AS (
        SELECT
            r.route_emissions_g::double precision AS emissions_g,
            split_part(trim(b.zone_geo_id::text), '.', 1) AS geo_id
        FROM {SCHEMA}.{routes} AS r
        JOIN {SCHEMA}.{bldg} AS b ON b.id::text = r.route_attributed_building_id::text
        WHERE r.route_emissions_g IS NOT NULL AND r.route_emissions_g > 0
          AND r.route_attributed_building_id IS NOT NULL
          AND btrim(r.route_attributed_building_id::text) <> ''
    ),
    zone_agg AS (
        SELECT geo_id, COUNT(*)::bigint AS trips,
               SUM(emissions_g)::double precision AS emissions_g
        FROM keyed
        WHERE geo_id IS NOT NULL AND btrim(geo_id) <> ''
        GROUP BY geo_id
        {having}
    )
    SELECT geo_id, trips, emissions_g FROM zone_agg
    """


def island_cte_sql(*, boundary_placeholder: str) -> str:
    return f"""
    island AS (
        SELECT g.geom,
               ST_YMin(g.env) AS lat_min,
               ST_YMax(g.env) AS lat_max,
               ST_XMin(g.env) AS lon_min,
               ST_XMax(g.env) AS lon_max
        FROM (
            SELECT ST_SetSRID(ST_GeomFromText({boundary_placeholder}, 4326), 4326) AS geom,
                   ST_Envelope(ST_SetSRID(ST_GeomFromText({boundary_placeholder}, 4326), 4326)) AS env
        ) AS g
    )"""


def st_on_island_sql(*, lat_expr: str, lon_expr: str, i_alias: str = "i") -> str:
    i = i_alias
    return f"""(
        ({lat_expr})::double precision BETWEEN {i}.lat_min AND {i}.lat_max
        AND ({lon_expr})::double precision BETWEEN {i}.lon_min AND {i}.lon_max
        AND ST_Contains({i}.geom, ST_SetSRID(ST_Point(({lon_expr})::double precision, ({lat_expr})::double precision), 4326))
    )"""


def fleet_leg_seed_u_sql(*, leg_alias: str = "ml") -> str:
    """Deterministic u in (0,1] from leg keys — weighted category pick (reproducible per route)."""
    L = leg_alias
    return f"""(
        (abs(hashtextextended(
            concat_ws('|',
                {L}.synthetic_person_id::text,
                {L}.orig_geo_id::text,
                {L}.dest_geo_id::text,
                COALESCE({L}.purpose::text, ''),
                COALESCE({L}.dep_time_bin::text, '')
            ),
            0
        )) %% 1000000000) + 1
    )::double precision / 1000000001.0"""


def _normalize_fleet_sample(fleet_sample: str) -> str:
    s = str(fleet_sample).strip().lower()
    if s in ("random", "category", "per_trip", "one", "sample"):
        return "random"
    return "blended"


def meeting_routes_populate_sql(
    routes_table: str,
    trips_table: str,
    person_buildings_table: str,
    trip_routes_key_join: str,
    *,
    boundary_placeholder: str = "%(boundary_wkt)s",
    batch_ix: int | None = None,
    n_batches: int | None = None,
    fleet_sample: str = "blended",
    coord_source: str = "routes",
    attribution_target: str = "building",
    attribution_only: bool = False,
) -> str:
    routes = _pg_ident(routes_table)
    trips = _pg_ident(trips_table)
    pb = _pg_ident(person_buildings_table)
    use_building = str(attribution_target).strip().lower() == "building"
    mapped_expr = mapped_building_id_sql(leg_alias="ml") if use_building else mapped_geo_id_sql(leg_alias="ml")
    assign = route_assignment_label_sql(
        leg_alias="ml",
        target="building" if use_building else "zone",
    )
    leg_seed = fleet_leg_seed_u_sql(leg_alias="ml")
    per_trip = _normalize_fleet_sample(fleet_sample) == "random"
    use_routes = str(coord_source).strip().lower() != "trips"
    home_flags_routes = (
        home_flags_buildings_lateral_sql(pb_alias="pb", r_alias="r")
        if use_building
        else home_flags_geo_lateral_sql(pb_alias="pb", r_alias="r")
    )
    batch_filter = ""
    if batch_ix is not None and n_batches is not None:
        nb, bi = int(n_batches), int(batch_ix)
        batch_filter = (
            f"AND (abs(hashtext(r.synthetic_person_id::text)) %% {nb}) = {bi}"
        )

    building_cols = (
        ",\n               r.orig_building_id::text AS orig_building_id, r.dest_building_id::text AS dest_building_id"
        if use_building
        else ""
    )

    if use_routes:
        legs_from = f"""
        FROM {SCHEMA}.{routes} AS r
        LEFT JOIN {SCHEMA}.{pb} AS pb
          ON pb.synthetic_person_id::text = r.synthetic_person_id::text
         AND pb.hh_id::text IS NOT DISTINCT FROM r.hh_id::text
        {home_flags_routes}
        CROSS JOIN island AS i
        WHERE r.orig_lat IS NOT NULL AND r.orig_lon IS NOT NULL
          AND r.dest_lat IS NOT NULL AND r.dest_lon IS NOT NULL
          AND r.distance_m > 0
          {batch_filter}"""
        leg_select = f"""
        SELECT r.ctid AS r_ctid, r.synthetic_person_id,
               r.purpose::text AS purpose, r.dep_time_bin,
               r.distance_m::double precision AS distance_m,
               trim(COALESCE(r.mode_group::text, '')) AS mode_group,
               r.orig_geo_id, r.dest_geo_id{building_cols},
               pb.work_building_id::text AS work_building_id,
               pb.education_building_id::text AS education_building_id,
               flags.is_home_orig, flags.is_home_dest,
               {st_on_island_sql(lat_expr="r.orig_lat", lon_expr="r.orig_lon")} AS orig_on_island,
               {st_on_island_sql(lat_expr="r.dest_lat", lon_expr="r.dest_lon")} AS dest_on_island,
               ({is_return_home_sql(leg_alias="r")}) AS is_return_home"""
    else:
        legs_from = f"""
        FROM {SCHEMA}.{routes} AS r
        JOIN {SCHEMA}.{trips} AS t
          ON t.synthetic_person_id::text = r.synthetic_person_id::text
         AND t.orig_geo_id::int = r.orig_geo_id::int
         AND t.dest_geo_id::int = r.dest_geo_id::int
         {trip_routes_key_join}
         AND (r.hh_id IS NULL OR t.hh_id::text IS NOT DISTINCT FROM r.hh_id::text)
        LEFT JOIN {SCHEMA}.{pb} AS pb
          ON pb.synthetic_person_id::text = r.synthetic_person_id::text
         AND pb.hh_id::text IS NOT DISTINCT FROM COALESCE(r.hh_id::text, t.hh_id::text)
        {home_flags_lateral_sql(pb_alias="pb", t_alias="t")}
        CROSS JOIN island AS i
        WHERE t.orig_lat IS NOT NULL AND t.orig_lon IS NOT NULL
          AND t.dest_lat IS NOT NULL AND t.dest_lon IS NOT NULL AND r.distance_m > 0
          {batch_filter}"""
        leg_select = f"""
        SELECT r.ctid AS r_ctid, r.synthetic_person_id,
               COALESCE(r.purpose::text, t.purpose::text) AS purpose, r.dep_time_bin,
               r.distance_m::double precision AS distance_m,
               trim(COALESCE(r.mode_group::text, t.mode_group::text)) AS mode_group,
               t.orig_geo_id, t.dest_geo_id,
               t.orig_building_id::text AS orig_building_id, t.dest_building_id::text AS dest_building_id,
               pb.work_building_id::text AS work_building_id,
               pb.education_building_id::text AS education_building_id,
               flags.is_home_orig, flags.is_home_dest,
               ST_Contains(i.geom, ST_SetSRID(ST_Point(t.orig_lon::double precision, t.orig_lat::double precision), 4326)) AS orig_on_island,
               ST_Contains(i.geom, ST_SetSRID(ST_Point(t.dest_lon::double precision, t.dest_lat::double precision), 4326)) AS dest_on_island,
               ({is_return_home_sql(leg_alias="t")}) AS is_return_home"""

    attr_building_col = (
        ",\n               CASE WHEN m.mapped_target_id IS NULL OR btrim(m.mapped_target_id) = '' THEN NULL\n                    ELSE m.mapped_target_id END AS attributed_building_id"
        if use_building
        else ",\n               NULL::text AS attributed_building_id"
    )
    attr_geo_col = """
               , CASE WHEN m.mapped_geo_id IS NULL OR btrim(m.mapped_geo_id) = '' THEN NULL
                    ELSE m.mapped_geo_id END AS attributed_geo_id"""
    fleet_cte = ""
    scored_sql = ""
    update_sets = """
        route_emissions_g = s.emissions_g,
        route_emission_assignment = s.assignment_label,
        route_fleet_category_id = s.fleet_category_id,
        route_attributed_building_id = s.attributed_building_id,
        route_attributed_geo_id = s.attributed_geo_id,
        route_dest_geo_id = split_part(trim(r.dest_geo_id::text), '.', 1)"""
    if attribution_only:
        scored_sql = f"""
    scored AS (
        SELECT m.r_ctid,
               CASE WHEN m.mapped_target_id IS NULL OR btrim(m.mapped_target_id) = '' THEN NULL
                    ELSE m.assignment_label END AS assignment_label{attr_building_col}{attr_geo_col}
        FROM mapped AS m
    )"""
        update_sets = """
        route_emission_assignment = s.assignment_label,
        route_attributed_building_id = s.attributed_building_id,
        route_attributed_geo_id = s.attributed_geo_id,
        route_dest_geo_id = split_part(trim(r.dest_geo_id::text), '.', 1)"""
    elif per_trip:
        fleet_cte = f"""
    fleet_cats AS (
        SELECT f.category_id::int AS category_id,
               f.emissions_g_per_km::double precision AS emissions_g_per_km,
               f.share::double precision AS share,
               SUM(f.share::double precision) OVER (ORDER BY f.category_id) AS cum_share
        FROM {SCHEMA}.saaq_fleet_shares AS f
        WHERE f.year = %(fleet_year)s AND f.geo = %(fleet_geo)s
    ),"""
        scored_sql = f"""
    scored AS (
        SELECT m.r_ctid,
               CASE WHEN m.mapped_target_id IS NULL OR btrim(m.mapped_target_id) = '' THEN NULL
                    WHEN m.mode_group IN ({CAR_MODE_LIST}) AND fp.emissions_g_per_km IS NOT NULL
                    THEN (m.distance_m / 1000.0) * fp.emissions_g_per_km ELSE NULL END AS emissions_g,
               CASE WHEN m.mapped_target_id IS NULL OR btrim(m.mapped_target_id) = '' THEN NULL
                    ELSE m.assignment_label END AS assignment_label,
               CASE WHEN m.mapped_target_id IS NULL OR btrim(m.mapped_target_id) = '' THEN NULL
                    WHEN m.mode_group IN ({CAR_MODE_LIST}) THEN fp.category_id ELSE NULL END AS fleet_category_id{attr_building_col}{attr_geo_col}
        FROM mapped AS m
        LEFT JOIN LATERAL (
            SELECT fc.category_id, fc.emissions_g_per_km
            FROM fleet_cats AS fc
            WHERE m.leg_seed_u <= fc.cum_share + 1e-15
            ORDER BY fc.category_id
            LIMIT 1
        ) AS fp ON m.mode_group IN ({CAR_MODE_LIST})
    )"""
    else:
        fleet_cte = f"""
    fleet_mix AS (
        SELECT SUM(f.share * f.emissions_g_per_km)::double precision AS expected_gpkm_g
        FROM {SCHEMA}.saaq_fleet_shares AS f
        WHERE f.year = %(fleet_year)s AND f.geo = %(fleet_geo)s
    ),"""
        scored_sql = f"""
    scored AS (
        SELECT m.r_ctid,
               CASE WHEN m.mapped_target_id IS NULL OR btrim(m.mapped_target_id) = '' THEN NULL
                    WHEN m.mode_group IN ({CAR_MODE_LIST}) AND fm.expected_gpkm_g IS NOT NULL
                    THEN (m.distance_m / 1000.0) * fm.expected_gpkm_g ELSE NULL END AS emissions_g,
               CASE WHEN m.mapped_target_id IS NULL OR btrim(m.mapped_target_id) = '' THEN NULL
                    ELSE m.assignment_label END AS assignment_label,
               NULL::int AS fleet_category_id{attr_building_col}{attr_geo_col}
        FROM mapped AS m CROSS JOIN fleet_mix AS fm
    )"""

    mapped_geo_expr = mapped_geo_id_sql(leg_alias="ml")
    mapped_cols = (
        f"ml.*, {mapped_expr} AS mapped_target_id, {mapped_geo_expr} AS mapped_geo_id, "
        f"{assign} AS assignment_label, {leg_seed} AS leg_seed_u"
        if per_trip
        else f"ml.*, {mapped_expr} AS mapped_target_id, {mapped_geo_expr} AS mapped_geo_id, {assign} AS assignment_label"
    )

    island_cte = island_cte_sql(boundary_placeholder=boundary_placeholder)
    # Always comma after `island` CTE. When `fleet_cte` is empty (attribution_only),
    # `fleet_prefix` used to be empty too, which produced invalid SQL:
    #   WITH island AS (...) meeting_legs AS (...)
    fleet_after_island = fleet_cte if fleet_cte else ""
    return f"""
    WITH {island_cte},
{fleet_after_island}    meeting_legs AS (
        {leg_select}
        {legs_from}
    ),
    mapped AS (
        SELECT {mapped_cols}
        FROM meeting_legs AS ml
    ),{scored_sql}
    UPDATE {SCHEMA}.{routes} AS r
    SET{update_sets}
    FROM scored AS s WHERE r.ctid = s.r_ctid
    """


def meeting_incoming_flows_sql(
    routes_table: str,
    trips_table: str,
    person_buildings_table: str,
    trip_routes_key_join: str,
    *,
    boundary_placeholder: str = "%s",
) -> tuple[str, str]:
    routes = _pg_ident(routes_table)
    trips = _pg_ident(trips_table)
    pb = _pg_ident(person_buildings_table)
    geo = mapped_geo_id_sql(leg_alias="leg")
    reason = motif_travel_reason_sql(purpose_expr="leg.purpose")

    base = f"""
    WITH island AS (
        SELECT ST_SetSRID(ST_GeomFromText({boundary_placeholder}, 4326), 4326) AS geom
    ),
    legs AS (
        SELECT t.orig_geo_id::text AS orig_geo_id, t.dest_geo_id::text AS dest_geo_id,
               {ROUTE_EMISSIONS_G_EXPR} AS emissions_g, r.distance_m::double precision AS distance_m,
               t.orig_lat::double precision AS orig_lat, t.orig_lon::double precision AS orig_lon,
               t.dest_lat::double precision AS dest_lat, t.dest_lon::double precision AS dest_lon,
               flags.is_home_orig, flags.is_home_dest,
               ST_Contains(i.geom, ST_SetSRID(ST_Point(t.orig_lon::double precision, t.orig_lat::double precision), 4326)) AS orig_on_island,
               ST_Contains(i.geom, ST_SetSRID(ST_Point(t.dest_lon::double precision, t.dest_lat::double precision), 4326)) AS dest_on_island,
               ({is_return_home_sql()}) AS is_return_home, t.purpose,
               {reason} AS travel_reason
        FROM {SCHEMA}.{routes} AS r
        JOIN {SCHEMA}.{trips} AS t
          ON t.synthetic_person_id::text = r.synthetic_person_id::text
         AND t.orig_geo_id::int = r.orig_geo_id::int
         AND t.dest_geo_id::int = r.dest_geo_id::int
         {trip_routes_key_join}
         AND (r.hh_id IS NULL OR t.hh_id::text IS NOT DISTINCT FROM r.hh_id::text)
        LEFT JOIN {SCHEMA}.{pb} AS pb
          ON pb.synthetic_person_id::text = r.synthetic_person_id::text
         AND pb.hh_id::text IS NOT DISTINCT FROM COALESCE(r.hh_id::text, t.hh_id::text)
        {home_flags_lateral_sql(pb_alias="pb", t_alias="t")}
        CROSS JOIN island AS i
        WHERE {CAR_MODE_FILTER_ROUTES}
          AND r.route_emissions_g IS NOT NULL AND r.route_emissions_g > 0 AND r.distance_m > 0
    ),
    attributed AS (
        SELECT orig_geo_id, dest_geo_id, emissions_g, distance_m, orig_lat, orig_lon, dest_lat, dest_lon,
               travel_reason, {geo} AS mapped_geo_id
        FROM legs
    )
    """
    agg = base + """
    SELECT orig_geo_id, COUNT(*)::bigint AS trips,
           SUM(emissions_g)::double precision AS total_emissions_g,
           SUM(distance_m)::double precision / 1000.0 AS total_distance_km,
           AVG(orig_lat) AS orig_lat, AVG(orig_lon) AS orig_lon,
           AVG(dest_lat) AS dest_lat, AVG(dest_lon) AS dest_lon
    FROM attributed
    WHERE mapped_geo_id::text = %s AND orig_geo_id IS DISTINCT FROM %s
      AND (%s <= 0 OR emissions_g >= %s)
    GROUP BY orig_geo_id ORDER BY total_emissions_g DESC LIMIT %s
    """
    cnt = base + """
    SELECT COUNT(*)::bigint FROM attributed
    WHERE mapped_geo_id::text = %s AND orig_geo_id IS DISTINCT FROM %s
      AND (%s <= 0 OR emissions_g >= %s)
    """
    return agg, cnt
