from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.dispatch.handoff import DispatchHandoff, EligibleDriverInput, HandoffOffer
from BACKEND.dispatch.handoff_service import ImmediateHandoffService
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.handoff_dispatch_repository import HandoffConflict


class DriverOperationalEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    driver_id: UUID
    vehicle_id: UUID
    authorized_vehicle_id: UUID
    account_active: bool
    authenticated_session_active: bool
    eligibility_status: str
    eligibility_expires_at: datetime
    vehicle_approved: bool
    supported_services: frozenset[str]
    availability: str
    availability_observed_at: datetime
    earning_capability: str
    fatigue_eligible: bool
    pickup_accessible: bool
    conflicting_commitment: bool
    active_workload_count: int = Field(ge=0, le=20)
    reliability_bps: int = Field(ge=0, le=10000)
    cancellation_history_bps: int = Field(ge=0, le=10000)
    opportunity_deficit_bps: int = Field(ge=0, le=10000)
    eligibility_policy_version: str


class PickupRouteEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    driver_id: UUID
    evidence_id: str = Field(min_length=8, max_length=128)
    pickup_eta_seconds: int = Field(ge=0, le=14400)
    observed_at: datetime
    temporary_restrictions_clear: bool
    traffic_evidence_fresh: bool
    pickup_confidence_bps: int = Field(ge=0, le=10000)
    heading_consistent: bool = True


class DriverSupplyEvidenceProvider(Protocol):
    def shortlist(
        self, *, service_zone_id: UUID, service_type: str, at: datetime, limit: int
    ) -> tuple[DriverOperationalEvidence, ...]: ...


class DispatchRouteIntelligence(Protocol):
    """AYO AP-095 boundary. Implementations may use providers; Dispatch may not."""

    def pickup_routes(
        self,
        *,
        pickup_reference: UUID,
        candidates: tuple[DriverOperationalEvidence, ...],
        at: datetime,
    ) -> tuple[PickupRouteEvidence, ...]: ...


class AcceptedRideStarter(Protocol):
    def __call__(self, assignment_id: UUID, *, now: datetime) -> object: ...


