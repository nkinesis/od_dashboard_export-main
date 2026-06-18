# OD dashboard export

Portable folder for the PM23 survey dashboard (`run_dashboard.py`).

## Layout

- `dashboard/` — static HTML / JS / CSS (SPA + zone / buildings / flows views)
- `scripts/` — Flask API server and dependencies
- `data/db/` — PostgreSQL dump (`od_dashboard_tables.dump`)
- `data/` — island boundary GeoJSON + `popgen_inputs/` zone label CSVs

## Target machine setup

1. Install **Python 3.10+**, **PostgreSQL 14+** with **PostGIS**.
2. Create database `Synthetic2023` (or your own name) and schema `popgen`.
3. Restore the dump::

     python scripts/bundle_od_dashboard.py unpack --bundle-dir .

4. Install Python deps::

     pip install -r requirements.txt

5. Start the server (from this folder)::

     python scripts/run_dashboard.py --db-host localhost --db-port 5433 \
       --db-name Synthetic2023 --db-user postgres --db-password YOUR_PASSWORD

6. Open **http://127.0.0.1:5051/**

## Notes

- The dump contains **precomputed aggregates only** (no `person_key` / `d_id`).
- Zone labels come from `data/popgen_inputs/zones.csv` and `geo_zone_sp23.csv`.
- Island map filter uses `data/mtl_boundary_file.geojson`.
