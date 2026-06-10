import logging
import os
from enum import Enum

import boto3
import pandas as pd
from botocore.exceptions import NoCredentialsError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DATA_NAMES(Enum):
    SMARD = "smard"
    WEATHER = "weather"

def is_already_uploaded(data_name: DATA_NAMES, year: int, month: int, day: int) -> bool:
    """Check if a Parquet file already exists in S3 for the given date."""
    BUCKET_NAME = os.environ.get("ZEPHYRWERK_AWS_BUCKET_NAME")
    AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL") or None
    
    key = get_file_name(data_name, year, month, day)
    s3 = boto3.client('s3', endpoint_url=AWS_ENDPOINT_URL)
    
    try:
        s3.head_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except Exception:
        return False

def get_file_name(data_name: DATA_NAMES, year: int, month: int, day: int) -> str:
    """Generates a file name for the Parquet file based on the given year, month, and day. 
    The file name follows the format: "smard_{year}_{month}_{day}.parquet" and is stored 
    in a directory structure organized by year and month.
    
    param: data_name: The name of the data (e.g. "smard").
    param: year: The year of the data (e.g. 2024).
    param: month: The month of the data (e.g. 6 for June).
    param: day: The day of the data (e.g. 15).
    return: A string representing the file name and path where the Parquet file should be stored in the S3 bucket. 
            The path follows the format: "raw/smard/year={year}/month={month}/{file_name}".
    """
    file_name = f"{data_name.value}_{year}_{month:02d}_{day:02d}.parquet"
    return f"raw/{data_name.value}/year={year}/month={month:02d}/{file_name}"

def upload_to_s3(dataframe: pd.DataFrame, data_name: DATA_NAMES):
    """Uploads a pandas DataFrame to an S3 bucket as a Parquet file. 
    The file name is generated based on the timestamp of the first row in the DataFrame.
    
    param: dataframe: A pandas DataFrame containing the data to be uploaded. 
                    The DataFrame must have a "timestamp" column with timezone-aware datetime values in UTC.
    param: data_name: The name of the data (e.g. "smard"). 
                    This is used to generate the file name and path in the S3 bucket. Default is "smard".
    return: None. The function uploads the DataFrame to the specified S3 bucket and does not return any value.
    """
    BUCKET_NAME = os.environ.get("ZEPHYRWERK_AWS_BUCKET_NAME")
    if BUCKET_NAME is None:
        raise ValueError("ZEPHYRWERK_AWS_BUCKET_NAME environment variable is not set.")

    AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL") or None
    
    date = dataframe["timestamp"].iloc[0]
    year, month, day = date.year, date.month, date.day
    file_name = get_file_name(data_name, year, month, day)

    # Don't write to disk, write to an in-memory buffer with boto3 and than upload that buffer to s3
    buffer = dataframe.to_parquet(index=False)
    s3 = boto3.client('s3', endpoint_url=AWS_ENDPOINT_URL)
    bucket_name = BUCKET_NAME
    try:
        s3.put_object(Bucket=bucket_name, Key=file_name, Body=buffer)
        logger.info(f"File uploaded successfully to {file_name}")
    except NoCredentialsError:
        logger.error("AWS credentials not found. \
                     Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables.")
        raise 
    except Exception as e:
        logger.error(f"Error uploading file to S3: {e}")
        raise
