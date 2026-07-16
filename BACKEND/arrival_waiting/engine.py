from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from BACKEND.arrival_waiting.models import (
    ArrivalEvaluation,
    ArrivalPolicy,
    ArrivalSignals,
    ArrivalState,
    ContinuitySignals,
    DepartureBehavior,
    EvidenceDecision,
    ReadinessClass,
    ReadinessDecision,
    ReadinessPolicy,
    ReadinessSignals,
    ResponsibilityClass,
    ServiceContext,
    WaitingPolicyContext,
    WaitingPolicyDefinition,
    WaitingPolicySnapshot,
    WaitingSession,
    WaitingState,
)


class ArrivalWaitingConflict(Exception):
    pass


def evaluate_arrival(
    ride_id: UUID,
    assignment_id: UUID,
    signals: ArrivalSignals,
    policy: ArrivalPolicy,
    *,
    now: datetime,
) -> ArrivalEvaluation:
    age = max(0, int((now - signals.observation.observed_at).total_seconds()))
    failures: list[str] = []
    if age > policy.maximum_location_age_seconds:
        failures.append("arrival.location_stale")
    if signals.observation.accuracy_meters > policy.maximum_accuracy_meters:
        failures.append("arrival.location_inaccurate")
    if not signals.inside_pickup_zone:
        failures.append("arrival.outside_pickup_zone")
    if signals.pickup_confidence_bps < policy.minimum_pickup_confidence_bps:
        failures.append("arrival.pickup_confidence_low")
    if signals.map_confidence_bps < policy.minimum_map_confidence_bps:
        failures.append("arrival.map_confidence_low")
    if (
        signals.observation.speed_cm_per_second
        > policy.maximum_stationary_speed_cm_per_second
    ):
        failures.append("arrival.driver_moving")
    if signals.seconds_stationary < policy.minimum_stationary_seconds:
        failures.append("arrival.stationarity_insufficient")
    if signals.heading_reliable and not signals.approach_consistent:
        failures.append("arrival.approach_inconsistent")
    if not signals.accessible_pickup:
        failures.append("arrival.pickup_inaccessible")
    if not signals.operationally_available:
        failures.append("arrival.pickup_unavailable")
    if signals.unsafe_or_restricted:
        failures.append("arrival.pickup_unsafe_or_restricted")
    if signals.service_context in {
        ServiceContext.AIRPORT_STANDARD,
        ServiceContext.AIRPORT_PREMIUM,
    }:
        if signals.airport_terminal_code is None or not signals.airport_zone_match:
            failures.append("arrival.airport_zone_mismatch")
        if not signals.airport_context_fresh:
            failures.append("arrival.airport_context_stale")
        if not signals.airport_staging_constraint_satisfied:
            failures.append("arrival.airport_staging_constraint")
        if not signals.airport_access_permitted or signals.airport_zone_closed:
            failures.append("arrival.airport_access_unavailable")
    passed = 14 - len(failures)
    confidence = max(
        0, min(signals.pickup_confidence_bps, signals.map_confidence_bps, passed * 1000)
    )
    verified = not failures and confidence >= policy.minimum_verification_confidence_bps
    reasons = (
        ("arrival.multisignal_verified",)
        if verified
        else tuple(failures or ["arrival.confidence_below_threshold"])
    )
    return ArrivalEvaluation(
        ride_id=ride_id,
        assignment_id=assignment_id,
        state=ArrivalState.ARRIVAL_VERIFIED
        if verified
        else ArrivalState.ARRIVAL_UNVERIFIED,
        confidence_bps=confidence,
        reason_codes=reasons,
        explanation_code="arrival.verified" if verified else "arrival.not_verified",
        pickup_place_id=signals.approved_pickup_place_id,
        pickup_zone_id=signals.pickup_zone_id,
        pickup_recommendation_id=signals.pickup_recommendation_id,
        pickup_recommendation_version=signals.pickup_recommendation_version,
        observation_sequence=signals.observation.sequence,
        evaluated_at=now,
    )


