import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.persistence.tables import (
    reconciliation_exceptions,
    reconciliation_records,
    settlement_approvals,
    settlement_batches,
    settlement_events,
    settlement_external_evidence,
    settlement_hold_evidence,
    settlement_idempotency,
    settlement_items,
    settlement_outbox,
)
from BACKEND.settlement.engine import (
    SettlementConflict,
    canonical_settlement_hash,
    ensure_batch_transition_allowed,
)
from BACKEND.settlement.models import (
    ReconciliationException,
    ReconciliationRecord,
    SettlementApproval,
    SettlementBatch,
    SettlementBatchState,
    SettlementExternalEvidence,
    SettlementHoldEvidence,
    SettlementItem,
)


def _batch(row: Any) -> SettlementBatch:
    return SettlementBatch.model_validate(dict(row))


def _item(row: Any) -> SettlementItem:
    return SettlementItem.model_validate(dict(row))


def _record(row: Any) -> ReconciliationRecord:
    return ReconciliationRecord.model_validate(dict(row))


def _exception(row: Any) -> ReconciliationException:
    return ReconciliationException.model_validate(dict(row))


def _approval(row: Any) -> SettlementApproval:
    return SettlementApproval.model_validate(dict(row))


def _hold_evidence(row: Any) -> SettlementHoldEvidence:
    return SettlementHoldEvidence.model_validate(dict(row))


def _external_evidence(row: Any) -> SettlementExternalEvidence:
    return SettlementExternalEvidence.model_validate(dict(row))


