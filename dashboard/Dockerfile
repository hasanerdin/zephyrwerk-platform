FROM python:3.12-slim

WORKDIR /app

# Dashboard has its own requirements.txt (not pyproject.toml) — the shared
# dependency list carries ml/api/ingestion-only packages (xgboost, boto3,
# sqlalchemy, ...) that this image has no use for.
COPY dashboard/requirements.txt ./dashboard/requirements.txt
RUN pip install --no-cache-dir -r dashboard/requirements.txt

# Copy application source
COPY dashboard/ ./dashboard/

# dashboard/ has no __init__.py (implicit namespace package); pages import
# via "from dashboard.xxx import ..." so /app must be on the import path.
ENV PYTHONPATH=/app

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health').status == 200 else 1)"

CMD ["streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
