from datetime import datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas.requests import PredictionRequest
from api.schemas.responses import GenerationPrediction, GenerationResponse, HourlyPrediction, PriceResponse
from api.services.model_loader import MLModel, get_price_model, get_solar_model, get_wind_model
from api.services.prediction_service import ForecastDataUnavailable, predict

router = APIRouter(prefix="/predict", tags=["predict"])

@router.post("/price", response_model=PriceResponse)
def predict_price(body: PredictionRequest,
                  model: Annotated[MLModel, Depends(get_price_model)]) -> PriceResponse:
    try:
        predictions = predict(model, body.target_date)
    except ForecastDataUnavailable as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    if body.hour is not None:
        exact_datetime = datetime.combine(body.target_date, time(body.hour), tzinfo=timezone.utc)
        if exact_datetime not in predictions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Requested hour is not found in the predicted values: {exact_datetime}")
        results = [HourlyPrediction(hour=body.hour, 
                                    value=predictions[exact_datetime])]
    else:
        results = [HourlyPrediction(hour=dt.hour, value=price) for dt, price in predictions.items()]
    
    return PriceResponse(
        target_date=body.target_date,
        hour=body.hour,
        prices=results,
        model_trained_at=model.metadata.get("trained_at")
    )        

@router.post("/generation", response_model=GenerationResponse)
def predict_generation(body: PredictionRequest, 
                       solar_model: Annotated[MLModel, Depends(get_solar_model)],
                       wind_model: Annotated[MLModel, Depends(get_wind_model)]) -> GenerationResponse:
    try:
        solar_predictions = predict(solar_model, body.target_date)
        wind_predictions = predict(wind_model, body.target_date)
    except ForecastDataUnavailable as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    if body.hour is not None:
        exact_datetime = datetime.combine(body.target_date, time(body.hour), tzinfo=timezone.utc)
        if exact_datetime not in solar_predictions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Requested hour is not found in the predicted solar values: {exact_datetime}")
        
        if exact_datetime not in wind_predictions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Requested hour is not found in the predicted wind values: {exact_datetime}")
        
        solar_results = [HourlyPrediction(hour=body.hour, 
                                          value=solar_predictions[exact_datetime])]
        wind_results = [HourlyPrediction(hour=body.hour, 
                                         value=wind_predictions[exact_datetime])]
    else:
        solar_results = [HourlyPrediction(hour=dt.hour, value=sg) for dt, sg in solar_predictions.items()]
        wind_results = [HourlyPrediction(hour=dt.hour, value=wg) for dt, wg in wind_predictions.items()]
    
    return GenerationResponse(
        target_date=body.target_date,
        hour=body.hour,
        solar_generations=GenerationPrediction(generations=solar_results, 
                                               model_trained_at=solar_model.metadata.get("trained_at")),
        wind_generations=GenerationPrediction(generations=wind_results,
                                              model_trained_at=wind_model.metadata.get("trained_at"))
    )