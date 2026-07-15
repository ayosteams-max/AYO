import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.scheduled.contracts import ScheduledDispatchStrategy, ScheduledRepository
from BACKEND.scheduled.engine import (
    ReservationConflict,
    plan_soft_candidate,
    should_replace_soft_candidate,
    transition,
    validate_formal_replacement,
)
from BACKEND.scheduled.models import (
    CandidateDecision,
    ConsentState,
    DriverCommitment,
    Participant,
    ParticipantRole,
    ReservationPolicy,
    ReservationState,
    ScheduledCandidate,
    ScheduledReservation,
)


def _audit(
    reservation: ScheduledReservation,
    action: str,
    reason: str,
    *,
    actor_type: ActorType = ActorType.SYSTEM,
    actor_id: UUID | None = None,
    correlation_id: UUID | None = None,
) -> AuditEvent:
    return AuditEvent(
        actor_type=actor_type,
        actor_id=str(actor_id) if actor_id else None,
        action=action,
        resource_type="scheduled_reservation",
        resource_id=str(reservation.reservation_id),
        outcome=AuditOutcome.SUCCESS,
        reason=reason,
        correlation_id=correlation_id or uuid4(),
        source_module="scheduled",
        safe_metadata={"policy_version": reservation.policy_version},
    )


def request_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


class ScheduledRideApplication:
    def __init__(
        self,
        repository: ScheduledRepository,
        strategy: ScheduledDispatchStrategy,
        policy: ReservationPolicy,
    ) -> None:
        self._repository = repository
        self._strategy = strategy
        self._policy = policy

    def create(
        self,
        reservation: ScheduledReservation,
        participants: tuple[Participant, ...],
        *,
        idempotency_key: str,
        now: datetime,
    ) -> tuple[ScheduledReservation, bool]:
        lead = (reservation.requested_pickup_at - now.astimezone(UTC)).total_seconds()
        if not (
            self._policy.minimum_booking_lead_seconds
            <= lead
            <= self._policy.maximum_booking_horizon_seconds
        ):
            raise ReservationConflict("Requested pickup is outside booking horizon")
        bookers = [item for item in participants if item.role is ParticipantRole.BOOKER]
        passengers = [
            item for item in participants if item.role is ParticipantRole.PASSENGER
        ]
        if len(bookers) != 1 or len(passengers) != 1:
            raise ReservationConflict("Exactly one booker and passenger are required")
        if passengers[0].participant_id != reservation.passenger_participant_id:
            raise ReservationConflict("Passenger reference does not match")
        third_party = bookers[0].identity_id != passengers[0].identity_id
        if third_party and passengers[0].consent_state not in {
            ConsentState.PENDING,
            ConsentState.ASSISTED_REQUIRED,
            ConsentState.CONFIRMED,
        }:
            raise ReservationConflict("Third-party passenger confirmation is required")
        fingerprint = hashlib.sha256(idempotency_key.encode()).hexdigest()
        payload_hash = request_hash(
            {
                "booker": reservation.booker_id,
                "passenger": reservation.passenger_participant_id,
                "pickup": reservation.pickup_place_id,
                "destination": reservation.destination_place_id,
                "pickup_at": reservation.requested_pickup_at,
            }
        )
        return self._repository.create(
            reservation,
            participants=participants,
            idempotency_fingerprint=fingerprint,
            request_hash=payload_hash,
            audit_event=_audit(
                reservation,
                "reservation.requested",
                "third_party" if third_party else "self_booking",
                actor_type=ActorType.RIDER,
                actor_id=reservation.booker_id,
            ),
        )

    def plan(
        self,
        reservation: ScheduledReservation,
        candidates: list[ScheduledCandidate],
        *,
        now: datetime,
        incumbent: CandidateDecision | None = None,
    ) -> ScheduledReservation:
        decisions = self._strategy.rank(reservation, candidates, now=now)
        if not decisions:
            return transition(
                reservation, ReservationState.NO_DRIVER_AVAILABLE, now=now
            )
        selected = decisions[0]
        previous = None
        reason = "soft_candidate_selected"
        if incumbent is not None:
            replace, reasons = should_replace_soft_candidate(
                incumbent, selected, reservation, self._policy
            )
            if not replace:
                return reservation
            reason = reasons[0]
        plan = plan_soft_candidate(
            reservation,
            selected,
            now=now,
            expires_at=now + timedelta(seconds=self._policy.soft_planning_lead_seconds),
            previous=previous,
        )
        return self._repository.save_soft_plan(
            reservation,
            plan,
            expected_version=reservation.version,
            audit_event=_audit(reservation, "reservation.soft_plan.selected", reason),
        )

    def authorize_committed_replacement(
        self, reservation: ScheduledReservation, trigger: str
    ) -> None:
        allowed, reason = validate_formal_replacement(
            reservation, trigger, self._policy
        )
        if not allowed:
            raise ReservationConflict(reason)

    def commit(
        self,
        reservation: ScheduledReservation,
        decision: CandidateDecision,
        *,
        now: datetime,
    ) -> ScheduledReservation:
        lead = timedelta(seconds=self._policy.formal_commitment_lead_seconds)
        commitment = DriverCommitment(
            reservation_id=reservation.reservation_id,
            driver_id=decision.driver_id,
            window_started_at=reservation.requested_pickup_at - lead,
            window_ended_at=reservation.requested_pickup_at + lead,
            committed_at=now,
            policy_version=self._policy.version,
        )
        return self._repository.commit_driver(
            reservation,
            commitment,
            expected_version=reservation.version,
            audit_event=_audit(
                reservation, "reservation.driver.committed", "driver_committed"
            ),
        )
