from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import pytest

import api.routers.predict as predict_router
from api.services.prediction_service import ForecastDataUnavailable
from ml.training_utils import ModelType

# predict() is imported with `from api.services.prediction_service import predict`
# in predict.py, which binds the name directly into that module's namespace.
# Patching api.services.prediction_service.predict would NOT affect the router
# (it already holds its own reference to the original function object) -- the
# mock has to target api.routers.predict.predict instead.

TODAY = datetime.now(timezone.utc).date()
TOMORROW = TODAY + timedelta(days=1)
YESTERDAY = TODAY - timedelta(days=1)


def _predictions_for(target_date: date, base_value: float = 40.0) -> dict:
    """
    tz-aware (UTC) predictions dict, one entry per hour 0-23 -- shaped like
    what prediction_service.predict() actually returns. Uses tz-aware
    pd.Timestamp keys (as the real service does, via features.index) rather
    than naive datetimes, so a regression to naive-datetime comparison in the
    router would show up as spurious 400s in the tests below.
    """
    return {
        pd.Timestamp(datetime.combine(target_date, time(h), tzinfo=timezone.utc)): base_value + h
        for h in range(24)
    }


def _key_for(target_date: date, hour: int) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(target_date, time(hour), tzinfo=timezone.utc))


class TestPredictPrice:
    def test_valid_target_date_no_hour_returns_24_distinct_hourly_predictions(self, client, monkeypatch):
        predictions = _predictions_for(TODAY)
        monkeypatch.setattr(predict_router, "predict", lambda model, target_date: predictions)

        response = client.post("/predict/price", json={"target_date": str(TODAY)})

        assert response.status_code == 200
        body = response.json()
        hours = [p["hour"] for p in body["prices"]]
        assert len(body["prices"]) == 24
        assert sorted(hours) == list(range(24))
        assert len(set(hours)) == 24

    def test_valid_tomorrow_no_hour_returns_200(self, client, monkeypatch):
        predictions = _predictions_for(TOMORROW)
        monkeypatch.setattr(predict_router, "predict", lambda model, target_date: predictions)

        response = client.post("/predict/price", json={"target_date": str(TOMORROW)})

        assert response.status_code == 200
        assert len(response.json()["prices"]) == 24

    def test_hour_zero_is_treated_as_an_explicit_hour_not_as_no_hour(self, client, monkeypatch):
        # Regression guard: `if body.hour:` previously treated hour=0 as falsy
        # and fell through to the "no hour given" branch (24 results, not 1).
        predictions = _predictions_for(TODAY)
        monkeypatch.setattr(predict_router, "predict", lambda model, target_date: predictions)

        response = client.post("/predict/price", json={"target_date": str(TODAY), "hour": 0})

        assert response.status_code == 200
        body = response.json()
        assert len(body["prices"]) == 1
        assert body["prices"][0]["hour"] == 0
        assert body["hour"] == 0

    def test_hour_23_returns_single_matching_prediction(self, client, monkeypatch):
        predictions = _predictions_for(TODAY)
        monkeypatch.setattr(predict_router, "predict", lambda model, target_date: predictions)

        response = client.post("/predict/price", json={"target_date": str(TODAY), "hour": 23})

        assert response.status_code == 200
        body = response.json()
        assert len(body["prices"]) == 1
        assert body["prices"][0]["hour"] == 23
        assert body["prices"][0]["value"] == predictions[_key_for(TODAY, 23)]

    def test_mid_range_hour_returns_single_matching_prediction(self, client, monkeypatch):
        predictions = _predictions_for(TODAY)
        monkeypatch.setattr(predict_router, "predict", lambda model, target_date: predictions)

        response = client.post("/predict/price", json={"target_date": str(TODAY), "hour": 12})

        assert response.status_code == 200
        body = response.json()
        assert len(body["prices"]) == 1
        assert body["prices"][0]["hour"] == 12
        assert body["prices"][0]["value"] == predictions[_key_for(TODAY, 12)]

    def test_target_date_more_than_one_day_ahead_returns_422_with_horizon_message(self, client):
        too_far = TODAY + timedelta(days=2)
        response = client.post("/predict/price", json={"target_date": str(too_far)})

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("target_date" in str(err.get("loc")) for err in detail)
        assert any("today or tomorrow" in err.get("msg", "") for err in detail)

    def test_target_date_in_the_past_returns_422(self, client):
        response = client.post("/predict/price", json={"target_date": str(YESTERDAY)})

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("target_date" in str(err.get("loc")) for err in detail)

    def test_requested_hour_present_in_tz_aware_predictions_returns_200(self, client, monkeypatch):
        # Regression guard: comparing a naive `exact_datetime` against these
        # tz-aware pd.Timestamp keys previously made the `in` check always
        # miss, turning every hour-scoped request into a spurious 400.
        predictions = _predictions_for(TODAY)
        monkeypatch.setattr(predict_router, "predict", lambda model, target_date: predictions)

        response = client.post("/predict/price", json={"target_date": str(TODAY), "hour": 5})

        assert response.status_code == 200

    def test_requested_hour_missing_from_predictions_returns_400_not_500(self, client, monkeypatch):
        predictions = _predictions_for(TODAY)
        del predictions[_key_for(TODAY, 5)]
        monkeypatch.setattr(predict_router, "predict", lambda model, target_date: predictions)

        response = client.post("/predict/price", json={"target_date": str(TODAY), "hour": 5})

        assert response.status_code == 400
        assert "05:00:00" in response.json()["detail"]

    def test_missing_price_model_returns_503(self, make_client):
        client = make_client(missing_model_types=[ModelType.PRICE])

        response = client.post("/predict/price", json={"target_date": str(TODAY)})

        assert response.status_code == 503
        assert "price" in response.json()["detail"].lower()

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"target_date": str(TODAY), "hour": 24}, id="hour-too-high"),
            pytest.param({"target_date": str(TODAY), "hour": -1}, id="hour-negative"),
            pytest.param({"hour": 5}, id="missing-target-date"),
        ],
    )
    def test_malformed_request_body_returns_422(self, client, body):
        response = client.post("/predict/price", json=body)
        assert response.status_code == 422

    def test_forecast_data_unavailable_returns_503_not_500(self, client, monkeypatch):
        def _raise_forecast_unavailable(model, target_date):
            raise ForecastDataUnavailable(f"Weather forecast data not yet available for {target_date}")

        monkeypatch.setattr(predict_router, "predict", _raise_forecast_unavailable)

        response = client.post("/predict/price", json={"target_date": str(TODAY)})

        assert response.status_code == 503
        assert str(TODAY) in response.json()["detail"]


