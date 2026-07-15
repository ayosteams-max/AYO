from copy import deepcopy
from datetime import datetime
from threading import RLock
from uuid import UUID

from BACKEND.audit.models import AuditEvent
from BACKEND.dispatch.contracts import DispatchConflict, IdempotencyConflict
from BACKEND.dispatch.models import (
    DispatchRide,
    DriverAvailability,
    DriverCandidate,
    DriverOffer,
    OfferState,
    RideState,
)


class InMemoryDispatchRepository:
    """Concurrency-safe test adapter; never a production authority."""

    def __init__(self, candidates: list[DriverCandidate] | None = None) -> None:
        self._lock = RLock()
        self._rides: dict[UUID, DispatchRide] = {}
        self._offers: dict[UUID, DriverOffer] = {}
        self._candidates = {item.driver_id: item for item in candidates or []}
        self._idempotency: dict[tuple[UUID, str], tuple[str, UUID]] = {}
        self.audit_events: list[AuditEvent] = []

    def create_ride_idempotently(
        self,
        *,
        rider_id: UUID,
        idempotency_fingerprint: str,
        request_hash: str,
        ride: DispatchRide,
        audit_event: AuditEvent,
    ) -> tuple[DispatchRide, bool]:
        with self._lock:
            key = (rider_id, idempotency_fingerprint)
            existing = self._idempotency.get(key)
            if existing:
                existing_hash, ride_id = existing
                if existing_hash != request_hash:
                    raise IdempotencyConflict("Idempotency key was reused")
                return deepcopy(self._rides[ride_id]), False
            if any(
                item.rider_id == rider_id
                and item.state
                in {RideState.SEARCHING, RideState.OFFERING, RideState.ASSIGNED}
                for item in self._rides.values()
            ):
                raise DispatchConflict("Rider already has an active ride")
            self._rides[ride.ride_id] = deepcopy(ride)
            self._idempotency[key] = (request_hash, ride.ride_id)
            self.audit_events.append(audit_event)
            return deepcopy(ride), True

    def get_ride(self, ride_id: UUID) -> DispatchRide | None:
        with self._lock:
            ride = self._rides.get(ride_id)
            return deepcopy(ride) if ride else None

    def get_active_ride_for_rider(self, rider_id: UUID) -> DispatchRide | None:
        with self._lock:
            for ride in self._rides.values():
                if ride.rider_id == rider_id and ride.state in {
                    RideState.SEARCHING,
                    RideState.OFFERING,
                    RideState.ASSIGNED,
                }:
                    return deepcopy(ride)
            return None

    def list_candidates(
        self, *, ride: DispatchRide, now: datetime, limit: int
    ) -> list[DriverCandidate]:
        del ride, now
        with self._lock:
            return deepcopy(list(self._candidates.values())[:limit])

    def reserve_and_offer(
        self,
        *,
        expected_ride_version: int,
        offer: DriverOffer,
        audit_event: AuditEvent,
    ) -> DispatchRide:
        with self._lock:
            ride = self._rides.get(offer.ride_id)
            driver = self._candidates.get(offer.driver_id)
            if (
                ride is None
                or ride.version != expected_ride_version
                or ride.state != RideState.SEARCHING
                or driver is None
                or driver.availability != DriverAvailability.AVAILABLE
            ):
                raise DispatchConflict("Ride or driver is no longer offerable")
            self._candidates[driver.driver_id] = driver.model_copy(
                update={"availability": DriverAvailability.RESERVED}
            )
            updated = ride.model_copy(
                update={
                    "state": RideState.OFFERING,
                    "active_offer_id": offer.offer_id,
                    "updated_at": offer.created_at,
                    "version": ride.version + 1,
                }
            )
            self._rides[ride.ride_id] = updated
            self._offers[offer.offer_id] = offer
            self.audit_events.append(audit_event)
            return deepcopy(updated)

    def resolve_offer_and_requeue(
        self,
        *,
        offer_id: UUID,
        driver_id: UUID,
        outcome: str,
        now: datetime,
        audit_event: AuditEvent,
    ) -> DispatchRide:
        with self._lock:
            offer = self._offers.get(offer_id)
            if offer is None or offer.driver_id != driver_id:
                raise DispatchConflict("Offer is unavailable")
            target = (
                OfferState.DECLINED if outcome == "declined" else OfferState.EXPIRED
            )
            if offer.state == target:
                ride = self._rides[offer.ride_id]
                return deepcopy(ride)
            if offer.state != OfferState.CREATED:
                raise DispatchConflict("Offer is already resolved")
            if target == OfferState.EXPIRED and now < offer.expires_at:
                raise DispatchConflict("Offer has not expired")
            self._offers[offer_id] = offer.model_copy(
                update={"state": target, "version": offer.version + 1}
            )
            driver = self._candidates[driver_id]
            self._candidates[driver_id] = driver.model_copy(
                update={"availability": DriverAvailability.AVAILABLE}
            )
            ride = self._rides[offer.ride_id]
            updated = ride.model_copy(
                update={
                    "state": RideState.SEARCHING,
                    "active_offer_id": None,
                    "attempted_driver_ids": ride.attempted_driver_ids | {driver_id},
                    "updated_at": now,
                    "version": ride.version + 1,
                }
            )
            self._rides[ride.ride_id] = updated
            self.audit_events.append(audit_event)
            return deepcopy(updated)

    def accept_offer(
        self,
        *,
        offer_id: UUID,
        driver_id: UUID,
        now: datetime,
        audit_event: AuditEvent,
    ) -> DispatchRide:
        with self._lock:
            offer = self._offers.get(offer_id)
            if offer is None or offer.driver_id != driver_id:
                raise DispatchConflict("Offer is unavailable")
            ride = self._rides[offer.ride_id]
            if (
                offer.state == OfferState.ACCEPTED
                and ride.assigned_driver_id == driver_id
            ):
                return deepcopy(ride)
            if offer.state != OfferState.CREATED or now >= offer.expires_at:
                raise DispatchConflict("Offer cannot be accepted")
            self._offers[offer_id] = offer.model_copy(
                update={"state": OfferState.ACCEPTED, "version": offer.version + 1}
            )
            driver = self._candidates[driver_id]
            self._candidates[driver_id] = driver.model_copy(
                update={"availability": DriverAvailability.ASSIGNED}
            )
            updated = ride.model_copy(
                update={
                    "state": RideState.ASSIGNED,
                    "assigned_driver_id": driver_id,
                    "updated_at": now,
                    "version": ride.version + 1,
                }
            )
            self._rides[ride.ride_id] = updated
            self.audit_events.append(audit_event)
            return deepcopy(updated)

    def get_offer(self, offer_id: UUID) -> DriverOffer | None:
        with self._lock:
            offer = self._offers.get(offer_id)
            return deepcopy(offer) if offer else None

    def list_expired_active_offers(
        self, *, now: datetime, limit: int
    ) -> list[DriverOffer]:
        with self._lock:
            return deepcopy(
                [
                    offer
                    for offer in self._offers.values()
                    if offer.state == OfferState.CREATED and offer.expires_at <= now
                ][:limit]
            )

    def mark_no_driver(
        self,
        *,
        ride_id: UUID,
        expected_version: int,
        now: datetime,
        audit_event: AuditEvent,
    ) -> DispatchRide:
        with self._lock:
            ride = self._rides.get(ride_id)
            if (
                ride is None
                or ride.version != expected_version
                or ride.state != RideState.SEARCHING
            ):
                raise DispatchConflict("Ride is no longer searching")
            updated = ride.model_copy(
                update={
                    "state": RideState.NO_DRIVER_AVAILABLE,
                    "updated_at": now,
                    "version": ride.version + 1,
                }
            )
            self._rides[ride_id] = updated
            self.audit_events.append(audit_event)
            return deepcopy(updated)

    def append_audit(self, event: AuditEvent) -> None:
        with self._lock:
            self.audit_events.append(event)
