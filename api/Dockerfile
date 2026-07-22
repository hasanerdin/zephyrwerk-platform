FROM python:3.12-slim

WORKDIR /app

# pyproject.toml declares source packages, so source must exist before pip install
COPY pyproject.toml README.md ./

# Copy application source
COPY api/ ./api/
COPY ml/ ./ml/
COPY db/ ./db/

# Install build tools and project dependencies
RUN pip install --no-cache-dir .

# Default entrypoint
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
