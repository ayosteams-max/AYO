from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.field_performance.engine import (
    FieldPerformanceConflict,
    readiness,
    validate_recommendation,
)
from BACKEND.field_performance.models import (
    EvidenceUnit,
    PerformanceEvidence,
    PerformanceMetric,
    PerformanceRecommendation,
    ReadinessAssertion,
    ReadinessRequirement,
    RecommendationKind,
)

NOW = datetime(2026, 7, 21, tzinfo=UTC)
PARTNER = uuid4()
ACTOR = uuid4()


def assertion(
    requirement: ReadinessRequirement,
    *,
    satisfied: bool = True,
    expires_at: datetime | None = None,
) -> ReadinessAssertion:
    return ReadinessAssertion(
        partner_id=PARTNER,
        requirement=requirement,
        satisfied=satisfied,
        source_domain="field.training",
        source_event_id=uuid4(),
        evidence_reference="immutable-readiness-evidence",
        effective_at=NOW - timedelta(days=1),
        expires_at=expires_at,
        recorded_by_identity_id=ACTOR,
        recorded_at=NOW,
    )


def evidence(metric: PerformanceMetric, value: int = 9000) -> PerformanceEvidence:
    return PerformanceEvidence(
        partner_id=PARTNER,
        metric=metric,
        value=value,
        unit=EvidenceUnit.BASIS_POINTS,
        source_domain="field.assistance",
        source_event_id=uuid4(),
        evidence_reference="immutable-performance-evidence",
        window_starts_at=NOW - timedelta(days=30),
        window_ends_at=NOW,
        policy_version="field-quality-v1",
        recorded_by_identity_id=ACTOR,
        recorded_at=NOW,
    )


def test_readiness_fails_closed_until_every_requirement_is_current() -> None:
    complete = tuple(assertion(item) for item in ReadinessRequirement)
    assert readiness(PARTNER, complete, at=NOW).ready is True
    assert readiness(PARTNER, complete[:-1], at=NOW).ready is False
    expired = complete[:-1] + (
        assertion(
            ReadinessRequirement.QUALITY_STANDING, expires_at=NOW - timedelta(seconds=1)
        ),
    )
    result = readiness(PARTNER, expired, at=NOW)
    assert result.ready is False
    assert ReadinessRequirement.QUALITY_STANDING in result.expired


def test_positive_recognition_requires_quality_and_rejects_adverse_evidence() -> None:
    with pytest.raises(FieldPerformanceConflict, match="quality_evidence_required"):
        validate_recommendation(
            RecommendationKind.OUTSTANDING_PERFORMANCE,
            (evidence(PerformanceMetric.VERIFIED_ONBOARDING),),
        )
    with pytest.raises(FieldPerformanceConflict, match="positive_recognition_blocked"):
        validate_recommendation(
            RecommendationKind.CONSISTENT_QUALITY,
            (
                evidence(PerformanceMetric.COMPLETION_QUALITY),
                evidence(PerformanceMetric.FRAUD_RISK, 1),
            ),
        )


def test_recommendation_is_evidenced_and_cannot_become_an_execution() -> None:
    quality = evidence(PerformanceMetric.OWNER_SATISFACTION)
    value = PerformanceRecommendation(
        partner_id=PARTNER,
        kind=RecommendationKind.MENTORING,
        evidence_ids=(quality.evidence_id,),
        confidence_bps=7200,
        reasoning="Evidence suggests focused mentoring may improve documentation quality.",
        risks=("Evidence window is limited.",),
        intelligence_domain="operations.intelligence",
        policy_version="recommendation-v1",
        recommended_by_identity_id=ACTOR,
        created_at=NOW,
    )
    assert value.status == "recommendation_only"
    with pytest.raises(ValidationError):
        value.model_copy(
            update={"status": "approved"}
        )  # frozen-copy bypass is checked below
        PerformanceRecommendation(**{**value.model_dump(), "status": "approved"})


def test_evidence_integrity_rejects_invalid_values_and_naive_time() -> None:
    with pytest.raises(ValidationError):
        evidence(PerformanceMetric.APPROVAL_QUALITY, 10_001)
    with pytest.raises(ValidationError):
        ReadinessAssertion(
            partner_id=PARTNER,
            requirement=ReadinessRequirement.TRAINING_COMPLETE,
            satisfied=True,
            source_domain="field.training",
            source_event_id=uuid4(),
            evidence_reference="immutable-readiness-evidence",
            effective_at=datetime(2026, 1, 1),
            recorded_by_identity_id=ACTOR,
            recorded_at=NOW,
        )


def test_migration_enforces_immutability_idempotency_and_non_execution() -> None:
    source = Path(
        "database/migrations/versions/20260721_0043_field_representative_performance.py"
    ).read_text()
    assert "uq_field_performance_source_metric" in source
    assert "uq_field_performance_idempotency" in source
    assert "status = 'recommendation_only'" in source
    assert "GRANT SELECT,INSERT" in source
    assert "GRANT UPDATE" not in source
    assert "GRANT DELETE" not in source


def test_phase_has_no_financial_or_automatic_promotion_authority() -> None:
    source = "\n".join(
        path.read_text()
        for root in (Path("BACKEND/field_performance"), Path("BACKEND/routes"))
        for path in root.glob("field_performance*.py")
    )
    for forbidden in (
        "wallet",
        "payroll",
        "tax_withholding",
        "bonus_payment",
        "automatic_promotion",
    ):
        assert forbidden not in source.lower()
