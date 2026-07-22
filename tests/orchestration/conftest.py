import os

# Must run at import time (before any test module imports orchestration.run_pipeline,
# which transitively imports ml.data_access -> db.database, which eagerly
# instantiates Settings) rather than in a fixture. Mirrors tests/ml/conftest.py.
os.environ.setdefault("ZEPHYRWERK_RDS_HOST", "localhost")
os.environ.setdefault("ZEPHYRWERK_RDS_PORT", "5432")
os.environ.setdefault("ZEPHYRWERK_RDS_DB", "test_db")
os.environ.setdefault("ZEPHYRWERK_RDS_USER", "test_user")
os.environ.setdefault("ZEPHYRWERK_RDS_PASSWORD", "test_password")
os.environ.setdefault("AWS_REGION", "eu-central-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test_access_key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test_secret_key")
os.environ.setdefault("ZEPHYRWERK_AWS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("ZEPHYRWERK_SMARD_BASE_URL", "http://localhost/smard")
os.environ.setdefault("ZEPHYRWERK_OPENMETEO_FORECAST_URL", "http://localhost/forecast")
os.environ.setdefault("ZEPHYRWERK_OPENMETEO_HISTORY_URL", "http://localhost/history")
os.environ.setdefault("ZEPHYRWERK_API_HOST", "localhost")
os.environ.setdefault("ZEPHYRWERK_API_PORT", "8000")
os.environ.setdefault("ZEPHYRWERK_DASHBOARD_API_URL", "http://localhost:8000")
