import os

# Must run at import time (before any test module imports api.services.prediction_service,
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
