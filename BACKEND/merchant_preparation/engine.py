from BACKEND.merchant_preparation.models import PreparationAction
from BACKEND.ordering.models import OrderState


class PreparationConflict(Exception):
    pass


def target_state(current: OrderState, action: PreparationAction) -> OrderState:
    allowed = {
        (OrderState.ACCEPTED, PreparationAction.START): OrderState.PREPARING,
        (OrderState.PREPARING, PreparationAction.UPDATE_PROGRESS): OrderState.PREPARING,
        (
            OrderState.PREPARING,
            PreparationAction.MARK_READY,
        ): OrderState.READY_FOR_PICKUP,
    }
    try:
        return allowed[(current, action)]
    except KeyError as error:
        raise PreparationConflict("preparation_transition_not_allowed") from error


def validate_progress(current: int, requested: int) -> int:
    if requested < 1 or requested > 99:
        raise PreparationConflict("preparation_progress_invalid")
    if requested <= current:
        raise PreparationConflict("preparation_progress_not_increasing")
    return requested
