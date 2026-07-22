from unittest.mock import MagicMock

from ml.training_utils import ModelType


class TestHealth:
    def test_all_models_present_and_db_reachable_returns_200_healthy(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["database"] == "connected"

    def test_db_check_raising_returns_503_naming_the_database(self, make_client):
        failing_db = MagicMock()
        failing_db.execute.side_effect = Exception("connection refused")
        client = make_client(db=failing_db)

        response = client.get("/health")

        assert response.status_code == 503
        detail = response.json()["detail"].lower()
        assert "database" in detail
        assert "price" not in detail and "wind" not in detail and "solar" not in detail

    def test_missing_price_model_returns_503_naming_price(self, make_client):
        client = make_client(missing_model_types=[ModelType.PRICE])

        response = client.get("/health")

        assert response.status_code == 503
        assert "price" in response.json()["detail"].lower()

    def test_missing_wind_model_returns_503_naming_wind(self, make_client):
        client = make_client(missing_model_types=[ModelType.WIND])

        response = client.get("/health")

        assert response.status_code == 503
        assert "wind" in response.json()["detail"].lower()

    def test_missing_solar_model_returns_503_naming_solar(self, make_client):
        client = make_client(missing_model_types=[ModelType.SOLAR])

        response = client.get("/health")

        assert response.status_code == 503
        assert "solar" in response.json()["detail"].lower()

    def test_db_failure_is_checked_before_models_and_takes_precedence(self, make_client):
        # Both failure conditions are forced true at once (DB broken AND a
        # model missing) so this actually exercises the try/except-before-
        # the-model-loop ordering in health.py, not just DB-failure handling
        # in isolation -- the model-loop code is reachable here too, so the
        # DB message winning is a real assertion, not a foregone conclusion.
        failing_db = MagicMock()
        failing_db.execute.side_effect = Exception("connection refused")
        client = make_client(missing_model_types=[ModelType.PRICE], db=failing_db)

        response = client.get("/health")

        assert response.status_code == 503
        detail = response.json()["detail"].lower()
        assert "database" in detail
        assert "price" not in detail

    def test_get_health_does_not_redirect_with_trailing_slash(self, client):
        # Regression guard: the route was previously accidentally mounted at
        # /health/ instead of /health, which meant GET /health 307-redirected
        # instead of answering directly.
        response = client.get("/health", follow_redirects=False)

        assert response.status_code != 307
        assert response.status_code == 200
