from enum import StrEnum

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AYO"
    APP_VERSION: str = "1.0.0"

    API_PREFIX: str = "/api"

    DEBUG: bool = True
    ENVIRONMENT: AppEnvironment = AppEnvironment.DEVELOPMENT
    DISPATCH_ENABLED: bool = False
    DISPATCH_MAX_REQUEST_BYTES: int = Field(default=16_384, ge=1_024, le=1_048_576)
    SCHEDULED_DISPATCH_ENABLED: bool = False
    SCHEDULED_DISPATCH_MAX_REQUEST_BYTES: int = Field(
        default=16_384, ge=1_024, le=1_048_576
    )

    @model_validator(mode="after")
    def production_dispatch_gate(self) -> "Settings":
        if self.DISPATCH_ENABLED and self.ENVIRONMENT is AppEnvironment.PRODUCTION:
            raise ValueError(
                "Dispatch production activation requires separate recorded approval"
            )
        return self

    @model_validator(mode="after")
    def production_scheduled_dispatch_gate(self) -> "Settings":
        if (
            self.SCHEDULED_DISPATCH_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Scheduled dispatch production activation requires separate approval"
            )
        return self


settings = Settings()
