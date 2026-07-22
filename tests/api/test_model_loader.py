import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api.services.model_loader as model_loader
from api.services.model_loader import (
    MLModel,
    _get_model_or_503,
    get_price_model,
    get_solar_model,
    get_wind_model,
    lifespan,
)
from ml.training_utils import ModelType

# lifespan() is an async context manager; no pytest-asyncio/anyio marker is
# configured for this project, so each test drives it with asyncio.run()
# around a small `async def _run():` body instead of using an async test fn.


def _fake_app():
    return SimpleNamespace(state=SimpleNamespace())


def _fake_request(models: dict):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(models=models)))


class TestMLModelInit:
    def test_unpacks_pipeline_and_metadata_from_load_pipeline(self, monkeypatch):
        fake_pipeline = object()
        fake_metadata = {"trained_at": "2024-01-01T00:00:00Z"}
        monkeypatch.setattr(model_loader, "load_pipeline", lambda model_type: (fake_pipeline, fake_metadata))

        model = MLModel(ModelType.PRICE)

        assert model.model_type == ModelType.PRICE
        assert model.pipeline is fake_pipeline
        assert model.metadata == fake_metadata

    def test_load_pipeline_failure_propagates_out_of_init(self, monkeypatch):
        # MLModel itself does not catch load failures -- lifespan() is the
        # thing responsible for turning a bad load into "just absent from
        # app.state.models" rather than a crashed __init__.
        def _raise(model_type):
            raise RuntimeError("s3 down")

        monkeypatch.setattr(model_loader, "load_pipeline", _raise)

        with pytest.raises(RuntimeError, match="s3 down"):
            MLModel(ModelType.PRICE)


class TestLifespan:
    def test_all_models_loading_successfully_populates_state_for_every_type(self, monkeypatch):
        monkeypatch.setattr(model_loader, "MLModel", lambda model_type: SimpleNamespace(model_type=model_type))
        app = _fake_app()

        async def _run():
            async with lifespan(app):
                assert set(app.state.models) == set(ModelType)

        asyncio.run(_run())

    def test_one_model_failing_to_load_is_caught_and_excluded_not_raised(self, monkeypatch, caplog):
        def _fake_ml_model(model_type):
            if model_type == ModelType.WIND:
                raise RuntimeError("s3 down")
            return SimpleNamespace(model_type=model_type)

        monkeypatch.setattr(model_loader, "MLModel", _fake_ml_model)
        app = _fake_app()

        async def _run():
            with caplog.at_level(logging.ERROR):
                async with lifespan(app):  # must not raise despite the WIND failure
                    assert ModelType.WIND not in app.state.models
                    assert ModelType.PRICE in app.state.models
                    assert ModelType.SOLAR in app.state.models

        asyncio.run(_run())
        assert "wind" in caplog.text.lower()

    def test_clears_state_models_on_shutdown(self, monkeypatch):
        monkeypatch.setattr(model_loader, "MLModel", lambda model_type: SimpleNamespace(model_type=model_type))
        app = _fake_app()

        async def _run():
            async with lifespan(app):
                assert len(app.state.models) == 3
            assert app.state.models == {}

        asyncio.run(_run())


class TestGetModelOr503:
    def test_returns_the_model_when_present(self):
        model = SimpleNamespace(model_type=ModelType.PRICE)
        request = _fake_request({ModelType.PRICE: model})

        assert _get_model_or_503(request, ModelType.PRICE) is model

    def test_raises_503_naming_the_model_type_when_missing(self):
        request = _fake_request({})

        with pytest.raises(HTTPException) as exc_info:
            _get_model_or_503(request, ModelType.PRICE)

        assert exc_info.value.status_code == 503
        assert "price" in exc_info.value.detail.lower()


class TestModelDependencyWrappers:
    def test_get_price_model_looks_up_the_price_key(self):
        model = SimpleNamespace(model_type=ModelType.PRICE)
        request = _fake_request({ModelType.PRICE: model})

        assert get_price_model(request) is model

    def test_get_wind_model_looks_up_the_wind_key(self):
        model = SimpleNamespace(model_type=ModelType.WIND)
        request = _fake_request({ModelType.WIND: model})

        assert get_wind_model(request) is model

    def test_get_solar_model_looks_up_the_solar_key(self):
        model = SimpleNamespace(model_type=ModelType.SOLAR)
        request = _fake_request({ModelType.SOLAR: model})

        assert get_solar_model(request) is model

    def test_get_wind_model_raises_503_when_only_price_is_present(self):
        # Guards against the three wrappers ever collapsing onto the wrong key.
        request = _fake_request({ModelType.PRICE: SimpleNamespace()})

        with pytest.raises(HTTPException) as exc_info:
            get_wind_model(request)

        assert exc_info.value.status_code == 503
        assert "wind" in exc_info.value.detail.lower()
