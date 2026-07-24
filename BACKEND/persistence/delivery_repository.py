import hashlib
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.delivery_verification.engine import DeliveryConflict
from BACKEND.delivery_verification.models import (
    DeliveryCredential,
    DeliveryCredentialView,
    DeliveryEvent,
    DeliveryRecord,
    DeliveryState,
    DeliveryVerificationMethod,
    DeliveryView,
)
from BACKEND.persistence.tables import (
    commerce_custody_records,
    commerce_deliveries,
    commerce_delivery_credentials,
    commerce_delivery_events,
    commerce_delivery_idempotency,
    commerce_delivery_notification_intents,
    commerce_delivery_reminders,
    commerce_order_outbox,
    commerce_orders,
)


class PostgresDeliveryRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create_credential(
        self,
        *,
        message_id: UUID,
        order_id: UUID,
        code_hash: str,
        expires_at: datetime,
        display_code: str,
        at: datetime,
    ) -> DeliveryCredentialView:
        source = (
            self._connection.execute(
                select(commerce_order_outbox.c.event_type, commerce_orders.c.order_id)
                .select_from(
                    commerce_order_outbox.join(
                        commerce_orders,
                        commerce_orders.c.order_id == commerce_order_outbox.c.order_id,
                    )
                )
                .where(
                    commerce_order_outbox.c.message_id == message_id,
                    commerce_orders.c.order_id == order_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if source is None or source["event_type"] != "commerce.order.created":
            raise DeliveryConflict("order_confirmation_event_invalid")
        credential_id = uuid4()
        order_number = f"AYO-{str(order_id).replace('-', '')[:12].upper()}"
        self._connection.execute(
            pg_insert(commerce_delivery_credentials)
            .values(
                credential_id=credential_id,
                order_id=order_id,
                source_message_id=message_id,
                order_number=order_number,
                code_hash=code_hash,
                expires_at=expires_at,
                used_at=None,
                created_at=at,
            )
            .on_conflict_do_nothing()
        )
        credential = self._credential(order_id)
        for channel in ("in_app", "email", "sms"):
            self._connection.execute(
                pg_insert(commerce_delivery_notification_intents)
                .values(
                    intent_id=uuid4(),
                    order_id=order_id,
                    delivery_id=None,
                    channel=channel,
                    template_code="order_confirmation_delivery_credential",
                    secure_credential_reference=credential.credential_id,
                    created_at=at,
                    published_at=None,
                )
                .on_conflict_do_nothing()
            )
        return DeliveryCredentialView(credential=credential, display_code=display_code)

    def credential_view(
        self, order_id: UUID, *, display_code: str
    ) -> DeliveryCredentialView:
        return DeliveryCredentialView(
            credential=self._credential(order_id), display_code=display_code
        )

    def _credential(self, order_id: UUID) -> DeliveryCredential:
        row = (
            self._connection.execute(
                select(commerce_delivery_credentials).where(
                    commerce_delivery_credentials.c.order_id == order_id
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DeliveryConflict("delivery_credential_not_found")
        return DeliveryCredential.model_validate(
            {
                k: v
                for k, v in row.items()
                if k not in ("code_hash", "source_message_id")
            }
        )

    def activate(
        self, *, message_id: UUID, custody_id: UUID, order_id: UUID, at: datetime
    ) -> DeliveryView:
        custody = (
            self._connection.execute(
                select(commerce_custody_records).where(
                    commerce_custody_records.c.custody_id == custody_id,
                    commerce_custody_records.c.order_id == order_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        source = self._connection.execute(
            select(commerce_order_outbox.c.event_type).where(
                commerce_order_outbox.c.message_id == message_id,
                commerce_order_outbox.c.order_id == order_id,
            )
        ).scalar_one_or_none()
        if (
            custody is None
            or custody["state"] != "courier_custody_accepted"
            or source != "commerce.custody.courier_custody_accepted"
        ):
            raise DeliveryConflict("custody_accepted_event_invalid")
        credential = self._credential(order_id)
        delivery_id = uuid4()
        self._connection.execute(
            pg_insert(commerce_deliveries)
            .values(
                delivery_id=delivery_id,
                custody_id=custody_id,
                order_id=order_id,
                merchant_id=custody["merchant_id"],
                courier_identity_id=custody["courier_identity_id"],
                credential_id=credential.credential_id,
                source_message_id=message_id,
                state=DeliveryState.ARRIVING.value,
                version=1,
                arriving_at=at,
                customer_available_at=None,
                verified_at=None,
                verification_method=None,
                customer_received_at=None,
                completed_at=None,
                closed_at=None,
                updated_at=at,
            )
            .on_conflict_do_nothing()
        )
        return self._by_order(order_id)

    def get(self, delivery_id: UUID, *, lock: bool = False) -> DeliveryRecord | None:
        statement = select(commerce_deliveries).where(
            commerce_deliveries.c.delivery_id == delivery_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else DeliveryRecord.model_validate(dict(row))

    def reserve(
        self, *, actor_id: UUID, delivery_id: UUID, key: str, payload: str, at: datetime
    ) -> DeliveryView | None:
        digest = hashlib.sha256(payload.encode()).hexdigest()
        created = self._connection.execute(
            pg_insert(commerce_delivery_idempotency)
            .values(
                actor_identity_id=actor_id,
                delivery_id=delivery_id,
                idempotency_key=key,
                request_hash=digest,
                response_version=None,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(commerce_delivery_idempotency.c.delivery_id)
        ).scalar_one_or_none()
        if created is not None:
            return None
        row = (
            self._connection.execute(
                select(commerce_delivery_idempotency).where(
                    commerce_delivery_idempotency.c.actor_identity_id == actor_id,
                    commerce_delivery_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["delivery_id"] != delivery_id or row["request_hash"] != digest:
            raise DeliveryConflict("idempotency_conflict")
        value = self._required(delivery_id)
        if row["response_version"] != value.delivery.version:
            raise DeliveryConflict("idempotency_result_unavailable")
        return value

    def verify(
        self,
        current: DeliveryRecord,
        *,
        target: DeliveryState,
        actor_id: UUID,
        code_hash: str,
        method: DeliveryVerificationMethod,
        key: str,
        at: datetime,
    ) -> DeliveryView:
        used = self._connection.execute(
            update(commerce_delivery_credentials)
            .where(
                commerce_delivery_credentials.c.credential_id == current.credential_id,
                commerce_delivery_credentials.c.code_hash == code_hash,
                commerce_delivery_credentials.c.used_at.is_(None),
                commerce_delivery_credentials.c.expires_at >= at,
            )
            .values(used_at=at)
            .returning(commerce_delivery_credentials.c.credential_id)
        ).scalar_one_or_none()
        if used is None:
            raise DeliveryConflict("delivery_credential_invalid_expired_or_used")
        return self._transition(
            current,
            target=target,
            actor_id=actor_id,
            key=key,
            at=at,
            extra={"verified_at": at, "verification_method": method.value},
        )

    def transition(
        self,
        current: DeliveryRecord,
        *,
        target: DeliveryState,
        actor_id: UUID,
        key: str,
        at: datetime,
    ) -> DeliveryView:
        names = {
            DeliveryState.AVAILABLE: "customer_available_at",
            DeliveryState.RECEIVED: "customer_received_at",
            DeliveryState.COMPLETED: "completed_at",
            DeliveryState.CLOSED: "closed_at",
        }
        return self._transition(
            current,
            target=target,
            actor_id=actor_id,
            key=key,
            at=at,
            extra={names[target]: at},
        )

    def _transition(
        self,
        current: DeliveryRecord,
        *,
        target: DeliveryState,
        actor_id: UUID,
        key: str,
        at: datetime,
        extra: dict,
    ) -> DeliveryView:
        version = current.version + 1
        changed = self._connection.execute(
            update(commerce_deliveries)
            .where(
                commerce_deliveries.c.delivery_id == current.delivery_id,
                commerce_deliveries.c.state == current.state.value,
                commerce_deliveries.c.version == current.version,
            )
            .values(state=target.value, version=version, updated_at=at, **extra)
            .returning(commerce_deliveries.c.delivery_id)
        ).scalar_one_or_none()
        if changed is None:
            raise DeliveryConflict("delivery_version_conflict")
        event_type = f"commerce.delivery.{target.value}"
        self._connection.execute(
            insert(commerce_delivery_events).values(
                event_id=uuid4(),
                delivery_id=current.delivery_id,
                event_type=event_type,
                from_state=current.state.value,
                to_state=target.value,
                actor_identity_id=actor_id,
                version=version,
                occurred_at=at,
            )
        )
        self._connection.execute(
            insert(commerce_order_outbox).values(
                message_id=uuid4(),
                order_id=current.order_id,
                event_type=event_type,
                safe_payload={
                    "order_id": str(current.order_id),
                    "delivery_id": str(current.delivery_id),
                    "state": target.value,
                    "version": version,
                },
                occurred_at=at,
                attempt_count=0,
            )
        )
        self._connection.execute(
            update(commerce_delivery_idempotency)
            .where(
                commerce_delivery_idempotency.c.actor_identity_id == actor_id,
                commerce_delivery_idempotency.c.delivery_id == current.delivery_id,
                commerce_delivery_idempotency.c.idempotency_key == key,
            )
            .values(response_version=version)
        )
        return self._required(current.delivery_id)

    def reminder_exists(self, delivery_id: UUID) -> bool:
        return (
            self._connection.execute(
                select(commerce_delivery_reminders.c.reminder_id)
                .where(commerce_delivery_reminders.c.delivery_id == delivery_id)
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def record_reminders(
        self,
        *,
        delivery_id: UUID,
        eta_evidence_id: UUID,
        eta_minutes: int,
        policy_version: int,
        at: datetime,
    ) -> None:
        delivery = self.get(delivery_id)
        if delivery is None:
            raise DeliveryConflict("delivery_not_found")
        for channel in ("in_app", "email"):
            self._connection.execute(
                pg_insert(commerce_delivery_reminders)
                .values(
                    reminder_id=uuid4(),
                    delivery_id=delivery_id,
                    channel=channel,
                    eta_evidence_id=eta_evidence_id,
                    eta_minutes=eta_minutes,
                    policy_version=policy_version,
                    created_at=at,
                )
                .on_conflict_do_nothing()
            )
            self._connection.execute(
                pg_insert(commerce_delivery_notification_intents)
                .values(
                    intent_id=uuid4(),
                    order_id=delivery.order_id,
                    delivery_id=delivery_id,
                    channel=channel,
                    template_code="courier_approximately_20_minutes_away",
                    secure_credential_reference=delivery.credential_id,
                    created_at=at,
                    published_at=None,
                )
                .on_conflict_do_nothing()
            )

    def _by_order(self, order_id: UUID) -> DeliveryView:
        delivery_id = self._connection.execute(
            select(commerce_deliveries.c.delivery_id).where(
                commerce_deliveries.c.order_id == order_id
            )
        ).scalar_one()
        return self._required(delivery_id)

    def _required(self, delivery_id: UUID) -> DeliveryView:
        delivery = self.get(delivery_id)
        if delivery is None:
            raise DeliveryConflict("delivery_not_found")
        credential = self._credential(delivery.order_id)
        rows = self._connection.execute(
            select(commerce_delivery_events)
            .where(commerce_delivery_events.c.delivery_id == delivery_id)
            .order_by(commerce_delivery_events.c.version)
        ).mappings()
        return DeliveryView(
            delivery=delivery,
            credential=credential,
            events=tuple(DeliveryEvent.model_validate(dict(row)) for row in rows),
        )
