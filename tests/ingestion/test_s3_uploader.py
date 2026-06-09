import io

import boto3
import pandas as pd
import pytest
from moto import mock_aws

from ingestion.s3_uploader import get_file_name, upload_to_s3, DATA_NAMES

BUCKET = "zephyrwerk-test-bucket"
REGION = "eu-central-1"
TEST_DATE = "2024-01-15"


@pytest.fixture
def fake_s3(monkeypatch):
    monkeypatch.setenv("ZEPHYRWERK_AWS_BUCKET_NAME", BUCKET)
    monkeypatch.setenv("AWS_ENDPOINT_URL", "")
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

def get_expected_key(data_name: DATA_NAMES):
    year, month, day = TEST_DATE.split("-")
    return f"raw/{data_name.value}/year={year}/month={month}/{data_name.value}_{year}_{month}_{day}.parquet"
    
def test_file_lands_at_correct_key(fake_s3, sample_df):
    upload_to_s3(sample_df, data_name=DATA_NAMES.SMARD)

    response = fake_s3.list_objects_v2(Bucket=BUCKET, Prefix=f"raw/{DATA_NAMES.SMARD.value}/")
    keys = [obj["Key"] for obj in response.get("Contents", [])]

    expected_key = get_expected_key(DATA_NAMES.SMARD)
    assert expected_key in keys, f"Expected key {get_expected_key(data_name='smard')!r} not found; got {keys}"


def test_uploaded_parquet_content_is_valid(fake_s3, sample_df):
    upload_to_s3(sample_df, data_name=DATA_NAMES.SMARD)

    expected_key = get_expected_key(DATA_NAMES.SMARD)
    obj = fake_s3.get_object(Bucket=BUCKET, Key=expected_key)
    result_df = pd.read_parquet(io.BytesIO(obj["Body"].read()))

    assert list(result_df.columns) == ["timestamp", "value", "signal", "unit"]
    assert len(result_df) == len(sample_df)
    assert result_df["value"].tolist() == sample_df["value"].tolist()

def test_get_file_name():
    expected_key = get_expected_key(DATA_NAMES.WEATHER)
    file_name = get_file_name(DATA_NAMES.WEATHER, 2024, 1, 15)
    assert file_name == expected_key, f"Expected file name {expected_key!r}, got {file_name!r}"

