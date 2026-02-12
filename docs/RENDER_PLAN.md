# Render Deployment Plan (Future)

> Saved for when budget is approved. The local Flask app can be promoted to Render
> by adding the files described below.

## Overview

Deploy the Ecosystem Research dashboard + pipeline as a Render Web Service:
- Single Python process (gunicorn with threads for pipeline background execution)
- Persistent disk for CSV data (survives redeploys)
- No external database needed

## Architecture

```
Render Web Service
    gunicorn wsgi:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT
    |
    ├── /              — Dashboard (charts)
    ├── /table         — Project table (filters)
    ├── /pipeline      — Upload + Run + Progress UI
    ├── /api/*         — Pipeline API endpoints
    └── Background thread runs 9-step pipeline
```

Workers = 1 (required: pipeline state is in-memory, not shared).
Threads = 4 (Flask serves poll requests while pipeline thread runs).

## Files to Create

### `render.yaml` (Infrastructure-as-Code)

```yaml
services:
  - type: web
    name: ecosystem-research
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn wsgi:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT
    envVars:
      - key: FLASK_ENV
        value: production
      - key: DATA_DIR
        value: /data
    disk:
      name: research-data
      mountPath: /data
      sizeGB: 1
    plan: starter  # $7/mo, 512MB RAM, 0.5 CPU
```

### `wsgi.py` (Gunicorn entry point)

```python
from dashboard import create_app
app = create_app()
```

### `requirements.txt`

```
flask>=3.0
gunicorn>=21.2
requests>=2.31
```

## Code Changes Needed

### `lib/csv_utils.py` — DATA_DIR support

The `resolve_data_path()` function needs to respect a `DATA_DIR` environment variable
for Render's persistent disk:

```python
def resolve_data_path(chain: str, filename: Optional[str] = None) -> Path:
    base_dir = os.environ.get("DATA_DIR")
    if base_dir:
        base = Path(base_dir) / chain.lower()
    else:
        base = Path(__file__).parent.parent / "data" / chain.lower()
    if filename:
        return base / filename
    return base
```

Similarly update `find_main_csv()` to use `resolve_data_path()`.

## Persistent Disk

Render provides a persistent disk mounted at `/data`. Structure:
```
/data/
  near/
    near_ecosystem_research.csv
    pipeline.log
  aptos/
    aptos_ecosystem_research.csv
```

The disk persists across redeploys but NOT across service deletion.
Back up important CSVs before deleting the service.

## Cost

- **Starter plan**: $7/month (512 MB RAM, 0.5 CPU)
- **Persistent disk**: $0.25/GB/month (1 GB = $0.25/month)
- **Total**: ~$7.25/month

## Deployment Steps

1. Create `render.yaml`, `wsgi.py`, `requirements.txt` as described above
2. Add DATA_DIR support to `lib/csv_utils.py`
3. Push to GitHub
4. Connect repo to Render dashboard
5. Render auto-deploys from `render.yaml`
6. Upload CSVs via the web UI (persistent disk starts empty)

## Limitations

- Single worker = one pipeline at a time (by design)
- 512 MB RAM may be tight for website scanning (many HTTP requests)
- Render's free tier has sleep behavior; starter plan stays awake
- No auth — anyone with the URL can access (add Flask-Login if needed)
