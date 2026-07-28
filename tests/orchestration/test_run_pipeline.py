import ast
import inspect
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

import orchestration.run_pipeline as run_pipeline
from ingestion.s3_uploader import DATA_NAMES

START = datetime(2024, 1, 15, tzinfo=timezone.utc)
END = datetime(2024, 1, 16, tzinfo=timezone.utc)


# ── module import must not trigger pipeline runs ────────────────────────────

# Regression guard for a bug where a bare `run_daily_pipeline()` call sat at
# module scope, outside `if __name__ == "__main__":` — it fired on every
# import, and a second time after any explicit --mode selection.
_FORBIDDEN_TOP_LEVEL_CALLS = {"run_daily_pipeline", "run_historical_pipeline", "run_model_training"}


def test_module_body_has_no_bare_pipeline_calls_outside_main_guard():
    source = inspect.getsource(run_pipeline)
    tree = ast.parse(source)

    def _call_name(node):
        return node.func.id if isinstance(node.func, ast.Name) else None

    offending = [
        _call_name(node.value)
        for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        and _call_name(node.value) in _FORBIDDEN_TOP_LEVEL_CALLS
    ]

    assert not offending, (
        "Found pipeline function(s) called at module scope, outside "
        f"`if __name__ == '__main__':` — these run on every import: {offending}"
    )


# ── _missing_day_ranges ──────────────────────────────────────────────────────

class TestMissingDayRanges:
    def test_all_days_missing_collapse_into_one_range(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 5, tzinfo=timezone.utc)
        with patch("orchestration.run_pipeline.is_already_uploaded", return_value=False):
            ranges = run_pipeline._missing_day_ranges(DATA_NAMES.SMARD, start, end)
        assert len(ranges) == 1
        range_start, range_end = ranges[0]
        assert range_start.date() == start.date()
        assert range_end.date() == end.date()

    def test_all_days_already_uploaded_returns_no_ranges(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 5, tzinfo=timezone.utc)
        with patch("orchestration.run_pipeline.is_already_uploaded", return_value=True) as mock_already:
            ranges = run_pipeline._missing_day_ranges(DATA_NAMES.SMARD, start, end)
        assert ranges == []
        assert mock_already.call_count == 5  # one check per calendar day, no fetch needed

    def test_a_gap_in_the_middle_splits_into_two_ranges(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 5, tzinfo=timezone.utc)

        def already_uploaded(data_name, year, month, day):
            return day == 3  # Jan 3rd is the only day already uploaded

        with patch("orchestration.run_pipeline.is_already_uploaded", side_effect=already_uploaded):
            ranges = run_pipeline._missing_day_ranges(DATA_NAMES.SMARD, start, end)

        assert len(ranges) == 2
        assert [r[0].day for r in ranges] == [1, 4]
        assert [r[1].day for r in ranges] == [2, 5]

    def test_single_day_range(self):
        day = datetime(2024, 1, 15, tzinfo=timezone.utc)
        with patch("orchestration.run_pipeline.is_already_uploaded", return_value=False):
            ranges = run_pipeline._missing_day_ranges(DATA_NAMES.SMARD, day, day)
        assert ranges == [(day, day)]


# ── run_smard_range ───────────────────────────────────────────────────────────

