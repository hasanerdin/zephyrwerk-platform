import logging
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import pyarrow.dataset as ds
from psycopg2.extras import execute_values
from pyarrow.fs import S3FileSystem

from db.connection import get_db_connection
from ingestion.s3_uploader import DATA_NAMES, get_file_name
from ingestion.smard_client import CONSUMPTION_TYPE, ENERGY_SOURCE, NEIGHBORING_REGION

logger = logging.getLogger(__name__)

# --- routing: signal name -> table name ---
_GENERATION_SIGNALS = {e.name for e in ENERGY_SOURCE} | {e.name for e in CONSUMPTION_TYPE}
_PRICE_SIGNALS = {NEIGHBORING_REGION.DE_LU.name}
_NEIGHBOUR_SIGNALS = {e.name for e in NEIGHBORING_REGION} - _PRICE_SIGNALS


def _get_filesystem():
    endpoint = os.environ.get("AWS_ENDPOINT_URL")

    fs_kwargs = {"region": os.environ.get("AWS_REGION", "eu-central-1")}
    if endpoint:
        # LocalStack 3.x doesn't return the AWS-style response checksums that
        # newer aws-sdk-cpp (bundled in pyarrow) validates on GET. Disable
        # validation for local dev only — real AWS keeps it on by default.
        os.environ.setdefault("AWS_RESPONSE_CHECKSUM_VALIDATION", "WHEN_REQUIRED")
        os.environ.setdefault("AWS_REQUEST_CHECKSUM_CALCULATION", "WHEN_REQUIRED")

        # strip scheme — pyarrow expects "host:port"
        fs_kwargs["access_key"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
        fs_kwargs["secret_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
        fs_kwargs["endpoint_override"] = endpoint.removeprefix("http://").removeprefix("https://")
        fs_kwargs["scheme"] = "http" if endpoint.startswith("http://") else "https"

    return S3FileSystem(**fs_kwargs)


def _get_dataframe(fs, data_name: DATA_NAMES, date: datetime) -> pd.DataFrame | None:
    """Read one day's Parquet file from S3.

    Returns None when the file simply isn't there yet, which is an expected
    state (the day hasn't been ingested). A file that exists but cannot be
    read is a real failure and is raised to the caller.
    """
    bucket = os.environ["ZEPHYRWERK_AWS_BUCKET_NAME"]

    file_name = get_file_name(data_name, date.year, date.month, date.day)
    source = f"{bucket}/{file_name}"

    try:
        dataset = ds.dataset(source, filesystem=fs, format="parquet")
    except Exception as e:
        logger.info(f"{data_name} file not found on S3: {file_name} ({e})")
        return None

    # A file that exists but fails to parse is corruption, not absence.
    table = dataset.to_table()
    df = table.to_pandas()

    if df is None or df.empty:
        logger.info(f"No {data_name} rows for {date.date()}")
        return None

    # ensure we only keep rows matching the requested day
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df[df["timestamp"].dt.date == date.date()]

    if df.empty:
        logger.info(f"No {data_name} rows for {date.date()} after filtering by time")
        return None

    return df


def _insert_rows(conn, table_name: str, cols: list[str], conflict_cols: list[str], df: pd.DataFrame) -> None:
    """Upsert one dataframe into one raw table. Raises on failure."""
    rows = list(df[cols].itertuples(index=False, name=None))

    insert_sql = (
        f"INSERT INTO raw.{table_name} ({', '.join(cols)}) VALUES %s "
        f"ON CONFLICT ({', '.join(conflict_cols)}) "
        f"DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit"
    )

    with conn.cursor() as cur:
        try:
            execute_values(cur, insert_sql, rows)
            conn.commit()
            logger.info(f"Inserted {len(rows)} rows into raw.{table_name}")
        except Exception:
            conn.rollback()
            raise


def _load_smard_day(conn, fs, date: datetime) -> None:
    df = _get_dataframe(fs, DATA_NAMES.SMARD, date)
    if df is None:
        return

    load_dfs = {
        "smard_generation": df[df["signal"].isin(_GENERATION_SIGNALS)],
        "smard_prices": df[df["signal"].isin(_PRICE_SIGNALS)],
        "smard_neighbour_prices": df[df["signal"].isin(_NEIGHBOUR_SIGNALS)],
    }

    cols = ["timestamp", "signal", "value", "unit"]
    conflict_cols = ["timestamp", "signal"]

    failures = []
    for table_name, table_df in load_dfs.items():
        if table_df.empty:
            continue
        try:
            _insert_rows(conn, table_name, cols, conflict_cols, table_df)
        except Exception:
            # Log every table before failing, so one run surfaces all problems.
            logger.exception(f"Failed to insert into raw.{table_name} for {date.date()}")
            failures.append(table_name)

    if failures:
        raise RuntimeError(f"SMARD load failed for {date.date()}: {failures}")


def _load_weather_day(conn, fs, date: datetime) -> None:
    df = _get_dataframe(fs, DATA_NAMES.WEATHER, date)
    if df is None:
        return

    _insert_rows(
        conn,
        "weather",
        ["timestamp", "region", "signal_type", "value", "unit"],
        ["timestamp", "region", "signal_type"],
        df,
    )


def _load_weather_forecast_day(conn, fs, date: datetime) -> None:
    df = _get_dataframe(fs, DATA_NAMES.WEATHER_FORECAST, date)
    if df is None:
        return

    _insert_rows(
        conn,
        "weather_forecast",
        ["timestamp", "region", "signal_type", "value", "unit", "fetched_at"],
        ["timestamp", "region", "signal_type", "fetched_at"],
        df,
    )


def load_from_s3_to_db(date: datetime) -> None:
    """Load one day of every dataset. Raises if any dataset fails."""
    fs = _get_filesystem()
    conn = get_db_connection()

    loaders = {
        "smard": _load_smard_day,
        "weather": _load_weather_day,
        "weather_forecast": _load_weather_forecast_day,
    }

    failures = []
    try:
        for name, loader in loaders.items():
            try:
                loader(conn, fs, date)
            except Exception:
                logger.exception(f"{name} load failed for {date.date()}")
                failures.append(name)
    finally:
        conn.close()

    if failures:
        raise RuntimeError(f"Load failed for {date.date()}: {failures}")

    logger.info(f"Load completed for date: {date.strftime('%Y-%m-%d')}")


def load_range(start_date: datetime, end_date: datetime) -> None:
    """Load every day in the range. Days are independent: a failing day does not
    stop the others, but the run as a whole fails so the container exits non-zero."""
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    failed_days = []
    current_day = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    while current_day <= end_date:
        try:
            load_from_s3_to_db(current_day)
        except Exception:
            logger.exception(f"Day failed: {current_day.date()}")
            failed_days.append(current_day.date())
        current_day += timedelta(days=1)

    if failed_days:
        raise RuntimeError(f"Load failed for {len(failed_days)} day(s): {failed_days}")