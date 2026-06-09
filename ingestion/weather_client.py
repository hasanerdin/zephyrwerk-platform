"""
Open-Meteo API client for fetching weather data.

This module provides utilities to retrieve current weather, forecasts, and historical weather data for specified locations using the Open-Meteo API.
It supports multiple endpoints and returns data as pandas DataFrames for easy analysis and integration with other data sources. 
The client handles API requests, response parsing, and error handling to ensure reliable data retrieval for various weather-related applications.
"""

import logging
import requests
import pandas as pd
from enum import Enum
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

BASE_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
BASE_HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"

class SignalType(Enum):
    WIND_SPEED = "wind_speed_100m"
    WIND_DIRECTION = "wind_direction_100m"
    SHORTWAVE_RADIATION = "shortwave_radiation"
    CLOUD_COVER = "cloud_cover"
    TEMPERATURE = "temperature_2m"

class Region(Enum):
    BRANDENBURG = "wind_region_brandenburg"
    SCHLESWIG = "wind_region_schleswig"
    BAVARIA = "solar_region_bavaria"
    BADEN_WURTTEMBERG = "solar_region_bawue"


REGION_COORDINATES = {
    Region.BRANDENBURG: {"latitude": 52.41, "longitude": 12.53},
    Region.SCHLESWIG: {"latitude": 54.51, "longitude": 9.55},
    Region.BAVARIA: {"latitude": 48.13, "longitude": 11.58},
    Region.BADEN_WURTTEMBERG: {"latitude": 48.77, "longitude": 9.18}
}

def _fetch_single_region_weather(region: Region, start_date: datetime, end_date: datetime, url: str) -> pd.DataFrame:
    """
    Fetch weather data for a single region from the Open-Meteo API.

    Args:
        region (Region): The region for which to fetch weather data.
        start_date (datetime): The start date and time for the data retrieval.
        end_date (datetime): The end date and time for the data retrieval.
        url (str): The API endpoint URL to use for the request.
    Returns:
        pd.DataFrame: A DataFrame containing the requested weather data for the specified region with timestamps as the index.
    """
    coordinates = REGION_COORDINATES[region]
    
    params = {
        "latitude": coordinates["latitude"],
        "longitude": coordinates["longitude"],
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "hourly": ",".join([signal_type.value for signal_type in SignalType]),
        "timezone": "UTC",
        "utc_offset_seconds": 0
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()

        data = response.json()

        # Convert the data to a DataFrame as (timestap, region, signal_type, value, unit)
        df = pd.DataFrame(data["hourly"])
        df["timestamp"] = pd.to_datetime(df["time"], utc=True)
        df = df.drop(columns=["time"])
        df = df.melt(id_vars=["timestamp"], var_name="signal_type", value_name="value")
        df["region"] = region.value 
        df["unit"] = df["signal_type"].map(data["hourly_units"])
        return df[["timestamp", "region", "signal_type", "value", "unit"]]
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching weather data for {region.value}: {e}")
        return pd.DataFrame()

def fetch_weather(start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """
    Fetch weather data from the Open-Meteo API for the specified parameters.

    Args:
        start_date (datetime): The start date and time for the data retrieval.
        end_date (datetime): The end date and time for the data retrieval.
    Returns:
        pd.DataFrame: A DataFrame containing the requested weather data with timestamps as the index.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=5)

    results = []
    for region in Region:
        if end_date < cutoff:
            df = _fetch_single_region_weather(region, start_date, end_date, BASE_HISTORICAL_URL)
        elif start_date >= cutoff:
            df = _fetch_single_region_weather(region, start_date, end_date, BASE_FORECAST_URL)
        else:
            # If the date range spans both historical and forecast data, we need to fetch separately for each part
            historical_end = cutoff - timedelta(seconds=1)  # End just before the cutoff
            forecast_start = cutoff  # Start at the cutoff

            historical_df = _fetch_single_region_weather(region, start_date, historical_end, BASE_HISTORICAL_URL)
            forecast_df = _fetch_single_region_weather(region, forecast_start, end_date, BASE_FORECAST_URL)
            df = pd.concat([historical_df, forecast_df])

        if not df.empty:
            results.append(df)
        
    return pd.concat(results) if results else pd.DataFrame()            

if __name__ == "__main__":
    start = datetime.now(timezone.utc) - timedelta(days=10)
    end = datetime.now(timezone.utc)
    df = fetch_weather(start, end)
    print(df.head(10))
    print(f"Total rows: {len(df)}")
    print(f"Regions: {df['region'].unique()}")
    print(f"Signals: {df['signal_type'].unique()}")
    print(df["timestamp"].min())
    print(df["timestamp"].max())
    print(df["value"].isna().sum())