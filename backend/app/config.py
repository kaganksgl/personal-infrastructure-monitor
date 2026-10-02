"""Application settings, loaded from environment variables (12-factor style)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "production", "test"] = "production"
    log_level: str = "INFO"

    database_url: str = Field(
        description="SQLAlchemy async URL, e.g. postgresql+asyncpg://user:pass@host/db",
    )
    db_pool_size: int = 10

    # Comma-separated list. Only needed when the dashboard is served from a
    # different origin than the API (e.g. the Vite dev server).
    cors_origins: list[str] = Field(default_factory=list)

    # Dashboard sessions
    session_ttl_hours: int = 12
    cookie_secure: bool = True
    allow_registration: bool = False

    # Agent health
    agent_offline_after_seconds: int = 30
    heartbeat_check_interval_seconds: int = 5

    # Retention (see docs/retention.md)
    raw_retention_hours: int = 48
    metric_retention_days: int = 30
    daily_retention_days: int = 365
    retention_job_interval_seconds: int = 300

    # Ingestion guards
    max_batch_size: int = 100
    max_clock_skew_seconds: int = 300
    ingest_rate_per_minute: int = 120
    login_rate_per_minute: int = 10

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg,unused-ignore]
