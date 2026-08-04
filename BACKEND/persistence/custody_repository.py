import hashlib
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.courier_pickup.models import CourierPickupState
from BACKEND.custody.engine import CustodyConflict
from BACKEND.custody.models import (
    CustodyEvent,
    CustodyRecord,
    CustodyState,
    CustodyView,
    PickupChallenge,
    VerificationMethod,
)
from BACKEND.persistence.tables import (
    commerce_courier_pickups,
    commerce_custody_challenges,
    commerce_custody_events,
    commerce_custody_idempotency,
    commerce_custody_records,
    commerce_order_outbox,
)


class PostgresCustodyRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def activate(self, *, pickup_id: UUID, at: datetime) -> CustodyView:
        pickup = (
            self._connection.execute(
                select(commerce_courier_pickups).where(
                    commerce_courier_pickups.c.pickup_id == pickup_id
                )
            )
            .mappings()
            .one_or_none()
        )
        if pickup is None or pickup["state"] != CourierPickupState.WAITING.value:
            raise CustodyConflict("pickup_not_waiting")
        custody_id = uuid4()
        inserted = self._connection.execute(
            pg_insert(commerce_custody_records)
            .values(
                custody_id=custody_id,
                pickup_id=pickup_id,
                order_id=pickup["order_id"],
                merchant_id=pickup["merchant_id"],
                courier_identity_id=pickup["assigned_courier_identity_id"],
                state=CustodyState.WAITING.value,
                version=1,
                sealed_at=None,
                verified_at=None,
                verification_method=None,
                merchant_released_at=None,
                custody_accepted_at=None,
                updated_at=at,
            )
            .on_conflict_do_nothing()
            .returning(commerce_custody_records.c.custody_id)
        ).scalar_one_or_none()
        if inserted is None:
            existing = self.get_by_order(pickup["order_id"])
            if existing is None or existing.custody.pickup_id != pickup_id:
                raise CustodyConflict("custody_activation_conflict")
            return existing
        return self._required(custody_id)

    def get(self, custody_id: UUID, *, lock: bool = False) -> CustodyRecord | None:
        statement = select(commerce_custody_records).where(
            commerce_custody_records.c.custody_id == custody_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else CustodyRecord.model_validate(dict(row))

    def get_by_order(self, order_id: UUID) -> CustodyView | None:
        value = self._connection.execute(
            select(commerce_custody_records.c.custody_id).where(
                commerce_custody_records.c.order_id == order_id
            )
        ).scalar_one_or_none()
        return None if value is None else self._required(value)

    def reserve(
        self, *, actor_id: UUID, custody_id: UUID, key: str, payload: str, at: datetime
    ) -> CustodyView | None:
        digest = hashlib.sha256(payload.encode()).hexdigest()
        created = self._connection.execute(
            pg_insert(commerce_custody_idempotency)
            .values(
                actor_identity_id=actor_id,
                custody_id=custody_id,
                idempotency_key=key,
                request_hash=digest,
                response_version=None,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(commerce_custody_idempotency.c.custody_id)
        ).scalar_one_or_none()
        if created is not None:
            return None
        row = (
            self._connection.execute(
                select(commerce_custody_idempotency).where(
                    commerce_custody_idempotency.c.actor_identity_id == actor_id,
                    commerce_custody_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["custody_id"] != custody_id or row["request_hash"] != digest:
            raise CustodyConflict("idempotency_conflict")
        result = self._required(custody_id)
        if row["response_version"] != result.custody.version:
            raise CustodyConflict("idempotency_result_unavailable")
        return result

    def seal(
        self,
        current: CustodyRecord,
        *,
        target: CustodyState,
        actor_id: UUID,
        code_hash: str,
        expires_at: datetime,
        key: str,
        at: datetime,
    ) -> CustodyView:
        self._transition(
            current,
            target=target,
            actor_id=actor_id,
            key=key,
            at=at,
            extra={"sealed_at": at},
        )
        self._connection.execute(
            insert(commerce_custody_challenges).values(
                challenge_id=uuid4(),
                custody_id=current.custody_id,
                code_hash=code_hash,
                expires_at=expires_at,
                used_at=None,
                created_at=at,
            )
        )
        return self._required(current.custody_id)

    def verify(
        self,
        current: CustodyRecord,
        *,
        target: CustodyState,
        actor_id: UUID,
        code_hash: str,
        method: VerificationMethod,
        key: str,
        at: datetime,
    ) -> CustodyView:
        challenge = (
            self._connection.execute(
                select(commerce_custody_challenges)
                .where(
                    commerce_custody_challenges.c.custody_id == current.custody_id,
                    commerce_custody_challenges.c.code_hash == code_hash,
                    commerce_custody_challenges.c.used_at.is_(None),
                    commerce_custody_challenges.c.expires_at >= at,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if challenge is None:
            raise CustodyConflict("pickup_code_invalid_or_expired")
        used = self._connection.execute(
            update(commerce_custody_challenges)
            .where(
                commerce_custody_challenges.c.challenge_id == challenge["challenge_id"],
                commerce_custody_challenges.c.used_at.is_(None),
            )
            .values(used_at=at)
            .returning(commerce_custody_challenges.c.challenge_id)
        ).scalar_one_or_none()
        if used is None:
            raise CustodyConflict("pickup_code_replayed")
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
        current: CustodyRecord,
        *,
        target: CustodyState,
        actor_id: UUID,
        key: str,
        at: datetime,
    ) -> CustodyView:
        extra = (
            {"merchant_released_at": at}
            if target is CustodyState.RELEASED
            else {"custody_accepted_at": at}
        )
        return self._transition(
            current, target=target, actor_id=actor_id, key=key, at=at, extra=extra
        )

    def _transition(
        self,
        current: CustodyRecord,
        *,
        target: CustodyState,
        actor_id: UUID,
        key: str,
        at: datetime,
        extra: dict,
    ) -> CustodyView:
        version = current.version + 1
        changed = self._connection.execute(
            update(commerce_custody_records)
            .where(
                commerce_custody_records.c.custody_id == current.custody_id,
                commerce_custody_records.c.state == current.state.value,
                commerce_custody_records.c.version == current.version,
            )
            .values(state=target.value, version=version, updated_at=at, **extra)
            .returning(commerce_custody_records.c.custody_id)
        ).scalar_one_or_none()
        if changed is None:
            raise CustodyConflict("custody_version_conflict")
        self._connection.execute(
            insert(commerce_custody_events).values(
                event_id=uuid4(),
                custody_id=current.custody_id,
                order_id=current.order_id,
                event_type=f"commerce.custody.{target.value}",
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
                event_type=f"commerce.custody.{target.value}",
                safe_payload={
                    "order_id": str(current.order_id),
                    "custody_id": str(current.custody_id),
                    "state": target.value,
                    "version": version,
                },
                occurred_at=at,
                attempt_count=0,
            )
        )
        self._connection.execute(
            update(commerce_custody_idempotency)
            .where(
                commerce_custody_idempotency.c.actor_identity_id == actor_id,
                commerce_custody_idempotency.c.custody_id == current.custody_id,
                commerce_custody_idempotency.c.idempotency_key == key,
            )
            .values(response_version=version)
        )
        return self._required(current.custody_id)

    def _required(self, custody_id: UUID) -> CustodyView:
        value = self.get(custody_id)
        if value is None:
            raise CustodyConflict("custody_not_found")
        challenge_row = (
            self._connection.execute(
                select(commerce_custody_challenges)
                .where(commerce_custody_challenges.c.custody_id == custody_id)
                .order_by(commerce_custody_challenges.c.created_at.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        rows = self._connection.execute(
            select(commerce_custody_events)
            .where(commerce_custody_events.c.custody_id == custody_id)
            .order_by(commerce_custody_events.c.version)
        ).mappings()
        challenge = (
            None
            if challenge_row is None
            else PickupChallenge.model_validate(
                {
                    k: v
                    for k, v in challenge_row.items()
                    if k != "code_hash" and k != "created_at"
                }
            )
        )
        return CustodyView(
            custody=value,
            challenge=challenge,
            events=tuple(CustodyEvent.model_validate(dict(row)) for row in rows),
        )
