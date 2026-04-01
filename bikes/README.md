# Lime Bikes ETL (Local Setup)

This project pulls Lime bike status data for Washington, DC, transforms it, and writes it to PostgreSQL.

It supports:
- repeated polling (`--iterations`, `--interval-seconds`)
- change-only inserts (new or changed bikes only)
- optional address enrichment via Nominatim (`--enrich-address`)
- test-mode row limiting (`--max-rows`)

## 1) Prerequisites

- Python 3.10+ (3.12 tested)
- PostgreSQL running locally
- Access to a PostgreSQL superuser (or a user that can create roles/databases)

## 2) Create and activate a virtual environment

From the `bikes` folder:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3) Create PostgreSQL role + database (from scratch)

If nothing exists yet, run this in DBeaver SQL editor (connected as postgres/admin) or in `psql`:

```sql
-- Create application role
CREATE ROLE etl_user WITH LOGIN PASSWORD 'password';

-- Create database and assign ownership
CREATE DATABASE bikes OWNER etl_user;

-- Optional but explicit privileges
GRANT ALL PRIVILEGES ON DATABASE bikes TO etl_user;
```

Then connect to the `bikes` database and run:

```sql
CREATE TABLE IF NOT EXISTS public.bike_status (
    id BIGSERIAL PRIMARY KEY,
    bike_id TEXT NOT NULL,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    is_reserved BOOLEAN,
    snapshot_timestamp TIMESTAMPTZ NOT NULL,
    street_address TEXT,
    geocoded_at TIMESTAMPTZ,
    geocode_provider TEXT,
    feed_last_updated BIGINT,
    vehicle_type_id TEXT,
    is_disabled BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_bike_status_snapshot_timestamp
    ON public.bike_status (snapshot_timestamp);

CREATE INDEX IF NOT EXISTS idx_bike_status_bike_id_snapshot
    ON public.bike_status (bike_id, snapshot_timestamp DESC);
```

## 4) Configure database connection

By default, the app uses:

`postgresql://etl_user:password@localhost:5432/bikes`

Override it with an environment variable if needed:

```bash
export BIKES_DB_URL="postgresql://<user>:<password>@<host>:<port>/<database>"
```

## 5) Run the ETL

### Basic run (no enrichment)

```bash
python main.py --iterations 5 --interval-seconds 10
```

### Fast test run (only first N rows)

```bash
python main.py --iterations 1 --max-rows 50
```

### With address enrichment

```bash
python main.py --enrich-address --iterations 1 --max-rows 50 --geocode-qps 1.0
```

## 6) CLI options

- `--iterations` number of polling cycles (default: `5`)
- `--interval-seconds` wait time between cycles (default: `10`)
- `--enrich-address` enable reverse geocoding
- `--max-rows` process only first N bikes per cycle (testing helper)
- `--geocode-qps` maximum geocoder request rate (requests per second, default: `1.0`)
  - `1.0` = about 1 request every 1 second
  - `0.5` = about 1 request every 2 seconds
  - `0.2` = about 1 request every 5 seconds
  - lower values are safer when you get `429 Too Many Requests`

## 7) Notes on geocoding / 429 responses

Public Nominatim is rate-limited. This project already:
- deduplicates coordinates per cycle
- caches geocode results in-memory
- rate-limits geocoder calls
- retries on 429 using `Retry-After` when present

If you still hit `429 Too Many Requests`:
- reduce `--geocode-qps` (for example `0.5` or `0.2`)
- lower `--max-rows` during testing
- consider a paid/batch provider or self-hosted Nominatim for heavy loads

Recommendation for this freeware test setup:
- do not run geolocation enrichment on the full dataset
- use a small cap like `--max-rows 10` with `--enrich-address` to avoid rate limiting
- example: `python main.py --enrich-address --max-rows 10 --geocode-qps 0.5 --iterations 1`

## 8) Project layout

- `main.py` orchestration + CLI
- `extract.py` API extraction
- `transform.py` transformation + optional enrichment mapping
- `geocode.py` geocoding, throttling, retries
- `load.py` load + change detection + insert error handling
- `config.py` config and SQLAlchemy engine