class CanonicalDispatchApplication:
    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        supply: DriverSupplyEvidenceProvider,
        routes: DispatchRouteIntelligence,
        *,
        policy_version: str,
        service_actor_id: UUID,
        maximum_candidates: int = 20,
        offer_timeout_seconds: int = 15,
        maximum_evidence_age_seconds: int = 45,
        accepted_ride_starter: AcceptedRideStarter | None = None,
    ) -> None:
        if not 1 <= maximum_candidates <= 100:
            raise ValueError("Maximum candidates must be between 1 and 100")
        self._composition = composition
        self._supply = supply
        self._routes = routes
        self._service_actor_id = service_actor_id
        self._maximum_candidates = maximum_candidates
        self._accepted_ride_starter = accepted_ride_starter
        self._service = ImmediateHandoffService(
            composition,
            policy_version=policy_version,
            offer_timeout_seconds=offer_timeout_seconds,
            maximum_location_age_seconds=maximum_evidence_age_seconds,
            require_worker_session=True,
        )

    def start(
        self,
        *,
        ride_request_id: UUID,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> tuple[DispatchHandoff, HandoffOffer | None]:
        handoff = self._service.receive(
            ride_request_id=ride_request_id,
            service_actor_id=self._service_actor_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            causation_id=causation_id,
            at=at,
        )
        if handoff.state.value == "searching":
            return handoff, self.progress(handoff.handoff_id, at=at)
        return handoff, self.offer_for_handoff(handoff.handoff_id)

    def progress(self, handoff_id: UUID, *, at: datetime) -> HandoffOffer | None:
        at = at.astimezone(UTC)
        with self._composition.unit_of_work() as unit:
            handoff = unit.handoff_dispatch.get_handoff(handoff_id)
        if handoff is None or handoff.state.value != "searching":
            raise HandoffConflict("Handoff is not searching")
        operational = self._supply.shortlist(
            service_zone_id=handoff.service_zone_id,
            service_type=handoff.service_type,
            at=at,
            limit=self._maximum_candidates,
        )[: self._maximum_candidates]
        route_items = self._routes.pickup_routes(
            pickup_reference=handoff.pickup_reference,
            candidates=operational,
            at=at,
        )
        by_driver = {item.driver_id: item for item in route_items}
        observations = []
        for item in operational:
            route = by_driver.get(item.driver_id)
            if route is None:
                continue
            observations.append(
                EligibleDriverInput(
                    **item.model_dump(),
                    pickup_cost_seconds=route.pickup_eta_seconds,
                    heading_consistent=route.heading_consistent,
                    temporary_restrictions_clear=route.temporary_restrictions_clear,
                    traffic_evidence_fresh=route.traffic_evidence_fresh,
                    pickup_confidence_bps=route.pickup_confidence_bps,
                    route_evidence_id=route.evidence_id,
                    route_observed_at=route.observed_at,
                )
            )
        return self._service.offer_next(handoff_id, observations=observations, at=at)

    def respond(
        self,
        *,
        subject: AuthorizationSubject,
        offer_id: UUID,
        accept: bool,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
    ) -> UUID | None:
        if subject.identity_type is not IdentityType.DRIVER:
            raise HandoffConflict("driver_authentication_required")
        assignment = self._service.respond(
            offer_id=offer_id,
            driver_id=subject.identity_id,
            accept=accept,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            at=at,
        )
        if (
            accept
            and assignment is not None
            and self._accepted_ride_starter is not None
        ):
            # Idempotent Active Ride creation closes the assignment-to-trip handoff.
            self._accepted_ride_starter(assignment, now=at)
        if not accept:
            with self._composition.unit_of_work() as unit:
                offer = unit.handoff_dispatch.get_offer(offer_id)
            if offer is not None:
                with self._composition.unit_of_work() as unit:
                    handoff = unit.handoff_dispatch.get_handoff(offer.handoff_id)
                if handoff is not None and handoff.state.value == "searching":
                    self.progress(offer.handoff_id, at=at)
        return assignment

    def offer_for_driver(self, driver_id: UUID) -> HandoffOffer | None:
        with self._composition.unit_of_work() as unit:
            return unit.handoff_dispatch.get_active_offer_for_driver(driver_id)

    def offer_for_handoff(self, handoff_id: UUID) -> HandoffOffer | None:
        with self._composition.unit_of_work() as unit:
            return unit.handoff_dispatch.get_active_offer_for_handoff(handoff_id)

    def status_for_rider(
        self, *, rider_id: UUID, ride_request_id: UUID
    ) -> DispatchHandoff | None:
        with self._composition.unit_of_work() as unit:
            return unit.handoff_dispatch.get_handoff_for_rider(
                rider_id=rider_id, ride_request_id=ride_request_id
            )

    def active_ride_id_for_request(
        self, *, rider_id: UUID, ride_request_id: UUID
    ) -> UUID | None:
        with self._composition.unit_of_work() as unit:
            ride = unit.active_rides.get_for_ride_request(ride_request_id)
            return None if ride is None or ride.rider_id != rider_id else ride.ride_id

    def active_ride_id_for_assignment(self, assignment_id: UUID) -> UUID | None:
        with self._composition.unit_of_work() as unit:
            ride = unit.active_rides.get_for_assignment(assignment_id)
            return None if ride is None else ride.ride_id

    def expire_and_redispatch(self, *, at: datetime, limit: int = 100) -> int:
        with self._composition.unit_of_work() as unit:
            expired = unit.handoff_dispatch.list_expired_offers(at=at, limit=limit)
        recovered = 0
        for offer in expired:
            try:
                self._service.expire_offer(offer.offer_id, at=at)
                self.progress(offer.handoff_id, at=at)
                recovered += 1
            except HandoffConflict:
                continue
        return recovered

    def recover(self, *, at: datetime, limit: int = 100) -> tuple[int, int, int]:
        if not 1 <= limit <= 1000:
            raise ValueError("Recovery limit must be between 1 and 1000")
        expired = self.expire_and_redispatch(at=at, limit=limit)
        with self._composition.unit_of_work() as unit:
            searching = unit.handoff_dispatch.list_searching_handoff_ids(
                at=at, limit=limit
            )
        resumed = 0
        for handoff_id in searching:
            try:
                self.progress(handoff_id, at=at)
                resumed += 1
            except (HandoffConflict, TimeoutError):
                continue
        with self._composition.unit_of_work() as unit:
            closed = unit.handoff_dispatch.close_expired_handoffs(at=at, limit=limit)
        return expired, resumed, closed


@dataclass(frozen=True, slots=True)
class CanonicalRecoveryResult:
    expired_offers: int
    resumed_searches: int
    closed_searches: int


class CanonicalDispatchRecoveryWorker:
    def __init__(
        self, application: CanonicalDispatchApplication, *, batch_limit: int = 100
    ) -> None:
        if not 1 <= batch_limit <= 1000:
            raise ValueError("Batch limit must be between 1 and 1000")
        self._application = application
        self._batch_limit = batch_limit

    def run_once(self, *, at: datetime | None = None) -> CanonicalRecoveryResult:
        instant = (at or datetime.now(UTC)).astimezone(UTC)
        expired, resumed, closed = self._application.recover(
            at=instant, limit=self._batch_limit
        )
        return CanonicalRecoveryResult(expired, resumed, closed)
