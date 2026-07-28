"""
This is the orchestration entry point. It runs the data pipeline in one of three modes:
daily (fetch yesterday's SMARD/weather data plus the weekly weather forecast, then load
into S3 and run dbt), weekly (retrain the ML models), or historical (backfill SMARD/weather
data for a date range, load into S3, run dbt, and train the ML models).
"""

import argparse
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from enum import Enum

from dotenv import load_dotenv

from ingestion.loader import load_range
from ingestion.s3_uploader import DATA_NAMES, is_already_uploaded, upload_to_s3
from ingestion.smard_client import fetch_range
from ingestion.weather_client import fetch_forecast_weather, fetch_historical_weather
from ml.data_access import load_ml_features
from ml.train_generation_model import start_generation_model_training
from ml.train_price_model import start_price_model_training

load_dotenv()  # Load environment variables from .env file

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),                    # still prints to terminal
        logging.FileHandler("pipeline.log"),        # also writes to file
    ]
)

class Mode(Enum):
    Daily = "daily"
    Weekly = "weekly"
    Hist = "historical"

def parser():
    arg_parser = argparse.ArgumentParser(
        description="Run the data pipeline to fetch SMARD and weather data and upload to S3."
        )
    arg_parser.add_argument("--mode",
                            type=str,
                            choices=["daily", "weekly", "historical"],
                            default="daily",
                            help="Mode of the pipeline run. " \
                            "Daily collects yesterday data and today's forecast " \
                            "Weekly trains the ml models " \
                            "Historical collects data between given start and end date and train the ml models")
    arg_parser.add_argument("--start_date",
                            type=str,
                            help="The start date in YYYY-MM-DD format. Required for historical mode."
                        )
    arg_parser.add_argument("--end_date",
                            type=str,
                            help="The end date in YYYY-MM-DD format. Required for historical mode."
                        )
    return arg_parser.parse_args()

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
    for range_start, range_end in _missing_day_ranges(DATA_NAMES.SMARD, start_date, end_date):
        range_end_ts = range_end.replace(hour=23, minute=59, second=59)
        try:
            smard_data = fetch_range(start_date=range_start, end_date=range_end_ts)
            if smard_data.empty:
                logger.warning(f"No SMARD data returned for {range_start.date()} to {range_end.date()}")
                continue

            logger.info(
                f"SMARD Data fetch operation is successfull with {len(smard_data)} rows "
                f"({range_start.date()} to {range_end.date()})."
            )
            for _, day_df in smard_data.groupby(smard_data["timestamp"].dt.date):
                upload_to_s3(day_df, DATA_NAMES.SMARD)
            logger.info(f"SMARD data is uploaded to S3 ({range_start.date()} to {range_end.date()}).")
        except Exception as e:
            logger.error(f"SMARD data for {range_start.date()} to {range_end.date()} cannot be fetched: {e}")

def run_weather_range(start_date: datetime, end_date: datetime) -> None:
    for range_start, range_end in _missing_day_ranges(DATA_NAMES.WEATHER, start_date, end_date):
        range_end_ts = range_end.replace(hour=23, minute=59, second=59)
        try:
            weather_hist_data = fetch_historical_weather(range_start, range_end_ts)
            if weather_hist_data.empty:
                logger.warning(f"No weather data returned for {range_start.date()} to {range_end.date()}")
                continue

            logger.info(
                f"Weather Data fetch operation is successfull with {len(weather_hist_data)} rows "
                f"({range_start.date()} to {range_end.date()})."
            )
            for _, day_df in weather_hist_data.groupby(weather_hist_data["timestamp"].dt.date):
                upload_to_s3(day_df, DATA_NAMES.WEATHER)
            logger.info(f"Weather data is uploaded to S3 ({range_start.date()} to {range_end.date()}).")
        except Exception as e:
            logger.error(f"Weather data for {range_start.date()} to {range_end.date()} cannot be fetched: {e}")

