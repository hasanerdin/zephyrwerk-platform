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
);

-- App-level role the loader/dbt/API connect as (ZEPHYRWERK_RDS_USER in
-- .env). CREATE ROLE has no IF NOT EXISTS, hence the DO block. Password
-- must match ZEPHYRWERK_RDS_PASSWORD.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'zephyrwerk') THEN
    CREATE ROLE zephyrwerk LOGIN PASSWORD 'test';
  END IF;
END
$$;

GRANT ALL PRIVILEGES ON DATABASE zephyrwerk TO zephyrwerk;
GRANT ALL PRIVILEGES ON SCHEMA public, raw, staging, analytics TO zephyrwerk;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public, raw, staging, analytics TO zephyrwerk;
ALTER DEFAULT PRIVILEGES IN SCHEMA public, raw, staging, analytics GRANT ALL ON TABLES TO zephyrwerk;