class TestRunSmardRange:
    def test_skips_fetch_when_all_days_already_uploaded(self):
        with patch("orchestration.run_pipeline.is_already_uploaded", return_value=True), \
             patch("orchestration.run_pipeline.fetch_range") as mock_fetch, \
             patch("orchestration.run_pipeline.upload_to_s3") as mock_upload:
            run_pipeline.run_smard_range(START, END)
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
        with patch("orchestration.run_pipeline.is_already_uploaded", return_value=False), \
             patch("orchestration.run_pipeline.fetch_range", return_value=df) as mock_fetch, \
             patch("orchestration.run_pipeline.upload_to_s3") as mock_upload:
            run_pipeline.run_smard_range(start, end)

        mock_fetch.assert_called_once()
        assert mock_fetch.call_args.kwargs["start_date"].date() == start.date()
        assert mock_fetch.call_args.kwargs["end_date"].date() == end.date()
        assert mock_upload.call_count == 5  # one upload per calendar day, split from the range fetch

    def test_skips_upload_when_fetch_returns_empty(self):
        with patch("orchestration.run_pipeline.is_already_uploaded", return_value=False), \
             patch("orchestration.run_pipeline.fetch_range", return_value=pd.DataFrame()) as mock_fetch, \
             patch("orchestration.run_pipeline.upload_to_s3") as mock_upload:
            run_pipeline.run_smard_range(START, START)
        mock_fetch.assert_called_once()
        mock_upload.assert_not_called()

    def test_continues_to_next_range_when_one_range_fails(self):
        # Two missing ranges (split by a gap); a failure fetching the first must
        # not prevent the second from being attempted.
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 5, tzinfo=timezone.utc)

        def already_uploaded(data_name, year, month, day):
            return day == 3

        df = pd.DataFrame({"timestamp": [datetime(2024, 1, 4, tzinfo=timezone.utc)], "value": [1.0]})
        with patch("orchestration.run_pipeline.is_already_uploaded", side_effect=already_uploaded), \
             patch("orchestration.run_pipeline.fetch_range", side_effect=[RuntimeError("boom"), df]) as mock_fetch, \
             patch("orchestration.run_pipeline.upload_to_s3") as mock_upload:
            run_pipeline.run_smard_range(start, end)  # must not raise

        assert mock_fetch.call_count == 2
        mock_upload.assert_called_once()


# ── run_weather_range ─────────────────────────────────────────────────────────

class TestRunWeatherRange:
    def test_skips_fetch_when_all_days_already_uploaded(self):
        with patch("orchestration.run_pipeline.is_already_uploaded", return_value=True), \
             patch("orchestration.run_pipeline.fetch_historical_weather") as mock_fetch, \
             patch("orchestration.run_pipeline.upload_to_s3") as mock_upload:
            run_pipeline.run_weather_range(START, END)
        mock_fetch.assert_not_called()
        mock_upload.assert_not_called()

    def test_fetches_once_for_a_multi_day_missing_range(self):
        start = datetime(2024, 1, 15, tzinfo=timezone.utc)
        end = datetime(2024, 1, 19, tzinfo=timezone.utc)
        df = pd.DataFrame({
            "timestamp": pd.date_range(start, periods=5, freq="D", tz="UTC"),
            "value": range(5),
        })
        with patch("orchestration.run_pipeline.is_already_uploaded", return_value=False), \
             patch("orchestration.run_pipeline.fetch_historical_weather", return_value=df) as mock_fetch, \
             patch("orchestration.run_pipeline.upload_to_s3") as mock_upload:
            run_pipeline.run_weather_range(start, end)

        mock_fetch.assert_called_once()
        call_start, call_end = mock_fetch.call_args.args
        assert call_start.date() == start.date()
        assert call_end.date() == end.date()
        assert mock_upload.call_count == 5

    def test_skips_upload_when_fetch_returns_empty(self):
        with patch("orchestration.run_pipeline.is_already_uploaded", return_value=False), \
             patch("orchestration.run_pipeline.fetch_historical_weather", return_value=pd.DataFrame()) as mock_fetch, \
             patch("orchestration.run_pipeline.upload_to_s3") as mock_upload:
            run_pipeline.run_weather_range(START, START)
        mock_fetch.assert_called_once()
        mock_upload.assert_not_called()

    def test_continues_to_next_range_when_one_range_fails(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 5, tzinfo=timezone.utc)

        def already_uploaded(data_name, year, month, day):
            return day == 3

        df = pd.DataFrame({"timestamp": [datetime(2024, 1, 4, tzinfo=timezone.utc)], "value": [1.0]})
        with patch("orchestration.run_pipeline.is_already_uploaded", side_effect=already_uploaded), \
             patch(
                 "orchestration.run_pipeline.fetch_historical_weather", side_effect=[RuntimeError("boom"), df]
             ) as mock_fetch, \
             patch("orchestration.run_pipeline.upload_to_s3") as mock_upload:
            run_pipeline.run_weather_range(start, end)  # must not raise

        assert mock_fetch.call_count == 2
        mock_upload.assert_called_once()


