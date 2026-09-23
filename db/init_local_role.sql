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