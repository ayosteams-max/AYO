import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.dispatch.contracts import DispatchConflict, DispatchRepository
from BACKEND.dispatch.models import (
    CreateRideCommand,
    DispatchPolicy,
    DispatchRide,
    DriverOffer,
    RideProjection,
    RideState,
    project_ride,
)
from BACKEND.dispatch.scoring import score_candidates


class QuoteExpired(ValueError):
    pass


class ImmediateDispatchService:
    def __init__(self, repository: DispatchRepository, policy: DispatchPolicy) -> None:
        self._repository = repository
        self._policy = policy

    @staticmethod
    def _fingerprint(value: str) -> str:
        if len(value) < 16 or len(value) > 128:
            raise ValueError("Idempotency key length is invalid")
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _request_hash(command: CreateRideCommand) -> str:
        return hashlib.sha256(
            command.model_dump_json(exclude_none=False).encode()
        ).hexdigest()

    def create_ride(
        self,
        *,
        rider_id: UUID,
        idempotency_key: str,
        command: CreateRideCommand,
        now: datetime | None = None,
    ) -> tuple[RideProjection, bool]:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        if command.quote.expires_at <= instant:
            raise QuoteExpired("Quote has expired")
        ride = DispatchRide(
            rider_id=rider_id,
            pickup=command.pickup,
            destination=command.destination,
            service_type=command.service_type,
            quote=command.quote,
            accepted_at=instant,
            updated_at=instant,
        )
        correlation_id = ride.ride_id
        event = AuditEvent(
            actor_type=ActorType.RIDER,
            actor_id=str(rider_id),
            action="dispatch.ride.create",
            resource_type="ride",
            resource_id=str(ride.ride_id),
            outcome=AuditOutcome.SUCCESS,
            reason="request_accepted",
            correlation_id=correlation_id,
            source_module="dispatch",
            safe_metadata={
                "operation": "create",
                "state_to": RideState.SEARCHING.value,
                "policy_version": self._policy.version,
            },
            idempotency_key=self._fingerprint(idempotency_key),
        )
        stored, created = self._repository.create_ride_idempotently(
            rider_id=rider_id,
            idempotency_fingerprint=self._fingerprint(idempotency_key),
            request_hash=self._request_hash(command),
            ride=ride,
            audit_event=event,
        )
        return project_ride(stored), created

    def dispatch_next(
        self, ride_id: UUID, *, now: datetime | None = None
    ) -> DriverOffer | None:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        ride = self._repository.get_ride(ride_id)
        if ride is None or ride.state != RideState.SEARCHING:
            raise DispatchConflict("Ride is not searching")
        candidates = self._repository.list_candidates(
            ride=ride, now=instant, limit=self._policy.maximum_candidates
        )
        scores = score_candidates(ride, candidates, self._policy, instant)
        if not scores:
            self._repository.mark_no_driver(
                ride_id=ride.ride_id,
                expected_version=ride.version,
                now=instant,
                audit_event=self._system_event(
                    ride,
                    "dispatch.ride.no_driver",
                    "no_eligible_driver",
                    instant,
                ),
            )
            return None
        score = scores[0]
        offer = DriverOffer(
            ride_id=ride.ride_id,
            driver_id=score.driver_id,
            created_at=instant,
            expires_at=instant + timedelta(seconds=self._policy.offer_timeout_seconds),
            policy_version=self._policy.version,
            score=score,
        )
        self._repository.reserve_and_offer(
            expected_ride_version=ride.version,
            offer=offer,
            audit_event=self._system_event(
                ride, "dispatch.offer.create", "candidate_selected", instant
            ),
        )
        return offer

    def decline_and_reassign(
        self, offer_id: UUID, driver_id: UUID, *, now: datetime | None = None
    ) -> DriverOffer | None:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        offer = self._require_offer(offer_id, driver_id)
        ride = self._require_ride(offer.ride_id)
        requeued = self._repository.resolve_offer_and_requeue(
            offer_id=offer_id,
            driver_id=driver_id,
            outcome="declined",
            now=instant,
            audit_event=self._driver_event(
                ride, driver_id, "dispatch.offer.decline", "driver_declined", instant
            ),
        )
        return self.dispatch_next(requeued.ride_id, now=instant)

    def expire_and_reassign(
        self, offer_id: UUID, *, now: datetime | None = None
    ) -> DriverOffer | None:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        offer = self._repository.get_offer(offer_id)
        if offer is None:
            raise DispatchConflict("Offer is unavailable")
        ride = self._require_ride(offer.ride_id)
        requeued = self._repository.resolve_offer_and_requeue(
            offer_id=offer_id,
            driver_id=offer.driver_id,
            outcome="expired",
            now=instant,
            audit_event=self._system_event(
                ride, "dispatch.offer.expire", "offer_timeout", instant
            ),
        )
        return self.dispatch_next(requeued.ride_id, now=instant)

    def accept_offer(
        self,
        offer_id: UUID,
        driver_id: UUID,
        *,
        now: datetime | None = None,
    ) -> RideProjection:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        offer = self._require_offer(offer_id, driver_id)
        ride = self._require_ride(offer.ride_id)
        assigned = self._repository.accept_offer(
            offer_id=offer_id,
            driver_id=driver_id,
            now=instant,
            audit_event=self._driver_event(
                ride, driver_id, "dispatch.offer.accept", "driver_accepted", instant
            ),
        )
        return project_ride(assigned)

    def recover_active_ride(self, rider_id: UUID) -> RideProjection | None:
        ride = self._repository.get_active_ride_for_rider(rider_id)
        return project_ride(ride) if ride else None

    def recover_expired_offers(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> int:
        if not 1 <= limit <= 1_000:
            raise ValueError("Recovery limit must be between 1 and 1000")
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        offers = self._repository.list_expired_active_offers(now=instant, limit=limit)
        recovered = 0
        for offer in offers:
            try:
                self.expire_and_reassign(offer.offer_id, now=instant)
                recovered += 1
            except DispatchConflict:
                # Another worker won; authoritative state is already progressing.
                continue
        return recovered

    def _require_offer(self, offer_id: UUID, driver_id: UUID) -> DriverOffer:
        offer = self._repository.get_offer(offer_id)
        if offer is None or offer.driver_id != driver_id:
            raise DispatchConflict("Offer is unavailable")
        return offer

    def _require_ride(self, ride_id: UUID) -> DispatchRide:
        ride = self._repository.get_ride(ride_id)
        if ride is None:
            raise DispatchConflict("Ride is unavailable")
        return ride

    def _system_event(
        self,
        ride: DispatchRide,
        action: str,
        reason: str,
        now: datetime,
    ) -> AuditEvent:
        return AuditEvent(
            occurred_at=now,
            recorded_at=now,
            actor_type=ActorType.SYSTEM,
            action=action,
            resource_type="ride",
            resource_id=str(ride.ride_id),
            outcome=AuditOutcome.SUCCESS,
            reason=reason,
            correlation_id=ride.ride_id,
            source_module="dispatch",
            safe_metadata={"policy_version": self._policy.version},
        )

    def _driver_event(
        self,
        ride: DispatchRide,
        driver_id: UUID,
        action: str,
        reason: str,
        now: datetime,
    ) -> AuditEvent:
        return AuditEvent(
            occurred_at=now,
            recorded_at=now,
            actor_type=ActorType.DRIVER,
            actor_id=str(driver_id),
            action=action,
            resource_type="ride",
            resource_id=str(ride.ride_id),
            outcome=AuditOutcome.SUCCESS,
            reason=reason,
            correlation_id=ride.ride_id,
            source_module="dispatch",
            safe_metadata={"policy_version": self._policy.version},
        )
