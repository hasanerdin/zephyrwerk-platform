from datetime import datetime, timezone
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
    _fetch_single_region_weather_with_retry,
    fetch_forecast_weather,
    fetch_historical_weather,
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

    def test_raises_http_error_on_server_error(self):
        # _fetch_single_region_weather no longer swallows errors itself — it must
        # let them propagate so _fetch_single_region_weather_with_retry can retry.
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({}, status_code=500)
            with pytest.raises(requests.HTTPError):
                _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)

    def test_raises_connection_error(self):
        with patch("ingestion.weather_client.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("timeout")
            with pytest.raises(requests.exceptions.ConnectionError):
                _fetch_single_region_weather(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)


# ── _fetch_single_region_weather_with_retry ─────────────────────────────────────

class TestFetchSingleRegionWeatherWithRetry:
    def test_retries_after_rate_limit_then_succeeds(self):
        # Regression guard: `raise Exception("Max retries exceeded")` used to sit
        # inside the for-loop body, so a single 429 killed the fetch after one sleep
        # instead of looping back for another attempt.
        responses = [_mock_response({}, status_code=429), _mock_response(API_RESPONSE)]
        with patch("ingestion.weather_client.requests.get", side_effect=responses), \
             patch("ingestion.weather_client.time.sleep") as mock_sleep:
            df = _fetch_single_region_weather_with_retry(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        assert len(df) == len(TIMES) * len(SignalType)
        mock_sleep.assert_called_once()

    def test_retries_after_server_error_then_succeeds(self):
        responses = [_mock_response({}, status_code=503), _mock_response(API_RESPONSE)]
        with patch("ingestion.weather_client.requests.get", side_effect=responses), \
             patch("ingestion.weather_client.time.sleep") as mock_sleep:
            df = _fetch_single_region_weather_with_retry(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        assert len(df) == len(TIMES) * len(SignalType)
        mock_sleep.assert_called_once()

    def test_raises_after_exhausting_all_retries(self):
        with patch("ingestion.weather_client.requests.get") as mock_get, \
             patch("ingestion.weather_client.time.sleep") as mock_sleep:
            mock_get.return_value = _mock_response({}, status_code=429)
            with pytest.raises(Exception, match="Max retries exceeded"):
                _fetch_single_region_weather_with_retry(
                    Region.BAVARIA, START, END, BASE_HISTORICAL_URL, max_retries=3
                )
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 3

    def test_does_not_retry_on_4xx_client_error(self):
        with patch("ingestion.weather_client.requests.get") as mock_get, \
             patch("ingestion.weather_client.time.sleep") as mock_sleep:
            mock_get.return_value = _mock_response({}, status_code=404)
            with pytest.raises(requests.HTTPError):
                _fetch_single_region_weather_with_retry(Region.BAVARIA, START, END, BASE_HISTORICAL_URL)
        assert mock_get.call_count == 1
        mock_sleep.assert_not_called()


# ── fetch_historical_weather / fetch_forecast_weather ──────────────────────────

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


class TestFetchHistoricalWeather:
    def test_returns_data_for_all_regions(self, mock_fetch_single):
        df = fetch_historical_weather(START, END)
        assert set(df["region"].unique()) == {r.value for r in Region}

    def test_uses_historical_url(self, mock_fetch_single):
        fetch_historical_weather(START, END)
        for call in mock_fetch_single.call_args_list:
            assert call.args[3] == BASE_HISTORICAL_URL

    def test_call_count(self, mock_fetch_single):
        fetch_historical_weather(START, END)
        assert mock_fetch_single.call_count == len(list(Region))

    def test_returns_empty_dataframe_when_all_regions_fail(self):
        with patch("ingestion.weather_client._fetch_single_region_weather") as mock:
            mock.return_value = pd.DataFrame()
            df = fetch_historical_weather(START, END)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_partial_failure_still_returns_successful_regions(self):
        regions = list(Region)

        def side_effect(region, *args, **kwargs):
            if region == regions[0]:
                return pd.DataFrame()  # first region fails
            return _single_region_df(region)

        with patch("ingestion.weather_client._fetch_single_region_weather", side_effect=side_effect):
            df = fetch_historical_weather(START, END)

        returned_regions = set(df["region"].unique())
        assert regions[0].value not in returned_regions
        assert len(returned_regions) == len(regions) - 1

    def test_result_contains_expected_columns(self, mock_fetch_single):
        df = fetch_historical_weather(START, END)
        assert set(df.columns) >= {"timestamp", "region", "signal_type", "value", "unit"}

    def test_does_not_add_fetched_at_column(self, mock_fetch_single):
        df = fetch_historical_weather(START, END)
        assert "fetched_at" not in df.columns


class TestFetchForecastWeather:
    def test_returns_data_for_all_regions(self, mock_fetch_single):
        df = fetch_forecast_weather(START, END)
        assert set(df["region"].unique()) == {r.value for r in Region}

    def test_uses_forecast_url(self, mock_fetch_single):
        fetch_forecast_weather(START, END)
        for call in mock_fetch_single.call_args_list:
            assert call.args[3] == BASE_FORECAST_URL

    def test_returns_empty_dataframe_when_all_regions_fail(self):
        with patch("ingestion.weather_client._fetch_single_region_weather") as mock:
            mock.return_value = pd.DataFrame()
            df = fetch_forecast_weather(START, END)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_adds_fetched_at_column(self, mock_fetch_single):
        # raw.weather_forecast's unique key includes fetched_at, and the loader
        # hard-requires the column — every non-empty forecast fetch must stamp it.
        df = fetch_forecast_weather(START, END)
        assert "fetched_at" in df.columns
        assert df["fetched_at"].notna().all()

    def test_fetched_at_is_utc_and_within_call_window(self, mock_fetch_single):
        before = datetime.now(timezone.utc)
        df = fetch_forecast_weather(START, END)
        after = datetime.now(timezone.utc)
        assert (df["fetched_at"] >= before).all()
        assert (df["fetched_at"] <= after).all()
