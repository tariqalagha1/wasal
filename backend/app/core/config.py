"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_timezone: str = "Asia/Riyadh"

    database_url: str = "mysql+asyncmy://qms_user:qms_pass@127.0.0.1:3307/qms?charset=utf8mb4"
    booking_database_url: str = ""

    jwt_secret: str = "dev_insecure_secret_change_me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 720

    daily_import_time: str = "05:00"
    early_threshold_minutes: int = 15
    late_threshold_minutes: int = 15

    public_base_url: str = "http://localhost:8100"
    frontend_base_url: str = "http://localhost:5173"
    default_locale: str = "en"
    supported_locales: str = "en,ar"

    cors_origins: str = "http://localhost:5173"

    @property
    def supported_locales_list(self) -> list[str]:
        return [x.strip() for x in self.supported_locales.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
