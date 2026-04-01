"""
T — Turn raw GBFS JSON into a flat DataFrame aligned with bike_status columns.

Optional: reverse-geocode unique (lat, lon) pairs once, then map addresses onto every row.
"""
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

import pandas as pd
import requests

from geocode import reverse_geocode


def to_bool(value: Any) -> Optional[bool]:
    """API may send 0/1 or strings; Postgres expects real booleans."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y"}:
            return True
        if normalized in {"0", "false", "f", "no", "n"}:
            return False
    return None


def transform(
    raw_data: dict,
    session: requests.Session,
    geocode_cache: dict[Tuple[float, float], Optional[str]],
    last_geocode_request_at: list[float],
    geocode_min_interval_seconds: float,
    enrich_address: bool,
    max_rows: Optional[int],
) -> pd.DataFrame:
    # GBFS: top-level last_updated (epoch) + data.bikes list.
    bikes = raw_data.get("data", {}).get("bikes", [])
    if max_rows is not None:
        bikes = bikes[:max_rows]
    fetched_at = datetime.now(timezone.utc)
    feed_last_updated = raw_data.get("last_updated")

    # One dict per bike; booleans normalized for Postgres BOOLEAN columns.
    records = []
    for bike in bikes:
        lat = bike.get("lat")
        lon = bike.get("lon")
        records.append(
            {
                "bike_id": bike.get("bike_id"),
                "lat": lat,
                "lon": lon,
                "is_reserved": to_bool(bike.get("is_reserved")),
                "snapshot_timestamp": fetched_at,
                "street_address": None,
                "geocoded_at": None,
                "geocode_provider": None,
                "feed_last_updated": feed_last_updated,
                "vehicle_type_id": bike.get("vehicle_type_id"),
                "is_disabled": to_bool(bike.get("is_disabled")),
            }
        )

    df = pd.DataFrame(records)
    if enrich_address and not df.empty:
        # Dedupe coordinates so we call Nominatim once per unique (lat, lon), not per bike.
        unique_coords = {
            (lat, lon)
            for lat, lon in zip(df["lat"], df["lon"])
            if lat is not None and lon is not None
        }
        coord_to_address: dict[Tuple[float, float], Optional[str]] = {}
        for lat, lon in unique_coords:
            coord_to_address[(lat, lon)] = reverse_geocode(
                session=session,
                lat=lat,
                lon=lon,
                geocode_cache=geocode_cache,
                last_geocode_request_at=last_geocode_request_at,
                min_interval_seconds=geocode_min_interval_seconds,
                enabled=True,
            )

        # Broadcast the resolved address to every row sharing that coordinate.
        coord_keys = list(zip(df["lat"], df["lon"]))
        df["street_address"] = [
            coord_to_address.get((lat, lon)) if lat is not None and lon is not None else None
            for lat, lon in coord_keys
        ]
        has_address = df["street_address"].notna()
        df.loc[has_address, "geocoded_at"] = fetched_at
        df.loc[has_address, "geocode_provider"] = "nominatim"

    return df