# ── run_weather_forecast ─────────────────────────────────────────────────────

class TestRunWeatherForecast:
    def test_fetches_and_uploads_for_given_range(self):
        df = pd.DataFrame({"timestamp": [START], "value": [1.0]})
        with patch("orchestration.run_pipeline.fetch_forecast_weather", return_value=df) as mock_fetch, \
             patch("orchestration.run_pipeline.upload_to_s3") as mock_upload:
            run_pipeline.run_weather_forecast(START, END)
        mock_fetch.assert_called_once_with(START, END)
        mock_upload.assert_called_once_with(df, DATA_NAMES.WEATHER_FORECAST)

    def test_has_no_already_uploaded_guard(self):
        # Forecasts should always refresh, unlike the real-data fetchers above.
        df = pd.DataFrame({"timestamp": [START], "value": [1.0]})
        with patch("orchestration.run_pipeline.is_already_uploaded") as mock_already, \
             patch("orchestration.run_pipeline.fetch_forecast_weather", return_value=df), \
             patch("orchestration.run_pipeline.upload_to_s3"):
            run_pipeline.run_weather_forecast(START, END)
        mock_already.assert_not_called()


# ── fetch_yesterday_data ──────────────────────────────────────────────────────

class TestFetchYesterdayData:
    def test_fetches_smard_and_weather_for_yesterday(self):
        with patch("orchestration.run_pipeline.run_smard_range") as mock_smard, \
             patch("orchestration.run_pipeline.run_weather_range") as mock_weather:
            run_pipeline.fetch_yesterday_data()

        smard_start, smard_end = mock_smard.call_args.args
        weather_start, weather_end = mock_weather.call_args.args
        assert (smard_start, smard_end) == (weather_start, weather_end)
        assert smard_start.time() == time(0, 0, 0)
        assert smard_start == smard_end  # a single calendar day
        assert smard_start.date() == (datetime.now(timezone.utc) - timedelta(days=1)).date()

    def test_does_not_raise_when_smard_fetch_fails(self):
        with patch("orchestration.run_pipeline.run_smard_range", side_effect=RuntimeError("api down")), \
             patch("orchestration.run_pipeline.run_weather_range") as mock_weather:
            run_pipeline.fetch_yesterday_data()  # must not raise

        # SMARD and weather each have their own try/except now, so a SMARD
        # failure does not prevent the weather fetch from running.
        weather_start, weather_end = mock_weather.call_args.args
        assert weather_start.time() == time(0, 0, 0)
        assert weather_start == weather_end
        assert weather_start.date() == (datetime.now(timezone.utc) - timedelta(days=1)).date()


# ── fetch_weekly_weather_forecast ────────────────────────────────────────────

class TestFetchWeeklyWeatherForecast:
    def test_fetches_one_day_at_a_time_for_eight_days_inclusive(self):
        with patch("orchestration.run_pipeline.run_weather_forecast") as mock_forecast:
            run_pipeline.fetch_weekly_weather_forecast()

        assert mock_forecast.call_count == 8  # today .. today+7, inclusive

        first_start, _ = mock_forecast.call_args_list[0].args
        last_start, _ = mock_forecast.call_args_list[-1].args
        assert first_start.date() == datetime.now(timezone.utc).date()
        assert last_start.date() == first_start.date() + timedelta(days=7)

        for call in mock_forecast.call_args_list:
            day_start, day_end = call.args
            assert day_start.date() == day_end.date()  # one calendar day per call

    def test_continues_to_next_day_when_one_day_fails(self):
        with patch(
                "orchestration.run_pipeline.run_weather_forecast",
                side_effect=[RuntimeError("boom")] + [None] * 7,
            ) as mock_forecast:
            run_pipeline.fetch_weekly_weather_forecast()  # must not raise
        assert mock_forecast.call_count == 8


