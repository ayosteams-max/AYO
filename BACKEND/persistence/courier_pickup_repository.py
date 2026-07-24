import hashlib
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupEvent,
    CourierPickupEvidence,
    CourierPickupEvidenceKind,
    CourierPickupExceptionReason,
    CourierPickupRecord,
    CourierPickupState,
    CourierPickupView,
)
from BACKEND.persistence.tables import (
    commerce_courier_dispatch_requests,
    commerce_courier_pickup_events,
    commerce_courier_pickup_evidence,
    commerce_courier_pickup_idempotency,
    commerce_courier_pickups,
    commerce_order_outbox,
    courier_dispatch_assignments,
)

POLICY_CODE = "AYO_COURIER_PICKUP_POLICY_V1"
POLICY_VERSION = 1


class PostgresCourierPickupRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def consume_assignment(
        self, *, message_id: UUID, dispatch_id: UUID, order_id: UUID, at: datetime
    ) -> CourierPickupView:
        source = (
            self._connection.execute(
                select(
                    commerce_order_outbox.c.order_id.label("source_order_id"),
                    commerce_order_outbox.c.event_type,
                    commerce_courier_dispatch_requests.c.merchant_id,
                    commerce_courier_dispatch_requests.c.active_assignment_id,
                    courier_dispatch_assignments.c.assignment_id,
                    courier_dispatch_assignments.c.version.label("assignment_version"),
                    courier_dispatch_assignments.c.attempt_number,
                    courier_dispatch_assignments.c.courier_identity_id,
                    courier_dispatch_assignments.c.assigned_at,
                    courier_dispatch_assignments.c.state.label("assignment_state"),
                )
                .select_from(
                    commerce_order_outbox.join(
                        commerce_courier_dispatch_requests,
                        commerce_courier_dispatch_requests.c.order_id
                        == commerce_order_outbox.c.order_id,
                    ).join(
                        courier_dispatch_assignments,
                        courier_dispatch_assignments.c.assignment_id
                        == commerce_courier_dispatch_requests.c.active_assignment_id,
                    )
                )
                .where(
                    commerce_order_outbox.c.message_id == message_id,
                    commerce_courier_dispatch_requests.c.dispatch_id == dispatch_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            source is None
            or source["source_order_id"] != order_id
            or source["event_type"]
            not in {
                "commerce.courier_dispatch.courier_assigned",
                "commerce.courier_dispatch.offer_accepted",
            }
            or source["assignment_state"] != "assigned"
            or source["active_assignment_id"] != source["assignment_id"]
        ):
            raise CourierPickupConflict("assignment_event_invalid")
        pickup_id = uuid4()
        inserted = self._connection.execute(
            pg_insert(commerce_courier_pickups)
            .values(
                pickup_id=pickup_id,
                dispatch_id=dispatch_id,
                order_id=order_id,
                merchant_id=source["merchant_id"],
                assigned_courier_identity_id=source["courier_identity_id"],
                assignment_id=source["assignment_id"],
                assignment_version=source["assignment_version"],
                attempt_number=source["attempt_number"],
                assignment_message_id=message_id,
                policy_code=POLICY_CODE,
                policy_version=POLICY_VERSION,
                state=CourierPickupState.ASSIGNED.value,
                version=1,
                assigned_at=source["assigned_at"] or at,
                updated_at=at,
            )
            .on_conflict_do_nothing(
                index_elements=[commerce_courier_pickups.c.assignment_id]
            )
            .returning(commerce_courier_pickups.c.pickup_id)
        ).scalar_one_or_none()
        if inserted is None:
            existing = self.get_by_assignment(source["assignment_id"])
            if (
                existing is None
                or existing.pickup.assignment_message_id != message_id
                or existing.pickup.assignment_version != source["assignment_version"]
            ):
                raise CourierPickupConflict("assignment_event_conflict")
            return existing
        current = self.get(pickup_id)
        self._record(
            current,
            from_state=None,
            actor_id=None,
            action=None,
            reason=None,
            authority_basis="courier_dispatch_assignment",
            source_reference=source["assignment_id"],
            source_version=source["assignment_version"],
            correlation_id=dispatch_id,
            causation_id=message_id,
            at=at,
        )
        return self._required(pickup_id)

    def get(self, pickup_id: UUID, *, lock: bool = False) -> CourierPickupRecord | None:
        statement = select(commerce_courier_pickups).where(
            commerce_courier_pickups.c.pickup_id == pickup_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else CourierPickupRecord.model_validate(dict(row))

    def view(self, pickup_id: UUID) -> CourierPickupView | None:
        return None if self.get(pickup_id) is None else self._required(pickup_id)

    def get_by_assignment(self, assignment_id: UUID) -> CourierPickupView | None:
        pickup_id = self._connection.execute(
            select(commerce_courier_pickups.c.pickup_id).where(
                commerce_courier_pickups.c.assignment_id == assignment_id
            )
        ).scalar_one_or_none()
        return None if pickup_id is None else self._required(pickup_id)

    def get_by_order(self, order_id: UUID) -> CourierPickupView | None:
        pickup_id = self._connection.execute(
            select(commerce_courier_pickups.c.pickup_id)
            .where(commerce_courier_pickups.c.order_id == order_id)
            .order_by(
                commerce_courier_pickups.c.attempt_number.desc(),
                commerce_courier_pickups.c.assigned_at.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        return None if pickup_id is None else self._required(pickup_id)

    def reserve(
        self,
        *,
        actor_id: UUID,
        pickup_id: UUID,
        key: str,
        action: CourierPickupAction,
        expected_version: int,
        at: datetime,
        reason: CourierPickupExceptionReason | None = None,
    ) -> CourierPickupView | None:
        digest = hashlib.sha256(
            f"{action.value}:{expected_version}:{reason or ''}".encode()
        ).hexdigest()
        created = self._connection.execute(
            pg_insert(commerce_courier_pickup_idempotency)
            .values(
                actor_identity_id=actor_id,
                pickup_id=pickup_id,
                action=action.value,
                idempotency_key=key,
                request_hash=digest,
                response_version=None,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(commerce_courier_pickup_idempotency.c.pickup_id)
        ).scalar_one_or_none()
        if created is not None:
            return None
        row = (
            self._connection.execute(
                select(commerce_courier_pickup_idempotency).where(
                    commerce_courier_pickup_idempotency.c.actor_identity_id == actor_id,
                    commerce_courier_pickup_idempotency.c.action == action.value,
                    commerce_courier_pickup_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["pickup_id"] != pickup_id or row["request_hash"] != digest:
            raise CourierPickupConflict("idempotency_conflict")
        result = self._required(pickup_id)
        if row["response_version"] != result.pickup.version:
            raise CourierPickupConflict("idempotency_result_unavailable")
        return result

    def transition(
        self,
        current: CourierPickupRecord,
        *,
        target: CourierPickupState,
        action: CourierPickupAction,
        actor_id: UUID,
        key: str,
        at: datetime,
        reason: CourierPickupExceptionReason | None = None,
        authority_basis: str,
        acting_for_identity_id: UUID | None = None,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
        location_evidence_reference: UUID | None = None,
        location_evidence_version: int | None = None,
        location_evidence_observed_at: datetime | None = None,
    ) -> CourierPickupView:
        if current.custody_accepted_at is not None:
            raise CourierPickupConflict("pickup_authority_ended_at_custody")
        if target is CourierPickupState.ENDED_BEFORE_CUSTODY and reason is None:
            raise CourierPickupConflict("pickup_end_reason_required")
        version = current.version + 1
        waiting = (
            int((at - current.arrived_at).total_seconds())
            if target is CourierPickupState.WAITING and current.arrived_at
            else None
        )
        values: dict[str, object] = {
            "state": target.value,
            "version": version,
            "updated_at": at,
        }
        if target is CourierPickupState.TRAVELLING:
            values["travelling_at"] = at
            if action is CourierPickupAction.CORRECT_ARRIVAL:
                values.update(
                    arrived_at=None,
                    merchant_acknowledged_at=None,
                    waiting_duration_seconds=None,
                )
        elif target is CourierPickupState.ARRIVED:
            if action is CourierPickupAction.MARK_ARRIVED:
                values["arrived_at"] = at
            elif action is CourierPickupAction.CORRECT_WAITING:
                values.update(
                    merchant_acknowledged_at=None, waiting_duration_seconds=None
                )
        elif target is CourierPickupState.WAITING:
            values.update(
                merchant_acknowledged_at=at,
                waiting_duration_seconds=max(0, waiting or 0),
            )
        elif target is CourierPickupState.ENDED_BEFORE_CUSTODY:
            values["terminal_reason"] = reason.value if reason else None
        changed = self._connection.execute(
            update(commerce_courier_pickups)
            .where(
                commerce_courier_pickups.c.pickup_id == current.pickup_id,
                commerce_courier_pickups.c.state == current.state.value,
                commerce_courier_pickups.c.version == current.version,
                commerce_courier_pickups.c.custody_accepted_at.is_(None),
            )
            .values(**values)
            .returning(commerce_courier_pickups.c.pickup_id)
        ).scalar_one_or_none()
        if changed is None:
            raise CourierPickupConflict("courier_pickup_version_conflict")
        updated = self.get(current.pickup_id)
        self._record(
            updated,
            from_state=current.state,
            actor_id=actor_id,
            action=action,
            reason=reason,
            authority_basis=authority_basis,
            source_reference=current.assignment_id,
            source_version=current.assignment_version,
            acting_for_identity_id=acting_for_identity_id,
            correlation_id=correlation_id or current.dispatch_id,
            causation_id=causation_id or current.pickup_id,
            at=at,
        )
        if (
            action is CourierPickupAction.MARK_ARRIVED
            and location_evidence_reference is not None
            and location_evidence_version is not None
            and location_evidence_observed_at is not None
        ):
            self._evidence(
                updated,
                kind=CourierPickupEvidenceKind.LOCATION_CORROBORATED,
                actor_id=actor_id,
                authority_basis="source_owned_location_evidence",
                source_reference=location_evidence_reference,
                source_version=location_evidence_version,
                reason=None,
                correlation_id=correlation_id or current.dispatch_id,
                causation_id=causation_id or current.pickup_id,
                at=location_evidence_observed_at,
            )
        self._connection.execute(
            update(commerce_courier_pickup_idempotency)
            .where(
                commerce_courier_pickup_idempotency.c.actor_identity_id == actor_id,
                commerce_courier_pickup_idempotency.c.pickup_id == current.pickup_id,
                commerce_courier_pickup_idempotency.c.action == action.value,
                commerce_courier_pickup_idempotency.c.idempotency_key == key,
            )
            .values(response_version=version)
        )
        return self._required(current.pickup_id)

    def _record(
        self,
        value: CourierPickupRecord | None,
        *,
        from_state: CourierPickupState | None,
        actor_id: UUID | None,
        action: CourierPickupAction | None,
        reason: CourierPickupExceptionReason | None,
        authority_basis: str,
        source_reference: UUID | None,
        source_version: int | None,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
        acting_for_identity_id: UUID | None = None,
    ) -> None:
        if value is None:
            raise CourierPickupConflict("courier_pickup_not_found")
        kind_by_action = {
            None: CourierPickupEvidenceKind.ASSIGNMENT_ADMITTED,
            CourierPickupAction.START_TRAVEL: CourierPickupEvidenceKind.TRAVEL_STARTED,
            CourierPickupAction.MARK_ARRIVED: CourierPickupEvidenceKind.ARRIVAL_DECLARED,
            CourierPickupAction.ACKNOWLEDGE_ARRIVAL: CourierPickupEvidenceKind.MERCHANT_ACKNOWLEDGED,
            CourierPickupAction.CORRECT_ARRIVAL: CourierPickupEvidenceKind.ARRIVAL_CORRECTED,
            CourierPickupAction.CORRECT_WAITING: CourierPickupEvidenceKind.WAITING_CORRECTED,
            CourierPickupAction.END_ATTEMPT: CourierPickupEvidenceKind.ATTEMPT_ENDED,
        }
        kind = kind_by_action[action]
        event_type = f"commerce.courier_pickup.{kind.value}"
        event_id = uuid4()
        self._connection.execute(
            insert(commerce_courier_pickup_events).values(
                event_id=event_id,
                pickup_id=value.pickup_id,
                order_id=value.order_id,
                event_type=event_type,
                from_state=None if from_state is None else from_state.value,
                to_state=value.state.value,
                actor_identity_id=actor_id,
                version=value.version,
                occurred_at=at,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
        )
        self._evidence(
            value,
            kind=kind,
            actor_id=actor_id,
            acting_for_identity_id=acting_for_identity_id,
            merchant_id=(
                value.merchant_id
                if action is CourierPickupAction.ACKNOWLEDGE_ARRIVAL
                else None
            ),
            authority_basis=authority_basis,
            source_reference=source_reference,
            source_version=source_version,
            reason=reason,
            waiting_duration_seconds=(
                value.waiting_duration_seconds
                if value.state is CourierPickupState.WAITING
                else None
            ),
            correlation_id=correlation_id,
            causation_id=causation_id,
            at=at,
        )
        self._connection.execute(
            insert(commerce_order_outbox).values(
                message_id=uuid4(),
                order_id=value.order_id,
                event_type=event_type,
                safe_payload={
                    "order_id": str(value.order_id),
                    "pickup_id": str(value.pickup_id),
                    "assignment_id": (
                        None
                        if value.assignment_id is None
                        else str(value.assignment_id)
                    ),
                    "state": value.state.value,
                    "version": value.version,
                    "policy_code": value.policy_code,
                    "policy_version": value.policy_version,
                },
                occurred_at=at,
                attempt_count=0,
            )
        )

    def _evidence(
        self,
        value: CourierPickupRecord | None,
        *,
        kind: CourierPickupEvidenceKind,
        actor_id: UUID | None,
        authority_basis: str,
        source_reference: UUID | None,
        source_version: int | None,
        reason: CourierPickupExceptionReason | None,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
        acting_for_identity_id: UUID | None = None,
        merchant_id: UUID | None = None,
        waiting_duration_seconds: int | None = None,
    ) -> None:
        if value is None:
            raise CourierPickupConflict("courier_pickup_not_found")
        self._connection.execute(
            insert(commerce_courier_pickup_evidence).values(
                evidence_id=uuid4(),
                pickup_id=value.pickup_id,
                pickup_version=value.version,
                kind=kind.value,
                actor_identity_id=actor_id,
                acting_for_identity_id=acting_for_identity_id,
                merchant_id=merchant_id,
                authority_basis=authority_basis,
                source_reference=source_reference,
                source_version=source_version,
                reason=None if reason is None else reason.value,
                waiting_duration_seconds=waiting_duration_seconds,
                occurred_at=at,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
        )

    def _required(self, pickup_id: UUID) -> CourierPickupView:
        value = self.get(pickup_id)
        if value is None:
            raise CourierPickupConflict("courier_pickup_not_found")
        event_rows = self._connection.execute(
            select(commerce_courier_pickup_events)
            .where(commerce_courier_pickup_events.c.pickup_id == pickup_id)
            .order_by(commerce_courier_pickup_events.c.version)
        ).mappings()
        evidence_rows = self._connection.execute(
            select(commerce_courier_pickup_evidence)
            .where(commerce_courier_pickup_evidence.c.pickup_id == pickup_id)
            .order_by(
                commerce_courier_pickup_evidence.c.pickup_version,
                commerce_courier_pickup_evidence.c.occurred_at,
            )
        ).mappings()
        return CourierPickupView(
            pickup=value,
            events=tuple(
                CourierPickupEvent.model_validate(dict(row)) for row in event_rows
            ),
            evidence=tuple(
                CourierPickupEvidence.model_validate(dict(row)) for row in evidence_rows
            ),
        )
