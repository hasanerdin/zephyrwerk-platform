import json
import logging

import boto3
import pytest
from moto import mock_aws

import ml.s3_model_io as s3_model_io
from ml.training_utils import ModelType

BUCKET = "zephyrwerk-test-models-bucket"
REGION = "eu-central-1"
MODEL_TYPE = ModelType.PRICE
MODEL_NAME = f"{MODEL_TYPE.value}_forecast"


@pytest.fixture
def fake_s3(monkeypatch):
    monkeypatch.setenv("ZEPHYRWERK_AWS_BUCKET_NAME", BUCKET)
    monkeypatch.setenv("AWS_ENDPOINT_URL", "")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)

    # the module caches its boto3 client at first use; reset it so each test
    # picks up a client bound to the currently active moto backend
    s3_model_io._reset_client_cache()

    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        yield client

    s3_model_io._reset_client_cache()


@pytest.fixture
def fake_pipeline():
    return {"coef": [1.0, 2.0, 3.0], "intercept": 0.5}


def test_save_pipeline_writes_latest_and_archive_copies(fake_s3, fake_pipeline):
    uri = s3_model_io.save_pipeline(fake_pipeline, MODEL_TYPE, metadata={"r2": 0.9})

    assert uri.startswith(f"s3://{BUCKET}/models/{MODEL_NAME}/archive/")
    assert uri.endswith(f"{MODEL_NAME}.joblib")

    keys = {obj["Key"] for obj in fake_s3.list_objects_v2(Bucket=BUCKET, Prefix="models/")["Contents"]}
    assert f"models/{MODEL_NAME}/latest/{MODEL_NAME}.joblib" in keys
    assert f"models/{MODEL_NAME}/latest/metadata.json" in keys

    archive_model_keys = [
        key for key in keys
        if key.startswith(f"models/{MODEL_NAME}/archive/") and key.endswith(f"{MODEL_NAME}.joblib")
    ]
    assert len(archive_model_keys) == 1


def test_save_pipeline_writes_metadata_content(fake_s3, fake_pipeline):
    s3_model_io.save_pipeline(fake_pipeline, MODEL_TYPE, metadata={"r2": 0.9})

    obj = fake_s3.get_object(Bucket=BUCKET, Key=f"models/{MODEL_NAME}/latest/metadata.json")
    assert json.loads(obj["Body"].read()) == {"r2": 0.9}


def test_save_pipeline_without_metadata_defaults_to_empty_dict_and_warns(fake_s3, fake_pipeline, caplog):
    with caplog.at_level(logging.WARNING):
        s3_model_io.save_pipeline(fake_pipeline, MODEL_TYPE)

    assert "without metadata" in caplog.text

    obj = fake_s3.get_object(Bucket=BUCKET, Key=f"models/{MODEL_NAME}/latest/metadata.json")
    assert json.loads(obj["Body"].read()) == {}


def test_save_then_load_pipeline_latest_round_trips(fake_s3, fake_pipeline):
    s3_model_io.save_pipeline(fake_pipeline, MODEL_TYPE, metadata={"r2": 0.9})

    loaded, metadata = s3_model_io.load_pipeline(MODEL_TYPE)

    assert loaded == fake_pipeline
    assert metadata == {"r2": 0.9}


def test_save_then_load_pipeline_specific_archive_version(fake_s3, fake_pipeline):
    s3_model_io.save_pipeline(fake_pipeline, MODEL_TYPE, metadata={"r2": 0.9})

    prefix = f"models/{MODEL_NAME}/archive/"
    keys = [obj["Key"] for obj in fake_s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)["Contents"]]
    model_key = next(key for key in keys if key.endswith(".joblib"))
    version = model_key[len(prefix):].split("/")[0]

    loaded, metadata = s3_model_io.load_pipeline(MODEL_TYPE, version=version)

    assert loaded == fake_pipeline
    assert metadata == {"r2": 0.9}


def test_load_pipeline_rejects_malformed_version(fake_s3):
    with pytest.raises(ValueError, match="version must be 'latest'"):
        s3_model_io.load_pipeline(MODEL_TYPE, version="not-a-valid-version")


def test_load_pipeline_missing_key_raises(fake_s3):
    with pytest.raises(Exception):
        s3_model_io.load_pipeline("never-saved-model")


def test_save_pipeline_raises_without_bucket_env_var(monkeypatch, fake_pipeline):
    monkeypatch.delenv("ZEPHYRWERK_AWS_BUCKET_NAME", raising=False)

    with pytest.raises(ValueError, match="ZEPHYRWERK_AWS_BUCKET_NAME"):
        s3_model_io.save_pipeline(fake_pipeline, MODEL_TYPE)
