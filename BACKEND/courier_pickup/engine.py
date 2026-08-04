from dataclasses import dataclass
from datetime import datetime, timedelta

from BACKEND.courier_pickup.models import CourierPickupAction, CourierPickupState


class CourierPickupConflict(ValueError):
    pass


@dataclass(frozen=True)
class CourierPickupPolicy:
    code: str = "AYO_COURIER_PICKUP_POLICY_V1"
    version: int = 1
    location_evidence_max_age: timedelta = timedelta(minutes=5)

    def validate_location_evidence(
        self, *, observed_at: datetime, evaluated_at: datetime
    ) -> None:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("location evidence timestamp must be timezone-aware")
        age = evaluated_at - observed_at
        if age < timedelta(0) or age > self.location_evidence_max_age:
            raise CourierPickupConflict("location_evidence_stale_or_invalid")


def target_state(
    state: CourierPickupState, action: CourierPickupAction
) -> CourierPickupState:
    transitions = {
        (
            CourierPickupState.ASSIGNED,
            CourierPickupAction.START_TRAVEL,
        ): CourierPickupState.TRAVELLING,
        (
            CourierPickupState.TRAVELLING,
            CourierPickupAction.MARK_ARRIVED,
        ): CourierPickupState.ARRIVED,
        (
            CourierPickupState.ARRIVED,
            CourierPickupAction.ACKNOWLEDGE_ARRIVAL,
        ): CourierPickupState.WAITING,
        (
            CourierPickupState.ARRIVED,
            CourierPickupAction.CORRECT_ARRIVAL,
        ): CourierPickupState.TRAVELLING,
        (
            CourierPickupState.WAITING,
            CourierPickupAction.CORRECT_WAITING,
        ): CourierPickupState.ARRIVED,
    }
    if (
        action is CourierPickupAction.END_ATTEMPT
        and state is not CourierPickupState.ENDED_BEFORE_CUSTODY
    ):
        return CourierPickupState.ENDED_BEFORE_CUSTODY
    try:
        return transitions[(state, action)]
    except KeyError as error:
        raise CourierPickupConflict("invalid_courier_pickup_transition") from error
