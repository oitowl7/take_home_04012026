"""
CLI entrypoint: orchestrates Extract → Transform → Load in a loop.

Each iteration is one "cycle": fetch Lime GBFS JSON, normalize to a DataFrame,
optionally enrich addresses, then insert only new/changed bikes into Postgres.
"""
import argparse
import logging
import time
from typing import Dict, Optional, Tuple

import requests
from config import get_engine
from extract import extract
from load import LoadError, load
from transform import transform

logger = logging.getLogger(__name__)


def run(
    interval_seconds: int,
    iterations: int,
    enrich_address: bool,
    max_rows: Optional[int],
    geocode_qps: float,
) -> None:
    # DB: SQLAlchemy engine (connection pool warms on first use).
    engine = get_engine()
    # Shared HTTP session: reuse connections to Lime API and Nominatim across cycles.
    session = requests.Session()
    # In-memory (lat, lon) → address; survives across cycles in this process only.
    geocode_cache: Dict[Tuple[float, float], Optional[str]] = {}
    geocode_min_interval_seconds = 1.0 / geocode_qps if geocode_qps > 0 else 1.0
    # Mutable float in a list so reverse_geocode can update "last request time" in place.
    last_geocode_request_at = [0.0]

    for cycle in range(1, iterations + 1):
        logger.info("Cycle %s/%s started.", cycle, iterations)
        try:
            # E — fetch raw GBFS free_bike_status JSON from Lime.
            raw = extract(session=session)
            # T — normalize rows, optional Nominatim enrichment (deduped per unique coord).
            df = transform(
                raw_data=raw,
                session=session,
                geocode_cache=geocode_cache,
                last_geocode_request_at=last_geocode_request_at,
                geocode_min_interval_seconds=geocode_min_interval_seconds,
                enrich_address=enrich_address,
                max_rows=max_rows,
            )
            # L — schema filter, diff vs latest DB row per bike_id, append only changes.
            load(df=df, engine=engine)
        except LoadError as exc:
            logger.error("Cycle %s load failed: %s", cycle, exc)
            logger.error("Stopping ETL loop after insert failure.")
            break
        except Exception as exc:
            logger.exception("Cycle %s failed: %s", cycle, exc)

        # Pause before the next poll (historical tracking / comparison across time).
        if cycle < iterations:
            logger.info("Sleeping for %s seconds.", interval_seconds)
            time.sleep(interval_seconds)

    logger.info("ETL run complete.")


def parse_args():
    parser = argparse.ArgumentParser(description="Lime bike ETL pipeline")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=10,
        help="Seconds between API polls (default: 60)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of polling cycles to run (default: 5)",
    )
    parser.add_argument(
        "--enrich-address",
        action="store_true",
        help="Reverse geocode bike coordinates to an address (bonus feature).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Process only the first N bikes per cycle (testing helper).",
    )
    parser.add_argument(
        "--geocode-qps",
        type=float,
        default=1.0,
        help="Max geocoder requests per second when --enrich-address is enabled.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    # Configure once so all modules' loggers share the same format/level.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    run(
        interval_seconds=args.interval_seconds,
        iterations=args.iterations,
        enrich_address=args.enrich_address,
        max_rows=args.max_rows,
        geocode_qps=args.geocode_qps,
    )