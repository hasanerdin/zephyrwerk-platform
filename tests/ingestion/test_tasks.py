from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

import ingestion.tasks as tasks
from ingestion.s3_uploader import DATA_NAMES

START = datetime(2024, 1, 15, tzinfo=timezone.utc)
END = datetime(2024, 1, 16, tzinfo=timezone.utc)


# ── _missing_day_ranges ──────────────────────────────────────────────────────

class TestMissingDayRanges:
    def test_all_days_missing_collapse_into_one_range(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 5, tzinfo=timezone.utc)
        with patch("ingestion.tasks.is_already_uploaded", return_value=False):
            ranges = tasks._missing_day_ranges(DATA_NAMES.SMARD, start, end)
        assert len(ranges) == 1
        range_start, range_end = ranges[0]
        assert range_start.date() == start.date()
        assert range_end.date() == end.date()

    def test_all_days_already_uploaded_returns_no_ranges(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 5, tzinfo=timezone.utc)
        with patch("ingestion.tasks.is_already_uploaded", return_value=True) as mock_already:
            ranges = tasks._missing_day_ranges(DATA_NAMES.SMARD, start, end)
        assert ranges == []
        assert mock_already.call_count == 5  # one check per calendar day, no fetch needed

    def test_a_gap_in_the_middle_splits_into_two_ranges(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 5, tzinfo=timezone.utc)

        def already_uploaded(data_name, year, month, day):
            return day == 3  # Jan 3rd is the only day already uploaded

        with patch("ingestion.tasks.is_already_uploaded", side_effect=already_uploaded):
            ranges = tasks._missing_day_ranges(DATA_NAMES.SMARD, start, end)

        assert len(ranges) == 2
        assert [r[0].day for r in ranges] == [1, 4]
        assert [r[1].day for r in ranges] == [2, 5]

    def test_single_day_range(self):
        day = datetime(2024, 1, 15, tzinfo=timezone.utc)
        with patch("ingestion.tasks.is_already_uploaded", return_value=False):
            ranges = tasks._missing_day_ranges(DATA_NAMES.SMARD, day, day)
        assert ranges == [(day, day)]


# ── run_smard_range ───────────────────────────────────────────────────────────

class TestRunSmardRange:
    def test_skips_fetch_when_all_days_already_uploaded(self):
        with patch("ingestion.tasks.is_already_uploaded", return_value=True), \
             patch("ingestion.tasks.fetch_range") as mock_fetch, \
             patch("ingestion.tasks.upload_to_s3") as mock_upload:
            tasks.run_smard_range(START, END)
        mock_fetch.assert_not_called()
        mock_upload.assert_not_called()

    def test_fetches_once_for_a_multi_day_missing_range(self):
        # Regression guard: a multi-day backfill used to call fetch_range once PER
        # DAY, redownloading the same underlying weekly SMARD chunk up to 7x. A
        # contiguous missing stretch must now be fetched in a single call.
        start = datetime(2024, 1, 15, tzinfo=timezone.utc)
        end = datetime(2024, 1, 19, tzinfo=timezone.utc)
        df = pd.DataFrame({
            "timestamp": pd.date_range(start, periods=5, freq="D", tz="UTC"),
            "value": range(5),
        })
        with patch("ingestion.tasks.is_already_uploaded", return_value=False), \
             patch("ingestion.tasks.fetch_range", return_value=df) as mock_fetch, \
             patch("ingestion.tasks.upload_to_s3") as mock_upload:
            tasks.run_smard_range(start, end)

        mock_fetch.assert_called_once()
        assert mock_fetch.call_args.kwargs["start_date"].date() == start.date()
        assert mock_fetch.call_args.kwargs["end_date"].date() == end.date()
        assert mock_upload.call_count == 5  # one upload per calendar day, split from the range fetch

    def test_skips_upload_when_fetch_returns_empty(self):
        with patch("ingestion.tasks.is_already_uploaded", return_value=False), \
             patch("ingestion.tasks.fetch_range", return_value=pd.DataFrame()) as mock_fetch, \
             patch("ingestion.tasks.upload_to_s3") as mock_upload:
            tasks.run_smard_range(START, START)
        mock_fetch.assert_called_once()
        mock_upload.assert_not_called()

    def test_continues_to_next_range_but_raises_after_a_range_fails(self):
        # Two missing ranges (split by a gap); a failure fetching the first must
        # not prevent the second from being attempted, but the overall call now
        # raises once every range has had a chance to run (see ingestion/tasks.py
        # docstring: tasks raise on failure so the container exits non-zero).
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 5, tzinfo=timezone.utc)

        def already_uploaded(data_name, year, month, day):
            return day == 3

        df = pd.DataFrame({"timestamp": [datetime(2024, 1, 4, tzinfo=timezone.utc)], "value": [1.0]})
        with patch("ingestion.tasks.is_already_uploaded", side_effect=already_uploaded), \
             patch("ingestion.tasks.fetch_range", side_effect=[RuntimeError("boom"), df]) as mock_fetch, \
             patch("ingestion.tasks.upload_to_s3") as mock_upload:
            with pytest.raises(RuntimeError):
                tasks.run_smard_range(start, end)

        assert mock_fetch.call_count == 2
        mock_upload.assert_called_once()


