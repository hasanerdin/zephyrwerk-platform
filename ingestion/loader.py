import logging
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import psycopg2
import pyarrow.dataset as ds
from psycopg2.extras import execute_values
from pyarrow.fs import S3FileSystem

from db.settings import Settings, get_settings
from ingestion.s3_uploader import DATA_NAMES, get_file_name
from ingestion.smard_client import CONSUMPTION_TYPE, ENERGY_SOURCE, NEIGHBORING_REGION

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- routing: signal name -> table name ---
_GENERATION_SIGNALS = {e.name for e in ENERGY_SOURCE} | {e.name for e in CONSUMPTION_TYPE}
_PRICE_SIGNALS = {NEIGHBORING_REGION.DE_LU.name}
_NEIGHBOUR_SIGNALS = {e.name for e in NEIGHBORING_REGION} - _PRICE_SIGNALS

def _get_db_connection():
    settings: Settings = get_settings()

    if not all([settings.ZEPHYRWERK_RDS_HOST, 
                settings.ZEPHYRWERK_RDS_USER, 
                settings.ZEPHYRWERK_RDS_PASSWORD, 
                settings.ZEPHYRWERK_RDS_DB]):
        raise RuntimeError(
            "Missing one or more required ZEPHYRWERK_RDS_* environment variables"
        )

    return psycopg2.connect(
        host=settings.ZEPHYRWERK_RDS_HOST,
        port=settings.ZEPHYRWERK_RDS_PORT,
        user=settings.ZEPHYRWERK_RDS_USER,
        password=settings.ZEPHYRWERK_RDS_PASSWORD,
        dbname=settings.ZEPHYRWERK_RDS_DB,
    )

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

def _get_dataframe(fs, data_name: DATA_NAMES, date:datetime) -> pd.DataFrame:
    bucket = os.environ["ZEPHYRWERK_AWS_BUCKET_NAME"]
    
    year = date.year
    month = date.month
    day = date.day
    file_name = get_file_name(data_name, year, month, day)

    source = f"{bucket}/{file_name}"

    # try to open parquet dataset for just that file
    try:
        dataset = ds.dataset(source, filesystem=fs, format="parquet")
    except Exception as e:
        logger.info(f"{data_name} file not found on S3: {file_name} ({e})")
        return

    try:
        table = dataset.to_table()
        df = table.to_pandas()
    except Exception as e:
        logger.error(f"Failed to read {data_name} parquet {file_name}: {e}")
        return
    
    if df is None or df.empty:
        logger.info(f"No {data_name} rows for {date.date()}")
        return
    
    # ensure we only keep rows matching the requested day if a datetime-like column exists
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df[df["timestamp"].dt.date == date.date()]

    if df.empty:
        logger.info(f"No {data_name} rows for {date.date()} after filtering by time")
        return
    
    return df

def _load_smard_day(conn, fs, date: datetime) -> None:
    df = _get_dataframe(fs, DATA_NAMES.SMARD, date)
    if df is None or df.empty:
        return
    
    gen_df = df[df["signal"].isin(_GENERATION_SIGNALS)]
    price_df = df[df["signal"].isin(_PRICE_SIGNALS)]
    neighbour_df = df[df["signal"].isin(_NEIGHBOUR_SIGNALS)]

    load_dfs = {
        "smard_generation": gen_df,
        "smard_prices": price_df,
        "smard_neighbour_prices": neighbour_df
    }

    for table_name, table_df in load_dfs.items():
        if table_df.empty:
            continue

        cols = ["timestamp", "signal", "value", "unit"]
        rows = list(table_df[["timestamp", "signal", "value", "unit"]].itertuples(index=False, name=None))

        insert_sql = (
            f"INSERT INTO raw.{table_name} ({', '.join(cols)}) VALUES %s \
                ON CONFLICT (timestamp, signal) \
                DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit"
        )

        with conn.cursor() as cur:
            try:
                execute_values(cur, insert_sql, rows)
                conn.commit()
                logger.info(f"Inserted {len(rows)} SMARD rows for {date.date()}")
            except Exception:
                conn.rollback()
                logger.exception(f"Failed to insert SMARD rows for {date.date()}")

def _load_weather_day(conn, fs, date: datetime) -> None:
    df = _get_dataframe(fs, DATA_NAMES.WEATHER, date)
    if df is None or df.empty:
        return
    
    cols = ["timestamp", "region", "signal_type", "value", "unit"]
    rows = list(df[["timestamp", "region", "signal_type", "value", "unit"]].itertuples(index=False, name=None))

    insert_sql = (
        f"INSERT INTO raw.weather ({', '.join(cols)}) VALUES %s \
            ON CONFLICT (timestamp, region, signal_type) \
            DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit"
    )

    with conn.cursor() as cur:
        try:
            execute_values(cur, insert_sql, rows)
            conn.commit()
            logger.info(f"Inserted {len(rows)} WEATHER rows for {date.date()}")
        except Exception:
            conn.rollback()
            logger.exception(f"Failed to insert WEATHER rows for {date.date()}")

def _load_weather_forecast_day(conn, fs, date: datetime) -> None:
    df = _get_dataframe(fs, DATA_NAMES.WEATHER_FORECAST, date)
    if df is None or df.empty:
        return
    
    cols = ["timestamp", "region", "signal_type", "value", "unit", "fetched_at"]
    rows = list(
        df[["timestamp", "region", "signal_type", "value", "unit", "fetched_at"]].itertuples(index=False, name=None)
        )
    
    insert_sql = (
        f"INSERT INTO raw.weather_forecast ({','.join(cols)}) VALUES %s\
            ON CONFLICT (timestamp, region, signal_type, fetched_at) \
            DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit"
    )

    with conn.cursor() as cur:
        try:
            execute_values(cur, insert_sql, rows)
            conn.commit()
            logger.info(f"Inserted {len(rows)} WEATHER FORECAST rows for {date.date()}.")
        except Exception:
            conn.rollback()
            logger.exception(f"Failed to insert WEATHER rows for {date.date()}")

def load_from_s3_to_db(date: datetime) -> None:
    fs = _get_filesystem()
    conn = _get_db_connection()

    try:
        _load_smard_day(conn, fs, date)
        _load_weather_day(conn, fs, date)
        _load_weather_forecast_day(conn, fs, date)
        logger.info(f"Pipeline completed for date: {date.strftime('%Y-%m-%d')}")
    finally:
        conn.close()


def load_range(start_date: datetime, end_date: datetime) -> None:
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    current_day = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    while current_day <= end_date:
        load_from_s3_to_db(current_day)
        current_day += timedelta(days=1)
    

if __name__ == "__main__":
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    load_range(datetime(2019, 1, 1), end)
    print('End date used:', end.date())
    