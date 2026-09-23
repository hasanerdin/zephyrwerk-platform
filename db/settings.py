from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class DatabaseSettings(BaseSettings):
    ZEPHYRWERK_RDS_HOST: str
    ZEPHYRWERK_RDS_PORT: int = 5432
    ZEPHYRWERK_RDS_DB: str
    ZEPHYRWERK_RDS_USER: str
    ZEPHYRWERK_RDS_PASSWORD: str

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @property
    def database_url(self) -> str: 
        return (
            f"postgresql+psycopg2://{self.ZEPHYRWERK_RDS_USER}:{self.ZEPHYRWERK_RDS_PASSWORD}"
            f"@{self.ZEPHYRWERK_RDS_HOST}:{self.ZEPHYRWERK_RDS_PORT}/{self.ZEPHYRWERK_RDS_DB}"
        )

class AWSSettings(BaseSettings):
    AWS_REGION: str = "eu-central-1"
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_ENDPOINT_URL: str | None = None
    ZEPHYRWERK_AWS_BUCKET_NAME: str

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


@lru_cache()
def get_db_settings() -> DatabaseSettings:
    return DatabaseSettings()

@lru_cache()
def get_aws_settings() -> AWSSettings:
    return AWSSettings()