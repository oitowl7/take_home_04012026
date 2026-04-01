"""
L — Insert into bike_status only columns that exist in the DB, and only rows that changed.

Compares each incoming row to the latest stored row for the same bike_id (by snapshot_timestamp).
"""
import logging

import pandas as pd
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class LoadError(Exception):
    """Raised when loading rows into bike_status fails."""


def load(df: pd.DataFrame, engine) -> None:
    if df.empty:
        logger.info("No bike rows in this snapshot.")
        return
    try:
        # Match DataFrame columns to actual table so ALTER TABLE additions don't break inserts.
        inspector = inspect(engine)
        table_columns = {col["name"] for col in inspector.get_columns("bike_status")}

        insert_df = df.copy()
        selected_columns = [col for col in insert_df.columns if col in table_columns]
        if not selected_columns:
            raise ValueError("No matching columns between ETL output and bike_status table.")

        insert_df = insert_df[selected_columns].copy()
        if "bike_id" not in insert_df.columns:
            raise ValueError("bike_status load requires bike_id column.")

        bike_ids = insert_df["bike_id"].dropna().unique().tolist()
        if not bike_ids:
            logger.info("No valid bike_id values in this snapshot.")
            return

        # Latest row per bike_id (Postgres DISTINCT ON + ORDER BY snapshot DESC).
        latest_query = """
            SELECT DISTINCT ON (bike_id) *
            FROM bike_status
            WHERE bike_id = ANY(%(bike_ids)s)
            ORDER BY bike_id, snapshot_timestamp DESC
        """
        latest_df = pd.read_sql(latest_query, engine, params={"bike_ids": bike_ids})
        # Fields we care about for "did this bike change since last insert?"
        compare_columns = [
            col
            for col in [
                "lat",
                "lon",
                "is_reserved",
                "street_address",
                "feed_last_updated",
                "vehicle_type_id",
                "is_disabled",
            ]
            if col in insert_df.columns and col in latest_df.columns
        ]

        if latest_df.empty:
            # First run against an empty table: treat whole snapshot as new.
            changed_df = insert_df
        else:
            latest_by_id = latest_df.set_index("bike_id")
            is_new_bike = ~insert_df["bike_id"].isin(latest_by_id.index)
            is_changed = pd.Series(False, index=insert_df.index)

            for col in compare_columns:
                old_values = insert_df["bike_id"].map(latest_by_id[col])
                new_values = insert_df[col]
                col_changed = new_values.fillna("__NULL__") != old_values.fillna("__NULL__")
                is_changed = is_changed | col_changed

            # Keep row if bike never seen, or any tracked column differs from DB.
            changed_df = insert_df[is_new_bike | is_changed]

        if changed_df.empty:
            logger.info("No changed rows detected; nothing inserted.")
            return

        changed_df.to_sql("bike_status", engine, if_exists="append", index=False)
        logger.info(
            "Inserted %s changed/new rows (from %s snapshot rows).",
            len(changed_df),
            len(insert_df),
        )
    except SQLAlchemyError as exc:
        logger.error("Database insert failed.")
        logger.error("SQLAlchemy error type: %s", type(exc).__name__)
        logger.error("SQLAlchemy message: %s", exc)

        statement = getattr(exc, "statement", None)
        params = getattr(exc, "params", None)
        original = getattr(exc, "orig", None)
        if statement:
            logger.error("Statement: %s", statement)
        if params is not None:
            logger.error("Params: %s", params)
        if original:
            logger.error("DBAPI original error: %r", original)

        logger.exception("Full traceback:")
        raise LoadError("Database insert failed.") from exc
    except Exception:
        logger.exception("Unexpected insert error. Full traceback:")
        raise LoadError("Unexpected insert failure.") from None
