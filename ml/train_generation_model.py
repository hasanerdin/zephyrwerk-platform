import logging
from datetime import datetime, timezone

import pandas as pd
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.pipeline import Pipeline

from ml.data_access import load_ml_features
from ml.features.feature_engineering import GenerationModelFeatureEngineer, split_x_y, temporal_split
from ml.s3_model_io import save_pipeline
from ml.training_utils import (
    ModelType,
    create_ml_model,
    create_preprocessor,
    draw_predictions,
    filter_raw_data,
    save_report,
    test_model,
)

logger = logging.getLogger(__name__)

def train_generation_model( raw: pd.DataFrame, mode: ModelType) -> None:
    """
    Train a generation model (wind or solar) and save the report to a JSON file.

    Args:
        raw (pd.DataFrame): Raw features DataFrame.
        mode (ModelType): Target variable, either ModelType.WIND or ModelType.SOLAR.
    """
    report = {"model": f"{mode.value}_forecast", "trained_at": datetime.now(timezone.utc).isoformat()}

    X_raw, y_raw = split_x_y(raw, mode)

    X_raw, y = filter_raw_data(X_raw, y_raw, mode)

    X_trainval, X_test, y_trainval, y_test = temporal_split(X_raw, y, holdout_days=90)
    
    report["n_train"] = len(X_trainval)
    report["n_test"] = len(X_test)
    report["train_window"] = {"start": str(X_trainval.index.min()), "end": str(X_trainval.index.max())}
    report["test_window"] = {"start": str(X_test.index.min()), "end": str(X_test.index.max())}

    preprocessor = create_preprocessor()
    model = create_ml_model()

    pipeline = Pipeline([
        ("engineer", GenerationModelFeatureEngineer()),
        ("preprocess", preprocessor),
        ("model", model),
    ])

    tscv = TimeSeriesSplit(n_splits=5, gap=24)

    cv_scores = cross_val_score(
        pipeline, X_trainval, y_trainval,
        cv=tscv, scoring="neg_mean_absolute_error", n_jobs=1,
    )
    cv_mae = -cv_scores  # sklearn returns negatives for consistency across scorers
    report["cv_mae_mean"] = float(cv_mae.mean())
    report["cv_mae_std"] = float(cv_mae.std())
    report["cv_mae_per_fold"] = cv_mae.tolist()

    pipeline.fit(X_trainval, y_trainval)
    report["hyperparameters"] = model.get_params()
    report["n_features"] = pipeline.named_steps["model"].n_features_in_


    y_pred = pipeline.predict(X_test)
    test_baseline_pred = raw["solar_mw" if mode == ModelType.SOLAR else "wind_total_mw"].shift(24).loc[X_test.index]

    holdout_report, baseline_report = test_model(y_pred, y_test, test_baseline_pred, mode=mode)
    report["holdout"] = holdout_report
    report["baseline_persistence"] = baseline_report

    save_report(report, mode=mode)
    draw_predictions(y_pred, y_test, mode=mode)

    # Save the trained model to S3 with metadata
    s3_uri = save_pipeline(pipeline, model_type=mode, metadata=report)
    logger.info(f"Model saved to {s3_uri}")

def start_generation_model_training(raw: pd.DataFrame = None):
    """
    Start the training of generation models for wind and solar using the full history of data.
    """
    train_generation_model(raw, ModelType.WIND)
    train_generation_model(raw, ModelType.SOLAR)


if __name__ == "__main__":
    raw = load_ml_features(start_date="2019-01-01")   # generation model uses full history
    start_generation_model_training(raw)
