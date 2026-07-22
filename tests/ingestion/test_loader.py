from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import ingestion.loader as loader
from ingestion.s3_uploader import DATA_NAMES


@pytest.fixture(autouse=True)
def bucket_env(monkeypatch):
    monkeypatch.setenv("ZEPHYRWERK_AWS_BUCKET_NAME", "test-bucket")


# ── _get_dataframe ───────────────────────────────────────────────────────────

class TestGetDataframe:
    def test_returns_none_when_dataset_not_found(self):
        with patch("ingestion.loader.ds.dataset", side_effect=FileNotFoundError):
            result = loader._get_dataframe(MagicMock(), DATA_NAMES.WEATHER, datetime(2024, 1, 15, tzinfo=timezone.utc))
        assert result is None

    def test_filters_rows_to_requested_date_only(self):
        raw_df = pd.DataFrame({
            "timestamp": pd.to_datetime([
                "2024-01-14T23:00:00Z", "2024-01-15T00:00:00Z", "2024-01-15T12:00:00Z", "2024-01-16T00:00:00Z",
            ]),
            "value": [1.0, 2.0, 3.0, 4.0],
        })
        mock_dataset = MagicMock()
        mock_dataset.to_table.return_value.to_pandas.return_value = raw_df
        with patch("ingestion.loader.ds.dataset", return_value=mock_dataset):
            result = loader._get_dataframe(MagicMock(), DATA_NAMES.WEATHER, datetime(2024, 1, 15, tzinfo=timezone.utc))
        assert result["value"].tolist() == [2.0, 3.0]

    def test_returns_none_when_no_rows_match_requested_date(self):
        raw_df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-14T23:00:00Z"]),
            "value": [1.0],
        })
        mock_dataset = MagicMock()
        mock_dataset.to_table.return_value.to_pandas.return_value = raw_df
        with patch("ingestion.loader.ds.dataset", return_value=mock_dataset):
            result = loader._get_dataframe(MagicMock(), DATA_NAMES.WEATHER, datetime(2024, 1, 15, tzinfo=timezone.utc))
        assert result is None

    def test_returns_none_for_empty_file(self):
        mock_dataset = MagicMock()
        mock_dataset.to_table.return_value.to_pandas.return_value = pd.DataFrame()
        with patch("ingestion.loader.ds.dataset", return_value=mock_dataset):
            result = loader._get_dataframe(MagicMock(), DATA_NAMES.WEATHER, datetime(2024, 1, 15, tzinfo=timezone.utc))
        assert result is None


# ── _load_weather_forecast_day ───────────────────────────────────────────────

def _forecast_df() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-15T00:00:00Z"]),
        "region": ["wind_region_brandenburg"],
        "signal_type": ["wind_speed_100m"],
        "value": [5.0],
        "unit": ["km/h"],
        "fetched_at": pd.to_datetime(["2024-01-14T03:00:00Z"]),
    })


