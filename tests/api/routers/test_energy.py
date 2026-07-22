from datetime import date, datetime, timezone

import api.routers.energy as energy_router
from api.schemas.responses import (
    DayAheadPrice,
    DayAheadResponse,
    EnergyGeneration,
    EnergyGenerationResponse,
    EnergySummaryResponse,
)

# get_energy_summary / get_generated_energy / get_day_ahead_prices are imported
# with `from api.services.data_services import ...` in energy.py, binding the
# names directly into that module's namespace -- so mocks target
# api.routers.energy.<name>, not api.services.data_services.<name>.

TARGET_DATE = date(2024, 6, 1)


class TestEnergySummary:
    def test_mounted_at_energy_summary(self, client, monkeypatch):
        # Regression guard: this project has previously had router prefix
        # bugs (routes mounted at the wrong path). Assert on the full path.
        fake_response = EnergySummaryResponse(
            target_date=TARGET_DATE, generation_mix={}, avg_price=None, renewable_share=None
        )
        monkeypatch.setattr(energy_router, "get_energy_summary", lambda db, target_date: fake_response)

        response = client.get(f"/energy/summary?target_date={TARGET_DATE}")

        assert response.status_code == 200

    def test_full_data_returns_200_with_expected_shape(self, client, monkeypatch):
        fake_response = EnergySummaryResponse(
            target_date=TARGET_DATE,
            generation_mix={"wind_onshore_mw": 100.0, "solar_mw": 50.0},
            avg_price=42.5,
            renewable_share=63.2,
        )
        monkeypatch.setattr(energy_router, "get_energy_summary", lambda db, target_date: fake_response)

        response = client.get(f"/energy/summary?target_date={TARGET_DATE}")

        assert response.status_code == 200
        body = response.json()
        assert body["avg_price"] == 42.5
        assert body["renewable_share"] == 63.2
        assert body["generation_mix"] == {"wind_onshore_mw": 100.0, "solar_mw": 50.0}

    def test_partial_data_day_with_null_avg_price_and_renewable_share_returns_200(self, client, monkeypatch):
        fake_response = EnergySummaryResponse(
            target_date=TARGET_DATE, generation_mix={}, avg_price=None, renewable_share=None
        )
        monkeypatch.setattr(energy_router, "get_energy_summary", lambda db, target_date: fake_response)

        response = client.get(f"/energy/summary?target_date={TARGET_DATE}")

        assert response.status_code == 200
        body = response.json()
        assert body["avg_price"] is None
        assert body["renewable_share"] is None

    def test_missing_target_date_returns_422(self, client):
        response = client.get("/energy/summary")
        assert response.status_code == 422


class TestEnergyGeneration:
    def test_mounted_at_energy_generation(self, client, monkeypatch):
        fake_response = EnergyGenerationResponse(start_date=None, end_date=None, source=None, generated_energy=[])
        monkeypatch.setattr(
            energy_router, "get_generated_energy", lambda db, start_date, end_date, source: fake_response
        )

        response = client.get("/energy/generation")

        assert response.status_code == 200

    def test_no_filters_returns_200(self, client, monkeypatch):
        fake_response = EnergyGenerationResponse(start_date=None, end_date=None, source=None, generated_energy=[])
        monkeypatch.setattr(
            energy_router, "get_generated_energy", lambda db, start_date, end_date, source: fake_response
        )

        response = client.get("/energy/generation")

        assert response.status_code == 200
        body = response.json()
        assert body["start_date"] is None
        assert body["end_date"] is None

    def test_start_and_end_date_only_are_passed_through(self, client, monkeypatch):
        captured = {}

        def _fake(db, start_date, end_date, source):
            captured["start_date"] = start_date
            captured["end_date"] = end_date
            captured["source"] = source
            return EnergyGenerationResponse(
                start_date=start_date, end_date=end_date, source=source, generated_energy=[]
            )

        monkeypatch.setattr(energy_router, "get_generated_energy", _fake)

        response = client.get("/energy/generation?start_date=2024-01-01&end_date=2024-01-31")

        assert response.status_code == 200
        assert captured["start_date"] == date(2024, 1, 1)
        assert captured["end_date"] == date(2024, 1, 31)
        assert captured["source"] is None

    def test_valid_source_returns_200_with_that_source_in_the_response(self, client, monkeypatch):
        fake_response = EnergyGenerationResponse(
            start_date=None,
            end_date=None,
            source="wind_onshore_mw",
            generated_energy=[
                EnergyGeneration(
                    timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), source="wind_onshore_mw", value=123.4
                )
            ],
        )
        monkeypatch.setattr(
            energy_router, "get_generated_energy", lambda db, start_date, end_date, source: fake_response
        )

        response = client.get("/energy/generation?source=wind_onshore_mw")

        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "wind_onshore_mw"
        assert len(body["generated_energy"]) == 1

    def test_invalid_source_returns_422_naming_the_source_not_500(self, client, monkeypatch):
        # The repository raises ValueError for a source outside its allow-list;
        # the router's try/except must convert that to a 422, not let it fall
        # through to the generic Exception handler (which would be a 500).
        def _raise(db, start_date, end_date, source):
            raise ValueError(f"Unknown generation source '{source}'. Valid sources: [...]")

        monkeypatch.setattr(energy_router, "get_generated_energy", _raise)

        response = client.get("/energy/generation?source=not_a_real_source")

        assert response.status_code == 422
        assert "not_a_real_source" in response.json()["detail"]


class TestEnergyPrices:
    def test_mounted_at_energy_prices(self, client, monkeypatch):
        fake_response = DayAheadResponse(start_date=None, end_date=None, prices=[])
        monkeypatch.setattr(energy_router, "get_day_ahead_prices", lambda db, start_date, end_date: fake_response)

        response = client.get("/energy/prices")

        assert response.status_code == 200

    def test_start_end_range_returns_list_of_timestamp_price_objects(self, client, monkeypatch):
        fake_response = DayAheadResponse(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            prices=[
                DayAheadPrice(timestamp=datetime(2024, 1, 1, 0, tzinfo=timezone.utc), price=45.6),
                DayAheadPrice(timestamp=datetime(2024, 1, 1, 1, tzinfo=timezone.utc), price=47.1),
            ],
        )
        monkeypatch.setattr(energy_router, "get_day_ahead_prices", lambda db, start_date, end_date: fake_response)

        response = client.get("/energy/prices?start_date=2024-01-01&end_date=2024-01-02")

        assert response.status_code == 200
        body = response.json()
        assert body["start_date"] == "2024-01-01"
        assert body["end_date"] == "2024-01-02"
        assert isinstance(body["prices"], list)
        assert body["prices"] == [
            {"timestamp": "2024-01-01T00:00:00Z", "price": 45.6},
            {"timestamp": "2024-01-01T01:00:00Z", "price": 47.1},
        ]
