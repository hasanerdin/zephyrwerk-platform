from datetime import date
from typing import Any

from sqlalchemy import Connection, text

from ml.energy_sources import GENERATION_SOURCE_COLUMNS


def _add_date_range_filter(params: dict[str, Any], start_date: date | None, end_date: date | None) -> str:
    """Build the ` AND timestamp ...` clauses for a date range, registering bind params."""
    clauses = []
    if start_date is not None:
        clauses.append("timestamp >= :start_date")
        params["start_date"] = start_date
    if end_date is not None:
        clauses.append("timestamp <= :end_date")
        params["end_date"] = end_date
    return "".join(f" AND {clause}" for clause in clauses)


def query_generation_sources(
    db: Connection, start_date: date | None, end_date: date | None, source: str | None
) -> list[dict[str, Any]]:
    if source and source not in GENERATION_SOURCE_COLUMNS:
        raise ValueError(f"Unknown generation source '{source}'. Valid sources: {sorted(GENERATION_SOURCE_COLUMNS)}")

    columns = source if source else ", ".join(GENERATION_SOURCE_COLUMNS)
    query = f"SELECT timestamp, {columns} FROM analytics.fct_energy_generation WHERE 1=1"

    params: dict[str, Any] = {}
    query += _add_date_range_filter(params, start_date, end_date)
    query += " ORDER BY timestamp DESC"

    result = db.execute(text(query), params)
    return [dict(row._mapping) for row in result.fetchall()]


def query_day_ahead_prices(db: Connection, start_date: date | None, end_date: date | None) -> list[dict[str, Any]]:
    query = "SELECT timestamp, price_eur_mwh FROM analytics.fct_market_prices WHERE 1=1"

    params: dict[str, Any] = {}
    query += _add_date_range_filter(params, start_date, end_date)
    query += " ORDER BY timestamp DESC"

    result = db.execute(text(query), params).fetchall()
    return [dict(row._mapping) for row in result]


def query_generation_mix(db: Connection, target_date: date) -> dict[str, float]:
    """Average MW per generation source for a single day. Pure SQL aggregation, no domain logic."""
    aggregates = ", ".join(f"AVG({col}) AS {col}" for col in GENERATION_SOURCE_COLUMNS)
    query = (
        f"SELECT {aggregates} FROM analytics.fct_energy_generation "
        "WHERE timestamp::date = :target_date"
    )
    row = db.execute(text(query), {"target_date": target_date}).mappings().one()
    return {col: value for col, value in row.items() if value is not None}


def query_avg_price(db: Connection, target_date: date) -> float | None:
    query = (
        "SELECT AVG(price_eur_mwh) AS avg_price FROM analytics.fct_market_prices "
        "WHERE timestamp::date = :target_date"
    )
    return db.execute(text(query), {"target_date": target_date}).scalar()
