from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_validator


def _validate_prediction_horizon(value: date) -> date:
    today = datetime.now(timezone.utc).date()
    if value < today or value > today + timedelta(days=1):
        raise ValueError(
            f"target_date must be today or tomorrow, got {value}"
        )
    return value


class PredictionRequest(BaseModel):
    target_date: date
    hour: int | None = Field(default=None, ge=0, le=23, description="Hour of day (0-23)")

    @field_validator("target_date")
    @classmethod
    def target_date_must_be_within_horizon(cls, value: date) -> date:
        return _validate_prediction_horizon(value)