class TestLoadWeatherForecastDay:
    def test_skips_when_no_data_found(self):
        conn = MagicMock()
        with patch("ingestion.loader._get_dataframe", return_value=None):
            loader._load_weather_forecast_day(conn, MagicMock(), datetime(2024, 1, 15, tzinfo=timezone.utc))
        conn.cursor.assert_not_called()

    def test_inserts_rows_including_fetched_at(self):
        conn = MagicMock()
        with patch("ingestion.loader._get_dataframe", return_value=_forecast_df()), \
             patch("ingestion.loader.execute_values") as mock_execute_values:
            loader._load_weather_forecast_day(conn, MagicMock(), datetime(2024, 1, 15, tzinfo=timezone.utc))

        rows = mock_execute_values.call_args.args[2]
        assert rows == [(
            pd.Timestamp("2024-01-15T00:00:00Z"),
            "wind_region_brandenburg",
            "wind_speed_100m",
            5.0,
            "km/h",
            pd.Timestamp("2024-01-14T03:00:00Z"),
        )]
        conn.commit.assert_called_once()

    def test_insert_sql_targets_weather_forecast_table_with_fetched_at_conflict_key(self):
        conn = MagicMock()
        with patch("ingestion.loader._get_dataframe", return_value=_forecast_df()), \
             patch("ingestion.loader.execute_values") as mock_execute_values:
            loader._load_weather_forecast_day(conn, MagicMock(), datetime(2024, 1, 15, tzinfo=timezone.utc))

        insert_sql = mock_execute_values.call_args.args[1]
        assert "raw.weather_forecast" in insert_sql
        assert "ON CONFLICT (timestamp, region, signal_type, fetched_at)" in insert_sql

    def test_raises_keyerror_if_fetched_at_column_missing(self):
        # Regression guard: fetch_forecast_weather must always stamp `fetched_at`
        # onto every non-empty result, since this loader hard-requires the column
        # for both the insert and the ON CONFLICT key.
        df_without_fetched_at = _forecast_df().drop(columns=["fetched_at"])
        conn = MagicMock()
        with patch("ingestion.loader._get_dataframe", return_value=df_without_fetched_at):
            with pytest.raises(KeyError):
                loader._load_weather_forecast_day(conn, MagicMock(), datetime(2024, 1, 15, tzinfo=timezone.utc))

    def test_rolls_back_and_does_not_raise_on_insert_failure(self):
        conn = MagicMock()
        with patch("ingestion.loader._get_dataframe", return_value=_forecast_df()), \
             patch("ingestion.loader.execute_values", side_effect=RuntimeError("db down")):
            loader._load_weather_forecast_day(conn, MagicMock(), datetime(2024, 1, 15, tzinfo=timezone.utc))
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()


# ── load_from_s3_to_db ───────────────────────────────────────────────────────

class TestLoadFromS3ToDb:
    def test_loads_smard_weather_and_forecast_for_the_same_given_date(self):
        date = datetime(2024, 1, 15, tzinfo=timezone.utc)
        conn = MagicMock()
        fs = MagicMock()
        with patch("ingestion.loader._get_db_connection", return_value=conn), \
             patch("ingestion.loader._get_filesystem", return_value=fs), \
             patch("ingestion.loader._load_smard_day") as mock_smard, \
             patch("ingestion.loader._load_weather_day") as mock_weather, \
             patch("ingestion.loader._load_weather_forecast_day") as mock_forecast:
            loader.load_from_s3_to_db(date)

        mock_smard.assert_called_once_with(conn, fs, date)
        mock_weather.assert_called_once_with(conn, fs, date)
        # The forecast pipeline now uploads one S3 file per target day (see
        # orchestration.run_pipeline.fetch_weekly_weather_forecast), so the
        # loader reads the forecast for `date` directly — no more +1 day offset.
        mock_forecast.assert_called_once_with(conn, fs, date)

    def test_closes_connection_even_if_a_loader_raises(self):
        date = datetime(2024, 1, 15, tzinfo=timezone.utc)
        conn = MagicMock()
        with patch("ingestion.loader._get_db_connection", return_value=conn), \
             patch("ingestion.loader._get_filesystem", return_value=MagicMock()), \
             patch("ingestion.loader._load_smard_day", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                loader.load_from_s3_to_db(date)
        conn.close.assert_called_once()


class TestLoadRange:
    def test_calls_load_from_s3_to_db_once_per_day_inclusive(self):
        start = datetime(2024, 1, 15, tzinfo=timezone.utc)
        end = datetime(2024, 1, 17, tzinfo=timezone.utc)
        with patch("ingestion.loader.load_from_s3_to_db") as mock_load:
            loader.load_range(start, end)
        called_dates = [c.args[0] for c in mock_load.call_args_list]
        assert called_dates == [
            datetime(2024, 1, 15, tzinfo=timezone.utc),
            datetime(2024, 1, 16, tzinfo=timezone.utc),
            datetime(2024, 1, 17, tzinfo=timezone.utc),
        ]

    def test_naive_datetimes_are_treated_as_utc(self):
        with patch("ingestion.loader.load_from_s3_to_db") as mock_load:
            loader.load_range(datetime(2024, 1, 15), datetime(2024, 1, 15))
        called_date = mock_load.call_args.args[0]
        assert called_date.tzinfo is not None
