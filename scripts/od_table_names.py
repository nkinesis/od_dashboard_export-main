"""OD table naming helpers (lightweight; safe for portable dashboard bundles)."""

from __future__ import annotations

DEFAULT_ROUTES = "od10_actual_od_ct_routes"
DEFAULT_TRIPS = "od10_actual_od_ct_trips"


def apply_run_tag(table_base: str, tag: str) -> str:
    """``zone_emissions_rules`` + tag ``od10`` -> ``zone_emissions_rules_od10``."""
    base = str(table_base).strip()
    t = str(tag).strip()
    if not t:
        return base
    if base.endswith(f"_{t}"):
        return base
    return f"{base}_{t}"
