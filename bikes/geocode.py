"""
Nominatim reverse geocoding: (lat, lon) → display_name (street-level address string).

Rate-limited (~1 req/s public policy); 429 handled with Retry-After / backoff.
"""
import logging
import time
from typing import Optional, Tuple

import requests

GEOCODER_URL = "https://nominatim.openstreetmap.org/reverse"
logger = logging.getLogger(__name__)


def throttle_geocoder(last_request_at: list[float], min_interval_seconds: float) -> None:
    if min_interval_seconds <= 0:
        return
    now = time.monotonic()
    elapsed = now - last_request_at[0]
    sleep_for = min_interval_seconds - elapsed
    if sleep_for > 0:
        time.sleep(sleep_for)


def reverse_geocode(
    session: requests.Session,
    lat: Optional[float],
    lon: Optional[float],
    geocode_cache: dict[Tuple[float, float], Optional[str]],
    last_geocode_request_at: list[float],
    min_interval_seconds: float,
    enabled: bool,
    timeout_seconds: int = 10,
    max_retries: int = 3,
) -> Optional[str]:
    if not enabled or lat is None or lon is None:
        return None

    # ~11m precision; ties nearby points to one cache entry.
    key = (round(float(lat), 5), round(float(lon), 5))
    if key in geocode_cache:
        return geocode_cache[key]

    params = {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18}
    headers = {"User-Agent": "bike-etl/1.0 (local project script)"}

    address = None
    for attempt in range(1, max_retries + 1):
        try:
            throttle_geocoder(last_geocode_request_at, min_interval_seconds)
            response = session.get(
                GEOCODER_URL, params=params, headers=headers, timeout=timeout_seconds
            )
            last_geocode_request_at[0] = time.monotonic()

            if response.status_code == 429:
                retry_after_header = response.headers.get("Retry-After", "")
                try:
                    retry_after = float(retry_after_header)
                except (TypeError, ValueError):
                    retry_after = min_interval_seconds * (2**attempt)

                logger.warning(
                    "429 rate limited; sleeping %.1fs before retry %s/%s.",
                    retry_after,
                    attempt,
                    max_retries,
                )
                time.sleep(retry_after)
                continue

            response.raise_for_status()
            payload = response.json()
            address = payload.get("display_name")
            break
        except requests.exceptions.RequestException as exc:
            if attempt == max_retries:
                logger.error(
                    "Failed after %s attempts for (%s, %s): %s",
                    max_retries,
                    lat,
                    lon,
                    exc,
                )
            else:
                backoff = min_interval_seconds * (2**attempt)
                time.sleep(backoff)

    geocode_cache[key] = address
    return address
