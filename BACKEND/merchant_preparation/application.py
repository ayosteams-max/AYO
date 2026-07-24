from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.merchant.models import MerchantState
from BACKEND.merchant_preparation.engine import (
    PreparationConflict,
    target_state,
    validate_progress,
)
from BACKEND.merchant_preparation.models import PreparationAction, PreparationView


class MerchantPreparationApplication:
    def __init__(self, composition: Any) -> None:
        self._composition = composition

    def detail(
        self, subject: AuthorizationSubject, *, merchant_id: UUID, order_id: UUID
    ) -> PreparationView:
        with self._composition.unit_of_work() as unit:
            self._owned(unit, subject, merchant_id)
            value = unit.preparation.get_view(order_id)
            if value is None or value.order.order.merchant_id != merchant_id:
                raise PreparationConflict("preparation_order_not_found")
            return value

    def command(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        order_id: UUID,
        expected_version: int,
        action: PreparationAction,
        estimated_duration_minutes: int | None,
        progress_percent: int | None,
        delay_reason_code: str | None,
        delay_message: str | None,
        idempotency_key: str,
        at: datetime,
    ) -> PreparationView:
        if (delay_reason_code is None) != (delay_message is None):
            raise PreparationConflict("preparation_delay_reason_incomplete")
        if action is PreparationAction.START and estimated_duration_minutes is None:
            raise PreparationConflict("preparation_estimate_required")
        if (
            estimated_duration_minutes is not None
            and not 1 <= estimated_duration_minutes <= 240
        ):
            raise PreparationConflict("preparation_estimate_invalid")
        if action is PreparationAction.UPDATE_PROGRESS and progress_percent is None:
            raise PreparationConflict("preparation_progress_required")
        if (
            action is not PreparationAction.START
            and estimated_duration_minutes is not None
        ):
            raise PreparationConflict("preparation_estimate_not_allowed")
        if action is not PreparationAction.UPDATE_PROGRESS and any(
            (progress_percent is not None, delay_reason_code, delay_message)
        ):
            raise PreparationConflict("preparation_progress_fields_not_allowed")
        payload = {
            "merchant_id": str(merchant_id),
            "order_id": str(order_id),
            "expected_version": expected_version,
            "action": action.value,
            "estimated_duration_minutes": estimated_duration_minutes,
            "progress_percent": progress_percent,
            "delay_reason_code": delay_reason_code,
            "delay_message": delay_message,
        }
        with self._composition.unit_of_work() as unit:
            self._owned(unit, subject, merchant_id)
            response_version, created = unit.preparation.reserve(
                actor_id=subject.identity_id,
                merchant_id=merchant_id,
                order_id=order_id,
                key=idempotency_key,
                payload=payload,
                at=at,
            )
            if not created:
                existing = unit.preparation.get_view(order_id)
                if (
                    existing is None
                    or existing.order.order.version != response_version
                    or existing.order.order.merchant_id != merchant_id
                ):
                    raise PreparationConflict("idempotency_result_unavailable")
                return existing
            order = unit.merchant_orders.get_order(order_id, lock=True)
            if order is None or order.merchant_id != merchant_id:
                raise PreparationConflict("preparation_order_not_found")
            if order.version != expected_version:
                raise PreparationConflict("order_version_conflict")
            target = target_state(order.state, action)
            current = unit.preparation.get_record(order_id, lock=True)
            if action is PreparationAction.START:
                if current is not None:
                    raise PreparationConflict("preparation_already_started")
                seconds = int(estimated_duration_minutes or 0) * 60
                return unit.preparation.start(
                    order,
                    actor_id=subject.identity_id,
                    estimated_duration_seconds=seconds,
                    estimated_ready_at=at + timedelta(seconds=seconds),
                    idempotency_key=idempotency_key,
                    at=at,
                )
            if current is None:
                raise PreparationConflict("preparation_not_started")
            if action is PreparationAction.UPDATE_PROGRESS:
                progress = validate_progress(
                    current.progress_percent, int(progress_percent or 0)
                )
                return unit.preparation.progress(
                    order,
                    current=current,
                    progress_percent=progress,
                    actor_id=subject.identity_id,
                    delay_reason_code=delay_reason_code,
                    delay_message=delay_message,
                    idempotency_key=idempotency_key,
                    at=at,
                )
            return unit.preparation.ready(
                order,
                current=current,
                actor_id=subject.identity_id,
                idempotency_key=idempotency_key,
                at=at,
                target=target,
            )

    @staticmethod
    def _owned(unit: Any, subject: AuthorizationSubject, merchant_id: UUID):
        merchant = unit.merchants.get_profile(merchant_id, lock=False)
        if merchant is None or merchant.owner_identity_id != subject.identity_id:
            raise PreparationConflict("access_denied")
        if merchant.state is not MerchantState.APPROVED:
            raise PreparationConflict("merchant_unavailable")
        return merchant
