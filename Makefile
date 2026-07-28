.PHONY: help infra-up localstack-up postgres-up dbt-deps dbt-seed dbt-run dbt-test \
        pipeline-daily pipeline-weekly pipeline-historical

DBT := uv run dotenv run -- dbt

help:
	@echo "Local infrastructure:"
	@echo "  make infra-up             start LocalStack + Postgres and bootstrap both"
	@echo "  make localstack-up        start LocalStack, wait healthy, create the S3 bucket"
	@echo "  make postgres-up          start Postgres (db/init.sql creates schemas + zephyrwerk role)"
	@echo ""
	@echo "dbt (one-time setup, do this before the first pipeline run):"
	@echo "  make dbt-deps             install dbt_utils"
	@echo "  make dbt-seed             load German public holidays seed"
	@echo "  make dbt-run              build staging views + analytics tables (normally automatic, see below)"
	@echo "  make dbt-test             run dbt schema + singular tests (normally automatic, see below)"
	@echo ""
	@echo "Ingestion pipeline (dbt run/test happen automatically inside daily/historical):"
	@echo "  make pipeline-daily"
	@echo "  make pipeline-weekly"
	@echo "  make pipeline-historical START=2019-01-01 END=2025-12-31"

# LocalStack — S3 emulation. Pinned to 3.8: LocalStack 2026.x requires a
# paid license for S3 (fails with exit code 55); 3.8 is the last free one.
# Volume mount matters — the full historical backfill takes hours, and
# without it a container restart loses everything.
localstack-up:
	docker run --rm -d \
		-p 4566:4566 \
		-v localstack-data:/var/lib/localstack \
		--name localstack \
		localstack/localstack:3.8
	@echo "waiting for LocalStack..."
	until [ "$$(docker inspect -f '{{.State.Health.Status}}' localstack)" = "healthy" ]; do sleep 1; done
	aws --endpoint-url=http://localhost:4566 s3 mb s3://zephyrwerk-data-lake --region eu-central-1

# PostgreSQL — mounts db/init.sql, which creates the raw, staging,
# analytics schemas, all five raw tables (including weather_forecast),
# and the zephyrwerk app role (POSTGRES_USER below is only the
# container's bootstrap superuser). $(CURDIR) is this Makefile's own
# directory, so the mount path is correct regardless of where `make`
# was invoked from.
postgres-up:
	docker run -d \
		--name zephyrwerk-postgres \
		-p 5432:5432 \
		-e POSTGRES_USER=postgres \
		-e POSTGRES_PASSWORD=postgres \
		-e POSTGRES_DB=zephyrwerk \
		-v "$(CURDIR)/db/init.sql:/docker-entrypoint-initdb.d/init.sql" \
		postgres:16

infra-up: localstack-up postgres-up

dbt-deps:
	$(DBT) deps --project-dir dbt --profiles-dir dbt

dbt-seed:
	$(DBT) seed --project-dir dbt --profiles-dir dbt

dbt-run:
	$(DBT) run --project-dir dbt --profiles-dir dbt

dbt-test:
	$(DBT) test --project-dir dbt --profiles-dir dbt

pipeline-daily:
	uv run python orchestration/run_pipeline.py --mode daily

pipeline-weekly:
	uv run python orchestration/run_pipeline.py --mode weekly

# END is optional — run_pipeline.py's get_dates() defaults it to
# yesterday (clamped in run_historical_pipeline()) when omitted.
START ?= 2019-01-01
pipeline-historical:
	uv run python orchestration/run_pipeline.py --mode historical --start_date $(START) $(if $(END),--end_date $(END),)

run-api:
	uv run uvicorn api.main:app --reload
