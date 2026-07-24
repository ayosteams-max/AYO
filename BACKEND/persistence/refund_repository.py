import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.persistence.tables import (
    refund_authorizations,
    refund_decisions,
    refund_events,
    refund_evidence,
    refund_idempotency,
    refund_outbox,
    refund_requests,
)
from BACKEND.refund.engine import (
    RefundConflict,
    canonical_refund_hash,
    ensure_request_transition_allowed,
)
from BACKEND.refund.models import (
    RefundAuthorization,
    RefundDecision,
    RefundEvidence,
    RefundRequest,
    RefundRequestState,
)


def _request(row: Any) -> RefundRequest:
    return RefundRequest.model_validate(dict(row))


def _decision(row: Any) -> RefundDecision:
    return RefundDecision.model_validate(dict(row))


def _authorization(row: Any) -> RefundAuthorization:
    return RefundAuthorization.model_validate(dict(row))


def _evidence(row: Any) -> RefundEvidence:
    return RefundEvidence.model_validate(dict(row))


class PostgresRefundRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve_idempotency(
        self,
        *,
        actor_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, str],
        response_reference: UUID,
        at: datetime,
    ) -> UUID:
        digest = canonical_refund_hash(payload)
        row = self._connection.execute(
            pg_insert(refund_idempotency)
            .values(
                actor_id=actor_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=response_reference,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(refund_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if row is not None:
            return cast(UUID, row)
        existing = (
            self._connection.execute(
                select(refund_idempotency).where(
                    refund_idempotency.c.actor_id == actor_id,
                    refund_idempotency.c.operation == operation,
                    refund_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if existing["request_hash"] != digest:
            raise RefundConflict("idempotency_conflict")
        return cast(UUID, existing["response_reference"])

    def create_request(self, request: RefundRequest) -> RefundRequest:
        if request.state is not RefundRequestState.REQUESTED:
            raise RefundConflict("refund_request_invalid_initial_state")
        self._connection.execute(
            insert(refund_requests).values(**request.model_dump(mode="json"))
        )
        self._event(
            aggregate_type="refund_request",
            aggregate_id=request.refund_request_id,
            event_type="refund.request_created",
            at=request.requested_at,
            correlation_id=request.correlation_id,
            causation_id=request.causation_id,
            safe_payload={
                "refund_request_id": str(request.refund_request_id),
                "ride_id": str(request.ride_id),
                "amount_minor": request.amount_minor,
                "currency": request.currency,
                "refund_type": request.refund_type.value,
            },
            replay_payload={"request": request.model_dump(mode="json")},
        )
        return request

    def get_request(
        self, refund_request_id: UUID, *, lock: bool = False
    ) -> RefundRequest | None:
        query = select(refund_requests).where(
            refund_requests.c.refund_request_id == refund_request_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _request(row)

    def transition_request(
        self,
        *,
        refund_request_id: UUID,
        target_state: RefundRequestState,
        at: datetime,
        correlation_id: UUID,
        causation_id: UUID,
        reason_code: str,
    ) -> RefundRequest:
        current = self.get_request(refund_request_id, lock=True)
        if current is None:
            raise RefundConflict("refund_request_not_found")
        ensure_request_transition_allowed(current.state, target_state, at=at)
        changed = current.model_copy(
            update={
                "state": target_state,
                "last_transition_at": at,
                "completed_at": at
                if target_state is RefundRequestState.COMPLETED
                else current.completed_at,
                "rejected_at": at
                if target_state is RefundRequestState.REJECTED
                else current.rejected_at,
            }
        )
        self._connection.execute(
            update(refund_requests)
            .where(refund_requests.c.refund_request_id == refund_request_id)
            .values(
                state=changed.state.value,
                last_transition_at=changed.last_transition_at,
                completed_at=changed.completed_at,
                rejected_at=changed.rejected_at,
            )
        )
        self._event(
            aggregate_type="refund_request",
            aggregate_id=changed.refund_request_id,
            event_type=f"refund.request_{changed.state.value}",
            at=at,
            correlation_id=correlation_id,
            causation_id=causation_id,
            safe_payload={
                "refund_request_id": str(changed.refund_request_id),
                "ride_id": str(changed.ride_id),
                "state": changed.state.value,
                "reason_code": reason_code,
            },
            replay_payload={
                "from_state": current.state.value,
                "to_state": changed.state.value,
                "reason_code": reason_code,
            },
        )
        return changed

    def append_decision(self, decision: RefundDecision) -> RefundDecision:
        self._connection.execute(
            insert(refund_decisions).values(**decision.model_dump(mode="json"))
        )
        return decision

    def append_authorization(
        self, authorization: RefundAuthorization
    ) -> RefundAuthorization:
        self._connection.execute(
            insert(refund_authorizations).values(
                **authorization.model_dump(mode="json")
            )
        )
        return authorization

    def append_evidence(self, evidence: RefundEvidence) -> RefundEvidence:
        self._connection.execute(
            insert(refund_evidence).values(**evidence.model_dump(mode="json"))
        )
        return evidence

    def list_decisions(self, refund_request_id: UUID) -> tuple[RefundDecision, ...]:
        rows = self._connection.execute(
            select(refund_decisions)
            .where(refund_decisions.c.refund_request_id == refund_request_id)
            .order_by(refund_decisions.c.decided_at, refund_decisions.c.decision_id)
        ).mappings()
        return tuple(_decision(row) for row in rows)

    def list_authorizations(
        self, refund_request_id: UUID
    ) -> tuple[RefundAuthorization, ...]:
        rows = self._connection.execute(
            select(refund_authorizations)
            .where(refund_authorizations.c.refund_request_id == refund_request_id)
            .order_by(
                refund_authorizations.c.authorized_at,
                refund_authorizations.c.authorization_id,
            )
        ).mappings()
        return tuple(_authorization(row) for row in rows)

    def list_evidence(self, refund_request_id: UUID) -> tuple[RefundEvidence, ...]:
        rows = self._connection.execute(
            select(refund_evidence)
            .where(refund_evidence.c.refund_request_id == refund_request_id)
            .order_by(refund_evidence.c.recorded_at, refund_evidence.c.evidence_id)
        ).mappings()
        return tuple(_evidence(row) for row in rows)

    def list_requests_for_ride(self, ride_id: UUID) -> tuple[RefundRequest, ...]:
        rows = self._connection.execute(
            select(refund_requests)
            .where(refund_requests.c.ride_id == ride_id)
            .order_by(
                refund_requests.c.requested_at, refund_requests.c.refund_request_id
            )
        ).mappings()
        return tuple(_request(row) for row in rows)

    def _event(
        self,
        *,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        at: datetime,
        correlation_id: UUID,
        causation_id: UUID,
        safe_payload: dict[str, Any],
        replay_payload: dict[str, Any],
    ) -> None:
        event_id = uuid4()
        self._connection.execute(
            insert(refund_events).values(
                event_id=event_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                schema_version=1,
                safe_payload=safe_payload,
                replay_payload=replay_payload,
                occurred_at=at,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
        )
        self._connection.execute(
            insert(refund_outbox).values(
                message_id=uuid4(),
                event_id=event_id,
                event_type=event_type,
                safe_payload=safe_payload,
                occurred_at=at,
                available_at=at,
                attempt_count=0,
            )
        )

    @staticmethod
    def payload_hash(payload: dict[str, Any]) -> str:
        return canonical_refund_hash(json.loads(json.dumps(payload)))
