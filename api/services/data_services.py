from datetime import date

from sqlalchemy import Connection

from api.repositories.energy_repository import (
    query_avg_price,
    query_day_ahead_prices,
    query_generation_mix,
    query_generation_sources,
)
from api.schemas.responses import (
    DayAheadPrice,
    DayAheadResponse,
    EnergyGeneration,
    EnergyGenerationResponse,
    EnergySummaryResponse,
)
from ml.energy_sources import RENEWABLE_SOURCE_COLUMNS


def get_energy_summary(db: Connection, target_date: date) -> EnergySummaryResponse:
    avg_price = query_avg_price(db, target_date)

    generation_mix = query_generation_mix(db, target_date)
    renewable_share = None
    if generation_mix:
        total_generation = sum(generation_mix.values())
        total_renewable = sum(value for source, value in generation_mix.items() if source in RENEWABLE_SOURCE_COLUMNS)
        renewable_share = (total_renewable / total_generation * 100) if total_generation else 0.0

    return EnergySummaryResponse(target_date=target_date,
                         generation_mix=generation_mix,
                         avg_price=avg_price,
                         renewable_share=renewable_share)


def get_generated_energy(
    db: Connection, start_date: date | None, end_date: date | None, source: str | None
) -> EnergyGenerationResponse:
    energy_by_sources = query_generation_sources(db, start_date, end_date, source)

    results = [
        EnergyGeneration(timestamp=row["timestamp"], source=column, value=value)
        for row in energy_by_sources
        for column, value in row.items()
        if column != "timestamp"
    ]

    return EnergyGenerationResponse(start_date=start_date,
                            end_date=end_date,
                            source=source,
                            generated_energy=results)


def get_day_ahead_prices(db: Connection, start_date: date | None, end_date: date | None) -> DayAheadResponse:
    day_ahead_prices = query_day_ahead_prices(db, start_date, end_date)

    results = [DayAheadPrice(timestamp=price["timestamp"],
                             price=price["price_eur_mwh"]) 
                             for price in day_ahead_prices]
    
    return DayAheadResponse(start_date=start_date,
                            end_date=end_date,
                            prices=results)

