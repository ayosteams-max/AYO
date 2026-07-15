from threading import RLock
from uuid import UUID

from BACKEND.audit.models import AuditEvent
from BACKEND.scheduled.engine import ReservationConflict
from BACKEND.scheduled.models import (
    DriverCommitment,
    Participant,
    ReservationState,
    ScheduledReservation,
    SoftPlan,
)


class InMemoryScheduledRepository:
    """Thread-safe local/test adapter; PostgreSQL remains production authority."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.reservations: dict[UUID, ScheduledReservation] = {}
        self.soft_plans: dict[UUID, SoftPlan] = {}
        self.commitments: dict[UUID, DriverCommitment] = {}
        self.audit_events: list[AuditEvent] = []
        self.participants: dict[UUID, Participant] = {}
        self._idempotency: dict[tuple[UUID, str], tuple[str, UUID]] = {}

    def create(
        self,
        reservation: ScheduledReservation,
        *,
        participants: tuple[Participant, ...],
        idempotency_fingerprint: str,
        request_hash: str,
        audit_event: AuditEvent,
    ) -> tuple[ScheduledReservation, bool]:
        key = reservation.booker_id, idempotency_fingerprint
        with self._lock:
            existing = self._idempotency.get(key)
            if existing is not None:
                stored_hash, reservation_id = existing
                if stored_hash != request_hash:
                    raise ReservationConflict("Idempotency key reused")
                return self.reservations[reservation_id], False
            self.reservations[reservation.reservation_id] = reservation
            self.participants.update(
                {item.participant_id: item for item in participants}
            )
            self._idempotency[key] = request_hash, reservation.reservation_id
            self.audit_events.append(audit_event)
            return reservation, True

    def get(self, reservation_id: UUID) -> ScheduledReservation | None:
        with self._lock:
            return self.reservations.get(reservation_id)

    def save_soft_plan(
        self,
        reservation: ScheduledReservation,
        plan: SoftPlan,
        *,
        expected_version: int,
        audit_event: AuditEvent,
    ) -> ScheduledReservation:
        with self._lock:
            current = self.reservations[reservation.reservation_id]
            if current.version != expected_version or current.active_commitment_id:
                raise ReservationConflict("Reservation changed or commitment locked")
            updated = current.model_copy(
                update={
                    "active_soft_plan_id": plan.soft_plan_id,
                    "soft_replacement_count": current.soft_replacement_count
                    + (1 if plan.supersedes_soft_plan_id else 0),
                    "updated_at": plan.selected_at,
                    "version": current.version + 1,
                }
            )
            self.soft_plans[plan.soft_plan_id] = plan
            self.reservations[current.reservation_id] = updated
            self.audit_events.append(audit_event)
            return updated

    def commit_driver(
        self,
        reservation: ScheduledReservation,
        commitment: DriverCommitment,
        *,
        expected_version: int,
        audit_event: AuditEvent,
    ) -> ScheduledReservation:
        with self._lock:
            current = self.reservations[reservation.reservation_id]
            if current.version != expected_version or current.active_commitment_id:
                raise ReservationConflict("Commitment race lost")
            for existing in self.commitments.values():
                if (
                    existing.driver_id == commitment.driver_id
                    and existing.state.value == "committed"
                    and existing.window_started_at < commitment.window_ended_at
                    and commitment.window_started_at < existing.window_ended_at
                ):
                    raise ReservationConflict("Driver commitment overlaps")
            updated = current.model_copy(
                update={
                    "active_commitment_id": commitment.commitment_id,
                    "state": ReservationState.DRIVER_COMMITTED,
                    "updated_at": commitment.committed_at,
                    "version": current.version + 1,
                }
            )
            self.commitments[commitment.commitment_id] = commitment
            self.reservations[current.reservation_id] = updated
            self.audit_events.append(audit_event)
            return updated
