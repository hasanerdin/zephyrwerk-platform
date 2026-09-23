"""Ingestion tasks: fetch upstream data for a date range and write it to S3.

Each task raises on failure so that the container exits with a non-zero status,
which is how ECS and Step Functions detect a failed run. Logging configuration
belongs to the entry point (__main__.py), not to this module.
"""

import logging
from datetime import datetime, timedelta

from ingestion.s3_uploader import DATA_NAMES, is_already_uploaded, upload_to_s3
from ingestion.smard_client import fetch_range
from ingestion.weather_client import fetch_forecast_weather, fetch_historical_weather

logger = logging.getLogger(__name__)


def _missing_day_ranges(data_name: DATA_NAMES, start_date: datetime, end_date: datetime) -> list:
    """Collapse the calendar days in [start_date.date(), end_date.date()] that are not
    yet uploaded into contiguous (day_start, day_end) ranges, so each stretch can be
    fetched from the upstream API with a single call instead of one call per day."""
    missing_days = []
    current_day = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    last_day = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
    while current_day <= last_day:
        if not is_already_uploaded(data_name, current_day.year, current_day.month, current_day.day):
            missing_days.append(current_day)
        current_day += timedelta(days=1)

    ranges = []
    for day in missing_days:
        if ranges and day == ranges[-1][1] + timedelta(days=1):
            ranges[-1] = (ranges[-1][0], day)
        else:
            ranges.append((day, day))
    return ranges


def run_smard_range(start_date: datetime, end_date: datetime) -> None:
    """Fetch SMARD data for every not-yet-uploaded day in the range and write one
    Parquet file per day to S3."""
    failures = []
    for range_start, range_end in _missing_day_ranges(DATA_NAMES.SMARD, start_date, end_date):
        range_end_ts = range_end.replace(hour=23, minute=59, second=59)
        try:
            smard_data = fetch_range(start_date=range_start, end_date=range_end_ts)
            if smard_data.empty:
                logger.warning(f"No SMARD data returned for {range_start.date()} to {range_end.date()}")
                continue

            logger.info(
                f"SMARD fetch succeeded with {len(smard_data)} rows "
                f"({range_start.date()} to {range_end.date()})."
            )
            for _, day_df in smard_data.groupby(smard_data["timestamp"].dt.date):
                upload_to_s3(day_df, DATA_NAMES.SMARD)
            logger.info(f"SMARD data uploaded to S3 ({range_start.date()} to {range_end.date()}).")
        except Exception as e:
            logger.error(f"SMARD data for {range_start.date()} to {range_end.date()} failed: {e}")
            failures.append((range_start.date(), range_end.date()))

    if failures:
        raise RuntimeError(f"SMARD ingestion failed for {len(failures)} range(s): {failures}")


def run_weather_range(start_date: datetime, end_date: datetime) -> None:
    """Fetch historical weather data for every not-yet-uploaded day in the range and
    write one Parquet file per day to S3."""
    failures = []
    for range_start, range_end in _missing_day_ranges(DATA_NAMES.WEATHER, start_date, end_date):
        range_end_ts = range_end.replace(hour=23, minute=59, second=59)
        try:
            weather_hist_data = fetch_historical_weather(range_start, range_end_ts)
            if weather_hist_data.empty:
                logger.warning(f"No weather data returned for {range_start.date()} to {range_end.date()}")
                continue

            logger.info(
                f"Weather fetch succeeded with {len(weather_hist_data)} rows "
                f"({range_start.date()} to {range_end.date()})."
            )
            for _, day_df in weather_hist_data.groupby(weather_hist_data["timestamp"].dt.date):
                upload_to_s3(day_df, DATA_NAMES.WEATHER)
            logger.info(f"Weather data uploaded to S3 ({range_start.date()} to {range_end.date()}).")
        except Exception as e:
            logger.error(f"Weather data for {range_start.date()} to {range_end.date()} failed: {e}")
            failures.append((range_start.date(), range_end.date()))

    if failures:
        raise RuntimeError(f"Weather ingestion failed for {len(failures)} range(s): {failures}")


def run_weather_forecast(start_date: datetime, end_date: datetime) -> None:
    """Fetch the weather forecast for the range and write one Parquet file per day.

    The range is split by day before upload because upload_to_s3 derives the S3 key
    from the first row's timestamp: passing a multi-day frame in one call would put
    every day into a single day's file.
    """
    end_date_ts = end_date.replace(hour=23, minute=59, second=59)
    forecast_data = fetch_forecast_weather(start_date, end_date_ts)

    if forecast_data.empty:
        raise RuntimeError(f"No forecast data returned for {start_date.date()} to {end_date.date()}")

    logger.info(
        f"Forecast fetch succeeded with {len(forecast_data)} rows "
        f"({start_date.date()} to {end_date.date()})."
    )

    for day, day_df in forecast_data.groupby(forecast_data["timestamp"].dt.date):
        upload_to_s3(day_df, DATA_NAMES.WEATHER_FORECAST)
        logger.info(f"Forecast data uploaded to S3 for {day}.")