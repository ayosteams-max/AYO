from datetime import datetime

from BACKEND.service_area.models import (
    AvailabilityOutcome,
    CustomerSafeAvailability,
    ServiceArea,
    ServiceAreaState,
)

_TRANSITIONS = {
    ServiceAreaState.PLANNED: {ServiceAreaState.APPROVED},
    ServiceAreaState.APPROVED: {ServiceAreaState.ACTIVE, ServiceAreaState.RETIRED},
    ServiceAreaState.ACTIVE: {
        ServiceAreaState.TEMPORARILY_SUSPENDED,
        ServiceAreaState.RETIRED,
    },
    ServiceAreaState.TEMPORARILY_SUSPENDED: {
        ServiceAreaState.ACTIVE,
        ServiceAreaState.RETIRED,
    },
    ServiceAreaState.RETIRED: set(),
}


def transition_service_area(
    area: ServiceArea, target: ServiceAreaState, *, at: datetime
) -> ServiceArea:
    if target not in _TRANSITIONS[area.state]:
        raise ValueError(f"Invalid Service Area transition: {area.state} -> {target}")
    return area.model_copy(
        update={"state": target, "updated_at": at, "version": area.version + 1}
    )


def customer_safe_availability(
    outcome: AvailabilityOutcome,
) -> CustomerSafeAvailability:
    if outcome is AvailabilityOutcome.AVAILABLE:
        return CustomerSafeAvailability(
            code="available",
            message="AYO is available in this area.",
            can_choose_another_area=False,
            can_book_for_trusted_person=True,
        )
    if outcome is AvailabilityOutcome.TEMPORARILY_UNAVAILABLE:
        return CustomerSafeAvailability(
            code="temporarily_unavailable",
            message="AYO is temporarily unavailable for local rides in this area.",
            can_choose_another_area=True,
            can_book_for_trusted_person=True,
        )
    if outcome is AvailabilityOutcome.UNKNOWN_OR_UNVERIFIABLE:
        return CustomerSafeAvailability(
            code="location_unverifiable",
            message="We couldn't confirm availability for this pickup. Check the pickup and try again.",
            can_choose_another_area=True,
            can_book_for_trusted_person=True,
        )
    return CustomerSafeAvailability(
        code="unavailable",
        message=(
            "AYO isn't available for local rides in this area, but you can book "
            "for someone in an AYO service area."
        ),
        can_choose_another_area=True,
        can_book_for_trusted_person=True,
    )
