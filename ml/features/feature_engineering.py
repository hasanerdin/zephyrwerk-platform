"""
ml/features/feature_engineering.py

Leak-safe feature engineering for the Zephyrwerk price and generation models.

Two sklearn-compatible transformers:
  - PriceModelFeatureEngineer: for the day-ahead price target (price_eur_mwh)
  - GenerationModelFeatureEngineer: for wind_total_mw or solar_mw targets

Both are shape-preserving (do not drop rows), so they compose cleanly inside
sklearn Pipelines. Row-dropping for lag NaN rows happens in the training
script, outside the pipeline.
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from ml.training_utils import ModelType

# ---- Column constants ----

TARGET_COLUMNS = {
    ModelType.PRICE: "price_eur_mwh",
    ModelType.WIND: "wind_total_mw",
    ModelType.SOLAR: "solar_mw",
}

# 14 current-hour generation/consumption signals — all leak against every target.
LEAKING_GEN_COLS = [
    "wind_total_mw",
    "wind_onshore_mw",
    "wind_offshore_mw",
    "solar_mw",
    "biomass_mw",
    "hydropower_mw",
    "pumped_storage_mw",
    "natural_gas_mw",
    "hard_coal_mw",
    "brown_coal_mw",
    #"nuclear_mw",
    "other_conventional_mw",
    "other_renewable_mw",
    "total_consumption_mw",
    "residual_load_mw",
]

# Current-hour price signals — unknown until the day-ahead auction clears.
# 1 DE/LU duplicate + 8 neighbours + 8 spreads = 17 columns.
LEAKING_PRICE_COLS = [
    "de_lu_price_eur_mwh",
    "austria_price_eur_mwh",
    "france_price_eur_mwh",
    "netherlands_price_eur_mwh",
    "poland_price_eur_mwh",
    "switzerland_price_eur_mwh",
    "czechia_price_eur_mwh",
    "denmark_1_price_eur_mwh",
    "denmark_2_price_eur_mwh",
    "austria_spread_eur_mwh",
    "france_spread_eur_mwh",
    "netherlands_spread_eur_mwh",
    "poland_spread_eur_mwh",
    "switzerland_spread_eur_mwh",
    "czechia_spread_eur_mwh",
    "denmark_1_spread_eur_mwh",
    "denmark_2_spread_eur_mwh",
]

# dbt's price_7d_rolling_avg window includes CURRENT ROW — leaky. Replace with
# a leak-free version built from price_24h_lag.
LEAKING_ROLLING_COL = "price_7d_rolling_avg"

# Price lag features from dbt — safe for price model, dropped for gen model.
PRICE_LAG_COLS = ["price_24h_lag", "price_48h_lag", "price_168h_lag"]

# Nuclear is ~75% NaN in the post-phase-out window; holiday_name is free text.
DROP_ALWAYS = ["nuclear_mw", "holiday_name", "date_day", "season"]

LAG_HORIZONS = [24, 168]

# Circular/cyclical columns and their periods, for sin/cos encoding.
CYCLICAL = {
    "wind_direction_100m_brandenburg": 360,
    "wind_direction_100m_schleswig": 360,
    "wind_direction_100m_bavaria": 360,
    "wind_direction_100m_bawue": 360,
    "hour_local": 24,
    "month": 12,
}


# ---- Pure helper functions ----

def add_lags(df: pd.DataFrame, cols: list[str], horizons: list[int]) -> pd.DataFrame:
    """Return df copy with `{col}_lag_{h}` columns for each present (col, h) pair."""
    df = df.copy()
    for col in cols:
        if col not in df.columns:
            continue
        for h in horizons:
            df[f"{col}_lag_{h}"] = df[col].shift(h)
    return df


def add_cyclical(df: pd.DataFrame, spec: dict[str, int]) -> pd.DataFrame:
    """Return df copy with `{col}_sin` and `{col}_cos` for each cyclical column."""
    df = df.copy()
    for col, period in spec.items():
        if col not in df.columns:
            continue
        radians = 2 * np.pi * df[col] / period
        df[f"{col}_sin"] = np.sin(radians)
        df[f"{col}_cos"] = np.cos(radians)
    return df


def _derive_hour_local(df: pd.DataFrame) -> pd.DataFrame:
    """Add `hour_local` (Europe/Berlin) from a UTC DatetimeIndex."""
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("Feature engineer expects a DatetimeIndex on input X")
    df = df.copy()
    df["hour_local"] = df.index.tz_convert("Europe/Berlin").hour
    return df


# ---- sklearn transformers ----

class PriceModelFeatureEngineer(BaseEstimator, TransformerMixin):
    """
    Feature transformer for the day-ahead price model.

    Expects `price_eur_mwh` (the target) to have been split out of X already
    via `split_x_y` before calling `transform`.
    """

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        df = X.copy()

        # Fill short gaps in residual_load_mw before lags reference it.
        if "residual_load_mw" in df.columns:
            df["residual_load_mw"] = df["residual_load_mw"].ffill(limit=3)

        # Derive local hour from the UTC DatetimeIndex.
        df = _derive_hour_local(df)

        # Leak-free 7-day rolling average of price, built from the 24h lag.
        if "price_24h_lag" in df.columns:
            df["price_rolling_avg_168h_leak_free"] = (
                df["price_24h_lag"].rolling(168, min_periods=1).mean()
            )

        # Lag current-hour generation, then sin/cos encode cyclical columns,
        # then drop all originals in one pass at the end.
        df = add_lags(df, LEAKING_GEN_COLS, LAG_HORIZONS)
        df = add_cyclical(df, CYCLICAL)

        to_drop = (
            LEAKING_GEN_COLS
            + LEAKING_PRICE_COLS
            + [LEAKING_ROLLING_COL]
            + DROP_ALWAYS
            + list(CYCLICAL)
        )
        return df.drop(columns=[c for c in to_drop if c in df.columns])


class GenerationModelFeatureEngineer(BaseEstimator, TransformerMixin):
    """
    Feature transformer for the wind and solar generation models.

    Drops all price-related columns: prices react to generation, not vice
    versa, so including them risks the model learning spurious relationships.
    Expects the target column (`wind_total_mw` or `solar_mw`) to have been
    split out of X before calling `transform`.
    """

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        df = X.copy()

        if "residual_load_mw" in df.columns:
            df["residual_load_mw"] = df["residual_load_mw"].ffill(limit=3)

        df = _derive_hour_local(df)

        df = add_lags(df, LEAKING_GEN_COLS, LAG_HORIZONS)
        df = add_cyclical(df, CYCLICAL)

        to_drop = (
            LEAKING_GEN_COLS
            + LEAKING_PRICE_COLS
            + [LEAKING_ROLLING_COL]
            + PRICE_LAG_COLS
            + ["price_eur_mwh"]
            + DROP_ALWAYS
            + list(CYCLICAL)
        )
        return df.drop(columns=[c for c in to_drop if c in df.columns])


# ---- Utilities ----

def split_x_y(df: pd.DataFrame, model_type: ModelType) -> tuple[pd.DataFrame, pd.Series]:
    """Separate target column from features."""
    target = TARGET_COLUMNS[model_type]
    if target not in df.columns:
        raise KeyError(f"target column '{target}' not found in DataFrame")
    return df.drop(columns=[target]), df[target].copy()


def temporal_split(X: pd.DataFrame, y: pd.Series, holdout_days: int = 90):
    """
    Time-based holdout split. Requires X to have a DatetimeIndex.
    Returns (X_trainval, X_test, y_trainval, y_test).
    """
    if len(X) != len(y):
        raise ValueError("X and y must have the same length")
    if not isinstance(X.index, pd.DatetimeIndex):
        raise TypeError("temporal_split requires a DatetimeIndex on X")
    cutoff = X.index.max() - pd.Timedelta(days=holdout_days)
    holdout_mask = X.index > cutoff
    return (
        X.loc[~holdout_mask],
        X.loc[holdout_mask],
        y.loc[~holdout_mask],
        y.loc[holdout_mask],
    )


# ---- Smoke test ----

if __name__ == "__main__":
    from ml.data_access import load_ml_features

    sample = load_ml_features(start_date="2023-04-16", end_date="2023-04-30")
    sample["wind_total_mw"] = sample["wind_onshore_mw"] + sample["wind_offshore_mw"]

    # Price model
    X_price_raw, y_price = split_x_y(sample, ModelType.PRICE)
    price_features = PriceModelFeatureEngineer().transform(X_price_raw)

    print("=== Price model ===")
    print("Shape:", price_features.shape)
    print("Target absent from features:", ModelType.PRICE.value not in price_features.columns)
    print("Feature columns:")
    for c in sorted(price_features.columns.tolist()):
        print(f"  {c}")

    # Wind generation model
    X_wind_raw, y_wind = split_x_y(sample, ModelType.WIND)
    wind_features = GenerationModelFeatureEngineer().transform(X_wind_raw)

    print("\n=== Wind generation model ===")
    print("Shape:", wind_features.shape)
    print("Target absent from features:", ModelType.WIND.value not in wind_features.columns)
    print("No price columns leaked:", not any("price" in c for c in wind_features.columns))
    print("Feature columns:")
    for c in sorted(wind_features.columns.tolist()):
        print(f"  {c}")