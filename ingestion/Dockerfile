FROM python:3.12-slim

RUN useradd --create-home appuser

WORKDIR /app

# Copy dependency manifest first to leverage Docker layer caching
COPY pyproject.toml README.md ./
COPY ingestion/ ./ingestion/
COPY orchestration/ ./orchestration/

# Install build tools and project dependencies
RUN pip install --no-cache-dir .

# Copy application source
COPY . .

USER appuser

# Default entrypoint
CMD ["python", "-m", "orchestration.run_pipeline"]