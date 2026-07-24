import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.payment.engine import (
    PaymentConflict,
    attempt_is_terminal,
    canonical_payment_hash,
    ensure_attempt_transition_allowed,
    ensure_intent_transition_allowed,
)
from BACKEND.payment.models import (
    PaymentAttempt,
    PaymentAttemptState,
    PaymentCallbackEnvelope,
    PaymentIntent,
    PaymentIntentState,
)
from BACKEND.persistence.tables import (
    payment_attempts,
    payment_callback_envelopes,
    payment_events,
    payment_idempotency,
    payment_intents,
    payment_outbox,
)


def _intent(row: Any) -> PaymentIntent:
    return PaymentIntent.model_validate(dict(row))


def _attempt(row: Any) -> PaymentAttempt:
    return PaymentAttempt.model_validate(dict(row))


class PostgresPaymentRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve_idempotency(
        self,
        *,
        actor_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, Any],
        response_reference: UUID,
        at: datetime,
    ) -> UUID:
        digest = canonical_payment_hash(payload)
        row = self._connection.execute(
            pg_insert(payment_idempotency)
            .values(
                actor_id=actor_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=response_reference,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(payment_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if row is not None:
            return cast(UUID, row)
        existing = (
            self._connection.execute(
                select(payment_idempotency).where(
                    payment_idempotency.c.actor_id == actor_id,
                    payment_idempotency.c.operation == operation,
                    payment_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if existing["request_hash"] != digest:
            raise PaymentConflict("idempotency_conflict")
        return cast(UUID, existing["response_reference"])

    def create_intent(self, intent: PaymentIntent) -> PaymentIntent:
        if intent.state.value != "created":
            raise PaymentConflict("payment_intent_invalid_initial_state")
        if intent.currency != "ETB":
            raise PaymentConflict("payment_currency_unsupported")
        self._connection.execute(
            insert(payment_intents).values(**intent.model_dump(mode="json"))
        )
        self._event(
            aggregate_type="payment_intent",
            aggregate_id=intent.payment_intent_id,
            event_type="payment.intent_created",
            at=intent.created_at,
            correlation_id=intent.payment_intent_id,
            causation_id=intent.traceability.fare_calculation_id,
            safe_payload={
                "payment_intent_id": str(intent.payment_intent_id),
                "ride_id": str(intent.ride_id),
                "amount_minor": intent.amount_minor,
                "currency": intent.currency,
            },
            replay_payload={
                "intent": intent.model_dump(mode="json"),
            },
        )
        return intent

    def transition_intent(
        self,
        *,
        payment_intent_id: UUID,
        target_state: PaymentIntentState,
        at: datetime,
        correlation_id: UUID,
        causation_id: UUID,
        reason_code: str,
    ) -> PaymentIntent:
        current = self.get_intent(payment_intent_id, lock=True)
        if current is None:
            raise PaymentConflict("payment_intent_not_found")
        ensure_intent_transition_allowed(current.state, target_state, at=at)
        changed = current.model_copy(
            update={
                "state": target_state,
                "cancelled_at": at
                if target_state is PaymentIntentState.CANCELLED
                else current.cancelled_at,
            }
        )
        self._connection.execute(
            update(payment_intents)
            .where(payment_intents.c.payment_intent_id == payment_intent_id)
            .values(
                state=changed.state.value,
                cancelled_at=changed.cancelled_at,
            )
        )
        self._event(
            aggregate_type="payment_intent",
            aggregate_id=changed.payment_intent_id,
            event_type=f"payment.intent_{changed.state.value}",
            at=at,
            correlation_id=correlation_id,
            causation_id=causation_id,
            safe_payload={
                "payment_intent_id": str(changed.payment_intent_id),
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

    def get_intent(
        self, payment_intent_id: UUID, *, lock: bool = False
    ) -> PaymentIntent | None:
        query = select(payment_intents).where(
            payment_intents.c.payment_intent_id == payment_intent_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _intent(row)

    def create_attempt(self, attempt: PaymentAttempt) -> PaymentAttempt:
        intent = self.get_intent(attempt.payment_intent_id, lock=True)
        if intent is None:
            raise PaymentConflict("payment_intent_not_found")
        if intent.state.value != "created":
            raise PaymentConflict("payment_intent_not_active")
        if (
            attempt.amount_minor != intent.amount_minor
            or attempt.currency != intent.currency
        ):
            raise PaymentConflict("payment_attempt_amount_conflict")
        for active in self.list_attempts_for_intent(
            attempt.payment_intent_id, lock=True
        ):
            if not attempt_is_terminal(active.state):
                raise PaymentConflict("payment_attempt_already_active")
        existing = (
            self._connection.execute(
                select(payment_attempts).where(
                    payment_attempts.c.payment_intent_id == attempt.payment_intent_id,
                    payment_attempts.c.provider_code == attempt.provider_code,
                    payment_attempts.c.provider_reference == attempt.provider_reference,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            return _attempt(existing)
        self._connection.execute(
            insert(payment_attempts).values(**attempt.model_dump(mode="json"))
        )
        self._event(
            aggregate_type="payment_attempt",
            aggregate_id=attempt.payment_attempt_id,
            event_type="payment.attempt_created",
            at=attempt.created_at,
            correlation_id=attempt.correlation_id,
            causation_id=attempt.causation_id,
            safe_payload={
                "payment_attempt_id": str(attempt.payment_attempt_id),
                "payment_intent_id": str(attempt.payment_intent_id),
                "provider_code": attempt.provider_code,
                "state": attempt.state.value,
            },
            replay_payload={
                "attempt": attempt.model_dump(mode="json"),
            },
        )
        return attempt

    def list_attempts_for_intent(
        self, payment_intent_id: UUID, *, lock: bool = False
    ) -> tuple[PaymentAttempt, ...]:
        query = (
            select(payment_attempts)
            .where(payment_attempts.c.payment_intent_id == payment_intent_id)
            .order_by(
                payment_attempts.c.created_at, payment_attempts.c.payment_attempt_id
            )
        )
        if lock:
            query = query.with_for_update()
        rows = self._connection.execute(query).mappings()
        return tuple(_attempt(row) for row in rows)

    def list_intents_for_ride(self, ride_id: UUID) -> tuple[PaymentIntent, ...]:
        rows = self._connection.execute(
            select(payment_intents)
            .where(payment_intents.c.ride_id == ride_id)
            .order_by(payment_intents.c.created_at, payment_intents.c.payment_intent_id)
        ).mappings()
        return tuple(_intent(row) for row in rows)

    def get_attempt(
        self, payment_attempt_id: UUID, *, lock: bool = False
    ) -> PaymentAttempt | None:
        query = select(payment_attempts).where(
            payment_attempts.c.payment_attempt_id == payment_attempt_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _attempt(row)

    def transition_attempt(
        self,
        *,
        payment_attempt_id: UUID,
        target_state: PaymentAttemptState,
        at: datetime,
        reason_code: str,
        correlation_id: UUID,
        causation_id: UUID,
        provider_event_id: str | None = None,
    ) -> PaymentAttempt:
        current = self.get_attempt(payment_attempt_id, lock=True)
        if current is None:
            raise PaymentConflict("payment_attempt_not_found")
        ensure_attempt_transition_allowed(current.state, target_state, at=at)
        changed = current.model_copy(
            update={
                "state": target_state,
                "reason_code": reason_code,
                "provider_event_id": provider_event_id or current.provider_event_id,
                "updated_at": at,
            }
        )
        self._connection.execute(
            update(payment_attempts)
            .where(payment_attempts.c.payment_attempt_id == payment_attempt_id)
            .values(
                state=changed.state.value,
                reason_code=changed.reason_code,
                provider_event_id=changed.provider_event_id,
                updated_at=changed.updated_at,
            )
        )
        self._event(
            aggregate_type="payment_attempt",
            aggregate_id=changed.payment_attempt_id,
            event_type=f"payment.attempt_{changed.state.value}",
            at=at,
            correlation_id=correlation_id,
            causation_id=causation_id,
            safe_payload={
                "payment_attempt_id": str(changed.payment_attempt_id),
                "payment_intent_id": str(changed.payment_intent_id),
                "provider_code": changed.provider_code,
                "state": changed.state.value,
                "reason_code": changed.reason_code,
            },
            replay_payload={
                "from_state": current.state.value,
                "to_state": changed.state.value,
                "provider_event_id": changed.provider_event_id,
            },
        )
        return changed

    def ingest_callback_envelope(
        self, envelope: PaymentCallbackEnvelope
    ) -> PaymentCallbackEnvelope:
        row = self._connection.execute(
            pg_insert(payment_callback_envelopes)
            .values(**envelope.model_dump(mode="json"))
            .on_conflict_do_nothing()
            .returning(payment_callback_envelopes.c.callback_id)
        ).scalar_one_or_none()
        if row is not None:
            return envelope
        existing = (
            self._connection.execute(
                select(payment_callback_envelopes).where(
                    payment_callback_envelopes.c.provider_code
                    == envelope.provider_code,
                    payment_callback_envelopes.c.provider_event_id
                    == envelope.provider_event_id,
                )
            )
            .mappings()
            .one()
        )
        if existing["payload_hash"] != envelope.payload_hash:
            raise PaymentConflict("payment_callback_replay_conflict")
        return PaymentCallbackEnvelope.model_validate(dict(existing))

    def mark_callback_processed(
        self,
        *,
        callback_id: UUID,
        correlated_attempt_id: UUID,
        processed_at: datetime,
    ) -> None:
        self._connection.execute(
            update(payment_callback_envelopes)
            .where(payment_callback_envelopes.c.callback_id == callback_id)
            .values(
                correlated_attempt_id=correlated_attempt_id,
                processed_at=processed_at,
            )
        )

    def payment_history_by_ride(
        self, ride_id: UUID
    ) -> tuple[tuple[PaymentIntent, ...], dict[UUID, tuple[PaymentAttempt, ...]]]:
        intents = self.list_intents_for_ride(ride_id)
        attempts = {
            item.payment_intent_id: self.list_attempts_for_intent(
                item.payment_intent_id
            )
            for item in intents
        }
        return intents, attempts

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
            insert(payment_events).values(
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
            insert(payment_outbox).values(
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
        return canonical_payment_hash(json.loads(json.dumps(payload)))
