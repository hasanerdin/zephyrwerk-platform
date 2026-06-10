"""
This is the orchestration entry point. It wires the three modules together to fetch SMARD data, 
fetch weather data, and upload both to S3 for a given date range.
The main function is `run_pipeline`, which takes a start date and end date as input, 
fetches the relevant data, and uploads it to S3.

It needs to support two modes of operation:
1. A "full backfill" mode, where the user can specify a start date and end date in the past, 
and the pipeline will fetch all relevant data for that date range and upload it to S3.
2. A "daily update" mode, where the user can specify a start date of yesterday and an end date of today, 
and the pipeline will fetch only the data for the last 24 hours and upload it to S3.

Incremental: fetches yesterday's data only.
"""

import argparse
import logging
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from ingestion.s3_uploader import DATA_NAMES, is_already_uploaded, upload_to_s3
from ingestion.smard_client import fetch_range
from ingestion.weather_client import fetch_weather

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

def parser():
    arg_parser = argparse.ArgumentParser(
        description="Run the data pipeline to fetch SMARD and weather data and upload to S3."
        )
    arg_parser.add_argument("--start_date", 
                            type=str, 
                            help="The start date in YYYY-MM-DD format. Required for full_backfill."
                        )
    arg_parser.add_argument("--end_date", 
                            type=str, 
                            help="The end date in YYYY-MM-DD format. Required for full_backfill."
                        )
    return arg_parser.parse_args()


def _run_smard_single_day(start_date: datetime, end_date: datetime):
    smard_exists = is_already_uploaded(DATA_NAMES.SMARD, start_date.year, start_date.month, start_date.day)
    if smard_exists:
        logger.info(f"Skipping {start_date.date()} smard data — already uploaded")
        return
    
    # Fetch SMARD data for the given date
    smard_data = fetch_range(start_date=start_date, end_date=end_date)
    logger.info(f"SMARD Data fetch operation is successfull with {len(smard_data)} rows.")

    # Upload combined data to S3
    upload_to_s3(smard_data, DATA_NAMES.SMARD)
    logger.info("SMARD data is upload to S3.")

def _run_weather_single_day(start_date: datetime, end_date: datetime):
    weather_exists = is_already_uploaded(DATA_NAMES.WEATHER, start_date.year, start_date.month, start_date.day)
    if weather_exists:
        logger.info(f"Skipping {start_date.date()} weather data — already uploaded")
        return

    # Fetch weather data for the given date
    weather_data = fetch_weather(start_date, end_date)
    logger.info(f"Weather Data fetch operation is successfull with {len(weather_data)} rows.")

    upload_to_s3(weather_data, DATA_NAMES.WEATHER)
    logger.info("Weather data is upload to S3.")

def run_pipeline(start_date: datetime, end_date: datetime):
    # For each day you fetch all 23 SMARD signals, combine into one long DataFrame, 
    # fetch weather, combine everything, then upload to S3.
    current_day = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    while current_day <= end_date:
        day_end = current_day.replace(hour=23, minute=59, second=59)

        try:
            _run_smard_single_day(current_day, day_end)
            _run_weather_single_day(current_day, day_end)
            logger.info(f"Pipeline completed for date: {current_day.strftime('%Y-%m-%d')}")
        except Exception as e:
            logger.error(f"Data for {current_day.strftime('%Y-%m-%d')} cannot fetched: {e}")
        current_day += timedelta(days=1)

if __name__ == "__main__":
    args = parser()
    
    if args.start_date and args.end_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    elif args.start_date or args.end_date:
        raise ValueError("Provide both --start_date and --end_date or neither.")
    else:
        start_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        end_date = datetime.now(timezone.utc)
    
    run_pipeline(start_date=start_date, end_date=end_date)