# ── run_daily_pipeline ────────────────────────────────────────────────────────

class TestRunDailyPipeline:
    def test_calls_yesterday_and_weekly_forecast_then_loads_and_runs_dbt(self):
        with patch("orchestration.run_pipeline.fetch_yesterday_data") as mock_yesterday, \
             patch("orchestration.run_pipeline.fetch_weekly_weather_forecast") as mock_weekly, \
             patch("orchestration.run_pipeline.load_range") as mock_load_range, \
             patch("orchestration.run_pipeline.run_dbt") as mock_dbt:
            run_pipeline.run_daily_pipeline()

        mock_yesterday.assert_called_once()
        mock_weekly.assert_called_once()

        load_start, load_end = mock_load_range.call_args.args
        today = datetime.now(timezone.utc).date()
        assert load_start.date() == today - timedelta(days=1)
        assert load_end.date() == today + timedelta(days=7)

        mock_dbt.assert_any_call("run")
        mock_dbt.assert_any_call("test")

    def test_forecast_still_runs_when_yesterdays_real_data_fetch_fails(self):
        # This is the fix for last session's finding: SMARD/weather and the
        # weekly forecast used to share one try/except, so a SMARD failure
        # silently skipped the forecast fetch too. They're now decoupled.
        with patch("orchestration.run_pipeline.run_smard_range", side_effect=RuntimeError("api down")), \
             patch("orchestration.run_pipeline.run_weather_range") as mock_weather, \
             patch("orchestration.run_pipeline.run_weather_forecast") as mock_forecast, \
             patch("orchestration.run_pipeline.load_range") as mock_load_range, \
             patch("orchestration.run_pipeline.run_dbt") as mock_dbt:
            run_pipeline.run_daily_pipeline()  # must not raise

        mock_load_range.assert_called_once()
        mock_dbt.assert_any_call("run")
        mock_dbt.assert_any_call("test")
        assert mock_forecast.call_count == 8  # forecast fetch unaffected by the SMARD failure
        mock_weather.assert_called_once()  # weather fetch is now independent of SMARD within fetch_yesterday_data


# ── run_historical_pipeline ──────────────────────────────────────────────────

