from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from ingestion.weather_client import (
    BASE_FORECAST_URL,
    BASE_HISTORICAL_URL,
    Region,
    SignalType,
    _fetch_single_region_weather,
    fetch_weather,
)


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(response=mock)
    else:
        mock.raise_for_status.return_value = None
    return mock


def _make_api_response(times: list[str]) -> dict:
    """Build a minimal but complete Open-Meteo API response for the given timestamps."""
    n = len(times)
    return {
        "hourly": {
            "time": times,
            "wind_speed_100m": [5.0] * n,
            "wind_direction_100m": [180.0] * n,
            "shortwave_radiation": [0.0] * n,
            "cloud_cover": [20.0] * n,
            "temperature_2m": [10.0] * n,
        },
        "hourly_units": {
            "wind_speed_100m": "km/h",
            "wind_direction_100m": "°",
            "shortwave_radiation": "W/m²",
            "cloud_cover": "%",
            "temperature_2m": "°C",
        },
    }


START = datetime(2024, 1, 10, tzinfo=timezone.utc)
END = datetime(2024, 1, 11, tzinfo=timezone.utc)
TIMES = ["2024-01-10T00:00", "2024-01-10T01:00"]
API_RESPONSE = _make_api_response(TIMES)


# ── _fetch_single_region_weather ──────────────────────────────────────────────

