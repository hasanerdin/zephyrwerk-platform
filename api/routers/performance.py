from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from api.schemas.responses import ModelResponse
from api.services.model_loader import MLModel, get_price_model, get_solar_model, get_wind_model
from ml.training_utils import ModelType

router = APIRouter(prefix="/models", tags=["models"])

_MODEL_GETTERS = {
    ModelType.PRICE: get_price_model,
    ModelType.WIND: get_wind_model,
    ModelType.SOLAR: get_solar_model,
}

@router.get("/performance", response_model=ModelResponse)
def get_model_performance(model_type: str, request: Request) -> ModelResponse:
    try:
        model_type_enum = ModelType(model_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"There is no model typed {model_type}. Choose one of {[m.value for m in ModelType]}"
        )

    model: MLModel = _MODEL_GETTERS[model_type_enum](request)

    try:
        return ModelResponse(**model.metadata)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Performance report not available for the {model_type_enum.value} model."
        )

