"""
SMARD client for fetching time series data from the SMARD API.

This module provides utilities to retrieve power generation, consumption,
and price signals for German and neighboring regions using the SMARD
chart_data endpoints. It supports multiple resolutions and returns data
as pandas DataFrames.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Union

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.smard.de/app/chart_data"
MAX_TIME_OUT = 30 # s
 
class RESOLUTION(Enum):
    HOUR = "hour"
    QUARTER_HOUR = "quarter-hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"

class ENERGY_SOURCE(Enum):
    WIND_ONSHORE = 4067
    WIND_OFFSHORE = 1225
    SOLAR = 4068
    BIOMASS = 4066
    HYDROPOWER = 1226
    PUMPED_STORAGE = 4070
    NATURAL_GAS = 4071
    HARD_COAL = 4069
    BROWN_COAL = 1223
    NUCLEAR = 1224
    OTHER_CONVENTIONAL = 1227
    OTHER_RENEWABLE = 1228

class NEIGHBORING_REGION(Enum):
    DE_LU = 4169
    AUSTRIA = 4170
    FRANCE = 254
    NETHERLANDS = 256
    POLAND = 258 # was 257 — filter 257 has gap 2017-2019, 258 is continuous
    SWITZERLAND = 259
    CZECHIA = 261
    DENMARK_1 = 252
    DENMARK_2 = 253

class CONSUMPTION_TYPE(Enum):
    TOTAL_CONSUMPTION = 410
    RESIDUAL_LOAD = 4359

class REGION(Enum):
    DE = "DE"
    DE_LU = "DE-LU"

class Units(Enum):
    MW = "MW"
    EUR_MWH = "EUR_MWH"

SMARD_SIGNALS = {
    # Generation (region: DE, unit: MW)
    ENERGY_SOURCE.WIND_ONSHORE:             {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.WIND_OFFSHORE:            {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.SOLAR:                    {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.BIOMASS:                  {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.HYDROPOWER:               {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.PUMPED_STORAGE:           {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.NATURAL_GAS:              {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.HARD_COAL:                {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.BROWN_COAL:               {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.NUCLEAR:                  {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.OTHER_CONVENTIONAL:       {"region": REGION.DE, "unit": Units.MW},
    ENERGY_SOURCE.OTHER_RENEWABLE:          {"region": REGION.DE, "unit": Units.MW},
    # Consumption (region: DE, unit: MW)
    CONSUMPTION_TYPE.TOTAL_CONSUMPTION :    {"region": REGION.DE, "unit": Units.MW},
    CONSUMPTION_TYPE.RESIDUAL_LOAD :        {"region": REGION.DE, "unit": Units.MW},
    # DE and Neighbour prices (region: DE-LU, unit: EUR_MWH)
    NEIGHBORING_REGION.DE_LU:               {"region": REGION.DE_LU, "unit": Units.EUR_MWH},
    NEIGHBORING_REGION.AUSTRIA:             {"region": REGION.DE_LU, "unit": Units.EUR_MWH},
    NEIGHBORING_REGION.FRANCE:              {"region": REGION.DE_LU, "unit": Units.EUR_MWH},
    NEIGHBORING_REGION.NETHERLANDS:         {"region": REGION.DE_LU, "unit": Units.EUR_MWH},
    NEIGHBORING_REGION.POLAND:              {"region": REGION.DE_LU, "unit": Units.EUR_MWH},
    NEIGHBORING_REGION.SWITZERLAND:         {"region": REGION.DE_LU, "unit": Units.EUR_MWH},
    NEIGHBORING_REGION.CZECHIA:             {"region": REGION.DE_LU, "unit": Units.EUR_MWH},
    NEIGHBORING_REGION.DENMARK_1:           {"region": REGION.DE_LU, "unit": Units.EUR_MWH},
    NEIGHBORING_REGION.DENMARK_2:           {"region": REGION.DE_LU, "unit": Units.EUR_MWH},
}


def _get_index(filter_id: Union[ENERGY_SOURCE, CONSUMPTION_TYPE, NEIGHBORING_REGION], 
               region: REGION, 
               resolution: RESOLUTION) -> list:
    """" Fetches the index of available timestamps for a given filter_id, region, and resolution.
        
    param: filter_id: The SMARD filter ID corresponding to the signal we want to fetch 
                    (e.g. 4067 for onshore wind generation).
    param: region: The region for which to fetch the data (e.g. REGION.DE).
    param: resolution: The desired data resolution (e.g. Resolution.HOUR).
    return: a list of timestamps (in milliseconds) that mark the start of each weekly chunk of data available 
    for the specified filter_id and region.
    """
    url = f"{BASE_URL}/{filter_id.value}/{region.value}/index_{resolution.value}.json"
    response = requests.get(url, timeout=MAX_TIME_OUT)
    response.raise_for_status()
    return response.json().get("timestamps", [])

def _get_series(filter_id: Union[ENERGY_SOURCE, CONSUMPTION_TYPE, NEIGHBORING_REGION], 
                region: REGION, 
                resolution: RESOLUTION, 
                timestamp: int) -> list:
    """ Fetches the time series data for a given filter_id, region, resolution, and timestamp.
    
    param: filter_id: The SMARD filter ID corresponding to the signal we want to fetch 
                    (e.g. 4067 for onshore wind generation).
    param: region: The region for which to fetch the data (e.g. REGION.DE).
    param: resolution: The desired data resolution (e.g. Resolution.HOUR).
    param: timestamp: The timestamp (in milliseconds) that marks the start of the weekly chunk of data to fetch. 
                      This timestamp should be one of the values returned by the _get_index function 
                      for the specified filter_id, region, and resolution.
    return: a list of [timestamp_ms, value] pairs representing the time series data 
            for the specified filter_id, region, resolution, and timestamp. 
            Each pair consists of a timestamp in milliseconds and the corresponding value for that timestamp.
    """
    file_name = f"{filter_id.value}_{region.value}_{resolution.value}_{timestamp}.json"
    url = f"{BASE_URL}/{filter_id.value}/{region.value}/{file_name}"
    logger.debug("Fetching data from URL: %s", url)
    response = requests.get(url, timeout=MAX_TIME_OUT)
    response.raise_for_status()
    return response.json().get("series", [])

def _get_series_with_retry(filter_id: Union[ENERGY_SOURCE, CONSUMPTION_TYPE, NEIGHBORING_REGION], 
                region: REGION, 
                resolution: RESOLUTION, 
                timestamp: int,
                max_retries=3) -> list:
    for attempt in range(max_retries):
        try:
            return _get_series(filter_id, region, resolution, timestamp)
        except requests.HTTPError as e:
            if e.response.status_code == 429: # rate limited
                wait = 2 ** attempt * 5 # 5s, 10s, 20s
                logger.warning(f"Rate limited. Waiting {wait}s before retry {attempt + 1}")
                time.sleep(wait)
            elif e.response.status_code >= 500:  # server error — retry
                wait = 2 ** attempt
                logger.warning(f"Server error {e.response.status_code}. Retrying in {wait}s")
                time.sleep(wait)
            else:
                raise  # 4xx client errors — don't retry, raise immediately
        raise Exception(f"Max retries exceeded for timestamp {timestamp}")

def _fetch_range_single_signal(signal_name: Union[ENERGY_SOURCE, CONSUMPTION_TYPE, NEIGHBORING_REGION], 
                start_date: datetime, 
                end_date: datetime, 
                region: REGION = REGION.DE,
                unit: Units = Units.MW,
                resolution: RESOLUTION = RESOLUTION.HOUR
                ) -> pd.DataFrame:
    """ Fetches time series data for a given signal, date range, and resolution from the SMARD API.
    param: signal_name: The name of the signal to fetch. This can be an instance of 
            ENERGY_SOURCE, CONSUMPTION_TYPE, or NEIGHBORING_REGION.
    param: start_date: The start date of the desired date range (inclusive).
    param: end_date: The end date of the desired date range (inclusive).
    param: resolution: The desired data resolution (e.g. Resolution.HOUR). Default is Resolution.HOUR.
    return: A pandas DataFrame containing the time series data for the specified signal, date range, and resolution. 
            The DataFrame has columns "timestamp" (as a timezone-aware datetime in UTC), 
                                        "value" (as a numeric value), 
                                        "signal" (the name of the signal), and 
                                        "unit" (the unit of the values).
    """
    
    filter_id = signal_name if isinstance(signal_name, Enum) else None
    if filter_id is None:
        raise ValueError(f"Unsupported signal name: {signal_name}. Must be an instance of \
                         ENERGY_SOURCE, CONSUMPTION_TYPE, or NEIGHBORING_REGION.")

    # Get the index for the specified filter_id, region, and resolution
    valid_timestamps = _get_index(filter_id, region, resolution)
    if not valid_timestamps:
        raise ValueError(f"No timestamps found in index for signal '{signal_name}' with \
                         filter_id {filter_id} and region {region.value}.")
    
    # Filter the index to get the relevant timestamps for the specified date range.
    # Each ts marks the start of a weekly chunk, so we must include the chunk whose
    # start is before start_date but whose data covers start_date (last ts <= start_timestamp).
    start_timestamp = int(start_date.timestamp() * 1000)  # Convert to milliseconds
    end_timestamp = int(end_date.timestamp() * 1000)      # Convert to milliseconds
    before_start = [ts for ts in valid_timestamps if ts <= start_timestamp]
    first_ts = before_start[-1] if before_start else valid_timestamps[0]
    relevant_timestamps = [ts for ts in valid_timestamps if first_ts <= ts <= end_timestamp]

    # Fetch the series data for each relevant timestamp and aggregate into a DataFrame
    data_frames = []
    for ts in relevant_timestamps:
        series = _get_series_with_retry(filter_id, region, resolution, ts)
        if not series:
            continue  # Skip if no data is returned for this timestamp

        df = pd.DataFrame(series, columns=["timestamp_ms", "value"])
        df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit='ms', utc=True)
        df["value"] = pd.to_numeric(df["value"], errors='coerce')
        df.drop(columns=["timestamp_ms"], inplace=True)
        
        # order columns as desired and keep only timestamp and value for now, we'll add signal and unit later
        df = df[["timestamp", "value"]]
        
        data_frames.append(df)
    
    if not data_frames:
        return pd.DataFrame(columns=["timestamp", "value", "signal", "unit"])

    df = pd.concat(data_frames, ignore_index=True)
    df["signal"] = signal_name.name
    df["unit"] = unit.value

    # Filter the final DataFrame to ensure it only contains data within the specified date range
    start_mask = df["timestamp"] >= pd.Timestamp(start_date).tz_convert("UTC")
    end_mask = df["timestamp"] <= pd.Timestamp(end_date).tz_convert("UTC")
    filtered_df = df[start_mask & end_mask]

    return filtered_df

def fetch_range(start_date: datetime, end_date: datetime):
    """ Fetches time series data for all the 23 smard signals inside the time range from the SMARD API.
    param: start_date: The start date of the desired date range (inclusive).
    param: end_date: The end date of the desired date range (inclusive).

    return: A pandas DataFrame containing the time series data for the signals, date range. 
            The DataFrame has columns "timestamp" (as a timezone-aware datetime in UTC), 
                                        "value" (as a numeric value), 
                                        "signal" (the name of the signal), 
                                        "unit" (the unit of the values).
    """

    data_frames = []
    for signal, signal_config in SMARD_SIGNALS.items():
        try:
            region = signal_config["region"]
            unit = signal_config["unit"]
            df = _fetch_range_single_signal(signal, start_date, end_date, region, unit, RESOLUTION.HOUR)
            data_frames.append(df)
        except Exception as e:
            logger.error(f"Failed to fetch signal {signal}: {e}")

    if not data_frames:
        return pd.DataFrame(columns=["timestamp", "value", "signal", "unit"])

    df = pd.concat(data_frames, ignore_index=True)
    return df.sort_values("timestamp").reset_index(drop=True)

if __name__ == "__main__":
    start_date = datetime.now(timezone.utc) - timedelta(days=7)
    end_date = datetime.now(timezone.utc)
    
    df = fetch_range(start_date, end_date)
    print(df.head())
    print(len(df))
    print(df["value"].isna().sum())