# ── run_weather_range ─────────────────────────────────────────────────────────

class TestRunWeatherRange:
    def test_skips_fetch_when_all_days_already_uploaded(self):
        with patch("ingestion.tasks.is_already_uploaded", return_value=True), \
             patch("ingestion.tasks.fetch_historical_weather") as mock_fetch, \
             patch("ingestion.tasks.upload_to_s3") as mock_upload:
            tasks.run_weather_range(START, END)
        mock_fetch.assert_not_called()
        mock_upload.assert_not_called()

    def test_fetches_once_for_a_multi_day_missing_range(self):
        start = datetime(2024, 1, 15, tzinfo=timezone.utc)
        end = datetime(2024, 1, 19, tzinfo=timezone.utc)
        df = pd.DataFrame({
            "timestamp": pd.date_range(start, periods=5, freq="D", tz="UTC"),
            "value": range(5),
        })
        with patch("ingestion.tasks.is_already_uploaded", return_value=False), \
             patch("ingestion.tasks.fetch_historical_weather", return_value=df) as mock_fetch, \
             patch("ingestion.tasks.upload_to_s3") as mock_upload:
            tasks.run_weather_range(start, end)

        mock_fetch.assert_called_once()
        call_start, call_end = mock_fetch.call_args.args
        assert call_start.date() == start.date()
        assert call_end.date() == end.date()
        assert mock_upload.call_count == 5

    def test_skips_upload_when_fetch_returns_empty(self):
        with patch("ingestion.tasks.is_already_uploaded", return_value=False), \
             patch("ingestion.tasks.fetch_historical_weather", return_value=pd.DataFrame()) as mock_fetch, \
             patch("ingestion.tasks.upload_to_s3") as mock_upload:
            tasks.run_weather_range(START, START)
        mock_fetch.assert_called_once()
        mock_upload.assert_not_called()

    def test_continues_to_next_range_but_raises_after_a_range_fails(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 5, tzinfo=timezone.utc)

        def already_uploaded(data_name, year, month, day):
            return day == 3

        df = pd.DataFrame({"timestamp": [datetime(2024, 1, 4, tzinfo=timezone.utc)], "value": [1.0]})
        with patch("ingestion.tasks.is_already_uploaded", side_effect=already_uploaded), \
             patch(
                 "ingestion.tasks.fetch_historical_weather", side_effect=[RuntimeError("boom"), df]
             ) as mock_fetch, \
             patch("ingestion.tasks.upload_to_s3") as mock_upload:
            with pytest.raises(RuntimeError):
                tasks.run_weather_range(start, end)

        assert mock_fetch.call_count == 2
        mock_upload.assert_called_once()


# ── run_weather_forecast ─────────────────────────────────────────────────────

class TestRunWeatherForecast:
    def test_fetches_full_range_and_uploads_one_file_per_day(self):
        day1 = datetime(2024, 1, 15, tzinfo=timezone.utc)
        day2 = datetime(2024, 1, 16, tzinfo=timezone.utc)
        df = pd.DataFrame({
            "timestamp": [day1, day2],
            "value": [1.0, 2.0],
        })
        with patch("ingestion.tasks.fetch_forecast_weather", return_value=df) as mock_fetch, \
             patch("ingestion.tasks.upload_to_s3") as mock_upload:
            tasks.run_weather_forecast(day1, day2)

        call_start, call_end = mock_fetch.call_args.args
        assert call_start == day1
        assert call_end == day2.replace(hour=23, minute=59, second=59)
        assert mock_upload.call_count == 2  # one upload per calendar day in the range

    def test_raises_when_no_forecast_data_returned(self):
        with patch("ingestion.tasks.fetch_forecast_weather", return_value=pd.DataFrame()), \
             patch("ingestion.tasks.upload_to_s3") as mock_upload:
            with pytest.raises(RuntimeError):
                tasks.run_weather_forecast(START, END)
        mock_upload.assert_not_called()

    def test_has_no_already_uploaded_guard(self):
        # Forecasts should always refresh, unlike the real-data fetchers above.
        df = pd.DataFrame({"timestamp": [START], "value": [1.0]})
        with patch("ingestion.tasks.is_already_uploaded") as mock_already, \
             patch("ingestion.tasks.fetch_forecast_weather", return_value=df), \
             patch("ingestion.tasks.upload_to_s3"):
            tasks.run_weather_forecast(START, END)
        mock_already.assert_not_called()
