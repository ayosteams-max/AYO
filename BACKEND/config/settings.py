from enum import StrEnum

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AYO_",
        env_file=".env",
        extra="ignore",
    )

    APP_NAME: str = "AYO"
    APP_VERSION: str = "1.0.0"

    API_PREFIX: str = "/api"

    DEBUG: bool = False
    ENVIRONMENT: AppEnvironment = AppEnvironment.DEVELOPMENT
    PERSISTENCE_ENABLED: bool = False
    LOG_LEVEL: str = Field(
        default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"
    )
    AUTHENTICATION_ENABLED: bool = False
    IDENTITY_ADMIN_BOOTSTRAP_ENABLED: bool = False
    IDENTITY_ADMIN_BOOTSTRAP_SECRET_SHA256: SecretStr | None = None
    AUTHENTICATION_MAX_REQUEST_BYTES: int = Field(default=16_384, ge=1_024, le=65_536)
    DISPATCH_ENABLED: bool = False
    CANONICAL_DISPATCH_ENABLED: bool = False
    DISPATCH_MAX_REQUEST_BYTES: int = Field(default=16_384, ge=1_024, le=1_048_576)
    SCHEDULED_DISPATCH_ENABLED: bool = False
    SCHEDULED_DISPATCH_MAX_REQUEST_BYTES: int = Field(
        default=16_384, ge=1_024, le=1_048_576
    )
    ACTIVE_RIDE_ENABLED: bool = False
    ACTIVE_RIDE_MAX_REQUEST_BYTES: int = Field(default=16_384, ge=1_024, le=1_048_576)
    ARRIVAL_WAITING_ENABLED: bool = False
    ARRIVAL_WAITING_MAX_REQUEST_BYTES: int = Field(
        default=16_384, ge=1_024, le=1_048_576
    )
    MOBILE_CASH_QUOTE_ENABLED: bool = False
    RIDER_BOOKING_ENABLED: bool = False
    RIDER_BOOKING_MAX_REQUEST_BYTES: int = Field(default=32_768, ge=4_096, le=262_144)
    POST_TRIP_ENABLED: bool = False
    POST_TRIP_MAX_REQUEST_BYTES: int = Field(default=16_384, ge=1_024, le=65_536)
    MERCHANT_PLATFORM_ENABLED: bool = False
    MERCHANT_PLATFORM_MAX_REQUEST_BYTES: int = Field(
        default=32_768, ge=4_096, le=262_144
    )
    CATALOGUE_PLATFORM_ENABLED: bool = False
    CATALOGUE_PLATFORM_MAX_REQUEST_BYTES: int = Field(
        default=65_536, ge=4_096, le=524_288
    )
    ORDERING_PLATFORM_ENABLED: bool = False
    ORDERING_PLATFORM_MAX_REQUEST_BYTES: int = Field(
        default=65_536, ge=4_096, le=524_288
    )
    MERCHANT_ORDER_MANAGEMENT_ENABLED: bool = False
    MERCHANT_ORDER_MANAGEMENT_MAX_REQUEST_BYTES: int = Field(
        default=32_768, ge=4_096, le=262_144
    )
    MERCHANT_PREPARATION_ENABLED: bool = False
    MERCHANT_PREPARATION_MAX_REQUEST_BYTES: int = Field(
        default=32_768, ge=4_096, le=262_144
    )
    COURIER_DISPATCH_PLATFORM_ENABLED: bool = False
    COURIER_DISPATCH_PLATFORM_MAX_REQUEST_BYTES: int = Field(
        default=32_768, ge=4_096, le=262_144
    )
    COURIER_PICKUP_PLATFORM_ENABLED: bool = False
    COURIER_PICKUP_PLATFORM_MAX_REQUEST_BYTES: int = Field(
        default=32_768, ge=4_096, le=262_144
    )
    CUSTODY_PLATFORM_ENABLED: bool = False
    CUSTODY_PLATFORM_MAX_REQUEST_BYTES: int = Field(
        default=32_768, ge=4_096, le=262_144
    )
    DELIVERY_PLATFORM_ENABLED: bool = False
    DELIVERY_PLATFORM_MAX_REQUEST_BYTES: int = Field(
        default=32_768, ge=4_096, le=262_144
    )
    FIELD_OPERATIONS_PLATFORM_ENABLED: bool = False
    FIELD_OPERATIONS_PLATFORM_MAX_REQUEST_BYTES: int = Field(
        default=32_768, ge=4_096, le=262_144
    )

    @model_validator(mode="after")
    def production_dispatch_gate(self) -> "Settings":
        if (
            self.DISPATCH_ENABLED or self.CANONICAL_DISPATCH_ENABLED
        ) and self.ENVIRONMENT is AppEnvironment.PRODUCTION:
            raise ValueError(
                "Dispatch production activation requires separate recorded approval"
            )
        return self

    @model_validator(mode="after")
    def identity_bootstrap_gate(self) -> "Settings":
        if self.IDENTITY_ADMIN_BOOTSTRAP_ENABLED:
            if self.ENVIRONMENT is AppEnvironment.PRODUCTION:
                raise ValueError(
                    "Identity administrator bootstrap is prohibited in production"
                )
            verifier = self.IDENTITY_ADMIN_BOOTSTRAP_SECRET_SHA256
            if verifier is None or len(verifier.get_secret_value()) != 64:
                raise ValueError("Identity bootstrap requires a SHA-256 verifier")
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

    @model_validator(mode="after")
    def production_active_ride_gate(self) -> "Settings":
        if self.ACTIVE_RIDE_ENABLED and self.ENVIRONMENT is AppEnvironment.PRODUCTION:
            raise ValueError(
                "Active ride production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_arrival_waiting_gate(self) -> "Settings":
        if (
            self.ARRIVAL_WAITING_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Arrival/waiting production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_mobile_quote_gate(self) -> "Settings":
        if (
            self.MOBILE_CASH_QUOTE_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Mobile cash quote production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_booking_gate(self) -> "Settings":
        if self.RIDER_BOOKING_ENABLED and self.ENVIRONMENT is AppEnvironment.PRODUCTION:
            raise ValueError(
                "Rider booking production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_post_trip_gate(self) -> "Settings":
        if self.POST_TRIP_ENABLED and self.ENVIRONMENT is AppEnvironment.PRODUCTION:
            raise ValueError(
                "Post-trip production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_merchant_gate(self) -> "Settings":
        if (
            self.MERCHANT_PLATFORM_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Merchant Platform production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_catalogue_gate(self) -> "Settings":
        if (
            self.CATALOGUE_PLATFORM_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Catalogue Platform production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_ordering_gate(self) -> "Settings":
        if (
            self.ORDERING_PLATFORM_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Ordering Platform production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_merchant_order_gate(self) -> "Settings":
        if (
            self.MERCHANT_ORDER_MANAGEMENT_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Merchant Order Management production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_merchant_preparation_gate(self) -> "Settings":
        if (
            self.MERCHANT_PREPARATION_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Merchant Preparation production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_courier_dispatch_platform_gate(self) -> "Settings":
        if (
            self.COURIER_DISPATCH_PLATFORM_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Courier Dispatch Platform production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_courier_pickup_platform_gate(self) -> "Settings":
        if (
            self.COURIER_PICKUP_PLATFORM_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Courier Pickup Platform production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_custody_platform_gate(self) -> "Settings":
        if (
            self.CUSTODY_PLATFORM_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Custody Platform production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_delivery_platform_gate(self) -> "Settings":
        if (
            self.DELIVERY_PLATFORM_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Delivery Platform production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_field_operations_platform_gate(self) -> "Settings":
        if (
            self.FIELD_OPERATIONS_PLATFORM_ENABLED
            and self.ENVIRONMENT is AppEnvironment.PRODUCTION
        ):
            raise ValueError(
                "Field Operations Platform production activation requires separate approval"
            )
        return self

    @model_validator(mode="after")
    def production_engineering_foundation_gate(self) -> "Settings":
        if self.ENVIRONMENT is AppEnvironment.PRODUCTION:
            if self.DEBUG:
                raise ValueError("Debug mode is prohibited in production")
            if not self.PERSISTENCE_ENABLED:
                raise ValueError("PostgreSQL persistence is required in production")
        return self


settings = Settings()
