"""Canonical generation source column names, shared across ml/ and api/."""

from enum import Enum


class SourceCategory(str, Enum):
    RENEWABLE = "renewable"
    FOSSIL = "fossil"
    NUCLEAR = "nuclear"
    STORAGE = "storage"

NEIGHBOUR_SOURCES = [
"AUSTRIA",
"FRANCE",
"NETHERLANDS",
"POLAND",
"SWITZERLAND",
"CZECHIA",
"DENMARK_1",
"DENMARK_2",
]

GENERATION_SOURCE_CATEGORIES: dict[str, SourceCategory] = {
    "wind_onshore_mw": SourceCategory.RENEWABLE,
    "wind_offshore_mw": SourceCategory.RENEWABLE,
    "solar_mw": SourceCategory.RENEWABLE,
    "biomass_mw": SourceCategory.RENEWABLE,
    "hydropower_mw": SourceCategory.RENEWABLE,
    "other_renewable_mw": SourceCategory.RENEWABLE,
    "natural_gas_mw": SourceCategory.FOSSIL,
    "hard_coal_mw": SourceCategory.FOSSIL,
    "brown_coal_mw": SourceCategory.FOSSIL,
    "other_conventional_mw": SourceCategory.FOSSIL,
    "nuclear_mw": SourceCategory.NUCLEAR,
    "pumped_storage_mw": SourceCategory.STORAGE,
}

GENERATION_SOURCE_COLUMNS = list(GENERATION_SOURCE_CATEGORIES)
RENEWABLE_SOURCE_COLUMNS = [
    col for col, category in GENERATION_SOURCE_CATEGORIES.items()
    if category == SourceCategory.RENEWABLE
]
