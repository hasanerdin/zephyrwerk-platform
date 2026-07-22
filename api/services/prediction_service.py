from datetime import date, datetime, time, timedelta, timezone

import pandas as pd

from api.services.model_loader import MLModel
from ml.data_access import load_ml_features, load_weather_forecast
from ml.features.feature_engineering import LAG_HORIZONS, LEAKING_GEN_COLS, split_x_y

# dbt only populates these from realized prices (fct_market_prices), so every
# forecast-horizon row starts out NaN here — fct_weather_forecast_features has
# no price data at all. PriceModelFeatureEngineer reads price_24h_lag/48h/168h
# as pre-existing columns and never shifts them itself (feature_engineering.py),
# so the fallback has to be computed here, before the pipeline runs.
PRICE_LAG_HORIZONS = [24, 48, 168]


class ForecastDataUnavailable(Exception):
    """
    Raised when fct_weather_forecast_features has no usable rows for the
    requested target_date (daily pipeline hasn't run yet, or ran but left
    the forecast columns null). Callers should turn this into a 503 rather
    than letting the missing data surface as a downstream TypeError from
    the feature pipeline (e.g. np.sin() on a null forecast column).
    """


def _lag_with_fallback(series: pd.Series, horizons: list[int]) -> pd.Series:
    """
    Positional lag with cascading fallback to the next-longest horizon
    whenever the shorter one's source row hasn't happened yet (i.e. is
    itself NaN). Complete as long as the longest horizon lands inside the
    historical buffer — get_inference_data keeps a fixed 7-day (168h)
    buffer for exactly this reason, so this is only safe when target_date
    is within 7 days of now.
    """
    result = series.shift(horizons[0])
    for h in horizons[1:]:
        result = result.fillna(series.shift(h))
    return result


def get_inference_data(target_date: date) -> pd.DataFrame:
    # The buffer's end anchors to the actual current moment, not midnight of
    # today: by the time this runs, hours 00:00..now already have real rows
    # in fct_ml_features (subject to ingestion lag), and truncating to
    # midnight would throw those away and force the forecast fetch to cover
    # them with forecast-only data instead.
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start_day = now - timedelta(days=7)

    target_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    target_end = target_start + timedelta(hours=23)

    # Buffer's end and the forecast's start are both inclusive bounds, so
    # starting the forecast an hour later avoids double-counting `now` — a
    # duplicate row there would throw off every positional shift()-based lag
    # feature computed downstream.
    buffer_features = load_ml_features(start_day, now)
    weather_forecast = load_weather_forecast(now + timedelta(hours=1), target_end)

    features = pd.concat([buffer_features, weather_forecast]).sort_index()
    features = features[~features.index.duplicated(keep="first")]

    target_mask = (features.index >= target_start) & (features.index <= target_end)
    target_rows = features.loc[target_mask]

    forecast_cols = [c for c in weather_forecast.columns if c in target_rows.columns]
    incomplete = len(target_rows) < 24 or (
        forecast_cols and target_rows[forecast_cols].isna().all().all()
    )
    if incomplete:
        raise ForecastDataUnavailable(
            f"Weather forecast data not yet available for {target_date} — "
            "check that the daily pipeline has run."
        )

    return features


def _patch_price_lags(features: pd.DataFrame) -> pd.DataFrame:
    """Overwrite dbt's price_24h_lag/48h/168h with fallback-aware versions computed from price_eur_mwh."""
    features = features.copy()
    features["price_24h_lag"] = _lag_with_fallback(features["price_eur_mwh"], PRICE_LAG_HORIZONS)
    features["price_48h_lag"] = _lag_with_fallback(features["price_eur_mwh"], PRICE_LAG_HORIZONS[1:])
    features["price_168h_lag"] = features["price_eur_mwh"].shift(PRICE_LAG_HORIZONS[-1])
    return features


def _patch_generation_lags(features: pd.DataFrame, pipeline) -> pd.DataFrame:
    """
    Run the pipeline's own feature engineer, then backfill each `{col}_lag_24`
    with `{col}_lag_168` wherever the 24h source row is itself unrealized.
    Done post-transform (not by pre-seeding raw columns) because add_lags()
    always recomputes `{col}_lag_h` from the raw current-hour column via
    .shift(), ignoring any pre-existing lag column of the same name.
    """
    engineered = pipeline.named_steps["engineer"].transform(features)
    shortest, longest = LAG_HORIZONS[0], LAG_HORIZONS[-1]
    for col in LEAKING_GEN_COLS:
        short_col, long_col = f"{col}_lag_{shortest}", f"{col}_lag_{longest}"
        if short_col in engineered.columns and long_col in engineered.columns:
            engineered[short_col] = engineered[short_col].fillna(engineered[long_col])
    return engineered


def predict(ml_model: MLModel, target_date: date) -> dict[datetime, float]:
    features = get_inference_data(target_date)
    features = _patch_price_lags(features)
    features, _ = split_x_y(features, model_type=ml_model.model_type)

    pipeline = ml_model.pipeline
    engineered = _patch_generation_lags(features, pipeline)
    preprocessed = pipeline.named_steps["preprocess"].transform(engineered)
    preds = pipeline.named_steps["model"].predict(preprocessed)

    target_start = pd.Timestamp(datetime.combine(target_date, time.min, tzinfo=timezone.utc))
    if features.index.tz is None:
        target_start = target_start.tz_localize(None)
    target_end = target_start + pd.Timedelta(hours=23)
    target_mask = (features.index >= target_start) & (features.index <= target_end)

    return dict(zip(features.index[target_mask], preds[target_mask]))
