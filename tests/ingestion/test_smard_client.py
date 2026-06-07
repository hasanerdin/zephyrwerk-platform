from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from ingestion.smard_client import (
    CONSUMPTION_TYPE,
    ENERGY_SOURCE,
    NEIGHBORING_REGION,
    REGION,
    Resolution,
    _get_index,
    _get_series,
    fetch_range,
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


# ── _get_index ────────────────────────────────────────────────────────────────

class TestGetIndex:
    def test_returns_timestamps(self):
        expected = [1704067200000, 1704672000000]
        with patch("ingestion.smard_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({"timestamps": expected})
            result = _get_index(ENERGY_SOURCE.WIND_ONSHORE, REGION.DE, Resolution.HOUR)
        assert result == expected

    def test_missing_key_returns_empty_list(self):
        with patch("ingestion.smard_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({})
            result = _get_index(ENERGY_SOURCE.WIND_ONSHORE, REGION.DE, Resolution.HOUR)
        assert result == []

    def test_raises_on_http_error(self):
        with patch("ingestion.smard_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({}, status_code=404)
            with pytest.raises(requests.HTTPError):
                _get_index(ENERGY_SOURCE.WIND_ONSHORE, REGION.DE, Resolution.HOUR)

    def test_url_constructed_correctly(self):
        with patch("ingestion.smard_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({"timestamps": []})
            _get_index(ENERGY_SOURCE.WIND_ONSHORE, REGION.DE, Resolution.HOUR)
        mock_get.assert_called_once_with(
            f"https://www.smard.de/app/chart_data/{ENERGY_SOURCE.WIND_ONSHORE.value}/{REGION.DE.value}/index_{Resolution.HOUR.value}.json"
        )

    def test_quarter_hour_resolution_in_url(self):
        with patch("ingestion.smard_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({"timestamps": []})
            _get_index(ENERGY_SOURCE.WIND_ONSHORE, REGION.DE_LU, Resolution.QUARTER_HOUR)
        mock_get.assert_called_once_with(
            f"https://www.smard.de/app/chart_data/{ENERGY_SOURCE.WIND_ONSHORE.value}/{REGION.DE_LU.value}/index_{Resolution.QUARTER_HOUR.value}.json"
        )


# ── _get_series ───────────────────────────────────────────────────────────────

class TestGetSeries:
    CHUNK_TS = 1704067200000

    def test_returns_series_data(self):
        expected = [[1704067200000, 100.0], [1704070800000, 200.0]]
        with patch("ingestion.smard_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({"series": expected})
            result = _get_series(ENERGY_SOURCE.WIND_ONSHORE, REGION.DE, Resolution.HOUR, self.CHUNK_TS)
        assert result == expected

    def test_missing_key_returns_empty_list(self):
        with patch("ingestion.smard_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({})
            result = _get_series(ENERGY_SOURCE.WIND_ONSHORE, REGION.DE, Resolution.HOUR, self.CHUNK_TS)
        assert result == []

    def test_raises_on_http_error(self):
        with patch("ingestion.smard_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({}, status_code=500)
            with pytest.raises(requests.HTTPError):
                _get_series(ENERGY_SOURCE.WIND_ONSHORE, REGION.DE, Resolution.HOUR, self.CHUNK_TS)

    def test_url_constructed_correctly(self):
        with patch("ingestion.smard_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response({"series": []})
            _get_series(ENERGY_SOURCE.WIND_ONSHORE, REGION.DE, Resolution.HOUR, self.CHUNK_TS)
        mock_get.assert_called_once_with(
            f"https://www.smard.de/app/chart_data/{ENERGY_SOURCE.WIND_ONSHORE.value}/{REGION.DE.value}/{ENERGY_SOURCE.WIND_ONSHORE.value}_{REGION.DE.value}_{Resolution.HOUR.value}_{self.CHUNK_TS}.json"
        )


# ── fetch_range ───────────────────────────────────────────────────────────────

START = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)
END = datetime(2024, 1, 21, 23, 0, tzinfo=timezone.utc)

# Chunk that starts 1 hour before START — simulates a weekly chunk that overlaps the range
_CHUNK_TS = int(START.timestamp() * 1000) - 3_600_000

_SERIES_DATA = [
    [int(START.timestamp() * 1000), 500.0],
    [int(START.timestamp() * 1000) + 3_600_000, 600.0],
    [int(END.timestamp() * 1000), 700.0],
]


@pytest.fixture
def mock_index_and_series():
    with patch("ingestion.smard_client._get_index") as m_idx, \
         patch("ingestion.smard_client._get_series") as m_ser:
        m_idx.return_value = [_CHUNK_TS]
        m_ser.return_value = _SERIES_DATA
        yield m_idx, m_ser


class TestFetchRange:
    def test_returns_expected_columns(self, mock_index_and_series):
        df = fetch_range(ENERGY_SOURCE.WIND_ONSHORE, START, END)
        assert list(df.columns) == ["timestamp", "value", "signal", "unit"]

    def test_energy_source_uses_region_de_and_unit_mw(self, mock_index_and_series):
        m_idx, _ = mock_index_and_series
        df = fetch_range(ENERGY_SOURCE.WIND_ONSHORE, START, END)
        m_idx.assert_called_once_with(
            ENERGY_SOURCE.WIND_ONSHORE, REGION.DE, Resolution.HOUR
        )
        assert df["unit"].unique().tolist() == ["MW"]

    def test_neighboring_region_uses_de_lu_and_eur_mwh(self, mock_index_and_series):
        m_idx, _ = mock_index_and_series
        df = fetch_range(NEIGHBORING_REGION.FRANCE, START, END)
        m_idx.assert_called_once_with(
            NEIGHBORING_REGION.FRANCE, REGION.DE_LU, Resolution.HOUR
        )
        assert df["unit"].unique().tolist() == ["EUR_MWH"]

    def test_signal_column_matches_enum_name(self, mock_index_and_series):
        df = fetch_range(ENERGY_SOURCE.SOLAR, START, END)
        assert df["signal"].unique().tolist() == ["SOLAR"]

    def test_result_is_sorted_by_timestamp(self, mock_index_and_series):
        df = fetch_range(ENERGY_SOURCE.WIND_ONSHORE, START, END)
        assert df["timestamp"].is_monotonic_increasing

    def test_timestamps_are_utc_aware(self, mock_index_and_series):
        df = fetch_range(ENERGY_SOURCE.WIND_ONSHORE, START, END)
        assert str(df["timestamp"].dt.tz) == "UTC"

    def test_data_filtered_to_date_range(self):
        narrow_start = datetime(2024, 1, 16, 0, 0, tzinfo=timezone.utc)
        narrow_end = datetime(2024, 1, 17, 0, 0, tzinfo=timezone.utc)

        start_ms = int(narrow_start.timestamp() * 1000)
        end_ms = int(narrow_end.timestamp() * 1000)
        before_start_ms = start_ms - 3_600_000  # 1 hour before range

        series = [
            [before_start_ms, 100.0],  # outside — should be excluded
            [start_ms, 200.0],         # at start — included
            [end_ms, 300.0],           # at end — included
        ]
        with patch("ingestion.smard_client._get_index") as m_idx, \
             patch("ingestion.smard_client._get_series") as m_ser:
            m_idx.return_value = [before_start_ms]
            m_ser.return_value = series
            df = fetch_range(ENERGY_SOURCE.WIND_ONSHORE, narrow_start, narrow_end)

        assert all(df["timestamp"] >= narrow_start)
        assert all(df["timestamp"] <= narrow_end)
        assert len(df) == 2

    def test_custom_resolution_is_forwarded(self, mock_index_and_series):
        m_idx, _ = mock_index_and_series
        fetch_range(ENERGY_SOURCE.WIND_ONSHORE, START, END, Resolution.DAY)
        m_idx.assert_called_once_with(
            ENERGY_SOURCE.WIND_ONSHORE, REGION.DE, Resolution.DAY
        )

    def test_none_values_coerced_to_nan(self, mock_index_and_series):
        _, m_ser = mock_index_and_series
        m_ser.return_value = [[int(START.timestamp() * 1000), None]]
        df = fetch_range(ENERGY_SOURCE.WIND_ONSHORE, START, END)
        assert df["value"].isna().sum() == 1

    def test_raises_on_empty_index(self):
        with patch("ingestion.smard_client._get_index") as m_idx:
            m_idx.return_value = []
            with pytest.raises(ValueError, match="No timestamps found"):
                fetch_range(ENERGY_SOURCE.WIND_ONSHORE, START, END)

    def test_raises_on_non_enum_signal(self):
        with pytest.raises(ValueError, match="Unsupported signal name"):
            fetch_range("NOT_A_SIGNAL", START, END)  # type: ignore[arg-type]

    def test_returns_empty_dataframe_when_all_series_empty(self):
        with patch("ingestion.smard_client._get_index") as m_idx, \
             patch("ingestion.smard_client._get_series") as m_ser:
            m_idx.return_value = [_CHUNK_TS]
            m_ser.return_value = []
            df = fetch_range(ENERGY_SOURCE.WIND_ONSHORE, START, END)
        assert list(df.columns) == ["timestamp", "value", "signal", "unit"]
        assert len(df) == 0

    def test_multiple_chunks_are_concatenated(self):
        chunk1 = _CHUNK_TS
        chunk2 = _CHUNK_TS + 7 * 24 * 3_600_000  # 1 week later

        series_chunk1 = [[int(START.timestamp() * 1000), 100.0]]
        series_chunk2 = [[int(START.timestamp() * 1000) + 7 * 24 * 3_600_000, 200.0]]

        with patch("ingestion.smard_client._get_index") as m_idx, \
             patch("ingestion.smard_client._get_series") as m_ser:
            # Make end wide enough to cover both chunks
            wide_end = datetime(2024, 1, 29, 23, 0, tzinfo=timezone.utc)
            m_idx.return_value = [chunk1, chunk2]
            m_ser.side_effect = [series_chunk1, series_chunk2]
            df = fetch_range(ENERGY_SOURCE.WIND_ONSHORE, START, wide_end)

        assert len(df) == 2
        assert m_ser.call_count == 2
