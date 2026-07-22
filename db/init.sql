CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS raw.smard_generation(
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    signal TEXT NOT NULL,
    value DOUBLE PRECISION,
    unit TEXT,
    UNIQUE(timestamp, signal)
);

CREATE TABLE IF NOT EXISTS raw.smard_prices(
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    signal TEXT NOT NULL,
    value DOUBLE PRECISION,
    unit TEXT,
    UNIQUE(timestamp, signal)
);

CREATE TABLE IF NOT EXISTS raw.smard_neighbour_prices(
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    signal TEXT NOT NULL,
    value DOUBLE PRECISION,
    unit TEXT,
    UNIQUE(timestamp, signal)
);

CREATE TABLE IF NOT EXISTS raw.weather(
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    region TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    value DOUBLE PRECISION,
    unit TEXT,
    UNIQUE(timestamp, region, signal_type)
);

CREATE TABLE IF NOT EXISTS raw.weather_forecast(
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    region TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    value DOUBLE PRECISION,
    unit TEXT,
    fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE(timestamp, region, signal_type, fetched_at)
)