class PostgresSettlementRepository:
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
        digest = canonical_settlement_hash(payload)
        row = self._connection.execute(
            pg_insert(settlement_idempotency)
            .values(
                actor_id=actor_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=response_reference,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(settlement_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if row is not None:
            return cast(UUID, row)
        existing = (
            self._connection.execute(
                select(settlement_idempotency).where(
                    settlement_idempotency.c.actor_id == actor_id,
                    settlement_idempotency.c.operation == operation,
                    settlement_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if existing["request_hash"] != digest:
            raise SettlementConflict("idempotency_conflict")
        return cast(UUID, existing["response_reference"])

    def create_batch(self, batch: SettlementBatch) -> SettlementBatch:
        if batch.state is not SettlementBatchState.CREATED:
            raise SettlementConflict("settlement_batch_invalid_initial_state")
        self._connection.execute(
            insert(settlement_batches).values(**batch.model_dump(mode="json"))
        )
        self._event(
            aggregate_type="settlement_batch",
            aggregate_id=batch.settlement_batch_id,
            event_type="settlement.batch_created",
            at=batch.created_at,
            correlation_id=batch.correlation_id,
            causation_id=batch.causation_id,
            safe_payload={
                "settlement_batch_id": str(batch.settlement_batch_id),
                "state": batch.state.value,
            },
            replay_payload={"batch": batch.model_dump(mode="json")},
        )
        return batch

    def get_batch(
        self, settlement_batch_id: UUID, *, lock: bool = False
    ) -> SettlementBatch | None:
        query = select(settlement_batches).where(
            settlement_batches.c.settlement_batch_id == settlement_batch_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _batch(row)

    def transition_batch(
        self,
        *,
        settlement_batch_id: UUID,
        target_state: SettlementBatchState,
        at: datetime,
        correlation_id: UUID,
        causation_id: UUID,
        reason_code: str,
    ) -> SettlementBatch:
        current = self.get_batch(settlement_batch_id, lock=True)
        if current is None:
            raise SettlementConflict("settlement_batch_not_found")
        ensure_batch_transition_allowed(current.state, target_state, at=at)
        changed = current.model_copy(
            update={
                "state": target_state,
                "last_transition_at": at,
                "ready_for_settlement_at": at
                if target_state is SettlementBatchState.READY_FOR_SETTLEMENT
                else current.ready_for_settlement_at,
            }
        )
        self._connection.execute(
            update(settlement_batches)
            .where(settlement_batches.c.settlement_batch_id == settlement_batch_id)
            .values(
                state=changed.state.value,
                last_transition_at=changed.last_transition_at,
                ready_for_settlement_at=changed.ready_for_settlement_at,
            )
        )
        self._event(
            aggregate_type="settlement_batch",
            aggregate_id=changed.settlement_batch_id,
            event_type=f"settlement.batch_{changed.state.value}",
            at=at,
            correlation_id=correlation_id,
            causation_id=causation_id,
            safe_payload={
                "settlement_batch_id": str(changed.settlement_batch_id),
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

    def add_item(self, item: SettlementItem) -> SettlementItem:
        self._connection.execute(
            insert(settlement_items).values(**item.model_dump(mode="json"))
        )
        self._event(
            aggregate_type="settlement_item",
            aggregate_id=item.settlement_item_id,
            event_type="settlement.item_collected",
            at=item.created_at,
            correlation_id=item.settlement_item_id,
            causation_id=item.settlement_batch_id,
            safe_payload={
                "settlement_item_id": str(item.settlement_item_id),
                "settlement_batch_id": str(item.settlement_batch_id),
                "ride_id": str(item.ride_id),
                "reconciliation_type": item.reconciliation_type.value,
            },
            replay_payload={"item": item.model_dump(mode="json")},
        )
        return item

    def get_item(
        self, settlement_item_id: UUID, *, lock: bool = False
    ) -> SettlementItem | None:
        query = select(settlement_items).where(
            settlement_items.c.settlement_item_id == settlement_item_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _item(row)

    def list_items(self, settlement_batch_id: UUID) -> tuple[SettlementItem, ...]:
        rows = self._connection.execute(
            select(settlement_items)
            .where(settlement_items.c.settlement_batch_id == settlement_batch_id)
            .order_by(
                settlement_items.c.created_at, settlement_items.c.settlement_item_id
            )
        ).mappings()
        return tuple(_item(row) for row in rows)

    def append_reconciliation_record(
        self, record: ReconciliationRecord
    ) -> ReconciliationRecord:
        self._connection.execute(
            insert(reconciliation_records).values(**record.model_dump(mode="json"))
        )
        return record

    def list_reconciliation_records(
        self, settlement_batch_id: UUID
    ) -> tuple[ReconciliationRecord, ...]:
        rows = self._connection.execute(
            select(reconciliation_records)
            .where(reconciliation_records.c.settlement_batch_id == settlement_batch_id)
            .order_by(
                reconciliation_records.c.recorded_at,
                reconciliation_records.c.reconciliation_record_id,
            )
        ).mappings()
        return tuple(_record(row) for row in rows)

    def append_exception(
        self, exception: ReconciliationException
    ) -> ReconciliationException:
        self._connection.execute(
            insert(reconciliation_exceptions).values(
                **exception.model_dump(mode="json")
            )
        )
        return exception

    def list_exceptions(
        self, settlement_batch_id: UUID
    ) -> tuple[ReconciliationException, ...]:
        rows = self._connection.execute(
            select(reconciliation_exceptions)
            .where(
                reconciliation_exceptions.c.settlement_batch_id == settlement_batch_id
            )
            .order_by(
                reconciliation_exceptions.c.raised_at,
                reconciliation_exceptions.c.reconciliation_exception_id,
            )
        ).mappings()
        return tuple(_exception(row) for row in rows)

    def append_approval(self, approval: SettlementApproval) -> SettlementApproval:
        self._connection.execute(
            insert(settlement_approvals).values(**approval.model_dump(mode="json"))
        )
        return approval

    def list_approvals(
        self, settlement_batch_id: UUID
    ) -> tuple[SettlementApproval, ...]:
        rows = self._connection.execute(
            select(settlement_approvals)
            .where(settlement_approvals.c.settlement_batch_id == settlement_batch_id)
            .order_by(
                settlement_approvals.c.decided_at,
                settlement_approvals.c.settlement_approval_id,
            )
        ).mappings()
        return tuple(_approval(row) for row in rows)

    def append_hold_evidence(
        self, evidence: SettlementHoldEvidence
    ) -> SettlementHoldEvidence:
        self._connection.execute(
            insert(settlement_hold_evidence).values(**evidence.model_dump(mode="json"))
        )
        return evidence

    def list_hold_evidence(
        self, settlement_batch_id: UUID
    ) -> tuple[SettlementHoldEvidence, ...]:
        rows = self._connection.execute(
            select(settlement_hold_evidence)
            .where(
                settlement_hold_evidence.c.settlement_batch_id == settlement_batch_id
            )
            .order_by(
                settlement_hold_evidence.c.evaluated_at,
                settlement_hold_evidence.c.settlement_hold_evidence_id,
            )
        ).mappings()
        return tuple(_hold_evidence(row) for row in rows)

    def append_external_evidence(
        self, evidence: SettlementExternalEvidence
    ) -> SettlementExternalEvidence:
        self._connection.execute(
            insert(settlement_external_evidence).values(
                **evidence.model_dump(mode="json")
            )
        )
        return evidence

    def list_external_evidence(
        self, settlement_batch_id: UUID
    ) -> tuple[SettlementExternalEvidence, ...]:
        rows = self._connection.execute(
            select(settlement_external_evidence)
            .where(
                settlement_external_evidence.c.settlement_batch_id
                == settlement_batch_id
            )
            .order_by(
                settlement_external_evidence.c.recorded_at,
                settlement_external_evidence.c.settlement_external_evidence_id,
            )
        ).mappings()
        return tuple(_external_evidence(row) for row in rows)

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
            insert(settlement_events).values(
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
            insert(settlement_outbox).values(
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
        return canonical_settlement_hash(json.loads(json.dumps(payload)))
