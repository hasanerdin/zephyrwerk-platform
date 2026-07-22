import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status

from ml.s3_model_io import load_pipeline
from ml.training_utils import ModelType

logger = logging.getLogger(__name__)


class MLModel:
    def __init__(self, model_type: ModelType):
        self.model_type = model_type
        self.pipeline, self.metadata = load_pipeline(model_type)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic: Load models
    models: dict[ModelType, MLModel] = {}
    for model_type in ModelType:
        try:
            models[model_type] = MLModel(model_type)
        except Exception as e:
            logger.error(f"Failed to load {model_type.value}: {e}")

    app.state.models = models

    yield

    app.state.models.clear()


def _get_model_or_503(request: Request, model_type: ModelType) -> MLModel:
    model = request.app.state.models.get(model_type)
    if model is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"{model_type.value} model not available.")

    return model


def get_price_model(request: Request) -> MLModel:
    return _get_model_or_503(request, ModelType.PRICE)


def get_wind_model(request: Request) -> MLModel:
    return _get_model_or_503(request, ModelType.WIND)


def get_solar_model(request: Request) -> MLModel:
    return _get_model_or_503(request, ModelType.SOLAR)