import io

import boto3
import pandas as pd
import pytest
from moto import mock_aws

from ingestion.s3_uploader import get_file_name, upload_to_s3

BUCKET = "zephyrwerk-test-bucket"
REGION = "eu-central-1"
TEST_DATE = "2024-01-15"
EXPECTED_KEY = "raw/smard/year=2024/month=01/smard_2024_01_15.parquet"


@pytest.fixture
def fake_s3(monkeypatch):
    monkeypatch.setenv("ZEPHYRWERK_AWS_BUCKET_NAME", BUCKET)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)

    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        yield client


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "timestamp": pd.to_datetime([
            f"{TEST_DATE}T00:00:00Z",
            f"{TEST_DATE}T01:00:00Z",
            f"{TEST_DATE}T02:00:00Z",
            f"{TEST_DATE}T03:00:00Z",
        ], utc=True),
        "value": [45_200.0, 43_100.0, 41_800.0, 40_500.0],
        "signal": ["SOLAR"] * 4,
        "unit": ["MW"] * 4,
    })


def test_file_lands_at_correct_key(fake_s3, sample_df):
    upload_to_s3(sample_df)

    response = fake_s3.list_objects_v2(Bucket=BUCKET, Prefix="raw/smard/")
    keys = [obj["Key"] for obj in response.get("Contents", [])]

    assert EXPECTED_KEY in keys, f"Expected key {EXPECTED_KEY!r} not found; got {keys}"


def test_uploaded_parquet_content_is_valid(fake_s3, sample_df):
    upload_to_s3(sample_df)

    obj = fake_s3.get_object(Bucket=BUCKET, Key=EXPECTED_KEY)
    result_df = pd.read_parquet(io.BytesIO(obj["Body"].read()))

    assert list(result_df.columns) == ["timestamp", "value", "signal", "unit"]
    assert len(result_df) == len(sample_df)
    assert result_df["value"].tolist() == sample_df["value"].tolist()
