from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import api.services.prediction_service as prediction_service
from api.services.prediction_service import (
    PRICE_LAG_HORIZONS,
    ForecastDataUnavailable,
    _lag_with_fallback,
    _patch_generation_lags,
    _patch_price_lags,
    get_inference_data,
    predict,
)
from ml.features.feature_engineering import GenerationModelFeatureEngineer, PriceModelFeatureEngineer
from ml.training_utils import ModelType, create_preprocessor

TODAY = pd.Timestamp("2024-01-01", tz="UTC")


def _freeze_now(monkeypatch, now: pd.Timestamp) -> None:
    """Freeze prediction_service's `datetime.now()` at a fixed instant."""

    class _FrozenDatetime(prediction_service.datetime):
        @classmethod
        def now(cls, tz=None):
            return now.to_pydatetime()

    monkeypatch.setattr(prediction_service, "datetime", _FrozenDatetime)


def _buffer_and_forecast_series(today: pd.Timestamp, n_future_day: int) -> pd.Series:
    """
    A series shaped like get_inference_data's output: real (non-NaN) values for
    the 7-day historical buffer up to `today`, NaN for every not-yet-elapsed
    forecast hour after it — exactly the pattern that makes T-24h/T-48h lags
    land on unrealized rows near the start of the forecast horizon.
    """
    buffer_idx = pd.date_range(today - pd.Timedelta(days=7), today, freq="h", tz="UTC")
    forecast_idx = pd.date_range(
        today + pd.Timedelta(hours=1), today + pd.Timedelta(days=n_future_day), freq="h", tz="UTC"
    )
    idx = buffer_idx.append(forecast_idx)
    values = np.concatenate([
        np.arange(len(buffer_idx), dtype=float),
        np.full(len(forecast_idx), np.nan),
    ])
    return pd.Series(values, index=idx)


class TestLagWithFallback:
    def test_uses_shortest_horizon_when_its_source_is_realized(self):
        series = _buffer_and_forecast_series(TODAY, n_future_day=3)
        result = _lag_with_fallback(series, PRICE_LAG_HORIZONS)

        t = TODAY - pd.Timedelta(hours=1)  # deep in history: T-24h is real
        assert result.loc[t] == series.shift(24).loc[t]

    def test_falls_back_one_level_when_24h_source_is_unrealized(self):
        series = _buffer_and_forecast_series(TODAY, n_future_day=3)
        result = _lag_with_fallback(series, PRICE_LAG_HORIZONS)

        # T is early in the forecast window: T-24h lands after `today` (unrealized),
        # but T-48h lands back in the buffer (realized).
        t = TODAY + pd.Timedelta(hours=29)
        assert pd.isna(series.shift(24).loc[t])
        assert not pd.isna(series.shift(48).loc[t])

        assert not pd.isna(result.loc[t])
        assert result.loc[t] == series.shift(48).loc[t]

    def test_cascades_two_levels_when_24h_and_48h_sources_are_both_unrealized(self):
        series = _buffer_and_forecast_series(TODAY, n_future_day=3)
        result = _lag_with_fallback(series, PRICE_LAG_HORIZONS)

        # T further into the forecast window: both T-24h and T-48h are unrealized,
        # only T-168h lands back in the buffer.
        t = TODAY + pd.Timedelta(hours=53)
        assert pd.isna(series.shift(24).loc[t])
        assert pd.isna(series.shift(48).loc[t])
        assert not pd.isna(series.shift(168).loc[t])

        assert not pd.isna(result.loc[t])
        assert result.loc[t] == series.shift(168).loc[t]


class TestPatchPriceLags:
    def test_fills_price_24h_lag_at_the_forecast_boundary(self):
        price = _buffer_and_forecast_series(TODAY, n_future_day=3)
        features = pd.DataFrame({"price_eur_mwh": price})

        patched = _patch_price_lags(features)

        t_one_level = TODAY + pd.Timedelta(hours=29)
        assert not np.isnan(patched.loc[t_one_level, "price_24h_lag"])
        assert patched.loc[t_one_level, "price_24h_lag"] == price.shift(48).loc[t_one_level]

        t_two_levels = TODAY + pd.Timedelta(hours=53)
        assert not np.isnan(patched.loc[t_two_levels, "price_24h_lag"])
        assert patched.loc[t_two_levels, "price_24h_lag"] == price.shift(168).loc[t_two_levels]

    def test_price_168h_lag_has_no_fallback_and_stays_grounded_in_the_buffer(self):
        price = _buffer_and_forecast_series(TODAY, n_future_day=3)
        features = pd.DataFrame({"price_eur_mwh": price})

        patched = _patch_price_lags(features)

        t = TODAY + pd.Timedelta(hours=53)
        assert not np.isnan(patched.loc[t, "price_168h_lag"])
        assert patched.loc[t, "price_168h_lag"] == price.shift(168).loc[t]


