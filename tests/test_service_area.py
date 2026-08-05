from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.service_area.engine import (
    customer_safe_availability,
    transition_service_area,
)
from BACKEND.service_area.models import (
    AvailabilityOutcome,
    RideProductCode,
    ServiceArea,
    ServiceAreaState,
)

pytestmark = pytest.mark.service_area
NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)


def planned_area() -> ServiceArea:
    return ServiceArea(
        service_area_id=uuid4(),
        internal_name="internal-test-area",
        state=ServiceAreaState.PLANNED,
        created_at=NOW,
        updated_at=NOW,
    )


def test_service_area_lifecycle_and_restore_are_explicit() -> None:
    area = transition_service_area(planned_area(), ServiceAreaState.APPROVED, at=NOW)
    area = transition_service_area(area, ServiceAreaState.ACTIVE, at=NOW)
    area = transition_service_area(area, ServiceAreaState.TEMPORARILY_SUSPENDED, at=NOW)
    restored = transition_service_area(area, ServiceAreaState.ACTIVE, at=NOW)

    assert restored.state is ServiceAreaState.ACTIVE
    assert restored.version == 5


def test_invalid_lifecycle_transition_and_retired_reactivation_are_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid Service Area transition"):
        transition_service_area(planned_area(), ServiceAreaState.ACTIVE, at=NOW)
    approved = transition_service_area(
        planned_area(), ServiceAreaState.APPROVED, at=NOW
    )
    retired = transition_service_area(approved, ServiceAreaState.RETIRED, at=NOW)
    with pytest.raises(ValueError, match="Invalid Service Area transition"):
        transition_service_area(retired, ServiceAreaState.ACTIVE, at=NOW)


def test_invalid_effective_period_is_rejected() -> None:
    with pytest.raises(ValidationError, match="effective_until"):
        ServiceArea(
            service_area_id=uuid4(),
            internal_name="invalid",
            effective_from=NOW,
            effective_until=NOW,
            created_at=NOW,
            updated_at=NOW,
        )


@pytest.mark.parametrize("code", list(RideProductCode))
def test_only_approved_private_products_are_modelled(code: RideProductCode) -> None:
    assert code.value in {
        "standard",
        "premium",
        "airport_transfer",
        "accessible_private_ride",
    }


def test_customer_safe_mapping_does_not_expose_internal_evidence() -> None:
    safe = customer_safe_availability(AvailabilityOutcome.OUTSIDE_SERVICE_AREA)
    serialized = safe.model_dump_json()

    assert safe.can_book_for_trusted_person
    assert "service_area_id" not in serialized
    assert "geometry" not in serialized
    assert "internal" not in serialized


def test_unknown_location_fails_safely_without_false_promise() -> None:
    safe = customer_safe_availability(AvailabilityOutcome.UNKNOWN_OR_UNVERIFIABLE)

    assert safe.code == "location_unverifiable"
    assert "available in this area" not in safe.message
