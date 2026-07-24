from typing import Any

import pytest

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.main import create_app


def _configuration(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "ENVIRONMENT": AppEnvironment.TEST,
        "DISPATCH_ENABLED": False,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("AUTHENTICATION_ENABLED", "authentication"),
        ("SCHEDULED_DISPATCH_ENABLED", "scheduled dispatch"),
        ("ACTIVE_RIDE_ENABLED", "active ride"),
        ("ARRIVAL_WAITING_ENABLED", "arrival/waiting"),
        ("MOBILE_CASH_QUOTE_ENABLED", "mobile cash quotes"),
        ("RIDER_BOOKING_ENABLED", "rider booking"),
        ("POST_TRIP_ENABLED", "post-trip"),
        ("MERCHANT_PLATFORM_ENABLED", "Merchant Platform"),
        ("CATALOGUE_PLATFORM_ENABLED", "Catalogue Platform"),
        ("ORDERING_PLATFORM_ENABLED", "Ordering Platform"),
        ("MERCHANT_ORDER_MANAGEMENT_ENABLED", "Merchant Order Management"),
        ("MERCHANT_PREPARATION_ENABLED", "Merchant Preparation"),
        ("COURIER_DISPATCH_PLATFORM_ENABLED", "Courier Dispatch Platform"),
        ("COURIER_PICKUP_PLATFORM_ENABLED", "Courier Pickup Platform"),
        ("CUSTODY_PLATFORM_ENABLED", "Custody Platform"),
        ("DELIVERY_PLATFORM_ENABLED", "Delivery Platform"),
        ("FIELD_OPERATIONS_PLATFORM_ENABLED", "Field Operations Platform"),
    ],
)
def test_every_platform_activation_fails_closed_without_secure_dependencies(
    flag: str, message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        create_app(_configuration(**{flag: True}))