class TestRunHistoricalPipeline:
    def test_calls_smard_and_weather_range_once_each_then_loads_and_runs_dbt(self):
        # Regression guard: the historical path used to loop day-by-day and call
        # a single-day fetch helper once per calendar day (redownloading the same
        # underlying weekly SMARD chunk up to 7x for a multi-day range). It now
        # delegates the whole range to run_smard_range/run_weather_range once,
        # which do their own internal batching by contiguous missing-day stretch.
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 3, tzinfo=timezone.utc)
        with patch("orchestration.run_pipeline.run_smard_range") as mock_smard, \
             patch("orchestration.run_pipeline.run_weather_range") as mock_weather, \
             patch("orchestration.run_pipeline.load_range") as mock_load_range, \
             patch("orchestration.run_pipeline.run_dbt") as mock_dbt, \
             patch("orchestration.run_pipeline.run_model_training") as mock_training:
            run_pipeline.run_historical_pipeline(start, end)

        mock_smard.assert_called_once_with(start, end)
        mock_weather.assert_called_once_with(start, end)
        mock_load_range.assert_called_once_with(start, end)
        mock_dbt.assert_any_call("run")
        mock_dbt.assert_any_call("test")
        mock_training.assert_called_once()

    def test_weather_and_downstream_steps_still_run_when_smard_range_fails(self):
        # SMARD and weather batching each have their own try/except, so a failure
        # fetching the whole SMARD range must not skip the weather fetch, nor the
        # downstream load/dbt/training steps.
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 3, tzinfo=timezone.utc)
        with patch("orchestration.run_pipeline.run_smard_range", side_effect=RuntimeError("boom")), \
             patch("orchestration.run_pipeline.run_weather_range") as mock_weather, \
             patch("orchestration.run_pipeline.load_range") as mock_load_range, \
             patch("orchestration.run_pipeline.run_dbt") as mock_dbt, \
             patch("orchestration.run_pipeline.run_model_training") as mock_training:
            run_pipeline.run_historical_pipeline(start, end)  # must not raise

        mock_weather.assert_called_once()
        mock_load_range.assert_called_once()
        mock_dbt.assert_any_call("run")
        mock_dbt.assert_any_call("test")
        mock_training.assert_called_once()

    def test_end_date_is_clamped_to_yesterday_when_given_a_future_date(self):
        # Regression guard: a requested end date at or after "today" must not
        # balloon into fetching thousands of days (previously a `max()` vs `min()`
        # bug caused exactly that).
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        far_future_end = datetime(2099, 1, 1, tzinfo=timezone.utc)
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        with patch("orchestration.run_pipeline.run_smard_range") as mock_smard, \
             patch("orchestration.run_pipeline.run_weather_range") as mock_weather, \
             patch("orchestration.run_pipeline.load_range") as mock_load_range, \
             patch("orchestration.run_pipeline.run_dbt"), \
             patch("orchestration.run_pipeline.run_model_training"):
            run_pipeline.run_historical_pipeline(start, far_future_end)

        assert mock_smard.call_args.args[1].date() == yesterday
        assert mock_weather.call_args.args[1].date() == yesterday
        loaded_end = mock_load_range.call_args.args[1]
        assert loaded_end.date() == yesterday


# ── run_model_training ───────────────────────────────────────────────────────

class TestRunModelTraining:
    def test_loads_features_and_trains_both_models(self):
        raw = pd.DataFrame({"a": [1]})
        with patch("orchestration.run_pipeline.load_ml_features", return_value=raw) as mock_load, \
             patch("orchestration.run_pipeline.start_generation_model_training") as mock_gen, \
             patch("orchestration.run_pipeline.start_price_model_training") as mock_price:
            run_pipeline.run_model_training()
        mock_load.assert_called_once()
        mock_gen.assert_called_once_with(raw)
        mock_price.assert_called_once_with(raw)


# ── get_dates ─────────────────────────────────────────────────────────────────

class TestGetDates:
    def test_raises_when_start_date_missing(self):
        args = SimpleNamespace(start_date=None, end_date=None)
        with pytest.raises(ValueError, match="Start date cannot be empty"):
            run_pipeline.get_dates(args)

    def test_defaults_end_date_to_today(self):
        args = SimpleNamespace(start_date="2020-01-01", end_date=None)
        start, end = run_pipeline.get_dates(args)
        assert start == datetime(2020, 1, 1, tzinfo=timezone.utc)
        assert end == datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    def test_raises_when_end_date_equals_start_date(self):
        args = SimpleNamespace(start_date="2024-01-15", end_date="2024-01-15")
        with pytest.raises(ValueError, match="End date cannot be smaller"):
            run_pipeline.get_dates(args)

    def test_raises_when_end_date_before_start_date(self):
        args = SimpleNamespace(start_date="2024-01-15", end_date="2024-01-10")
        with pytest.raises(ValueError, match="End date cannot be smaller"):
            run_pipeline.get_dates(args)

    def test_parses_explicit_range(self):
        args = SimpleNamespace(start_date="2024-01-01", end_date="2024-01-31")
        start, end = run_pipeline.get_dates(args)
        assert start == datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert end == datetime(2024, 1, 31, tzinfo=timezone.utc)
