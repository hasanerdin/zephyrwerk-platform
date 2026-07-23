from datetime import date

from sqlalchemy import Connection

from api.repositories.energy_repository import (
    query_avg_price,
    query_day_ahead_prices,
    query_generation_mix,
    query_generation_sources,
    query_neighbour_prices
)
from api.schemas.responses import (
    DayAheadPrice,
    DayAheadResponse,
    EnergyGeneration,
    EnergyGenerationResponse,
    EnergySummaryResponse,
    NeighbourPrice,
    NeighbourPriceResponse
)
from ml.energy_sources import NEIGHBOUR_SOURCES, RENEWABLE_SOURCE_COLUMNS


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


def get_generated_energy(db: Connection, 
                         start_date: date | None, 
                         end_date: date | None, 
                         source: str | None
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


def get_neighbour_prices(db: Connection,
                         start_date: date | None,
                         end_date: date | None,
                         source: str | None
                        ) -> NeighbourPriceResponse:
    neighbour_prices_by_source = query_neighbour_prices(db, start_date, end_date, source)

    neighbours = [source] if source else NEIGHBOUR_SOURCES

    results = [
        NeighbourPrice(timestamp=row["timestamp"],
                       source=neighbour,
                       price=row[f"{neighbour.lower()}_price_eur_mwh"],
                       spread=row[f"{neighbour.lower()}_spread_eur_mwh"])
        for row in neighbour_prices_by_source
        for neighbour in neighbours
    ]

    return NeighbourPriceResponse(start_date=start_date,
                                  end_date=end_date,
                                  source=source,
                                  neighbour_prices=results)