class TestFetchSingleRegionWeather:
    def test_returns_expected_columns(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(API_RESPONSE)
            df = _fetch_single_region_weather(Region.BRANDENBURG, START, END, BASE_HISTORICAL_URL)
        assert list(df.columns) == ["timestamp", "region", "signal_type", "value", "unit"]

    def test_row_count_is_timestamps_times_signal_types(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(API_RESPONSE)
            df = _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_FORECAST_URL)
        assert len(df) == len(TIMES) * len(SignalType)

    def test_region_column_matches_enum_value(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(API_RESPONSE)
            df = _fetch_single_region_weather(Region.SCHLESWIG, START, END, BASE_HISTORICAL_URL)
        assert (df["region"] == Region.SCHLESWIG.value).all()

    def test_signal_types_match_enum_values(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(API_RESPONSE)
            df = _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        expected_signals = {s.value for s in SignalType}
        assert set(df["signal_type"].unique()) == expected_signals

    def test_timestamps_are_utc_aware(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(API_RESPONSE)
            df = _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        assert str(df["timestamp"].dt.tz) == "UTC"

    def test_units_mapped_from_api_response(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(API_RESPONSE)
            df = _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        wind_speed_rows = df[df["signal_type"] == SignalType.WIND_SPEED.value]
        assert (wind_speed_rows["unit"] == "km/h").all()

    def test_correct_url_is_used(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(API_RESPONSE)
            _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        called_url = mock_get.call_args.args[0]
        assert called_url == BASE_HISTORICAL_URL

    def test_correct_coordinates_for_region(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(API_RESPONSE)
            _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        params = mock_get.call_args.kwargs.get("params", {})
        assert params["latitude"] == 48.13
        assert params["longitude"] == 11.58

    def test_date_range_sent_as_strings(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(API_RESPONSE)
            _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        params = mock_get.call_args.kwargs.get("params", {})
        assert params["start_date"] == "2024-01-10"
        assert params["end_date"] == "2024-01-11"

    def test_all_signal_types_requested(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(API_RESPONSE)
            _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        params = mock_get.call_args.kwargs.get("params", {})
        requested_signals = set(params["hourly"].split(","))
        expected_signals = {s.value for s in SignalType}
        assert requested_signals == expected_signals

    def test_returns_empty_dataframe_on_http_error(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({}, status_code=500)
            df = _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_returns_empty_dataframe_on_connection_error(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("timeout")
            df = _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        assert df.empty


# ── fetch_weather ─────────────────────────────────────────────────────────────

def _single_region_df(region: Region) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.to_datetime(TIMES, utc=True),
        "region": region.value,
        "signal_type": SignalType.WIND_SPEED.value,
        "value": [5.0, 6.0],
        "unit": "km/h",
    })


@pytest.fixture
def mock_fetch_single():
    with patch("ingestion.weather_client._fetch_single_region_weather") as mock:
        mock.side_effect = lambda region, *args, **kwargs: _single_region_df(region)
        yield mock


class TestFetchWeather:
    def test_returns_data_for_all_regions(self, mock_fetch_single):
        start = datetime.now(timezone.utc) - timedelta(days=10)
        end = datetime.now(timezone.utc) - timedelta(days=8)
        df = fetch_weather(start, end)
        assert set(df["region"].unique()) == {r.value for r in Region}

    def test_historical_url_used_when_entirely_in_past(self, mock_fetch_single):
        start = datetime.now(timezone.utc) - timedelta(days=10)
        end = datetime.now(timezone.utc) - timedelta(days=8)
        fetch_weather(start, end)
        for call in mock_fetch_single.call_args_list:
            assert call.args[3] == BASE_HISTORICAL_URL

    def test_forecast_url_used_when_entirely_in_future(self, mock_fetch_single):
        start = datetime.now(timezone.utc) + timedelta(days=1)
        end = datetime.now(timezone.utc) + timedelta(days=3)
        fetch_weather(start, end)
        for call in mock_fetch_single.call_args_list:
            assert call.args[3] == BASE_FORECAST_URL

    def test_split_fetch_when_range_spans_cutoff(self, mock_fetch_single):
        start = datetime.now(timezone.utc) - timedelta(days=10)
        end = datetime.now(timezone.utc) + timedelta(days=2)
        fetch_weather(start, end)
        urls_used = {call.args[3] for call in mock_fetch_single.call_args_list}
        assert BASE_HISTORICAL_URL in urls_used
        assert BASE_FORECAST_URL in urls_used

    def test_call_count_for_split_range(self, mock_fetch_single):
        start = datetime.now(timezone.utc) - timedelta(days=10)
        end = datetime.now(timezone.utc) + timedelta(days=2)
        fetch_weather(start, end)
        # Each of the 4 regions gets 2 calls (historical + forecast)
        assert mock_fetch_single.call_count == len(list(Region)) * 2

    def test_call_count_for_pure_historical(self, mock_fetch_single):
        start = datetime.now(timezone.utc) - timedelta(days=10)
        end = datetime.now(timezone.utc) - timedelta(days=8)
        fetch_weather(start, end)
        assert mock_fetch_single.call_count == len(list(Region))

    def test_returns_empty_dataframe_when_all_regions_fail(self):
        with patch("ingestion.weather_client._fetch_single_region_weather") as mock:
            mock.return_value = pd.DataFrame()
            start = datetime.now(timezone.utc) - timedelta(days=10)
            end = datetime.now(timezone.utc) - timedelta(days=8)
            df = fetch_weather(start, end)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_partial_failure_still_returns_successful_regions(self):
        regions = list(Region)

        def side_effect(region, *args, **kwargs):
            if region == regions[0]:
                return pd.DataFrame()  # first region fails
            return _single_region_df(region)

        with patch("ingestion.weather_client._fetch_single_region_weather", side_effect=side_effect):
            start = datetime.now(timezone.utc) - timedelta(days=10)
            end = datetime.now(timezone.utc) - timedelta(days=8)
            df = fetch_weather(start, end)

        returned_regions = set(df["region"].unique())
        assert regions[0].value not in returned_regions
        assert len(returned_regions) == len(regions) - 1

    def test_result_contains_expected_columns(self, mock_fetch_single):
        start = datetime.now(timezone.utc) - timedelta(days=10)
        end = datetime.now(timezone.utc) - timedelta(days=8)
        df = fetch_weather(start, end)
        assert set(df.columns) >= {"timestamp", "region", "signal_type", "value", "unit"}
