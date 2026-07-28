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

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status == 200 else 1)"

# Default entrypoint
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
