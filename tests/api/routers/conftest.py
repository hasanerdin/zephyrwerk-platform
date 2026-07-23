from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.deps import get_db
from ml.training_utils import ModelType


class _StubMLModel:
    """
    Stand-in for MLModel that skips the real S3-backed pipeline load
    (MLModel.__init__ calls ml.s3_model_io.load_pipeline). Only the
    attributes the routers actually read (.pipeline, .metadata, .model_type)
    are provided.

    metadata is populated with every field ModelResponse requires (not just
    trained_at) so the performance router's happy path -- ModelResponse(**model.metadata)
    -- works against this stub without each test having to fill in the rest.
    """

    def __init__(self, model_type: ModelType, trained_at: str = "2024-01-01T00:00:00Z"):
        self.model_type = model_type
        self.pipeline = MagicMock()
        self.metadata = {
            "model": f"{model_type.value}_forecast",
            "trained_at": trained_at,
            "n_train": 1000,
            "n_test": 200,
            "train_window": {"start": "2023-01-01", "end": "2023-06-01"},
            "test_window": {"start": "2023-06-01", "end": "2023-07-01"},
            "cv_mae_mean": 1.5,
            "cv_mae_std": 0.2,
            "cv_mae_per_fold": [1.4, 1.5, 1.6],
            "hyperparameters": {},
            "n_features": 10,
            "holdout": {"mae": 1.5, "rmse": 2.0, "r2": 0.9},
            "baseline_persistence": {"mae": 2.5, "rmse": 3.0, "r2": 0.7, "directional_accuracy": 0.6},
        }


@pytest.fixture
def make_client():
    """
    Builds a TestClient(app) without running the app's real lifespan (which
    would hit S3 to load models and a real Postgres via get_db). Used as a
    plain object rather than `with TestClient(app) as c:` specifically so the
    lifespan startup/shutdown never fires; app.state.models and the get_db
    dependency are populated by hand instead.

    missing_model_types: ModelType members to leave out of app.state.models,
        to exercise the 503 "model not available" paths.
    db: object yielded by the overridden get_db dependency. Defaults to a
        bare MagicMock (routers under test here call into a mocked service
        layer, so the db object itself is normally just passed through
        unused).
    """

    def _make(missing_model_types=(), db=None):
        resolved_db = db if db is not None else MagicMock()

        app.state.models = {
            model_type: _StubMLModel(model_type)
            for model_type in ModelType
            if model_type not in missing_model_types
        }

        def _override_get_db():
            yield resolved_db

        app.dependency_overrides[get_db] = _override_get_db

        return TestClient(app)

    yield _make

    app.dependency_overrides.clear()
    app.state.models = {}


@pytest.fixture
def client(make_client):
    """A TestClient with all three models present and a working (mocked) db."""
    return make_client()