class TestPatchGenerationLags:
    def test_fills_lag_24_with_lag_168_at_the_forecast_boundary(self):
        wind = _buffer_and_forecast_series(TODAY, n_future_day=3)
        features = pd.DataFrame({"wind_total_mw": wind})
        fake_pipeline = SimpleNamespace(named_steps={"engineer": GenerationModelFeatureEngineer()})

        engineered = _patch_generation_lags(features, fake_pipeline)

        t = TODAY + pd.Timedelta(hours=53)  # both lag_24 and its naive source are unrealized here
        assert not np.isnan(engineered.loc[t, "wind_total_mw_lag_24"])
        assert engineered.loc[t, "wind_total_mw_lag_24"] == engineered.loc[t, "wind_total_mw_lag_168"]

    def test_leaves_lag_24_untouched_when_its_source_is_realized(self):
        wind = _buffer_and_forecast_series(TODAY, n_future_day=3)
        features = pd.DataFrame({"wind_total_mw": wind})
        fake_pipeline = SimpleNamespace(named_steps={"engineer": GenerationModelFeatureEngineer()})

        engineered = _patch_generation_lags(features, fake_pipeline)

        t = TODAY - pd.Timedelta(hours=1)
        assert engineered.loc[t, "wind_total_mw_lag_24"] == wind.shift(24).loc[t]


def _fake_load_ml_features(start, end):
    idx = pd.date_range(start, end, freq="h", tz="UTC")
    return pd.DataFrame({"price_eur_mwh": np.arange(len(idx), dtype=float)}, index=idx)


def _fake_load_weather_forecast(start, end):
    idx = pd.date_range(start, end, freq="h", tz="UTC")
    return pd.DataFrame({"temperature_2m_bavaria": np.zeros(len(idx))}, index=idx)


class TestGetInferenceData:
    def test_no_duplicate_row_at_the_buffer_forecast_boundary(self, monkeypatch):
        monkeypatch.setattr(prediction_service, "load_ml_features", _fake_load_ml_features)
        monkeypatch.setattr(prediction_service, "load_weather_forecast", _fake_load_weather_forecast)
        _freeze_now(monkeypatch, TODAY)

        features = get_inference_data(target_date=(TODAY + pd.Timedelta(days=2)).date())

        assert not features.index.duplicated().any()
        assert features.index.is_monotonic_increasing

    def test_buffer_extends_through_already_elapsed_hours_of_today(self, monkeypatch):
        """
        Calling mid-afternoon should pull real data for today's already-elapsed
        hours into the buffer instead of truncating the buffer at midnight.
        """
        monkeypatch.setattr(prediction_service, "load_ml_features", _fake_load_ml_features)
        monkeypatch.setattr(prediction_service, "load_weather_forecast", _fake_load_weather_forecast)

        now = TODAY + pd.Timedelta(hours=14)
        _freeze_now(monkeypatch, now)

        features = get_inference_data(target_date=(TODAY + pd.Timedelta(days=1)).date())

        # Today's already-elapsed hours (00:00..14:00) come from the buffer
        # loader (which has price_eur_mwh), not the forecast loader (which
        # doesn't) — a NaN here would mean the buffer stopped at midnight.
        elapsed_hour = TODAY + pd.Timedelta(hours=10)
        assert elapsed_hour in features.index
        assert not np.isnan(features.loc[elapsed_hour, "price_eur_mwh"])

    def test_forecast_fills_gap_left_by_ml_features_ingestion_lag(self, monkeypatch):
        """
        fct_ml_features ingestion can lag well behind `now` — the buffer
        loader may only have real rows up through some earlier cutoff. The
        forecast fetch must start right after that cutoff (not after `now`),
        or the hours in between are missing from both sources even though
        fct_weather_forecast_features already covers them.
        """
        now = TODAY + pd.Timedelta(hours=12)
        ingestion_cutoff = TODAY - pd.Timedelta(hours=1)  # buffer is 13h behind `now`

        def _lagging_ml_features(start, end):
            idx = pd.date_range(start, min(end, ingestion_cutoff), freq="h", tz="UTC")
            return pd.DataFrame({"price_eur_mwh": np.arange(len(idx), dtype=float)}, index=idx)

        monkeypatch.setattr(prediction_service, "load_ml_features", _lagging_ml_features)
        monkeypatch.setattr(prediction_service, "load_weather_forecast", _fake_load_weather_forecast)
        _freeze_now(monkeypatch, now)

        features = get_inference_data(target_date=TODAY.date())

        gap_hour = TODAY + pd.Timedelta(hours=5)  # between ingestion_cutoff and now
        assert gap_hour in features.index
        assert not features.loc[gap_hour].isna().all()

    def test_raises_when_forecast_query_returns_no_rows_for_target_date(self, monkeypatch):
        """Daily pipeline hasn't run yet: the forecast loader returns nothing."""

        def _empty_forecast(start, end):
            return pd.DataFrame(
                columns=["temperature_2m_bavaria"], index=pd.DatetimeIndex([], tz="UTC")
            )

        monkeypatch.setattr(prediction_service, "load_ml_features", _fake_load_ml_features)
        monkeypatch.setattr(prediction_service, "load_weather_forecast", _empty_forecast)
        _freeze_now(monkeypatch, TODAY)

        with pytest.raises(ForecastDataUnavailable):
            get_inference_data(target_date=(TODAY + pd.Timedelta(days=1)).date())

    def test_raises_when_forecast_rows_exist_but_forecast_columns_are_all_null(self, monkeypatch):
        """Pipeline ran but left the forecast columns null (e.g. upstream weather API failure)."""

        def _null_forecast(start, end):
            idx = pd.date_range(start, end, freq="h", tz="UTC")
            return pd.DataFrame({"temperature_2m_bavaria": np.full(len(idx), np.nan)}, index=idx)

        monkeypatch.setattr(prediction_service, "load_ml_features", _fake_load_ml_features)
        monkeypatch.setattr(prediction_service, "load_weather_forecast", _null_forecast)
        _freeze_now(monkeypatch, TODAY)

        with pytest.raises(ForecastDataUnavailable):
            get_inference_data(target_date=(TODAY + pd.Timedelta(days=1)).date())


