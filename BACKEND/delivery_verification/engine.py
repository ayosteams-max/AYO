from dataclasses import dataclass

from BACKEND.delivery_verification.models import DeliveryAction, DeliveryState


class DeliveryConflict(ValueError):
    pass


def target_state(state: DeliveryState, action: DeliveryAction) -> DeliveryState:
    transitions = {
        (
            DeliveryState.ARRIVING,
            DeliveryAction.CUSTOMER_AVAILABLE,
        ): DeliveryState.AVAILABLE,
        (DeliveryState.AVAILABLE, DeliveryAction.VERIFY): DeliveryState.VERIFIED,
        (
            DeliveryState.VERIFIED,
            DeliveryAction.CONFIRM_RECEIVED,
        ): DeliveryState.RECEIVED,
        (DeliveryState.RECEIVED, DeliveryAction.COMPLETE): DeliveryState.COMPLETED,
        (DeliveryState.COMPLETED, DeliveryAction.CLOSE): DeliveryState.CLOSED,
    }
    try:
        return transitions[(state, action)]
    except KeyError as error:
        raise DeliveryConflict("invalid_delivery_transition") from error


@dataclass(frozen=True)
class ReminderPolicy:
    threshold_minutes: int = 20
    version: int = 1


def reminder_allowed(
    *,
    eta_minutes: int,
    customer_following: bool,
    already_sent: bool,
    policy: ReminderPolicy,
) -> bool:
    return (
        not customer_following
        and not already_sent
        and 0 <= eta_minutes <= policy.threshold_minutes
    )
