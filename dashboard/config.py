from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DashboardSettings(BaseSettings):
    ZEPHYRWERK_DASHBOARD_API_URL: str

    ttl_historical: int = 60 * 60 * 6   # 6h — EDA/history data, changes at most daily
    ttl_forecast: int = 60 * 30         # 30m — until next model run
    ttl_model_metrics: int = 60 * 60 * 24  # 24h — only changes on retrain

    request_timeout: int = 10  # seconds, applied to every requests call in api_client.py

    model_config = SettingsConfigDict(env_file=".env", 
                                      case_sensitive=False, 
                                      env_file_encoding="utf-8",
                                      extra="ignore")


@lru_cache
def get_settings() -> DashboardSettings:
    return DashboardSettings()
