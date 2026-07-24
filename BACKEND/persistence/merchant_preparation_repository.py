import hashlib
import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.merchant_preparation.engine import PreparationConflict
from BACKEND.merchant_preparation.models import (
    PreparationEvent,
    PreparationRecord,
    PreparationView,
)
from BACKEND.ordering.models import CanonicalOrder, OrderState
from BACKEND.persistence.merchant_order_repository import (
    PostgresMerchantOrderRepository,
)
from BACKEND.persistence.tables import (
    commerce_order_outbox,
    commerce_order_preparations,
    commerce_order_timeline,
    commerce_orders,
    commerce_preparation_events,
    commerce_preparation_idempotency,
)


class PostgresMerchantPreparationRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve(
        self,
        *,
        actor_id: UUID,
        merchant_id: UUID,
        order_id: UUID,
        key: str,
        payload: dict[str, Any],
        at: datetime,
    ) -> tuple[int | None, bool]:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        inserted = self._connection.execute(
            pg_insert(commerce_preparation_idempotency)
            .values(
                actor_identity_id=actor_id,
                merchant_id=merchant_id,
                order_id=order_id,
                idempotency_key=key,
                request_hash=digest,
                response_version=None,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(commerce_preparation_idempotency.c.order_id)
        ).scalar_one_or_none()
        if inserted is not None:
            return None, True
        row = (
            self._connection.execute(
                select(commerce_preparation_idempotency).where(
                    commerce_preparation_idempotency.c.actor_identity_id == actor_id,
                    commerce_preparation_idempotency.c.merchant_id == merchant_id,
                    commerce_preparation_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["request_hash"] != digest or row["order_id"] != order_id:
            raise PreparationConflict("idempotency_conflict")
        return cast(int | None, row["response_version"]), False

    def get_record(
        self, order_id: UUID, *, lock: bool = False
    ) -> PreparationRecord | None:
        statement = select(commerce_order_preparations).where(
            commerce_order_preparations.c.order_id == order_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else PreparationRecord.model_validate(dict(row))

    def get_view(self, order_id: UUID) -> PreparationView | None:
        order = PostgresMerchantOrderRepository(self._connection).get_view(order_id)
        if order is None:
            return None
        rows = self._connection.execute(
            select(commerce_preparation_events)
            .where(commerce_preparation_events.c.order_id == order_id)
            .order_by(
                commerce_preparation_events.c.order_version,
                commerce_preparation_events.c.event_id,
            )
        ).mappings()
        return PreparationView(
            order=order,
            preparation=self.get_record(order_id),
            preparation_events=tuple(
                PreparationEvent.model_validate(dict(row)) for row in rows
            ),
        )

    def start(
        self,
        order: CanonicalOrder,
        *,
        actor_id: UUID,
        estimated_duration_seconds: int,
        estimated_ready_at: datetime,
        idempotency_key: str,
        at: datetime,
    ) -> PreparationView:
        next_version = self._order_transition(order, target=OrderState.PREPARING)
        self._connection.execute(
            insert(commerce_order_preparations).values(
                order_id=order.order_id,
                merchant_id=order.merchant_id,
                started_at=at,
                estimated_duration_seconds=estimated_duration_seconds,
                estimated_ready_at=estimated_ready_at,
                progress_percent=0,
                latest_delay_reason_code=None,
                latest_delay_message=None,
                updated_at=at,
                ready_at=None,
            )
        )
        self._append(
            order,
            actor_id=actor_id,
            from_state=order.state,
            to_state=OrderState.PREPARING,
            version=next_version,
            event_type="started",
            progress=0,
            estimated_duration_seconds=estimated_duration_seconds,
            delay_reason_code=None,
            delay_message=None,
            at=at,
        )
        self._finish_idempotency(actor_id, order, idempotency_key, next_version)
        return self._required_view(order.order_id)

    def progress(
        self,
        order: CanonicalOrder,
        *,
        current: PreparationRecord,
        progress_percent: int,
        actor_id: UUID,
        delay_reason_code: str | None,
        delay_message: str | None,
        idempotency_key: str,
        at: datetime,
    ) -> PreparationView:
        next_version = self._order_transition(order, target=OrderState.PREPARING)
        result = self._connection.execute(
            update(commerce_order_preparations)
            .where(
                commerce_order_preparations.c.order_id == order.order_id,
                commerce_order_preparations.c.progress_percent
                == current.progress_percent,
                commerce_order_preparations.c.ready_at.is_(None),
            )
            .values(
                progress_percent=progress_percent,
                latest_delay_reason_code=delay_reason_code,
                latest_delay_message=delay_message,
                updated_at=at,
            )
            .returning(commerce_order_preparations.c.order_id)
        ).scalar_one_or_none()
        if result is None:
            raise PreparationConflict("preparation_version_conflict")
        self._append(
            order,
            actor_id=actor_id,
            from_state=order.state,
            to_state=OrderState.PREPARING,
            version=next_version,
            event_type="progress_updated",
            progress=progress_percent,
            estimated_duration_seconds=None,
            delay_reason_code=delay_reason_code,
            delay_message=delay_message,
            at=at,
        )
        self._finish_idempotency(actor_id, order, idempotency_key, next_version)
        return self._required_view(order.order_id)

    def ready(
        self,
        order: CanonicalOrder,
        *,
        current: PreparationRecord,
        actor_id: UUID,
        idempotency_key: str,
        at: datetime,
        target: OrderState,
    ) -> PreparationView:
        next_version = self._order_transition(order, target=target)
        result = self._connection.execute(
            update(commerce_order_preparations)
            .where(
                commerce_order_preparations.c.order_id == order.order_id,
                commerce_order_preparations.c.progress_percent
                == current.progress_percent,
                commerce_order_preparations.c.ready_at.is_(None),
            )
            .values(progress_percent=100, updated_at=at, ready_at=at)
            .returning(commerce_order_preparations.c.order_id)
        ).scalar_one_or_none()
        if result is None:
            raise PreparationConflict("preparation_version_conflict")
        self._append(
            order,
            actor_id=actor_id,
            from_state=order.state,
            to_state=target,
            version=next_version,
            event_type="ready_for_pickup",
            progress=100,
            estimated_duration_seconds=None,
            delay_reason_code=None,
            delay_message=None,
            at=at,
        )
        self._finish_idempotency(actor_id, order, idempotency_key, next_version)
        return self._required_view(order.order_id)

    def _order_transition(self, order: CanonicalOrder, *, target: OrderState) -> int:
        version = order.version + 1
        result = self._connection.execute(
            update(commerce_orders)
            .where(
                commerce_orders.c.order_id == order.order_id,
                commerce_orders.c.merchant_id == order.merchant_id,
                commerce_orders.c.state == order.state.value,
                commerce_orders.c.version == order.version,
            )
            .values(state=target.value, version=version)
            .returning(commerce_orders.c.order_id)
        ).scalar_one_or_none()
        if result is None:
            raise PreparationConflict("order_version_conflict")
        return version

    def _append(
        self,
        order: CanonicalOrder,
        *,
        actor_id: UUID,
        from_state: OrderState,
        to_state: OrderState,
        version: int,
        event_type: str,
        progress: int,
        estimated_duration_seconds: int | None,
        delay_reason_code: str | None,
        delay_message: str | None,
        at: datetime,
    ) -> None:
        self._connection.execute(
            insert(commerce_preparation_events).values(
                event_id=uuid4(),
                order_id=order.order_id,
                merchant_id=order.merchant_id,
                event_type=f"commerce.preparation.{event_type}",
                actor_identity_id=actor_id,
                order_version=version,
                progress_percent=progress,
                estimated_duration_seconds=estimated_duration_seconds,
                delay_reason_code=delay_reason_code,
                delay_message=delay_message,
                occurred_at=at,
            )
        )
        self._connection.execute(
            insert(commerce_order_timeline).values(
                event_id=uuid4(),
                order_id=order.order_id,
                merchant_id=order.merchant_id,
                event_type=f"commerce.order.{to_state.value}"
                if from_state is not to_state
                else "commerce.order.preparation_progress",
                from_state=from_state.value,
                to_state=to_state.value,
                actor_identity_id=actor_id,
                order_version=version,
                customer_reason_code=None,
                occurred_at=at,
            )
        )
        self._connection.execute(
            insert(commerce_order_outbox).values(
                message_id=uuid4(),
                order_id=order.order_id,
                event_type=f"commerce.preparation.{event_type}",
                safe_payload={
                    "order_id": str(order.order_id),
                    "state": to_state.value,
                    "version": version,
                    "progress_percent": progress,
                    "delay_reason_code": delay_reason_code,
                },
                occurred_at=at,
                attempt_count=0,
            )
        )

    def _finish_idempotency(
        self, actor_id: UUID, order: CanonicalOrder, key: str, version: int
    ) -> None:
        self._connection.execute(
            update(commerce_preparation_idempotency)
            .where(
                commerce_preparation_idempotency.c.actor_identity_id == actor_id,
                commerce_preparation_idempotency.c.merchant_id == order.merchant_id,
                commerce_preparation_idempotency.c.order_id == order.order_id,
                commerce_preparation_idempotency.c.idempotency_key == key,
                commerce_preparation_idempotency.c.response_version.is_(None),
            )
            .values(response_version=version)
        )

    def _required_view(self, order_id: UUID) -> PreparationView:
        result = self.get_view(order_id)
        if result is None:
            raise PreparationConflict("preparation_order_not_found")
        return result