def evaluate_readiness(
    ride_id: UUID,
    signals: ReadinessSignals,
    policy: ReadinessPolicy,
    *,
    now: datetime,
    prior_notification_at: datetime | None = None,
    notification_count: int = 0,
) -> ReadinessDecision:
    reasons: tuple[str, ...]
    insufficient = (
        signals.driver_eta_seconds is None
        or signals.rider_walking_eta_seconds is None
        or signals.rider_location_age_seconds is None
        or signals.rider_location_age_seconds > policy.maximum_location_age_seconds
        or signals.rider_location_accuracy_meters is None
        or signals.rider_location_accuracy_meters > policy.maximum_accuracy_meters
        or signals.pickup_confidence_bps < policy.minimum_confidence_bps
    )
    if insufficient:
        classification = ReadinessClass.INSUFFICIENT_DATA
        confidence = 0
        reasons = ("readiness.data_insufficient",)
    elif signals.within_pickup_zone:
        classification = ReadinessClass.READY
        confidence = min(10_000, signals.pickup_confidence_bps)
        reasons = ("readiness.rider_at_pickup",)
    elif signals.moving_toward_pickup:
        classification = ReadinessClass.MOVING_TO_PICKUP
        confidence = min(9_500, signals.pickup_confidence_bps)
        reasons = ("readiness.moving_toward_pickup",)
    else:
        walking_eta = cast(int, signals.rider_walking_eta_seconds)
        driver_eta = cast(int, signals.driver_eta_seconds)
        difference = walking_eta - driver_eta
        if difference <= 0:
            classification = ReadinessClass.LIKELY_ON_TIME
            confidence = min(9_000, signals.pickup_confidence_bps)
            reasons = ("readiness.walk_eta_within_driver_eta",)
        elif difference <= policy.lateness_margin_seconds:
            classification = ReadinessClass.MAY_BE_LATE
            confidence = min(8_500, signals.pickup_confidence_bps)
            reasons = ("readiness.walk_eta_near_driver_eta",)
        else:
            classification = ReadinessClass.UNLIKELY_ON_TIME
            confidence = min(9_000, signals.pickup_confidence_bps)
            reasons = ("readiness.walk_eta_exceeds_driver_eta",)
        if signals.venue_context_possible:
            reasons = (*reasons, "readiness.venue_context_possible_not_verified")
    cooldown = (
        prior_notification_at is not None
        and (now - prior_notification_at).total_seconds()
        < policy.notification_cooldown_seconds
    )
    capped = notification_count >= policy.maximum_notifications_per_ride
    recommend = (
        classification in {ReadinessClass.MAY_BE_LATE, ReadinessClass.UNLIKELY_ON_TIME}
        and confidence >= policy.notification_confidence_bps
        and not cooldown
        and not capped
        and not signals.connectivity_degraded
    )
    notification_reason = (
        "notification.readiness_recommended"
        if recommend
        else "notification.suppressed_cooldown"
        if cooldown
        else "notification.suppressed_cap"
        if capped
        else "notification.suppressed_connectivity"
        if signals.connectivity_degraded
        else "notification.not_actionable"
    )
    return ReadinessDecision(
        ride_id=ride_id,
        classification=classification,
        confidence_bps=confidence,
        reason_codes=reasons,
        explanation_code=f"readiness.{classification.value}",
        policy_id=policy.policy_id,
        policy_version=policy.version,
        evaluated_at=now,
        expires_at=now + timedelta(seconds=policy.maximum_location_age_seconds),
        notification_recommended=recommend,
        notification_reason_code=notification_reason,
    )


def _matches(
    policy: WaitingPolicyDefinition, context: WaitingPolicyContext, now: datetime
) -> tuple[str, ...] | None:
    if policy.city_code != context.city_code or now < policy.effective_from:
        return None
    if policy.effective_until is not None and now >= policy.effective_until:
        return None
    dimensions: list[str] = ["waiting_policy.context.city"]
    for name in (
        "ride_origin",
        "pickup_context",
        "service_context",
        "assisted",
        "accessibility_accommodation",
        "severe_weather",
        "operational_override_code",
    ):
        expected = getattr(policy, name)
        if expected is not None and expected != getattr(context, name):
            return None
        if expected is not None:
            dimensions.append(f"waiting_policy.context.{name}")
    return tuple(dimensions)


