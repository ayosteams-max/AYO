from datetime import datetime, timedelta
from uuid import UUID

from BACKEND.active_ride.models import (
    ActiveRide,
    ActiveRideState,
    ConfidenceDecision,
    ConfidenceLevel,
    ConfidencePolicy,
    ConfidenceSignals,
    DataQualityStatus,
)
from BACKEND.domain.rides import RideStatus


class ActiveRideConflict(Exception):
    pass


ALLOWED_TRANSITIONS: dict[ActiveRideState, frozenset[ActiveRideState]] = {
    ActiveRideState.REQUEST_ACCEPTED: frozenset({ActiveRideState.SEARCHING}),
    ActiveRideState.SEARCHING: frozenset(
        {
            ActiveRideState.OFFERING,
            ActiveRideState.NO_DRIVER_AVAILABLE,
            ActiveRideState.CANCELLATION_PENDING,
        }
    ),
    ActiveRideState.OFFERING: frozenset(
        {
            ActiveRideState.SEARCHING,
            ActiveRideState.ASSIGNED,
            ActiveRideState.NO_DRIVER_AVAILABLE,
            ActiveRideState.CANCELLATION_PENDING,
        }
    ),
    ActiveRideState.ASSIGNED: frozenset(
        {
            ActiveRideState.DRIVER_EN_ROUTE,
            ActiveRideState.REASSIGNING,
            ActiveRideState.CANCELLATION_PENDING,
            ActiveRideState.OPERATIONAL_RECOVERY,
        }
    ),
    ActiveRideState.DRIVER_EN_ROUTE: frozenset(
        {
            ActiveRideState.DRIVER_ARRIVED,
            ActiveRideState.REASSIGNING,
            ActiveRideState.CANCELLATION_PENDING,
            ActiveRideState.OPERATIONAL_RECOVERY,
        }
    ),
    ActiveRideState.DRIVER_ARRIVED: frozenset(
        {
            ActiveRideState.PICKUP_VERIFICATION_PENDING,
            ActiveRideState.NO_SHOW_REVIEW,
            ActiveRideState.REASSIGNING,
            ActiveRideState.CANCELLATION_PENDING,
            ActiveRideState.OPERATIONAL_RECOVERY,
        }
    ),
    ActiveRideState.PICKUP_VERIFICATION_PENDING: frozenset(
        {
            ActiveRideState.PICKUP_VERIFIED,
            ActiveRideState.NO_SHOW_REVIEW,
            ActiveRideState.REASSIGNING,
            ActiveRideState.CANCELLATION_PENDING,
            ActiveRideState.OPERATIONAL_RECOVERY,
        }
    ),
    ActiveRideState.PICKUP_VERIFIED: frozenset(
        {ActiveRideState.IN_PROGRESS, ActiveRideState.CANCELLATION_PENDING}
    ),
    ActiveRideState.IN_PROGRESS: frozenset(
        {
            ActiveRideState.IN_PROGRESS,
            ActiveRideState.DESTINATION_APPROACHING,
            ActiveRideState.COMPLETION_PENDING,
            ActiveRideState.OPERATIONAL_RECOVERY,
        }
    ),
    ActiveRideState.DESTINATION_APPROACHING: frozenset(
        {ActiveRideState.COMPLETION_PENDING, ActiveRideState.OPERATIONAL_RECOVERY}
    ),
    ActiveRideState.COMPLETION_PENDING: frozenset(
        {ActiveRideState.COMPLETED, ActiveRideState.OPERATIONAL_RECOVERY}
    ),
    ActiveRideState.REASSIGNING: frozenset(
        {
            ActiveRideState.SEARCHING,
            ActiveRideState.ASSIGNED,
            ActiveRideState.NO_DRIVER_AVAILABLE,
        }
    ),
    ActiveRideState.CANCELLATION_PENDING: frozenset(
        {ActiveRideState.CANCELLED, ActiveRideState.OPERATIONAL_REVIEW}
    ),
    ActiveRideState.NO_SHOW_REVIEW: frozenset(
        {
            ActiveRideState.PICKUP_VERIFICATION_PENDING,
            ActiveRideState.CANCELLED,
            ActiveRideState.OPERATIONAL_REVIEW,
        }
    ),
    ActiveRideState.OPERATIONAL_RECOVERY: frozenset(
        {
            ActiveRideState.REASSIGNING,
            ActiveRideState.CANCELLED,
            ActiveRideState.OPERATIONAL_REVIEW,
            ActiveRideState.DRIVER_EN_ROUTE,
            ActiveRideState.IN_PROGRESS,
        }
    ),
}


def transition(
    ride: ActiveRide, target: ActiveRideState, *, now: datetime
) -> ActiveRide:
    if target not in ALLOWED_TRANSITIONS.get(ride.state, frozenset()):
        raise ActiveRideConflict(
            f"unsupported_transition:{ride.state.value}:{target.value}"
        )
    return ride.model_copy(
        update={
            "state": target,
            "updated_at": now,
            "version": ride.version + 1,
            "last_sequence": ride.last_sequence + 1,
        }
    )


