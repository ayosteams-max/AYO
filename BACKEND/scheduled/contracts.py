from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.audit.models import AuditEvent
from BACKEND.scheduled.models import (
    AirportContext,
    CandidateDecision,
    DriverCommitment,
    Participant,
    ScheduledCandidate,
    ScheduledReservation,
    SoftPlan,
)


class ScheduledDispatchStrategy(Protocol):
    def rank(
        self,
        reservation: ScheduledReservation,
        candidates: list[ScheduledCandidate],
        *,
        now: datetime,
        airport_context: AirportContext | None = None,
    ) -> list[CandidateDecision]: ...


class CompletionTimeProvider(Protocol):
    def completion_range(self, driver_id: UUID) -> tuple[int, int, int]: ...


class AirportPolicyProvider(Protocol):
    def context_for(
        self, reservation_id: UUID, now: datetime
    ) -> AirportContext | None: ...


class FlightStatusProvider(Protocol):
    def refresh(self, context: AirportContext, now: datetime) -> AirportContext: ...


class ScheduledRepository(Protocol):
    def create(
        self,
        reservation: ScheduledReservation,
        *,
        participants: tuple[Participant, ...],
        idempotency_fingerprint: str,
        request_hash: str,
        audit_event: AuditEvent,
    ) -> tuple[ScheduledReservation, bool]: ...

    def get(self, reservation_id: UUID) -> ScheduledReservation | None: ...

    def save_soft_plan(
        self,
        reservation: ScheduledReservation,
        plan: SoftPlan,
        *,
        expected_version: int,
        audit_event: AuditEvent,
    ) -> ScheduledReservation: ...

    def commit_driver(
        self,
        reservation: ScheduledReservation,
        commitment: DriverCommitment,
        *,
        expected_version: int,
        audit_event: AuditEvent,
    ) -> ScheduledReservation: ...
