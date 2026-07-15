from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from BACKEND.scheduled.models import (
    AirportContext,
    CandidateDecision,
    FlightState,
    PreDispatchProjection,
    PreDispatchState,
    ReservationPolicy,
    ReservationState,
    ScheduledCandidate,
    ScheduledReservation,
    SoftPlan,
)

POST_COMMITMENT_TRIGGERS = frozenset(
    {
        "driver_cancelled",
        "driver_offline_or_unreachable",
        "vehicle_breakdown",
        "major_lateness_risk",
        "conflicting_commitment",
        "eligibility_failure",
        "safety_failure",
        "emergency",
        "confirmed_operational_failure",
    }
)

ALLOWED_TRANSITIONS: dict[ReservationState, frozenset[ReservationState]] = {
    ReservationState.REQUESTED: frozenset(
        {
            ReservationState.PASSENGER_CONFIRMATION_PENDING,
            ReservationState.ACCEPTED,
            ReservationState.RIDER_CANCELLED,
        }
    ),
    ReservationState.PASSENGER_CONFIRMATION_PENDING: frozenset(
        {
            ReservationState.ACCEPTED,
            ReservationState.PASSENGER_DECLINED,
            ReservationState.CONFIRMATION_EXPIRED,
            ReservationState.RIDER_CANCELLED,
        }
    ),
    ReservationState.ACCEPTED: frozenset(
        {ReservationState.PLANNING, ReservationState.RIDER_CANCELLED}
    ),
    ReservationState.PLANNING: frozenset(
        {
            ReservationState.DRIVER_COMMITTED,
            ReservationState.NO_DRIVER_AVAILABLE,
            ReservationState.OPERATIONAL_REVIEW,
            ReservationState.RIDER_CANCELLED,
        }
    ),
    ReservationState.DRIVER_COMMITTED: frozenset(
        {
            ReservationState.REVALIDATING,
            ReservationState.REASSIGNING,
            ReservationState.DRIVER_EN_ROUTE,
            ReservationState.RIDER_CANCELLED,
        }
    ),
    ReservationState.REVALIDATING: frozenset(
        {
            ReservationState.DRIVER_EN_ROUTE,
            ReservationState.REASSIGNING,
            ReservationState.FALLBACK_DISPATCH,
            ReservationState.OPERATIONAL_REVIEW,
            ReservationState.RIDER_CANCELLED,
        }
    ),
    ReservationState.REASSIGNING: frozenset(
        {
            ReservationState.DRIVER_COMMITTED,
            ReservationState.DRIVER_EN_ROUTE,
            ReservationState.FALLBACK_DISPATCH,
            ReservationState.NO_DRIVER_AVAILABLE,
            ReservationState.OPERATIONAL_REVIEW,
        }
    ),
    ReservationState.FALLBACK_DISPATCH: frozenset(
        {
            ReservationState.DRIVER_EN_ROUTE,
            ReservationState.NO_DRIVER_AVAILABLE,
            ReservationState.OPERATIONAL_REVIEW,
        }
    ),
    ReservationState.DRIVER_EN_ROUTE: frozenset(
        {
            ReservationState.READY_FOR_PICKUP,
            ReservationState.REASSIGNING,
            ReservationState.OPERATIONAL_REVIEW,
            ReservationState.RIDER_CANCELLED,
        }
    ),
    ReservationState.READY_FOR_PICKUP: frozenset(
        {
            ReservationState.ACTIVATED_AS_RIDE,
            ReservationState.RIDER_CANCELLED,
        }
    ),
    ReservationState.ACTIVATED_AS_RIDE: frozenset({ReservationState.FULFILLED}),
    ReservationState.OPERATIONAL_REVIEW: frozenset(
        {
            ReservationState.REASSIGNING,
            ReservationState.FALLBACK_DISPATCH,
            ReservationState.NO_DRIVER_AVAILABLE,
            ReservationState.RIDER_CANCELLED,
        }
    ),
}


class ReservationConflict(RuntimeError):
    pass


def transition(
    reservation: ScheduledReservation,
    target: ReservationState,
    *,
    now: datetime,
) -> ScheduledReservation:
    if target not in ALLOWED_TRANSITIONS.get(reservation.state, frozenset()):
        raise ReservationConflict(
            f"Invalid reservation transition: {reservation.state} -> {target}"
        )
    return reservation.model_copy(
        update={"state": target, "updated_at": now, "version": reservation.version + 1}
    )


class DeterministicScheduledStrategy:
    def __init__(self, policy: ReservationPolicy) -> None:
        self._policy = policy

    def rank(
        self,
        reservation: ScheduledReservation,
        candidates: list[ScheduledCandidate],
        *,
        now: datetime,
        airport_context: AirportContext | None = None,
    ) -> list[CandidateDecision]:
        eligible = [
            item
            for item in candidates
            if item.eligible
            and item.safety_eligible
            and not item.has_conflicting_commitment
            and item.location_observed_at <= now
            and item.prediction_confidence_bps
            >= self._policy.minimum_prediction_confidence_bps
            and item.current_trip_completion_high_seconds
            <= self._policy.maximum_current_trip_completion_seconds
            and (airport_context is None or item.airport_eligible)
        ]
        if not eligible:
            return []
        best_eta = min(item.pickup_eta_high_seconds for item in eligible)
        decisions: list[CandidateDecision] = []
        for item in eligible:
            fairness = 0
            reasons = ["eligible", "conservative_eta", "policy_versioned"]
            if (
                item.pickup_eta_high_seconds
                <= best_eta + self._policy.fairness_eta_equivalence_seconds
            ):
                fairness = min(
                    item.opportunity_deficit_bps,
                    self._policy.maximum_fairness_credit_bps,
                )
                if fairness:
                    reasons.append("bounded_opportunity_fairness")
            effective = min(10_000, item.pickup_window_success_bps + fairness)
            if item.current_trip_completion_high_seconds:
                reasons.append("current_trip_completion_protected")
            if airport_context is not None:
                reasons.append("airport_eligible")
            decisions.append(
                CandidateDecision(
                    decision_id=uuid5(
                        NAMESPACE_URL,
                        f"{reservation.reservation_id}:{item.driver_id}:{self._policy.version}",
                    ),
                    driver_id=item.driver_id,
                    policy_version=self._policy.version,
                    conservative_eta_seconds=item.pickup_eta_high_seconds,
                    reliability_bps=item.pickup_window_success_bps,
                    fairness_credit_bps=fairness,
                    effective_reliability_bps=effective,
                    reason_codes=tuple(reasons),
                )
            )
        return sorted(
            decisions,
            key=lambda item: (
                -item.effective_reliability_bps,
                item.conservative_eta_seconds,
                str(item.driver_id),
            ),
        )


