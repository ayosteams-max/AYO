import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.delivery_verification.engine import (
    DeliveryConflict,
    ReminderPolicy,
    reminder_allowed,
    target_state,
)
from BACKEND.delivery_verification.models import (
    DeliveryAction,
    DeliveryCredentialView,
    DeliveryVerificationMethod,
    DeliveryView,
)


class DeliveryApplication:
    def __init__(
        self,
        composition: Any,
        *,
        credential_pepper: bytes,
        credential_days: int = 7,
        reminder_policy: ReminderPolicy | None = None,
    ) -> None:
        if len(credential_pepper) < 32:
            raise ValueError("delivery_credential_pepper_too_short")
        self._composition = composition
        self._pepper = credential_pepper
        self._days = credential_days
        self._reminder = reminder_policy or ReminderPolicy()

    def consume_order_confirmed(
        self, *, message_id: UUID, order_id: UUID, at: datetime
    ) -> DeliveryCredentialView:
        code = self._code(order_id)
        with self._composition.unit_of_work() as unit:
            return unit.delivery.create_credential(
                message_id=message_id,
                order_id=order_id,
                code_hash=self._digest(code),
                expires_at=at + timedelta(days=self._days),
                display_code=code,
                at=at,
            )

    def consume_custody_accepted(
        self, *, message_id: UUID, custody_id: UUID, order_id: UUID, at: datetime
    ) -> DeliveryView:
        with self._composition.unit_of_work() as unit:
            return unit.delivery.activate(
                message_id=message_id, custody_id=custody_id, order_id=order_id, at=at
            )

    def credential(
        self, subject: AuthorizationSubject, *, order_id: UUID
    ) -> DeliveryCredentialView:
        with self._composition.unit_of_work() as unit:
            order = unit.orders.get_order(order_id)
            if order is None or order.customer_identity_id != subject.identity_id:
                raise DeliveryConflict("access_denied")
            return unit.delivery.credential_view(
                order_id, display_code=self._code(order_id)
            )

    def command(
        self,
        subject: AuthorizationSubject,
        *,
        delivery_id: UUID,
        expected_version: int,
        action: DeliveryAction,
        idempotency_key: str,
        at: datetime,
        code: str | None = None,
        method: DeliveryVerificationMethod | None = None,
    ) -> DeliveryView:
        with self._composition.unit_of_work() as unit:
            current = unit.delivery.get(delivery_id, lock=True)
            if current is None:
                raise DeliveryConflict("delivery_not_found")
            if current.courier_identity_id != subject.identity_id:
                raise DeliveryConflict("access_denied")
            replay = unit.delivery.reserve(
                actor_id=subject.identity_id,
                delivery_id=delivery_id,
                key=idempotency_key,
                payload=f"{action}:{expected_version}:{self._digest(code or '')}:{method or ''}",
                at=at,
            )
            if replay is not None:
                return replay
            if current.version != expected_version:
                raise DeliveryConflict("delivery_version_conflict")
            if action is DeliveryAction.VERIFY:
                if not code or method is None:
                    raise DeliveryConflict("delivery_credential_required")
                return unit.delivery.verify(
                    current,
                    target=target_state(current.state, action),
                    actor_id=subject.identity_id,
                    code_hash=self._digest(code),
                    method=method,
                    key=idempotency_key,
                    at=at,
                )
            if action not in (
                DeliveryAction.CUSTOMER_AVAILABLE,
                DeliveryAction.COMPLETE,
            ):
                raise DeliveryConflict("unsupported_delivery_action")
            result = unit.delivery.transition(
                current,
                target=target_state(current.state, action),
                actor_id=subject.identity_id,
                key=idempotency_key,
                at=at,
            )
            if action is DeliveryAction.COMPLETE:
                return unit.delivery.transition(
                    result.delivery,
                    target=target_state(result.delivery.state, DeliveryAction.CLOSE),
                    actor_id=subject.identity_id,
                    key=idempotency_key,
                    at=at,
                )
            return result

    def customer_received(
        self,
        subject: AuthorizationSubject,
        *,
        delivery_id: UUID,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
    ) -> DeliveryView:
        with self._composition.unit_of_work() as unit:
            current = unit.delivery.get(delivery_id, lock=True)
            if current is None:
                raise DeliveryConflict("delivery_not_found")
            order = unit.orders.get_order(current.order_id)
            if order is None or order.customer_identity_id != subject.identity_id:
                raise DeliveryConflict("access_denied")
            replay = unit.delivery.reserve(
                actor_id=subject.identity_id,
                delivery_id=delivery_id,
                key=idempotency_key,
                payload=f"received:{expected_version}",
                at=at,
            )
            if replay is not None:
                return replay
            if current.version != expected_version:
                raise DeliveryConflict("delivery_version_conflict")
            return unit.delivery.transition(
                current,
                target=target_state(current.state, DeliveryAction.CONFIRM_RECEIVED),
                actor_id=subject.identity_id,
                key=idempotency_key,
                at=at,
            )

    def reminder(
        self,
        *,
        delivery_id: UUID,
        eta_evidence_id: UUID,
        eta_minutes: int,
        customer_following: bool,
        at: datetime,
    ) -> bool:
        with self._composition.unit_of_work() as unit:
            sent = unit.delivery.reminder_exists(delivery_id)
            if not reminder_allowed(
                eta_minutes=eta_minutes,
                customer_following=customer_following,
                already_sent=sent,
                policy=self._reminder,
            ):
                return False
            unit.delivery.record_reminders(
                delivery_id=delivery_id,
                eta_evidence_id=eta_evidence_id,
                eta_minutes=eta_minutes,
                policy_version=self._reminder.version,
                at=at,
            )
            return True

    def _digest(self, code: str) -> str:
        return hmac.new(self._pepper, code.encode(), hashlib.sha256).hexdigest()

    def _code(self, order_id: UUID) -> str:
        return (
            base64.b32encode(
                hmac.new(
                    self._pepper, f"delivery:{order_id}".encode(), hashlib.sha256
                ).digest()[:10]
            )
            .decode()
            .rstrip("=")
        )
