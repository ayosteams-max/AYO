from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.audit.models import AuditEvent
from BACKEND.dispatch.models import (
    DispatchRide,
    DriverCandidate,
    DriverOffer,
)


class IdempotencyConflict(ValueError):
    """The same key was reused for a different command."""


class DispatchConflict(RuntimeError):
    """Authoritative dispatch state changed concurrently or is no longer valid."""


class DispatchRepository(Protocol):
    def create_ride_idempotently(
        self,
        *,
        rider_id: UUID,
        idempotency_fingerprint: str,
        request_hash: str,
        ride: DispatchRide,
        audit_event: AuditEvent,
    ) -> tuple[DispatchRide, bool]: ...

    def get_ride(self, ride_id: UUID) -> DispatchRide | None: ...

    def get_active_ride_for_rider(self, rider_id: UUID) -> DispatchRide | None: ...

    def list_candidates(
        self, *, ride: DispatchRide, now: datetime, limit: int
    ) -> list[DriverCandidate]: ...

    def reserve_and_offer(
        self,
        *,
        expected_ride_version: int,
        offer: DriverOffer,
        audit_event: AuditEvent,
    ) -> DispatchRide: ...

    def resolve_offer_and_requeue(
        self,
        *,
        offer_id: UUID,
        driver_id: UUID,
        outcome: str,
        now: datetime,
        audit_event: AuditEvent,
    ) -> DispatchRide: ...

    def accept_offer(
        self,
        *,
        offer_id: UUID,
        driver_id: UUID,
        now: datetime,
        audit_event: AuditEvent,
    ) -> DispatchRide: ...

    def get_offer(self, offer_id: UUID) -> DriverOffer | None: ...

    def list_expired_active_offers(
        self, *, now: datetime, limit: int
    ) -> list[DriverOffer]: ...

    def mark_no_driver(
        self,
        *,
        ride_id: UUID,
        expected_version: int,
        now: datetime,
        audit_event: AuditEvent,
    ) -> DispatchRide: ...

    def append_audit(self, event: AuditEvent) -> None: ...
