from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Connection

from api.schemas.responses import (
    DayAheadResponse,
    EnergyGenerationResponse,
    EnergySummaryResponse,
    NeighbourPriceResponse,
)
from api.services.data_services import (
    get_day_ahead_prices,
    get_energy_summary,
    get_generated_energy,
    get_neighbour_prices,
)
from db.deps import get_db

router = APIRouter(prefix="/energy", tags=["energy"])

@router.get("/summary", response_model=EnergySummaryResponse)
def get_summary(target_date: date,
                db: Annotated[Connection, Depends(get_db)]) -> EnergySummaryResponse:
    return get_energy_summary(db, target_date)


@router.get("/generation", response_model=EnergyGenerationResponse)
def get_generations(db: Annotated[Connection, Depends(get_db)],
                    start_date: date | None = Query(default=None, description="Filter from this date (YYYY-MM-DD)"),
                    end_date: date | None = Query(default=None, description="Filter up to this date (YYYY-MM-DD)"),
                    source: str | None = Query(default=None, 
                                               description="Source name ('wind_onshore_mw', 'solar_mw' etc.)")
                    ) -> EnergyGenerationResponse:
    try:
        return get_generated_energy(db, start_date, end_date, source)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e)
        )
    
@router.get("/prices", response_model=DayAheadResponse)
def get_day_ahead(db: Annotated[Connection, Depends(get_db)],
                  start_date: date | None = Query(default=None, description="Filter from this date (YYYY-MM-DD)"),
                  end_date: date | None = Query(default=None, description="Filter up to this date (YYYY-MM-DD)")
                ) -> DayAheadResponse:
    return get_day_ahead_prices(db, start_date, end_date)

@router.get("/price-spreads", response_model=NeighbourPriceResponse)
def get_price_spreads(db: Annotated[Connection, Depends(get_db)],
                    start_date: date | None = Query(default=None, description="Filter from this date (YYYY-MM-DD)"),
                    end_date: date | None = Query(default=None, description="Filter up to this date (YYYY-MM-DD)"),
                    source: str | None = Query(default=None,
                                        description="Neighbour country code ('FRANCE', 'AUSTRIA', 'DENMARK_1' etc.)")
                  ) -> NeighbourPriceResponse:
    try:
        return get_neighbour_prices(db, start_date, end_date, source)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e)
        )