def resolve_waiting_policy(
    ride_id: UUID,
    context: WaitingPolicyContext,
    policies: tuple[WaitingPolicyDefinition, ...],
    *,
    now: datetime,
) -> WaitingPolicySnapshot:
    matches = [
        (policy, dimensions)
        for policy in policies
        if (dimensions := _matches(policy, context, now)) is not None
    ]
    if not matches:
        raise ArrivalWaitingConflict("waiting_policy_unavailable")
    ranked = sorted(
        matches, key=lambda item: (len(item[1]), item[0].priority), reverse=True
    )
    winner, dimensions = ranked[0]
    if len(ranked) > 1 and (len(ranked[1][1]), ranked[1][0].priority) == (
        len(dimensions),
        winner.priority,
    ):
        raise ArrivalWaitingConflict("waiting_policy_ambiguous")
    return WaitingPolicySnapshot(
        ride_id=ride_id,
        source_policy_id=winner.policy_id,
        source_policy_version=winner.version,
        context=context,
        matched_dimensions=dimensions,
        selected_at=now,
        free_wait_seconds=winner.free_wait_seconds,
        ending_warning_seconds=winner.ending_warning_seconds,
        departure_behavior=winner.departure_behavior,
        pause_on_insufficient_quality=winner.pause_on_insufficient_quality,
        maximum_location_age_seconds=winner.maximum_location_age_seconds,
        minimum_location_confidence_bps=winner.minimum_location_confidence_bps,
        reasonable_notification_required=winner.reasonable_notification_required,
    )


def start_waiting(
    ride_id: UUID,
    assignment_id: UUID,
    arrival: ArrivalEvaluation,
    snapshot: WaitingPolicySnapshot,
    *,
    now: datetime,
) -> WaitingSession:
    if arrival.state is not ArrivalState.ARRIVAL_VERIFIED:
        raise ArrivalWaitingConflict("arrival_not_verified")
    if (
        arrival.ride_id != ride_id
        or snapshot.ride_id != ride_id
        or arrival.assignment_id != assignment_id
    ):
        raise ArrivalWaitingConflict("waiting_context_mismatch")
    return WaitingSession(
        ride_id=ride_id,
        assignment_id=assignment_id,
        arrival_evaluation_id=arrival.evaluation_id,
        policy_snapshot_id=snapshot.snapshot_id,
        state=WaitingState.FREE_WAIT_ACTIVE,
        verified_arrival_at=arrival.evaluated_at,
        started_at=now,
        free_wait_deadline=now + timedelta(seconds=snapshot.free_wait_seconds),
        updated_at=now,
        last_observation_sequence=arrival.observation_sequence,
        reason_codes=("waiting.free_wait_started",),
    )


def evaluate_waiting_continuity(
    session: WaitingSession,
    snapshot: WaitingPolicySnapshot,
    signals: ContinuitySignals,
    *,
    observation_sequence: int,
    now: datetime,
) -> WaitingSession:
    if observation_sequence <= session.last_observation_sequence:
        raise ArrivalWaitingConflict("stale_location_observation")
    reasons: list[str] = []
    if not signals.inside_pickup_zone:
        reasons.append("suppression.driver_moved_away")
    if signals.location_age_seconds > snapshot.maximum_location_age_seconds:
        reasons.append("suppression.stale_gps")
    if signals.location_confidence_bps < snapshot.minimum_location_confidence_bps:
        reasons.append("suppression.conflicting_or_low_confidence_gps")
    if signals.unsafe_or_inaccessible:
        reasons.append("suppression.unsafe_or_inaccessible_pickup")
    if signals.platform_failure:
        reasons.append("suppression.platform_failure")
    if signals.map_or_eta_failure:
        reasons.append("suppression.map_or_eta_failure")
    if signals.airport_zone_confusion:
        reasons.append("suppression.airport_zone_confusion")
    if signals.road_closure:
        reasons.append("suppression.road_closure")
    if signals.emergency:
        reasons.append("suppression.emergency")
    if signals.weak_network_uncertainty:
        reasons.append("suppression.weak_network_uncertainty")
    if signals.driver_materially_late:
        reasons.append("suppression.driver_materially_late")
    if not signals.pickup_guidance_valid:
        reasons.append("suppression.incorrect_pickup")
    quality_only = reasons and all(
        reason
        in {
            "suppression.stale_gps",
            "suppression.conflicting_or_low_confidence_gps",
            "suppression.weak_network_uncertainty",
        }
        for reason in reasons
    )
    resumed_pause_seconds = 0
    resumed_deadline = session.free_wait_deadline
    if not reasons and session.state is WaitingState.WAIT_PAUSED:
        if session.paused_at is None:
            raise ArrivalWaitingConflict("waiting_pause_timestamp_missing")
        resumed_pause_seconds = max(0, int((now - session.paused_at).total_seconds()))
        resumed_deadline += timedelta(seconds=resumed_pause_seconds)
    if reasons:
        pause = (
            not signals.inside_pickup_zone
            and snapshot.departure_behavior is DepartureBehavior.PAUSE
        ) or (quality_only and snapshot.pause_on_insufficient_quality)
        state = WaitingState.WAIT_PAUSED if pause else WaitingState.WAIT_INVALIDATED
    elif now >= resumed_deadline:
        state = WaitingState.FREE_WAIT_ENDING
        reasons = ["waiting.free_wait_expired_evaluation_required"]
    elif now >= resumed_deadline - timedelta(seconds=snapshot.ending_warning_seconds):
        state = WaitingState.FREE_WAIT_ENDING
        reasons = ["waiting.free_wait_ending"]
    else:
        state = WaitingState.FREE_WAIT_ACTIVE
        reasons = ["waiting.continuity_verified"]
    return session.model_copy(
        update={
            "state": state,
            "version": session.version + 1,
            "updated_at": now,
            "last_observation_sequence": observation_sequence,
            "reason_codes": tuple(reasons),
            "paused_at": (
                session.paused_at or now if state is WaitingState.WAIT_PAUSED else None
            ),
            "free_wait_deadline": resumed_deadline,
            "total_paused_seconds": session.total_paused_seconds
            + resumed_pause_seconds,
        }
    )


