"""
Shared PostgreSQL identifiers for the PopGen pipeline.

Buildings are loaded from the CMM-wide footprint GeoJSON into
popgen.buildings_footprint (see load_buildings_footprint.py).
The old name buildings_odb is no longer used.
"""

SCHEMA = "popgen"
BUILDINGS_TABLE = "buildings_footprint"

# mode_group values treated as private auto for building routes / emissions / trip CSV filters.
# niv2.2b path: d_mode_gr → often "1" / "1.0". pm23_ctcsd path: mode_group = d_mode → "10" driver, "11" passenger.
CAR_MODE_GROUP_TEXTS: tuple[str, ...] = ("1", "1.0", "10", "11", "10.0", "11.0")