class TestPredictGeneration:
    def _patch_generation_predict(self, monkeypatch, solar_predictions, wind_predictions):
        def _fake_predict(model, target_date):
            return solar_predictions if model.model_type == ModelType.SOLAR else wind_predictions

        monkeypatch.setattr(predict_router, "predict", _fake_predict)

    def test_valid_target_date_no_hour_returns_24_entries_for_each_source(self, client, monkeypatch):
        solar = _predictions_for(TODAY, base_value=10.0)
        wind = _predictions_for(TODAY, base_value=200.0)
        self._patch_generation_predict(monkeypatch, solar, wind)

        response = client.post("/predict/generation", json={"target_date": str(TODAY)})

        assert response.status_code == 200
        body = response.json()
        assert len(body["solar_generations"]["generations"]) == 24
        assert len(body["wind_generations"]["generations"]) == 24

    def test_solar_and_wind_generations_are_not_swapped_or_mixed(self, client, monkeypatch):
        solar = _predictions_for(TODAY, base_value=10.0)
        wind = _predictions_for(TODAY, base_value=1000.0)
        self._patch_generation_predict(monkeypatch, solar, wind)

        response = client.post("/predict/generation", json={"target_date": str(TODAY), "hour": 3})

        assert response.status_code == 200
        body = response.json()
        solar_value = body["solar_generations"]["generations"][0]["value"]
        wind_value = body["wind_generations"]["generations"][0]["value"]
        assert solar_value == pytest.approx(10.0 + 3)
        assert wind_value == pytest.approx(1000.0 + 3)

    def test_hour_zero_is_treated_as_an_explicit_hour_for_generation_too(self, client, monkeypatch):
        # Same hour=0-as-falsy bug class as the price endpoint.
        solar = _predictions_for(TODAY)
        wind = _predictions_for(TODAY)
        self._patch_generation_predict(monkeypatch, solar, wind)

        response = client.post("/predict/generation", json={"target_date": str(TODAY), "hour": 0})

        assert response.status_code == 200
        body = response.json()
        assert len(body["solar_generations"]["generations"]) == 1
        assert len(body["wind_generations"]["generations"]) == 1
        assert body["solar_generations"]["generations"][0]["hour"] == 0
        assert body["wind_generations"]["generations"][0]["hour"] == 0

    def test_missing_solar_model_returns_503_naming_solar(self, make_client):
        client = make_client(missing_model_types=[ModelType.SOLAR])

        response = client.post("/predict/generation", json={"target_date": str(TODAY)})

        assert response.status_code == 503
        assert "solar" in response.json()["detail"].lower()

    def test_missing_wind_model_returns_503_naming_wind(self, make_client):
        client = make_client(missing_model_types=[ModelType.WIND])

        response = client.post("/predict/generation", json={"target_date": str(TODAY)})

        assert response.status_code == 503
        assert "wind" in response.json()["detail"].lower()

    def test_requested_hour_missing_from_wind_predictions_returns_400_naming_wind(self, client, monkeypatch):
        solar = _predictions_for(TODAY)
        wind = _predictions_for(TODAY)
        del wind[_key_for(TODAY, 5)]
        self._patch_generation_predict(monkeypatch, solar, wind)

        response = client.post("/predict/generation", json={"target_date": str(TODAY), "hour": 5})

        assert response.status_code == 400
        assert "wind" in response.json()["detail"].lower()

    def test_requested_hour_missing_from_solar_predictions_returns_400_naming_solar(self, client, monkeypatch):
        solar = _predictions_for(TODAY)
        wind = _predictions_for(TODAY)
        del solar[_key_for(TODAY, 5)]
        self._patch_generation_predict(monkeypatch, solar, wind)

        response = client.post("/predict/generation", json={"target_date": str(TODAY), "hour": 5})

        assert response.status_code == 400
        assert "solar" in response.json()["detail"].lower()

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"target_date": str(TODAY), "hour": 24}, id="hour-too-high"),
            pytest.param({"target_date": str(TODAY), "hour": -1}, id="hour-negative"),
            pytest.param({"hour": 5}, id="missing-target-date"),
        ],
    )
    def test_malformed_request_body_returns_422(self, client, body):
        response = client.post("/predict/generation", json=body)
        assert response.status_code == 422

    def test_forecast_data_unavailable_returns_503_not_500(self, client, monkeypatch):
        def _raise_forecast_unavailable(model, target_date):
            raise ForecastDataUnavailable(f"Weather forecast data not yet available for {target_date}")

        monkeypatch.setattr(predict_router, "predict", _raise_forecast_unavailable)

        response = client.post("/predict/generation", json={"target_date": str(TODAY)})

        assert response.status_code == 503
        assert str(TODAY) in response.json()["detail"]
