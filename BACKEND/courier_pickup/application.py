from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from BACKEND.audit.models import AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.courier_pickup.engine import (
    CourierPickupConflict,
    CourierPickupPolicy,
    target_state,
)
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupExceptionReason,
    CourierPickupView,
)
from BACKEND.custody.models import CustodyState
from BACKEND.merchant.models import MerchantState


class CourierPickupApplication:
    def __init__(
        self, composition: Any, policy: CourierPickupPolicy | None = None
    ) -> None:
        self._composition = composition
        self._policy = policy or CourierPickupPolicy()

    def consume_assignment(
        self, *, message_id: UUID, dispatch_id: UUID, order_id: UUID, at: datetime
    ) -> CourierPickupView:
        with self._composition.unit_of_work() as unit:
            return unit.courier_pickup.consume_assignment(
                message_id=message_id, dispatch_id=dispatch_id, order_id=order_id, at=at
            )

    def merchant_detail(
        self, subject: AuthorizationSubject, *, merchant_id: UUID, order_id: UUID
    ) -> CourierPickupView:
        with self._composition.unit_of_work() as unit:
            merchant = unit.merchants.get_profile(merchant_id, lock=False)
            if merchant is None or merchant.owner_identity_id != subject.identity_id:
                raise CourierPickupConflict("access_denied")
            if merchant.state is not MerchantState.APPROVED:
                raise CourierPickupConflict("merchant_unavailable")
            value = unit.courier_pickup.get_by_order(order_id)
            if value is None or value.pickup.merchant_id != merchant_id:
                raise CourierPickupConflict("courier_pickup_not_found")
            return value

    def courier_detail(
        self, subject: AuthorizationSubject, *, pickup_id: UUID
    ) -> CourierPickupView:
        with self._composition.unit_of_work() as unit:
            value = unit.courier_pickup.view(pickup_id)
            if value is None:
                raise CourierPickupConflict("courier_pickup_not_found")
            if value.pickup.assigned_courier_identity_id != subject.identity_id:
                raise CourierPickupConflict("access_denied")
            return value

    def courier_command(
        self,
        subject: AuthorizationSubject,
        *,
        pickup_id: UUID,
        expected_version: int,
        action: CourierPickupAction,
        idempotency_key: str,
        at: datetime,
        reason: CourierPickupExceptionReason | None = None,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
        location_evidence_reference: UUID | None = None,
        location_evidence_version: int | None = None,
        location_evidence_observed_at: datetime | None = None,
    ) -> CourierPickupView:
        if action not in (
            CourierPickupAction.START_TRAVEL,
            CourierPickupAction.MARK_ARRIVED,
            CourierPickupAction.CORRECT_ARRIVAL,
            CourierPickupAction.END_ATTEMPT,
        ):
            raise CourierPickupConflict("merchant_acknowledgement_required")
        if action is CourierPickupAction.END_ATTEMPT and reason not in {
            CourierPickupExceptionReason.COURIER_UNABLE,
            CourierPickupExceptionReason.MERCHANT_LOCATION_UNREACHABLE,
            CourierPickupExceptionReason.MERCHANT_NOT_FOUND,
            CourierPickupExceptionReason.MERCHANT_UNAVAILABLE,
            CourierPickupExceptionReason.ORDER_NOT_READY,
            CourierPickupExceptionReason.OTHER_REVIEW,
        }:
            raise CourierPickupConflict("pickup_end_reason_not_permitted")
        supplied = (
            location_evidence_reference,
            location_evidence_version,
            location_evidence_observed_at,
        )
        if any(value is not None for value in supplied):
            if action is not CourierPickupAction.MARK_ARRIVED or any(
                value is None for value in supplied
            ):
                raise CourierPickupConflict("location_evidence_invalid")
            self._policy.validate_location_evidence(
                observed_at=cast(datetime, location_evidence_observed_at),
                evaluated_at=self._at(at),
            )
        return self._command(
            subject,
            pickup_id=pickup_id,
            expected_version=expected_version,
            action=action,
            idempotency_key=idempotency_key,
            at=at,
            merchant_id=None,
            reason=reason,
            correlation_id=correlation_id,
            causation_id=causation_id,
            location_evidence_reference=location_evidence_reference,
            location_evidence_version=location_evidence_version,
            location_evidence_observed_at=location_evidence_observed_at,
        )

    def merchant_acknowledge(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        pickup_id: UUID,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
        action: CourierPickupAction = CourierPickupAction.ACKNOWLEDGE_ARRIVAL,
        reason: CourierPickupExceptionReason | None = None,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
    ) -> CourierPickupView:
        if action not in {
            CourierPickupAction.ACKNOWLEDGE_ARRIVAL,
            CourierPickupAction.CORRECT_WAITING,
            CourierPickupAction.END_ATTEMPT,
        }:
            raise CourierPickupConflict("merchant_acknowledgement_action_required")
        return self._command(
            subject,
            pickup_id=pickup_id,
            expected_version=expected_version,
            action=action,
            idempotency_key=idempotency_key,
            at=at,
            merchant_id=merchant_id,
            reason=reason,
            correlation_id=correlation_id,
            causation_id=causation_id,
            location_evidence_reference=None,
            location_evidence_version=None,
            location_evidence_observed_at=None,
        )

    def _command(
        self,
        subject: AuthorizationSubject,
        *,
        pickup_id: UUID,
        expected_version: int,
        action: CourierPickupAction,
        idempotency_key: str,
        at: datetime,
        merchant_id: UUID | None,
        reason: CourierPickupExceptionReason | None,
        correlation_id: UUID | None,
        causation_id: UUID | None,
        location_evidence_reference: UUID | None,
        location_evidence_version: int | None,
        location_evidence_observed_at: datetime | None,
    ) -> CourierPickupView:
        with self._composition.unit_of_work() as unit:
            instant = self._at(at)
            current = unit.courier_pickup.get(pickup_id, lock=True)
            if current is None:
                raise CourierPickupConflict("courier_pickup_not_found")
            if merchant_id is None:
                if current.assigned_courier_identity_id != subject.identity_id:
                    raise CourierPickupConflict("access_denied")
                permission = {
                    CourierPickupAction.CORRECT_ARRIVAL: "courier_pickup.correct_assigned",
                    CourierPickupAction.END_ATTEMPT: "courier_pickup.close_assigned",
                }.get(action, "courier_pickup.manage_assigned")
            else:
                merchant = unit.merchants.get_profile(merchant_id, lock=False)
                if (
                    merchant is None
                    or merchant.owner_identity_id != subject.identity_id
                    or current.merchant_id != merchant_id
                ):
                    raise CourierPickupConflict("access_denied")
                permission = {
                    CourierPickupAction.CORRECT_WAITING: "courier_pickup.correct_own_merchant",
                    CourierPickupAction.END_ATTEMPT: "courier_pickup.close_own_merchant",
                }.get(action, "courier_pickup.acknowledge_own_merchant")
            if not unit.authorization.has_permission(
                subject.identity_id, permission, at=instant
            ):
                raise CourierPickupConflict("access_denied")
            custody = unit.custody.get_by_order(current.order_id)
            if custody is not None and custody.custody.state is CustodyState.ACCEPTED:
                raise CourierPickupConflict("pickup_authority_ended_at_custody")
            replay = unit.courier_pickup.reserve(
                actor_id=subject.identity_id,
                pickup_id=pickup_id,
                key=idempotency_key,
                action=action,
                expected_version=expected_version,
                at=instant,
                reason=reason,
            )
            if replay is not None:
                return replay
            if current.version != expected_version:
                raise CourierPickupConflict("courier_pickup_version_conflict")
            result = unit.courier_pickup.transition(
                current,
                target=target_state(current.state, action),
                action=action,
                actor_id=subject.identity_id,
                key=idempotency_key,
                at=instant,
                reason=reason,
                authority_basis=permission,
                acting_for_identity_id=None,
                correlation_id=correlation_id or current.dispatch_id,
                causation_id=causation_id or current.pickup_id,
                location_evidence_reference=location_evidence_reference,
                location_evidence_version=location_evidence_version,
                location_evidence_observed_at=location_evidence_observed_at,
            )
            unit.audit_events.append(
                self._audit(
                    subject,
                    result,
                    action,
                    correlation_id or current.dispatch_id,
                    causation_id or current.pickup_id,
                    idempotency_key,
                )
            )
            return result

    @staticmethod
    def _at(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("courier pickup timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _audit(
        subject: AuthorizationSubject,
        result: CourierPickupView,
        action: CourierPickupAction,
        correlation_id: UUID,
        causation_id: UUID,
        idempotency_key: str,
    ) -> AuditEvent:
        return AuditEvent(
            actor_type=subject.actor_type,
            actor_id=str(subject.identity_id),
            session_id=subject.session_id,
            action=f"courier_pickup.{action.value}",
            resource_type="courier_pickup",
            resource_id=str(result.pickup.pickup_id),
            outcome=AuditOutcome.SUCCESS,
            correlation_id=correlation_id,
            causation_id=causation_id,
            source_module="courier_pickup",
            safe_metadata={
                "operation": action.value,
                "state_to": result.pickup.state.value,
            },
            idempotency_key=idempotency_key,
        )
