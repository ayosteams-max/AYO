import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.financial_control.engine import FinancialHoldConflict, canonical_hold_hash
from BACKEND.financial_control.models import (
    FinancialHold,
    FinancialHoldSourceType,
    FinancialHoldState,
    FinancialHoldStateHistory,
)
from BACKEND.persistence.tables import (
    financial_hold_events,
    financial_hold_idempotency,
    financial_hold_outbox,
    financial_hold_state_history,
    financial_holds,
)


def _hold(row: Any) -> FinancialHold:
    return FinancialHold.model_validate(dict(row))


def _history(row: Any) -> FinancialHoldStateHistory:
    return FinancialHoldStateHistory.model_validate(dict(row))


class PostgresFinancialHoldRepository:
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
        digest = canonical_hold_hash(payload)
        row = self._connection.execute(
            pg_insert(financial_hold_idempotency)
            .values(
                actor_id=actor_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=response_reference,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(financial_hold_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if row is not None:
            return cast(UUID, row)
        existing = (
            self._connection.execute(
                select(financial_hold_idempotency).where(
                    financial_hold_idempotency.c.actor_id == actor_id,
                    financial_hold_idempotency.c.operation == operation,
                    financial_hold_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if existing["request_hash"] != digest:
            raise FinancialHoldConflict("idempotency_conflict")
        return cast(UUID, existing["response_reference"])

    def get_hold(self, hold_id: UUID, *, lock: bool = False) -> FinancialHold | None:
        query = select(financial_holds).where(financial_holds.c.hold_id == hold_id)
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _hold(row)

    def list_holds_for_source(
        self, *, source_type: FinancialHoldSourceType, source_id: UUID
    ) -> tuple[FinancialHold, ...]:
        rows = self._connection.execute(
            select(financial_holds)
            .where(
                financial_holds.c.source_type == source_type.value,
                financial_holds.c.source_id == source_id,
            )
            .order_by(financial_holds.c.created_at, financial_holds.c.hold_id)
        ).mappings()
        return tuple(_hold(row) for row in rows)

    def create_hold(
        self,
        hold: FinancialHold,
        initial_history: FinancialHoldStateHistory,
    ) -> FinancialHold:
        self._connection.execute(
            insert(financial_holds).values(**hold.model_dump(mode="json"))
        )
        self._connection.execute(
            insert(financial_hold_state_history).values(
                **initial_history.model_dump(mode="json")
            )
        )
        self._event(
            hold_id=hold.hold_id,
            event_type="financial_hold.created",
            at=initial_history.changed_at,
            correlation_id=initial_history.correlation_id,
            causation_id=initial_history.causation_id,
            safe_payload={
                "hold_id": str(hold.hold_id),
                "hold_type": hold.hold_type.value,
                "state": hold.state.value,
                "source_type": hold.source_type.value,
                "source_id": str(hold.source_id),
            },
            replay_payload={
                "hold": hold.model_dump(mode="json"),
                "history": initial_history.model_dump(mode="json"),
            },
        )
        return hold

    def transition_hold(
        self,
        *,
        hold_id: UUID,
        target_state: FinancialHoldState,
        updated_at: datetime,
        history: FinancialHoldStateHistory,
    ) -> FinancialHold:
        row = (
            self._connection.execute(
                update(financial_holds)
                .where(financial_holds.c.hold_id == hold_id)
                .values(
                    state=target_state.value,
                    updated_at=updated_at,
                )
                .returning(financial_holds)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise FinancialHoldConflict("financial_hold_not_found")
        self._connection.execute(
            insert(financial_hold_state_history).values(
                **history.model_dump(mode="json")
            )
        )
        self._event(
            hold_id=hold_id,
            event_type=f"financial_hold.{target_state.value}",
            at=history.changed_at,
            correlation_id=history.correlation_id,
            causation_id=history.causation_id,
            safe_payload={
                "hold_id": str(hold_id),
                "to_state": target_state.value,
                "reason_code": history.reason_code.value,
            },
            replay_payload={
                "history": history.model_dump(mode="json"),
            },
        )
        return _hold(row)

    def list_history(self, hold_id: UUID) -> tuple[FinancialHoldStateHistory, ...]:
        rows = self._connection.execute(
            select(financial_hold_state_history)
            .where(financial_hold_state_history.c.hold_id == hold_id)
            .order_by(
                financial_hold_state_history.c.changed_at,
                financial_hold_state_history.c.history_id,
            )
        ).mappings()
        return tuple(_history(row) for row in rows)

    def _event(
        self,
        *,
        hold_id: UUID,
        event_type: str,
        at: datetime,
        correlation_id: UUID,
        causation_id: UUID,
        safe_payload: dict[str, Any],
        replay_payload: dict[str, Any],
    ) -> None:
        event_id = uuid4()
        self._connection.execute(
            insert(financial_hold_events).values(
                event_id=event_id,
                aggregate_type="financial_hold",
                aggregate_id=hold_id,
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
            insert(financial_hold_outbox).values(
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
        return canonical_hold_hash(json.loads(json.dumps(payload)))
