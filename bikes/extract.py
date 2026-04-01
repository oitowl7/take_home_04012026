"""E — HTTP GET the Lime Washington DC GBFS free_bike_status feed (JSON)."""
import logging
from typing import Any, Dict

import requests

from config import API_URL

logger = logging.getLogger(__name__)


def extract(session: requests.Session, timeout_seconds: int = 20) -> Dict[str, Any]:
    """Download one snapshot; structure is data.bikes[] with bike_id, lat, lon, etc."""
    try:
        response = session.get(API_URL, timeout=timeout_seconds)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to fetch bike status: %s", exc)
        raise
