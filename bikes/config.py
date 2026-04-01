"""Shared URLs and SQLAlchemy engine factory (override DB via BIKES_DB_URL)."""
import os

from sqlalchemy import create_engine

API_URL = (
    "https://data.lime.bike/api/partners/v1/gbfs/washington_dc/"
    "free_bike_status.json?utm_source=chatgpt.com"
)
DEFAULT_DB_URL = "postgresql://etl_user:password@localhost:5432/bikes"


def get_engine():
    db_url = os.getenv("BIKES_DB_URL", DEFAULT_DB_URL)
    return create_engine(db_url)