def evaluate_evidence(
    session: WaitingSession,
    snapshot: WaitingPolicySnapshot,
    signals: ContinuitySignals,
    *,
    now: datetime,
) -> EvidenceDecision:
    suppressions: list[str] = []
    if session.state is WaitingState.WAIT_INVALIDATED:
        suppressions.extend(session.reason_codes)
    if now < session.free_wait_deadline:
        suppressions.append("suppression.free_wait_not_expired")
    if not signals.inside_pickup_zone or not signals.driver_available:
        suppressions.append("suppression.driver_moved_away")
    if signals.location_age_seconds > snapshot.maximum_location_age_seconds:
        suppressions.append("suppression.stale_gps")
    if signals.location_confidence_bps < snapshot.minimum_location_confidence_bps:
        suppressions.append("suppression.conflicting_or_low_confidence_gps")
    if (
        snapshot.reasonable_notification_required
        and not signals.reasonable_notification
    ):
        suppressions.append("suppression.notification_failure")
    mapping = {
        "pickup_guidance_valid": "suppression.incorrect_pickup",
        "platform_failure": "suppression.platform_failure",
        "map_or_eta_failure": "suppression.map_or_eta_failure",
        "external_disruption": "suppression.external_disruption",
        "unsafe_or_inaccessible": "suppression.unsafe_or_inaccessible_pickup",
        "airport_zone_confusion": "suppression.airport_zone_confusion",
        "road_closure": "suppression.road_closure",
        "emergency": "suppression.emergency",
        "weak_network_uncertainty": "suppression.weak_network_uncertainty",
        "driver_materially_late": "suppression.driver_materially_late",
    }
    for field, reason in mapping.items():
        value = getattr(signals, field)
        if (field == "pickup_guidance_valid" and not value) or (
            field != "pickup_guidance_valid" and value
        ):
            suppressions.append(reason)
    unique = tuple(dict.fromkeys(suppressions))
    ready = not unique
    responsibility = (
        ResponsibilityClass.RIDER
        if ready
        else ResponsibilityClass.EXTERNAL
        if signals.external_disruption
        else ResponsibilityClass.AYO
        if signals.platform_failure or signals.map_or_eta_failure
        else ResponsibilityClass.DRIVER
        if signals.driver_materially_late or not signals.inside_pickup_zone
        else ResponsibilityClass.INSUFFICIENT
    )
    confidence = signals.location_confidence_bps if ready else 0
    return EvidenceDecision(
        ride_id=session.ride_id,
        session_id=session.session_id,
        ready=ready,
        responsibility=responsibility,
        confidence_bps=confidence,
        reason_codes=("evidence.no_show_ready",)
        if ready
        else ("evidence.consequence_suppressed",),
        suppression_reason_codes=unique,
        explanation_code="evidence.ready_for_review"
        if ready
        else "evidence.suppressed_for_fairness",
        evaluated_at=now,
    )
