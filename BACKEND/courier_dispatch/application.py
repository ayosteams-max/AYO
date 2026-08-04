from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from BACKEND.audit.models import AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.courier_dispatch.engine import (
    CourierDispatchConflict,
    DispatchPolicy,
    target_state,
)
from BACKEND.courier_dispatch.models import (
    CourierDispatchAction,
    CourierEligibilityEvidence,
    MerchantCourierDispatchView,
)
from BACKEND.custody.models import CustodyState
from BACKEND.merchant.models import MerchantState


class CourierDispatchApplication:
    def __init__(self, composition: Any, policy: DispatchPolicy | None = None) -> None:
        self._composition = composition
        self._policy = policy or DispatchPolicy()

    def consume_merchant_ready(
        self,
        subject: AuthorizationSubject,
        *,
        message_id: UUID,
        order_id: UUID,
        merchant_id: UUID,
        event_type: str,
        at: datetime,
    ) -> MerchantCourierDispatchView:
        if event_type != "commerce.preparation.ready_for_pickup":
            raise CourierDispatchConflict("unsupported_readiness_event")
        with self._composition.unit_of_work() as unit:
            instant = self._at(at)
            if not unit.authorization.has_permission(
                subject.identity_id, "courier_dispatch.admit", at=instant
            ):
                raise CourierDispatchConflict("access_denied")
            result = unit.courier_dispatch.consume_ready(
                message_id=message_id,
                order_id=order_id,
                merchant_id=merchant_id,
                policy=self._policy,
                at=instant,
            )
            unit.audit_events.append(
                self._audit(
                    subject,
                    result,
                    "admit",
                    message_id,
                    message_id,
                    f"readiness:{message_id}",
                )
            )
            return result

    def merchant_detail(
        self, subject: AuthorizationSubject, *, merchant_id: UUID, order_id: UUID
    ) -> MerchantCourierDispatchView:
        with self._composition.unit_of_work() as unit:
            merchant = unit.merchants.get_profile(merchant_id, lock=False)
            if merchant is None or merchant.owner_identity_id != subject.identity_id:
                raise CourierDispatchConflict("access_denied")
            if merchant.state is not MerchantState.APPROVED:
                raise CourierDispatchConflict("merchant_unavailable")
            value = unit.courier_dispatch.get_by_order(order_id)
            if value is None or value.dispatch.merchant_id != merchant_id:
                raise CourierDispatchConflict("courier_dispatch_not_found")
            return value

    def command(
        self,
        subject: AuthorizationSubject,
        *,
        dispatch_id: UUID,
        expected_version: int,
        action: CourierDispatchAction,
        courier_identity_id: UUID,
        idempotency_key: str,
        at: datetime,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
    ) -> MerchantCourierDispatchView:
        if action not in {
            CourierDispatchAction.ACCEPT,
            CourierDispatchAction.DECLINE,
        }:
            raise CourierDispatchConflict("offer_requires_dispatch_authority")
        if subject.identity_id != courier_identity_id:
            raise CourierDispatchConflict("access_denied")
        with self._composition.unit_of_work() as unit:
            current = unit.courier_dispatch.get(dispatch_id, lock=True)
            if current is None:
                raise CourierDispatchConflict("courier_dispatch_not_found")
            replay = unit.courier_dispatch.reserve(
                actor_id=subject.identity_id,
                dispatch_id=dispatch_id,
                key=idempotency_key,
                action=action,
                expected_version=expected_version,
                at=at,
            )
            if replay is not None:
                return replay
            if current.version != expected_version:
                raise CourierDispatchConflict("courier_dispatch_version_conflict")
            target = target_state(current.state, action)
            if current.offered_courier_identity_id != courier_identity_id:
                raise CourierDispatchConflict("courier_offer_not_owned")
            result = unit.courier_dispatch.respond_offer(
                current,
                courier_id=courier_identity_id,
                action=action,
                target=target,
                key=idempotency_key,
                at=self._at(at),
                correlation_id=correlation_id or current.dispatch_id,
                causation_id=causation_id
                or current.active_offer_id
                or current.dispatch_id,
            )
            unit.audit_events.append(
                self._audit(
                    subject,
                    result,
                    action.value,
                    correlation_id or current.dispatch_id,
                    causation_id or current.active_offer_id or current.dispatch_id,
                    idempotency_key,
                )
            )
            return result

    def offer_courier(
        self,
        subject: AuthorizationSubject,
        *,
        dispatch_id: UUID,
        expected_version: int,
        eligible_courier_identity_id: UUID,
        eligibility_evidence: tuple[CourierEligibilityEvidence, ...],
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> MerchantCourierDispatchView:
        """Dispatch decision over explicit source-owned evidence."""
        instant = self._at(at)
        evaluated = self._policy.evaluate(eligibility_evidence, at=instant)
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "courier_dispatch.manage", at=instant
            ):
                raise CourierDispatchConflict("access_denied")
            current = unit.courier_dispatch.get(dispatch_id, lock=True)
            if current is None:
                raise CourierDispatchConflict("courier_dispatch_not_found")
            replay = unit.courier_dispatch.reserve(
                actor_id=subject.identity_id,
                dispatch_id=dispatch_id,
                key=idempotency_key,
                action=CourierDispatchAction.OFFER,
                expected_version=expected_version,
                at=at,
            )
            if replay is not None:
                return replay
            if current.version != expected_version:
                raise CourierDispatchConflict("courier_dispatch_version_conflict")
            target = target_state(current.state, CourierDispatchAction.OFFER)
            result = unit.courier_dispatch.offer(
                current,
                courier_id=eligible_courier_identity_id,
                actor_id=subject.identity_id,
                target=target,
                key=idempotency_key,
                evidence=evaluated,
                expires_at=self._policy.expires_at(instant),
                correlation_id=correlation_id,
                causation_id=causation_id,
                at=instant,
            )
            unit.audit_events.append(
                self._audit(
                    subject,
                    result,
                    "offer",
                    correlation_id,
                    causation_id,
                    idempotency_key,
                )
            )
            return result

    def authority_command(
        self,
        subject: AuthorizationSubject,
        *,
        dispatch_id: UUID,
        expected_version: int,
        action: CourierDispatchAction,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        reason: str,
        at: datetime,
    ) -> MerchantCourierDispatchView:
        if action not in {
            CourierDispatchAction.EXPIRE,
            CourierDispatchAction.REVOKE,
            CourierDispatchAction.RELEASE,
            CourierDispatchAction.CANCEL,
            CourierDispatchAction.CONCLUDE_UNFULFILLED,
        }:
            raise CourierDispatchConflict("dispatch_authority_action_invalid")
        instant = self._at(at)
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "courier_dispatch.manage", at=instant
            ):
                raise CourierDispatchConflict("access_denied")
            current = unit.courier_dispatch.get(dispatch_id, lock=True)
            if current is None:
                raise CourierDispatchConflict("courier_dispatch_not_found")
            replay = unit.courier_dispatch.reserve(
                actor_id=subject.identity_id,
                dispatch_id=dispatch_id,
                key=idempotency_key,
                action=action,
                expected_version=expected_version,
                at=instant,
            )
            if replay is not None:
                return replay
            if current.version != expected_version:
                raise CourierDispatchConflict("courier_dispatch_version_conflict")
            if action in {
                CourierDispatchAction.RELEASE,
                CourierDispatchAction.CANCEL,
            }:
                custody = unit.custody.get_by_order(current.order_id)
                if (
                    custody is not None
                    and custody.custody.state is CustodyState.ACCEPTED
                ):
                    raise CourierDispatchConflict("dispatch_authority_ended_at_custody")
            target = target_state(current.state, action)
            result = unit.courier_dispatch.authority_transition(
                current,
                action=action,
                target=target,
                actor_id=subject.identity_id,
                reason=reason,
                key=idempotency_key,
                correlation_id=correlation_id,
                causation_id=causation_id,
                at=instant,
            )
            unit.audit_events.append(
                self._audit(
                    subject,
                    result,
                    action.value,
                    correlation_id,
                    causation_id,
                    idempotency_key,
                )
            )
            return result

    @staticmethod
    def _at(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("courier dispatch timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _audit(
        subject: AuthorizationSubject,
        result: MerchantCourierDispatchView,
        action: str,
        correlation_id: UUID,
        causation_id: UUID,
        idempotency_key: str,
    ) -> AuditEvent:
        return AuditEvent(
            actor_type=subject.actor_type,
            actor_id=str(subject.identity_id),
            session_id=subject.session_id,
            action=f"courier_dispatch.{action}",
            resource_type="courier_dispatch",
            resource_id=str(result.dispatch.dispatch_id),
            outcome=AuditOutcome.SUCCESS,
            correlation_id=correlation_id,
            causation_id=causation_id,
            source_module="courier_dispatch",
            safe_metadata={
                "operation": action,
                "state_to": result.dispatch.state.value,
            },
            idempotency_key=idempotency_key,
        )
