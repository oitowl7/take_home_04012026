# Lime Bikes ETL (Local Setup)

This project pulls Lime bike status data for Washington, DC, transforms it, and writes it to PostgreSQL.

It supports:

- repeated polling (`--iterations`, `--interval-seconds`)
- change-only inserts (new or changed bikes only)
- optional address enrichment via Nominatim (`--enrich-address`)
- test-mode row limiting (`--max-rows`)

**Data model:** The loader **append**s new rows when a bike’s tracked fields change, so `bike_status` keeps a **history** of snapshots over time (analytics / warehouse–style). I’m aware of the alternative: for a **transactional / operational / app backend** where you only need **current** state per bike, you would typically **`UPDATE` or `UPSERT`** one row per `bike_id` instead of inserting new history rows. This project chooses the historical pattern on purpose.

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

If nothing exists yet, run the SQL below in **any** PostgreSQL client you prefer: `psql`, DBeaver, pgAdmin, VS Code/Cursor SQL extensions, IntelliJ, etc. Connect as a user that can create roles and databases (often `postgres`).

```sql
-- Create application role
CREATE ROLE etl_user WITH LOGIN PASSWORD 'password';

-- Create database and assign ownership
CREATE DATABASE bikes OWNER etl_user;

-- Optional but explicit privileges
GRANT ALL PRIVILEGES ON DATABASE bikes TO etl_user;
```

Then connect to the `bikes` database (same tools as above) and run:

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

**Scale:** The Lime feed returns **well over 7,000** bike records per snapshot. If you reverse-geocode **one coordinate per second** (a reasonable public Nominatim pace), processing **7,000** distinct lookups takes about **7,000 seconds** — roughly **2 hours**. In practice this codebase deduplicates identical `(lat, lon)` pairs (often ~6k unique pairs instead of ~7k rows), but you are still looking at **hours** of wall-clock time if you run enrichment across the full feed at ~1 req/s.

Public Nominatim is rate-limited. This project already:

- deduplicates coordinates per cycle
- caches geocode results in-memory
- rate-limits geocoder calls
- retries on 429 using `Retry-After` when present

If you still hit `429 Too Many Requests`:

- reduce `--geocode-qps` (for example `0.5` or `0.2`)
- lower `--max-rows` during testing

Recommendation for this freeware test setup:

- do not run geolocation enrichment on the full dataset
- use a small cap like `--max-rows 10` with `--enrich-address` to avoid rate limiting
- example: `python main.py --enrich-address --max-rows 10 --iterations 1`

## 8) Project layout

- `main.py` orchestration + CLI
- `extract.py` API extraction
- `transform.py` transformation + optional enrichment mapping
- `geocode.py` geocoding, throttling, retries
- `load.py` load + change detection + insert error handling
- `config.py` config and SQLAlchemy engine

