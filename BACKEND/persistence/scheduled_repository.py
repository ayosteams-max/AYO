from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.audit.models import AuditEvent
from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.tables import (
    reservation_driver_commitments,
    reservation_idempotency_records,
    reservation_participants,
    reservation_soft_plans,
    ride_reservations,
)
from BACKEND.scheduled.engine import ReservationConflict
from BACKEND.scheduled.models import (
    DriverCommitment,
    Participant,
    ReservationState,
    ScheduledReservation,
    SoftPlan,
)


class PostgresScheduledRepository:
    """Transactional scheduled-dispatch repository over a caller-owned unit of work."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(
        self,
        reservation: ScheduledReservation,
        *,
        participants: tuple[Participant, ...],
        idempotency_fingerprint: str,
        request_hash: str,
        audit_event: AuditEvent,
    ) -> tuple[ScheduledReservation, bool]:
        existing = self._connection.execute(
            select(
                reservation_idempotency_records.c.request_hash,
                reservation_idempotency_records.c.reservation_id,
            ).where(
                reservation_idempotency_records.c.actor_id == reservation.booker_id,
                reservation_idempotency_records.c.key_fingerprint
                == idempotency_fingerprint,
            )
        ).one_or_none()
        if existing:
            if existing.request_hash != request_hash:
                raise ReservationConflict("Idempotency key reused")
            stored = self.get(existing.reservation_id)
            if stored is None:
                raise ReservationConflict("Idempotency authority is inconsistent")
            return stored, False
        try:
            self._connection.execute(
                insert(ride_reservations).values(
                    **reservation.model_dump(mode="python")
                )
            )
            for participant in participants:
                self._connection.execute(
                    insert(reservation_participants).values(
                        participant_id=participant.participant_id,
                        reservation_id=reservation.reservation_id,
                        payload=participant.model_dump(mode="json"),
                        created_at=reservation.created_at,
                    )
                )
            self._connection.execute(
                insert(reservation_idempotency_records).values(
                    actor_id=reservation.booker_id,
                    key_fingerprint=idempotency_fingerprint,
                    request_hash=request_hash,
                    reservation_id=reservation.reservation_id,
                    created_at=reservation.created_at,
                    expires_at=reservation.created_at + timedelta(days=7),
                )
            )
            PostgresAuditEventRepository(self._connection).append(audit_event)
            return reservation, True
        except IntegrityError as error:
            raise ReservationConflict(
                "Concurrent reservation creation conflict"
            ) from error

    def get(self, reservation_id: UUID) -> ScheduledReservation | None:
        row = (
            self._connection.execute(
                select(ride_reservations).where(
                    ride_reservations.c.reservation_id == reservation_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return ScheduledReservation.model_validate(dict(row)) if row else None

    def save_soft_plan(
        self,
        reservation: ScheduledReservation,
        plan: SoftPlan,
        *,
        expected_version: int,
        audit_event: AuditEvent,
    ) -> ScheduledReservation:
        self._connection.execute(
            insert(reservation_soft_plans).values(
                soft_plan_id=plan.soft_plan_id,
                reservation_id=plan.reservation_id,
                payload=plan.model_dump(mode="json"),
                created_at=plan.selected_at,
            )
        )
        values = {
            "active_soft_plan_id": plan.soft_plan_id,
            "soft_replacement_count": reservation.soft_replacement_count
            + (1 if plan.supersedes_soft_plan_id else 0),
            "updated_at": plan.selected_at,
            "version": expected_version + 1,
        }
        result = self._connection.execute(
            update(ride_reservations)
            .where(
                ride_reservations.c.reservation_id == reservation.reservation_id,
                ride_reservations.c.version == expected_version,
                ride_reservations.c.active_commitment_id.is_(None),
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise ReservationConflict("Reservation changed or commitment locked")
        PostgresAuditEventRepository(self._connection).append(audit_event)
        return reservation.model_copy(update=values)

    def commit_driver(
        self,
        reservation: ScheduledReservation,
        commitment: DriverCommitment,
        *,
        expected_version: int,
        audit_event: AuditEvent,
    ) -> ScheduledReservation:
        try:
            self._connection.execute(
                insert(reservation_driver_commitments).values(
                    commitment_id=commitment.commitment_id,
                    reservation_id=commitment.reservation_id,
                    driver_id=commitment.driver_id,
                    state=commitment.state.value,
                    window_started_at=commitment.window_started_at,
                    window_ended_at=commitment.window_ended_at,
                    payload=commitment.model_dump(mode="json"),
                    version=commitment.version,
                    created_at=commitment.committed_at,
                )
            )
        except IntegrityError as error:
            raise ReservationConflict("Driver commitment overlaps") from error
        values = {
            "active_commitment_id": commitment.commitment_id,
            "state": ReservationState.DRIVER_COMMITTED.value,
            "updated_at": datetime.now(UTC),
            "version": expected_version + 1,
        }
        result = self._connection.execute(
            update(ride_reservations)
            .where(
                ride_reservations.c.reservation_id == reservation.reservation_id,
                ride_reservations.c.version == expected_version,
                ride_reservations.c.active_commitment_id.is_(None),
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise ReservationConflict("Commitment race lost")
        PostgresAuditEventRepository(self._connection).append(audit_event)
        return reservation.model_copy(update=values)