def run_weather_forecast(start_date: datetime, end_date:datetime):
    weather_forecast_data = fetch_forecast_weather(start_date, end_date)
    logger.info(f"Weather forecast fetch operation is successfull with {len(weather_forecast_data)} rows.")

    upload_to_s3(weather_forecast_data, DATA_NAMES.WEATHER_FORECAST)
    logger.info("Weather forecast data is uploaded to S3.")

def run_dbt(command: str) -> None:
    logger.info(f"Starting: dbt {command}")
    try:
        result = subprocess.run(
            ["dbt", command, "--project-dir", "dbt", "--profiles-dir", "dbt"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"dbt {command} failed:\n{e.stdout}\n{e.stderr}")
        raise
    logger.info(f"Completed: dbt {command}")

# Run once at the beginning
def run_historical_pipeline(start_date: datetime, end_date: datetime):
    # Fetch each of SMARD/weather once for the whole range (batched by contiguous
    # missing-day stretches internally), rather than once per calendar day.
    yesterday = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(minutes=1)
    end_date = min(end_date, yesterday)

    try:
        run_smard_range(start_date, end_date)
    except Exception as e:
        logger.error(f"SMARD data for {start_date.date()} to {end_date.date()} cannot be fetched: {e}")

    try:
        run_weather_range(start_date, end_date)
    except Exception as e:
        logger.error(f"Weather data for {start_date.date()} to {end_date.date()} cannot be fetched: {e}")

    logger.info(f"Historical fetch completed for {start_date.date()} to {end_date.date()}")
    
    # Load raw data from S3 into PostgreSQL
    load_range(start_date, end_date)

    run_dbt("run")  # Run dbt models to transform raw data into features
    run_dbt("test")  # Run dbt tests to validate the transformed data

    run_model_training()

# Run Weekly
def run_model_training():
    # Train generation models for wind and solar
    raw = load_ml_features()
    try:
        start_generation_model_training(raw)
    except Exception as e:
        logger.error(f"Error is occured while training geenration model: {str(e)}")
    
    try:
        start_price_model_training(raw)
    except Exception as e:
        logger.error(f"Error is occured while training price model: {str(e)}")

# Run Daily
def fetch_yesterday_data():
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        run_smard_range(start_date, start_date)
    except Exception as e:
        logger.error(f"SMARD data for {yesterday.strftime('%Y-%m-%d')} cannot fetched: {e}")

    try:
        run_weather_range(start_date, start_date)
    except Exception as e:
        logger.error(f"Weather data for {yesterday.strftime('%Y-%m-%d')} cannot fetched: {e}")

    logger.info(f"Yesterday's data fetch completed (date: {yesterday.strftime('%Y-%m-%d')})")

def fetch_weekly_weather_forecast():
    current_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = current_day + timedelta(days=7)

    while current_day <= end_date:
        day_end = current_day.replace(hour=23, minute=59, second=59)
        try:
            run_weather_forecast(current_day, day_end)
            logger.info(f"Weather forecast data for {current_day.strftime('%Y-%m-%d')} is fetched successfully.")

            
        except Exception as e:
            logger.error(f"Weather forecast data for {current_day.strftime('%Y-%m-%d')} cannot fetched: {e}")

        current_day += timedelta(days=1)

def run_daily_pipeline():
    fetch_yesterday_data()
    fetch_weekly_weather_forecast()

    # Load raw data from S3 into PostgreSQL
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    week_later = today + timedelta(days=7)
    load_range(yesterday, week_later)

    run_dbt("run")  # Run dbt models to transform raw data into features
    run_dbt("test")  # Run dbt tests to validate the transformed data

def get_dates(args):
    if args.start_date is None:
        raise ValueError("Start date cannot be empty.")
    
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    if end_date <= start_date:
        raise ValueError("End date cannot be smaller then start date.")
    
    return start_date, end_date

if __name__ == "__main__":
    args = parser()
    
    if args.mode == Mode.Hist.value:
        start_date, end_date = get_dates(args)
        run_historical_pipeline(start_date=start_date, end_date=end_date)
    elif args.mode == Mode.Weekly.value:
        run_model_training()
    else:
        run_daily_pipeline()
    