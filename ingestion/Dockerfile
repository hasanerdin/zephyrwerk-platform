FROM python:3.12-slim

RUN useradd --create-home appuser

WORKDIR /app

# Copy dependency manifest first to leverage Docker layer caching
COPY pyproject.toml README.md ./
COPY ingestion/ ./ingestion/
COPY db/ ./db/

# Install build tools and project dependencies
RUN pip install --no-cache-dir .

USER appuser

# Default entrypoint
CMD ["python", "-m", "ingestion", "--task", "smard"]