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
# 2. Copy into project
mkdir data\db
copy %USERPROFILE%\Downloads\od_dashboard_tables.dump data\db\

# 2. Python deps
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Restore DB (create od_dashboard in pgAdmin first)
python scripts/bundle_od_dashboard.py unpack --bundle-dir . --dbname od_dashboard

# 4. Run
python scripts/run_dashboard.py --bundle-root . --db-name od_dashboard
```

Open **http://127.0.0.1:5051/** · Health: **http://127.0.0.1:5051/api/health**

## Layout

- `dashboard/` — SPA + map views (HTML / JS / CSS)
- `scripts/run_dashboard.py` — Flask API server
- `data/db/` — PostgreSQL dump location
- `data/` — island boundary GeoJSON
- `docs/screenshots/` — README figures

See **README.html** for architecture diagrams, UI tour, API list, and troubleshooting flowchart.
