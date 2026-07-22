import logging

import pandas as pd
import pytest

import ml.data_access as data_access


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setattr(data_access.engine, "connect", lambda: FakeConnection())


@pytest.fixture
def capture_read_sql(monkeypatch):
    calls = []

    def fake_read_sql_query(query, conn, params=None):
        calls.append({"query": str(query), "params": params})
        return pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-02", "2024-01-01"]),
            "value": [2.0, 1.0],
            "wind_onshore_mw": [30.0, 20.0],
            "wind_offshore_mw": [8.0, 5.0],
            "solar_mw": [12.0, 9.0],
        })

    monkeypatch.setattr(data_access.pd, "read_sql_query", fake_read_sql_query)
    return calls


def test_load_features_no_date_filters(fake_engine, capture_read_sql):
    data_access.load_ml_features()

    query = capture_read_sql[0]["query"]
    assert "WHERE 1=1" in query
    assert "start_date" not in query
    assert "end_date" not in query
    assert "ORDER BY timestamp ASC" in query
    assert capture_read_sql[0]["params"] == {}


def test_load_features_with_start_date_only(fake_engine, capture_read_sql):
    data_access.load_ml_features(start_date="2024-01-01")

    call = capture_read_sql[0]
    assert "AND timestamp >= :start_date" in call["query"]
    assert "AND timestamp <= :end_date" not in call["query"]
    assert call["params"] == {"start_date": "2024-01-01"}


def test_load_features_with_end_date_only(fake_engine, capture_read_sql):
    data_access.load_ml_features(end_date="2024-02-01")

    call = capture_read_sql[0]
    assert "AND timestamp <= :end_date" in call["query"]
    assert "AND timestamp >= :start_date" not in call["query"]
    assert call["params"] == {"end_date": "2024-02-01"}


def test_load_features_with_both_dates(fake_engine, capture_read_sql):
    data_access.load_ml_features(start_date="2024-01-01", end_date="2024-02-01")

    call = capture_read_sql[0]
    assert "AND timestamp >= :start_date" in call["query"]
    assert "AND timestamp <= :end_date" in call["query"]
    assert call["params"] == {"start_date": "2024-01-01", "end_date": "2024-02-01"}


def test_load_features_indexes_and_sorts_by_timestamp(fake_engine, capture_read_sql):
    df = data_access.load_ml_features()

    assert df.index.name == "timestamp"
    assert df.index.is_monotonic_increasing


def test_load_features_computes_wind_total(fake_engine, capture_read_sql):
    df = data_access.load_ml_features()

    # load_features sorts ascending by timestamp, so 2024-01-01 (25.0) comes
    # before 2024-01-02 (38.0), even though the fixture returns them reversed.
    assert df["wind_total_mw"].tolist() == [25.0, 38.0]


def test_load_features_solar_lags_are_nan_with_insufficient_history(fake_engine, capture_read_sql):
    # Only 2 rows are available here, well short of the 24h/168h lookback —
    # shift() should produce NaN rather than wrapping around or erroring.
    df = data_access.load_ml_features()

    assert df["solar_mw_lag_24h"].isna().all()
    assert df["solar_mw_lag_168h"].isna().all()


def test_load_features_solar_lag_24h_pulls_correct_historical_value(fake_engine, monkeypatch):
    hours = 30
    timestamps = pd.date_range("2024-01-01", periods=hours, freq="h")
    solar_values = list(range(hours))  # 0, 1, 2, ... so lag is easy to verify

    def fake_read_sql_query(query, conn, params=None):
        return pd.DataFrame({
            "timestamp": timestamps,
            "wind_onshore_mw": [0.0] * hours,
            "wind_offshore_mw": [0.0] * hours,
            "solar_mw": solar_values,
        })

    monkeypatch.setattr(data_access.pd, "read_sql_query", fake_read_sql_query)

    df = data_access.load_ml_features()

    # Row at index 24 (hour 24) should carry hour 0's solar value as its 24h lag.
    assert df["solar_mw_lag_24h"].iloc[24] == solar_values[0]
    assert df["solar_mw_lag_24h"].iloc[:24].isna().all()


def test_load_features_logs_and_reraises_on_failure(fake_engine, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(data_access.pd, "read_sql_query", boom)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError, match="db exploded"):
            data_access.load_ml_features()

    assert "Failed to load features" in caplog.text
