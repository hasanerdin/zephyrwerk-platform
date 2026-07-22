from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import Connection, text

from api.schemas.responses import HealthResponse
from db.deps import get_db
from ml.training_utils import ModelType

router = APIRouter(prefix="/health",tags=["health"])
@router.get("", response_model=HealthResponse)
def get_health_status(request: Request, db: Annotated[Connection, Depends(get_db)]) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}"
        )

    for model_type in ModelType:
        if request.app.state.models.get(model_type) is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"ML Model for {model_type.value} is not loaded correctly!"
            )
    
    return HealthResponse(status="healthy", 
                          timestamp=datetime.now(timezone.utc),
                          database="connected")