class _CaptureModel:
    """Stub final pipeline step that records whatever DataFrame reaches .predict()."""

    def __init__(self):
        self.last_X: pd.DataFrame | None = None

    def predict(self, X):
        self.last_X = X
        return np.zeros(len(X))


def _fit_price_pipeline() -> tuple[SimpleNamespace, _CaptureModel]:
    """
    A real (untrained-for-accuracy) price pipeline: real PriceModelFeatureEngineer
    and real ColumnTransformer/StandardScaler (fit on synthetic clean history), with
    a capture stub swapped in for the final XGBRegressor so the test can inspect
    exactly what reached "the model" without depending on real predictions.
    """
    train_idx = pd.date_range("2023-01-01", periods=400, freq="h", tz="UTC")
    train_frame = pd.DataFrame(
        {"price_eur_mwh": np.sin(np.arange(len(train_idx))) + 50.0},
        index=train_idx,
    )
    train_frame = _patch_price_lags(train_frame)
    train_frame = train_frame.drop(columns=["price_eur_mwh"])

    engineer = PriceModelFeatureEngineer()
    engineered_train = engineer.transform(train_frame).dropna()

    preprocess = create_preprocessor()
    preprocess.fit(engineered_train)

    model = _CaptureModel()
    pipeline = SimpleNamespace(named_steps={"engineer": engineer, "preprocess": preprocess, "model": model})
    return pipeline, model


def _fake_weather_forecast_no_columns(start, end):
    # PriceModelFeatureEngineer only needs the price lag columns for this test;
    # an empty-columns forecast frame keeps the schema identical to what the
    # preprocessor was fit on (temperature_2m_bavaria would otherwise be an
    # unseen column at transform time and trip ColumnTransformer's shape check).
    idx = pd.date_range(start, end, freq="h", tz="UTC")
    return pd.DataFrame(index=idx)


class TestPredictBoundaryFallback:
    def test_price_24h_lag_is_not_nan_for_a_target_hour_whose_t24_is_unrealized(self, monkeypatch):
        pipeline, model = _fit_price_pipeline()
        fake_ml_model = SimpleNamespace(pipeline=pipeline, model_type=ModelType.PRICE)

        monkeypatch.setattr(prediction_service, "load_ml_features", _fake_price_ml_features)
        monkeypatch.setattr(prediction_service, "load_weather_forecast", _fake_weather_forecast_no_columns)
        _freeze_now(monkeypatch, TODAY)

        target_hour = TODAY + pd.Timedelta(hours=53)  # 2-level fallback boundary case
        predict(fake_ml_model, target_date=target_hour.date())

        assert model.last_X is not None
        assert target_hour in model.last_X.index

        engineered_col = model.last_X.loc[target_hour, "price_24h_lag"]
        assert not np.isnan(engineered_col)


def _fake_price_ml_features(start, end):
    idx = pd.date_range(start, end, freq="h", tz="UTC")
    return pd.DataFrame({"price_eur_mwh": np.sin(np.arange(len(idx))) + 50.0}, index=idx)