def should_replace_soft_candidate(
    incumbent: CandidateDecision,
    challenger: CandidateDecision,
    reservation: ScheduledReservation,
    policy: ReservationPolicy,
) -> tuple[bool, tuple[str, ...]]:
    if reservation.active_commitment_id is not None:
        return False, ("formal_commitment_lock_active",)
    if reservation.soft_replacement_count >= policy.maximum_soft_replacements:
        return False, ("soft_replacement_limit_reached",)
    lateness_gain = (
        incumbent.conservative_eta_seconds - challenger.conservative_eta_seconds
    )
    reliability_gain = (
        challenger.effective_reliability_bps - incumbent.effective_reliability_bps
    )
    if lateness_gain <= policy.stability_margin_seconds:
        return False, ("stability_margin_not_met",)
    if (
        lateness_gain < policy.material_lateness_reduction_seconds
        or reliability_gain < policy.material_reliability_gain_bps
    ):
        return False, ("material_improvement_not_met",)
    return True, (
        "material_lateness_risk_reduction",
        "material_pickup_reliability_gain",
        "recovery_capacity_improved",
    )


def plan_soft_candidate(
    reservation: ScheduledReservation,
    decision: CandidateDecision,
    *,
    now: datetime,
    expires_at: datetime,
    previous: SoftPlan | None = None,
) -> SoftPlan:
    if reservation.active_commitment_id is not None:
        raise ReservationConflict("Formal commitment lock prevents soft planning")
    return SoftPlan(
        reservation_id=reservation.reservation_id,
        driver_id=decision.driver_id,
        decision=decision,
        selected_at=now,
        expires_at=expires_at,
        supersedes_soft_plan_id=(previous.soft_plan_id if previous else None),
    )


def validate_formal_replacement(
    reservation: ScheduledReservation,
    trigger: str,
    policy: ReservationPolicy,
) -> tuple[bool, str]:
    if trigger not in POST_COMMITMENT_TRIGGERS:
        return False, "untyped_commitment_replacement_prohibited"
    if reservation.formal_replacement_count >= policy.maximum_formal_replacements:
        return False, "formal_replacement_limit_reached"
    return True, trigger


def evaluate_pre_dispatch(
    reservation: ScheduledReservation,
    candidate: ScheduledCandidate,
    policy: ReservationPolicy,
) -> PreDispatchProjection:
    if (
        candidate.current_trip_completion_high_seconds == 0
        and candidate.eligible
        and candidate.safety_eligible
        and not candidate.has_conflicting_commitment
        and candidate.prediction_confidence_bps
        >= policy.minimum_prediction_confidence_bps
    ):
        state = PreDispatchState.CONFIRMED
        reasons: tuple[str, ...] = ("driver_available",)
    elif (
        candidate.eligible
        and candidate.safety_eligible
        and not candidate.has_conflicting_commitment
        and candidate.prediction_confidence_bps
        >= policy.minimum_prediction_confidence_bps
        and candidate.current_trip_completion_high_seconds
        <= policy.maximum_current_trip_completion_seconds
    ):
        state = PreDispatchState.PROVISIONAL
        reasons = (
            "current_trip_completion_protected",
            "conservative_completion_range",
            "no_current_trip_diversion",
        )
    else:
        state = PreDispatchState.RELEASED
        reasons = ("pre_dispatch_safeguard_failed",)
    return PreDispatchProjection(
        reservation_id=reservation.reservation_id,
        driver_id=candidate.driver_id,
        state=state,
        current_trip_completion_high_seconds=candidate.current_trip_completion_high_seconds,
        pickup_eta_high_seconds=candidate.pickup_eta_high_seconds,
        confidence_bps=candidate.prediction_confidence_bps,
        reason_codes=reasons,
    )


def effective_airport_pickup_time(
    reservation: ScheduledReservation,
    context: AirportContext,
    *,
    now: datetime,
) -> tuple[datetime, tuple[str, ...]]:
    if context.flight_state in {FlightState.CANCELLED, FlightState.DIVERTED}:
        raise ReservationConflict("Flight requires cancellation or operational review")
    if context.expires_at <= now or context.observed_at > now:
        return reservation.requested_pickup_at, ("flight_context_stale",)
    if context.estimated_arrival_at is not None:
        return context.estimated_arrival_at, ("fresh_estimated_arrival",)
    if context.scheduled_arrival_at is not None:
        return context.scheduled_arrival_at, ("scheduled_arrival_fallback",)
    return reservation.requested_pickup_at, ("rider_pickup_time_fallback",)
