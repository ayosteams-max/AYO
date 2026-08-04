from datetime import datetime
from uuid import UUID

from BACKEND.field_performance.models import (
    PerformanceEvidence,
    PerformanceMetric,
    ReadinessAssertion,
    ReadinessRequirement,
    ReadinessView,
    RecommendationKind,
)


class FieldPerformanceConflict(ValueError):
    pass


MANDATORY_READINESS = tuple(ReadinessRequirement)
QUALITY_METRICS = frozenset(
    {
        PerformanceMetric.APPROVAL_QUALITY,
        PerformanceMetric.OWNER_SATISFACTION,
        PerformanceMetric.COMPLETION_QUALITY,
        PerformanceMetric.DOCUMENTATION_QUALITY,
    }
)
ADVERSE_METRICS = frozenset(
    {
        PerformanceMetric.DUPLICATE_ONBOARDING_RISK,
        PerformanceMetric.FRAUD_RISK,
        PerformanceMetric.MISCONDUCT_RISK,
        PerformanceMetric.MISLEADING_MERCHANT_RISK,
        PerformanceMetric.PRESSURE_SELLING_RISK,
        PerformanceMetric.UNRESOLVED_QUALITY_RISK,
    }
)
POSITIVE_RECOGNITION = frozenset(
    {
        RecommendationKind.OUTSTANDING_PERFORMANCE,
        RecommendationKind.CONSISTENT_QUALITY,
        RecommendationKind.EXCELLENT_CUSTOMER_TREATMENT,
        RecommendationKind.EXCEPTIONAL_MERCHANT_SUPPORT,
        RecommendationKind.PROMOTION_CANDIDATE,
        RecommendationKind.LEADERSHIP_CANDIDATE,
    }
)


def readiness(
    partner_id: UUID, assertions: tuple[ReadinessAssertion, ...], *, at: datetime
) -> ReadinessView:
    latest: dict[ReadinessRequirement, ReadinessAssertion] = {}
    for assertion in sorted(assertions, key=lambda value: value.recorded_at):
        latest[assertion.requirement] = assertion
    satisfied = []
    missing = []
    expired = []
    for requirement in MANDATORY_READINESS:
        current = latest.get(requirement)
        if current is None or not current.satisfied:
            missing.append(requirement)
        elif current.expires_at is not None and current.expires_at <= at:
            expired.append(requirement)
        else:
            satisfied.append(requirement)
    return ReadinessView(
        partner_id=partner_id,
        ready=not missing and not expired,
        satisfied=tuple(satisfied),
        missing=tuple(missing),
        expired=tuple(expired),
    )


def validate_recommendation(
    kind: RecommendationKind, evidence: tuple[PerformanceEvidence, ...]
) -> None:
    if not evidence:
        raise FieldPerformanceConflict("performance_recommendation_evidence_required")
    if kind in POSITIVE_RECOGNITION:
        if not any(
            item.metric in QUALITY_METRICS and item.value > 0 for item in evidence
        ):
            raise FieldPerformanceConflict("performance_quality_evidence_required")
        if any(item.metric in ADVERSE_METRICS and item.value > 0 for item in evidence):
            raise FieldPerformanceConflict("performance_positive_recognition_blocked")
