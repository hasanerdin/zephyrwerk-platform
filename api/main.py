import logging

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routers.energy import router as energy_router
from api.routers.health import router as health_router
from api.routers.performance import router as performance_router
from api.routers.predict import router as predict_router
from api.services.model_loader import lifespan as model_lifespan

load_dotenv()  # Load environment variables from .env file

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Zephyrwerk Platform",
    description="End-to-end platform for renewable energy generation and price prediction",
    version="0.6.0",
    lifespan=model_lifespan
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

app.include_router(predict_router)
app.include_router(energy_router)
app.include_router(health_router)
app.include_router(performance_router)
