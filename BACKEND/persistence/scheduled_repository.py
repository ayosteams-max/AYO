from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.audit.models import AuditEvent
from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.tables import (
    dispatch_outbox,
    reservation_consents,
    reservation_driver_commitments,
    reservation_idempotency_records,
    reservation_participants,
    reservation_pickup_verifications,
    reservation_soft_plans,
    reservation_state_history,
    ride_reservations,
)
from BACKEND.scheduled.engine import ALLOWED_TRANSITIONS, ReservationConflict
from BACKEND.scheduled.models import (
    ConsentState,
    DriverCommitment,
    Participant,
    ParticipantRole,
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
                raise ReservationConflict(
                    "Idempotency authority is inconsistent"
                ) from None
            return stored, False
        try:
            with self._connection.begin_nested():
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
                self._append_effects(
                    audit_event,
                    "reservation.requested",
                    reservation.reservation_id,
                    reservation.created_at,
                )
            return reservation, True
        except IntegrityError as error:
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
            if existing is None or existing.request_hash != request_hash:
                raise ReservationConflict(
                    "Concurrent reservation creation conflict"
                ) from error
            stored = self.get(existing.reservation_id)
            if stored is None:
                raise ReservationConflict(
                    "Idempotency authority is inconsistent"
                ) from error
            return stored, False

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

    def participants(self, reservation_id: UUID) -> tuple[Participant, ...]:
        rows = self._connection.execute(
            select(reservation_participants.c.payload).where(
                reservation_participants.c.reservation_id == reservation_id
            )
        ).scalars()
        return tuple(Participant.model_validate(row) for row in rows)

    def committed_driver_id(self, reservation_id: UUID) -> UUID | None:
        return self._connection.execute(
            select(reservation_driver_commitments.c.driver_id).where(
                reservation_driver_commitments.c.reservation_id == reservation_id,
                reservation_driver_commitments.c.state == "committed",
            )
        ).scalar_one_or_none()

    def mutate(
        self,
        reservation: ScheduledReservation,
        *,
        expected_version: int,
        state: ReservationState | None,
        values: dict[str, object] | None,
        audit_event: AuditEvent,
        event_type: str,
        reason: str,
        now: datetime,
    ) -> ScheduledReservation:
        changes = dict(values or {})
        if state is not None:
            if state is not reservation.state and state not in ALLOWED_TRANSITIONS.get(
                reservation.state, frozenset()
            ):
                raise ReservationConflict("Invalid reservation transition")
            changes["state"] = state.value
        changes.update({"updated_at": now, "version": expected_version + 1})
        result = self._connection.execute(
            update(ride_reservations)
            .where(
                ride_reservations.c.reservation_id == reservation.reservation_id,
                ride_reservations.c.version == expected_version,
            )
            .values(**changes)
        )
        if result.rowcount != 1:
            raise ReservationConflict("Reservation version conflict")
        self._connection.execute(
            insert(reservation_state_history).values(
                history_id=uuid4(),
                reservation_id=reservation.reservation_id,
                payload={
                    "from": reservation.state.value,
                    "to": state.value if state else reservation.state.value,
                    "reason": reason,
                    "version": expected_version + 1,
                },
                created_at=now,
            )
        )
        self._append_effects(audit_event, event_type, reservation.reservation_id, now)
        model_changes = dict(changes)
        if state is not None:
            model_changes["state"] = state
        return reservation.model_copy(update=model_changes)

    def record_consent(
        self,
        reservation: ScheduledReservation,
        participant: Participant,
        consent: ConsentState,
        *,
        expected_version: int,
        audit_event: AuditEvent,
        now: datetime,
    ) -> ScheduledReservation:
        if participant.role is not ParticipantRole.PASSENGER:
            raise ReservationConflict("Only passenger consent is valid")
        self._connection.execute(
            insert(reservation_consents).values(
                consent_id=uuid4(),
                reservation_id=reservation.reservation_id,
                payload={
                    "participant_id": str(participant.participant_id),
                    "state": consent.value,
                    "policy_version": reservation.policy_version,
                },
                created_at=now,
            )
        )
        updated_participant = participant.model_copy(update={"consent_state": consent})
        self._connection.execute(
            update(reservation_participants)
            .where(
                reservation_participants.c.participant_id == participant.participant_id
            )
            .values(
                payload=updated_participant.model_dump(mode="json"),
                version=reservation_participants.c.version + 1,
            )
        )
        target = (
            ReservationState.ACCEPTED
            if consent is ConsentState.CONFIRMED
            else ReservationState.PASSENGER_DECLINED
        )
        return self.mutate(
            reservation,
            expected_version=expected_version,
            state=target,
            values=None,
            audit_event=audit_event,
            event_type=f"reservation.passenger_{consent.value}",
            reason=f"passenger_{consent.value}",
            now=now,
        )

    def create_pickup_verification(
        self,
        reservation_id: UUID,
        *,
        code_hash: bytes,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        self._connection.execute(
            insert(reservation_pickup_verifications).values(
                verification_id=uuid4(),
                reservation_id=reservation_id,
                code_hash=code_hash,
                expires_at=expires_at,
                created_at=now,
            )
        )

    def verify_pickup(
        self, reservation_id: UUID, *, code_hash: bytes, now: datetime
    ) -> bool:
        row = (
            self._connection.execute(
                select(reservation_pickup_verifications)
                .where(
                    reservation_pickup_verifications.c.reservation_id == reservation_id
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["verified_at"] is not None:
            return False
        if row["expires_at"] <= now or row["attempt_count"] >= 5:
            return False
        valid = bytes(row["code_hash"]) == code_hash
        self._connection.execute(
            update(reservation_pickup_verifications)
            .where(
                reservation_pickup_verifications.c.verification_id
                == row["verification_id"]
            )
            .values(
                attempt_count=row["attempt_count"] + (0 if valid else 1),
                verified_at=now if valid else None,
            )
        )
        return valid

    def _append_effects(
        self,
        audit_event: AuditEvent,
        event_type: str,
        aggregate_id: UUID,
        now: datetime,
    ) -> None:
        PostgresAuditEventRepository(self._connection).append(audit_event)
        self._connection.execute(
            insert(dispatch_outbox).values(
                message_id=uuid4(),
                aggregate_type="reservation",
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload={"reservation_id": str(aggregate_id)},
                occurred_at=now,
                available_at=now,
            )
        )

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
        self._append_effects(
            audit_event,
            "reservation.soft_planned",
            reservation.reservation_id,
            plan.selected_at,
        )
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
            "updated_at": commitment.committed_at,
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
        self._append_effects(
            audit_event,
            "reservation.driver_committed",
            reservation.reservation_id,
            commitment.committed_at,
        )
        model_values = dict(values)
        model_values["state"] = ReservationState.DRIVER_COMMITTED
        return reservation.model_copy(update=model_values)
