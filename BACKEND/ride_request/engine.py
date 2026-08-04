import re
from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt

from BACKEND.ride_request.models import (
    Coordinate,
    DestinationDefinition,
    MobilityRideRequestState,
    PassengerMobilityRideRequest,
    PickupDefinition,
    PickupSafetyStatus,
    RideRequest,
    RideRequestState,
    ServiceZone,
    ValidationDecision,
    ValidationPolicy,
    ValidationStatus,
)

TRANSITIONS = {
    RideRequestState.DRAFT: frozenset(
        {
            RideRequestState.REQUESTED,
            RideRequestState.CANCELLED,
            RideRequestState.EXPIRED,
        }
    ),
    RideRequestState.REQUESTED: frozenset(
        {
            RideRequestState.VALIDATING,
            RideRequestState.CANCELLED,
            RideRequestState.EXPIRED,
        }
    ),
    RideRequestState.VALIDATING: frozenset(
        {
            RideRequestState.READY_FOR_DISPATCH,
            RideRequestState.VALIDATION_FAILED,
            RideRequestState.CANCELLED,
            RideRequestState.EXPIRED,
        }
    ),
    RideRequestState.READY_FOR_DISPATCH: frozenset(
        {RideRequestState.CANCELLED, RideRequestState.EXPIRED}
    ),
    RideRequestState.VALIDATION_FAILED: frozenset(
        {
            RideRequestState.VALIDATING,
            RideRequestState.CANCELLED,
            RideRequestState.EXPIRED,
        }
    ),
    RideRequestState.CANCELLED: frozenset(),
    RideRequestState.EXPIRED: frozenset(),
}

MOBILITY_TRANSITIONS = {
    MobilityRideRequestState.DRAFT: frozenset(
        {
            MobilityRideRequestState.VALIDATED,
            MobilityRideRequestState.WITHDRAWN,
            MobilityRideRequestState.EXPIRED,
        }
    ),
    MobilityRideRequestState.VALIDATED: frozenset(
        {
            MobilityRideRequestState.SUBMITTED,
            MobilityRideRequestState.WITHDRAWN,
            MobilityRideRequestState.EXPIRED,
        }
    ),
    MobilityRideRequestState.SUBMITTED: frozenset(
        {
            MobilityRideRequestState.WITHDRAWN,
            MobilityRideRequestState.EXPIRED,
        }
    ),
    MobilityRideRequestState.WITHDRAWN: frozenset(),
    MobilityRideRequestState.EXPIRED: frozenset(),
}


def transition_mobility_request(
    request: PassengerMobilityRideRequest,
    target: MobilityRideRequestState,
    *,
    at: datetime,
) -> PassengerMobilityRideRequest:
    if target not in MOBILITY_TRANSITIONS[request.state]:
        raise ValueError("Invalid Passenger Mobility Ride Request transition")
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("Transition timestamp must be timezone-aware")
    return request.model_copy(
        update={
            "state": target,
            "updated_at": at.astimezone(UTC),
            "version": request.version + 1,
        }
    )


def transition(
    request: RideRequest,
    target: RideRequestState,
    *,
    at: datetime,
    cancellation_reason: str | None = None,
) -> RideRequest:
    if target not in TRANSITIONS[request.state]:
        raise ValueError("Invalid ride-request transition")
    if target is RideRequestState.CANCELLED and cancellation_reason is None:
        raise ValueError("Cancellation requires a reason code")
    if (
        cancellation_reason is not None
        and re.fullmatch(r"[a-z][a-z0-9_.-]{2,62}", cancellation_reason) is None
    ):
        raise ValueError("Cancellation reason code is invalid")
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("Transition timestamp must be timezone-aware")
    return request.model_copy(
        update={
            "state": target,
            "updated_at": at,
            "version": request.version + 1,
            "cancellation_reason": cancellation_reason,
        }
    )


def zone_contains(zone: ServiceZone, point: Coordinate, *, at: datetime) -> bool:
    at = at.astimezone(UTC)
    return (
        zone.active_from <= at
        and (zone.active_until is None or at < zone.active_until)
        and zone.min_latitude <= point.latitude <= zone.max_latitude
        and zone.min_longitude <= point.longitude <= zone.max_longitude
    )


def prohibited(zone: ServiceZone, point: Coordinate) -> bool:
    return any(
        a <= point.latitude <= b and c <= point.longitude <= d
        for a, b, c, d in zone.prohibited_rectangles
    )


def separation_metres(a: Coordinate, b: Coordinate) -> float:
    lat1, lat2 = radians(a.latitude), radians(b.latitude)
    dlat, dlon = lat2 - lat1, radians(b.longitude - a.longitude)
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(value))


def validate_request(
    *,
    request: RideRequest,
    pickup: PickupDefinition,
    destination: DestinationDefinition,
    zone: ServiceZone | None,
    policy: ValidationPolicy,
    at: datetime,
    rider_active: bool,
    has_conflicting_request: bool,
) -> ValidationDecision:
    at = at.astimezone(UTC)
    reasons: list[str] = []
    fields: list[str] = []
    freshness = max(0, int((at - pickup.observed_at).total_seconds()))
    if at < policy.effective_from or (
        policy.effective_until is not None and at >= policy.effective_until
    ):
        reasons.append("policy.inactive")
    if not rider_active:
        reasons.append("rider.inactive")
    if (
        zone is None
        or not zone_contains(zone, pickup.coordinate, at=at)
        or request.service_type not in zone.supported_service_types
    ):
        reasons.append("service_zone.unsupported")
        fields.append("pickup.coordinate")
    elif (
        prohibited(zone, pickup.coordinate)
        or pickup.safety_status is PickupSafetyStatus.RESTRICTED
    ):
        reasons.append("pickup.prohibited")
        fields.append("pickup.coordinate")
    if (
        pickup.accuracy_metres is None
        or pickup.accuracy_metres > policy.maximum_accuracy_metres
    ):
        reasons.append("pickup.accuracy_insufficient")
        fields.append("pickup.accuracy_metres")
    if freshness > policy.maximum_observation_age_seconds:
        reasons.append("pickup.observation_stale")
        fields.append("pickup.observed_at")
    if (
        separation_metres(pickup.coordinate, destination.coordinate)
        < policy.minimum_separation_metres
    ):
        reasons.append("destination.too_close")
        fields.append("destination.coordinate")
    if policy.prohibit_multiple_active_requests and has_conflicting_request:
        reasons.append("request.active_conflict")
    return ValidationDecision(
        request_id=request.request_id,
        policy_version=policy.version,
        zone_id=None if zone is None else zone.zone_id,
        zone_version=None if zone is None else zone.version,
        status=ValidationStatus.INVALID if reasons else ValidationStatus.VALID,
        reason_codes=tuple(reasons or ["request.valid"]),
        invalid_fields=tuple(dict.fromkeys(fields)),
        evidence_freshness_seconds=freshness,
        decided_at=at,
    )
