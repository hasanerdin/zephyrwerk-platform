FROM python:3.12-slim

RUN useradd --create-home appuser

WORKDIR /app

# Install dbt
RUN pip install --no-cache-dir dbt-core==1.11.11 dbt-postgres==1.10.1

# Copy dbt project
COPY dbt/ ./dbt/

WORKDIR /app/dbt

RUN dbt deps --profiles-dir .

RUN mkdir -p /app/dbt/logs /app/dbt/target
RUN chown -R appuser:appuser /app/dbt/logs /app/dbt/target

USER appuser

# Run dbt run then dbt test
CMD ["/bin/sh", "-c", "dbt run --profiles-dir . && dbt test --profiles-dir ."]