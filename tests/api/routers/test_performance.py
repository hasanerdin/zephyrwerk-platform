import pytest

import api.routers.performance as performance_router
from ml.training_utils import ModelType

# _MODEL_GETTERS is built once at import time from the functions imported
# with `from api.services.model_loader import ...`, so it captures those
# function objects directly. Patching api.services.model_loader.get_price_model
# (or even performance_router.get_price_model) afterwards would NOT affect
# the endpoint -- the dict already holds the original reference. Faking a
# model getter for a test has to replace the dict entry itself:
# performance_router._MODEL_GETTERS[ModelType.X].


class TestModelPerformance:
    @pytest.mark.parametrize("model_type", ["price", "wind", "solar"])
    def test_valid_model_type_returns_200_with_expected_shape(self, client, model_type):
        response = client.get(f"/models/performance?model_type={model_type}")

        assert response.status_code == 200
        body = response.json()
        assert body["model"] == f"{model_type}_forecast"
        assert body["holdout"]["mae"] == 1.5
        assert body["baseline_persistence"]["directional_accuracy"] == 0.6

    def test_mounted_at_models_performance(self, client):
        # Regression guard: assert on the full path, not just "some 200 somewhere".
        response = client.get("/models/performance?model_type=price")
        assert response.status_code == 200

    def test_missing_model_type_query_param_returns_422(self, client):
        response = client.get("/models/performance")
        assert response.status_code == 422

    def test_invalid_model_type_returns_422_naming_valid_choices(self, client):
        # Regression guard: this previously returned 406 Not Acceptable, which
        # is reserved for Accept-header negotiation failures, not bad query
        # parameter values -- inconsistent with the 422 used elsewhere in the API.
        response = client.get("/models/performance?model_type=not_a_real_model")

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "not_a_real_model" in detail
        assert "price" in detail and "wind" in detail and "solar" in detail

    def test_missing_price_model_returns_503(self, make_client):
        client = make_client(missing_model_types=[ModelType.PRICE])

        response = client.get("/models/performance?model_type=price")

        assert response.status_code == 503
        assert "price" in response.json()["detail"].lower()

    def test_incomplete_metadata_returns_503_not_500(self, client, monkeypatch):
        # Regression guard: a model saved without a full training report
        # (ml.s3_model_io.save_pipeline allows metadata=None -> {}) previously
        # made ModelResponse(**model.metadata) raise an uncaught pydantic
        # ValidationError, surfacing as a generic 500 via the app's catch-all
        # exception handler instead of a clear, specific error.
        class _BareModel:
            metadata = {"trained_at": "2024-01-01T00:00:00Z"}

        monkeypatch.setitem(performance_router._MODEL_GETTERS, ModelType.PRICE, lambda request: _BareModel())

        response = client.get("/models/performance?model_type=price")

        assert response.status_code == 503
        assert "price" in response.json()["detail"].lower()
