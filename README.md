# OD dashboard export

Portable **PM23 survey** dashboard — CMM island-eligible car trips, zone maps, buildings, and flows.

| Resource | Link |
|----------|------|
| **Full install guide (HTML)** | Open [`README.html`](README.html) in your browser |
| **GitHub** | [github.com/atiyasehar/od_dashboard_export-main](https://github.com/atiyasehar/od_dashboard_export-main) |
| **DB dump** | [OneDrive — od_dashboard_tables.dump](https://liveconcordia-my.sharepoint.com/:u:/g/personal/atiya_atiya_concordia_ca/IQDAgc05pD40SK9YSnDwFZURAcydIl6xbQHGRnafPX5VfIE?e=j6PxkO) — copy to `data/db/` |

## Quick start

```powershell
# 1. Download od_dashboard_tables.dump from OneDrive (link in README.html)
#    — or use Data/db/od_dashboard_tables.zip from the PopGen2023 repo
# 2. Copy into project
mkdir data\db
copy %USERPROFILE%\Downloads\od_dashboard_tables.dump data\db\

# 2. Python deps
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Restore DB — see "Database restore" below (pgAdmin or script)
# 4. Run
python scripts/run_dashboard.py --bundle-root . --db-name od_dashboard
```

Open **http://127.0.0.1:5051/** · Health: **http://127.0.0.1:5051/api/health**

## Database restore

Target database: **`od_dashboard`** · Schema: **`public`** · 8 precomputed tables.

### Option A — pgAdmin (Windows)

**Step 1 — Create database**

pgAdmin → **Databases** → right-click → **Create** → **Database…** → name: **`od_dashboard`**

**Step 2 — Prepare schema and PostGIS**

Query Tool on **`od_dashboard`**, run:

```sql
DROP SCHEMA IF EXISTS public CASCADE;

CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;
```

**Step 3 — Restore dump**

Right-click **`od_dashboard`** → **Restore…**

- **General:** Format = `Custom or tar`, Filename = `data\db\od_dashboard_tables.dump`
- **Data Options** tab:

| Section | Option | Setting |
|---------|--------|---------|
| Sections | Pre-data, Post-data, Data | **On** |
| Type of objects | Only data, Only schema | Off |
| Do not save | **Owner**, **Privileges** | **On** |
| Do not save | Tablespaces, Comments, Publications, Subscriptions, Security labels, Table access methods | Off |

Click **Restore**.

**Step 4 — Verify**

```sql
SELECT table_schema, table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name LIKE '%od10%' OR table_name IN
('popgen_zones_geom','buildings_footprint','trips_route_emissions')
ORDER BY table_name;
```

See also **`PopGen2023/Data/db/README.md`** for the same steps (dump zip in repo).

### Option B — Python script

```powershell
python scripts/bundle_od_dashboard.py unpack --bundle-dir . `
  --host localhost --port 5433 --user postgres --password YOUR_PASSWORD `
  --dbname od_dashboard
```

## Layout

- `dashboard/` — SPA + map views (HTML / JS / CSS)
- `scripts/run_dashboard.py` — Flask API server
- `data/db/` — PostgreSQL dump location
- `data/` — island boundary GeoJSON
- `docs/screenshots/` — README figures

See **README.html** for architecture diagrams, UI tour, API list, and troubleshooting flowchart.