LEGACY_TRANSLATION: dict[RideStatus, ActiveRideState] = {
    RideStatus.REQUESTED: ActiveRideState.REQUEST_ACCEPTED,
    RideStatus.SEARCHING_FOR_DRIVER: ActiveRideState.SEARCHING,
    RideStatus.WAITING_FOR_DRIVER: ActiveRideState.OFFERING,
    RideStatus.DRIVER_ACCEPTED: ActiveRideState.ASSIGNED,
    RideStatus.DRIVER_ON_THE_WAY: ActiveRideState.DRIVER_EN_ROUTE,
    RideStatus.DRIVER_ARRIVED: ActiveRideState.DRIVER_ARRIVED,
    RideStatus.TRIP_STARTED: ActiveRideState.IN_PROGRESS,
    RideStatus.TRIP_COMPLETED: ActiveRideState.COMPLETED,
    RideStatus.RIDER_CANCELLED: ActiveRideState.CANCELLED,
    RideStatus.DRIVER_CANCELLED: ActiveRideState.REASSIGNING,
}


def translate_legacy_status(status: RideStatus) -> ActiveRideState:
    try:
        return LEGACY_TRANSLATION[status]
    except KeyError as error:
        raise ActiveRideConflict(f"ambiguous_legacy_status:{status.value}") from error


def evaluate_confidence(
    ride_id: UUID,
    signals: ConfidenceSignals,
    policy: ConfidencePolicy,
    *,
    now: datetime,
    previous: ConfidenceDecision | None = None,
) -> ConfidenceDecision:
    reasons: list[str] = []
    actions: list[str] = []
    ages = [
        age
        for age in (
            signals.driver_location_age_seconds,
            signals.rider_location_age_seconds,
        )
        if age is not None
    ]
    if not ages or all(age > policy.maximum_location_age_seconds for age in ages):
        return ConfidenceDecision(
            ride_id=ride_id,
            rule_set_id=policy.rule_set_id,
            rule_set_version=policy.version,
            health_level=ConfidenceLevel.INSUFFICIENT_DATA,
            reason_codes=("insufficient_fresh_evidence",),
            signal_freshness={"locations": "stale_or_missing"},
            data_quality_status=DataQualityStatus.STALE,
            generated_at=now,
            expires_at=now + timedelta(seconds=policy.decision_ttl_seconds),
            recommended_actions=("request_location_observation",),
        )
    if signals.provider_unavailable:
        reasons.append("map_provider_unavailable")
    if signals.verified_external_delay:
        reasons.append("verified_external_delay")
    severe = (
        signals.locations_conflict
        or signals.repeated_verification_failure
        or signals.lifecycle_stagnation_seconds >= policy.stagnation_seconds
    )
    risk = (
        signals.driver_moving_away
        or signals.unexpected_stop
        or (signals.pickup_eta_increase_seconds or 0)
        >= policy.at_risk_eta_increase_seconds
    )
    watch = (
        signals.pickup_eta_increase_seconds or 0
    ) >= policy.watch_eta_increase_seconds or signals.provider_unavailable
    stability_met = signals.anomaly_duration_seconds >= policy.hysteresis_seconds
    if severe and stability_met:
        level = ConfidenceLevel.CRITICAL
        actions.append("alert_operations")
        reasons.append("lifecycle_or_pickup_material_risk")
    elif risk and stability_met:
        level = ConfidenceLevel.AT_RISK
        actions.append(
            "refresh_eta" if signals.verified_external_delay else "prepare_reassignment"
        )
        reasons.append("pickup_progress_at_risk")
    elif severe or risk or watch:
        level = ConfidenceLevel.WATCH
        actions.append("refresh_eta")
        reasons.append(
            "stability_margin_not_met" if severe or risk else "pickup_progress_watch"
        )
    else:
        level = ConfidenceLevel.HEALTHY
        reasons.append("signals_consistent")
    if (
        previous is not None
        and previous.health_level is level
        and (now - previous.generated_at).total_seconds()
        < policy.alert_cooldown_seconds
    ):
        actions = []
        reasons.append("alert_cooldown_active")
    return ConfidenceDecision(
        ride_id=ride_id,
        rule_set_id=policy.rule_set_id,
        rule_set_version=policy.version,
        health_level=level,
        reason_codes=tuple(dict.fromkeys(reasons)),
        signal_freshness={"locations": "fresh"},
        data_quality_status=DataQualityStatus.DEGRADED
        if signals.provider_unavailable
        else DataQualityStatus.GOOD,
        generated_at=now,
        expires_at=now + timedelta(seconds=policy.decision_ttl_seconds),
        recommended_actions=tuple(actions),
    )
