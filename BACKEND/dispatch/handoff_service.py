from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from BACKEND.dispatch.handoff import (
    DispatchHandoff,
    EligibleDriverInput,
    HandoffOffer,
    decision_reason_codes,
    rank_candidates,
)
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.handoff_dispatch_repository import HandoffConflict


class ImmediateHandoffService:
    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        *,
        policy_version: str,
        offer_timeout_seconds: int = 15,
        maximum_location_age_seconds: int = 45,
        require_worker_session: bool = False,
    ) -> None:
        self._composition = composition
        self._policy_version = policy_version
        self._offer_timeout = offer_timeout_seconds
        self._maximum_location_age = maximum_location_age_seconds
        self._require_worker_session = require_worker_session

    def receive(
        self,
        *,
        ride_request_id: UUID,
        service_actor_id: UUID,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> DispatchHandoff:
        if not 16 <= len(idempotency_key) <= 128:
            raise ValueError("Idempotency key length is invalid")
        at = at.astimezone(UTC)
        digest = sha256(
            f"{ride_request_id}:{correlation_id}:{causation_id}".encode()
        ).hexdigest()
        candidate_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.handoff_dispatch.reserve_idempotency(
                actor_id=service_actor_id,
                operation="handoff",
                key=idempotency_key,
                request_hash=digest,
                response_reference=candidate_id,
                at=at,
            )
            existing = unit.handoff_dispatch.get_handoff(canonical)
            if existing is not None:
                return existing
            source = unit.handoff_dispatch.ready_source(ride_request_id)
            if source is None:
                raise HandoffConflict("Ride request is not validated for dispatch")
            if source["expires_at"] <= at:
                raise HandoffConflict("Ride request expired")
            if source["service_zone_id"] is None:
                raise HandoffConflict("Service zone unavailable")
            handoff = DispatchHandoff(
                handoff_id=canonical,
                ride_request_id=ride_request_id,
                rider_identity_id=source["rider_identity_id"],
                service_type=source["service_type"],
                pickup_reference=source["pickup_id"],
                destination_reference=source["destination_id"],
                service_zone_id=source["service_zone_id"],
                service_zone_version=source["zone_version"],
                validation_decision_id=source["decision_id"],
                ride_request_version=source["version"],
                ride_policy_version=source["validation_policy_version"],
                dispatch_policy_version=self._policy_version,
                created_at=at,
                expires_at=source["expires_at"],
                correlation_id=correlation_id,
                causation_id=causation_id,
                idempotency_identity=sha256(idempotency_key.encode()).hexdigest(),
                audit_reference=uuid4(),
            )
            return unit.handoff_dispatch.create_handoff(handoff)

    def offer_next(
        self, handoff_id: UUID, *, observations: list[EligibleDriverInput], at: datetime
    ) -> HandoffOffer | None:
        at = at.astimezone(UTC)
        with self._composition.unit_of_work() as unit:
            handoff = unit.handoff_dispatch.get_handoff(handoff_id)
            if handoff is None or handoff.expires_at <= at:
                raise HandoffConflict("Handoff unavailable")
            authoritative = [
                item
                for item in observations
                if unit.handoff_dispatch.eligibility_current(
                    item.driver_id, item.vehicle_id, now=at
                )
                and (
                    not self._require_worker_session
                    or unit.worker_sessions.ride_driver_online(
                        identity_id=item.driver_id,
                        vehicle_id=item.vehicle_id,
                        service_zone_id=handoff.service_zone_id,
                        now=at,
                    )
                )
            ]
            ranked = rank_candidates(
                authoritative, now=at, max_age_seconds=self._maximum_location_age
            )
            unit.handoff_dispatch.record_candidates(
                handoff,
                [item.driver_id for item in ranked],
                at,
                {
                    "route_evidence_ids": [item.route_evidence_id for item in ranked],
                    "signals": [
                        "pickup_eta",
                        "availability",
                        "vehicle_eligibility",
                        "fatigue",
                        "reliability",
                        "cancellation_history",
                        "traffic",
                        "pickup_confidence",
                        "workload",
                        "fair_opportunity",
                    ],
                },
            )
            if not ranked:
                unit.handoff_dispatch.event(
                    handoff,
                    "dispatch.assignment_failed",
                    at,
                    {"reason": "no_suitable_driver"},
                )
                return None
            selected = ranked[0]
            offer = HandoffOffer(
                handoff_id=handoff_id,
                driver_id=selected.driver_id,
                vehicle_id=selected.vehicle_id,
                created_at=at,
                expires_at=at + timedelta(seconds=self._offer_timeout),
                dispatch_policy_version=self._policy_version,
                pickup_cost_seconds=selected.pickup_cost_seconds,
                route_evidence_id=selected.route_evidence_id,
                decision_reason_codes=decision_reason_codes(selected),
            )
            return unit.handoff_dispatch.create_offer(handoff, offer)

    def respond(
        self,
        *,
        offer_id: UUID,
        driver_id: UUID,
        accept: bool,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
    ) -> UUID | None:
        with self._composition.unit_of_work() as unit:
            responder = (
                unit.handoff_dispatch.respond_canonical
                if self._require_worker_session
                else unit.handoff_dispatch.respond
            )
            return responder(
                offer_id=offer_id,
                driver_id=driver_id,
                accept=accept,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                at=at,
            )

    def cancel_before_assignment(self, ride_request_id: UUID, *, at: datetime) -> bool:
        with self._composition.unit_of_work() as unit:
            return unit.handoff_dispatch.cancel_before_assignment(
                ride_request_id, at=at
            )

    def expire_offer(self, offer_id: UUID, *, at: datetime) -> None:
        with self._composition.unit_of_work() as unit:
            unit.handoff_dispatch.resolve_open_offer(offer_id, outcome="expired", at=at)

    def supersede_offer(self, offer_id: UUID, *, at: datetime) -> None:
        with self._composition.unit_of_work() as unit:
            unit.handoff_dispatch.resolve_open_offer(
                offer_id, outcome="superseded", at=at
            )
