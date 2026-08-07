from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Impala Lineage Service"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+psycopg2://lineage:lineage@localhost:5432/lineage",
        description="SQLAlchemy connection string for the metadata/lineage store",
    )

    secret_key: str = Field(
        default="change-me-in-production-32-bytes!!",
        description="Used to derive the Fernet key that encrypts stored connection credentials",
    )

    api_key: str | None = Field(
        default=None,
        description="If set, all API requests must send this value in the X-API-Key header",
    )

    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    anthropic_api_key: str | None = Field(default=None)
    anthropic_model: str = Field(default="claude-sonnet-5")
    ai_lineage_fallback_enabled: bool = Field(
        default=True,
        description="When sqlglot cannot confidently resolve lineage, fall back to an AI-assisted pass",
    )

    default_query_timeout_seconds: int = Field(default=120)
    scan_max_concurrent_objects: int = Field(default=8)


@lru_cache
def get_settings() -> Settings:
    return Settings()
