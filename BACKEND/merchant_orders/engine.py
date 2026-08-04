from datetime import datetime

from BACKEND.merchant_orders.models import (
    MerchantDecisionCase,
    MerchantDecisionState,
    MerchantOrderAction,
)
from BACKEND.ordering.models import OrderState


class MerchantOrderConflict(Exception):
    pass


def transition(current: OrderState, action: MerchantOrderAction) -> OrderState:
    if current is not OrderState.WAITING_FOR_MERCHANT_CONFIRMATION:
        raise MerchantOrderConflict("order_transition_not_allowed")
    return (
        OrderState.ACCEPTED
        if action is MerchantOrderAction.ACCEPT
        else OrderState.REJECTED
    )


def decision_transition(
    current: MerchantDecisionCase,
    target: MerchantDecisionState,
    *,
    at: datetime,
) -> MerchantDecisionState:
    if current.state is not MerchantDecisionState.PENDING:
        raise MerchantOrderConflict("merchant_decision_transition_not_allowed")
    if target is MerchantDecisionState.PENDING:
        raise MerchantOrderConflict("merchant_decision_transition_not_allowed")
    if target is MerchantDecisionState.EXPIRED:
        if at < current.expires_at:
            raise MerchantOrderConflict("merchant_decision_window_active")
    elif at >= current.expires_at:
        raise MerchantOrderConflict("merchant_decision_window_expired")
    return target
