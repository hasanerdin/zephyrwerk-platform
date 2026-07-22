from datetime import date, datetime

from pydantic import BaseModel, Field


# ML MODEL POSTs
class HourlyPrediction(BaseModel):
    """A single hour's predicted value."""
    hour: int
    value: float


class PriceResponse(BaseModel):
    """Predicted day-ahead prices, optionally scoped to a single hour."""
    target_date: date
    hour: int | None = Field(default=None, ge=0, le=23, description="Hour of day (0-23)")
    prices: list[HourlyPrediction]
    model_trained_at: str | None = None

class GenerationPrediction(BaseModel):
    generations: list[HourlyPrediction]
    model_trained_at: str | None = None


class GenerationResponse(BaseModel):
    """Predicted solar and wind generation, optionally scoped to a single hour."""
    target_date: date
    hour: int | None = Field(default=None, ge=0, le=23, description="Hour of day (0-23)")
    solar_generations: GenerationPrediction
    wind_generations: GenerationPrediction


# ENERGY GETs
class EnergyGeneration(BaseModel):
    """Generated energy for a single source."""
    timestamp: datetime
    source: str
    value: float | None


class EnergyGenerationResponse(BaseModel):
    """Historical generation over a date range, optionally filtered to one source."""
    start_date: date | None
    end_date: date | None
    source: str | None = None
    generated_energy: list[EnergyGeneration]


class EnergySummaryResponse(BaseModel):
    """Generation mix, average price, and renewable share for a single day."""
    target_date: date
    generation_mix: dict[str, float]
    avg_price: float | None
    renewable_share: float | None


# PRICE GETs
class DayAheadPrice(BaseModel):
    """A single day-ahead market price observation."""
    timestamp: datetime
    price: float


class DayAheadResponse(BaseModel):
    """Historical day-ahead prices over a date range."""
    start_date: date | None
    end_date: date | None
    prices: list[DayAheadPrice]


# HEALTH GET
class HealthResponse(BaseModel):
    """Schema for health check response."""
    status: str
    timestamp: datetime
    database: str

