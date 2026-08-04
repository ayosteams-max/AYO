from datetime import datetime
from typing import Any
from uuid import UUID

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.merchant.models import MerchantState
from BACKEND.merchant_orders.engine import MerchantOrderConflict, transition
from BACKEND.merchant_orders.models import MerchantOrderAction, MerchantOrderView


class MerchantOrderApplication:
    def __init__(self, composition: Any) -> None:
        self._composition = composition

    def list_orders(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        state: str | None,
        limit: int,
        at: datetime,
    ) -> tuple[MerchantOrderView, ...]:
        with self._composition.unit_of_work() as unit:
            self._owned_merchant(unit, subject, merchant_id)
            return unit.merchant_orders.list_for_merchant(
                merchant_id, state=state, limit=min(max(limit, 1), 100)
            )

    def detail(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        order_id: UUID,
        at: datetime,
    ) -> MerchantOrderView:
        del at
        with self._composition.unit_of_work() as unit:
            self._owned_merchant(unit, subject, merchant_id)
            value = unit.merchant_orders.get_view(order_id)
            if value is None or value.order.merchant_id != merchant_id:
                raise MerchantOrderConflict("merchant_order_not_found")
            return value

    def decide(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        order_id: UUID,
        expected_version: int,
        action: MerchantOrderAction,
        customer_reason_code: str | None,
        customer_message: str | None,
        internal_merchant_note: str | None,
        idempotency_key: str,
        at: datetime,
    ) -> MerchantOrderView:
        if action is MerchantOrderAction.REJECT and (
            not customer_reason_code or not customer_message
        ):
            raise MerchantOrderConflict("rejection_reason_required")
        if action is MerchantOrderAction.ACCEPT and any(
            (customer_reason_code, customer_message, internal_merchant_note)
        ):
            raise MerchantOrderConflict("acceptance_rejection_fields_forbidden")
        payload = {
            "merchant_id": str(merchant_id),
            "order_id": str(order_id),
            "expected_version": expected_version,
            "action": action.value,
            "customer_reason_code": customer_reason_code,
            "customer_message": customer_message,
            "internal_merchant_note": internal_merchant_note,
        }
        with self._composition.unit_of_work() as unit:
            self._owned_merchant(unit, subject, merchant_id)
            existing_version, created = unit.merchant_orders.reserve(
                actor_id=subject.identity_id,
                merchant_id=merchant_id,
                order_id=order_id,
                key=idempotency_key,
                payload=payload,
                at=at,
            )
            if not created:
                existing = unit.merchant_orders.get_view(order_id)
                if (
                    existing is None
                    or existing.order.merchant_id != merchant_id
                    or existing.order.version != existing_version
                ):
                    raise MerchantOrderConflict("idempotency_result_unavailable")
                return existing
            current = unit.merchant_orders.get_order(order_id, lock=True)
            if current is None or current.merchant_id != merchant_id:
                raise MerchantOrderConflict("merchant_order_not_found")
            if current.version != expected_version:
                raise MerchantOrderConflict("order_version_conflict")
            target = transition(current.state, action)
            return unit.merchant_orders.transition(
                current,
                target=target,
                actor_id=subject.identity_id,
                customer_reason_code=customer_reason_code,
                customer_message=customer_message,
                internal_merchant_note=internal_merchant_note,
                idempotency_key=idempotency_key,
                at=at,
            )

    @staticmethod
    def _owned_merchant(unit: Any, subject: AuthorizationSubject, merchant_id: UUID):
        merchant = unit.merchants.get_profile(merchant_id, lock=False)
        if merchant is None or merchant.owner_identity_id != subject.identity_id:
            raise MerchantOrderConflict("access_denied")
        if merchant.state is not MerchantState.APPROVED:
            raise MerchantOrderConflict("merchant_unavailable")
        return merchant
