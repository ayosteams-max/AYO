from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Validated, namespaced PostgreSQL connection and pool settings."""

    model_config = SettingsConfigDict(
        env_prefix="AYO_DATABASE_",
        env_file=".env",
        extra="ignore",
    )

    url: SecretStr | None = None
    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=5, ge=0, le=100)
    pool_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    pool_recycle_seconds: int = Field(default=900, ge=30)
    connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    statement_timeout_ms: int = Field(default=5_000, ge=100, le=120_000)
    idle_transaction_timeout_ms: int = Field(default=10_000, ge=1_000, le=300_000)
    ssl_mode: Literal[
        "disable", "allow", "prefer", "require", "verify-ca", "verify-full"
    ] = "verify-full"
    application_name: str = Field(default="ayo-api", min_length=1, max_length=63)

    def require_url(self) -> str:
        if self.url is None:
            raise RuntimeError(
                "AYO_DATABASE_URL is required for PostgreSQL persistence."
            )
        return self.url.get_secret_value()
