from decimal import Decimal

import pytest

from BACKEND.models.driver import DriverStatus, VehicleType
from BACKEND.schemas.ride import RideType
from BACKEND.services.driver_service import DRIVERS
from BACKEND.services.ride_service import calculate_distance_km, driver_is_eligible
from BACKEND.services.wallet_service import add_trip_earning, get_wallet


def test_distance_and_driver_eligibility_basics():
    assert calculate_distance_km(8.98, 38.75, 8.98, 38.75) == 0
    assert driver_is_eligible(DRIVERS[0], RideType.PREMIUM)

    unavailable = DRIVERS[0].model_copy(update={"status": DriverStatus.BUSY})
    assert not driver_is_eligible(unavailable, RideType.STANDARD)

    standard = DRIVERS[0].model_copy(
        update={"vehicle_type": VehicleType.STANDARD, "premium_eligible": False}
    )
    assert not driver_is_eligible(standard, RideType.PREMIUM)


def test_online_trip_earning_uses_decimal_money():
    result = add_trip_earning("TEST-DRIVER", "TEST-RIDE", "100.05", "CARD")

    assert result["breakdown"]["commission"] == Decimal("15.01")
    assert result["wallet"]["available_to_cashout"] == Decimal("85.04")


@pytest.mark.known_defect
@pytest.mark.xfail(
    strict=True,
    reason="Known prototype defect: cash commission is destructively netted twice",
)
def test_cash_commission_is_not_lost_on_repeated_wallet_refresh():
    add_trip_earning("TEST-DRIVER", "CASH-RIDE", 100, "CASH")
    add_trip_earning("TEST-DRIVER", "CARD-RIDE", 100, "CARD")

    first_read = get_wallet("TEST-DRIVER")["available_to_cashout"]
    second_read = get_wallet("TEST-DRIVER")["available_to_cashout"]

    assert first_read == second_read == Decimal("70.00")
