import hashlib
import json
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.courier_dispatch.engine import CourierDispatchConflict, DispatchPolicy
from BACKEND.courier_dispatch.models import (
    CourierAssignment,
    CourierAssignmentState,
    CourierDispatchAction,
    CourierDispatchEvent,
    CourierDispatchRequest,
    CourierDispatchState,
    CourierEligibilityEvidence,
    CourierOffer,
    CourierOfferState,
    MerchantCourierDispatchView,
)
from BACKEND.persistence.tables import (
    commerce_courier_dispatch_events,
    commerce_courier_dispatch_idempotency,
    commerce_courier_dispatch_requests,
    commerce_order_outbox,
    commerce_orders,
    courier_dispatch_assignments,
    courier_dispatch_evidence,
    courier_dispatch_offers,
    preparation_cases,
    preparation_outbox,
)


class PostgresCourierDispatchRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def consume_ready(
        self,
        *,
        message_id: UUID,
        order_id: UUID,
        merchant_id: UUID,
        policy: DispatchPolicy,
        at: datetime,
    ) -> MerchantCourierDispatchView:
        canonical_source = (
            self._connection.execute(
                select(
                    preparation_cases.c.order_id,
                    preparation_outbox.c.event_type,
                    preparation_cases.c.merchant_id,
                    preparation_cases.c.state,
                )
                .select_from(
                    preparation_outbox.join(
                        preparation_cases,
                        preparation_cases.c.preparation_case_id
                        == preparation_outbox.c.preparation_case_id,
                    )
                )
                .where(preparation_outbox.c.message_id == message_id)
            )
            .mappings()
            .one_or_none()
        )
        legacy_source = (
            self._connection.execute(
                select(
                    commerce_order_outbox.c.order_id,
                    commerce_order_outbox.c.event_type,
                    commerce_orders.c.merchant_id,
                )
                .select_from(
                    commerce_order_outbox.join(
                        commerce_orders,
                        commerce_orders.c.order_id == commerce_order_outbox.c.order_id,
                    )
                )
                .where(commerce_order_outbox.c.message_id == message_id)
            )
            .mappings()
            .one_or_none()
        )
        source = canonical_source or legacy_source
        if (
            source is None
            or source["order_id"] != order_id
            or source["merchant_id"] != merchant_id
            or source["event_type"] != "commerce.preparation.ready_for_pickup"
            or (canonical_source is not None and source["state"] != "ready_for_pickup")
        ):
            raise CourierDispatchConflict("readiness_event_invalid")
        dispatch_id = uuid4()
        inserted = self._connection.execute(
            pg_insert(commerce_courier_dispatch_requests)
            .values(
                dispatch_id=dispatch_id,
                order_id=order_id,
                merchant_id=merchant_id,
                readiness_message_id=message_id,
                state=CourierDispatchState.WAITING.value,
                version=1,
                policy_code=policy.code,
                policy_version=policy.version,
                attempt_number=0,
                active_offer_id=None,
                active_assignment_id=None,
                offered_courier_identity_id=None,
                assigned_courier_identity_id=None,
                created_at=at,
                offered_at=None,
                assigned_at=None,
                updated_at=at,
            )
            .on_conflict_do_nothing()
            .returning(commerce_courier_dispatch_requests.c.dispatch_id)
        ).scalar_one_or_none()
        if inserted is None:
            existing = self.get_by_order(order_id)
            if existing is None or existing.dispatch.readiness_message_id != message_id:
                raise CourierDispatchConflict("readiness_event_conflict")
            return existing
        self._event(
            self.get(dispatch_id),
            event_type="created",
            from_state=None,
            actor_id=None,
            correlation_id=message_id,
            causation_id=message_id,
            at=at,
        )
        self._evidence(
            self.get(dispatch_id),
            event_type="commerce.courier_dispatch.requested",
            actor_id=None,
            correlation_id=message_id,
            causation_id=message_id,
            source_evidence=(),
            at=at,
        )
        return self._required(dispatch_id)

    def get(
        self, dispatch_id: UUID, *, lock: bool = False
    ) -> CourierDispatchRequest | None:
        statement = select(commerce_courier_dispatch_requests).where(
            commerce_courier_dispatch_requests.c.dispatch_id == dispatch_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else CourierDispatchRequest.model_validate(dict(row))

    def get_by_order(self, order_id: UUID) -> MerchantCourierDispatchView | None:
        row = self._connection.execute(
            select(commerce_courier_dispatch_requests.c.dispatch_id).where(
                commerce_courier_dispatch_requests.c.order_id == order_id
            )
        ).scalar_one_or_none()
        return None if row is None else self._required(row)

    def reserve(
        self,
        *,
        actor_id: UUID | None,
        dispatch_id: UUID,
        key: str,
        action: CourierDispatchAction,
        expected_version: int,
        at: datetime,
    ) -> MerchantCourierDispatchView | None:
        digest = hashlib.sha256(
            f"{action.value}:{expected_version}".encode()
        ).hexdigest()
        created = self._connection.execute(
            pg_insert(commerce_courier_dispatch_idempotency)
            .values(
                actor_identity_id=actor_id,
                dispatch_id=dispatch_id,
                operation=action.value,
                idempotency_key=key,
                request_hash=digest,
                response_version=None,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(commerce_courier_dispatch_idempotency.c.dispatch_id)
        ).scalar_one_or_none()
        if created is not None:
            return None
        row = (
            self._connection.execute(
                select(commerce_courier_dispatch_idempotency).where(
                    commerce_courier_dispatch_idempotency.c.actor_identity_id
                    == actor_id,
                    commerce_courier_dispatch_idempotency.c.operation == action.value,
                    commerce_courier_dispatch_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["dispatch_id"] != dispatch_id or row["request_hash"] != digest:
            raise CourierDispatchConflict("idempotency_conflict")
        value = self._required(dispatch_id)
        if row["response_version"] != value.dispatch.version:
            raise CourierDispatchConflict("idempotency_result_unavailable")
        return value

    def offer(
        self,
        current: CourierDispatchRequest,
        *,
        courier_id: UUID,
        actor_id: UUID,
        target: CourierDispatchState,
        key: str,
        evidence: tuple[CourierEligibilityEvidence, ...],
        expires_at: datetime,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> MerchantCourierDispatchView:
        offer_id = uuid4()
        attempt = current.attempt_number + 1
        self._connection.execute(
            insert(courier_dispatch_offers).values(
                offer_id=offer_id,
                dispatch_id=current.dispatch_id,
                attempt_number=attempt,
                courier_identity_id=courier_id,
                state=CourierOfferState.ACTIVE.value,
                offered_at=at,
                expires_at=expires_at,
                version=1,
            )
        )
        return self._transition(
            current,
            target=target,
            actor_id=actor_id,
            offered_courier_identity_id=courier_id,
            assigned_courier_identity_id=None,
            active_offer_id=offer_id,
            active_assignment_id=None,
            attempt_number=attempt,
            key=key,
            operation=CourierDispatchAction.OFFER,
            event_suffix="offer_created",
            correlation_id=correlation_id,
            causation_id=causation_id,
            source_evidence=evidence,
            at=at,
        )

    def respond_offer(
        self,
        current: CourierDispatchRequest,
        *,
        courier_id: UUID,
        action: CourierDispatchAction,
        target: CourierDispatchState,
        key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> MerchantCourierDispatchView:
        if current.active_offer_id is None:
            raise CourierDispatchConflict("active_offer_required")
        offer_state = (
            CourierOfferState.ACCEPTED
            if action is CourierDispatchAction.ACCEPT
            else CourierOfferState.DECLINED
        )
        offer = self._connection.execute(
            update(courier_dispatch_offers)
            .where(
                courier_dispatch_offers.c.offer_id == current.active_offer_id,
                courier_dispatch_offers.c.state == CourierOfferState.ACTIVE.value,
                courier_dispatch_offers.c.courier_identity_id == courier_id,
                courier_dispatch_offers.c.expires_at > at,
            )
            .values(
                state=offer_state.value,
                resolved_at=at,
                resolution_actor_identity_id=courier_id,
                resolution_reason=offer_state.value,
                version=courier_dispatch_offers.c.version + 1,
            )
            .returning(courier_dispatch_offers.c.offer_id)
        ).scalar_one_or_none()
        if offer is None:
            raise CourierDispatchConflict("offer_terminal_outcome_conflict")
        assignment_id = None
        assigned_id = None
        if action is CourierDispatchAction.ACCEPT:
            assignment_id = uuid4()
            assigned_id = courier_id
            self._connection.execute(
                insert(courier_dispatch_assignments).values(
                    assignment_id=assignment_id,
                    dispatch_id=current.dispatch_id,
                    offer_id=current.active_offer_id,
                    attempt_number=current.attempt_number,
                    courier_identity_id=courier_id,
                    state=CourierAssignmentState.ASSIGNED.value,
                    assigned_at=at,
                    version=1,
                )
            )
        return self._transition(
            current,
            target=target,
            actor_id=courier_id,
            offered_courier_identity_id=(
                courier_id if action is CourierDispatchAction.ACCEPT else None
            ),
            assigned_courier_identity_id=assigned_id,
            active_offer_id=None,
            active_assignment_id=assignment_id,
            attempt_number=current.attempt_number,
            key=key,
            operation=action,
            event_suffix=(
                "offer_accepted"
                if action is CourierDispatchAction.ACCEPT
                else "offer_declined"
            ),
            correlation_id=correlation_id,
            causation_id=causation_id,
            source_evidence=(),
            at=at,
        )

    def authority_transition(
        self,
        current: CourierDispatchRequest,
        *,
        action: CourierDispatchAction,
        target: CourierDispatchState,
        actor_id: UUID,
        reason: str,
        key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> MerchantCourierDispatchView:
        if len(reason) < 3 or len(reason) > 80:
            raise CourierDispatchConflict("dispatch_reason_invalid")
        offered_id = current.offered_courier_identity_id
        assigned_id = current.assigned_courier_identity_id
        active_offer_id = current.active_offer_id
        active_assignment_id = current.active_assignment_id
        suffix = action.value
        if action in {CourierDispatchAction.EXPIRE, CourierDispatchAction.REVOKE}:
            if active_offer_id is None:
                raise CourierDispatchConflict("active_offer_required")
            terminal = (
                CourierOfferState.EXPIRED
                if action is CourierDispatchAction.EXPIRE
                else CourierOfferState.REVOKED
            )
            conditions = [
                courier_dispatch_offers.c.offer_id == active_offer_id,
                courier_dispatch_offers.c.state == CourierOfferState.ACTIVE.value,
            ]
            if action is CourierDispatchAction.EXPIRE:
                conditions.append(courier_dispatch_offers.c.expires_at <= at)
            changed = self._connection.execute(
                update(courier_dispatch_offers)
                .where(*conditions)
                .values(
                    state=terminal.value,
                    resolved_at=at,
                    resolution_actor_identity_id=actor_id,
                    resolution_reason=reason,
                    version=courier_dispatch_offers.c.version + 1,
                )
                .returning(courier_dispatch_offers.c.offer_id)
            ).scalar_one_or_none()
            if changed is None:
                raise CourierDispatchConflict("offer_terminal_outcome_conflict")
            offered_id = None
            active_offer_id = None
            suffix = f"offer_{terminal.value}"
        elif action is CourierDispatchAction.RELEASE:
            if active_assignment_id is None:
                raise CourierDispatchConflict("active_assignment_required")
            changed = self._connection.execute(
                update(courier_dispatch_assignments)
                .where(
                    courier_dispatch_assignments.c.assignment_id
                    == active_assignment_id,
                    courier_dispatch_assignments.c.state
                    == CourierAssignmentState.ASSIGNED.value,
                )
                .values(
                    state=CourierAssignmentState.RELEASED.value,
                    closed_at=at,
                    close_reason=reason,
                    version=courier_dispatch_assignments.c.version + 1,
                )
                .returning(courier_dispatch_assignments.c.assignment_id)
            ).scalar_one_or_none()
            if changed is None:
                raise CourierDispatchConflict("assignment_release_conflict")
            assigned_id = None
            active_assignment_id = None
            suffix = "assignment_released"
        elif action is CourierDispatchAction.CANCEL:
            if active_offer_id is not None:
                self._close_offer(active_offer_id, actor_id, reason, at)
            if active_assignment_id is not None:
                self._close_assignment(active_assignment_id, reason, at)
            offered_id = assigned_id = active_offer_id = active_assignment_id = None
            suffix = "cancelled"
        elif action is CourierDispatchAction.CONCLUDE_UNFULFILLED:
            suffix = "unfulfilled"
        return self._transition(
            current,
            target=target,
            actor_id=actor_id,
            offered_courier_identity_id=offered_id,
            assigned_courier_identity_id=assigned_id,
            active_offer_id=active_offer_id,
            active_assignment_id=active_assignment_id,
            attempt_number=current.attempt_number,
            key=key,
            operation=action,
            event_suffix=suffix,
            correlation_id=correlation_id,
            causation_id=causation_id,
            source_evidence=(),
            at=at,
        )

    def _transition(
        self,
        current: CourierDispatchRequest,
        *,
        target: CourierDispatchState,
        actor_id: UUID,
        offered_courier_identity_id: UUID | None,
        assigned_courier_identity_id: UUID | None,
        active_offer_id: UUID | None,
        active_assignment_id: UUID | None,
        attempt_number: int,
        key: str,
        operation: CourierDispatchAction,
        event_suffix: str,
        correlation_id: UUID,
        causation_id: UUID,
        source_evidence: tuple[CourierEligibilityEvidence, ...],
        at: datetime,
    ) -> MerchantCourierDispatchView:
        version = current.version + 1
        result = self._connection.execute(
            update(commerce_courier_dispatch_requests)
            .where(
                commerce_courier_dispatch_requests.c.dispatch_id == current.dispatch_id,
                commerce_courier_dispatch_requests.c.state == current.state.value,
                commerce_courier_dispatch_requests.c.version == current.version,
            )
            .values(
                state=target.value,
                version=version,
                offered_courier_identity_id=offered_courier_identity_id,
                assigned_courier_identity_id=assigned_courier_identity_id,
                active_offer_id=active_offer_id,
                active_assignment_id=active_assignment_id,
                attempt_number=attempt_number,
                offered_at=at
                if target is CourierDispatchState.OFFERED
                else current.offered_at,
                assigned_at=at if target is CourierDispatchState.ASSIGNED else None,
                updated_at=at,
            )
            .returning(commerce_courier_dispatch_requests.c.dispatch_id)
        ).scalar_one_or_none()
        if result is None:
            raise CourierDispatchConflict("courier_dispatch_version_conflict")
        updated = self.get(current.dispatch_id)
        self._event(
            updated,
            event_type=event_suffix,
            from_state=current.state,
            actor_id=actor_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            at=at,
        )
        self._evidence(
            updated,
            event_type=f"commerce.courier_dispatch.{event_suffix}",
            actor_id=actor_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            source_evidence=source_evidence,
            at=at,
        )
        self._connection.execute(
            update(commerce_courier_dispatch_idempotency)
            .where(
                commerce_courier_dispatch_idempotency.c.actor_identity_id == actor_id,
                commerce_courier_dispatch_idempotency.c.dispatch_id
                == current.dispatch_id,
                commerce_courier_dispatch_idempotency.c.operation == operation.value,
                commerce_courier_dispatch_idempotency.c.idempotency_key == key,
            )
            .values(response_version=version)
        )
        return self._required(current.dispatch_id)

    def _event(
        self,
        value: CourierDispatchRequest | None,
        *,
        event_type: str,
        from_state: CourierDispatchState | None,
        actor_id: UUID | None,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> None:
        if value is None:
            raise CourierDispatchConflict("courier_dispatch_not_found")
        self._connection.execute(
            insert(commerce_courier_dispatch_events).values(
                event_id=uuid4(),
                dispatch_id=value.dispatch_id,
                order_id=value.order_id,
                event_type=f"commerce.courier_dispatch.{event_type}",
                from_state=None if from_state is None else from_state.value,
                to_state=value.state.value,
                actor_identity_id=actor_id,
                version=value.version,
                occurred_at=at,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
        )
        self._connection.execute(
            insert(commerce_order_outbox).values(
                message_id=uuid4(),
                order_id=value.order_id,
                event_type=f"commerce.courier_dispatch.{event_type}",
                safe_payload={
                    "order_id": str(value.order_id),
                    "dispatch_id": str(value.dispatch_id),
                    "state": value.state.value,
                    "version": value.version,
                    "correlation_id": str(correlation_id),
                    "causation_id": str(causation_id),
                },
                occurred_at=at,
                attempt_count=0,
            )
        )

    def _required(self, dispatch_id: UUID) -> MerchantCourierDispatchView:
        value = self.get(dispatch_id)
        if value is None:
            raise CourierDispatchConflict("courier_dispatch_not_found")
        rows = self._connection.execute(
            select(commerce_courier_dispatch_events)
            .where(commerce_courier_dispatch_events.c.dispatch_id == dispatch_id)
            .order_by(commerce_courier_dispatch_events.c.version)
        ).mappings()
        offers = self._connection.execute(
            select(courier_dispatch_offers)
            .where(courier_dispatch_offers.c.dispatch_id == dispatch_id)
            .order_by(courier_dispatch_offers.c.attempt_number)
        ).mappings()
        assignments = self._connection.execute(
            select(courier_dispatch_assignments)
            .where(courier_dispatch_assignments.c.dispatch_id == dispatch_id)
            .order_by(courier_dispatch_assignments.c.attempt_number)
        ).mappings()
        return MerchantCourierDispatchView(
            dispatch=value,
            events=tuple(
                CourierDispatchEvent.model_validate(dict(row)) for row in rows
            ),
            offers=tuple(CourierOffer.model_validate(dict(row)) for row in offers),
            assignments=tuple(
                CourierAssignment.model_validate(dict(row)) for row in assignments
            ),
        )

    def _close_offer(
        self, offer_id: UUID, actor_id: UUID, reason: str, at: datetime
    ) -> None:
        changed = self._connection.execute(
            update(courier_dispatch_offers)
            .where(
                courier_dispatch_offers.c.offer_id == offer_id,
                courier_dispatch_offers.c.state == CourierOfferState.ACTIVE.value,
            )
            .values(
                state=CourierOfferState.REVOKED.value,
                resolved_at=at,
                resolution_actor_identity_id=actor_id,
                resolution_reason=reason,
                version=courier_dispatch_offers.c.version + 1,
            )
            .returning(courier_dispatch_offers.c.offer_id)
        ).scalar_one_or_none()
        if changed is None:
            raise CourierDispatchConflict("offer_terminal_outcome_conflict")

    def _close_assignment(self, assignment_id: UUID, reason: str, at: datetime) -> None:
        changed = self._connection.execute(
            update(courier_dispatch_assignments)
            .where(
                courier_dispatch_assignments.c.assignment_id == assignment_id,
                courier_dispatch_assignments.c.state
                == CourierAssignmentState.ASSIGNED.value,
            )
            .values(
                state=CourierAssignmentState.CANCELLED.value,
                closed_at=at,
                close_reason=reason,
                version=courier_dispatch_assignments.c.version + 1,
            )
            .returning(courier_dispatch_assignments.c.assignment_id)
        ).scalar_one_or_none()
        if changed is None:
            raise CourierDispatchConflict("assignment_cancel_conflict")

    def _evidence(
        self,
        value: CourierDispatchRequest | None,
        *,
        event_type: str,
        actor_id: UUID | None,
        correlation_id: UUID,
        causation_id: UUID,
        source_evidence: tuple[CourierEligibilityEvidence, ...],
        at: datetime,
    ) -> None:
        if value is None:
            raise CourierDispatchConflict("courier_dispatch_not_found")
        sources = [item.model_dump(mode="json") for item in source_evidence]
        payload = {
            "dispatch_id": str(value.dispatch_id),
            "version": value.version,
            "event_type": event_type,
            "actor": None if actor_id is None else str(actor_id),
            "sources": sources,
            "policy": [value.policy_code, value.policy_version],
            "correlation_id": str(correlation_id),
            "causation_id": str(causation_id),
            "occurred_at": at.isoformat(),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self._connection.execute(
            insert(courier_dispatch_evidence).values(
                evidence_id=uuid4(),
                dispatch_id=value.dispatch_id,
                dispatch_version=value.version,
                event_type=event_type,
                actor_identity_id=actor_id,
                source_evidence=sources,
                policy_code=value.policy_code,
                policy_version=value.policy_version,
                decision_outcome=value.state.value,
                correlation_id=correlation_id,
                causation_id=causation_id,
                occurred_at=at,
                evidence_hash=digest,
            )
        )
