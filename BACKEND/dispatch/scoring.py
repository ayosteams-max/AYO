from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from BACKEND.dispatch.models import (
    DispatchPolicy,
    DispatchRide,
    DispatchScore,
    DriverAvailability,
    DriverCandidate,
)


def eligible_candidates(
    ride: DispatchRide,
    candidates: list[DriverCandidate],
    policy: DispatchPolicy,
    now: datetime,
) -> list[DriverCandidate]:
    result: list[DriverCandidate] = []
    for candidate in candidates[: policy.maximum_candidates]:
        location_age = (now - candidate.location_observed_at).total_seconds()
        if (
            candidate.driver_id in ride.attempted_driver_ids
            or candidate.availability != DriverAvailability.AVAILABLE
            or not candidate.verified
            or not candidate.safety_eligible
            or ride.service_type not in candidate.service_types
            or location_age < 0
            or location_age > policy.maximum_location_age_seconds
        ):
            continue
        result.append(candidate)
    return result


def score_candidates(
    ride: DispatchRide,
    candidates: list[DriverCandidate],
    policy: DispatchPolicy,
    now: datetime,
) -> list[DispatchScore]:
    eligible = eligible_candidates(ride, candidates, policy, now)
    if not eligible:
        return []
    fastest_eta = min(item.pickup_eta_seconds for item in eligible)
    scores: list[DispatchScore] = []
    for candidate in eligible:
        if (
            candidate.pickup_eta_seconds
            > fastest_eta + policy.maximum_fairness_eta_tradeoff_seconds
        ):
            continue
        trust, neutral = candidate.reputation.trust(policy.minimum_reputation_history)
        reliability_penalty = 0
        if not neutral:
            reliability_penalty = int(
                (Decimal("1") - trust) * Decimal(policy.reliability_penalty_seconds)
            )
        fairness_credit = int(
            (
                candidate.opportunity_deficit
                * Decimal(policy.maximum_fairness_eta_tradeoff_seconds)
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        effective_eta = max(
            0,
            candidate.pickup_eta_seconds + reliability_penalty - fairness_credit,
        )
        reasons = ["fast_pickup", "eligible", "policy_versioned"]
        if neutral:
            reasons.append("neutral_reputation")
        if fairness_credit:
            reasons.append("bounded_opportunity_balance")
        if reliability_penalty:
            reasons.append("established_reliability")
        scores.append(
            DispatchScore(
                driver_id=candidate.driver_id,
                pickup_eta_seconds=candidate.pickup_eta_seconds,
                effective_eta_seconds=effective_eta,
                trust_score=trust,
                neutral_reputation=neutral,
                fairness_credit_seconds=fairness_credit,
                reliability_penalty_seconds=reliability_penalty,
                policy_version=policy.version,
                reason_codes=tuple(reasons),
            )
        )
    return sorted(
        scores,
        key=lambda item: (
            item.effective_eta_seconds,
            item.pickup_eta_seconds,
            str(item.driver_id),
        ),
    )
